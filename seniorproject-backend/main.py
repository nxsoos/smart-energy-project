from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import firebase_admin
import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from firebase_admin import db


SERVICE_NAME = "smart-energy-ai"
BAHRAIN_TZ = timezone(timedelta(hours=3))
DEFAULT_HOME_ID = os.environ.get("DEFAULT_HOME_ID", "home_001")
MODEL_PATH = Path(os.environ.get("MODEL_PATH", "devices/models/smart_energy_ai.joblib"))
EFFICIENCY_SCORE_CHANGE_THRESHOLD = 3
NEXT_HOUR_ENERGY_CHANGE_THRESHOLD = 0.01
NEXT_HOUR_COST_CHANGE_THRESHOLD = 0.001

app = FastAPI(
    title="Smart Energy AI",
    description="Cloud Run FastAPI service for Smart Energy Consumption AI predictions.",
    version="1.0.0",
)

model_bundle: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    service: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    home_id: str
    answer: str
    used_data: bool
    timestamp: int


def now_ms() -> int:
    return int(time.time() * 1000)


def initialize_firebase() -> None:
    """Initialize Firebase Admin with Cloud Run Application Default Credentials."""
    if firebase_admin._apps:
        return

    database_url = os.environ.get("FIREBASE_DATABASE_URL")
    if not database_url:
        raise RuntimeError("FIREBASE_DATABASE_URL environment variable is required.")

    # No serviceAccountKey.json is used here. In Cloud Run, Firebase Admin uses
    # the Cloud Run service account through Application Default Credentials.
    firebase_admin.initialize_app(options={"databaseURL": database_url})


def load_model() -> dict[str, Any]:
    """Load the trained joblib model once and reuse it across requests."""
    global model_bundle

    if model_bundle is not None:
        return model_bundle

    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")

    loaded = joblib.load(MODEL_PATH)

    if not isinstance(loaded, dict) or "models" not in loaded or "feature_columns" not in loaded:
        raise RuntimeError("Model file has an invalid format.")

    model_bundle = loaded
    return model_bundle


@app.on_event("startup")
def startup() -> None:
    """Fail early if Firebase config or the model is missing."""
    initialize_firebase()
    load_model()


def as_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(default)

    if isinstance(value, (int, float)):
        return float(value)

    return float(default)


def get_time_features(summary: dict[str, Any]) -> dict[str, Any]:
    timestamp_ms = summary.get("hour_start")

    if not isinstance(timestamp_ms, (int, float)):
        timestamp_ms = now_ms()

    bahrain_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=BAHRAIN_TZ)
    day_of_week = bahrain_time.strftime("%A")

    return {
        "hour_of_day": bahrain_time.hour,
        "day_of_week": day_of_week,
        "is_weekend": day_of_week in {"Friday", "Saturday"},
    }


def get_branch_energy(branches: dict[str, Any], breaker_id: str) -> dict[str, float]:
    branch = branches.get(breaker_id)
    if not isinstance(branch, dict):
        branch = {}

    power = branch.get("avg_power_W", branch.get("power_W"))
    peak_power = branch.get("peak_power_W", branch.get("power_W"))
    energy = branch.get("estimated_energy_kWh", branch.get("total_estimated_energy_kWh"))

    return {
        "avg_power_W": as_number(power),
        "peak_power_W": as_number(peak_power),
        "energy_kWh": as_number(energy),
    }


def calculate_occupancy_score(
    motion_count: Any,
    noise_count: Any,
    sample_count: Any,
) -> float:
    usable_sample_count = as_number(sample_count)
    denominator = usable_sample_count if 0 < usable_sample_count <= 1 else 48.0
    motion_score = as_number(motion_count) / denominator
    noise_score = as_number(noise_count) / denominator
    return round(min(1.0, max(motion_score, noise_score)), 4)


def read_backend_data(home_id: str) -> dict[str, Any]:
    try:
        backend_ref = db.reference(f"/homes/{home_id}/backend")
        return {
            "latest_hourly_summary": backend_ref.child("latest_hourly_summary").get(),
            "dashboard_energy": backend_ref.child("dashboard/energy").get(),
            "dashboard_environment": backend_ref.child("dashboard/environment").get(),
            "current_state": backend_ref.child("current_state").get(),
        }
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to read Firebase data: {error}",
        ) from error


def read_chat_context(home_id: str) -> dict[str, Any]:
    try:
        backend_ref = db.reference(f"/homes/{home_id}/backend")
        home_ref = db.reference(f"/homes/{home_id}")
        history_raw = backend_ref.child("ai/prediction_history").get()
        history = history_raw if isinstance(history_raw, dict) else {}
        latest_history = sorted(
            [
                value
                for value in history.values()
                if isinstance(value, dict)
            ],
            key=lambda item: as_number(item.get("created_at")),
            reverse=True,
        )[:5]

        chat_history_raw = backend_ref.child("ai/chat_history").get()
        chat_history = chat_history_raw if isinstance(chat_history_raw, dict) else {}
        latest_chat_history = sorted(
            [
                {
                    "user_message": value.get("user_message"),
                    "assistant_answer": value.get("assistant_answer"),
                    "created_at": value.get("created_at"),
                    "created_at_readable": format_bahrain_time(value.get("created_at")),
                }
                for value in chat_history.values()
                if isinstance(value, dict)
            ],
            key=lambda item: as_number(item.get("created_at")),
            reverse=True,
        )[:6]

        context = {
            "latest_prediction": backend_ref.child("ai/latest_prediction").get(),
            "dashboard_ai": backend_ref.child("dashboard/ai").get(),
            "daily_summary": backend_ref.child("ai/daily_summary").get(),
            "recommendation": backend_ref.child("recommendations/ai_energy_insight").get(),
            "ai_abnormal_usage_alert": backend_ref.child(
                "active_alerts/ai_abnormal_usage"
            ).get(),
            "prediction_history_latest_5": latest_history,
            "dashboard_environment": backend_ref.child("dashboard/environment").get(),
            "current_state": backend_ref.child("current_state").get(),
            "device_health": backend_ref.child("device_health").get(),
            "latest_hourly_summary": backend_ref.child("latest_hourly_summary").get(),
            "devices": summarize_devices(home_ref.child("devices").get()),
            "recent_chat_history_latest_6": latest_chat_history,
        }
        context["derived_context"] = build_chat_derived_context(context)
        return context
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to read Firebase chat context: {error}",
        ) from error


