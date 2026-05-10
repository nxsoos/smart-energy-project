from __future__ import annotations

import json
import os
import hmac
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from timestamp_utils import TIMEZONE, BAHRAIN_TZ, ms_to_iso, now_ms
from aws_cloud_store import (
    app_get_path,
    app_set_path,
    app_update_path,
    latest_summary as cloud_latest_summary,
)


load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
load_dotenv()

SERVICE_NAME = "smart-energy-ai"
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "aws").strip().lower()
DEFAULT_HOME_ID = os.environ.get("DEFAULT_HOME_ID", "home_001")
MODEL_PATH = Path(os.environ.get("MODEL_PATH", "devices/models/smart_energy_ai.joblib"))
EFFICIENCY_SCORE_CHANGE_THRESHOLD = 3
NEXT_HOUR_ENERGY_CHANGE_THRESHOLD = 0.01
NEXT_HOUR_COST_CHANGE_THRESHOLD = 0.001
LOW_TOTAL_POWER_W = 5.0
ACTIVE_DEVICE_POWER_W = 10.0
FRESH_DATA_MAX_AGE_MS = 3 * 60 * 1000

app = FastAPI(
    title="KahrabaIQ Intelligence",
    description="Reusable EC2 AI engine for KahrabaIQ energy predictions.",
    version="1.0.0",
)

model_bundle: dict[str, Any] | None = None


class AwsPathReference:
    def __init__(self, path: str):
        self.path = "/" + path.strip().strip("/")

    def child(self, path: str) -> "AwsPathReference":
        return AwsPathReference(f"{self.path.rstrip('/')}/{path.strip().strip('/')}")

    def get(self) -> Any:
        return app_get_path(self.path)

    def set(self, value: Any) -> None:
        app_set_path(self.path, value)

    def update(self, value: dict[str, Any]) -> None:
        app_update_path(self.path, value)


class AwsPathDb:
    def ref(self, path: str) -> AwsPathReference:
        return AwsPathReference(path)


store = AwsPathDb()


class HealthResponse(BaseModel):
    status: str
    service: str


class ChatRequest(BaseModel):
    message: str
    home_id: str | None = None
    home_name: str | None = None
    scenario_id: str | None = None
    scenario_name: str | None = None
    conversation_history: list[dict[str, Any]] | None = None


class ChatResponse(BaseModel):
    home_id: str
    answer: str
    used_data: bool
    timestamp: int


def require_internal_service_token(
    x_service_token: str | None = Header(default=None),
) -> None:
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
    if not expected:
        return
    if not x_service_token or not hmac.compare_digest(x_service_token, expected):
        raise HTTPException(status_code=401, detail="Invalid internal service token.")


def initialize_storage() -> None:
    if STORAGE_BACKEND != "aws":
        raise RuntimeError("Only AWS storage is supported. Set STORAGE_BACKEND=aws.")


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
    """Fail early if AWS storage config or the model is missing."""
    initialize_storage()
    load_model()


def as_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(default)

    if isinstance(value, (int, float)):
        return float(value)

    return float(default)


