from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


TIMEZONE = "Asia/Bahrain"
BAHRAIN_TZ = ZoneInfo(TIMEZONE)


def now_ms() -> int:
    return int(time.time() * 1000)


def now_iso() -> str:
    return datetime.now(BAHRAIN_TZ).isoformat()


def now_timestamp() -> dict[str, Any]:
    timestamp_ms = now_ms()
    return {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": ms_to_iso(timestamp_ms),
        "timezone": TIMEZONE,
    }


def ms_to_iso(timestamp_ms: Any) -> str | None:
    if not isinstance(timestamp_ms, (int, float)) or timestamp_ms <= 0:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=BAHRAIN_TZ).isoformat()


def iso_to_ms(timestamp_iso: str) -> int | None:
    if not isinstance(timestamp_iso, str) or not timestamp_iso.strip():
        return None
    try:
        parsed = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BAHRAIN_TZ)
    return int(parsed.timestamp() * 1000)