def summarize_devices(devices: Any) -> dict[str, Any]:
    if not isinstance(devices, dict):
        return {}

    summarized: dict[str, Any] = {}
    for device_id, device in devices.items():
        if not isinstance(device, dict):
            continue

        status = ensure_dict(device.get("status"))
        summarized[device_id] = {
            "name": device.get("name"),
            "type": device.get("type"),
            "online": status.get("online"),
            "health_status": status.get("health_status"),
            "relay_status": status.get("relay_status"),
            "switch": status.get("switch"),
            "lastSeenMs": status.get("lastSeenMs"),
            "lastSeen_readable": format_bahrain_time(status.get("lastSeenMs")),
        }

    return summarized


def build_chat_derived_context(context: dict[str, Any]) -> dict[str, Any]:
    now = now_ms()
    latest_sensor_timestamp = latest_sensor_timestamp_ms(context)
    latest_sensor_age_seconds = (
        round((now - latest_sensor_timestamp) / 1000, 1)
        if latest_sensor_timestamp is not None
        else None
    )

    latest_prediction = ensure_dict(context.get("latest_prediction"))
    device_health = ensure_dict(context.get("device_health"))
    device_health_devices = ensure_dict(device_health.get("devices"))

    return {
        "current_time_ms": now,
        "current_time_readable": format_bahrain_time(now),
        "timezone": "Asia/Bahrain (UTC+03:00)",
        "latest_sensor_data_time_ms": latest_sensor_timestamp,
        "latest_sensor_data_time_readable": format_bahrain_time(latest_sensor_timestamp),
        "latest_sensor_data_age_seconds": latest_sensor_age_seconds,
        "latest_sensor_data_is_fresh": (
            latest_sensor_age_seconds is not None and latest_sensor_age_seconds <= 600
        ),
        "latest_ai_checked_at_readable": format_bahrain_time(
            latest_prediction.get("last_checked_at") or latest_prediction.get("created_at")
        ),
        "latest_ai_changed_at_readable": format_bahrain_time(
            latest_prediction.get("last_changed_at")
        ),
        "device_health_updated_at_readable": format_bahrain_time(
            device_health.get("updated_at")
        ),
        "device_health_summary": summarize_device_health(device_health_devices),
    }


def latest_sensor_timestamp_ms(context: dict[str, Any]) -> int | None:
    candidates: list[float] = []

    dashboard_environment = ensure_dict(context.get("dashboard_environment"))
    current_state = ensure_dict(context.get("current_state"))
    latest_hourly_summary = ensure_dict(context.get("latest_hourly_summary"))
    device_health = ensure_dict(context.get("device_health"))
    devices = ensure_dict(context.get("devices"))

    for value in [
        dashboard_environment.get("updated_at"),
        current_state.get("last_processed_at"),
        latest_hourly_summary.get("created_at"),
        latest_hourly_summary.get("hour_start"),
    ]:
        if isinstance(value, (int, float)) and value > 0:
            candidates.append(float(value))

    for health in ensure_dict(device_health.get("devices")).values():
        if isinstance(health, dict):
            last_seen = health.get("lastSeenMs")
            if isinstance(last_seen, (int, float)) and last_seen > 0:
                candidates.append(float(last_seen))

    for device in devices.values():
        if isinstance(device, dict):
            last_seen = device.get("lastSeenMs")
            if isinstance(last_seen, (int, float)) and last_seen > 0:
                candidates.append(float(last_seen))

    if not candidates:
        return None

    return int(max(candidates))


def summarize_device_health(devices: dict[str, Any]) -> dict[str, Any]:
    if not devices:
        return {
            "online_count": 0,
            "offline_count": 0,
            "unknown_count": 0,
            "offline_devices": [],
        }

    online_count = 0
    offline_count = 0
    unknown_count = 0
    offline_devices: list[str] = []

    for device_id, health in devices.items():
        health_dict = ensure_dict(health)
        status = health_dict.get("health_status")
        online = health_dict.get("online")

        if online is True or status == "online":
            online_count += 1
        elif online is False or status == "offline":
            offline_count += 1
            offline_devices.append(str(device_id))
        else:
            unknown_count += 1

    return {
        "online_count": online_count,
        "offline_count": offline_count,
        "unknown_count": unknown_count,
        "offline_devices": offline_devices,
    }


def format_bahrain_time(timestamp_ms: Any) -> str | None:
    if not isinstance(timestamp_ms, (int, float)) or timestamp_ms <= 0:
        return None

    return datetime.fromtimestamp(timestamp_ms / 1000, tz=BAHRAIN_TZ).strftime(
        "%Y-%m-%d %H:%M:%S Bahrain time"
    )