def first_present(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None:
            return value
    return default


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


def timestamp_age_ms(value: Any, current_ms: int) -> int | None:
    timestamp = as_number(value, 0)
    if timestamp <= 0:
        return None
    return max(0, current_ms - int(timestamp))


def is_fresh_timestamp(value: Any, current_ms: int, max_age_ms: int = FRESH_DATA_MAX_AGE_MS) -> bool:
    age = timestamp_age_ms(value, current_ms)
    return age is not None and age <= max_age_ms


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_live_energy(latest_state: dict[str, Any]) -> dict[str, Any]:
    energy = as_dict(latest_state.get("energy"))
    devices = as_dict(latest_state.get("devices"))
    timestamp_ms = first_present(
        energy.get("updated_at_ms"),
        energy.get("timestampMs"),
        energy.get("timestamp_ms"),
        latest_state.get("updated_at_ms"),
        latest_state.get("timestampMs"),
        latest_state.get("timestamp_ms"),
    )
    current_power_w = first_present(
        energy.get("current_power_w"),
        energy.get("currentPowerW"),
        energy.get("powerW"),
        energy.get("total_power_W"),
    )
    total_energy_kwh = first_present(
        energy.get("total_energy_kWh"),
        energy.get("totalEnergyKwh"),
        energy.get("energyTodayKwh"),
    )
    total_cost_bhd = first_present(
        energy.get("total_cost_BHD"),
        energy.get("costToday"),
        energy.get("totalCostBhd"),
    )
    normalized = {
        "updated_at_ms": timestamp_ms,
        "timestamp_ms": timestamp_ms,
        "current_power_w": current_power_w,
        "total_power_W": current_power_w,
        "total_avg_power_W": current_power_w,
        "total_energy_kWh": total_energy_kwh,
        "total_estimated_energy_kWh": total_energy_kwh,
        "total_cost_BHD": total_cost_bhd,
        "total_estimated_cost_BHD": total_cost_bhd,
        "tariff_BHD_per_kWh": first_present(
            energy.get("tariff_BHD_per_kWh"),
            energy.get("tariff"),
        ),
        "voltage_V": first_present(energy.get("voltage_V"), energy.get("voltageV")),
        "current_A": first_present(energy.get("current_A"), energy.get("currentA")),
        "branches": {},
    }

    branches: dict[str, Any] = {}
    for breaker_id in ("breaker_01", "breaker_02"):
        device = as_dict(devices.get(breaker_id))
        metering = as_dict(device.get("metering"))
        power_w = first_present(
            metering.get("power_W"),
            metering.get("power_w"),
            device.get("power_W"),
            device.get("power_w"),
        )
        energy_kwh = first_present(
            metering.get("energy_kWh"),
            metering.get("energy_kwh"),
            device.get("energy_kWh"),
            device.get("energy_kwh"),
        )
        branches[breaker_id] = {
            "power_W": power_w,
            "avg_power_W": power_w,
            "peak_power_W": power_w,
            "estimated_energy_kWh": energy_kwh,
            "total_estimated_energy_kWh": energy_kwh,
        }
    normalized["branches"] = branches
    return {key: value for key, value in normalized.items() if value is not None}


def normalize_live_environment(latest_state: dict[str, Any]) -> dict[str, Any]:
    room = as_dict(latest_state.get("room"))
    timestamp_ms = first_present(
        room.get("timestampMs"),
        room.get("timestamp_ms"),
        room.get("updated_at_ms"),
        latest_state.get("updated_at_ms"),
        latest_state.get("timestampMs"),
        latest_state.get("timestamp_ms"),
    )
    motion = first_present(room.get("motion"), room.get("motionDetected"), room.get("motion_detected"))
    smoke = first_present(
        room.get("smoke"),
        room.get("smokeDetected"),
        room.get("smoke_detected"),
        room.get("gasDetected"),
        room.get("gas_detected"),
    )
    sound_raw = first_present(
        room.get("sound_raw"),
        room.get("soundLevel"),
        room.get("sound_level"),
    )
    light_level = first_present(room.get("lightLevel"), room.get("light_level"))
    light_status = first_present(room.get("light_status"), room.get("lightStatus"))
    if light_status is None and isinstance(light_level, (int, float)):
        light_status = "Bright" if light_level >= 1000 else "Dark"
    return {
        "temperature": first_present(room.get("temperature"), room.get("temp")),
        "humidity": room.get("humidity"),
        "sound_raw": sound_raw,
        "sound_level": sound_raw,
        "light_raw": light_level,
        "light_status": light_status,
        "motion": 1 if motion is True else 0 if motion is False else motion,
        "smoke": 1 if smoke is True else 0 if smoke is False else smoke,
        "noise": room.get("noise"),
        "timestamp_ms": timestamp_ms,
        "updated_at_ms": timestamp_ms,
        "sensor_timestamp_ms": timestamp_ms,
    }


def normalize_live_occupancy(latest_state: dict[str, Any]) -> dict[str, Any]:
    occupancy = as_dict(latest_state.get("occupancy"))
    occupied = first_present(occupancy.get("occupied"), occupancy.get("is_occupied"))
    normalized = dict(occupancy)
    if "state" not in normalized and isinstance(occupied, bool):
        normalized["state"] = "occupied" if occupied else "empty"
    if "occupied" not in normalized and isinstance(occupied, bool):
        normalized["occupied"] = occupied
    return normalized


def normalize_live_device_status(latest_state: dict[str, Any], device_id: str) -> dict[str, Any]:
    device = as_dict(as_dict(latest_state.get("devices")).get(device_id))
    status = as_dict(device.get("status"))
    metering = as_dict(device.get("metering"))
    return {
        **status,
        "power_W": first_present(metering.get("power_W"), device.get("power_W"), device.get("power_w")),
        "power_w": first_present(metering.get("power_w"), metering.get("power_W"), device.get("power_w"), device.get("power_W")),
        "last_seen_ms": first_present(
            status.get("last_seen_ms"),
            status.get("lastSeenMs"),
            latest_state.get("updated_at_ms"),
            latest_state.get("timestamp_ms"),
        ),
    }


def read_backend_data(home_id: str, scenario_id: str | None = None) -> dict[str, Any]:
    try:
        home_ref = store.ref(f"/homes/{home_id}")
        if home_id == "home_test" and scenario_id:
            scenario_raw = home_ref.child(f"demo_scenarios/{scenario_id}").get()
            if not isinstance(scenario_raw, dict) or not scenario_raw:
                raise HTTPException(
                    status_code=404,
                    detail=f"No demo scenario '{scenario_id}' found for {home_id}.",
                )
            backend_ref = home_ref.child(f"demo_scenarios/{scenario_id}/backend")
        else:
            backend_ref = home_ref.child("backend")

        latest_state = as_dict(home_ref.child("latest_state").get()) or as_dict(
            home_ref.child("dashboard/latest").get()
        )
        legacy_summary = as_dict(backend_ref.child("latest_hourly_summary").get())
        legacy_energy = as_dict(backend_ref.child("dashboard/energy").get())
        legacy_environment = as_dict(backend_ref.child("dashboard/environment").get())
        cloud_summary = cloud_latest_summary(home_id, "hourly") if not legacy_summary else {}

        return {
            "latest_hourly_summary": legacy_summary or cloud_summary,
            "dashboard_energy": legacy_energy or normalize_live_energy(latest_state),
            "dashboard_environment": legacy_environment or normalize_live_environment(latest_state),
            "current_state": as_dict(backend_ref.child("current_state").get()) or latest_state,
            "occupancy": as_dict(home_ref.child("occupancy/room1").get())
            or normalize_live_occupancy(latest_state),
            "breaker_01_status": as_dict(home_ref.child("devices/breaker_01/status").get())
            or normalize_live_device_status(latest_state, "breaker_01"),
            "breaker_02_status": as_dict(home_ref.child("devices/breaker_02/status").get())
            or normalize_live_device_status(latest_state, "breaker_02"),
        }
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to read backend store data: {error}",
        ) from error


def read_chat_context(home_id: str, scenario_id: str | None = None) -> dict[str, Any]:
    try:
        root_home_ref = store.ref(f"/homes/{home_id}")
        root_backend_ref = store.ref(f"/homes/{home_id}/backend")
        scenario_data = None
        if home_id == "home_test" and scenario_id:
            scenario_data = root_home_ref.child(f"demo_scenarios/{scenario_id}").get()

        if isinstance(scenario_data, dict) and scenario_data:
            home_ref = root_home_ref.child(f"demo_scenarios/{scenario_id}")
            backend_ref = home_ref.child("backend")
        else:
            home_ref = root_home_ref
            backend_ref = root_backend_ref

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

        chat_history_raw = root_backend_ref.child("ai/chat_history").get()
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
        if scenario_id:
            context["selected_scenario_id"] = scenario_id
            context["selected_scenario"] = home_ref.child("scenario").get()
        context["derived_context"] = build_chat_derived_context(context)
        return context
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to read backend store chat context: {error}",
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


