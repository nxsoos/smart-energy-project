from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from occupancy_utils import calculate_occupancy


BASE_SETTINGS = {
    "motion_recent_seconds": 90,
    "sound_recent_seconds": 120,
    "occupancy_empty_minutes": 10,
    "sound_activity_threshold": 45,
    "occupancy_history_interval_minutes": 5,
}


def check(name: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected}, got {actual}")
    print(f"{name}: {actual}")


def run() -> None:
    now = 1770000000000

    occupied = calculate_occupancy(
        {"motion": 1, "sound_raw": 12, "light_status": "Dark"},
        {},
        BASE_SETTINGS,
        {"total_power_W": 0},
        now,
    )
    check("occupied room", occupied["state"], "occupied")

    still_person = calculate_occupancy(
        {"motion": 0, "sound_raw": 70, "light_status": "Dark"},
        occupied,
        BASE_SETTINGS,
        {"total_power_W": 0},
        now + 30_000,
    )
    check("still person", still_person["state"], "probably_occupied")

    false_no_motion = calculate_occupancy(
        {"motion": 0, "sound_raw": 0, "light_status": "Dark"},
        still_person,
        BASE_SETTINGS,
        {"total_power_W": 0},
        now + 60_000,
    )
    check("false no-motion case", false_no_motion["state"], "probably_occupied")

    empty = calculate_occupancy(
        {"motion": 0, "sound_raw": 0, "light_status": "Dark"},
        still_person,
        BASE_SETTINGS,
        {"total_power_W": 0},
        now + 11 * 60_000,
    )
    check("empty room", empty["state"], "empty")

    light_waste = calculate_occupancy(
        {"motion": 0, "sound_raw": 0, "light_status": "Bright"},
        empty,
        BASE_SETTINGS,
        {"total_power_W": 85},
        now + 12 * 60_000,
    )
    check("light waste occupancy", light_waste["state"], "empty")
    if not light_waste["light_on"] or not light_waste["device_power_active"]:
        raise AssertionError("light waste: expected light and device activity")

    missing = calculate_occupancy({}, {}, BASE_SETTINGS, {}, now)
    check("missing sensor data", missing["state"], "unknown")


if __name__ == "__main__":
    run()
