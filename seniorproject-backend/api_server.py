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
DEVICE_STALE_AFTER_MS = 45 * 1000
VALID_CONTROL_MODES = {"manual", "assist", "auto"}
AUTO_REQUESTERS = {"ai", "backend_ai", "automation", "backend_automation"}
USER_COMMAND_REQUESTERS = {
    "flutter_app",
    "pi_dashboard",
    "api",
    "mobile_app",
    "user_approved_ai_suggestion",
}

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

CONTROL_MODE_OPTIONS = [
    {
        "value": "manual",
        "label": "Manual",
        "description": "You control all devices. The system only monitors and recommends.",
    },
    {
        "value": "assist",
        "label": "Assist",
        "description": "The system suggests actions and asks before controlling devices.",
    },
    {
        "value": "auto",
        "label": "Auto",
        "description": "The system can automatically control allowed devices to save energy.",
    },
]

DEFAULT_AUTOMATION_BY_DEVICE = {
    "breaker_01": {
        "manual_allowed": True,
        "assist_allowed": True,
        "auto_allowed": True,
        "auto_actions": ["turn_off"],
        "requires_confirmation": False,
        "cooldown_ms": 5 * 60 * 1000,
    },
    "breaker_02": {
        "manual_allowed": True,
        "assist_allowed": True,
        "auto_allowed": True,
        "auto_actions": ["turn_on", "turn_off"],
        "requires_confirmation": False,
        "comfort_min_temp": 22,
        "comfort_max_temp": 25,
        "cooldown_ms": 10 * 60 * 1000,
    },
}