def build_ai_payload(
    home_id: str,
    scenario_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    source = read_backend_data(home_id, scenario_id)

    latest_summary = ensure_dict(source["latest_hourly_summary"])
    dashboard_energy = ensure_dict(source["dashboard_energy"])
    dashboard_environment = ensure_dict(source["dashboard_environment"])
    occupancy = ensure_dict(source.get("occupancy"))
    breaker_01_status = ensure_dict(source.get("breaker_01_status"))
    breaker_02_status = ensure_dict(source.get("breaker_02_status"))

    if not latest_summary and not dashboard_energy and not dashboard_environment:
        raise HTTPException(
            status_code=404,
            detail=f"No usable backend store backend data found for home_id '{home_id}'.",
        )

    summary_energy = latest_summary.get("energy")
    if isinstance(summary_energy, dict):
        energy = {**dashboard_energy, **summary_energy}
    else:
        energy = dashboard_energy

    branches = energy.get("branches")
    if not isinstance(branches, dict):
        branches = {}

    switch_branch = get_branch_energy(branches, "breaker_01")
    ac_branch = get_branch_energy(branches, "breaker_02")
    switch_live_power_w = as_number(
        first_present(breaker_01_status.get("power_W"), breaker_01_status.get("power_w"))
    )
    ac_live_power_w = as_number(
        first_present(breaker_02_status.get("power_W"), breaker_02_status.get("power_w"))
    )

    using_hourly_summary = bool(latest_summary.get("hour_id"))
    input_source = "latest_hourly_summary" if using_hourly_summary else "dashboard_fallback"
    if scenario_id:
        input_source = f"demo_scenario:{scenario_id}:{input_source}"

    sample_count = as_number(latest_summary.get("sample_count"), 1.0)
    if sample_count <= 0 and dashboard_environment:
        sample_count = 1.0

    motion_count = as_number(latest_summary.get("motion_count"))
    if not using_hourly_summary:
        motion_count = 1.0 if dashboard_environment.get("motion") == 1 else 0.0

    temperature = first_present(
        latest_summary.get("avg_temperature"),
        dashboard_environment.get("temperature"),
    )
    humidity = first_present(
        latest_summary.get("avg_humidity"),
        dashboard_environment.get("humidity"),
    )
    sound_raw = first_present(
        latest_summary.get("avg_sound_raw"),
        dashboard_environment.get("sound_raw"),
        dashboard_environment.get("sound_level"),
    )
    light_is_bright = dashboard_environment.get("light_status") == "Bright"
    occupancy_state = str(occupancy.get("state", "unknown"))
    occupied = bool(occupancy.get("occupied"))
    occupancy_confidence = as_number(occupancy.get("confidence"))
    minutes_since_last_activity = as_number(occupancy.get("minutes_since_last_activity"))
    motion_recent = bool(occupancy.get("motion_recent"))
    sound_recent = bool(occupancy.get("sound_recent"))
    sound_active = bool(occupancy.get("sound_active"))
    derived_light_on = bool(occupancy.get("light_on")) or light_is_bright
    current_ms = now_ms()
    energy_timestamp = first_present(
        dashboard_energy.get("updated_at_ms"),
        dashboard_energy.get("timestamp_ms"),
    )
    breaker_status_timestamp = max(
        int(as_number(breaker_01_status.get("last_seen_ms"), 0)),
        int(as_number(breaker_02_status.get("last_seen_ms"), 0)),
    ) or None
    sensor_timestamp = first_present(
        dashboard_environment.get("sensor_timestamp_ms"),
        dashboard_environment.get("updated_at_ms"),
        dashboard_environment.get("timestamp_ms"),
        occupancy.get("updated_at_ms"),
    )
    breaker_data_fresh = is_fresh_timestamp(energy_timestamp, current_ms) or is_fresh_timestamp(
        breaker_status_timestamp,
        current_ms,
    )
    sensor_data_fresh = is_fresh_timestamp(sensor_timestamp, current_ms)
    dashboard_current_power_w = as_number(
        first_present(
            dashboard_energy.get("current_power_w"),
            dashboard_energy.get("total_power_W"),
            dashboard_energy.get("total_avg_power_W"),
        )
    )
    total_avg_power_w = as_number(
        first_present(energy.get("total_avg_power_W"), energy.get("total_power_W"))
    )
    total_power_for_guardrails = max(dashboard_current_power_w, switch_live_power_w + ac_live_power_w)
    if total_power_for_guardrails <= 0 and not breaker_data_fresh:
        total_power_for_guardrails = total_avg_power_w
    power_is_low = total_power_for_guardrails <= LOW_TOTAL_POWER_W

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
        "occupancy_state": occupancy_state,
        "occupancy_confidence": occupancy_confidence,
        "occupied": occupied,
        "minutes_since_last_activity": minutes_since_last_activity,
        "motion_recent": motion_recent,
        "sound_recent": sound_recent,
        "sound_active": sound_active,
        "light_on_while_empty": occupancy_state in {"empty", "probably_empty"} and derived_light_on,
        "device_on_while_empty": occupancy_state in {"empty", "probably_empty"}
        and total_power_for_guardrails > ACTIVE_DEVICE_POWER_W,
        "empty_room_power_w": (
            total_power_for_guardrails
            if occupancy_state in {"empty", "probably_empty"}
            else 0
        ),
        "power_is_low": power_is_low,
        "total_power_for_guardrails_W": round(total_power_for_guardrails, 3),
        "switch_live_power_W": round(switch_live_power_w, 3),
        "ac_live_power_W": round(ac_live_power_w, 3),
        "breaker_data_fresh": breaker_data_fresh,
        "sensor_data_fresh": sensor_data_fresh,
        "energy_data_age_ms": timestamp_age_ms(energy_timestamp, current_ms),
        "sensor_data_age_ms": timestamp_age_ms(sensor_timestamp, current_ms),
        "switch_avg_power_W": switch_branch["avg_power_W"],
        "switch_peak_power_W": switch_branch["peak_power_W"],
        "switch_energy_kWh": switch_branch["energy_kWh"],
        "ac_avg_power_W": ac_branch["avg_power_W"],
        "ac_peak_power_W": ac_branch["peak_power_W"],
        "ac_energy_kWh": ac_branch["energy_kWh"],
        "total_avg_power_W": total_avg_power_w,
        "total_peak_power_W": as_number(
            first_present(energy.get("total_peak_power_W"), energy.get("total_power_W"))
        ),
        "total_energy_kWh": as_number(
            first_present(
                energy.get("total_estimated_energy_kWh"),
                energy.get("total_energy_kWh"),
            )
        ),
        "total_cost_BHD": as_number(
            first_present(
                energy.get("total_estimated_cost_BHD"),
                energy.get("total_cost_BHD"),
            )
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

    if payload.get("breaker_data_fresh") is False:
        set_classifier_result(result, "waste_event", False)
        set_classifier_result(result, "anomaly_label", "breaker_data_stale")
        set_classifier_result(result, "recommendation_type", "check_breaker_data")
        result["energy_efficiency_score"] = 0
        result["prediction_status"] = "needs_fresh_breaker_data"
        result["explanation"] = (
            "AI is waiting for fresh breaker readings before judging energy waste."
        )
        result["post_processing_rules"].append("stale_breaker_data_guardrail")
        return result

    if payload.get("power_is_low") is True:
        set_classifier_result(result, "waste_event", False)
        set_classifier_result(result, "anomaly_label", "normal")
        set_classifier_result(result, "recommendation_type", "none")
        result["energy_efficiency_score"] = max(
            as_number(result.get("energy_efficiency_score"), 100),
            95,
        )
        result["prediction_status"] = "normal_low_power"
        result["explanation"] = (
            "No active waste detected. Current breaker power is very low."
        )
        result["post_processing_rules"].append("low_power_no_waste_guardrail")
        return result

    if has_missing_required_sensor_data(payload):
        set_classifier_result(result, "waste_event", False)
        set_classifier_result(result, "anomaly_label", "insufficient_data")
        set_classifier_result(result, "recommendation_type", "check_sensor_data")
        result["energy_efficiency_score"] = 0
        result["prediction_status"] = "needs_fresh_sensor_data"
        result["explanation"] = (
            "AI prediction was limited because required sensor data is missing. "
            "Check sensor connection and wait for fresh readings."
        )
        result["post_processing_rules"].append("missing_sensor_data")
        return result

    occupancy_state = str(payload.get("occupancy_state", "unknown"))
    room_empty = occupancy_state in {"empty", "probably_empty"}
    room_occupied = occupancy_state in {"occupied", "probably_occupied"}
    occupancy_low = as_number(payload.get("occupancy_score")) < 0.2 or room_empty
    lighting_active = as_number(payload.get("switch_avg_power_W")) > 20
    light_very_high = as_number(payload.get("bright_count")) >= 45
    total_power_active = as_number(payload.get("total_avg_power_W")) > 20
    ac_power_active = as_number(payload.get("ac_avg_power_W")) > 0
    smoke_detected = as_number(payload.get("smoke_count")) > 0
    high_temperature = (
        as_number(payload.get("avg_temperature")) >= 27
        or as_number(payload.get("high_temp_count")) > 0
    )
    occupied = room_occupied or (as_number(payload.get("motion_count")) > 0 and not occupancy_low)

    if smoke_detected:
        set_classifier_result(result, "waste_event", False)
        set_classifier_result(result, "anomaly_label", "safety_smoke_gas_warning")
        set_classifier_result(result, "recommendation_type", "check_smoke_gas_sensor")
        result["energy_efficiency_score"] = min(
            as_number(result.get("energy_efficiency_score"), 100),
            20,
        )
        result["explanation"] = (
            "Smoke or gas was detected in the scenario. This is a safety warning, "
            "so the user should check the room and sensor immediately. Energy saving "
            "recommendations are secondary to safety."
        )
        result["post_processing_rules"].append("smoke_gas_safety_warning")
        return result

    if (
        (bool(payload.get("light_on_while_empty")) or light_very_high)
        and lighting_active
        and room_empty
        and as_number(payload.get("switch_avg_power_W")) >= as_number(payload.get("ac_avg_power_W"))
    ):
        set_classifier_result(result, "waste_event", True)
        set_classifier_result(result, "anomaly_label", "light_on_no_motion")
        set_classifier_result(result, "recommendation_type", "turn_off_lights_or_switch_breaker")
        result["energy_efficiency_score"] = min(
            as_number(result.get("energy_efficiency_score"), 100),
            40,
        )
        result["explanation"] = (
            "Light or switch breaker is on while the room appears empty."
        )
        result["post_processing_rules"].append("occupancy_light_energy_waste")
        return result

    if room_empty and as_number(payload.get("empty_room_power_w")) > 10:
        set_classifier_result(result, "waste_event", True)
        set_classifier_result(result, "anomaly_label", "empty_room_power_active")
        set_classifier_result(result, "recommendation_type", "turn_off_unused_devices")
        result["explanation"] = "Power is active while the room appears empty."
        result["post_processing_rules"].append("empty_room_power_active")
        return result

    if room_occupied and ensure_dict(result.get("anomaly_label")).get("value") == "light_on_no_motion":
        set_classifier_result(result, "waste_event", False, confidence=0.8)
        set_classifier_result(result, "anomaly_label", "normal", confidence=0.8)
        set_classifier_result(result, "recommendation_type", "none", confidence=0.8)
        result["explanation"] = (
            "Occupancy evidence suggests the room is still in use, so no-motion alone is not treated as waste."
        )
        result["post_processing_rules"].append("occupancy_reduced_false_waste")
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

    if (
        waste_detected
        and anomaly == "ac_running_while_empty"
        and payload.get("ac_live_power_W", payload.get("ac_avg_power_W", 0)) > ACTIVE_DEVICE_POWER_W
    ):
        return {
            "device_id": "breaker_02",
            "action": "turn_off",
            "priority": "high",
            "requires_user_approval": True,
            "reason": "AC power is active while occupancy appears low.",
        }

    if (
        waste_detected
        and anomaly in {"light_on_no_motion", "empty_room_power_active"}
        and payload.get("switch_live_power_W", payload.get("switch_avg_power_W", 0)) > ACTIVE_DEVICE_POWER_W
    ):
        return {
            "device_id": "breaker_01",
            "action": "turn_off",
            "priority": "medium",
            "requires_user_approval": True,
            "reason": "Switch Breaker is active while the room appears empty.",
        }

    return None


def build_ai_status(prediction: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
    prediction_status = str(prediction.get("prediction_status", "ok"))
    waste_detected = bool(prediction["waste_event"]["value"])
    anomaly = str(prediction["anomaly_label"]["value"])
    recommendation_type = str(prediction["recommendation_type"]["value"])

    if prediction_status == "needs_fresh_breaker_data":
        return {
            "code": "needs_data",
            "label": "Needs Data",
            "tone": "warning",
            "summary": "Waiting for fresh breaker readings.",
            "action_title": "Check breaker data",
        }
    if prediction_status == "needs_fresh_sensor_data":
        return {
            "code": "needs_data",
            "label": "Needs Data",
            "tone": "warning",
            "summary": "Waiting for fresh room sensor readings.",
            "action_title": "Check room sensor",
        }
    if prediction_status == "normal_low_power" or (
        not waste_detected and anomaly == "normal" and recommendation_type == "none"
    ):
        return {
            "code": "normal",
            "label": "Normal",
            "tone": "safe",
            "summary": "Energy use is low or normal right now.",
            "action_title": "No action needed",
        }
    if waste_detected and payload.get("empty_room_power_w", 0) > ACTIVE_DEVICE_POWER_W:
        return {
            "code": "likely_waste",
            "label": "Likely Waste",
            "tone": "danger",
            "summary": "Power is active while the room appears empty.",
            "action_title": "Review device power",
        }
    if waste_detected:
        return {
            "code": "possible_waste",
            "label": "Possible Waste",
            "tone": "warning",
            "summary": "AI found a possible energy-saving opportunity.",
            "action_title": "Review recommendation",
        }
    return {
        "code": "watching",
        "label": "Watching",
        "tone": "info",
        "summary": "AI is monitoring an unusual but non-waste condition.",
        "action_title": "Keep monitoring",
    }


def build_ai_result(
    home_id: str,
    payload: dict[str, Any],
    prediction: dict[str, Any],
    input_source: str,
    scenario_id: str | None = None,
) -> dict[str, Any]:
    control_suggestion = make_control_suggestion(prediction, payload)
    ai_status = build_ai_status(prediction, payload)
    created_at = now_ms()
    created_at_iso = ms_to_iso(created_at)

    return {
        "home_id": home_id,
        "scenario_id": scenario_id,
        "timestamp_ms": created_at,
        "timestamp_iso": created_at_iso,
        "timezone": TIMEZONE,
        "created_at": created_at,
        "created_at_ms": created_at,
        "created_at_iso": created_at_iso,
        "model_name": prediction["model_name"],
        "model_version": prediction["model_version"],
        "input_source": input_source,
        "prediction_status": prediction.get("prediction_status", "ok"),
        "ai_status": ai_status,
        "ai_status_code": ai_status["code"],
        "ai_status_label": ai_status["label"],
        "ai_status_tone": ai_status["tone"],
        "ai_status_summary": ai_status["summary"],
        "ai_action_title": ai_status["action_title"],
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
            "ai_status": ai_status,
            "post_processing_rules": prediction.get("post_processing_rules", []),
        },
        "control_suggestion": control_suggestion,
    }


def write_ai_result(
    home_id: str,
    result: dict[str, Any],
    scenario_id: str | None = None,
) -> str:
    try:
        if home_id == "home_test" and scenario_id:
            backend_path = f"/homes/{home_id}/demo_scenarios/{scenario_id}/backend"
        else:
            backend_path = f"/homes/{home_id}/backend"

        backend_ref = store.ref(backend_path)
        prediction_path = f"{backend_path}/ai/latest_prediction"
        prediction_id = f"ai_{result['created_at']}"
        previous_prediction = ensure_dict(backend_ref.child("ai/latest_prediction").get())
        previous_daily_summary = ensure_dict(backend_ref.child("ai/daily_summary").get())

        result.update(build_deduplication_metadata(previous_prediction, result))

        updates = build_ai_store_updates(
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
            detail=f"Failed to write AI result to backend store: {error}",
        ) from error


def build_ai_store_updates(
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
        updates["recommendations/ai_energy_insight/resolved_at_ms"] = result["created_at"]
        updates["recommendations/ai_energy_insight/resolved_at_iso"] = ms_to_iso(result["created_at"])
        updates["recommendations/ai_energy_insight/updated_at"] = result["created_at"]
        updates["recommendations/ai_energy_insight/updated_at_ms"] = result["created_at"]
        updates["recommendations/ai_energy_insight/updated_at_iso"] = ms_to_iso(result["created_at"])
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
            "timestamp_ms": created_at,
            "timestamp_iso": ms_to_iso(created_at),
            "timezone": TIMEZONE,
            "last_checked_at": created_at,
            "last_checked_at_ms": created_at,
            "last_checked_at_iso": ms_to_iso(created_at),
            "last_changed_at": created_at,
            "last_changed_at_ms": created_at,
            "last_changed_at_iso": ms_to_iso(created_at),
            "same_status_count": 1,
            "checks_since_change": 0,
            "check_count": previous_check_count + 1,
            "history_written": True,
            "change_reason": get_change_reason(previous_prediction, new_prediction),
        }

    return {
        "timestamp": created_at,
        "timestamp_ms": created_at,
        "timestamp_iso": ms_to_iso(created_at),
        "timezone": TIMEZONE,
        "last_checked_at": created_at,
        "last_checked_at_ms": created_at,
        "last_checked_at_iso": ms_to_iso(created_at),
        "last_changed_at": previous_prediction.get("last_changed_at", created_at),
        "last_changed_at_ms": previous_prediction.get("last_changed_at", created_at),
        "last_changed_at_iso": ms_to_iso(previous_prediction.get("last_changed_at", created_at)),
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


def build_chat_prompt(
    home_id: str,
    user_message: str,
    context: dict[str, Any],
    *,
    home_name: str | None = None,
    scenario_id: str | None = None,
    scenario_name: str | None = None,
) -> str:
    context_json = json_safe_dumps(context)
    scenario_line = ""
    if scenario_id or scenario_name:
        scenario_line = (
            f"\nSelected demo scenario ID: {scenario_id or 'not provided'}"
            f"\nSelected demo scenario name: {scenario_name or 'not provided'}"
            "\nTreat this as demo/test data, not real live hardware data."
        )

    return f"""
You are the KahrabaIQ Intelligence assistant.

Rules:
- Answer the user's exact question first. Do not switch topics unless the user asks.
- Answer using the system data provided below.
- Do not invent energy values, costs, device states, alerts, or recommendations.
- For hypothetical "what if I connect/install..." questions, give a clearly labeled estimate range using normal appliance assumptions and explain that it is not a measured value.
- If a value is missing, say that information is not available.
- Do not control devices directly.
- You may suggest that the user review or approve a control suggestion if the data includes one.
- Do not override safety-critical alerts.
- Smoke, gas, breaker safety, and device-health alerts are handled by the safety system, not by this chatbot.
- Keep answers clear, short, and understandable.
- If the user asks a follow-up such as "explain more", "why", "how", or "what about that", use current_conversation_latest to identify what they mean.
- Do not use messages from unrelated chat sessions. The provided current_conversation_latest is the only chat memory you should use.
- Do not mention internal implementation words such as backend store, backend, database paths, JSON, device IDs, breaker_01, breaker_02, or esp32_01 unless the user explicitly asks for technical details.
- Use friendly names like "room sensor", "switch breaker", and "AC breaker".
- Use BHD for cost values and kWh for energy values when those units are present.
- Timestamp fields are epoch milliseconds. When answering about time/date, use the readable Bahrain time fields from derived_context. Do not reply with only a raw millisecond timestamp unless the user explicitly asks for the raw value.
- If the user asks for "real time", explain that this is the latest system reading time, then give the readable time and the latest available readings.
- If the user asks whether sensors are working, answer from dashboard_environment and current_state first. Mention the room sensor feed, not breaker devices.
- If the user asks whether devices/breakers are working, use device_health, devices, and derived_context.device_health_summary.
- If the user asks about sensor data, use dashboard_environment and current_state first. The AI prediction inputs are secondary and may be older or aggregated.
- Use recent_chat_history_latest_6 and current_conversation_latest to understand follow-up questions. Do not repeat the whole chat history.
- If the latest data is old or a sensor/device is offline, say that clearly.

Home ID: {home_id}
Home name: {home_name or home_id}{scenario_line}

backend store system data:
{context_json}

User question:
{user_message}
""".strip()


def answer_direct_chat_question(user_message: str, context: dict[str, Any]) -> str | None:
    """Answer simple factual backend store questions without asking Gemini to reason."""
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
        and any(
            phrase in normalized
            for phrase in [
                "working",
                "work",
                "status",
                "right now",
                "on right now",
                "on now",
                "are the sensors on",
            ]
        )
    )
    asks_sensor_data = (
        "sensor data" in normalized
        or "any sensor" in normalized
        or ("sensor" in normalized and "access" in normalized)
    )
    asks_hypothetical_power = (
        any(phrase in normalized for phrase in ["what do you think", "estimate", "predict", "will be the power"])
        and any(word in normalized for word in ["connect", "install", "add", "plug"])
        and any(word in normalized for word in ["power", "watt", "kw", "ac", "charger"])
    )

    if asks_sensor_status:
        return build_sensor_status_answer(context)

    if asks_hypothetical_power:
        return build_hypothetical_power_answer(user_message, context)

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
        return "The latest room sensor time is not available yet."

    age_text = ""
    if isinstance(age_seconds, (int, float)):
        age_text = f" That is about {round(float(age_seconds))} seconds before this chat request."

    return (
        f"The latest room sensor reading was recorded at {readable_time}."
        f"{age_text} The raw timestamp is {raw_time}."
    )


def build_sensor_status_answer(context: dict[str, Any]) -> str:
    environment = ensure_dict(context.get("dashboard_environment"))
    current_state = ensure_dict(context.get("current_state"))
    derived = ensure_dict(context.get("derived_context"))
    source = environment if environment else current_state

    if not source:
        return "I do not have a recent room sensor reading yet, so I cannot confirm the sensors right now."

    readable_time = derived.get("latest_sensor_data_time_readable")
    is_fresh = derived.get("latest_sensor_data_is_fresh")
    age_seconds = derived.get("latest_sensor_data_age_seconds")
    temperature = source.get("temperature", current_state.get("latest_temperature"))
    humidity = source.get("humidity", current_state.get("latest_humidity"))
    sound = source.get("sound_raw", current_state.get("latest_sound_raw"))
    noise = source.get("noise")
    motion = source.get("motion")
    light_status = source.get("light_status")
    smoke = source.get("smoke")

    available_sensors = []
    missing_sensors = []
    if temperature is not None and humidity is not None:
        available_sensors.append("temperature/humidity")
    else:
        missing_sensors.append("temperature/humidity")
    if light_status is not None:
        available_sensors.append("light")
    else:
        missing_sensors.append("light")
    if motion is not None:
        available_sensors.append("motion")
    else:
        missing_sensors.append("motion")
    if sound is not None or noise is not None:
        available_sensors.append("noise")
    else:
        missing_sensors.append("noise")
    if smoke is not None:
        available_sensors.append("smoke/gas")
    else:
        missing_sensors.append("smoke/gas")

    status_text = "The room sensor feed is recent." if is_fresh else "The room sensor feed looks old."
    details = []
    if temperature is not None:
        details.append(f"temperature {temperature} C")
    if humidity is not None:
        details.append(f"humidity {humidity}%")
    if motion is not None:
        details.append("motion detected" if as_number(motion) > 0 else "no motion")
    if light_status is not None:
        details.append(f"light is {light_status}")
    if smoke is not None:
        details.append("smoke/gas warning" if as_number(smoke) > 0 else "smoke/gas clear")
    if sound is not None:
        details.append(f"noise raw {sound}")

    age_text = ""
    if isinstance(age_seconds, (int, float)):
        age_text = f" It is about {round(float(age_seconds))} seconds old."

    answer = (
        f"{status_text}{age_text} I can see these sensor readings: "
        f"{', '.join(available_sensors)}."
    )
    if details:
        answer += f" Current values: {', '.join(details)}."
    if missing_sensors:
        answer += f" Missing values: {', '.join(missing_sensors)}."
    if readable_time:
        answer += f" Last reading: {readable_time}."

    return answer


def build_sensor_data_answer(context: dict[str, Any]) -> str:
    environment = ensure_dict(context.get("dashboard_environment"))
    current_state = ensure_dict(context.get("current_state"))
    source = environment if environment else current_state

    if not source:
        return "Room sensor data is not available yet."

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
    return f"Yes. Latest room sensor data: {', '.join(available)}.{time_text}"


def build_hypothetical_power_answer(user_message: str, context: dict[str, Any]) -> str:
    dashboard_energy = ensure_dict(context.get("dashboard_energy"))
    latest_summary = ensure_dict(context.get("latest_hourly_summary"))
    summary_energy = ensure_dict(latest_summary.get("energy"))
    energy = dashboard_energy if dashboard_energy else summary_energy
    current_power_w = as_number(
        energy.get("total_power_W", energy.get("total_avg_power_W"))
    )

    normalized = normalize_text(user_message)
    added_min_w = 0.0
    added_max_w = 0.0
    assumptions: list[str] = []

    if "charger" in normalized:
        added_min_w += 10
        added_max_w += 100
        assumptions.append("a normal charger is usually about 10-100 W")

    if "ac" in normalized:
        added_min_w += 800
        added_max_w += 1800
        assumptions.append("a normal split AC while cooling is often about 800-1800 W")
        assumptions.append("AC startup can briefly be higher than steady running power")

    if added_max_w == 0:
        return (
            "I can estimate it, but I need the device type or watt rating. "
            "For example, tell me the AC size or the charger's watt rating."
        )

    estimated_min_kw = (current_power_w + added_min_w) / 1000
    estimated_max_kw = (current_power_w + added_max_w) / 1000
    current_kw = current_power_w / 1000

    return (
        f"Estimated, not measured: your total power could rise from about "
        f"{current_kw:.2f} kW now to roughly {estimated_min_kw:.2f}-"
        f"{estimated_max_kw:.2f} kW. I assumed {', and '.join(assumptions)}. "
        "For an exact answer, use the device watt rating or connect it and check the live reading."
    )


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
        store.ref(f"/homes/{home_id}/backend/ai/chat_history/{key}").set(
            {
                "timestamp_ms": created_at,
                "timestamp_iso": ms_to_iso(created_at),
                "timezone": TIMEZONE,
                "user_message": user_message,
                "assistant_answer": assistant_answer,
                "created_at": created_at,
                "created_at_ms": created_at,
                "created_at_iso": ms_to_iso(created_at),
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
        "timestamp_ms": result["created_at"],
        "timestamp_iso": ms_to_iso(result["created_at"]),
        "timezone": TIMEZONE,
        "updated_at": result["created_at"],
        "updated_at_ms": result["created_at"],
        "updated_at_iso": ms_to_iso(result["created_at"]),
        "last_checked_at": result["last_checked_at"],
        "last_checked_at_ms": result["last_checked_at"],
        "last_checked_at_iso": ms_to_iso(result["last_checked_at"]),
        "last_changed_at": result["last_changed_at"],
        "last_changed_at_ms": result["last_changed_at"],
        "last_changed_at_iso": ms_to_iso(result["last_changed_at"]),
        "source": "smart_energy_ai",
        "model_name": result["model_name"],
        "model_version": result["model_version"],
        "input_source": result["input_source"],
        "prediction_status": result.get("prediction_status", "ok"),
        "ai_status": result.get("ai_status", {}),
        "ai_status_code": result.get("ai_status_code", "watching"),
        "ai_status_label": result.get("ai_status_label", "Watching"),
        "ai_status_tone": result.get("ai_status_tone", "info"),
        "ai_status_summary": result.get("ai_status_summary", ""),
        "ai_action_title": result.get("ai_action_title", ""),
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
    if result.get("prediction_status") in {"insufficient_data", "needs_fresh_sensor_data"}:
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
            "timestamp_ms": result["created_at"],
            "timestamp_iso": ms_to_iso(result["created_at"]),
            "timezone": TIMEZONE,
            "created_at": result["created_at"],
            "created_at_ms": result["created_at"],
            "created_at_iso": ms_to_iso(result["created_at"]),
            "updated_at": result["created_at"],
            "updated_at_ms": result["created_at"],
            "updated_at_iso": ms_to_iso(result["created_at"]),
            "resolved_at": None,
            "resolved_at_ms": None,
            "resolved_at_iso": None,
        }

    if result.get("prediction_status") == "needs_fresh_breaker_data":
        return {
            "recommendation_id": "ai_energy_insight",
            "type": "device_health",
            "priority": "medium",
            "title": "AI needs fresh breaker data",
            "message": predictions["explanation"],
            "source": "smart_energy_ai",
            "related_device_id": "breaker_01",
            "related_alert_key": None,
            "ai_prediction_id": result["created_at"],
            "recommendation_type": "check_breaker_data",
            "status": "active",
            "timestamp_ms": result["created_at"],
            "timestamp_iso": ms_to_iso(result["created_at"]),
            "timezone": TIMEZONE,
            "created_at": result["created_at"],
            "created_at_ms": result["created_at"],
            "created_at_iso": ms_to_iso(result["created_at"]),
            "updated_at": result["created_at"],
            "updated_at_ms": result["created_at"],
            "updated_at_iso": ms_to_iso(result["created_at"]),
            "resolved_at": None,
            "resolved_at_ms": None,
            "resolved_at_iso": None,
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
        "timestamp_ms": result["created_at"],
        "timestamp_iso": ms_to_iso(result["created_at"]),
        "timezone": TIMEZONE,
        "created_at": result["created_at"],
        "created_at_ms": result["created_at"],
        "created_at_iso": ms_to_iso(result["created_at"]),
        "updated_at": result["created_at"],
        "updated_at_ms": result["created_at"],
        "updated_at_iso": ms_to_iso(result["created_at"]),
        "resolved_at": None,
        "resolved_at_ms": None,
        "resolved_at_iso": None,
    }


def build_ai_alert(result: dict[str, Any]) -> dict[str, Any] | None:
    predictions = result["predictions"]
    if result.get("prediction_status") in {
        "insufficient_data",
        "needs_fresh_sensor_data",
        "needs_fresh_breaker_data",
        "normal_low_power",
    }:
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
        "timestamp_ms": result["created_at"],
        "timestamp_iso": ms_to_iso(result["created_at"]),
        "timezone": TIMEZONE,
        "first_detected_at": result["created_at"],
        "created_at_ms": result["created_at"],
        "created_at_iso": ms_to_iso(result["created_at"]),
        "last_seen_at": result["created_at"],
        "last_seen_ms": result["created_at"],
        "last_seen_iso": ms_to_iso(result["created_at"]),
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
    count_this_as_new_moment = history_written or not same_day
    waste_predictions_today = previous_waste_count + (
        1 if count_this_as_new_moment and predictions["waste_event"]["value"] is True else 0
    )
    abnormal_predictions_today = previous_abnormal_count + (
        1
        if count_this_as_new_moment and predictions["anomaly_label"]["value"] != "normal"
        else 0
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
        "timestamp_ms": created_at,
        "timestamp_iso": ms_to_iso(created_at),
        "timezone": TIMEZONE,
        "updated_at": created_at,
        "updated_at_ms": created_at,
        "updated_at_iso": ms_to_iso(created_at),
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
            f"AI reviewed this home {total_ai_checks_today} times today. "
            f"Most checks found normal usage. "
            f"It stored {history_records_today} meaningful changes. "
            f"Latest insight: {latest_explanation}"
        )

    return (
        f"AI reviewed this home {total_ai_checks_today} times today. "
        f"It found {waste_predictions_today} possible waste moments and "
        f"{abnormal_predictions_today} unusual usage moments after grouping repeated checks. "
        f"Average efficiency score is {average_efficiency_score}. "
        f"Latest insight: {latest_explanation}"
    )


def flatten_response(
    home_id: str,
    ai_result: dict[str, Any],
    store_path_written: str,
) -> dict[str, Any]:
    predictions = ai_result["predictions"]

    return {
        "home_id": home_id,
        "scenario_id": ai_result.get("scenario_id"),
        "timestamp": ai_result["created_at"],
        "timestamp_ms": ai_result["created_at"],
        "timestamp_iso": ms_to_iso(ai_result["created_at"]),
        "timezone": TIMEZONE,
        "prediction_status": ai_result.get("prediction_status", "ok"),
        "energy_waste": predictions["waste_event"]["value"],
        "abnormal_usage": predictions["anomaly_label"]["value"],
        "recommendation_type": predictions["recommendation_type"]["value"],
        "next_hour_energy": predictions["next_hour_total_energy_kWh"]["value"],
        "next_hour_cost": predictions["next_hour_total_cost_BHD"]["value"],
        "efficiency_score": predictions["energy_efficiency_score"],
        "explanation": predictions["explanation"],
        "store_path_written": store_path_written,
        "history_written": ai_result["history_written"],
        "change_reason": ai_result["change_reason"],
        "same_status_count": ai_result["same_status_count"],
        "checks_since_change": ai_result["checks_since_change"],
        "last_checked_at": ai_result["last_checked_at"],
        "last_changed_at": ai_result["last_changed_at"],
        "post_processing_rules": ai_result.get("post_processing_rules", []),
        "latest_prediction": ai_result,
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME)


@app.post("/chat/{home_id}", response_model=ChatResponse, dependencies=[Depends(require_internal_service_token)])
def chat_home(home_id: str, request: ChatRequest) -> ChatResponse:
    user_message = request.message.strip()
    created_at = now_ms()

    if not user_message:
        raise HTTPException(status_code=400, detail="Message must not be empty.")

    context = read_chat_context(home_id, request.scenario_id)
    if request.conversation_history:
        context["current_conversation_latest"] = request.conversation_history[-8:]
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

    prompt = build_chat_prompt(
        home_id,
        user_message,
        context,
        home_name=request.home_name,
        scenario_id=request.scenario_id,
        scenario_name=request.scenario_name,
    )
    answer = call_gemini(prompt)
    log_chat_message(home_id, user_message, answer, created_at, used_data=True)

    return ChatResponse(
        home_id=home_id,
        answer=answer,
        used_data=True,
        timestamp=created_at,
    )


@app.post("/predict", dependencies=[Depends(require_internal_service_token)])
def predict_default_home() -> dict[str, Any]:
    return predict_home(DEFAULT_HOME_ID)


@app.post("/predict/{home_id}", dependencies=[Depends(require_internal_service_token)])
def predict_home(home_id: str) -> dict[str, Any]:
    payload, input_source = build_ai_payload(home_id)
    prediction = run_model(payload)
    ai_result = build_ai_result(home_id, payload, prediction, input_source)
    store_path_written = write_ai_result(home_id, ai_result)
    return flatten_response(home_id, ai_result, store_path_written)


@app.post("/predict/{home_id}/scenario/{scenario_id}", dependencies=[Depends(require_internal_service_token)])
def predict_home_scenario(home_id: str, scenario_id: str) -> dict[str, Any]:
    if home_id != "home_test":
        raise HTTPException(
            status_code=400,
            detail="Scenario prediction is only supported for home_test.",
        )

    payload, input_source = build_ai_payload(home_id, scenario_id)
    prediction = run_model(payload)
    ai_result = build_ai_result(
        home_id,
        payload,
        prediction,
        input_source,
        scenario_id=scenario_id,
    )
    store_path_written = write_ai_result(
        home_id,
        ai_result,
        scenario_id=scenario_id,
    )
    return flatten_response(home_id, ai_result, store_path_written)
