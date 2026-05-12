from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "datasets"
MODEL_DIR = BASE_DIR / "models"
LEGACY_DATASET_PATH = BASE_DIR / "ai_ready_dataset_60_days.csv"
FULL_DATASET_PATH = DATASET_DIR / "ai_dataset_full.csv"
TRAIN_DATASET_PATH = DATASET_DIR / "ai_dataset_train.csv"
VALIDATION_DATASET_PATH = DATASET_DIR / "ai_dataset_validation.csv"
TEST_DATASET_PATH = DATASET_DIR / "ai_dataset_test.csv"
DATASET_METADATA_PATH = DATASET_DIR / "ai_dataset_metadata.json"
MANUAL_LABELS_PATH = DATASET_DIR / "manual_labels.csv"
MODEL_PATH = MODEL_DIR / "smart_energy_ai.joblib"
METRICS_PATH = MODEL_DIR / "smart_energy_ai_metrics.json"
EVALUATION_REPORT_PATH = MODEL_DIR / "smart_energy_ai_evaluation_report.md"
CONFUSION_MATRICES_PATH = MODEL_DIR / "smart_energy_ai_confusion_matrices.json"
FEATURE_IMPORTANCE_PATH = MODEL_DIR / "smart_energy_ai_feature_importance.csv"

LABEL_RULE_VERSION = "weak_rules_v2"
MODEL_VERSION = "2"
TARIFF_BHD_PER_KWH = 0.032

CLASSIFICATION_TARGETS = ["waste_event", "anomaly_label", "recommendation_type"]
REGRESSION_TARGETS = ["next_hour_total_energy_kWh", "next_hour_total_cost_BHD"]
TARGET_COLUMNS = CLASSIFICATION_TARGETS + REGRESSION_TARGETS
IDENTIFIER_COLUMNS = {
    "record_id",
    "timestamp_ms",
    "datetime_bahrain",
    "date",
    "data_source",
    "data_origin",
    "scenario_family",
    "scenario_variant_id",
    "synthetic_same_hour_energy_avg_hint",
    "synthetic_rolling_energy_avg_hint",
    "synthetic_same_hour_power_avg_hint",
    "synthetic_rolling_power_avg_hint",
    "split",
    "label_rule_version",
}
SPECIAL_RECALL_CLASSES = [
    "smoke_gas_safety",
    "safety_smoke_gas_warning",
    "high_power_empty_room",
    "high_power_while_empty",
    "ac_running_empty_room",
    "ac_running_while_empty",
    "socket_left_on",
    "unusual_same_hour_usage",
]


