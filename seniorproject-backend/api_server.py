from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import firebase_admin
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import credentials, db
from pydantic import BaseModel, Field


load_dotenv()

SERVICE_NAME = "smart_energy_api"
BAHRAIN_TZ = ZoneInfo("Asia/Bahrain")
DEFAULT_HOME_ID = "home_001"
CONTROLLABLE_DEVICES = {"breaker_01", "breaker_02"}
VALID_COMMANDS = {"turn_on", "turn_off"}

DEFAULT_DEVICE_NAMES = {
    "esp32_01": "Room Sensor",
    "breaker_01": "Switch Breaker",
    "breaker_02": "AC Breaker",
}

DEFAULT_DEVICE_TYPES = {
    "esp32_01": "sensor_hub",
    "breaker_01": "smart_breaker",
    "breaker_02": "smart_breaker",
}

app = FastAPI(
    title="Smart Energy API",
    description="Clean API layer for Flutter and Raspberry Pi dashboard clients.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DeviceCommandRequest(BaseModel):
    command: str = Field(..., description="turn_on or turn_off")
    requested_by: str = Field("api", description="flutter_app or pi_dashboard")


class DeviceCommandResponse(BaseModel):
    success: bool
    command_id: str
    device_id: str
    command: str
    status: str
    message: str


class ScenarioRunResponse(BaseModel):
    success: bool
    request_id: str
    home_id: str
    scenario_id: str
    status: str
    message: str


def now_ms() -> int:
    return int(time.time() * 1000)


def now_iso() -> str:
    return datetime.now(BAHRAIN_TZ).isoformat()


def iso_from_ms(timestamp_ms: Any) -> str | None:
    if not isinstance(timestamp_ms, (int, float)) or timestamp_ms <= 0:
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=BAHRAIN_TZ).isoformat()


def initialize_firebase() -> None:
    """Initialize Firebase Admin using a service account file or ADC."""
    if firebase_admin._apps:
        return

    database_url = os.environ.get("FIREBASE_DATABASE_URL")
    if not database_url:
        raise RuntimeError("FIREBASE_DATABASE_URL environment variable is required.")

    service_account_path = os.environ.get("SERVICE_ACCOUNT_PATH") or os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )

    if service_account_path:
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred, {"databaseURL": database_url})
    else:
        firebase_admin.initialize_app(options={"databaseURL": database_url})


@app.on_event("startup")
def startup() -> None:
    initialize_firebase()


def safe_get(path: str, default: Any = None) -> Any:
    """Read Firebase safely so one missing/broken path does not break the UI."""
    try:
        value = db.reference(path).get()
        return default if value is None else value
    except Exception:
        return default


def safe_set(path: str, value: Any) -> None:
    try:
        db.reference(path).set(value)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to write Firebase path {path}: {error}",
        ) from error


def safe_update(path: str, value: dict[str, Any]) -> None:
    try:
        db.reference(path).update(value)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to update Firebase path {path}: {error}",
        ) from error


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def object_to_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [as_dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        items: list[dict[str, Any]] = []
        for key, item in value.items():
            if isinstance(item, dict):
                items.append({"id": str(key), **item})
            else:
                items.append({"id": str(key), "value": item})
        return items
    return []


def normalize_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "on", "yes", "detected", "motion", "smoke"}:
            return True
        if normalized in {"false", "0", "off", "no", "clear", "no motion", "none"}:
            return False
    return None


