from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(
    os.environ.get("LOCAL_STATE_DB_PATH")
    or os.environ.get("SMART_ENERGY_LOCAL_DB")
    or BASE_DIR / "smart_energy_local.sqlite3"
)
_LOCK = threading.RLock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=float(os.environ.get("LOCAL_SQLITE_BUSY_TIMEOUT_SECONDS", "30")))
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS state (
            path TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at_ms INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            category TEXT NOT NULL,
            record_id TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at_ms INTEGER NOT NULL,
            PRIMARY KEY (category, record_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS summaries (
            summary_id TEXT PRIMARY KEY,
            home_id TEXT NOT NULL,
            period TEXT NOT NULL,
            start_at_ms INTEGER NOT NULL,
            end_at_ms INTEGER NOT NULL,
            value TEXT NOT NULL,
            created_at_ms INTEGER NOT NULL,
            updated_at_ms INTEGER NOT NULL,
            synced_at_ms INTEGER,
            sync_error TEXT
        )
        """
    )
    return conn


def _normalize(path: str) -> str:
    return "/".join(part for part in str(path or "").strip("/").split("/") if part)


def _parent_and_child(path: str) -> tuple[str, str]:
    normalized = _normalize(path)
    if not normalized:
        return "", ""
    parts = normalized.rsplit("/", 1)
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], parts[1]


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _decode(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def get_path(path: str, default: Any = None) -> Any:
    normalized = _normalize(path)
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT value FROM state WHERE path = ?", (normalized,)).fetchone()
        if row:
            return _decode(row[0])

        prefix = f"{normalized}/" if normalized else ""
        rows = conn.execute(
            "SELECT path, value FROM state WHERE path LIKE ?",
            (f"{prefix}%",),
        ).fetchall()

    if not rows:
        return default

    root: dict[str, Any] = {}
    for child_path, raw_value in rows:
        remainder = child_path[len(prefix) :] if prefix else child_path
        if not remainder:
            continue
        parts = remainder.split("/")
        current = root
        for part in parts[:-1]:
            current = current.setdefault(part, {})
            if not isinstance(current, dict):
                break
        else:
            current[parts[-1]] = _decode(raw_value)
    return root if root else default


def set_path(path: str, value: Any) -> None:
    normalized = _normalize(path)
    with _LOCK, _connect() as conn:
        if value is None:
            prefix = f"{normalized}/" if normalized else ""
            conn.execute("DELETE FROM state WHERE path = ?", (normalized,))
            if prefix:
                conn.execute("DELETE FROM state WHERE path LIKE ?", (f"{prefix}%",))
            return
        conn.execute(
            "REPLACE INTO state(path, value, updated_at_ms) VALUES (?, ?, ?)",
            (normalized, json.dumps(value, separators=(",", ":"), default=str), _now_ms()),
        )


def update_path(path: str, updates: dict[str, Any]) -> None:
    current = get_path(path, {})
    if not isinstance(current, dict):
        current = {}
    merged = {**current, **updates}
    for key, value in updates.items():
        if value is None and key in merged:
            merged.pop(key, None)
    set_path(path, merged)


def delete_path(path: str) -> None:
    normalized = _normalize(path)
    prefix = f"{normalized}/" if normalized else ""
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM state WHERE path = ?", (normalized,))
        if prefix:
            conn.execute("DELETE FROM state WHERE path LIKE ?", (f"{prefix}%",))


def add_history(category: str, record_id: str, value: dict[str, Any], max_records: int = 5000) -> None:
    created_at_ms = int(value.get("timestamp_ms") or value.get("created_at_ms") or _now_ms())
    with _LOCK, _connect() as conn:
        conn.execute(
            "REPLACE INTO history(category, record_id, value, created_at_ms) VALUES (?, ?, ?, ?)",
            (
                category,
                str(record_id),
                json.dumps(value, separators=(",", ":"), default=str),
                created_at_ms,
            ),
        )
        stale = conn.execute(
            """
            SELECT record_id FROM history
            WHERE category = ?
            ORDER BY created_at_ms DESC
            LIMIT -1 OFFSET ?
            """,
            (category, max_records),
        ).fetchall()
        if stale:
            conn.executemany(
                "DELETE FROM history WHERE category = ? AND record_id = ?",
                [(category, row[0]) for row in stale],
            )


def latest_history(category: str) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            """
            SELECT value FROM history
            WHERE category = ?
            ORDER BY created_at_ms DESC
            LIMIT 1
            """,
            (category,),
        ).fetchone()
    return _decode(row[0]) if row else {}


def history_between(category: str, start_at_ms: int, end_at_ms: int) -> list[dict[str, Any]]:
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            """
            SELECT value FROM history
            WHERE category = ?
              AND created_at_ms >= ?
              AND created_at_ms < ?
            ORDER BY created_at_ms ASC
            """,
            (category, int(start_at_ms), int(end_at_ms)),
        ).fetchall()
    return [value for row in rows if isinstance((value := _decode(row[0])), dict)]


def upsert_summary(
    summary_id: str,
    home_id: str,
    period: str,
    start_at_ms: int,
    end_at_ms: int,
    value: dict[str, Any],
) -> None:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)
    now = _now_ms()
    with _LOCK, _connect() as conn:
        existing = conn.execute(
            "SELECT value, synced_at_ms FROM summaries WHERE summary_id = ?",
            (summary_id,),
        ).fetchone()
        synced_at_ms = existing[1] if existing and existing[0] == encoded else None
        created_at_ms = now
        if existing:
            created = conn.execute(
                "SELECT created_at_ms FROM summaries WHERE summary_id = ?",
                (summary_id,),
            ).fetchone()
            created_at_ms = int(created[0]) if created else now
        conn.execute(
            """
            REPLACE INTO summaries(
                summary_id, home_id, period, start_at_ms, end_at_ms, value,
                created_at_ms, updated_at_ms, synced_at_ms, sync_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary_id,
                home_id,
                period,
                int(start_at_ms),
                int(end_at_ms),
                encoded,
                created_at_ms,
                now,
                synced_at_ms,
                None if synced_at_ms else "",
            ),
        )


def pending_summaries(limit: int = 25) -> list[dict[str, Any]]:
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            """
            SELECT summary_id, home_id, period, start_at_ms, end_at_ms, value,
                   created_at_ms, updated_at_ms
            FROM summaries
            WHERE synced_at_ms IS NULL
            ORDER BY start_at_ms ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    summaries = []
    for row in rows:
        value = _decode(row[5])
        if not isinstance(value, dict):
            continue
        summaries.append(
            {
                "summary_id": row[0],
                "home_id": row[1],
                "period": row[2],
                "start_at_ms": row[3],
                "end_at_ms": row[4],
                "value": value,
                "created_at_ms": row[6],
                "updated_at_ms": row[7],
            }
        )
    return summaries


def summaries_between(period: str, start_at_ms: int, end_at_ms: int) -> list[dict[str, Any]]:
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            """
            SELECT value FROM summaries
            WHERE period = ?
              AND start_at_ms >= ?
              AND end_at_ms <= ?
            ORDER BY start_at_ms ASC
            """,
            (period, int(start_at_ms), int(end_at_ms)),
        ).fetchall()
    return [value for row in rows if isinstance((value := _decode(row[0])), dict)]


def cleanup_old_data(retention_days: int = 7) -> dict[str, int]:
    days = max(1, int(retention_days or 7))
    cutoff_ms = _now_ms() - days * 24 * 60 * 60 * 1000
    with _LOCK, _connect() as conn:
        history_deleted = conn.execute(
            "DELETE FROM history WHERE created_at_ms < ?",
            (cutoff_ms,),
        ).rowcount
        summaries_deleted = conn.execute(
            """
            DELETE FROM summaries
            WHERE end_at_ms < ?
              AND synced_at_ms IS NOT NULL
            """,
            (cutoff_ms,),
        ).rowcount
        conn.execute("PRAGMA optimize")
    return {
        "cutoff_ms": cutoff_ms,
        "history_deleted": max(0, history_deleted),
        "summaries_deleted": max(0, summaries_deleted),
    }


def mark_summary_synced(summary_id: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            UPDATE summaries
            SET synced_at_ms = ?, sync_error = NULL
            WHERE summary_id = ?
            """,
            (_now_ms(), summary_id),
        )


def mark_summary_sync_failed(summary_id: str, error: Any) -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            UPDATE summaries
            SET sync_error = ?
            WHERE summary_id = ?
            """,
            (str(error)[:1000], summary_id),
        )


class LocalReference:
    def __init__(self, path: str = "") -> None:
        self.path = _normalize(path)

    def child(self, child_path: str) -> "LocalReference":
        return LocalReference(f"{self.path}/{child_path}" if self.path else child_path)

    def get(self) -> Any:
        return get_path(self.path)

    def set(self, value: Any) -> None:
        set_path(self.path, value)

    def update(self, value: dict[str, Any]) -> None:
        update_path(self.path, value)

    def delete(self) -> None:
        delete_path(self.path)


def home_ref(home_id: str, path: str = "") -> LocalReference:
    root = f"homes/{home_id}"
    return LocalReference(f"{root}/{path}" if path else root)


def home_snapshot(home_id: str) -> dict[str, Any]:
    value = get_path(f"homes/{home_id}", {})
    return value if isinstance(value, dict) else {}
