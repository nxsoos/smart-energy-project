from __future__ import annotations

from typing import Any

from timestamp_utils import TIMEZONE, ms_to_iso


DEFAULT_OCCUPANCY_SETTINGS = {
    "motion_recent_seconds": 90,
    "sound_recent_seconds": 120,
    "occupancy_empty_minutes": 10,
    "sound_activity_threshold": 45,
    "occupancy_confidence_threshold": 0.65,
    "occupancy_history_interval_minutes": 5,
}


def as_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on", "motion", "detected", "noise"}
    return False


def merged_occupancy_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    return {**DEFAULT_OCCUPANCY_SETTINGS, **(settings or {})}


def calculate_occupancy(
    sensor_data: dict[str, Any],
    previous_occupancy: dict[str, Any] | None,
    settings: dict[str, Any] | None,
    breaker_data: dict[str, Any] | None,
    timestamp_ms: int,
) -> dict[str, Any]:
    previous = previous_occupancy or {}
    config = merged_occupancy_settings(settings)
    breakers = breaker_data or {}

    motion_now = as_bool(sensor_data.get("motion"))
    sound_level = as_number(
        sensor_data.get("sound_level", sensor_data.get("sound_raw", sensor_data.get("noise_level"))),
        0,
    )
    sound_active = as_bool(sensor_data.get("noise")) or sound_level >= as_number(
        config.get("sound_activity_threshold"),
        DEFAULT_OCCUPANCY_SETTINGS["sound_activity_threshold"],
    )
    light_status = str(sensor_data.get("light_status", "")).strip().lower()
    light_raw = as_number(sensor_data.get("light_raw"), 0)
    light_on = light_status in {"bright", "on"} or light_raw >= 700

    total_power_w = as_number(
        breakers.get("total_power_W", breakers.get("current_power_w", breakers.get("total_avg_power_W"))),
        0,
    )
    device_power_active = total_power_w > 10

    last_motion_at_ms = (
        timestamp_ms
        if motion_now
        else int(as_number(previous.get("last_motion_at_ms"), 0)) or None
    )
    last_sound_at_ms = (
        timestamp_ms
        if sound_active
        else int(as_number(previous.get("last_sound_at_ms"), 0)) or None
    )
    activity_candidates = [
        value for value in [last_motion_at_ms, last_sound_at_ms] if isinstance(value, int) and value > 0
    ]
    last_activity_at_ms = max(activity_candidates) if activity_candidates else None

    motion_recent = (
        isinstance(last_motion_at_ms, int)
        and timestamp_ms - last_motion_at_ms <= int(as_number(config.get("motion_recent_seconds"), 90) * 1000)
    )
    sound_recent = (
        isinstance(last_sound_at_ms, int)
        and timestamp_ms - last_sound_at_ms <= int(as_number(config.get("sound_recent_seconds"), 120) * 1000)
    )

    minutes_since_last_activity = (
        round((timestamp_ms - last_activity_at_ms) / 60000, 2)
        if isinstance(last_activity_at_ms, int)
        else None
    )

    score = 0.0
    reasons: list[str] = []
    if motion_now:
        score += 0.80
        reasons.append("Motion detected now")
    elif motion_recent:
        score += 0.60
        reasons.append("Recent motion detected")
    if sound_active:
        score += 0.40
        reasons.append("Sound activity detected")
    elif sound_recent:
        score += 0.30
        reasons.append("Recent sound activity detected")
    if device_power_active:
        score += 0.10
    if light_on:
        score += 0.05

    if not motion_now:
        score = min(score, 0.74)
    confidence = min(1.0, round(score, 2))
    empty_after_minutes = as_number(config.get("occupancy_empty_minutes"), 10)
    activity_timed_out = (
        minutes_since_last_activity is None
        or minutes_since_last_activity >= empty_after_minutes
    )

    if not sensor_data:
        state = "unknown"
        occupied = False
        confidence = 0.0
        reason = "Sensor data missing or outdated"
    elif confidence >= 0.75:
        state = "occupied"
        occupied = True
        reason = reasons[0] if reasons else "Strong occupancy evidence detected"
    elif confidence >= 0.45:
        state = "probably_occupied"
        occupied = True
        reason = reasons[0] if reasons else "Recent activity detected"
    elif activity_timed_out:
        state = "empty"
        occupied = False
        reason = f"No motion or sound activity for {int(empty_after_minutes)} minutes"
    else:
        state = "probably_empty"
        occupied = False
        reason = "No current motion or sound activity"

    return {
        "room_id": "room1",
        "state": state,
        "occupied": occupied,
        "confidence": confidence,
        "reason": reason,
        "last_activity_at_ms": last_activity_at_ms,
        "last_activity_at_iso": ms_to_iso(last_activity_at_ms),
        "last_motion_at_ms": last_motion_at_ms,
        "last_motion_at_iso": ms_to_iso(last_motion_at_ms),
        "last_sound_at_ms": last_sound_at_ms,
        "last_sound_at_iso": ms_to_iso(last_sound_at_ms),
        "motion_now": motion_now,
        "sound_active": sound_active,
        "motion_recent": motion_recent,
        "sound_recent": sound_recent,
        "light_on": light_on,
        "device_power_active": device_power_active,
        "minutes_since_last_activity": minutes_since_last_activity,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": ms_to_iso(timestamp_ms),
        "timezone": TIMEZONE,
    }


def should_write_occupancy_history(
    previous_occupancy: dict[str, Any] | None,
    latest_history: dict[str, Any] | None,
    new_occupancy: dict[str, Any],
    settings: dict[str, Any] | None,
    timestamp_ms: int,
) -> bool:
    previous_state = (previous_occupancy or {}).get("state")
    if previous_state != new_occupancy.get("state"):
        return True
    interval_minutes = as_number(
        (settings or {}).get("occupancy_history_interval_minutes"),
        DEFAULT_OCCUPANCY_SETTINGS["occupancy_history_interval_minutes"],
    )
    last_history_at = as_number((latest_history or {}).get("updated_at_ms"), 0)
    return last_history_at <= 0 or timestamp_ms - int(last_history_at) >= interval_minutes * 60 * 1000