def as_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def first_present(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None:
            return value
    return default


def nested(raw: dict[str, Any], *keys: str) -> Any:
    current: Any = raw
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def format_device(device_id: str, raw_device: Any) -> dict[str, Any]:
    raw = as_dict(raw_device)
    status = as_dict(raw.get("status"))
    metering = as_dict(raw.get("metering"))
    backend_energy = as_dict(raw.get("_backend_energy"))

    switch_value = first_present(
        status.get("switch"),
        status.get("on"),
        raw.get("switch"),
        raw.get("isOn"),
        backend_energy.get("switch"),
    )
    switch_bool = normalize_bool(switch_value)
    relay_status = first_present(
        status.get("relay_status"),
        raw.get("relay_status"),
        backend_energy.get("relay_status"),
    )

    if switch_bool is True:
        state = "on"
    elif switch_bool is False:
        state = "off"
    elif isinstance(relay_status, str) and relay_status:
        state = relay_status.lower()
    else:
        state = "unknown"

    last_seen_ms = first_present(
        status.get("lastSeenMs"),
        status.get("last_seen_ms"),
        status.get("last_seen_at"),
        backend_energy.get("last_seen_at"),
    )

    online = normalize_bool(status.get("online"))
    if online is None and isinstance(last_seen_ms, (int, float)):
        online = now_ms() - int(last_seen_ms) <= 3 * 60 * 1000

    return {
        "device_id": device_id,
        "name": raw.get("name") or DEFAULT_DEVICE_NAMES.get(device_id, device_id),
        "type": raw.get("type") or DEFAULT_DEVICE_TYPES.get(device_id, "unknown"),
        "online": bool(online),
        "state": state,
        "power_w": as_number(
            first_present(
                metering.get("power_W"),
                metering.get("power"),
                raw.get("power_W"),
                raw.get("currentPower"),
                backend_energy.get("power_W"),
            )
        ),
        "today_kwh": as_number(
            first_present(
                metering.get("energy_kWh"),
                metering.get("energy_today"),
                backend_energy.get("estimated_energy_kWh"),
                backend_energy.get("total_estimated_energy_kWh"),
            )
        ),
        "today_cost_bhd": as_number(
            first_present(
                metering.get("cost_BHD"),
                backend_energy.get("estimated_cost_BHD"),
                backend_energy.get("total_estimated_cost_BHD"),
            )
        ),
        "last_seen_ms": last_seen_ms,
        "last_seen_iso": iso_from_ms(last_seen_ms),
    }


def active_only(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in items:
        status = str(item.get("status", "active")).lower()
        if status in {"active", "pending", "open"}:
            result.append(item)
    return result


def read_home_bundle(home_id: str) -> dict[str, Any]:
    home_path = f"/homes/{home_id}"
    home = as_dict(safe_get(home_path, {}))
    backend = as_dict(home.get("backend"))
    backend_dashboard = as_dict(backend.get("dashboard"))
    backend_energy = as_dict(backend.get("energy"))
    backend_ai = as_dict(backend.get("ai"))

    return {
        "home": home,
        "devices": as_dict(home.get("devices")),
        "dashboard_latest": as_dict(as_dict(home.get("dashboard")).get("latest")),
        "alerts_active": as_dict(as_dict(home.get("alerts")).get("active")),
        "recommendations_active": as_dict(
            as_dict(home.get("recommendations")).get("active")
        ),
        "ai_latest": as_dict(as_dict(home.get("ai")).get("latest_prediction")),
        "occupancy_room1": as_dict(as_dict(home.get("occupancy")).get("room1")),
        "system_health": as_dict(home.get("system_health")),
        # Existing project paths. These keep the API immediately compatible.
        "backend": backend,
        "backend_dashboard_energy": as_dict(backend_dashboard.get("energy")),
        "backend_dashboard_environment": as_dict(backend_dashboard.get("environment")),
        "backend_dashboard_ai": as_dict(backend_dashboard.get("ai")),
        "backend_active_alerts": as_dict(backend.get("active_alerts")),
        "backend_recommendations": as_dict(backend.get("recommendations")),
        "backend_latest_prediction": as_dict(backend_ai.get("latest_prediction")),
        "backend_current_total": as_dict(backend_energy.get("current_total")),
        "backend_branches": as_dict(backend_energy.get("branches")),
        "backend_device_health": as_dict(backend.get("device_health")),
    }


def build_room(bundle: dict[str, Any]) -> dict[str, Any]:
    esp32 = as_dict(bundle["devices"].get("esp32_01"))
    sensors = as_dict(esp32.get("sensors"))
    status = as_dict(esp32.get("status"))
    dashboard_env = bundle["backend_dashboard_environment"]
    current_state = as_dict(bundle["backend"].get("current_state"))
    occupancy = bundle["occupancy_room1"]

    source = {
        **sensors,
        **dashboard_env,
        **current_state,
        **occupancy,
    }

    motion_bool = normalize_bool(first_present(source.get("motion"), source.get("occupied")))
    smoke_bool = normalize_bool(source.get("smoke"))
    sensor_timestamp_ms = first_present(
        sensors.get("timestamp_ms"),
        status.get("lastSeenMs"),
        status.get("last_seen_ms"),
        dashboard_env.get("updated_at"),
        current_state.get("last_processed_at"),
    )
    feed_online = normalize_bool(status.get("online"))
    if feed_online is None and isinstance(sensor_timestamp_ms, (int, float)):
        feed_online = now_ms() - int(sensor_timestamp_ms) <= 2 * 60 * 1000

    return {
        "sensor_timestamp_ms": sensor_timestamp_ms,
        "sensor_timestamp_iso": iso_from_ms(sensor_timestamp_ms),
        "feed_online": bool(feed_online),
        "temperature": first_present(source.get("temperature"), source.get("latest_temperature")),
        "humidity": first_present(source.get("humidity"), source.get("latest_humidity")),
        "aht_ok": bool(feed_online) and bool(normalize_bool(source.get("aht_ok"))),
        "ens160_ok": bool(feed_online) and bool(normalize_bool(source.get("ens160_ok"))),
        "aqi": source.get("aqi"),
        "tvoc": source.get("tvoc"),
        "eco2": source.get("eco2"),
        "light_raw": source.get("light_raw"),
        "light_status": source.get("light_status", "Unknown"),
        "motion": bool(motion_bool) if motion_bool is not None else False,
        "motion_text": source.get("motion_text")
        or ("Motion" if motion_bool else "No motion" if motion_bool is False else "Unknown"),
        "smoke": bool(smoke_bool) if smoke_bool is not None else False,
        "smoke_text": source.get("smoke_text")
        or ("Smoke/Gas" if smoke_bool else "Clear" if smoke_bool is False else "Unknown"),
        "sound_level": first_present(
            source.get("sound_level"),
            source.get("sound_raw"),
            source.get("latest_sound_raw"),
        ),
        "occupancy": first_present(
            source.get("occupancy"),
            source.get("occupancy_state"),
            status.get("occupancy"),
            default="unknown",
        ),
    }


def build_devices(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_devices = dict(bundle["devices"])
    branches = bundle["backend_branches"]
    health_devices = as_dict(bundle["backend_device_health"].get("devices"))

    for device_id in ["esp32_01", "breaker_01", "breaker_02"]:
        raw_devices.setdefault(device_id, {})

    formatted: dict[str, dict[str, Any]] = {}
    for device_id, raw_device in raw_devices.items():
        raw = as_dict(raw_device)
        raw["_backend_energy"] = as_dict(branches.get(device_id))
        health = as_dict(health_devices.get(device_id))
        if health:
            raw["status"] = {**as_dict(raw.get("status")), **health}
        formatted[device_id] = format_device(device_id, raw)

    return formatted


def build_energy(bundle: dict[str, Any], devices: dict[str, dict[str, Any]]) -> dict[str, Any]:
    dashboard_energy = bundle["backend_dashboard_energy"]
    current_total = bundle["backend_current_total"]
    latest = bundle["dashboard_latest"]

    source = {**latest, **dashboard_energy, **current_total}
    highest_device = None
    highest_power = -1.0
    for device_id, device in devices.items():
        if device.get("type") != "smart_breaker":
            continue
        power = as_number(device.get("power_w"))
        if power > highest_power:
            highest_power = power
            highest_device = device_id

    return {
        "current_power_w": as_number(
            first_present(source.get("total_power_W"), source.get("current_power_w"))
        ),
        "today_kwh": as_number(
            first_present(
                source.get("total_estimated_energy_kWh"),
                source.get("total_energy_kWh"),
                source.get("today_kwh"),
            )
        ),
        "today_cost_bhd": as_number(
            first_present(
                source.get("total_estimated_cost_BHD"),
                source.get("total_cost_BHD"),
                source.get("today_cost_bhd"),
            )
        ),
        "highest_consuming_device": highest_device if highest_power > 0 else None,
    }


def build_ai(bundle: dict[str, Any]) -> dict[str, Any]:
    latest = {
        **bundle["ai_latest"],
        **bundle["backend_latest_prediction"],
        **bundle["backend_dashboard_ai"],
    }
    predictions = as_dict(latest.get("predictions"))
    waste = as_dict(predictions.get("waste_event"))
    recommendation = as_dict(predictions.get("recommendation_type"))

    return {
        "status": first_present(
            latest.get("prediction_status"),
            latest.get("abnormal_usage"),
            default="unknown",
        ),
        "confidence": first_present(
            latest.get("confidence"),
            waste.get("confidence"),
            recommendation.get("confidence"),
        ),
        "summary": first_present(latest.get("explanation"), latest.get("summary")),
        "recommended_action": first_present(
            latest.get("recommendation_type"),
            recommendation.get("value"),
            nested(latest, "control_suggestion", "action"),
        ),
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    timestamp_ms = now_ms()
    return {
        "status": "online",
        "service": SERVICE_NAME,
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
    }


@app.get("/api/home/{home_id}/dashboard")
def get_dashboard(home_id: str) -> dict[str, Any]:
    bundle = read_home_bundle(home_id)
    devices = build_devices(bundle)
    timestamp_ms = now_ms()

    alerts = active_only(
        object_to_list(bundle["alerts_active"])
        + object_to_list(bundle["backend_active_alerts"])
    )
    recommendations = active_only(
        object_to_list(bundle["recommendations_active"])
        + object_to_list(bundle["backend_recommendations"])
    )

    return {
        "home_id": home_id,
        "room": build_room(bundle),
        "energy": build_energy(bundle, devices),
        "devices": devices,
        "alerts": alerts,
        "recommendations": recommendations,
        "ai": build_ai(bundle),
        "system_health": bundle["system_health"] or bundle["backend_device_health"],
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }


@app.get("/api/home/{home_id}/devices")
def get_devices(home_id: str) -> dict[str, Any]:
    bundle = read_home_bundle(home_id)
    devices = build_devices(bundle)
    return {
        "home_id": home_id,
        "count": len(devices),
        "devices": list(devices.values()),
    }


@app.get("/api/home/{home_id}/alerts/active")
def get_active_alerts(home_id: str) -> dict[str, Any]:
    bundle = read_home_bundle(home_id)
    alerts = active_only(
        object_to_list(bundle["alerts_active"])
        + object_to_list(bundle["backend_active_alerts"])
    )
    return {"home_id": home_id, "count": len(alerts), "alerts": alerts}


@app.get("/api/home/{home_id}/recommendations/active")
def get_active_recommendations(home_id: str) -> dict[str, Any]:
    bundle = read_home_bundle(home_id)
    recommendations = active_only(
        object_to_list(bundle["recommendations_active"])
        + object_to_list(bundle["backend_recommendations"])
    )
    return {
        "home_id": home_id,
        "count": len(recommendations),
        "recommendations": recommendations,
    }


@app.post(
    "/api/home/{home_id}/devices/{device_id}/command",
    response_model=DeviceCommandResponse,
)
def create_device_command(
    home_id: str,
    device_id: str,
    request: DeviceCommandRequest,
) -> DeviceCommandResponse:
    command = request.command.strip().lower()

    if command not in VALID_COMMANDS:
        raise HTTPException(status_code=400, detail="Command must be turn_on or turn_off.")

    if device_id not in CONTROLLABLE_DEVICES:
        raise HTTPException(status_code=400, detail="Device is not controllable.")

    device = safe_get(f"/homes/{home_id}/devices/{device_id}")
    if device is None:
        raise HTTPException(status_code=404, detail="Device does not exist.")

    timestamp_ms = now_ms()
    timestamp_iso = iso_from_ms(timestamp_ms)
    command_id = f"cmd_{timestamp_ms}"
    command_record = {
        "command_id": command_id,
        "home_id": home_id,
        "device_id": device_id,
        "command": command,
        "requested_by": request.requested_by,
        "status": "pending",
        "requested_at_ms": timestamp_ms,
        "requested_at_iso": timestamp_iso,
        "sent_at_ms": None,
        "completed_at_ms": None,
        "error": None,
    }

    safe_set(f"/homes/{home_id}/commands/pending/{command_id}", command_record)
    safe_set(f"/homes/{home_id}/commands/history/{command_id}", command_record)

    # Compatibility with the current Raspberry Pi Tuya controller, which watches
    # /commands/{device_id}/latest and expects the field name "action".
    legacy_command = {
        **command_record,
        "action": command,
        "created_at": timestamp_ms,
        "source": request.requested_by,
    }
    safe_set(f"/homes/{home_id}/commands/{device_id}/latest", legacy_command)

    return DeviceCommandResponse(
        success=True,
        command_id=command_id,
        device_id=device_id,
        command=command,
        status="pending",
        message="Command accepted.",
    )


@app.post("/api/home/{home_id}/ai/predict")
def trigger_ai_prediction(home_id: str) -> dict[str, Any]:
    ai_service_url = os.environ.get("AI_SERVICE_URL", "").strip().rstrip("/")
    if not ai_service_url:
        return {
            "success": False,
            "home_id": home_id,
            "message": "AI_SERVICE_URL is not configured.",
        }

    try:
        response = requests.post(f"{ai_service_url}/predict/{home_id}", timeout=30)
        payload = response.json() if response.content else {}
        return {
            "success": response.ok,
            "home_id": home_id,
            "status_code": response.status_code,
            "ai_response": payload,
        }
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"AI service request failed: {error}",
        ) from error


@app.post(
    "/api/home/{home_id}/scenarios/{scenario_id}/run",
    response_model=ScenarioRunResponse,
)
def run_scenario(home_id: str, scenario_id: str) -> ScenarioRunResponse:
    timestamp_ms = now_ms()
    request_id = f"scenario_{timestamp_ms}"
    scenario_request = {
        "request_id": request_id,
        "home_id": home_id,
        "scenario_id": scenario_id,
        "status": "pending",
        "requested_at_ms": timestamp_ms,
        "requested_at_iso": iso_from_ms(timestamp_ms),
        "requested_by": "api",
    }

    safe_set(
        f"/homes/{home_id}/demo/scenario_requests/{request_id}",
        scenario_request,
    )

    return ScenarioRunResponse(
        success=True,
        request_id=request_id,
        home_id=home_id,
        scenario_id=scenario_id,
        status="pending",
        message="Scenario request accepted.",
    )