def has_chat_context(context: dict[str, Any]) -> bool:
    for key in [
        "latest_prediction",
        "dashboard_ai",
        "daily_summary",
        "recommendation",
        "ai_abnormal_usage_alert",
        "prediction_history_latest_5",
        "dashboard_environment",
        "current_state",
        "device_health",
        "latest_hourly_summary",
        "devices",
    ]:
        value = context.get(key)
        if value is not None and value != {} and value != []:
            return True

    return False


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_ai_payload(home_id: str) -> tuple[dict[str, Any], str]:
    source = read_backend_data(home_id)

    latest_summary = ensure_dict(source["latest_hourly_summary"])
    dashboard_energy = ensure_dict(source["dashboard_energy"])
    dashboard_environment = ensure_dict(source["dashboard_environment"])

    if not latest_summary and not dashboard_energy and not dashboard_environment:
        raise HTTPException(
            status_code=404,
            detail=f"No usable Firebase backend data found for home_id '{home_id}'.",
        )

    energy = latest_summary.get("energy")
    if not isinstance(energy, dict):
        energy = dashboard_energy

    branches = energy.get("branches")
    if not isinstance(branches, dict):
        branches = {}

    switch_branch = get_branch_energy(branches, "breaker_01")
    ac_branch = get_branch_energy(branches, "breaker_02")

    using_hourly_summary = bool(latest_summary.get("hour_id"))
    input_source = "latest_hourly_summary" if using_hourly_summary else "dashboard_fallback"

    sample_count = as_number(latest_summary.get("sample_count"), 1.0)
    if sample_count <= 0 and dashboard_environment:
        sample_count = 1.0

    motion_count = as_number(latest_summary.get("motion_count"))
    if not using_hourly_summary:
        motion_count = 1.0 if dashboard_environment.get("motion") == 1 else 0.0

    temperature = latest_summary.get("avg_temperature", dashboard_environment.get("temperature"))
    humidity = latest_summary.get("avg_humidity", dashboard_environment.get("humidity"))
    sound_raw = latest_summary.get("avg_sound_raw", dashboard_environment.get("sound_raw"))
    light_is_bright = dashboard_environment.get("light_status") == "Bright"

    noise_count = (
        as_number(latest_summary.get("noise_count"))
        if using_hourly_summary
        else as_number(dashboard_environment.get("noise"))
    )

    payload = {
        **get_time_features(latest_summary),
        "sample_count": sample_count,
        "avg_temperature": temperature,
        "avg_humidity": humidity,
        "avg_sound_raw": sound_raw,
        "motion_count": motion_count,
        "bright_count": (
            as_number(latest_summary.get("bright_count"))
            if using_hourly_summary
            else 1.0 if light_is_bright else 0.0
        ),
        "smoke_count": (
            as_number(latest_summary.get("smoke_count"))
            if using_hourly_summary
            else as_number(dashboard_environment.get("smoke"))
        ),
        "noise_count": noise_count,
        "high_temp_count": (
            as_number(latest_summary.get("high_temp_count"))
            if using_hourly_summary
            else 1.0 if as_number(temperature) >= 27 else 0.0
        ),
        "occupancy_score": calculate_occupancy_score(
            motion_count,
            noise_count,
            sample_count,
        ),
        "switch_avg_power_W": switch_branch["avg_power_W"],
        "switch_peak_power_W": switch_branch["peak_power_W"],
        "switch_energy_kWh": switch_branch["energy_kWh"],
        "ac_avg_power_W": ac_branch["avg_power_W"],
        "ac_peak_power_W": ac_branch["peak_power_W"],
        "ac_energy_kWh": ac_branch["energy_kWh"],
        "total_avg_power_W": as_number(
            energy.get("total_avg_power_W", energy.get("total_power_W"))
        ),
        "total_peak_power_W": as_number(
            energy.get("total_peak_power_W", energy.get("total_power_W"))
        ),
        "total_energy_kWh": as_number(
            energy.get("total_estimated_energy_kWh", energy.get("total_energy_kWh"))
        ),
        "total_cost_BHD": as_number(
            energy.get("total_estimated_cost_BHD", energy.get("total_cost_BHD"))
        ),
        "tariff_BHD_per_kWh": as_number(energy.get("tariff_BHD_per_kWh"), 0.032),
    }

    return payload, input_source


def confidence_from_model(model: Any, row: pd.DataFrame, prediction: Any) -> float | None:
    classifier = model.named_steps.get("model")
    if not hasattr(classifier, "predict_proba"):
        return None

    probabilities = model.predict_proba(row)[0]
    classes = list(classifier.classes_)
    predicted_index = classes.index(prediction)
    return round(float(probabilities[predicted_index]), 4)


def build_explanation(result: dict[str, Any], payload: dict[str, Any]) -> str:
    waste = result["waste_event"]["value"]
    anomaly = result["anomaly_label"]["value"]
    recommendation = result["recommendation_type"]["value"]

    if waste:
        if payload.get("occupancy_score", 1) < 0.2 and payload.get("total_avg_power_W", 0) > 0:
            return "Energy waste is likely because power usage is active while occupancy appears low."
        return "Energy waste is likely based on the current power, room, and time pattern."

    if anomaly != "normal":
        return f"Abnormal usage pattern detected: {anomaly}."

    if recommendation != "none":
        return f"The AI recommends a {recommendation} action based on the current pattern."

    return "Current usage looks normal compared with the training pattern."


def has_missing_required_sensor_data(payload: dict[str, Any]) -> bool:
    required_fields = [
        "avg_temperature",
        "avg_humidity",
        "avg_sound_raw",
        "motion_count",
        "bright_count",
    ]
    return any(payload.get(field) is None for field in required_fields)


def is_night_hour(hour: Any) -> bool:
    return isinstance(hour, (int, float)) and (hour <= 5 or hour >= 23)


def set_classifier_result(
    result: dict[str, Any],
    key: str,
    value: Any,
    confidence: float = 1.0,
    source: str = "post_processing_rule",
) -> None:
    result[key] = {
        "value": value,
        "confidence": confidence,
        "source": source,
    }