def as_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        return default if math.isnan(number) else number
    try:
        number = float(value)
        return default if math.isnan(number) else number
    except (TypeError, ValueError):
        return default


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_present(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return default


def safe_ratio(numerator: Any, denominator: Any, default: float = 0.0) -> float:
    denominator_number = as_number(denominator)
    if denominator_number <= 0:
        return default
    return as_number(numerator) / denominator_number


def timestamp_to_datetime(timestamp_ms: Any) -> pd.Timestamp:
    timestamp = as_number(timestamp_ms)
    if timestamp <= 0:
        return pd.Timestamp.utcnow()
    return pd.to_datetime(int(timestamp), unit="ms", utc=True)


def day_part(hour: int) -> str:
    if 5 <= hour <= 11:
        return "morning"
    if 12 <= hour <= 16:
        return "afternoon"
    if 17 <= hour <= 21:
        return "evening"
    return "night"


def normalize_state(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"on", "true", "1", "open", "active"}:
        return "on"
    if text in {"off", "false", "0", "closed", "inactive"}:
        return "off"
    return "unknown"


def state_on_flag(*values: Any) -> int:
    return 1 if any(normalize_state(value) == "on" for value in values) else 0


def label_row(row: dict[str, Any]) -> dict[str, Any]:
    smoke = as_number(row.get("smoke_count")) > 0 or as_number(row.get("smoke_rate")) > 0
    sensor_stale = bool(row.get("sensor_stale_flag"))
    breaker_stale = bool(row.get("breaker_stale_flag"))
    hub_offline = bool(row.get("hub_offline_flag"))
    occupancy_score = as_number(row.get("occupancy_score"))
    low_occupancy = occupancy_score < 0.2 or as_number(row.get("empty_room_duration_minutes")) >= 30
    total_power = max(as_number(row.get("total_avg_power_W")), as_number(row.get("total_power_for_guardrails_W")))
    ac_power = max(as_number(row.get("ac_avg_power_W")), as_number(row.get("ac_live_power_W")))
    socket_power = max(as_number(row.get("switch_avg_power_W")), as_number(row.get("switch_live_power_W")))
    high_power = total_power > 100
    power_spike = as_number(row.get("power_z_score_24h")) >= 2.0 or as_number(row.get("same_hour_power_z_score")) >= 2.0
    energy_spike = as_number(row.get("energy_z_score_24h")) >= 2.0 or as_number(row.get("same_hour_energy_z_score")) >= 2.0
    high_temp = as_number(row.get("high_temp_count")) > 0 or as_number(row.get("avg_temperature")) >= 30
    noisy_possible_occupancy = as_number(row.get("noise_rate")) > 0.35 and occupancy_score < 0.2
    routine_change = as_number(row.get("routine_deviation_score")) > 0.8
    night_left_on = bool(row.get("is_night")) and total_power > 30 and low_occupancy

    if smoke:
        return {
            "waste_event": False,
            "anomaly_label": "smoke_gas_safety",
            "recommendation_type": "check_smoke_gas_sensor",
        }
    if hub_offline:
        return {
            "waste_event": False,
            "anomaly_label": "hub_offline_or_stale",
            "recommendation_type": "wait_for_fresh_data",
        }
    if sensor_stale:
        return {
            "waste_event": False,
            "anomaly_label": "possible_sensor_stale",
            "recommendation_type": "check_sensor_connection",
        }
    if breaker_stale:
        return {
            "waste_event": False,
            "anomaly_label": "possible_breaker_stale",
            "recommendation_type": "check_breaker_connection",
        }
    if low_occupancy and ac_power > 50:
        return {
            "waste_event": True,
            "anomaly_label": "ac_running_empty_room",
            "recommendation_type": "turn_off_or_adjust_ac",
        }
    if low_occupancy and socket_power > 15:
        return {
            "waste_event": True,
            "anomaly_label": "socket_left_on",
            "recommendation_type": "turn_off_unused_socket",
        }
    if low_occupancy and high_power:
        return {
            "waste_event": True,
            "anomaly_label": "high_power_empty_room",
            "recommendation_type": "turn_off_unused_socket",
        }
    if energy_spike:
        return {
            "waste_event": total_power > 50,
            "anomaly_label": "unusual_same_hour_usage",
            "recommendation_type": "review_unusual_usage",
        }
    if power_spike:
        return {
            "waste_event": total_power > 80,
            "anomaly_label": "sudden_power_spike",
            "recommendation_type": "reduce_peak_load",
        }
    if night_left_on:
        return {
            "waste_event": True,
            "anomaly_label": "socket_left_on",
            "recommendation_type": "turn_off_unused_socket",
        }
    if high_temp:
        return {
            "waste_event": False,
            "anomaly_label": "high_temperature_comfort",
            "recommendation_type": "verify_occupancy",
        }
    if noisy_possible_occupancy:
        return {
            "waste_event": False,
            "anomaly_label": "noisy_room_possible_occupancy",
            "recommendation_type": "verify_occupancy",
        }
    if routine_change:
        return {
            "waste_event": False,
            "anomaly_label": "routine_change",
            "recommendation_type": "review_unusual_usage",
        }
    if total_power <= 5:
        return {
            "waste_event": False,
            "anomaly_label": "low_usage_normal",
            "recommendation_type": "keep_monitoring",
        }
    return {
        "waste_event": False,
        "anomaly_label": "normal",
        "recommendation_type": "keep_monitoring",
    }


def breaker_summary(summary: dict[str, Any], *device_ids: str) -> dict[str, Any]:
    breakers = as_dict(summary.get("breakerSummaries"))
    energy = as_dict(summary.get("energy"))
    branches = as_dict(energy.get("branches"))
    for device_id in device_ids:
        candidate = as_dict(breakers.get(device_id)) or as_dict(branches.get(device_id))
        if candidate:
            return candidate
    return {}


def row_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    sensor = as_dict(summary.get("sensorSummary"))
    occupancy = as_dict(summary.get("occupancySummary"))
    switch = breaker_summary(summary, "breaker_01", "socket_breaker", "matter_socket_switch")
    ac = breaker_summary(summary, "breaker_02", "ac_breaker", "matter_ac_switch")
    timestamp_ms = first_present(summary.get("startAtMs"), summary.get("start_at_ms"), summary.get("timestamp_ms"))
    dt = timestamp_to_datetime(timestamp_ms)
    sample_count = max(1.0, as_number(first_present(sensor.get("sampleCount"), occupancy.get("sampleCount"), summary.get("sample_count")), 1))
    occupied_count = as_number(first_present(occupancy.get("occupiedCount"), occupancy.get("occupied_count")))
    motion_count = as_number(first_present(sensor.get("motionDetectedCount"), summary.get("motion_count"), occupied_count))
    smoke_count = as_number(first_present(sensor.get("smokeDetectedCount"), summary.get("smoke_count")))
    noise_count = as_number(first_present(sensor.get("noiseCount"), summary.get("noise_count")))
    high_temp_count = as_number(first_present(sensor.get("highTempCount"), summary.get("high_temp_count")))
    bright_count = as_number(first_present(sensor.get("brightCount"), summary.get("bright_count")))
    switch_power = as_number(first_present(switch.get("avgPowerW"), switch.get("avg_power_W"), switch.get("power")))
    ac_power = as_number(first_present(ac.get("avgPowerW"), ac.get("avg_power_W"), ac.get("power")))
    total_avg_power = as_number(
        first_present(
            summary.get("total_avg_power_W"),
            as_dict(summary.get("energy")).get("total_avg_power_W"),
            switch_power + ac_power,
        )
    )
    total_energy = as_number(
        first_present(
            summary.get("totalEnergyKwh"),
            summary.get("total_energy_kWh"),
            as_dict(summary.get("energy")).get("total_energy_kWh"),
            as_dict(summary.get("energy")).get("total_estimated_energy_kWh"),
        )
    )
    row = {
        "record_id": first_present(summary.get("summaryId"), summary.get("SK"), summary.get("hour_id")),
        "timestamp_ms": int(as_number(timestamp_ms, 0)),
        "data_origin": "real_dynamodb",
        "scenario_family": "real_home",
        "scenario_variant_id": str(first_present(summary.get("summaryId"), summary.get("SK"), summary.get("hour_id"), default="real_unknown")),
        "datetime_bahrain": dt.tz_convert("Asia/Bahrain").isoformat(),
        "date": dt.tz_convert("Asia/Bahrain").date().isoformat(),
        "data_source": "hourly_summary",
        "hour_of_day": int(dt.tz_convert("Asia/Bahrain").hour),
        "day_of_week": dt.tz_convert("Asia/Bahrain").day_name(),
        "is_weekend": bool(dt.tz_convert("Asia/Bahrain").dayofweek in {4, 5}),
        "sample_count": sample_count,
        "avg_temperature": first_present(sensor.get("avgTemperatureC"), summary.get("avg_temperature")),
        "avg_humidity": first_present(sensor.get("avgHumidity"), summary.get("avg_humidity")),
        "avg_sound_raw": first_present(sensor.get("avgSoundRaw"), summary.get("avg_sound_raw")),
        "motion_count": motion_count,
        "bright_count": bright_count,
        "smoke_count": smoke_count,
        "noise_count": noise_count,
        "high_temp_count": high_temp_count,
        "occupancy_score": min(1.0, max(safe_ratio(occupied_count or motion_count, sample_count), safe_ratio(motion_count + noise_count, sample_count))),
        "switch_avg_power_W": switch_power,
        "switch_peak_power_W": as_number(first_present(switch.get("peakPowerW"), switch.get("peak_power_W"), switch.get("peak_power"))),
        "switch_energy_kWh": as_number(first_present(switch.get("energyDeltaKwh"), switch.get("energy_delta_kWh"), switch.get("energy_kWh"))),
        "ac_avg_power_W": ac_power,
        "ac_peak_power_W": as_number(first_present(ac.get("peakPowerW"), ac.get("peak_power_W"), ac.get("peak_power"))),
        "ac_energy_kWh": as_number(first_present(ac.get("energyDeltaKwh"), ac.get("energy_delta_kWh"), ac.get("energy_kWh"))),
        "total_avg_power_W": total_avg_power,
        "total_peak_power_W": max(
            as_number(first_present(summary.get("total_peak_power_W"), as_dict(summary.get("energy")).get("total_peak_power_W"))),
            as_number(first_present(switch.get("peakPowerW"), switch.get("peak_power_W"))),
            as_number(first_present(ac.get("peakPowerW"), ac.get("peak_power_W"))),
        ),
        "total_energy_kWh": total_energy,
        "total_cost_BHD": total_energy * TARIFF_BHD_PER_KWH,
        "tariff_BHD_per_kWh": TARIFF_BHD_PER_KWH,
        "sensor_freshness_age_seconds": as_number(first_present(summary.get("sensor_age_seconds"), summary.get("sensor_staleness_seconds"))),
        "breaker_freshness_age_seconds": as_number(first_present(summary.get("breaker_age_seconds"), summary.get("breaker_staleness_seconds"))),
        "hub_freshness_age_seconds": as_number(first_present(summary.get("hub_age_seconds"), summary.get("hub_staleness_seconds"))),
        "ac_on_flag": state_on_flag(ac.get("state"), ac.get("switch"), ac.get("isOn")) or int(ac_power > 5),
        "socket_on_flag": state_on_flag(switch.get("state"), switch.get("switch"), switch.get("isOn")) or int(switch_power > 5),
        "command_count_last_hour": as_number(first_present(as_dict(summary.get("commandSummary")).get("commandCount"), summary.get("command_count_last_hour"))),
        "command_failure_count_last_hour": as_number(first_present(as_dict(summary.get("commandSummary")).get("failedCount"), summary.get("command_failure_count_last_hour"))),
    }
    return row


SCENARIO_FAMILIES = [
    "normal_usage",
    "ac_left_on",
    "socket_left_on",
    "routine_anomaly",
    "high_energy",
    "smoke_gas",
    "stale_data",
    "hub_offline",
    "low_usage_normal",
    "power_spike",
]


def generate_synthetic_scenario_rows(
    row_count: int = 1200,
    *,
    start_timestamp_ms: int = 1770000000000,
    seed: int = 42,
) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    rows_per_variant = 4
    variant_count = max(len(SCENARIO_FAMILIES), math.ceil(row_count / rows_per_variant))
    for variant_index in range(variant_count):
        family = SCENARIO_FAMILIES[variant_index % len(SCENARIO_FAMILIES)]
        variant_id = f"{family}_{variant_index:04d}"
        base_hour = int(rng.integers(0, 24))
        day_offset = int(rng.integers(0, 60))
        for step in range(rows_per_variant):
            if len(rows) >= row_count:
                break
            timestamp_ms = start_timestamp_ms + ((day_offset * 24) + base_hour + step + variant_index * rows_per_variant) * 60 * 60 * 1000
            row = synthetic_row_for_family(family, variant_id, timestamp_ms, rng)
            rows.append(row)
    return rows


def synthetic_row_for_family(
    family: str,
    variant_id: str,
    timestamp_ms: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    dt = timestamp_to_datetime(timestamp_ms).tz_convert("Asia/Bahrain")
    hour = int(dt.hour)
    sample_count = int(rng.integers(45, 181))
    temperature = float(np.clip(rng.normal(27, 2.2), 20, 36))
    humidity = float(np.clip(rng.normal(52, 10), 25, 85))
    avg_sound_raw = float(np.clip(rng.normal(380, 180), 40, 1200))
    motion_count = int(rng.integers(5, max(6, sample_count // 2)))
    bright_count = int(rng.integers(10, max(11, sample_count)))
    noise_count = int(rng.integers(0, max(1, sample_count // 8)))
    smoke_count = 0
    high_temp_count = int(sample_count * 0.15) if temperature >= 30 else 0
    occupancy_score = float(np.clip(rng.normal(0.55, 0.2), 0, 1))
    socket_power = float(np.clip(rng.normal(10, 8), 0, 80))
    ac_power = float(np.clip(rng.normal(25, 35), 0, 350))
    sensor_age = float(rng.integers(5, 80))
    breaker_age = float(rng.integers(5, 80))
    hub_age = float(rng.integers(5, 90))
    command_count = int(rng.integers(0, 4))
    command_failures = 0

    if family == "normal_usage":
        occupancy_score = float(np.clip(rng.normal(0.65, 0.15), 0.25, 1))
        motion_count = int(occupancy_score * sample_count)
        socket_power = float(np.clip(rng.normal(12, 8), 0, 60))
        ac_power = float(np.clip(rng.normal(45, 35), 0, 180))
    elif family == "low_usage_normal":
        occupancy_score = float(np.clip(rng.normal(0.2, 0.15), 0, 0.55))
        motion_count = int(occupancy_score * sample_count)
        socket_power = float(np.clip(rng.normal(1.5, 1.5), 0, 5))
        ac_power = float(np.clip(rng.normal(1.5, 2), 0, 6))
    elif family == "ac_left_on":
        occupancy_score = float(np.clip(rng.normal(0.04, 0.04), 0, 0.16))
        motion_count = int(occupancy_score * sample_count)
        ac_power = float(np.clip(rng.normal(210, 55), 90, 420))
        socket_power = float(np.clip(rng.normal(8, 6), 0, 40))
    elif family == "socket_left_on":
        occupancy_score = float(np.clip(rng.normal(0.05, 0.05), 0, 0.18))
        motion_count = int(occupancy_score * sample_count)
        socket_power = float(np.clip(rng.normal(42, 18), 18, 110))
        ac_power = float(np.clip(rng.normal(2, 3), 0, 10))
    elif family == "routine_anomaly":
        occupancy_score = float(np.clip(rng.normal(0.25, 0.18), 0, 0.65))
        motion_count = int(occupancy_score * sample_count)
        ac_power = float(np.clip(rng.normal(130, 50), 40, 280))
        socket_power = float(np.clip(rng.normal(25, 15), 0, 90))
    elif family == "high_energy":
        occupancy_score = float(np.clip(rng.normal(0.55, 0.25), 0, 1))
        motion_count = int(occupancy_score * sample_count)
        ac_power = float(np.clip(rng.normal(260, 70), 130, 520))
        socket_power = float(np.clip(rng.normal(85, 30), 35, 180))
    elif family == "smoke_gas":
        occupancy_score = float(np.clip(rng.normal(0.6, 0.25), 0, 1))
        motion_count = int(occupancy_score * sample_count)
        smoke_count = int(rng.integers(1, max(2, sample_count // 6)))
        socket_power = float(np.clip(rng.normal(12, 10), 0, 80))
        ac_power = float(np.clip(rng.normal(25, 25), 0, 140))
    elif family == "stale_data":
        sensor_age = float(rng.integers(240, 1800))
        breaker_age = float(rng.integers(240, 1800))
        occupancy_score = float(np.clip(rng.normal(0.4, 0.25), 0, 1))
        motion_count = int(occupancy_score * sample_count)
    elif family == "hub_offline":
        hub_age = float(rng.integers(420, 3600))
        sensor_age = float(rng.integers(180, 1800))
        breaker_age = float(rng.integers(180, 1800))
        occupancy_score = float(np.clip(rng.normal(0.35, 0.25), 0, 1))
        motion_count = int(occupancy_score * sample_count)
    elif family == "power_spike":
        occupancy_score = float(np.clip(rng.normal(0.5, 0.25), 0, 1))
        motion_count = int(occupancy_score * sample_count)
        ac_power = float(np.clip(rng.normal(180, 70), 40, 450))
        socket_power = float(np.clip(rng.normal(120, 45), 50, 260))

    total_power = max(0.0, ac_power + socket_power + float(np.clip(rng.normal(2, 3), 0, 15)))
    energy_kwh = max(0.0, (total_power / 1000.0) * float(np.clip(rng.normal(0.7, 0.18), 0.35, 1.05)))
    socket_energy = energy_kwh * (socket_power / total_power) if total_power > 0 else 0
    ac_energy = energy_kwh * (ac_power / total_power) if total_power > 0 else 0
    same_hour_avg = max(0.002, energy_kwh * float(np.clip(rng.normal(0.75, 0.25), 0.2, 1.6)))
    rolling_avg = max(0.002, energy_kwh * float(np.clip(rng.normal(0.8, 0.2), 0.25, 1.5)))
    same_hour_power_avg = max(1.0, total_power * float(np.clip(rng.normal(0.75, 0.25), 0.2, 1.6)))
    rolling_power_avg = max(1.0, total_power * float(np.clip(rng.normal(0.8, 0.2), 0.25, 1.5)))

    if family in {"high_energy", "power_spike", "routine_anomaly"}:
        same_hour_avg = max(0.002, energy_kwh / float(np.clip(rng.normal(2.4, 0.4), 1.6, 3.4)))
        rolling_avg = max(0.002, energy_kwh / float(np.clip(rng.normal(2.1, 0.4), 1.4, 3.2)))
        same_hour_power_avg = max(1.0, total_power / float(np.clip(rng.normal(2.3, 0.4), 1.5, 3.2)))
        rolling_power_avg = max(1.0, total_power / float(np.clip(rng.normal(2.0, 0.4), 1.3, 3.0)))

    return {
        "record_id": f"synthetic_{variant_id}_{timestamp_ms}",
        "timestamp_ms": timestamp_ms,
        "data_origin": "synthetic_scenario",
        "scenario_family": family,
        "scenario_variant_id": variant_id,
        "datetime_bahrain": dt.isoformat(),
        "date": dt.date().isoformat(),
        "data_source": "synthetic_hourly_summary",
        "hour_of_day": hour,
        "day_of_week": dt.day_name(),
        "is_weekend": bool(dt.dayofweek in {4, 5}),
        "sample_count": sample_count,
        "avg_temperature": round(temperature, 3),
        "avg_humidity": round(humidity, 3),
        "avg_sound_raw": round(avg_sound_raw, 3),
        "motion_count": motion_count,
        "bright_count": bright_count,
        "smoke_count": smoke_count,
        "noise_count": noise_count,
        "high_temp_count": high_temp_count,
        "occupancy_score": round(occupancy_score, 4),
        "switch_avg_power_W": round(socket_power, 3),
        "switch_peak_power_W": round(socket_power * float(np.clip(rng.normal(1.45, 0.2), 1.0, 2.2)), 3),
        "switch_energy_kWh": round(socket_energy, 6),
        "ac_avg_power_W": round(ac_power, 3),
        "ac_peak_power_W": round(ac_power * float(np.clip(rng.normal(1.35, 0.18), 1.0, 2.0)), 3),
        "ac_energy_kWh": round(ac_energy, 6),
        "total_avg_power_W": round(total_power, 3),
        "total_peak_power_W": round(total_power * float(np.clip(rng.normal(1.35, 0.2), 1.0, 2.2)), 3),
        "total_energy_kWh": round(energy_kwh, 6),
        "total_cost_BHD": round(energy_kwh * TARIFF_BHD_PER_KWH, 6),
        "tariff_BHD_per_kWh": TARIFF_BHD_PER_KWH,
        "sensor_freshness_age_seconds": sensor_age,
        "breaker_freshness_age_seconds": breaker_age,
        "hub_freshness_age_seconds": hub_age,
        "ac_on_flag": int(ac_power > 10),
        "socket_on_flag": int(socket_power > 10),
        "command_count_last_hour": command_count,
        "command_failure_count_last_hour": command_failures,
        "synthetic_same_hour_energy_avg_hint": round(same_hour_avg, 6),
        "synthetic_rolling_energy_avg_hint": round(rolling_avg, 6),
        "synthetic_same_hour_power_avg_hint": round(same_hour_power_avg, 3),
        "synthetic_rolling_power_avg_hint": round(rolling_power_avg, 3),
    }


def add_engineered_features(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data
    data = data.copy().sort_values("timestamp_ms").reset_index(drop=True)
    dt = pd.to_datetime(data["timestamp_ms"], unit="ms", utc=True, errors="coerce").dt.tz_convert("Asia/Bahrain")
    data["hour_of_day"] = data.get("hour_of_day", dt.dt.hour).fillna(dt.dt.hour).astype(int)
    data["day_of_week"] = data.get("day_of_week", dt.dt.day_name()).fillna(dt.dt.day_name())
    data["is_weekend"] = data.get("is_weekend", dt.dt.dayofweek.isin([4, 5])).fillna(dt.dt.dayofweek.isin([4, 5])).astype(bool)
    data["is_night"] = data["hour_of_day"].between(0, 5) | data["hour_of_day"].between(23, 23)
    data["is_morning"] = data["hour_of_day"].between(5, 11)
    data["is_evening"] = data["hour_of_day"].between(17, 21)
    data["is_working_hour"] = (~data["is_weekend"]) & data["hour_of_day"].between(8, 17)
    data["is_sleep_hour"] = data["hour_of_day"].between(0, 5) | data["hour_of_day"].between(23, 23)
    data["day_part"] = data["hour_of_day"].apply(lambda h: day_part(int(h)))

    for column in ["total_energy_kWh", "total_avg_power_W", "total_peak_power_W", "sample_count"]:
        if column not in data.columns:
            data[column] = 0.0
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0.0)

    data["previous_hour_total_energy_kWh"] = data["total_energy_kWh"].shift(1).fillna(0.0)
    data["previous_hour_total_avg_power_W"] = data["total_avg_power_W"].shift(1).fillna(0.0)
    data["previous_hour_total_peak_power_W"] = data["total_peak_power_W"].shift(1).fillna(0.0)
    data["energy_delta_from_previous_hour"] = data["total_energy_kWh"] - data["previous_hour_total_energy_kWh"]
    data["power_delta_from_previous_hour"] = data["total_avg_power_W"] - data["previous_hour_total_avg_power_W"]

    for window in [3, 6, 24]:
        data[f"rolling_{window}h_energy_avg"] = data["total_energy_kWh"].rolling(window, min_periods=1).mean()
        data[f"rolling_{window}h_power_avg"] = data["total_avg_power_W"].rolling(window, min_periods=1).mean()
    for window in [3, 24]:
        data[f"rolling_{window}h_energy_std"] = data["total_energy_kWh"].rolling(window, min_periods=2).std().fillna(0.0)
        data[f"rolling_{window}h_power_std"] = data["total_avg_power_W"].rolling(window, min_periods=2).std().fillna(0.0)

    same_hour_group = data.groupby("hour_of_day", dropna=False)
    data["same_hour_7day_energy_avg"] = same_hour_group["total_energy_kWh"].transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean()).fillna(0.0)
    data["same_hour_7day_power_avg"] = same_hour_group["total_avg_power_W"].transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean()).fillna(0.0)
    data["same_hour_7day_energy_std"] = same_hour_group["total_energy_kWh"].transform(lambda s: s.shift(1).rolling(7, min_periods=2).std()).fillna(0.0)
    data["same_hour_7day_power_std"] = same_hour_group["total_avg_power_W"].transform(lambda s: s.shift(1).rolling(7, min_periods=2).std()).fillna(0.0)

    synthetic_mask = data.get("data_origin", pd.Series("", index=data.index)).eq("synthetic_scenario")
    if synthetic_mask.any():
        if "synthetic_same_hour_energy_avg_hint" in data.columns:
            data.loc[synthetic_mask, "same_hour_7day_energy_avg"] = numeric_series(data, "synthetic_same_hour_energy_avg_hint", 0).loc[synthetic_mask]
        if "synthetic_same_hour_power_avg_hint" in data.columns:
            data.loc[synthetic_mask, "same_hour_7day_power_avg"] = numeric_series(data, "synthetic_same_hour_power_avg_hint", 0).loc[synthetic_mask]
        if "synthetic_rolling_energy_avg_hint" in data.columns:
            data.loc[synthetic_mask, "rolling_24h_energy_avg"] = numeric_series(data, "synthetic_rolling_energy_avg_hint", 0).loc[synthetic_mask]
        if "synthetic_rolling_power_avg_hint" in data.columns:
            data.loc[synthetic_mask, "rolling_24h_power_avg"] = numeric_series(data, "synthetic_rolling_power_avg_hint", 0).loc[synthetic_mask]
        data.loc[synthetic_mask, "same_hour_7day_energy_std"] = np.maximum(data.loc[synthetic_mask, "same_hour_7day_energy_avg"] * 0.18, 0.002)
        data.loc[synthetic_mask, "same_hour_7day_power_std"] = np.maximum(data.loc[synthetic_mask, "same_hour_7day_power_avg"] * 0.18, 3.0)
        data.loc[synthetic_mask, "rolling_24h_energy_std"] = np.maximum(data.loc[synthetic_mask, "rolling_24h_energy_avg"] * 0.2, 0.002)
        data.loc[synthetic_mask, "rolling_24h_power_std"] = np.maximum(data.loc[synthetic_mask, "rolling_24h_power_avg"] * 0.2, 3.0)

    data["energy_z_score_24h"] = z_score(data["total_energy_kWh"], data["rolling_24h_energy_avg"], data["rolling_24h_energy_std"])
    data["power_z_score_24h"] = z_score(data["total_avg_power_W"], data["rolling_24h_power_avg"], data["rolling_24h_power_std"])
    data["same_hour_energy_z_score"] = z_score(data["total_energy_kWh"], data["same_hour_7day_energy_avg"], data["same_hour_7day_energy_std"])
    data["same_hour_power_z_score"] = z_score(data["total_avg_power_W"], data["same_hour_7day_power_avg"], data["same_hour_7day_power_std"])

    sample = numeric_series(data, "sample_count", 1).clip(lower=1)
    for name, count_col in [
        ("motion_rate", "motion_count"),
        ("bright_rate", "bright_count"),
        ("noise_rate", "noise_count"),
        ("smoke_rate", "smoke_count"),
        ("high_temp_rate", "high_temp_count"),
    ]:
        data[name] = numeric_series(data, count_col, 0) / sample

    data["minutes_since_motion"] = np.where(data["motion_rate"] > 0, 0.0, 60.0)
    data["sensor_stale_flag"] = numeric_series(data, "sensor_freshness_age_seconds", 0) > 180
    data["breaker_stale_flag"] = numeric_series(data, "breaker_freshness_age_seconds", 0) > 180
    data["hub_offline_flag"] = numeric_series(data, "hub_freshness_age_seconds", 0) > 300
    data["ac_on_flag"] = numeric_series(data, "ac_on_flag", 0).astype(int)
    data["socket_on_flag"] = numeric_series(data, "socket_on_flag", 0).astype(int)
    data["device_on_count"] = data["ac_on_flag"] + data["socket_on_flag"]
    data["ac_state_duration_minutes"] = state_duration_minutes(data["ac_on_flag"])
    data["socket_state_duration_minutes"] = state_duration_minutes(data["socket_on_flag"])
    data["high_power_duration_minutes"] = consecutive_duration_minutes(data["total_avg_power_W"] > 100)
    data["empty_room_duration_minutes"] = consecutive_duration_minutes(pd.to_numeric(data.get("occupancy_score", 0), errors="coerce").fillna(0) < 0.2)
    data["occupancy_power_mismatch_score"] = (
        (1.0 - numeric_series(data, "occupancy_score", 0).clip(0, 1))
        * (data["total_avg_power_W"] / 200.0).clip(0, 1)
    )
    data["routine_score_for_hour"] = (1.0 - data["same_hour_power_z_score"].abs().clip(0, 3) / 3).clip(0, 1)
    data["routine_deviation_score"] = (data["same_hour_power_z_score"].abs().clip(0, 3) / 3).clip(0, 1)
    data["label_rule_version"] = LABEL_RULE_VERSION

    labels = [label_row(record) for record in data.to_dict("records")]
    for target in CLASSIFICATION_TARGETS:
        data[target] = [label[target] for label in labels]

    apply_manual_label_overrides(data)
    data["next_hour_total_energy_kWh"] = data["total_energy_kWh"].shift(-1)
    data["next_hour_total_cost_BHD"] = data["total_cost_BHD"].shift(-1)
    data = data.dropna(subset=REGRESSION_TARGETS, how="any").reset_index(drop=True)
    return data


def z_score(value: pd.Series, mean: pd.Series, std: pd.Series) -> pd.Series:
    usable_std = std.replace(0, np.nan)
    return ((value - mean) / usable_std).replace([np.inf, -np.inf], 0).fillna(0.0)


def numeric_series(data: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column in data.columns:
        return pd.to_numeric(data[column], errors="coerce").fillna(default)
    return pd.Series([default] * len(data), index=data.index, dtype="float64")


def state_duration_minutes(flags: pd.Series) -> pd.Series:
    flags = flags.astype(int).fillna(0)
    durations: list[float] = []
    current = 0
    for flag in flags:
        current = current + 60 if flag else 0
        durations.append(float(current))
    return pd.Series(durations, index=flags.index)


def consecutive_duration_minutes(condition: pd.Series) -> pd.Series:
    durations: list[float] = []
    current = 0
    for value in condition.fillna(False):
        current = current + 60 if bool(value) else 0
        durations.append(float(current))
    return pd.Series(durations, index=condition.index)


def apply_manual_label_overrides(data: pd.DataFrame) -> None:
    if not MANUAL_LABELS_PATH.exists():
        return
    manual = pd.read_csv(MANUAL_LABELS_PATH)
    if manual.empty:
        return
    key_column = "record_id" if "record_id" in manual.columns else "timestamp_ms" if "timestamp_ms" in manual.columns else None
    if not key_column or key_column not in data.columns:
        return
    manual = manual.set_index(key_column)
    for index, row in data.iterrows():
        key = row.get(key_column)
        if key not in manual.index:
            continue
        override = manual.loc[key]
        if isinstance(override, pd.DataFrame):
            override = override.iloc[-1]
        for target in CLASSIFICATION_TARGETS:
            if target in override and pd.notna(override[target]):
                data.at[index, target] = override[target]


def split_time_based(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data = data.sort_values("timestamp_ms").reset_index(drop=True)
    total = len(data)
    if total < 5:
        train_end = max(1, total - 2)
        validation_end = max(train_end + 1, total - 1)
    else:
        train_end = max(1, int(total * 0.70))
        validation_end = max(train_end + 1, int(total * 0.85))
    train = data.iloc[:train_end].copy()
    validation = data.iloc[train_end:validation_end].copy()
    test = data.iloc[validation_end:].copy()
    if validation.empty and not train.empty:
        validation = train.tail(1).copy()
    if test.empty:
        test = validation.tail(1).copy()
    train["split"] = "train"
    validation["split"] = "validation"
    test["split"] = "test"
    return train, validation, test


def split_grouped_by_variant(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if "scenario_variant_id" not in data.columns:
        return split_time_based(data)
    data = data.sort_values("timestamp_ms").reset_index(drop=True)
    variant_rows = (
        data.groupby("scenario_variant_id", dropna=False)
        .agg(
            first_timestamp=("timestamp_ms", "min"),
            row_count=("timestamp_ms", "count"),
            data_origin=("data_origin", "first") if "data_origin" in data.columns else ("timestamp_ms", "count"),
            scenario_family=("scenario_family", "first") if "scenario_family" in data.columns else ("timestamp_ms", "count"),
        )
        .reset_index()
        .sort_values(["first_timestamp", "scenario_variant_id"])
    )
    synthetic_variants = variant_rows[variant_rows["data_origin"] == "synthetic_scenario"].copy()
    real_variants = variant_rows[variant_rows["data_origin"] != "synthetic_scenario"].copy()

    train_ids: set[Any] = set()
    validation_ids: set[Any] = set()
    test_ids: set[Any] = set()

    for _, family_group in synthetic_variants.groupby("scenario_family", sort=False):
        ids = list(family_group["scenario_variant_id"])
        total = len(ids)
        train_end = max(1, int(total * 0.70))
        validation_end = max(train_end + 1, int(total * 0.85)) if total >= 3 else train_end
        train_ids.update(ids[:train_end])
        validation_ids.update(ids[train_end:validation_end])
        test_ids.update(ids[validation_end:])
        if total >= 3 and not ids[validation_end:]:
            moved = ids[-1]
            train_ids.discard(moved)
            validation_ids.discard(moved)
            test_ids.add(moved)

    real_ids = list(real_variants["scenario_variant_id"])
    if real_ids:
        real_total = len(real_ids)
        train_end = max(1, int(real_total * 0.70))
        validation_end = max(train_end + 1, int(real_total * 0.85)) if real_total >= 3 else train_end
        train_ids.update(real_ids[:train_end])
        validation_ids.update(real_ids[train_end:validation_end])
        test_ids.update(real_ids[validation_end:])

    train = data[data["scenario_variant_id"].isin(train_ids)].copy()
    validation = data[data["scenario_variant_id"].isin(validation_ids)].copy()
    test = data[data["scenario_variant_id"].isin(test_ids)].copy()
    if validation.empty:
        validation = train.tail(max(1, min(5, len(train)))).copy()
        train = train.iloc[: max(1, len(train) - len(validation))].copy()
    if test.empty:
        test = validation.tail(max(1, min(5, len(validation)))).copy()
        validation = validation.iloc[: max(1, len(validation) - len(test))].copy()
    train["split"] = "train"
    validation["split"] = "validation"
    test["split"] = "test"
    return train.sort_values("timestamp_ms"), validation.sort_values("timestamp_ms"), test.sort_values("timestamp_ms")


def feature_columns(data: pd.DataFrame) -> list[str]:
    ignored = set(TARGET_COLUMNS) | IDENTIFIER_COLUMNS
    return [column for column in data.columns if column not in ignored]


def build_preprocessor(data: pd.DataFrame, columns: list[str]) -> ColumnTransformer:
    numeric_features = [column for column in columns if pd.api.types.is_numeric_dtype(data[column])]
    categorical_features = [column for column in columns if column not in numeric_features]
    return ColumnTransformer(
        transformers=[
            ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median"))]), numeric_features),
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical_features,
            ),
        ]
    )


def candidate_classifiers(preprocessor: ColumnTransformer, class_count: int, row_count: int) -> dict[str, Pipeline]:
    if class_count < 2 or row_count < 12:
        return {"DummyMostFrequent": Pipeline([("preprocess", preprocessor), ("model", DummyClassifier(strategy="most_frequent"))])}
    return {
        "RandomForest": Pipeline(
            [
                ("preprocess", preprocessor),
                ("model", RandomForestClassifier(n_estimators=180, min_samples_leaf=2, class_weight="balanced", random_state=42, n_jobs=-1)),
            ]
        ),
        "ExtraTrees": Pipeline(
            [
                ("preprocess", preprocessor),
                ("model", ExtraTreesClassifier(n_estimators=220, min_samples_leaf=2, class_weight="balanced", random_state=42, n_jobs=-1)),
            ]
        ),
        "GradientBoosting": Pipeline([("preprocess", preprocessor), ("model", GradientBoostingClassifier(random_state=42))]),
        "HistGradientBoosting": Pipeline([("preprocess", preprocessor), ("model", HistGradientBoostingClassifier(random_state=42))]),
    }


def candidate_regressors(preprocessor: ColumnTransformer, row_count: int) -> dict[str, Pipeline]:
    if row_count < 12:
        return {"DummyMean": Pipeline([("preprocess", preprocessor), ("model", DummyRegressor(strategy="mean"))])}
    return {
        "RandomForest": Pipeline(
            [
                ("preprocess", preprocessor),
                ("model", RandomForestRegressor(n_estimators=180, min_samples_leaf=2, random_state=42, n_jobs=-1)),
            ]
        ),
        "ExtraTrees": Pipeline(
            [
                ("preprocess", preprocessor),
                ("model", ExtraTreesRegressor(n_estimators=220, min_samples_leaf=2, random_state=42, n_jobs=-1)),
            ]
        ),
        "GradientBoosting": Pipeline([("preprocess", preprocessor), ("model", GradientBoostingRegressor(random_state=42))]),
        "HistGradientBoosting": Pipeline([("preprocess", preprocessor), ("model", HistGradientBoostingRegressor(random_state=42))]),
    }


def classification_metrics(y_true: pd.Series, y_pred: Any) -> dict[str, Any]:
    labels = sorted({str(item) for item in list(y_true) + list(y_pred)})
    report = classification_report(y_true, y_pred, labels=labels, zero_division=0, output_dict=True)
    metrics = {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision_macro": round(float(precision_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "recall_macro": round(float(recall_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "f1_weighted": round(float(f1_score(y_true, y_pred, average="weighted", zero_division=0)), 4),
        "per_class": report,
        "special_recall": {
            label: round(float(report.get(label, {}).get("recall", 0.0)), 4)
            for label in SPECIAL_RECALL_CLASSES
            if label in report
        },
    }
    return metrics


def regression_metrics(y_true: pd.Series, y_pred: Any) -> dict[str, Any]:
    rmse = math.sqrt(float(mean_squared_error(y_true, y_pred)))
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 6),
        "rmse": round(rmse, 6),
        "r2": round(float(r2_score(y_true, y_pred)), 4) if len(y_true) > 1 else None,
        "mean_actual": round(float(np.mean(y_true)), 6),
        "mean_predicted": round(float(np.mean(y_pred)), 6),
        "error_summary": {
            "p50_abs_error": round(float(np.percentile(np.abs(np.asarray(y_true) - np.asarray(y_pred)), 50)), 6),
            "p90_abs_error": round(float(np.percentile(np.abs(np.asarray(y_true) - np.asarray(y_pred)), 90)), 6),
            "max_abs_error": round(float(np.max(np.abs(np.asarray(y_true) - np.asarray(y_pred)))), 6),
        },
    }


def confusion_matrix_payload(y_true: pd.Series, y_pred: Any) -> dict[str, Any]:
    labels = sorted({str(item) for item in list(y_true) + list(y_pred)})
    return {
        "labels": labels,
        "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def extract_feature_importance(model: Pipeline, columns: list[str], target: str, model_name: str) -> list[dict[str, Any]]:
    estimator = model.named_steps.get("model")
    if not hasattr(estimator, "feature_importances_"):
        return []
    preprocessor = model.named_steps.get("preprocess")
    try:
        names = list(preprocessor.get_feature_names_out())
    except Exception:
        names = columns
    importances = list(getattr(estimator, "feature_importances_", []))
    rows = [
        {
            "target": target,
            "model": model_name,
            "feature": str(name).replace("numeric__", "").replace("categorical__", ""),
            "importance": float(importance),
        }
        for name, importance in zip(names, importances)
    ]
    rows.sort(key=lambda item: item["importance"], reverse=True)
    return rows[:30]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def generated_at_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
