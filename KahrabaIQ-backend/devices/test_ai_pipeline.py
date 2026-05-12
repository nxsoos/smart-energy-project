from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from devices.ai_pipeline import (
    add_engineered_features,
    generate_synthetic_scenario_rows,
    label_row,
    split_grouped_by_variant,
)


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(name)


def synthetic_rows(count: int = 40) -> list[dict]:
    base = 1770000000000
    rows = []
    for index in range(count):
        empty_waste = index % 6 == 0
        rows.append(
            {
                "record_id": f"row_{index}",
                "timestamp_ms": base + index * 60 * 60 * 1000,
                "sample_count": 60,
                "avg_temperature": 26 + (index % 5),
                "avg_humidity": 50,
                "avg_sound_raw": 300,
                "motion_count": 0 if empty_waste else 8,
                "bright_count": 12,
                "smoke_count": 0,
                "noise_count": 0,
                "high_temp_count": 0,
                "occupancy_score": 0.0 if empty_waste else 0.7,
                "switch_avg_power_W": 45 if empty_waste else 4,
                "switch_peak_power_W": 80 if empty_waste else 8,
                "switch_energy_kWh": 0.045 if empty_waste else 0.004,
                "ac_avg_power_W": 0,
                "ac_peak_power_W": 0,
                "ac_energy_kWh": 0,
                "total_avg_power_W": 45 if empty_waste else 4,
                "total_peak_power_W": 80 if empty_waste else 8,
                "total_energy_kWh": 0.045 if empty_waste else 0.004,
                "total_cost_BHD": 0.00144 if empty_waste else 0.000128,
                "tariff_BHD_per_kWh": 0.032,
            }
        )
    return rows


def run() -> None:
    smoke = label_row({"smoke_count": 1})
    check("smoke rule is safety-first", smoke["anomaly_label"] == "smoke_gas_safety")
    stale = label_row({"sensor_stale_flag": True})
    check("stale sensor gets data recommendation", stale["recommendation_type"] == "check_sensor_connection")
    socket = label_row({"occupancy_score": 0.0, "switch_avg_power_W": 40, "total_avg_power_W": 40})
    check("socket left on is waste", socket["waste_event"] is True and socket["anomaly_label"] == "socket_left_on")

    data = add_engineered_features(pd.DataFrame(synthetic_rows()))
    check("next-hour regression target exists", "next_hour_total_energy_kWh" in data.columns)
    check("rolling feature exists", "rolling_24h_power_avg" in data.columns)
    check("same-hour z-score exists", "same_hour_power_z_score" in data.columns)
    check("manual weak label exists", data["recommendation_type"].notna().all())
    train, validation, test = split_grouped_by_variant(data)
    check("time split preserves row count", len(train) + len(validation) + len(test) == len(data))
    check("time split has all partitions", len(train) > 0 and len(validation) > 0 and len(test) > 0)
    check("train is oldest", train["timestamp_ms"].max() <= validation["timestamp_ms"].min())
    check("test is newest", validation["timestamp_ms"].max() <= test["timestamp_ms"].min())

    synthetic = add_engineered_features(pd.DataFrame(generate_synthetic_scenario_rows(120, seed=7)))
    check("synthetic origin is present", set(synthetic["data_origin"]) == {"synthetic_scenario"})
    check("synthetic families are varied", synthetic["scenario_family"].nunique() >= 8)
    s_train, s_validation, s_test = split_grouped_by_variant(synthetic)
    train_variants = set(s_train["scenario_variant_id"])
    validation_variants = set(s_validation["scenario_variant_id"])
    test_variants = set(s_test["scenario_variant_id"])
    check("variant train/test split has no leakage", train_variants.isdisjoint(test_variants))
    check("variant validation/test split has no leakage", validation_variants.isdisjoint(test_variants))
    check("test includes unseen synthetic variants", len(test_variants) > 0)


if __name__ == "__main__":
    run()