def apply_post_processing_rules(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    result["prediction_status"] = "ok"
    result["post_processing_rules"] = []

    if has_missing_required_sensor_data(payload):
        set_classifier_result(result, "waste_event", False)
        set_classifier_result(result, "anomaly_label", "insufficient_data")
        set_classifier_result(result, "recommendation_type", "check_sensor_data")
        result["energy_efficiency_score"] = 0
        result["prediction_status"] = "insufficient_data"
        result["explanation"] = (
            "AI prediction was limited because required sensor data is missing. "
            "Check sensor connection and wait for fresh readings."
        )
        result["post_processing_rules"].append("missing_sensor_data")
        return result

    occupancy_low = as_number(payload.get("occupancy_score")) < 0.2
    lighting_active = as_number(payload.get("switch_avg_power_W")) > 20
    light_very_high = as_number(payload.get("bright_count")) >= 45
    total_power_active = as_number(payload.get("total_avg_power_W")) > 20
    ac_power_active = as_number(payload.get("ac_avg_power_W")) > 0
    high_temperature = (
        as_number(payload.get("avg_temperature")) >= 27
        or as_number(payload.get("high_temp_count")) > 0
    )
    occupied = as_number(payload.get("motion_count")) > 0 and not occupancy_low

    if (
        light_very_high
        and lighting_active
        and occupancy_low
        and as_number(payload.get("switch_avg_power_W")) >= as_number(payload.get("ac_avg_power_W"))
    ):
        set_classifier_result(result, "waste_event", True)
        set_classifier_result(result, "anomaly_label", "light_on_no_motion")
        set_classifier_result(result, "recommendation_type", "turn_off_lights")
        result["energy_efficiency_score"] = min(
            as_number(result.get("energy_efficiency_score"), 100),
            40,
        )
        result["explanation"] = (
            "Energy waste is likely because the room is bright, lighting power is active, "
            "and occupancy appears low."
        )
        result["post_processing_rules"].append("lighting_energy_waste")
        return result

    if is_night_hour(payload.get("hour_of_day")) and occupancy_low and total_power_active:
        set_classifier_result(result, "waste_event", True)
        set_classifier_result(result, "anomaly_label", "device_left_on_at_night")
        set_classifier_result(result, "recommendation_type", "turn_off_unused_devices")
        result["energy_efficiency_score"] = min(
            as_number(result.get("energy_efficiency_score"), 100),
            45,
        )
        result["explanation"] = (
            "Energy waste is likely because devices are using power at night while "
            "occupancy appears low."
        )
        result["post_processing_rules"].append("night_device_left_on")
        return result

    if high_temperature and occupied:
        set_classifier_result(result, "waste_event", False)
        set_classifier_result(result, "anomaly_label", "comfort_high_temperature")
        set_classifier_result(result, "recommendation_type", "comfort_balance")
        result["energy_efficiency_score"] = min(
            as_number(result.get("energy_efficiency_score"), 100),
            75 if ac_power_active else 85,
        )
        result["explanation"] = (
            "Room temperature is high while the room is occupied. Balance comfort and "
            "energy use with cooling, ventilation, or a small AC setting adjustment."
        )
        result["post_processing_rules"].append("occupied_high_temperature")
        return result

    return result


def calculate_efficiency_score(result: dict[str, Any], payload: dict[str, Any]) -> int:
    score = 100

    if result["waste_event"]["value"]:
        score -= 30

    if result["anomaly_label"]["value"] != "normal":
        score -= 20

    if payload.get("high_temp_count", 0) > 0 and payload.get("ac_avg_power_W", 0) > 0:
        score -= 10

    if payload.get("occupancy_score", 1) < 0.2 and payload.get("total_avg_power_W", 0) > 0:
        score -= 20

    return max(0, min(100, score))


def run_model(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        bundle = load_model()
        feature_columns: list[str] = bundle["feature_columns"]
        models: dict[str, Any] = bundle["models"]
        row = pd.DataFrame([{column: payload.get(column) for column in feature_columns}])

        result: dict[str, Any] = {
            "model_name": bundle["model_name"],
            "model_version": bundle["model_version"],
        }

        for target, model in models.items():
            prediction = model.predict(row)[0]
            value: Any = prediction.item() if hasattr(prediction, "item") else prediction
            result[target] = {"value": value}

            confidence = confidence_from_model(model, row, prediction)
            if confidence is not None:
                result[target]["confidence"] = confidence

        result["energy_efficiency_score"] = calculate_efficiency_score(result, payload)
        result["explanation"] = build_explanation(result, payload)
        result = apply_post_processing_rules(result, payload)
        return result
    except FileNotFoundError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {error}") from error


def make_control_suggestion(
    prediction: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    waste_detected = bool(prediction["waste_event"]["value"])
    anomaly = prediction["anomaly_label"]["value"]

    if waste_detected and anomaly == "ac_running_while_empty" and payload.get("ac_avg_power_W", 0) > 0:
        return {
            "device_id": "breaker_02",
            "action": "turn_off",
            "priority": "high",
            "requires_user_approval": True,
            "reason": "AC power is active while occupancy appears low.",
        }

    if waste_detected and anomaly == "light_on_no_motion" and payload.get("switch_avg_power_W", 0) > 0:
        return {
            "device_id": "breaker_01",
            "action": "turn_off",
            "priority": "medium",
            "requires_user_approval": True,
            "reason": "Switch Breaker is active while motion appears low.",
        }

    return None


def build_firebase_result(
    home_id: str,
    payload: dict[str, Any],
    prediction: dict[str, Any],
    input_source: str,
) -> dict[str, Any]:
    control_suggestion = make_control_suggestion(prediction, payload)

    return {
        "home_id": home_id,
        "created_at": now_ms(),
        "model_name": prediction["model_name"],
        "model_version": prediction["model_version"],
        "input_source": input_source,
        "prediction_status": prediction.get("prediction_status", "ok"),
        "post_processing_rules": prediction.get("post_processing_rules", []),
        # Flat fields keep app screens simple while the nested predictions object
        # preserves the full model output with confidences.
        "energy_waste": prediction["waste_event"]["value"],
        "abnormal_usage": prediction["anomaly_label"]["value"],
        "recommendation_type": prediction["recommendation_type"]["value"],
        "next_hour_energy": prediction["next_hour_total_energy_kWh"]["value"],
        "next_hour_cost": prediction["next_hour_total_cost_BHD"]["value"],
        "efficiency_score": prediction["energy_efficiency_score"],
        "explanation": prediction["explanation"],
        "inputs": payload,
        "predictions": {
            "waste_event": prediction["waste_event"],
            "anomaly_label": prediction["anomaly_label"],
            "recommendation_type": prediction["recommendation_type"],
            "next_hour_total_energy_kWh": prediction["next_hour_total_energy_kWh"],
            "next_hour_total_cost_BHD": prediction["next_hour_total_cost_BHD"],
            "energy_efficiency_score": prediction["energy_efficiency_score"],
            "explanation": prediction["explanation"],
            "prediction_status": prediction.get("prediction_status", "ok"),
            "post_processing_rules": prediction.get("post_processing_rules", []),
        },
        "control_suggestion": control_suggestion,
    }


def write_ai_result(home_id: str, result: dict[str, Any]) -> str:
    try:
        backend_ref = db.reference(f"/homes/{home_id}/backend")
        prediction_path = f"/homes/{home_id}/backend/ai/latest_prediction"
        prediction_id = f"prediction_{result['created_at']}"
        previous_prediction = ensure_dict(backend_ref.child("ai/latest_prediction").get())
        previous_daily_summary = ensure_dict(backend_ref.child("ai/daily_summary").get())

        result.update(build_deduplication_metadata(previous_prediction, result))

        updates = build_ai_firebase_updates(
            home_id,
            result,
            prediction_id,
            previous_daily_summary,
        )

        backend_ref.update(updates)
        return prediction_path
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to write AI result to Firebase: {error}",
        ) from error


def build_ai_firebase_updates(
    home_id: str,
    result: dict[str, Any],
    prediction_id: str,
    previous_daily_summary: dict[str, Any],
) -> dict[str, Any]:
    dashboard_ai = build_ai_dashboard_summary(result)
    daily_summary = build_daily_ai_summary(
        result,
        previous_daily_summary,
        history_written=bool(result["history_written"]),
    )

    updates: dict[str, Any] = {
        "ai/latest_prediction": result,
        "dashboard/ai": dashboard_ai,
        "ai/daily_summary": daily_summary,
    }

    if result["history_written"]:
        updates[f"ai/prediction_history/{prediction_id}"] = result

    recommendation = build_ai_recommendation(result)
    if recommendation is None:
        updates["recommendations/ai_energy_insight/status"] = "resolved"
        updates["recommendations/ai_energy_insight/resolved_at"] = result["created_at"]
        updates["recommendations/ai_energy_insight/updated_at"] = result["created_at"]
    else:
        updates["recommendations/ai_energy_insight"] = recommendation

    active_alert = build_ai_alert(result)
    if active_alert is None:
        updates["active_alerts/ai_abnormal_usage"] = None
    else:
        updates["active_alerts/ai_abnormal_usage"] = active_alert

    return updates


def build_deduplication_metadata(
    previous_prediction: dict[str, Any],
    new_prediction: dict[str, Any],
) -> dict[str, Any]:
    changed = is_meaningful_change(previous_prediction, new_prediction)
    created_at = new_prediction["created_at"]

    previous_same_status_count = int(as_number(previous_prediction.get("same_status_count")))
    previous_checks_since_change = int(as_number(previous_prediction.get("checks_since_change")))
    previous_check_count = int(as_number(previous_prediction.get("check_count")))

    if changed:
        return {
            "timestamp": created_at,
            "last_checked_at": created_at,
            "last_changed_at": created_at,
            "same_status_count": 1,
            "checks_since_change": 0,
            "check_count": previous_check_count + 1,
            "history_written": True,
            "change_reason": get_change_reason(previous_prediction, new_prediction),
        }

    return {
        "timestamp": created_at,
        "last_checked_at": created_at,
        "last_changed_at": previous_prediction.get("last_changed_at", created_at),
        "same_status_count": max(previous_same_status_count, 1) + 1,
        "checks_since_change": previous_checks_since_change + 1,
        "check_count": previous_check_count + 1,
        "history_written": False,
        "change_reason": "No meaningful change from previous AI output",
    }


def is_meaningful_change(
    previous_prediction: dict[str, Any],
    new_prediction: dict[str, Any],
) -> bool:
    if not previous_prediction:
        return True

    return get_change_reason(previous_prediction, new_prediction) != (
        "No meaningful change from previous AI output"
    )


def get_change_reason(
    previous_prediction: dict[str, Any],
    new_prediction: dict[str, Any],
) -> str:
    if not previous_prediction:
        return "First AI prediction for this home"

    previous_output = comparable_ai_output(previous_prediction)
    new_output = comparable_ai_output(new_prediction)

    for field in ["energy_waste", "abnormal_usage", "recommendation_type"]:
        if previous_output[field] != new_output[field]:
            return (
                f"{field} changed from {previous_output[field]} "
                f"to {new_output[field]}"
            )

    efficiency_delta = abs(
        new_output["efficiency_score"] - previous_output["efficiency_score"]
    )
    if efficiency_delta >= EFFICIENCY_SCORE_CHANGE_THRESHOLD:
        return f"efficiency_score changed by {round(efficiency_delta, 2)} points"

    energy_delta = abs(new_output["next_hour_energy"] - previous_output["next_hour_energy"])
    if energy_delta >= NEXT_HOUR_ENERGY_CHANGE_THRESHOLD:
        return f"next_hour_energy changed by {round(energy_delta, 6)} kWh"

    cost_delta = abs(new_output["next_hour_cost"] - previous_output["next_hour_cost"])
    if cost_delta >= NEXT_HOUR_COST_CHANGE_THRESHOLD:
        return f"next_hour_cost changed by {round(cost_delta, 6)} BHD"

    if normalize_text(previous_output["explanation"]) != normalize_text(new_output["explanation"]):
        return "explanation changed"

    return "No meaningful change from previous AI output"


def comparable_ai_output(prediction: dict[str, Any]) -> dict[str, Any]:
    predictions = ensure_dict(prediction.get("predictions"))

    return {
        "energy_waste": bool(ensure_dict(predictions.get("waste_event")).get("value")),
        "abnormal_usage": ensure_dict(predictions.get("anomaly_label")).get("value", "normal"),
        "recommendation_type": ensure_dict(predictions.get("recommendation_type")).get(
            "value",
            "none",
        ),
        "efficiency_score": as_number(predictions.get("energy_efficiency_score")),
        "next_hour_energy": as_number(
            ensure_dict(predictions.get("next_hour_total_energy_kWh")).get("value")
        ),
        "next_hour_cost": as_number(
            ensure_dict(predictions.get("next_hour_total_cost_BHD")).get("value")
        ),
        "explanation": str(predictions.get("explanation", "")),
    }


def normalize_text(value: str) -> str:
    return " ".join(value.lower().strip().split())


def build_chat_prompt(home_id: str, user_message: str, context: dict[str, Any]) -> str:
    context_json = json_safe_dumps(context)

    return f"""
You are the Smart Energy AI assistant for a senior project.

Rules:
- Answer only using the Firebase system data provided below.
- Do not invent energy values, costs, device states, alerts, or recommendations.
- If a value is missing, say that information is not available.
- Do not control devices directly.
- You may suggest that the user review or approve a control suggestion if the data includes one.
- Do not override safety-critical alerts.
- Smoke, gas, breaker safety, and device-health alerts are handled by the rule-based backend, not by this chatbot.
- Keep answers clear, short, and understandable.
- Use BHD for cost values and kWh for energy values when those units are present.
- Firebase timestamp fields are epoch milliseconds. When answering about time/date, use the readable Bahrain time fields from derived_context. Do not reply with only a raw millisecond timestamp unless the user explicitly asks for the raw value.
- If the user asks for "real time", explain that this is the latest Firebase reading time, then give the readable time and the latest available readings.
- If the user asks whether sensors or devices are working, use device_health, devices, dashboard_environment, current_state, and derived_context.device_health_summary.
- If the user asks about sensor data, use dashboard_environment and current_state first. The AI prediction inputs are secondary and may be older or aggregated.
- Use recent_chat_history_latest_6 only to understand short follow-up questions. Do not repeat the whole chat history.
- If the latest data is old or a sensor/device is offline, say that clearly.

Home ID: {home_id}

Firebase system data:
{context_json}

User question:
{user_message}
""".strip()


def answer_direct_chat_question(user_message: str, context: dict[str, Any]) -> str | None:
    """Answer simple factual Firebase questions without asking Gemini to reason."""
    normalized = normalize_text(user_message)

    asks_time = any(
        phrase in normalized
        for phrase in [
            "what is the time",
            "last sensor time",
            "time of the last sensor",
            "when was the last sensor",
            "real time",
            "this format",
        ]
    )
    asks_sensor_status = (
        "sensor" in normalized
        and any(word in normalized for word in ["working", "work", "status", "right now"])
    )
    asks_sensor_data = (
        "sensor data" in normalized
        or "any sensor" in normalized
        or ("sensor" in normalized and "access" in normalized)
    )

    if asks_sensor_status:
        return build_sensor_status_answer(context)

    if asks_time:
        return build_latest_sensor_time_answer(context)

    if asks_sensor_data:
        return build_sensor_data_answer(context)

    return None


def build_latest_sensor_time_answer(context: dict[str, Any]) -> str:
    derived = ensure_dict(context.get("derived_context"))
    readable_time = derived.get("latest_sensor_data_time_readable")
    raw_time = derived.get("latest_sensor_data_time_ms")
    age_seconds = derived.get("latest_sensor_data_age_seconds")

    if not readable_time:
        return "The latest sensor data time is not available in Firebase yet."

    age_text = ""
    if isinstance(age_seconds, (int, float)):
        age_text = f" That is about {round(float(age_seconds))} seconds before this chat request."

    return (
        f"The latest sensor data was recorded at {readable_time}."
        f"{age_text} The raw Firebase timestamp is {raw_time}."
    )


def build_sensor_status_answer(context: dict[str, Any]) -> str:
    device_health = ensure_dict(context.get("device_health"))
    devices = ensure_dict(device_health.get("devices"))
    derived = ensure_dict(context.get("derived_context"))
    summary = ensure_dict(derived.get("device_health_summary"))

    if not devices:
        if context.get("dashboard_environment") or context.get("current_state"):
            return (
                "I can see the latest sensor readings in Firebase, but the device-health "
                "status is not available, so I cannot fully confirm whether every sensor "
                "is online."
            )
        return "Sensor status is not available in Firebase yet."

    offline_devices = summary.get("offline_devices") or []
    online_count = int(as_number(summary.get("online_count")))
    offline_count = int(as_number(summary.get("offline_count")))
    unknown_count = int(as_number(summary.get("unknown_count")))
    health_time = derived.get("device_health_updated_at_readable")

    if offline_count == 0 and unknown_count == 0:
        return (
            f"Yes. Firebase device health shows {online_count} devices online and no "
            f"offline devices. Last health check: {health_time or 'not available'}."
        )

    parts = [
        f"Firebase device health shows {online_count} online, {offline_count} offline, "
        f"and {unknown_count} unknown devices."
    ]
    if offline_devices:
        parts.append(f"Offline devices: {', '.join(map(str, offline_devices))}.")
    if health_time:
        parts.append(f"Last health check: {health_time}.")

    return " ".join(parts)


def build_sensor_data_answer(context: dict[str, Any]) -> str:
    environment = ensure_dict(context.get("dashboard_environment"))
    current_state = ensure_dict(context.get("current_state"))
    source = environment if environment else current_state

    if not source:
        return "Sensor data is not available in Firebase yet."

    derived = ensure_dict(context.get("derived_context"))
    readable_time = derived.get("latest_sensor_data_time_readable")

    temperature = source.get("temperature", current_state.get("latest_temperature"))
    humidity = source.get("humidity", current_state.get("latest_humidity"))
    sound = source.get("sound_raw", current_state.get("latest_sound_raw"))
    motion = source.get("motion")
    light_status = source.get("light_status")
    smoke = source.get("smoke")

    fields = [
        ("temperature", temperature, "C"),
        ("humidity", humidity, "%"),
        ("sound", sound, "raw units"),
        ("motion", motion, ""),
        ("light", light_status, ""),
        ("smoke", smoke, ""),
    ]
    available = [
        f"{name}: {value}{(' ' + unit) if unit else ''}"
        for name, value, unit in fields
        if value is not None
    ]

    if not available:
        return "Sensor data exists, but the individual sensor values are not available."

    time_text = f" Latest reading time: {readable_time}." if readable_time else ""
    return f"Yes. Latest sensor data: {', '.join(available)}.{time_text}"


def json_safe_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def call_gemini(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY environment variable is not configured.",
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        errors: list[str] = []

        for model_name in get_gemini_model_candidates():
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                answer = getattr(response, "text", None)

                if not answer:
                    raise RuntimeError("Gemini returned an empty response.")

                return str(answer).strip()
            except Exception as error:
                errors.append(f"{model_name}: {error}")
                continue

        raise RuntimeError("All Gemini model attempts failed. " + " | ".join(errors))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini API request failed: {error}",
        ) from error


def get_gemini_model_candidates() -> list[str]:
    configured_model = os.environ.get("GEMINI_MODEL", "").strip()
    candidates = [
        configured_model,
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-flash-latest",
    ]

    result: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in result:
            result.append(candidate)

    return result


def log_chat_message(
    home_id: str,
    user_message: str,
    assistant_answer: str,
    created_at: int,
    used_data: bool,
) -> None:
    try:
        key = f"chat_{created_at}"
        db.reference(f"/homes/{home_id}/backend/ai/chat_history/{key}").set(
            {
                "user_message": user_message,
                "assistant_answer": assistant_answer,
                "created_at": created_at,
                "used_data": used_data,
                "home_id": home_id,
            }
        )
    except Exception:
        # Chat logging should never break the user-facing chatbot response.
        return


def build_ai_dashboard_summary(result: dict[str, Any]) -> dict[str, Any]:
    predictions = result["predictions"]

    return {
        "updated_at": result["created_at"],
        "last_checked_at": result["last_checked_at"],
        "last_changed_at": result["last_changed_at"],
        "source": "smart_energy_ai",
        "model_name": result["model_name"],
        "model_version": result["model_version"],
        "input_source": result["input_source"],
        "prediction_status": result.get("prediction_status", "ok"),
        "post_processing_rules": result.get("post_processing_rules", []),
        "history_written": result["history_written"],
        "change_reason": result["change_reason"],
        "same_status_count": result["same_status_count"],
        "checks_since_change": result["checks_since_change"],
        "energy_waste": predictions["waste_event"]["value"],
        "waste_confidence": predictions["waste_event"].get("confidence"),
        "abnormal_usage": predictions["anomaly_label"]["value"],
        "abnormal_usage_confidence": predictions["anomaly_label"].get("confidence"),
        "recommendation_type": predictions["recommendation_type"]["value"],
        "next_hour_energy_kWh": predictions["next_hour_total_energy_kWh"]["value"],
        "next_hour_cost_BHD": predictions["next_hour_total_cost_BHD"]["value"],
        "efficiency_score": predictions["energy_efficiency_score"],
        "explanation": predictions["explanation"],
        "control_suggestion": result["control_suggestion"],
    }


def build_ai_recommendation(result: dict[str, Any]) -> dict[str, Any] | None:
    predictions = result["predictions"]
    if result.get("prediction_status") == "insufficient_data":
        return {
            "recommendation_id": "ai_energy_insight",
            "type": "device_health",
            "priority": "medium",
            "title": "AI needs fresh sensor data",
            "message": predictions["explanation"],
            "source": "smart_energy_ai",
            "related_device_id": "esp32_01",
            "related_alert_key": None,
            "ai_prediction_id": result["created_at"],
            "recommendation_type": "check_sensor_data",
            "status": "active",
            "created_at": result["created_at"],
            "updated_at": result["created_at"],
            "resolved_at": None,
        }

    waste_detected = bool(predictions["waste_event"]["value"])
    anomaly = predictions["anomaly_label"]["value"]
    recommendation_type = predictions["recommendation_type"]["value"]

    if not waste_detected and anomaly == "normal" and recommendation_type == "none":
        return None

    priority = "high" if anomaly != "normal" else "medium"
    if result["control_suggestion"] is not None:
        priority = result["control_suggestion"]["priority"]

    return {
        "recommendation_id": "ai_energy_insight",
        "type": "energy_saving",
        "priority": priority,
        "title": "AI energy insight",
        "message": predictions["explanation"],
        "source": "smart_energy_ai",
        "related_device_id": (
            result["control_suggestion"]["device_id"]
            if result["control_suggestion"] is not None
            else None
        ),
        "related_alert_key": "ai_abnormal_usage" if anomaly != "normal" else None,
        "ai_prediction_id": result["created_at"],
        "recommendation_type": recommendation_type,
        "status": "active",
        "created_at": result["created_at"],
        "updated_at": result["created_at"],
        "resolved_at": None,
    }


def build_ai_alert(result: dict[str, Any]) -> dict[str, Any] | None:
    predictions = result["predictions"]
    if result.get("prediction_status") == "insufficient_data":
        return None

    waste_detected = bool(predictions["waste_event"]["value"])
    anomaly = predictions["anomaly_label"]["value"]

    if not waste_detected and anomaly == "normal":
        return None

    alert_subtype = anomaly if anomaly != "normal" else "energy_waste"
    alert_level = "medium" if anomaly == "normal" else "high"

    return {
        "alert_key": "ai_abnormal_usage",
        "type": "ai_energy",
        "subtype": alert_subtype,
        "level": alert_level,
        "status": "active",
        "message": predictions["explanation"],
        "first_detected_at": result["created_at"],
        "last_seen_at": result["created_at"],
        "last_triggered_at": result["created_at"],
        "last_seen_normal_at": None,
        "alert_count": 1,
        "source": "smart_energy_ai",
        "source_log": None,
        "ai_prediction_id": result["created_at"],
        "waste_event": predictions["waste_event"],
        "anomaly_label": predictions["anomaly_label"],
        "efficiency_score": predictions["energy_efficiency_score"],
    }


def build_daily_ai_summary(
    latest_result: dict[str, Any],
    previous_daily_summary: dict[str, Any],
    history_written: bool,
) -> dict[str, Any]:
    created_at = latest_result["created_at"]
    bahrain_time = datetime.fromtimestamp(created_at / 1000, tz=BAHRAIN_TZ)
    day_id = bahrain_time.strftime("%Y-%m-%d")

    same_day = previous_daily_summary.get("day_id") == day_id
    previous_total_checks = (
        int(as_number(previous_daily_summary.get("total_ai_checks_today")))
        if same_day
        else 0
    )
    previous_history_records = (
        int(as_number(previous_daily_summary.get("history_records_today")))
        if same_day
        else 0
    )
    previous_waste_count = (
        int(as_number(previous_daily_summary.get("waste_predictions_today")))
        if same_day
        else 0
    )
    previous_abnormal_count = (
        int(as_number(previous_daily_summary.get("abnormal_predictions_today")))
        if same_day
        else 0
    )
    previous_score_sum = (
        as_number(previous_daily_summary.get("efficiency_score_sum"))
        if same_day
        else 0.0
    )

    predictions = latest_result["predictions"]
    total_ai_checks_today = previous_total_checks + 1
    history_records_today = previous_history_records + (1 if history_written else 0)
    waste_predictions_today = previous_waste_count + (
        1 if predictions["waste_event"]["value"] is True else 0
    )
    abnormal_predictions_today = previous_abnormal_count + (
        1 if predictions["anomaly_label"]["value"] != "normal" else 0
    )
    efficiency_score_sum = previous_score_sum + as_number(
        predictions["energy_efficiency_score"]
    )
    average_efficiency_score = round(
        efficiency_score_sum / total_ai_checks_today,
        2,
    )
    latest_explanation = predictions["explanation"]

    return {
        "day_id": day_id,
        "updated_at": created_at,
        "source": "smart_energy_ai",
        "total_ai_checks_today": total_ai_checks_today,
        "history_records_today": history_records_today,
        "waste_predictions_today": waste_predictions_today,
        "abnormal_predictions_today": abnormal_predictions_today,
        "average_efficiency_score": average_efficiency_score,
        "latest_status_message": latest_explanation,
        "latest_history_written": history_written,
        "latest_change_reason": latest_result["change_reason"],
        # Keep previous names for app compatibility.
        "prediction_count": total_ai_checks_today,
        "waste_prediction_count": waste_predictions_today,
        "abnormal_prediction_count": abnormal_predictions_today,
        "efficiency_score_sum": round(efficiency_score_sum, 2),
        "predicted_next_hour_energy_total_kWh": round(
            as_number(
                ensure_dict(predictions.get("next_hour_total_energy_kWh")).get("value")
            ),
            6,
        ),
        "predicted_next_hour_cost_total_BHD": round(
            as_number(
                ensure_dict(predictions.get("next_hour_total_cost_BHD")).get("value")
            ),
            6,
        ),
        "latest_explanation": latest_explanation,
        "summary": build_daily_summary_text(
            total_ai_checks_today,
            waste_predictions_today,
            abnormal_predictions_today,
            history_records_today,
            average_efficiency_score,
            latest_explanation,
        ),
    }


def build_daily_summary_text(
    total_ai_checks_today: int,
    waste_predictions_today: int,
    abnormal_predictions_today: int,
    history_records_today: int,
    average_efficiency_score: float,
    latest_explanation: str,
) -> str:
    if total_ai_checks_today == 0:
        return "No AI predictions have been created today yet."

    if waste_predictions_today == 0 and abnormal_predictions_today == 0:
        return (
            f"AI checked the home {total_ai_checks_today} times today "
            f"with {history_records_today} meaningful history records. "
            f"Average efficiency score is {average_efficiency_score}. "
            f"Latest status: {latest_explanation}"
        )

    return (
        f"AI checked the home {total_ai_checks_today} times today and found "
        f"{waste_predictions_today} waste events and "
        f"{abnormal_predictions_today} abnormal usage events. "
        f"It stored {history_records_today} meaningful history records. "
        f"Average efficiency score is {average_efficiency_score}. "
        f"Latest status: {latest_explanation}"
    )


def flatten_response(
    home_id: str,
    firebase_result: dict[str, Any],
    firebase_path_written: str,
) -> dict[str, Any]:
    predictions = firebase_result["predictions"]

    return {
        "home_id": home_id,
        "timestamp": firebase_result["created_at"],
        "prediction_status": firebase_result.get("prediction_status", "ok"),
        "energy_waste": predictions["waste_event"]["value"],
        "abnormal_usage": predictions["anomaly_label"]["value"],
        "recommendation_type": predictions["recommendation_type"]["value"],
        "next_hour_energy": predictions["next_hour_total_energy_kWh"]["value"],
        "next_hour_cost": predictions["next_hour_total_cost_BHD"]["value"],
        "efficiency_score": predictions["energy_efficiency_score"],
        "explanation": predictions["explanation"],
        "firebase_path_written": firebase_path_written,
        "history_written": firebase_result["history_written"],
        "change_reason": firebase_result["change_reason"],
        "same_status_count": firebase_result["same_status_count"],
        "checks_since_change": firebase_result["checks_since_change"],
        "last_checked_at": firebase_result["last_checked_at"],
        "last_changed_at": firebase_result["last_changed_at"],
        "post_processing_rules": firebase_result.get("post_processing_rules", []),
        "latest_prediction": firebase_result,
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME)


@app.post("/chat/{home_id}", response_model=ChatResponse)
def chat_home(home_id: str, request: ChatRequest) -> ChatResponse:
    user_message = request.message.strip()
    created_at = now_ms()

    if not user_message:
        raise HTTPException(status_code=400, detail="Message must not be empty.")

    context = read_chat_context(home_id)
    used_data = has_chat_context(context)

    if not used_data:
        answer = (
            "AI data is not available yet for this home. Run the AI prediction first, "
            "then ask again."
        )
        log_chat_message(home_id, user_message, answer, created_at, used_data=False)
        return ChatResponse(
            home_id=home_id,
            answer=answer,
            used_data=False,
            timestamp=created_at,
        )

    direct_answer = answer_direct_chat_question(user_message, context)
    if direct_answer is not None:
        log_chat_message(home_id, user_message, direct_answer, created_at, used_data=True)
        return ChatResponse(
            home_id=home_id,
            answer=direct_answer,
            used_data=True,
            timestamp=created_at,
        )

    prompt = build_chat_prompt(home_id, user_message, context)
    answer = call_gemini(prompt)
    log_chat_message(home_id, user_message, answer, created_at, used_data=True)

    return ChatResponse(
        home_id=home_id,
        answer=answer,
        used_data=True,
        timestamp=created_at,
    )


@app.post("/predict")
def predict_default_home() -> dict[str, Any]:
    return predict_home(DEFAULT_HOME_ID)


@app.post("/predict/{home_id}")
def predict_home(home_id: str) -> dict[str, Any]:
    payload, input_source = build_ai_payload(home_id)
    prediction = run_model(payload)
    firebase_result = build_firebase_result(home_id, payload, prediction, input_source)
    firebase_path_written = write_ai_result(home_id, firebase_result)
    return flatten_response(home_id, firebase_result, firebase_path_written)