SAFE_AUTO_ACTIONS = {
    "breaker_01": {"turn_off"},
    "breaker_02": {"turn_on", "turn_off"},
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
    reason: str | None = None
    source_suggestion_id: str | None = None


class DeviceCommandResponse(BaseModel):
    success: bool
    no_action: bool = False
    status: str
    message: str
    device_id: str | None = None
    command_id: str | None = None
    command: str | None = None
    current_state: str | None = None
    target_state: str | None = None
    previous_state: str | None = None


class ScenarioRunResponse(BaseModel):
    success: bool
    request_id: str
    home_id: str
    scenario_id: str
    status: str
    message: str


class ControlModeUpdateRequest(BaseModel):
    mode: str
    updated_by: str = Field("api", description="flutter_app or pi_dashboard")


class SuggestionDecisionResponse(BaseModel):
    success: bool
    home_id: str
    suggestion_id: str
    status: str
    message: str
    command_id: str | None = None


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


def command_to_target_state(command: str) -> str:
    return "on" if command == "turn_on" else "off"


def state_to_command(state: str) -> str:
    return "turn_on" if state == "on" else "turn_off"


def control_label(mode: str) -> str:
    return {"manual": "Manual", "assist": "Assist", "auto": "Auto"}.get(
        mode,
        "Assist",
    )


def control_description(mode: str) -> str:
    for option in CONTROL_MODE_OPTIONS:
        if option["value"] == mode:
            return option["description"]
    return CONTROL_MODE_OPTIONS[1]["description"]


def default_control_record(updated_by: str = "system_default") -> dict[str, Any]:
    timestamp_ms = now_ms()
    return {
        "mode": "assist",
        "updated_by": updated_by,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }


def ensure_control(home_id: str) -> dict[str, Any]:
    path = f"/homes/{home_id}/control"
    control = as_dict(safe_get(path, {}))
    mode = str(control.get("mode", "")).strip().lower()
    if mode not in VALID_CONTROL_MODES:
        control = default_control_record()
        safe_set(path, control)
    return control


def ensure_device_automation(home_id: str, device_id: str) -> dict[str, Any]:
    path = f"/homes/{home_id}/devices/{device_id}/automation"
    automation = as_dict(safe_get(path, {}))
    if automation:
        return automation

    automation = DEFAULT_AUTOMATION_BY_DEVICE.get(
        device_id,
        {
            "manual_allowed": True,
            "assist_allowed": False,
            "auto_allowed": False,
            "auto_actions": [],
            "requires_confirmation": True,
        },
    )
    safe_set(path, automation)
    return automation


def control_response(home_id: str, control: dict[str, Any]) -> dict[str, Any]:
    mode = str(control.get("mode", "assist")).lower()
    if mode not in VALID_CONTROL_MODES:
        mode = "assist"
    return {
        "home_id": home_id,
        "mode": mode,
        "available_modes": CONTROL_MODE_OPTIONS,
        "updated_at_ms": control.get("updated_at_ms"),
        "updated_at_iso": control.get("updated_at_iso"),
    }


def is_auto_requester(requested_by: str) -> bool:
    return requested_by.strip().lower() in AUTO_REQUESTERS


def check_auto_safety(
    home_id: str,
    device_id: str,
    command: str,
    device: dict[str, Any],
) -> None:
    automation = ensure_device_automation(home_id, device_id)
    if normalize_bool(automation.get("auto_allowed")) is not True:
        raise HTTPException(status_code=403, detail="Auto control is not allowed for this device.")

    auto_actions = automation.get("auto_actions")
    allowed_actions = auto_actions if isinstance(auto_actions, list) else []
    if command not in allowed_actions:
        raise HTTPException(status_code=403, detail="This auto action is not allowed for this device.")

    if command not in SAFE_AUTO_ACTIONS.get(device_id, set()):
        raise HTTPException(status_code=403, detail="This auto action is blocked by safety rules.")

    current_state = as_dict(safe_get(f"/homes/{home_id}/backend/current_state", {}))
    esp32_sensors = as_dict(safe_get(f"/homes/{home_id}/devices/esp32_01/sensors", {}))
    if normalize_bool(current_state.get("smoke")) is True or normalize_bool(
        esp32_sensors.get("smoke")
    ) is True:
        raise HTTPException(
            status_code=403,
            detail="Automatic control is blocked while smoke or gas is detected.",
        )

    if normalize_bool(automation.get("requires_confirmation")) is True:
        raise HTTPException(status_code=403, detail="This device requires user confirmation.")

    device_name = device_message_name(device_id, device).lower()
    if "main" in device_name or "critical" in device_name or "safety" in device_name:
        raise HTTPException(status_code=403, detail="Safety-critical devices cannot be auto controlled.")

    state = as_dict(safe_get(f"/homes/{home_id}/automation_state/{device_id}", {}))
    cooldown_until_ms = state.get("cooldown_until_ms")
    if isinstance(cooldown_until_ms, (int, float)) and now_ms() < int(cooldown_until_ms):
        raise HTTPException(status_code=429, detail="Automation cooldown is active for this device.")


def write_automation_log(
    home_id: str,
    device_id: str,
    device_name: str,
    command: str,
    command_id: str | None,
    reason: str | None,
) -> None:
    timestamp_ms = now_ms()
    log_id = f"auto_{timestamp_ms}"
    log = {
        "log_id": log_id,
        "home_id": home_id,
        "device_id": device_id,
        "device_name": device_name,
        "command": command,
        "target_state": command_to_target_state(command),
        "reason": reason or "Automatic energy-saving action.",
        "command_id": command_id,
        "created_at_ms": timestamp_ms,
        "created_at_iso": iso_from_ms(timestamp_ms),
        "source": "auto_mode",
    }
    safe_set(f"/homes/{home_id}/automation_logs/{log_id}", log)

    automation = ensure_device_automation(home_id, device_id)
    cooldown_ms = as_number(automation.get("cooldown_ms"))
    if cooldown_ms <= 0:
        cooldown_ms = 10 * 60 * 1000 if device_id == "breaker_02" else 5 * 60 * 1000
    safe_set(
        f"/homes/{home_id}/automation_state/{device_id}",
        {
            "last_auto_action": command,
            "last_auto_action_at_ms": timestamp_ms,
            "cooldown_until_ms": timestamp_ms + int(cooldown_ms),
        },
    )


def is_controllable_device(device_id: str, device: dict[str, Any]) -> bool:
    if device_id in CONTROLLABLE_DEVICES:
        return normalize_bool(device.get("controllable")) is not False
    return normalize_bool(device.get("controllable")) is True


def friendly_state(state: str) -> str:
    return "on" if state == "on" else "off" if state == "off" else state


def device_message_name(device_id: str, device: dict[str, Any]) -> str:
    return str(device.get("name") or DEFAULT_DEVICE_NAMES.get(device_id, device_id))


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

    explicit_state = raw.get("state")
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
    elif isinstance(explicit_state, str) and explicit_state.lower() in {
        "on",
        "off",
        "unknown",
    }:
        state = explicit_state.lower()
    else:
        state = "unknown"

    last_seen_ms = first_present(
        status.get("lastSeenMs"),
        status.get("last_seen_ms"),
        status.get("last_seen_at"),
        backend_energy.get("last_seen_at"),
    )

    online = normalize_bool(status.get("online"))
    is_stale = not isinstance(last_seen_ms, (int, float)) or (
        now_ms() - int(last_seen_ms) > DEVICE_STALE_AFTER_MS
    )
    is_breaker = str(raw.get("type") or DEFAULT_DEVICE_TYPES.get(device_id, "")).lower() in {
        "smart_breaker",
        "breaker",
    } or device_id.startswith("breaker_")
    if online is None:
        online = not is_stale
    elif is_stale and not is_breaker:
        online = False

    command_in_progress = bool(normalize_bool(raw.get("command_in_progress")))
    pending_target_state = raw.get("pending_target_state")
    if pending_target_state not in {"on", "off"}:
        pending_target_state = None
    display_state = pending_target_state if command_in_progress and pending_target_state else state
    if not online:
        display_state = "off"
    latest_command = as_dict(raw.get("last_command"))
    power_w = as_number(
        first_present(
            metering.get("power_W"),
            metering.get("power"),
            raw.get("power_W"),
            raw.get("currentPower"),
            backend_energy.get("power_W"),
        )
    )
    if not online:
        power_w = 0.0

    return {
        "device_id": device_id,
        "name": raw.get("name") or DEFAULT_DEVICE_NAMES.get(device_id, device_id),
        "type": raw.get("type") or DEFAULT_DEVICE_TYPES.get(device_id, "unknown"),
        "online": bool(online),
        "stale": is_stale,
        "controllable": is_controllable_device(device_id, raw),
        "state": state,
        "display_state": display_state,
        "power_w": power_w,
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
        "command_in_progress": command_in_progress,
        "pending_command_id": raw.get("pending_command_id"),
        "pending_target_state": pending_target_state,
        "last_requested_state": raw.get("last_requested_state"),
        "last_command": {
            "status": first_present(
                raw.get("last_command_status"),
                latest_command.get("status"),
            ),
            "user_message": first_present(
                raw.get("last_command_message"),
                latest_command.get("user_message"),
            ),
            "error_code": latest_command.get("error_code"),
        },
        "last_command_status": raw.get("last_command_status"),
        "last_command_message": raw.get("last_command_message"),
    }


def active_only(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in items:
        status = str(item.get("status", "active")).lower()
        if status in {"active", "pending", "open", "waiting_for_user"}:
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
        "backend_ai": backend_ai,
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


def build_devices(bundle: dict[str, Any], home_id: str | None = None) -> dict[str, dict[str, Any]]:
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
        formatted_device = format_device(device_id, raw)
        if home_id and formatted_device.get("controllable") is True:
            formatted_device["automation"] = ensure_device_automation(home_id, device_id)
        formatted[device_id] = formatted_device

    return formatted


def build_energy(bundle: dict[str, Any], devices: dict[str, dict[str, Any]]) -> dict[str, Any]:
    dashboard_energy = bundle["backend_dashboard_energy"]
    current_total = bundle["backend_current_total"]
    latest = bundle["dashboard_latest"]

    source = {**latest, **dashboard_energy, **current_total}
    branches = as_dict(first_present(source.get("branches"), current_total.get("branches")))
    highest_device = None
    highest_power = -1.0
    device_power_total = 0.0
    device_energy_total = 0.0
    device_cost_total = 0.0
    voltage_values: list[float] = []
    current_total_a = 0.0

    for device_id, device in devices.items():
        if device.get("type") != "smart_breaker":
            continue
        power = as_number(device.get("power_w"))
        device_power_total += power
        device_energy_total += as_number(device.get("today_kwh"))
        device_cost_total += as_number(device.get("today_cost_bhd"))

        raw_device = as_dict(bundle["devices"].get(device_id))
        metering = as_dict(raw_device.get("metering"))
        branch = as_dict(branches.get(device_id))
        voltage = as_number(first_present(metering.get("voltage_V"), branch.get("voltage_V")))
        current = as_number(first_present(metering.get("current_A"), branch.get("current_A")))
        if voltage > 0:
            voltage_values.append(voltage)
        if current > 0:
            current_total_a += current

        if power > highest_power:
            highest_power = power
            highest_device = device_id

    source_power = as_number(
        first_present(source.get("total_power_W"), source.get("current_power_w"))
    )
    source_energy = as_number(
        first_present(
            source.get("total_estimated_energy_kWh"),
            source.get("total_energy_kWh"),
            source.get("today_kwh"),
        )
    )
    source_cost = as_number(
        first_present(
            source.get("total_estimated_cost_BHD"),
            source.get("total_cost_BHD"),
            source.get("today_cost_bhd"),
        )
    )
    source_voltage = as_number(
        first_present(source.get("voltage_V"), source.get("voltage_v"), source.get("voltage"))
    )
    source_current = as_number(
        first_present(source.get("current_A"), source.get("current_a"), source.get("current"))
    )

    return {
        "current_power_w": device_power_total if device_power_total > 0 else source_power,
        "today_kwh": source_energy if source_energy > 0 else device_energy_total,
        "today_cost_bhd": source_cost if source_cost > 0 else device_cost_total,
        "voltage_V": source_voltage
        if source_voltage > 0
        else round(sum(voltage_values) / len(voltage_values), 1)
        if voltage_values
        else 0,
        "current_A": source_current if source_current > 0 else round(current_total_a, 3),
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
    anomaly = as_dict(predictions.get("anomaly_label"))
    recommendation = as_dict(predictions.get("recommendation_type"))
    next_energy = as_dict(predictions.get("next_hour_total_energy_kWh"))
    next_cost = as_dict(predictions.get("next_hour_total_cost_BHD"))

    return {
        "status": first_present(
            latest.get("prediction_status"),
            latest.get("abnormal_usage"),
            default="unknown",
        ),
        "prediction_status": first_present(latest.get("prediction_status"), default="unknown"),
        "confidence": first_present(latest.get("confidence"), waste.get("confidence")),
        "waste_confidence": first_present(latest.get("waste_confidence"), waste.get("confidence")),
        "abnormal_usage_confidence": first_present(
            latest.get("abnormal_usage_confidence"),
            anomaly.get("confidence"),
        ),
        "energy_waste": first_present(latest.get("energy_waste"), waste.get("value")),
        "abnormal_usage": first_present(latest.get("abnormal_usage"), anomaly.get("value")),
        "recommendation_type": first_present(
            latest.get("recommendation_type"),
            recommendation.get("value"),
        ),
        "next_hour_energy_kWh": first_present(
            latest.get("next_hour_energy_kWh"),
            latest.get("next_hour_energy"),
            next_energy.get("value"),
        ),
        "next_hour_cost_BHD": first_present(
            latest.get("next_hour_cost_BHD"),
            latest.get("next_hour_cost"),
            next_cost.get("value"),
        ),
        "efficiency_score": first_present(
            latest.get("efficiency_score"),
            predictions.get("energy_efficiency_score"),
        ),
        "summary": first_present(latest.get("explanation"), latest.get("summary")),
        "recommended_action": first_present(
            latest.get("recommendation_type"),
            recommendation.get("value"),
            nested(latest, "control_suggestion", "action"),
        ),
        "control_suggestion": latest.get("control_suggestion"),
        "updated_at": first_present(latest.get("updated_at"), latest.get("created_at")),
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
    devices = build_devices(bundle, home_id)
    timestamp_ms = now_ms()
    control = ensure_control(home_id)
    control_mode = str(control.get("mode", "assist")).lower()

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
        "control": {
            "mode": control_mode,
            "label": control_label(control_mode),
            "description": control_description(control_mode),
        },
        "room": build_room(bundle),
        "energy": build_energy(bundle, devices),
        "devices": devices,
        "alerts": alerts,
        "recommendations": recommendations,
        "action_suggestions": active_only(
            object_to_list(safe_get(f"/homes/{home_id}/action_suggestions/active", {}))
        ),
        "automation_logs": object_to_list(
            safe_get(f"/homes/{home_id}/automation_logs", {})
        )[-10:],
        "ai": build_ai(bundle),
        "ai_daily_summary": as_dict(as_dict(bundle["backend_ai"]).get("daily_summary")),
        "system_health": bundle["system_health"] or bundle["backend_device_health"],
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }


@app.get("/api/home/{home_id}/control")
def get_control(home_id: str) -> dict[str, Any]:
    return control_response(home_id, ensure_control(home_id))


@app.put("/api/home/{home_id}/control/mode")
def update_control_mode(
    home_id: str,
    request: ControlModeUpdateRequest,
) -> dict[str, Any]:
    mode = request.mode.strip().lower()
    if mode not in VALID_CONTROL_MODES:
        raise HTTPException(status_code=400, detail="Mode must be manual, assist, or auto.")

    timestamp_ms = now_ms()
    record = {
        "mode": mode,
        "updated_by": request.updated_by,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    history_id = f"mode_{timestamp_ms}"

    safe_update(f"/homes/{home_id}/control", record)
    safe_set(
        f"/homes/{home_id}/control/history/{history_id}",
        {"history_id": history_id, "home_id": home_id, **record},
    )

    return {
        "success": True,
        "home_id": home_id,
        "mode": mode,
        "message": f"Control mode updated to {control_label(mode)} Mode.",
    }


@app.get("/api/home/{home_id}/action-suggestions/active")
def get_active_action_suggestions(home_id: str) -> dict[str, Any]:
    suggestions = active_only(
        object_to_list(safe_get(f"/homes/{home_id}/action_suggestions/active", {}))
    )
    suggestions.sort(key=lambda item: as_number(item.get("created_at_ms")), reverse=True)
    return {"home_id": home_id, "count": len(suggestions), "suggestions": suggestions}


def read_waiting_suggestion(home_id: str, suggestion_id: str) -> dict[str, Any]:
    suggestion = as_dict(
        safe_get(f"/homes/{home_id}/action_suggestions/active/{suggestion_id}", {})
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail="Action suggestion does not exist.")
    if str(suggestion.get("status", "")).lower() != "waiting_for_user":
        raise HTTPException(status_code=409, detail="Action suggestion is not waiting for user.")
    return suggestion


@app.post(
    "/api/home/{home_id}/action-suggestions/{suggestion_id}/approve",
    response_model=SuggestionDecisionResponse,
)
def approve_action_suggestion(home_id: str, suggestion_id: str) -> SuggestionDecisionResponse:
    suggestion = read_waiting_suggestion(home_id, suggestion_id)
    device_id = str(suggestion.get("device_id", ""))
    command = str(suggestion.get("suggested_command", "")).lower()
    command_response = create_device_command(
        home_id,
        device_id,
        DeviceCommandRequest(
            command=command,
            requested_by="user_approved_ai_suggestion",
            reason=str(suggestion.get("reason", "")),
            source_suggestion_id=suggestion_id,
        ),
    )

    timestamp_ms = now_ms()
    updated = {
        **suggestion,
        "status": "approved",
        "approved_at_ms": timestamp_ms,
        "approved_at_iso": iso_from_ms(timestamp_ms),
        "command_id": command_response.command_id,
    }
    safe_set(f"/homes/{home_id}/action_suggestions/history/{suggestion_id}", updated)
    safe_set(f"/homes/{home_id}/action_suggestions/active/{suggestion_id}", None)
    return SuggestionDecisionResponse(
        success=True,
        home_id=home_id,
        suggestion_id=suggestion_id,
        status="approved",
        command_id=command_response.command_id,
        message="Action suggestion approved and command accepted.",
    )


@app.post(
    "/api/home/{home_id}/action-suggestions/{suggestion_id}/dismiss",
    response_model=SuggestionDecisionResponse,
)
def dismiss_action_suggestion(home_id: str, suggestion_id: str) -> SuggestionDecisionResponse:
    suggestion = read_waiting_suggestion(home_id, suggestion_id)
    timestamp_ms = now_ms()
    updated = {
        **suggestion,
        "status": "dismissed",
        "dismissed_at_ms": timestamp_ms,
        "dismissed_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_set(f"/homes/{home_id}/action_suggestions/history/{suggestion_id}", updated)
    safe_set(f"/homes/{home_id}/action_suggestions/active/{suggestion_id}", None)
    return SuggestionDecisionResponse(
        success=True,
        home_id=home_id,
        suggestion_id=suggestion_id,
        status="dismissed",
        message="Action suggestion dismissed.",
    )


@app.get("/api/home/{home_id}/devices")
def get_devices(home_id: str) -> dict[str, Any]:
    bundle = read_home_bundle(home_id)
    devices = build_devices(bundle, home_id)
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
    requested_by = request.requested_by.strip().lower()

    if command not in VALID_COMMANDS:
        raise HTTPException(status_code=400, detail="Command must be turn_on or turn_off.")

    control = ensure_control(home_id)
    mode = str(control.get("mode", "assist")).lower()
    if is_auto_requester(requested_by):
        if mode != "auto":
            raise HTTPException(
                status_code=403,
                detail="Automatic commands are only allowed in Auto Mode.",
            )
    elif requested_by not in USER_COMMAND_REQUESTERS:
        raise HTTPException(status_code=400, detail="Unsupported requested_by value.")

    device = safe_get(f"/homes/{home_id}/devices/{device_id}")
    if device is None:
        raise HTTPException(status_code=404, detail="Device does not exist.")
    device = as_dict(device)

    if not is_controllable_device(device_id, device):
        raise HTTPException(status_code=400, detail="Device is not controllable.")

    if is_auto_requester(requested_by):
        check_auto_safety(home_id, device_id, command, device)

    formatted_device = format_device(device_id, device)
    if formatted_device.get("online") is not True:
        raise HTTPException(
            status_code=409,
            detail={
                "success": False,
                "status": "device_offline",
                "message": "Device is offline. Check power or Wi-Fi connection.",
            },
        )

    target_state = command_to_target_state(command)
    current_state = str(formatted_device.get("state", "unknown")).lower()
    device_name = device_message_name(device_id, device)
    pending_target_state = device.get("pending_target_state")

    if normalize_bool(device.get("command_in_progress")) is True:
        if pending_target_state == target_state:
            return DeviceCommandResponse(
                success=True,
                no_action=True,
                status="command_already_in_progress",
                device_id=device_id,
                current_state=current_state,
                target_state=target_state,
                message=(
                    f"A command to turn this device {friendly_state(target_state)} "
                    "is already in progress."
                ),
            )
        raise HTTPException(
            status_code=409,
            detail={
                "success": False,
                "status": "command_in_progress",
                "message": "Another command is already in progress for this device.",
            },
        )

    if current_state == target_state:
        timestamp_ms = now_ms()
        already_record = {
            "command_id": f"cmd_{timestamp_ms}",
            "home_id": home_id,
            "device_id": device_id,
            "device_name": device_name,
            "command": command,
            "action": command,
            "target_state": target_state,
            "previous_state": current_state,
            "requested_by": request.requested_by,
            "status": "already_in_state",
            "requested_at_ms": timestamp_ms,
            "requested_at_iso": iso_from_ms(timestamp_ms),
            "result": {
                "success": True,
                "actual_state": current_state,
                "error_code": None,
                "user_message": f"{device_name} is already {target_state}.",
                "raw_error": None,
            },
        }
        safe_set(
            f"/homes/{home_id}/commands/latest_by_device/{device_id}",
            already_record,
        )
        safe_update(
            f"/homes/{home_id}/devices/{device_id}",
            {
                "last_requested_state": target_state,
                "last_command_status": "already_in_state",
                "last_command_message": f"{device_name} is already {target_state}.",
                "last_command": {
                    "status": "already_in_state",
                    "user_message": f"{device_name} is already {target_state}.",
                    "error_code": None,
                },
            },
        )
        if is_auto_requester(requested_by):
            write_automation_log(
                home_id,
                device_id,
                device_name,
                command,
                already_record["command_id"],
                request.reason,
            )
        return DeviceCommandResponse(
            success=True,
            no_action=True,
            status="already_in_state",
            device_id=device_id,
            current_state=current_state,
            target_state=target_state,
            message=f"{device_name} is already {target_state}.",
        )

    timestamp_ms = now_ms()
    timestamp_iso = iso_from_ms(timestamp_ms)
    command_id = f"cmd_{timestamp_ms}"
    command_record = {
        "command_id": command_id,
        "home_id": home_id,
        "device_id": device_id,
        "device_name": device_name,
        "command": command,
        "target_state": target_state,
        "previous_state": current_state,
        "requested_by": request.requested_by,
        "reason": request.reason,
        "source_suggestion_id": request.source_suggestion_id,
        "status": "pending",
        "requested_at_ms": timestamp_ms,
        "requested_at_iso": timestamp_iso,
        "sent_at_ms": None,
        "sent_at_iso": None,
        "confirmed_at_ms": None,
        "confirmed_at_iso": None,
        "failed_at_ms": None,
        "failed_at_iso": None,
        "timeout_at_ms": None,
        "timeout_at_iso": None,
        "result": {
            "success": None,
            "actual_state": None,
            "error_code": None,
            "user_message": None,
            "raw_error": None,
        },
        "retry_count": 0,
        "max_retries": 1,
    }

    safe_set(f"/homes/{home_id}/commands/pending/{command_id}", command_record)
    safe_set(f"/homes/{home_id}/commands/history/{command_id}", command_record)
    safe_set(f"/homes/{home_id}/commands/latest_by_device/{device_id}", command_record)
    safe_update(
        f"/homes/{home_id}/devices/{device_id}",
        {
            "command_in_progress": True,
            "pending_command_id": command_id,
            "pending_target_state": target_state,
            "last_requested_state": target_state,
            "last_command_status": "pending",
            "last_command_message": "Command sent. Waiting for breaker confirmation.",
            "last_command": {
                "status": "pending",
                "user_message": None,
                "error_code": None,
            },
        },
    )

    # Compatibility with the current Raspberry Pi Tuya controller, which watches
    # /commands/{device_id}/latest and expects the field name "action".
    legacy_command = {
        **command_record,
        "action": command,
        "created_at": timestamp_ms,
        "source": request.requested_by,
    }
    safe_set(f"/homes/{home_id}/commands/{device_id}/latest", legacy_command)

    if is_auto_requester(requested_by):
        write_automation_log(
            home_id,
            device_id,
            device_name,
            command,
            command_id,
            request.reason,
        )

    return DeviceCommandResponse(
        success=True,
        no_action=False,
        command_id=command_id,
        device_id=device_id,
        command=command,
        target_state=target_state,
        previous_state=current_state,
        status="pending",
        message="Command sent. Waiting for breaker confirmation.",
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
