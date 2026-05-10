from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from aws_cloud_store import query_summaries_between


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "ai_ready_dataset_60_days.csv"
DEFAULT_HOME_ID = "home_001"


def as_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def label_row(row: dict[str, Any]) -> dict[str, Any]:
    smoke = as_number(row.get("smoke_count")) > 0
    low_occupancy = as_number(row.get("occupancy_score")) < 0.2
    high_power = as_number(row.get("total_avg_power_W")) > 100
    ac_active = as_number(row.get("ac_avg_power_W")) > 50

    if smoke:
        return {
            "waste_event": False,
            "anomaly_label": "safety_smoke_gas_warning",
            "recommendation_type": "check_smoke_gas_sensor",
        }
    if low_occupancy and high_power:
        return {
            "waste_event": True,
            "anomaly_label": "high_power_while_empty",
            "recommendation_type": "turn_off_unused_devices",
        }
    if ac_active and low_occupancy:
        return {
            "waste_event": True,
            "anomaly_label": "ac_running_while_empty",
            "recommendation_type": "turn_off_ac",
        }
    return {"waste_event": False, "anomaly_label": "normal", "recommendation_type": "none"}


def row_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    sensor = as_dict(summary.get("sensorSummary"))
    occupancy = as_dict(summary.get("occupancySummary"))
    breakers = as_dict(summary.get("breakerSummaries"))
    switch = as_dict(breakers.get("breaker_01"))
    ac = as_dict(breakers.get("breaker_02"))
    sample_count = as_number(sensor.get("sampleCount"), 1)
    occupied_count = as_number(occupancy.get("occupiedCount"))
    total_power = as_number(switch.get("avgPowerW")) + as_number(ac.get("avgPowerW"))
    row = {
        "record_id": summary.get("summaryId") or summary.get("SK"),
        "timestamp_ms": summary.get("startAtMs"),
        "data_source": "hourly_summary",
        "sample_count": sample_count,
        "avg_temperature": sensor.get("avgTemperatureC"),
        "avg_humidity": sensor.get("avgHumidity"),
        "avg_sound_raw": sensor.get("avgSoundRaw"),
        "motion_count": sensor.get("motionDetectedCount"),
        "bright_count": sensor.get("brightCount", 0),
        "smoke_count": sensor.get("smokeDetectedCount"),
        "noise_count": sensor.get("noiseCount", 0),
        "high_temp_count": sensor.get("highTempCount", 0),
        "occupancy_score": min(1.0, occupied_count / sample_count) if sample_count > 0 else 0,
        "switch_avg_power_W": switch.get("avgPowerW"),
        "switch_peak_power_W": switch.get("peakPowerW"),
        "switch_energy_kWh": switch.get("energyDeltaKwh"),
        "ac_avg_power_W": ac.get("avgPowerW"),
        "ac_peak_power_W": ac.get("peakPowerW"),
        "ac_energy_kWh": ac.get("energyDeltaKwh"),
        "total_avg_power_W": total_power,
        "total_peak_power_W": max(as_number(switch.get("peakPowerW")), as_number(ac.get("peakPowerW"))),
        "total_energy_kWh": summary.get("totalEnergyKwh"),
        "total_cost_BHD": as_number(summary.get("totalEnergyKwh")) * 0.032,
        "tariff_BHD_per_kWh": 0.032,
    }
    row.update(label_row(row))
    return row


def build(home_id: str = DEFAULT_HOME_ID, limit: int = 1440) -> Path:
    summaries = query_summaries_between(home_id, "hourly", limit=limit)
    rows = [row_from_summary(summary) for summary in reversed(summaries)]
    if not rows:
        raise RuntimeError("No hourly summaries found. Sync Pi summaries before building the dataset.")
    fieldnames = list(rows[0].keys())
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return OUTPUT_PATH


if __name__ == "__main__":
    print(f"Wrote dataset: {build()}")
