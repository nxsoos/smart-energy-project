from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SMART_ENERGY_LOCAL_DB", BASE_DIR / "smart_energy_local.sqlite3"))
_LOCK = threading.RLock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
