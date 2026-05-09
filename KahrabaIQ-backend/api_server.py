from __future__ import annotations

import os
import re
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import jwt
import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from jwt import PyJWKClient
from pydantic import BaseModel, Field

from occupancy_utils import DEFAULT_OCCUPANCY_SETTINGS
from timestamp_utils import (
    TIMEZONE,
    ms_to_iso,
    now_ms,
)
from home_assistant_controller import (
    HomeAssistantError,
    execute_home_assistant_command,
    get_entity_state,
    is_home_assistant_configured,
)
from aws_cloud_store import (
    app_get_path,
    app_set_path,
    app_update_path,
    create_remote_command,
    create_iot_websocket_config,
    find_remote_command,
    query_recent_remote_commands,
    update_remote_command,
)


load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
load_dotenv()

SERVICE_NAME = "smart_energy_api"
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "aws").strip().lower()
BAHRAIN_TZ = ZoneInfo(TIMEZONE)
DEFAULT_HOME_ID = "home_001"
HOME_MEMBER_LIMIT = int(os.environ.get("HOME_MEMBER_LIMIT", "3"))
PAIRING_TOKEN_TTL_MS = int(os.environ.get("PAIRING_TOKEN_TTL_SECONDS", "900")) * 1000
HOME_INVITE_TTL_MS = int(os.environ.get("HOME_INVITE_TTL_SECONDS", str(7 * 24 * 60 * 60))) * 1000
KIOSK_SESSION_TTL_SECONDS = int(os.environ.get("KIOSK_SESSION_TTL_SECONDS", "600"))
KIOSK_COMMAND_TTL_SECONDS = int(os.environ.get("KIOSK_COMMAND_TTL_SECONDS", "300"))
KIOSK_SESSION_SECRET = os.environ.get("KIOSK_SESSION_SECRET") or os.environ.get("INTERNAL_SERVICE_TOKEN") or "dev-kiosk-session-secret"
KIOSK_ALLOWED_COMMANDS = {"provision_esp32", "discover_esp32", "reset_esp32"}
MATTER_DEVICE_IDS = {"matter_socket_switch", "matter_ac_switch"}
CONTROLLABLE_DEVICES = {"breaker_01", "breaker_02", *MATTER_DEVICE_IDS}
VALID_COMMANDS = {"turn_on", "turn_off"}
DEVICE_STALE_AFTER_MS = 45 * 1000
HA_SYNC_INTERVAL_SECONDS = int(os.environ.get("HA_SYNC_INTERVAL_SECONDS", "30"))
VALID_CONTROL_MODES = {"manual", "assist", "auto"}
AUTO_REQUESTERS = {"ai", "backend_ai", "automation", "backend_automation"}
EMERGENCY_REQUESTERS = {"user_emergency_action", "emergency_auto_shutdown"}
USER_COMMAND_REQUESTERS = {
    "flutter_app",
    "pi_dashboard",
    "api",
    "mobile_app",
    "user_approved_ai_suggestion",
    "schedule",
    "schedule_manual_run",
    "user_emergency_action",
    "emergency_auto_shutdown",
}
SMOKE_ALERT_ID = "smoke_detected_room1"
SMOKE_CLEAR_DELAY_MS = 15 * 1000
VALID_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
PY_WEEKDAY_TO_DAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")
COGNITO_ISSUER = (
    f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
    if COGNITO_USER_POOL_ID
    else ""
)
COGNITO_JWKS_CLIENT = (
    PyJWKClient(f"{COGNITO_ISSUER}/.well-known/jwks.json")
    if COGNITO_ISSUER
    else None
)

DEFAULT_DEVICE_NAMES = {
    "esp32_01": "Room Sensor",
    "breaker_01": "Switch Breaker",
    "breaker_02": "AC Breaker",
    "matter_socket_switch": "Socket Switch",
    "matter_ac_switch": "AC Switch",
}

DEFAULT_DEVICE_TYPES = {
    "esp32_01": "sensor_hub",
    "breaker_01": "smart_breaker",
    "breaker_02": "smart_breaker",
    "matter_socket_switch": "matter_switch",
    "matter_ac_switch": "matter_switch",
}

MATTER_DEVICE_DEFINITIONS = {
    "matter_socket_switch": {
        "device_id": "matter_socket_switch",
        "name": "Socket Switch",
        "type": "matter_switch",
        "branch": "Socket",
        "control_method": "home_assistant",
        "ha_entity_id": "switch.socket_switch_switch_1",
        "online": True,
        "local_online": True,
        "cloud_online": False,
        "controllable": True,
        "state": "off",
        "display_state": "off",
        "power_w": None,
        "energy_supported": False,
        "command_in_progress": False,
        "pending_command_id": None,
        "pending_target_state": None,
        "last_command_status": None,
        "last_command_message": None,
        "automation": {
            "manual_allowed": True,
            "assist_allowed": True,
            "auto_allowed": True,
            "auto_actions": ["turn_off"],
            "requires_confirmation": False,
        },
        "safety": {
            "critical_device": False,
            "emergency_shutdown_allowed": True,
            "auto_shutdown_on_smoke": False,
        },
    },
    "matter_ac_switch": {
        "device_id": "matter_ac_switch",
        "name": "AC Switch",
        "type": "matter_switch",
        "branch": "AC",
        "control_method": "home_assistant",
        "ha_entity_id": "switch.ac_switch_switch_1",
        "online": True,
        "local_online": True,
        "cloud_online": False,
        "controllable": True,
        "state": "off",
        "display_state": "off",
        "power_w": None,
        "energy_supported": False,
        "command_in_progress": False,
        "pending_command_id": None,
        "pending_target_state": None,
        "last_command_status": None,
        "last_command_message": None,
        "automation": {
            "manual_allowed": True,
            "assist_allowed": True,
            "auto_allowed": True,
            "auto_actions": ["turn_on", "turn_off"],
            "requires_confirmation": False,
        },
        "safety": {
            "critical_device": False,
            "emergency_shutdown_allowed": True,
            "auto_shutdown_on_smoke": False,
        },
    },
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
    "matter_socket_switch": {
        "manual_allowed": True,
        "assist_allowed": True,
        "auto_allowed": True,
        "auto_actions": ["turn_off"],
        "requires_confirmation": False,
        "cooldown_ms": 5 * 60 * 1000,
    },
    "matter_ac_switch": {
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
    "matter_socket_switch": {"turn_off"},
    "matter_ac_switch": {"turn_on", "turn_off"},
}

DEFAULT_DEVICE_SAFETY_BY_DEVICE = {
    "breaker_01": {
        "critical_device": False,
        "emergency_shutdown_allowed": True,
        "auto_shutdown_on_smoke": True,
    },
    "breaker_02": {
        "critical_device": False,
        "emergency_shutdown_allowed": True,
        "auto_shutdown_on_smoke": False,
    },
    "matter_socket_switch": {
        "critical_device": False,
        "emergency_shutdown_allowed": True,
        "auto_shutdown_on_smoke": False,
    },
    "matter_ac_switch": {
        "critical_device": False,
        "emergency_shutdown_allowed": True,
        "auto_shutdown_on_smoke": False,
    },
}

DEFAULT_UNKNOWN_DEVICE_SAFETY = {
    "critical_device": True,
    "emergency_shutdown_allowed": False,
    "auto_shutdown_on_smoke": False,
}

DEFAULT_SETTINGS = {
    "currency": "BHD",
    "cost_per_kwh": 0.029,
    "temperature_unit": "C",
    "comfort_temperature_min": 22,
    "comfort_temperature_max": 25,
    "high_temperature_threshold": 28,
    "humidity_min": 30,
    "humidity_max": 70,
    "light_waste_minutes": 5,
    "motion_recent_seconds": DEFAULT_OCCUPANCY_SETTINGS["motion_recent_seconds"],
    "sound_recent_seconds": DEFAULT_OCCUPANCY_SETTINGS["sound_recent_seconds"],
    "occupancy_empty_minutes": 10,
    "sound_activity_threshold": DEFAULT_OCCUPANCY_SETTINGS["sound_activity_threshold"],
    "occupancy_confidence_threshold": DEFAULT_OCCUPANCY_SETTINGS["occupancy_confidence_threshold"],
    "occupancy_history_interval_minutes": DEFAULT_OCCUPANCY_SETTINGS["occupancy_history_interval_minutes"],
    "device_offline_minutes": 2,
    "quiet_hours_enabled": True,
    "quiet_hours_start": "23:00",
    "quiet_hours_end": "06:00",
    "ai_recommendations_enabled": True,
    "auto_control_enabled": True,
    "notifications_enabled": True,
    "schedules_enabled": True,
    "chat_history_retention_days": 90,
}

SETTINGS_OPTIONS = {
    "currency": ["BHD"],
    "temperature_unit": ["C", "F"],
    "cost_per_kwh": {"min": 0, "max": 1},
    "comfort_temperature_min": {"min": 16, "max": 30},
    "comfort_temperature_max": {"min": 18, "max": 35},
    "high_temperature_threshold": {"min": 20, "max": 45},
    "light_waste_minutes": {"min": 1, "max": 60},
    "motion_recent_seconds": {"min": 10, "max": 600},
    "sound_recent_seconds": {"min": 10, "max": 600},
    "occupancy_empty_minutes": {"min": 1, "max": 120},
    "sound_activity_threshold": {"min": 0, "max": 4095},
    "occupancy_confidence_threshold": {"min": 0, "max": 1},
    "occupancy_history_interval_minutes": {"min": 1, "max": 60},
    "device_offline_minutes": {"min": 1, "max": 60},
    "chat_history_retention_days": {"min": 1, "max": 3650},
}

app = FastAPI(
    title="KahrabaIQ API",
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
    source: str | None = None
    emergency: bool = False
    alert_id: str | None = None


class CloudRemoteCommandRequest(BaseModel):
    device_id: str
    command: str = Field(..., description="turn_on or turn_off")
    requested_by: str = "flutter_app"
    source: str = "cloud_remote_api"
    emergency: bool = False
    alert_id: str | None = None
    reason: str | None = None


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


class SettingsUpdateRequest(BaseModel):
    currency: str | None = None
    cost_per_kwh: float | None = None
    temperature_unit: str | None = None
    comfort_temperature_min: float | None = None
    comfort_temperature_max: float | None = None
    high_temperature_threshold: float | None = None
    humidity_min: float | None = None
    humidity_max: float | None = None
    light_waste_minutes: int | None = None
    motion_recent_seconds: int | None = None
    sound_recent_seconds: int | None = None
    occupancy_empty_minutes: int | None = None
    sound_activity_threshold: float | None = None
    occupancy_confidence_threshold: float | None = None
    occupancy_history_interval_minutes: int | None = None
    device_offline_minutes: int | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    ai_recommendations_enabled: bool | None = None
    auto_control_enabled: bool | None = None
    notifications_enabled: bool | None = None
    schedules_enabled: bool | None = None
    updated_by: str = "api"


class ScheduleCreateRequest(BaseModel):
    name: str
    device_id: str
    command: str
    time: str
    days: list[str]
    enabled: bool = True
    created_by: str = "api"


class ScheduleUpdateRequest(BaseModel):
    name: str | None = None
    device_id: str | None = None
    command: str | None = None
    time: str | None = None
    days: list[str] | None = None
    enabled: bool | None = None
    updated_by: str = "api"


class NotificationTokenRequest(BaseModel):
    user_id: str = "user_001"
    token: str
    platform: str = "android"
    installation_id: str | None = None


class ScheduleEnabledRequest(BaseModel):
    enabled: bool
    updated_by: str = "api"


class ChatProxyRequest(BaseModel):
    message: str
    home_name: str | None = None
    scenario_id: str | None = None
    scenario_name: str | None = None
    conversation_history: list[dict[str, Any]] | None = None


class ChatSessionCreateRequest(BaseModel):
    title: str | None = None


class ChatSessionRenameRequest(BaseModel):
    title: str


class ChatSessionMessageRequest(BaseModel):
    message: str
    home_name: str | None = None
    scenario_id: str | None = None
    scenario_name: str | None = None


class SignupProfileRequest(BaseModel):
    display_name: str
    home_id: str | None = None


class PiPairingTokenRequest(BaseModel):
    display_name: str | None = None
    dashboard_version: str | None = None
    firmware_version: str | None = None


class PiClaimRequest(BaseModel):
    pi_id: str
    token: str
    home_name: str | None = None


class HomeInviteCreateRequest(BaseModel):
    role: str = "member"
    max_uses: int = Field(1, ge=1, le=3)


class HomeInviteClaimRequest(BaseModel):
    invite_id: str
    token: str


class PiHeartbeatRequest(BaseModel):
    status: str = "online"
    agent_version: str | None = None
    local_ip: str | None = None
    wifi_ssid: str | None = None
    esp32: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None


class PiSensorStateRequest(BaseModel):
    home_id: str | None = None
    dashboard: dict[str, Any] = Field(default_factory=dict)
    room: dict[str, Any] = Field(default_factory=dict)
    devices: dict[str, Any] = Field(default_factory=dict)
    energy: dict[str, Any] = Field(default_factory=dict)
    commands: dict[str, Any] = Field(default_factory=dict)
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    notifications: list[dict[str, Any]] = Field(default_factory=list)
    occupancy: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
    updated_at_ms: int | None = None


class PiEsp32LinkRequest(BaseModel):
    device_id: str = "esp32_01"
    ip: str | None = None
    base_url: str | None = None
    status: dict[str, Any] = Field(default_factory=dict)


class KioskCommandCreateRequest(BaseModel):
    command: str
    payload: dict[str, Any] = Field(default_factory=dict)


class MemberCreateRequest(BaseModel):
    email: str
    role: str = "member"


class MemberRoleUpdateRequest(BaseModel):
    role: str


@dataclass(frozen=True)
class AuthContext:
    actor_type: str
    actor_id: str
    actor_role: str
    permissions: dict[str, bool]
    uid: str | None = None
    email: str | None = None
    claims: dict[str, Any] | None = None


ROLE_PERMISSIONS: dict[str, dict[str, bool]] = {
    "home_admin": {
        "can_view": True,
        "can_control_devices": True,
        "can_change_settings": True,
        "can_manage_users": True,
        "can_manage_schedules": True,
        "can_change_control_mode": True,
        "can_use_ai_chat": True,
        "can_acknowledge_alerts": True,
        "can_generate_invites": True,
    },
    "member": {
        "can_view": True,
        "can_control_devices": True,
        "can_change_settings": False,
        "can_manage_users": False,
        "can_manage_schedules": False,
        "can_change_control_mode": False,
        "can_use_ai_chat": True,
        "can_acknowledge_alerts": True,
        "can_generate_invites": False,
    },
    "viewer": {
        "can_view": True,
        "can_control_devices": False,
        "can_change_settings": False,
        "can_manage_users": False,
        "can_manage_schedules": False,
        "can_change_control_mode": False,
        "can_use_ai_chat": False,
        "can_acknowledge_alerts": False,
        "can_generate_invites": False,
    },
}

ROLE_ALIASES = {"admin": "home_admin"}


def iso_from_ms(timestamp_ms: Any) -> str | None:
    return ms_to_iso(timestamp_ms)


def initialize_storage() -> None:
    if STORAGE_BACKEND != "aws":
        raise RuntimeError("Only AWS storage is supported. Set STORAGE_BACKEND=aws.")


@app.on_event("startup")
def startup() -> None:
    initialize_storage()
    ensure_matter_devices(DEFAULT_HOME_ID)
    start_home_assistant_sync_thread(DEFAULT_HOME_ID)


def safe_get(path: str, default: Any = None) -> Any:
    """Read app storage safely so one missing path does not break the UI."""
    try:
        return app_get_path(path, default)
    except Exception:
        return default


def safe_set(path: str, value: Any) -> None:
    try:
        app_set_path(path, value)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to write DynamoDB path {path}: {error}",
        ) from error


def safe_update(path: str, value: dict[str, Any]) -> None:
    try:
        app_update_path(path, value)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to update DynamoDB path {path}: {error}",
        ) from error


def ensure_matter_devices(home_id: str) -> None:
    timestamp_ms = now_ms()
    timestamp_iso = iso_from_ms(timestamp_ms)
    for device_id, definition in MATTER_DEVICE_DEFINITIONS.items():
        path = f"/homes/{home_id}/devices/{device_id}"
        existing = as_dict(safe_get(path, {}))
        created_at_ms = existing.get("created_at_ms") or timestamp_ms
        created_at_iso = existing.get("created_at_iso") or timestamp_iso
        static_update = {
            **definition,
            "created_at_ms": created_at_ms,
            "created_at_iso": created_at_iso,
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": timestamp_iso,
        }
        if existing:
            static_update["state"] = existing.get("state", definition["state"])
            static_update["display_state"] = existing.get(
                "display_state",
                static_update["state"],
            )
            static_update["command_in_progress"] = existing.get("command_in_progress", False)
            static_update["pending_command_id"] = existing.get("pending_command_id")
            static_update["pending_target_state"] = existing.get("pending_target_state")
            static_update["last_command_status"] = existing.get("last_command_status")
            static_update["last_command_message"] = existing.get("last_command_message")
            static_update["last_command"] = existing.get("last_command")
        safe_update(path, static_update) if existing else safe_set(path, static_update)


def ha_error_payload(error: HomeAssistantError) -> dict[str, str]:
    return {
        "error_code": error.code,
        "user_message": error.user_message,
        "raw_error": str(error.raw_error or error),
    }


def update_ha_device_from_state(home_id: str, device_id: str, state: str) -> None:
    timestamp_ms = now_ms()
    online = state in {"on", "off"}
    safe_update(
        f"/homes/{home_id}/devices/{device_id}",
        {
            "state": state,
            "display_state": state,
            "online": online,
            "local_online": online,
            "cloud_online": False,
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": iso_from_ms(timestamp_ms),
        },
    )


def mark_ha_device_error(
    home_id: str,
    device_id: str,
    error: HomeAssistantError,
    *,
    state: str | None = None,
) -> None:
    timestamp_ms = now_ms()
    device_updates: dict[str, Any] = {
        "online": False,
        "local_online": False,
        "cloud_online": False,
        "command_in_progress": False,
        "pending_command_id": None,
        "pending_target_state": None,
        "last_command_status": "failed",
        "last_command_message": error.user_message,
        "last_command": {
            "status": "failed",
            "user_message": error.user_message,
            "error_code": error.code,
        },
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    if state:
        device_updates["state"] = state
        device_updates["display_state"] = state
    safe_update(f"/homes/{home_id}/devices/{device_id}", device_updates)


def sync_home_assistant_device(home_id: str, device_id: str, device: dict[str, Any]) -> str:
    entity_id = str(device.get("ha_entity_id") or "").strip()
    if not entity_id:
        raise HomeAssistantError(
            "HA_ENTITY_NOT_FOUND",
            "Matter switch was not found in Home Assistant.",
            "Missing ha_entity_id.",
        )
    try:
        state = get_entity_state(entity_id)
        update_ha_device_from_state(home_id, device_id, state)
        return state
    except HomeAssistantError as error:
        mark_ha_device_error(home_id, device_id, error, state="unknown")
        raise


def sync_home_assistant_devices(home_id: str) -> dict[str, Any]:
    devices = as_dict(safe_get(f"/homes/{home_id}/devices", {}))
    results: dict[str, Any] = {}
    for device_id, raw_device in devices.items():
        device = as_dict(raw_device)
        if str(device.get("control_method", "")).lower() != "home_assistant":
            continue
        try:
            results[device_id] = {"state": sync_home_assistant_device(home_id, device_id, device)}
        except HomeAssistantError as error:
            results[device_id] = {"error": ha_error_payload(error)}
    return results


_ha_sync_thread_started = False


def start_home_assistant_sync_thread(home_id: str) -> None:
    global _ha_sync_thread_started
    if _ha_sync_thread_started or not is_home_assistant_configured():
        return
    _ha_sync_thread_started = True

    def sync_loop() -> None:
        while True:
            try:
                sync_home_assistant_devices(home_id)
            except Exception:
                pass
            time.sleep(max(5, HA_SYNC_INTERVAL_SECONDS))

    thread = threading.Thread(target=sync_loop, name="ha-state-sync", daemon=True)
    thread.start()


def get_permissions_for_role(role: str) -> dict[str, bool]:
    normalized = ROLE_ALIASES.get(role.strip().lower(), role.strip().lower())
    if normalized not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=400, detail="Invalid role.")
    return dict(ROLE_PERMISSIONS[normalized])


def validate_role(role: str) -> str:
    normalized = ROLE_ALIASES.get(role.strip().lower(), role.strip().lower())
    if normalized not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=400, detail="Role must be home_admin, member, or viewer.")
    return normalized


def platform_admin_emails() -> set[str]:
    return {
        item.strip().lower()
        for item in os.environ.get("PLATFORM_ADMIN_EMAILS", "").split(",")
        if item.strip()
    }


def platform_role_for_email(email: str) -> str:
    return "platform_admin" if email.strip().lower() in platform_admin_emails() else "user"


def is_platform_admin_profile(profile: dict[str, Any]) -> bool:
    return str(profile.get("platform_role") or "user").lower() == "platform_admin"


def home_member_count(home_id: str, *, roles: set[str] | None = None) -> int:
    members = as_dict(safe_get(f"/homes/{home_id}/members", {}))
    count = 0
    for raw_member in members.values():
        member = as_dict(raw_member)
        role = validate_role(str(member.get("role", "viewer")))
        if roles is None or role in roles:
            count += 1
    return count


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def secret_matches(secret: str, expected: str | None) -> bool:
    if not secret or not expected:
        return False
    expected_text = str(expected)
    candidate_hash = hash_secret(secret)
    return hmac.compare_digest(secret, expected_text) or hmac.compare_digest(
        candidate_hash,
        expected_text,
    )


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def audit_log(
    home_id: str,
    actor: AuthContext | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    result: str = "success",
) -> None:
    timestamp_ms = now_ms()
    audit_id = f"audit_{timestamp_ms}"
    try:
        safe_set(
            f"/homes/{home_id}/audit_logs/{audit_id}",
            {
                "audit_id": audit_id,
                "home_id": home_id,
                "actor_type": actor.actor_type if actor else "service",
                "actor_id": actor.actor_id if actor else SERVICE_NAME,
                "actor_role": actor.actor_role if actor else "service",
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "details": details or {},
                "result": result,
                "created_at_ms": timestamp_ms,
                "created_at_iso": iso_from_ms(timestamp_ms),
            },
        )
    except Exception:
        return


def user_has_permission(uid: str, home_id: str, permission: str) -> bool:
    member = as_dict(safe_get(f"/homes/{home_id}/members/{uid}", {}))
    role = validate_role(str(member.get("role", "viewer"))) if member else "viewer"
    permissions = {**get_permissions_for_role(role), **as_dict(member.get("permissions"))}
    return permissions.get(permission) is True


def home_exists(home_id: str) -> bool:
    return safe_get(f"/homes/{home_id}") is not None


def verify_cognito_id_token(token: str) -> dict[str, Any]:
    if not COGNITO_JWKS_CLIENT or not COGNITO_APP_CLIENT_ID or not COGNITO_ISSUER:
        raise ValueError("Cognito authentication is not configured.")
    signing_key = COGNITO_JWKS_CLIENT.get_signing_key_from_jwt(token)
    decoded = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=COGNITO_APP_CLIENT_ID,
        issuer=COGNITO_ISSUER,
    )
    if decoded.get("token_use") != "id":
        raise ValueError("Cognito token is not an ID token.")
    return decoded


def ensure_user_profile(uid: str, email: str, display_name: str) -> dict[str, Any]:
    profile = as_dict(safe_get(f"/users/{uid}", {}))
    timestamp_ms = now_ms()
    timestamp_iso = iso_from_ms(timestamp_ms)
    platform_role = platform_role_for_email(email)
    if profile:
        updates: dict[str, Any] = {
            "email": profile.get("email") or email,
            "display_name": profile.get("display_name") or display_name or email or uid,
            "platform_role": platform_role,
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": timestamp_iso,
        }
        safe_update(f"/users/{uid}", updates)
        return {**profile, **updates}
    profile = {
        "uid": uid,
        "email": email,
        "display_name": display_name or email or uid,
        "platform_role": platform_role,
        "default_home_id": None,
        "homes": {},
        "created_at_ms": timestamp_ms,
        "created_at_iso": timestamp_iso,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": timestamp_iso,
    }
    safe_set(f"/users/{uid}", profile)
    return profile


def find_user_profile_by_email(email: str) -> dict[str, Any]:
    normalized = email.strip().lower()
    for uid, raw_profile in as_dict(safe_get("/users", {})).items():
        profile = as_dict(raw_profile)
        if str(profile.get("email") or "").strip().lower() == normalized:
            return {"uid": str(profile.get("uid") or uid), **profile}
    return {}


def authenticate_user_token(token: str) -> AuthContext:
    try:
        decoded = verify_cognito_id_token(token)
    except Exception as error:
        raise HTTPException(status_code=401, detail="Invalid Cognito ID token.") from error

    uid = str(decoded.get("uid") or decoded.get("sub") or "")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user ID token.")
    email = str(decoded.get("email") or "")
    display_name = str(decoded.get("name") or email or uid)
    profile = ensure_user_profile(uid, email, display_name)
    email = str(email or profile.get("email") or "")
    platform_role = platform_role_for_email(email)
    if profile.get("platform_role") != platform_role:
        safe_update(f"/users/{uid}", {"platform_role": platform_role, "updated_at_ms": now_ms(), "updated_at_iso": iso_from_ms(now_ms())})
    return AuthContext(
        actor_type="user",
        actor_id=uid,
        actor_role=platform_role,
        uid=uid,
        email=email,
        claims=decoded,
        permissions={},
    )


def authenticate_trusted_device(home_id: str, device_token: str) -> AuthContext:
    trusted_devices = as_dict(safe_get(f"/homes/{home_id}/trusted_devices", {}))
    for device_id, raw_device in trusted_devices.items():
        device = as_dict(raw_device)
        if device.get("active") is not True:
            continue
        expected = device.get("token_hash") or device.get("api_key_hash")
        if secret_matches(device_token, str(expected or "")):
            safe_update(
                f"/homes/{home_id}/trusted_devices/{device_id}",
                {"last_seen_at_ms": now_ms(), "last_seen_at_iso": iso_from_ms(now_ms())},
            )
            return AuthContext(
                actor_type="trusted_device",
                actor_id=str(device.get("device_id") or device_id),
                actor_role=str(device.get("device_type") or "trusted_device"),
                permissions={key: bool(value) for key, value in as_dict(device.get("permissions")).items()},
            )

    fallback_token = os.environ.get("PI_DASHBOARD_TOKEN", "")
    if secret_matches(device_token, fallback_token):
        return AuthContext(
            actor_type="trusted_device",
            actor_id="pi_dashboard_01",
            actor_role="pi_dashboard",
            permissions={
                "can_view": True,
                "can_control_devices": True,
                "can_change_settings": False,
                "can_manage_schedules": True,
                "can_change_control_mode": False,
                "can_use_ai_chat": True,
                "can_acknowledge_alerts": True,
            },
        )
    raise HTTPException(status_code=401, detail="Invalid trusted device token.")


def authenticate_service_token(service_token: str) -> AuthContext:
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
    if not secret_matches(service_token, expected):
        raise HTTPException(status_code=401, detail="Invalid internal service token.")
    return AuthContext(
        actor_type="service",
        actor_id=SERVICE_NAME,
        actor_role="service",
        permissions={permission: True for permissions in ROLE_PERMISSIONS.values() for permission in permissions},
    )


def require_authenticated_user(
    authorization: str | None = Header(default=None),
) -> AuthContext:
    token = bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token.")
    return authenticate_user_token(token)


def require_permission(home_id: str, permission: str):
    return require_home_permission(permission)


def require_home_permission(permission: str):
    def dependency(
        home_id: str,
        authorization: str | None = Header(default=None),
        x_device_token: str | None = Header(default=None),
        x_service_token: str | None = Header(default=None),
    ) -> AuthContext:
        if not home_exists(home_id):
            raise HTTPException(status_code=404, detail="Home does not exist.")

        token = bearer_token(authorization)
        actor: AuthContext
        if token:
            actor = authenticate_user_token(token)
            if actor.actor_role == "platform_admin":
                actor = AuthContext(
                    actor_type=actor.actor_type,
                    actor_id=actor.actor_id,
                    actor_role="platform_admin",
                    uid=actor.uid,
                    email=actor.email,
                    claims=actor.claims,
                    permissions={permission: True for permissions in ROLE_PERMISSIONS.values() for permission in permissions},
                )
                return actor
            member = as_dict(safe_get(f"/homes/{home_id}/members/{actor.uid}", {}))
            if not member:
                audit_log(home_id, actor, "permission_check_failed", "home", home_id, {"permission": permission}, "denied")
                raise HTTPException(status_code=403, detail="User is not a member of this home.")
            role = validate_role(str(member.get("role", "viewer")))
            permissions = {**get_permissions_for_role(role), **as_dict(member.get("permissions"))}
            actor = AuthContext(
                actor_type=actor.actor_type,
                actor_id=actor.actor_id,
                actor_role=role,
                uid=actor.uid,
                email=actor.email,
                claims=actor.claims,
                permissions=permissions,
            )
        elif x_device_token:
            actor = authenticate_trusted_device(home_id, x_device_token)
        elif x_service_token:
            actor = authenticate_service_token(x_service_token)
        else:
            raise HTTPException(status_code=401, detail="Authentication token is required.")

        if actor.permissions.get(permission) is not True:
            audit_log(home_id, actor, "permission_check_failed", "home", home_id, {"permission": permission}, "denied")
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action.")
        return actor

    return dependency


def require_home_role(required_role: str):
    def dependency(actor: AuthContext = Depends(require_home_permission("can_view"))) -> AuthContext:
        normalized_required = ROLE_ALIASES.get(required_role, required_role)
        if actor.actor_role not in {normalized_required, "platform_admin"} and actor.actor_type != "service":
            raise HTTPException(status_code=403, detail="Admin role is required.")
        return actor

    return dependency


def admin_count(home_id: str) -> int:
    members = as_dict(safe_get(f"/homes/{home_id}/members", {}))
    return sum(1 for member in members.values() if validate_role(str(as_dict(member).get("role", "viewer"))) == "home_admin")


def member_record(uid: str, email: str, display_name: str, role: str) -> dict[str, Any]:
    timestamp_ms = now_ms()
    role = validate_role(role)
    permissions = get_permissions_for_role(role)
    return {
        "uid": uid,
        "email": email,
        "display_name": display_name,
        "role": role,
        "permissions": permissions,
        "added_at_ms": timestamp_ms,
        "added_at_iso": iso_from_ms(timestamp_ms),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }


def add_user_to_home(uid: str, email: str, display_name: str, home_id: str, role: str) -> dict[str, Any]:
    record = member_record(uid, email, display_name, role)
    safe_set(f"/homes/{home_id}/members/{uid}", record)
    profile = as_dict(safe_get(f"/users/{uid}", {}))
    safe_update(
        f"/users/{uid}",
        {
            "uid": uid,
            "email": email,
            "display_name": display_name,
            "platform_role": profile.get("platform_role") or platform_role_for_email(email),
            "default_home_id": profile.get("default_home_id") or home_id,
            "homes": {**as_dict(profile.get("homes")), home_id: {"role": record["role"], **record["permissions"]}},
            "created_at_ms": profile.get("created_at_ms") or record["added_at_ms"],
            "created_at_iso": profile.get("created_at_iso") or record["added_at_iso"],
            "updated_at_ms": record["updated_at_ms"],
            "updated_at_iso": record["updated_at_iso"],
        },
    )
    return record


def create_home_for_pi(pi_id: str, uid: str, email: str, display_name: str, home_name: str | None) -> str:
    timestamp_ms = now_ms()
    preferred_home_id = os.environ.get("DEFAULT_HOME_ID", "").strip()
    if preferred_home_id:
        existing_home = as_dict(safe_get(f"/homes/{preferred_home_id}", {}))
        if not existing_home or existing_home.get("pi_id") in {None, "", pi_id}:
            home_id = preferred_home_id
        else:
            home_id = f"home_{timestamp_ms}_{secrets.token_hex(3)}"
    else:
        home_id = f"home_{timestamp_ms}_{secrets.token_hex(3)}"
    safe_set(
        f"/homes/{home_id}",
        {
            "home_id": home_id,
            "name": (home_name or "KahrabaIQ Home").strip() or "KahrabaIQ Home",
            "owner_uid": uid,
            "pi_id": pi_id,
            "status": "active",
            "created_at_ms": timestamp_ms,
            "created_at_iso": iso_from_ms(timestamp_ms),
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": iso_from_ms(timestamp_ms),
        },
    )
    safe_set(f"/homes/{home_id}/settings", {**DEFAULT_SETTINGS, "updated_at_ms": timestamp_ms, "updated_at_iso": iso_from_ms(timestamp_ms)})
    safe_set(f"/homes/{home_id}/control", {"mode": "assist", "updated_at_ms": timestamp_ms, "updated_at_iso": iso_from_ms(timestamp_ms)})
    ensure_matter_devices(home_id)
    add_user_to_home(uid, email, display_name, home_id, "home_admin")
    safe_update(
        f"/pis/{pi_id}",
        {
            "pi_id": pi_id,
            "status": "paired",
            "home_id": home_id,
            "paired_by_uid": uid,
            "paired_at_ms": timestamp_ms,
            "paired_at_iso": iso_from_ms(timestamp_ms),
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": iso_from_ms(timestamp_ms),
        },
    )
    return home_id


@app.post("/api/auth/complete-signup")
def complete_signup_profile(
    request: SignupProfileRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token.")
    try:
        decoded = verify_cognito_id_token(token)
    except Exception as error:
        raise HTTPException(status_code=401, detail="Invalid Cognito ID token.") from error

    uid = str(decoded.get("uid") or decoded.get("sub") or "")
    email = str(decoded.get("email") or "")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid user ID token.")
    display_name = request.display_name.strip() or email or uid
    existing_profile = as_dict(safe_get(f"/users/{uid}", {}))
    requested_home_id = (request.home_id or "").strip()
    if existing_profile and not requested_home_id:
        return {
            "success": True,
            "home_id": existing_profile.get("default_home_id"),
            "uid": uid,
            "role": None,
            "platform_role": existing_profile.get("platform_role", platform_role_for_email(email)),
            "created": False,
        }

    timestamp_ms = now_ms()
    timestamp_iso = iso_from_ms(timestamp_ms)
    platform_role = platform_role_for_email(email)
    homes = as_dict(existing_profile.get("homes"))
    profile = {
        "uid": uid,
        "email": email,
        "display_name": display_name,
        "platform_role": platform_role,
        "default_home_id": existing_profile.get("default_home_id"),
        "homes": homes,
        "created_at_ms": existing_profile.get("created_at_ms") or timestamp_ms,
        "created_at_iso": existing_profile.get("created_at_iso") or timestamp_iso,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": timestamp_iso,
    }
    safe_set(f"/users/{uid}", profile)
    return {
        "success": True,
        "home_id": profile.get("default_home_id"),
        "uid": uid,
        "role": None,
        "platform_role": platform_role,
        "created": not bool(existing_profile),
    }


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


@app.get("/api/me")
def get_me(actor: AuthContext = Depends(require_authenticated_user)) -> dict[str, Any]:
    profile = as_dict(safe_get(f"/users/{actor.uid}", {}))
    homes = []
    profile_homes = {
        **as_dict(profile.get("homes")),
        **as_dict(safe_get(f"/users/{actor.uid}/homes", {})),
    }
    for home_id, raw_access in profile_homes.items():
        access = as_dict(raw_access)
        home = as_dict(safe_get(f"/homes/{home_id}", {}))
        role = validate_role(str(access.get("role", "viewer")))
        homes.append(
            {
                "home_id": home_id,
                "name": home.get("name") or home_id,
                "role": role,
                "permissions": {**get_permissions_for_role(role), **as_dict(access.get("permissions"))},
                "pi_id": home.get("pi_id"),
                "status": home.get("status", "active"),
            }
        )
    platform_role = platform_role_for_email(actor.email or "")
    return {
        "success": True,
        "uid": actor.uid,
        "email": actor.email,
        "display_name": profile.get("display_name") or actor.email,
        "platform_role": platform_role,
        "is_platform_admin": platform_role == "platform_admin",
        "default_home_id": profile.get("default_home_id"),
        "homes": homes,
    }


def authenticate_pi_request(pi_id: str, device_token: str) -> dict[str, Any]:
    pi_id = pi_id.strip()
    if not pi_id or not device_token:
        raise HTTPException(status_code=401, detail="Pi ID and device token are required.")
    pi = as_dict(safe_get(f"/pis/{pi_id}", {}))
    if not pi:
        timestamp_ms = now_ms()
        pi = {
            "pi_id": pi_id,
            "status": "unpaired",
            "token_hash": hash_secret(device_token),
            "created_at_ms": timestamp_ms,
            "created_at_iso": iso_from_ms(timestamp_ms),
        }
        safe_set(f"/pis/{pi_id}", pi)
    elif not secret_matches(device_token, str(pi.get("token_hash") or "")):
        raise HTTPException(status_code=401, detail="Invalid Pi device token.")
    safe_update(f"/pis/{pi_id}", {"last_seen_at_ms": now_ms(), "last_seen_at_iso": iso_from_ms(now_ms())})
    return {**pi, "pi_id": pi_id}


def pi_auth_context(
    pi_id: str,
    x_pi_id: str | None,
    x_device_token: str | None,
) -> dict[str, Any]:
    if x_pi_id and x_pi_id != pi_id:
        raise HTTPException(status_code=401, detail="Pi header does not match route.")
    return authenticate_pi_request(pi_id, x_device_token or "")


def create_kiosk_token(pi: dict[str, Any]) -> dict[str, Any]:
    timestamp = int(time.time())
    expires_at = timestamp + KIOSK_SESSION_TTL_SECONDS
    pi_id = str(pi.get("pi_id") or "")
    home_id = str(pi.get("home_id") or "")
    session_id = f"kiosk_{int(time.time() * 1000)}_{secrets.token_hex(4)}"
    payload = {
        "iss": "kahrabaiq-api",
        "aud": "kahrabaiq-kiosk",
        "scope": "kiosk",
        "session_id": session_id,
        "pi_id": pi_id,
        "home_id": home_id,
        "iat": timestamp,
        "exp": expires_at,
    }
    token = jwt.encode(payload, KIOSK_SESSION_SECRET, algorithm="HS256")
    safe_set(
        f"/kiosk_sessions/{session_id}",
        {
            "session_id": session_id,
            "pi_id": pi_id,
            "home_id": home_id,
            "scope": "kiosk",
            "expires_at_ms": expires_at * 1000,
            "created_at_ms": timestamp * 1000,
            "created_at_iso": iso_from_ms(timestamp * 1000),
            "active": True,
        },
    )
    return {"token": token, "session_id": session_id, "expires_at_ms": expires_at * 1000}


def require_kiosk_session(authorization: str | None = Header(default=None)) -> AuthContext:
    token = bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing kiosk session token.")
    try:
        claims = jwt.decode(
            token,
            KIOSK_SESSION_SECRET,
            algorithms=["HS256"],
            audience="kahrabaiq-kiosk",
            issuer="kahrabaiq-api",
        )
    except Exception as error:
        raise HTTPException(status_code=401, detail="Invalid kiosk session token.") from error
    if claims.get("scope") != "kiosk":
        raise HTTPException(status_code=403, detail="Invalid kiosk token scope.")
    session_id = str(claims.get("session_id") or "")
    session = as_dict(safe_get(f"/kiosk_sessions/{session_id}", {}))
    if session.get("active") is not True:
        raise HTTPException(status_code=401, detail="Kiosk session is not active.")
    if as_number(session.get("expires_at_ms")) < now_ms():
        raise HTTPException(status_code=401, detail="Kiosk session expired.")
    pi_id = str(claims.get("pi_id") or "")
    home_id = str(claims.get("home_id") or "")
    return AuthContext(
        actor_type="kiosk",
        actor_id=session_id,
        actor_role="kiosk",
        permissions={"can_view": True, "can_create_kiosk_commands": True},
        uid=None,
        email=None,
        claims={"pi_id": pi_id, "home_id": home_id, **claims},
    )


def kiosk_pi_and_home(actor: AuthContext) -> tuple[str, str]:
    claims = actor.claims or {}
    pi_id = str(claims.get("pi_id") or "")
    home_id = str(claims.get("home_id") or "")
    if not pi_id:
        raise HTTPException(status_code=403, detail="Kiosk token is missing Pi scope.")
    return pi_id, home_id


@app.post("/api/pi/kiosk-session")
def create_pi_kiosk_session(
    x_pi_id: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
) -> dict[str, Any]:
    pi = authenticate_pi_request(x_pi_id or "", x_device_token or "")
    session = create_kiosk_token(pi)
    return {
        "success": True,
        "pi_id": pi["pi_id"],
        "home_id": pi.get("home_id"),
        "paired": bool(pi.get("home_id")) and pi.get("status") == "paired",
        "kiosk_token": session["token"],
        "session_id": session["session_id"],
        "expires_at_ms": session["expires_at_ms"],
    }


@app.post("/api/pairing/pi-token")
def create_pi_pairing_token(
    request: PiPairingTokenRequest,
    x_pi_id: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
) -> dict[str, Any]:
    pi = authenticate_pi_request(x_pi_id or "", x_device_token or "")
    pi_id = str(pi["pi_id"])
    timestamp_ms = now_ms()
    raw_token = secrets.token_urlsafe(24)
    token_id = f"pair_{timestamp_ms}_{secrets.token_hex(3)}"
    safe_set(
        f"/pi_pairing_tokens/{token_id}",
        {
            "token_id": token_id,
            "pi_id": pi_id,
            "token_hash": hash_secret(raw_token),
            "expires_at_ms": timestamp_ms + PAIRING_TOKEN_TTL_MS,
            "created_at_ms": timestamp_ms,
            "created_at_iso": iso_from_ms(timestamp_ms),
            "used": False,
        },
    )
    safe_update(
        f"/pis/{pi_id}",
        {
            "display_name": request.display_name or pi.get("display_name") or pi_id,
            "dashboard_version": request.dashboard_version,
            "firmware_version": request.firmware_version,
            "latest_pairing_token_id": token_id,
            "status": pi.get("status") or "unpaired",
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": iso_from_ms(timestamp_ms),
        },
    )
    return {
        "success": True,
        "pi_id": pi_id,
        "token_id": token_id,
        "token": raw_token,
        "expires_at_ms": timestamp_ms + PAIRING_TOKEN_TTL_MS,
        "qr_payload": f"kahrabaiq://pair?pi_id={pi_id}&token={raw_token}",
    }


@app.get("/api/pairing/pi-status/{pi_id}")
def get_pi_pairing_status(pi_id: str) -> dict[str, Any]:
    pi = as_dict(safe_get(f"/pis/{pi_id}", {}))
    if not pi:
        raise HTTPException(status_code=404, detail="Pi does not exist.")
    return {"success": True, "pi": {"pi_id": pi_id, **pi}}


@app.post("/api/pi/{pi_id}/heartbeat")
def pi_heartbeat(
    pi_id: str,
    request: PiHeartbeatRequest,
    x_pi_id: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
) -> dict[str, Any]:
    pi = pi_auth_context(pi_id, x_pi_id, x_device_token)
    timestamp_ms = now_ms()
    updates = {
        "status": pi.get("status") or "unpaired",
        "online_status": request.status,
        "agent_version": request.agent_version,
        "local_ip": request.local_ip,
        "wifi_ssid": request.wifi_ssid,
        "esp32": request.esp32 or {},
        "metrics": request.metrics or {},
        "last_heartbeat_at_ms": timestamp_ms,
        "last_heartbeat_at_iso": iso_from_ms(timestamp_ms),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_update(f"/pis/{pi_id}", updates)
    return {"success": True, "pi_id": pi_id, "home_id": pi.get("home_id"), "heartbeat": updates}


@app.post("/api/pi/{pi_id}/sensor-state")
def pi_sensor_state(
    pi_id: str,
    request: PiSensorStateRequest,
    x_pi_id: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
) -> dict[str, Any]:
    pi = pi_auth_context(pi_id, x_pi_id, x_device_token)
    home_id = request.home_id or str(pi.get("home_id") or "")
    if not home_id:
        raise HTTPException(status_code=409, detail="Pi is not paired to a home.")
    if pi.get("home_id") and home_id != pi.get("home_id"):
        raise HTTPException(status_code=403, detail="Pi cannot write to this home.")
    timestamp_ms = request.updated_at_ms or now_ms()
    latest = {
        "home_id": home_id,
        "pi_id": pi_id,
        "dashboard": request.dashboard,
        "room": request.room,
        "devices": request.devices,
        "energy": request.energy,
        "commands": request.commands,
        "alerts": request.alerts,
        "notifications": request.notifications,
        "occupancy": request.occupancy,
        "safety": request.safety,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_set(f"/homes/{home_id}/latest_state", latest)
    safe_set(f"/homes/{home_id}/dashboard/latest", latest)
    if request.devices:
        for device_id, device in request.devices.items():
            if isinstance(device, dict):
                safe_update(f"/homes/{home_id}/devices/{device_id}", device)
    if request.alerts:
        active_alerts = {
            str(alert.get("id") or alert.get("alert_id") or f"alert_{index}"): alert
            for index, alert in enumerate(request.alerts)
            if isinstance(alert, dict)
        }
        safe_set(f"/homes/{home_id}/alerts/active", active_alerts)
    if request.notifications:
        for index, notification in enumerate(request.notifications):
            if not isinstance(notification, dict):
                continue
            notification_id = str(
                notification.get("notification_id")
                or notification.get("id")
                or f"notification_{index}"
            )
            safe_update(
                f"/homes/{home_id}/notifications/{notification_id}",
                notification,
            )
    safe_update(
        f"/pis/{pi_id}",
        {"last_state_sync_at_ms": timestamp_ms, "last_state_sync_at_iso": iso_from_ms(timestamp_ms)},
    )
    return {"success": True, "home_id": home_id, "pi_id": pi_id, "updated_at_ms": timestamp_ms}


@app.post("/api/pi/{pi_id}/esp32/link")
def pi_esp32_link(
    pi_id: str,
    request: PiEsp32LinkRequest,
    x_pi_id: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
) -> dict[str, Any]:
    pi = pi_auth_context(pi_id, x_pi_id, x_device_token)
    home_id = str(pi.get("home_id") or "")
    if not home_id:
        raise HTTPException(status_code=409, detail="Pi is not paired to a home.")
    timestamp_ms = now_ms()
    record = {
        "device_id": request.device_id,
        "pi_id": pi_id,
        "home_id": home_id,
        "ip": request.ip,
        "base_url": request.base_url,
        "status": request.status,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_set(f"/homes/{home_id}/devices/{request.device_id}/link", record)
    safe_set(f"/pis/{pi_id}/esp32/{request.device_id}", record)
    return {"success": True, "esp32": record}


@app.get("/api/pi/{pi_id}/commands")
def pi_commands(
    pi_id: str,
    x_pi_id: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
) -> dict[str, Any]:
    pi_auth_context(pi_id, x_pi_id, x_device_token)
    commands = []
    for item in object_to_list(safe_get(f"/pi_commands/{pi_id}", {})):
        if item.get("status") != "pending":
            continue
        if as_number(item.get("expires_at_ms")) and as_number(item.get("expires_at_ms")) < now_ms():
            safe_update(f"/pi_commands/{pi_id}/{item['id']}", {"status": "expired", "updated_at_ms": now_ms(), "updated_at_iso": iso_from_ms(now_ms())})
            continue
        commands.append(item)
    return {"success": True, "pi_id": pi_id, "commands": commands}


@app.post("/api/pi/{pi_id}/commands/{command_id}/complete")
def pi_command_complete(
    pi_id: str,
    command_id: str,
    payload: dict[str, Any],
    x_pi_id: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
) -> dict[str, Any]:
    pi_auth_context(pi_id, x_pi_id, x_device_token)
    command = as_dict(safe_get(f"/pi_commands/{pi_id}/{command_id}", {}))
    if not command:
        raise HTTPException(status_code=404, detail="Command does not exist.")
    timestamp_ms = now_ms()
    success = payload.get("success") is not False
    update = {
        "status": "completed" if success else "failed",
        "result": payload,
        "completed_at_ms": timestamp_ms,
        "completed_at_iso": iso_from_ms(timestamp_ms),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_update(f"/pi_commands/{pi_id}/{command_id}", update)
    return {"success": True, "command": {**command, **update}}


@app.get("/api/pi/{pi_id}/remote-commands")
def pi_remote_commands(
    pi_id: str,
    limit: int = Query(25, ge=1, le=100),
    x_pi_id: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
) -> dict[str, Any]:
    pi = pi_auth_context(pi_id, x_pi_id, x_device_token)
    home_id = str(pi.get("home_id") or "")
    if not home_id:
        raise HTTPException(status_code=409, detail="Pi is not paired to a home.")
    try:
        commands = [
            command
            for command in query_recent_remote_commands(home_id, limit=limit)
            if str(command.get("status") or "") == "pending"
        ]
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Remote command queue read failed: {error}") from error
    return {"success": True, "pi_id": pi_id, "home_id": home_id, "commands": commands}


@app.post("/api/pi/{pi_id}/remote-commands/{command_id}/claim")
def pi_remote_command_claim(
    pi_id: str,
    command_id: str,
    x_pi_id: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
) -> dict[str, Any]:
    pi = pi_auth_context(pi_id, x_pi_id, x_device_token)
    home_id = str(pi.get("home_id") or "")
    if not home_id:
        raise HTTPException(status_code=409, detail="Pi is not paired to a home.")
    command = find_remote_command(home_id, command_id)
    if not command:
        raise HTTPException(status_code=404, detail="Remote command not found.")
    if str(command.get("status") or "") != "pending":
        raise HTTPException(status_code=409, detail="Remote command is no longer pending.")
    timestamp_ms = now_ms()
    try:
        updated = update_remote_command(
            home_id,
            command_id,
            {
                "status": "processing",
                "claimedBy": pi_id,
                "claimed_by": pi_id,
                "claimedAtMs": timestamp_ms,
                "claimed_at_ms": timestamp_ms,
                "claimedAt": iso_from_ms(timestamp_ms),
                "claimed_at_iso": iso_from_ms(timestamp_ms),
            },
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Remote command claim failed: {error}") from error
    return {"success": True, "home_id": home_id, "pi_id": pi_id, "command": updated}


@app.post("/api/pi/{pi_id}/remote-commands/{command_id}/complete")
def pi_remote_command_complete(
    pi_id: str,
    command_id: str,
    payload: dict[str, Any],
    x_pi_id: str | None = Header(default=None),
    x_device_token: str | None = Header(default=None),
) -> dict[str, Any]:
    pi = pi_auth_context(pi_id, x_pi_id, x_device_token)
    home_id = str(pi.get("home_id") or "")
    if not home_id:
        raise HTTPException(status_code=409, detail="Pi is not paired to a home.")
    result = as_dict(payload.get("result"))
    success = payload.get("success")
    if success is None:
        success = result.get("success") is not False
    timestamp_ms = now_ms()
    updates = {
        "status": "confirmed" if success else "failed",
        "result": {
            **result,
            "success": bool(success),
        },
        "message": payload.get("message") or result.get("message") or result.get("user_message"),
        "executedAtMs": timestamp_ms,
        "executed_at_ms": timestamp_ms,
        "executedAt": iso_from_ms(timestamp_ms),
        "executed_at_iso": iso_from_ms(timestamp_ms),
        "completedBy": pi_id,
        "completed_by": pi_id,
    }
    try:
        updated = update_remote_command(home_id, command_id, updates)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Remote command result write failed: {error}") from error
    if not updated:
        raise HTTPException(status_code=404, detail="Remote command not found.")
    return {"success": True, "home_id": home_id, "pi_id": pi_id, "command": updated}


@app.post("/api/pairing/claim-pi")
def claim_pi(request: PiClaimRequest, actor: AuthContext = Depends(require_authenticated_user)) -> dict[str, Any]:
    pi_id = request.pi_id.strip()
    pi = as_dict(safe_get(f"/pis/{pi_id}", {}))
    if not pi:
        raise HTTPException(status_code=404, detail="Pi does not exist.")
    if pi.get("status") == "paired" and pi.get("home_id"):
        raise HTTPException(status_code=409, detail="This Pi is already paired.")
    active_token_id = str(pi.get("latest_pairing_token_id") or "")
    token_record = as_dict(safe_get(f"/pi_pairing_tokens/{active_token_id}", {}))
    if not token_record or token_record.get("pi_id") != pi_id:
        raise HTTPException(status_code=404, detail="Pairing token does not exist.")
    if token_record.get("used") is True or as_number(token_record.get("expires_at_ms")) < now_ms():
        raise HTTPException(status_code=409, detail="Pairing token expired. Refresh the QR code on the Pi.")
    if not secret_matches(request.token, str(token_record.get("token_hash") or "")):
        raise HTTPException(status_code=401, detail="Invalid pairing token.")
    profile = as_dict(safe_get(f"/users/{actor.uid}", {}))
    display_name = str(profile.get("display_name") or actor.email or actor.uid)
    home_id = create_home_for_pi(pi_id, str(actor.uid), str(actor.email or ""), display_name, request.home_name)
    timestamp_ms = now_ms()
    safe_update(
        f"/pi_pairing_tokens/{active_token_id}",
        {"used": True, "used_by_uid": actor.uid, "used_at_ms": timestamp_ms, "used_at_iso": iso_from_ms(timestamp_ms)},
    )
    return {"success": True, "home_id": home_id, "pi_id": pi_id, "role": "home_admin"}


@app.post("/api/home/{home_id}/invites")
def create_home_invite(
    home_id: str,
    request: HomeInviteCreateRequest,
    actor: AuthContext = Depends(require_home_permission("can_generate_invites")),
) -> dict[str, Any]:
    role = validate_role(request.role)
    if role == "home_admin":
        raise HTTPException(status_code=400, detail="Invite role cannot be home_admin.")
    if home_member_count(home_id, roles={"member"}) >= HOME_MEMBER_LIMIT:
        raise HTTPException(status_code=409, detail=f"This home already has the maximum {HOME_MEMBER_LIMIT} members.")
    timestamp_ms = now_ms()
    raw_token = secrets.token_urlsafe(24)
    invite_id = f"invite_{timestamp_ms}_{secrets.token_hex(3)}"
    safe_set(
        f"/home_invites/{invite_id}",
        {
            "invite_id": invite_id,
            "home_id": home_id,
            "role": role,
            "token_hash": hash_secret(raw_token),
            "created_by_uid": actor.uid,
            "expires_at_ms": timestamp_ms + HOME_INVITE_TTL_MS,
            "max_uses": request.max_uses,
            "used_count": 0,
            "active": True,
            "created_at_ms": timestamp_ms,
            "created_at_iso": iso_from_ms(timestamp_ms),
        },
    )
    return {
        "success": True,
        "home_id": home_id,
        "invite_id": invite_id,
        "token": raw_token,
        "expires_at_ms": timestamp_ms + HOME_INVITE_TTL_MS,
        "qr_payload": f"kahrabaiq://invite?invite_id={invite_id}&token={raw_token}",
    }


@app.get("/api/kiosk/session-state")
def kiosk_session_state(actor: AuthContext = Depends(require_kiosk_session)) -> dict[str, Any]:
    pi_id, home_id = kiosk_pi_and_home(actor)
    pi = as_dict(safe_get(f"/pis/{pi_id}", {}))
    pairing_payload = None
    expires_at_ms = None
    if not home_id:
        timestamp_ms = now_ms()
        raw_token = secrets.token_urlsafe(24)
        token_id = f"pair_{timestamp_ms}_{secrets.token_hex(3)}"
        safe_set(
            f"/pi_pairing_tokens/{token_id}",
            {
                "token_id": token_id,
                "pi_id": pi_id,
                "token_hash": hash_secret(raw_token),
                "expires_at_ms": timestamp_ms + PAIRING_TOKEN_TTL_MS,
                "created_at_ms": timestamp_ms,
                "created_at_iso": iso_from_ms(timestamp_ms),
                "used": False,
            },
        )
        safe_update(f"/pis/{pi_id}", {"latest_pairing_token_id": token_id, "updated_at_ms": timestamp_ms, "updated_at_iso": iso_from_ms(timestamp_ms)})
        expires_at_ms = timestamp_ms + PAIRING_TOKEN_TTL_MS
        pairing_payload = f"kahrabaiq://pair?pi_id={pi_id}&token={raw_token}"
    return {
        "success": True,
        "pi": {"pi_id": pi_id, **pi},
        "pi_id": pi_id,
        "home_id": home_id or None,
        "paired": bool(home_id),
        "pairing_payload": pairing_payload,
        "pairing_expires_at_ms": expires_at_ms,
    }


@app.get("/api/kiosk/dashboard")
def kiosk_dashboard(actor: AuthContext = Depends(require_kiosk_session)) -> dict[str, Any]:
    pi_id, home_id = kiosk_pi_and_home(actor)
    if not home_id:
        return {"success": True, "pi_id": pi_id, "home_id": None, "paired": False, "dashboard": {}}
    latest = as_dict(safe_get(f"/homes/{home_id}/latest_state", {}))
    return {"success": True, "pi_id": pi_id, "home_id": home_id, "paired": True, "dashboard": latest}


@app.post("/api/kiosk/commands")
def kiosk_create_command(
    request: KioskCommandCreateRequest,
    actor: AuthContext = Depends(require_kiosk_session),
) -> dict[str, Any]:
    pi_id, home_id = kiosk_pi_and_home(actor)
    command_name = request.command.strip().lower()
    if command_name not in KIOSK_ALLOWED_COMMANDS:
        raise HTTPException(status_code=400, detail="Unsupported kiosk command.")
    timestamp_ms = now_ms()
    command_id = f"kcmd_{timestamp_ms}_{secrets.token_hex(4)}"
    command = {
        "command_id": command_id,
        "pi_id": pi_id,
        "home_id": home_id,
        "command": command_name,
        "payload": request.payload,
        "status": "pending",
        "created_by": actor.actor_id,
        "created_at_ms": timestamp_ms,
        "created_at_iso": iso_from_ms(timestamp_ms),
        "expires_at_ms": timestamp_ms + (KIOSK_COMMAND_TTL_SECONDS * 1000),
    }
    safe_set(f"/pi_commands/{pi_id}/{command_id}", command)
    return {"success": True, "command": command}


@app.post("/api/home-invites/claim")
def claim_home_invite(
    request: HomeInviteClaimRequest,
    actor: AuthContext = Depends(require_authenticated_user),
) -> dict[str, Any]:
    invite = as_dict(safe_get(f"/home_invites/{request.invite_id}", {}))
    if not invite or invite.get("active") is not True:
        raise HTTPException(status_code=404, detail="Invite does not exist.")
    if as_number(invite.get("expires_at_ms")) < now_ms():
        raise HTTPException(status_code=409, detail="Invite expired.")
    if as_number(invite.get("used_count")) >= as_number(invite.get("max_uses"), 1):
        raise HTTPException(status_code=409, detail="Invite has already been used.")
    if not secret_matches(request.token, str(invite.get("token_hash") or "")):
        raise HTTPException(status_code=401, detail="Invalid invite token.")
    home_id = str(invite.get("home_id") or "")
    if home_member_count(home_id, roles={"member"}) >= HOME_MEMBER_LIMIT:
        raise HTTPException(status_code=409, detail=f"This home already has the maximum {HOME_MEMBER_LIMIT} members.")
    existing = as_dict(safe_get(f"/homes/{home_id}/members/{actor.uid}", {}))
    if existing:
        return {"success": True, "home_id": home_id, "role": validate_role(str(existing.get("role", "viewer"))), "already_member": True}
    profile = as_dict(safe_get(f"/users/{actor.uid}", {}))
    display_name = str(profile.get("display_name") or actor.email or actor.uid)
    role = validate_role(str(invite.get("role", "member")))
    member = add_user_to_home(str(actor.uid), str(actor.email or ""), display_name, home_id, role)
    used_count = int(as_number(invite.get("used_count"))) + 1
    safe_update(
        f"/home_invites/{request.invite_id}",
        {"used_count": used_count, "active": used_count < int(as_number(invite.get("max_uses"), 1)), "last_used_at_ms": now_ms(), "last_used_at_iso": iso_from_ms(now_ms())},
    )
    return {"success": True, "home_id": home_id, "role": member["role"], "already_member": False}


def require_platform_admin(actor: AuthContext = Depends(require_authenticated_user)) -> AuthContext:
    if actor.actor_role != "platform_admin":
        raise HTTPException(status_code=403, detail="Platform admin role is required.")
    return actor


@app.get("/api/admin/users")
def admin_users(actor: AuthContext = Depends(require_platform_admin)) -> dict[str, Any]:
    users = object_to_list(safe_get("/users", {}))
    return {"success": True, "count": len(users), "users": users}


@app.get("/api/admin/homes")
def admin_homes(actor: AuthContext = Depends(require_platform_admin)) -> dict[str, Any]:
    homes = object_to_list(safe_get("/homes", {}))
    return {"success": True, "count": len(homes), "homes": homes}


@app.get("/api/admin/pis")
def admin_pis(actor: AuthContext = Depends(require_platform_admin)) -> dict[str, Any]:
    pis = object_to_list(safe_get("/pis", {}))
    for pi in pis:
        pi.pop("token_hash", None)
    return {"success": True, "count": len(pis), "pis": pis}


@app.get("/api/admin/pairings")
def admin_pairings(actor: AuthContext = Depends(require_platform_admin)) -> dict[str, Any]:
    tokens = object_to_list(safe_get("/pi_pairing_tokens", {}))
    for token in tokens:
        token.pop("token_hash", None)
    return {"success": True, "count": len(tokens), "pairings": tokens}
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
        if normalized in {"true", "1", "on", "yes", "detected", "motion", "smoke", "gas"}:
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
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
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


def ensure_device_safety(home_id: str, device_id: str) -> dict[str, Any]:
    path = f"/homes/{home_id}/devices/{device_id}/safety"
    current = as_dict(safe_get(path, {}))
    fallback = DEFAULT_DEVICE_SAFETY_BY_DEVICE.get(device_id, DEFAULT_UNKNOWN_DEVICE_SAFETY)
    if not current:
        safe_set(path, fallback)
        return dict(fallback)
    merged = {**fallback, **current}
    if merged != current:
        safe_update(path, merged)
    return merged


def safety_event(
    home_id: str,
    event_type: str,
    message: str,
    severity: str = "critical",
    actions_taken: list[str] | None = None,
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    event_id = f"safety_{timestamp_ms}"
    event = {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
        "event_id": event_id,
        "type": event_type,
        "severity": severity,
        "message": message,
        "source": "mq2",
        "actions_taken": actions_taken or [],
        "created_at_ms": timestamp_ms,
        "created_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_set(f"/homes/{home_id}/safety/events/{event_id}", event)
    return event


def active_emergency_mode(home_id: str) -> dict[str, Any]:
    emergency = as_dict(safe_get(f"/homes/{home_id}/safety/emergency_mode", {}))
    return emergency if emergency.get("active") is True else {}


def latest_smoke_is_clear_for(home_id: str, clear_delay_ms: int = SMOKE_CLEAR_DELAY_MS) -> bool:
    esp32 = as_dict(safe_get(f"/homes/{home_id}/devices/esp32_01", {}))
    sensors = as_dict(esp32.get("sensors"))
    status = as_dict(esp32.get("status"))
    smoke_state = as_dict(safe_get(f"/homes/{home_id}/safety/smoke_state", {}))
    smoke = normalize_bool(sensors.get("smoke"))
    smoke_text = str(sensors.get("smoke_text", "")).lower()
    if smoke is True or "detect" in smoke_text or "smoke" in smoke_text or "gas" in smoke_text:
        return False
    clear_started_at_ms = as_number(smoke_state.get("last_clear_at_ms"))
    if clear_started_at_ms <= 0:
        clear_started_at_ms = as_number(
            first_present(
                sensors.get("timestamp_ms"),
                status.get("last_seen_ms"),
                status.get("lastSeenMs"),
            )
        )
    latest_sensor_timestamp_ms = as_number(
        first_present(
            sensors.get("timestamp_ms"),
            status.get("last_seen_ms"),
            status.get("lastSeenMs"),
        )
    )
    if clear_started_at_ms <= 0 or latest_sensor_timestamp_ms <= 0:
        return False
    if now_ms() - latest_sensor_timestamp_ms > 2 * 60 * 1000:
        return False
    return now_ms() - clear_started_at_ms >= clear_delay_ms


def resolve_smoke_emergency_if_clear(home_id: str) -> None:
    if not latest_smoke_is_clear_for(home_id):
        return
    timestamp_ms = now_ms()
    alert = as_dict(safe_get(f"/homes/{home_id}/alerts/active/{SMOKE_ALERT_ID}", {}))
    if alert:
        safe_set(
            f"/homes/{home_id}/alerts/history/alert_{timestamp_ms}_{SMOKE_ALERT_ID}",
            {
                **alert,
                "status": "resolved",
                "resolved_at_ms": timestamp_ms,
                "resolved_at_iso": iso_from_ms(timestamp_ms),
                "updated_at_ms": timestamp_ms,
                "updated_at_iso": iso_from_ms(timestamp_ms),
            },
        )
        safe_set(f"/homes/{home_id}/alerts/active/{SMOKE_ALERT_ID}", None)
    safe_update(
        f"/homes/{home_id}/safety/emergency_mode",
        {
            "active": False,
            "ended_at_ms": timestamp_ms,
            "ended_at_iso": iso_from_ms(timestamp_ms),
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": iso_from_ms(timestamp_ms),
        },
    )
    safe_update(
        f"/homes/{home_id}/safety/smoke_state",
        {
            "status": "clear",
            "consecutive_detections": 0,
            "last_clear_at_ms": timestamp_ms,
            "last_clear_at_iso": iso_from_ms(timestamp_ms),
            "notification_sent": False,
            "notification_sent_at_ms": None,
            "notification_sent_at_iso": None,
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": iso_from_ms(timestamp_ms),
        },
    )


def create_notification_record(home_id: str, title: str, body: str) -> dict[str, Any]:
    timestamp_ms = now_ms()
    notification_id = f"notif_{timestamp_ms}"
    notification = {
        "notification_id": notification_id,
        "type": "critical_alert",
        "alert_type": "smoke_detected",
        "severity": "critical",
        "title": title,
        "body": body,
        "home_id": home_id,
        "room_id": "room1",
        "read": False,
        "delivered": False,
        "created_at_ms": timestamp_ms,
        "created_at_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
    }
    safe_set(f"/homes/{home_id}/notifications/{notification_id}", notification)
    send_push_notifications(home_id, notification_id, title, body)
    return notification


def send_push_notifications(home_id: str, notification_id: str, title: str, body: str) -> None:
    # Mobile push delivery is intentionally disabled until AWS SNS/Pinpoint is wired.
    return


def notification_sort_key(item: dict[str, Any]) -> int:
    return int(
        first_present(
            item.get("created_at_ms"),
            item.get("timestamp_ms"),
            item.get("updated_at_ms"),
            0,
        )
        or 0
    )


def default_settings_record(updated_by: str = "system_default") -> dict[str, Any]:
    timestamp_ms = now_ms()
    return {
        **DEFAULT_SETTINGS,
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
        "updated_by": updated_by,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }


def ensure_settings(home_id: str) -> dict[str, Any]:
    path = f"/homes/{home_id}/settings"
    current = as_dict(safe_get(path, {}))
    if not current:
        settings = default_settings_record()
        safe_set(path, settings)
        return settings

    merged = {**DEFAULT_SETTINGS, **current}
    if any(key not in current for key in DEFAULT_SETTINGS):
        safe_update(path, merged)
    return merged


def validate_hhmm(value: str) -> str:
    if not isinstance(value, str) or not HHMM_RE.match(value):
        raise HTTPException(status_code=400, detail=f"{value} must use HH:MM format.")
    return value


def validate_settings(settings: dict[str, Any]) -> None:
    if settings.get("currency") != "BHD":
        raise HTTPException(status_code=400, detail="currency currently only supports BHD.")
    if settings.get("temperature_unit") not in {"C", "F"}:
        raise HTTPException(status_code=400, detail="temperature_unit must be C or F.")
    if as_number(settings.get("cost_per_kwh"), -1) < 0:
        raise HTTPException(status_code=400, detail="cost_per_kwh must be >= 0.")

    comfort_min = as_number(settings.get("comfort_temperature_min"))
    comfort_max = as_number(settings.get("comfort_temperature_max"))
    high_threshold = as_number(settings.get("high_temperature_threshold"))
    humidity_min = as_number(settings.get("humidity_min"))
    humidity_max = as_number(settings.get("humidity_max"))

    if comfort_min >= comfort_max:
        raise HTTPException(
            status_code=400,
            detail="comfort_temperature_min must be less than comfort_temperature_max.",
        )
    if high_threshold <= comfort_max:
        raise HTTPException(
            status_code=400,
            detail="high_temperature_threshold must be greater than comfort_temperature_max.",
        )
    if humidity_min >= humidity_max:
        raise HTTPException(status_code=400, detail="humidity_min must be less than humidity_max.")

    for field in [
        "light_waste_minutes",
        "motion_recent_seconds",
        "sound_recent_seconds",
        "occupancy_empty_minutes",
        "occupancy_history_interval_minutes",
        "device_offline_minutes",
        "chat_history_retention_days",
    ]:
        if as_number(settings.get(field), -1) <= 0:
            raise HTTPException(status_code=400, detail=f"{field} must be positive.")

    if as_number(settings.get("sound_activity_threshold"), -1) < 0:
        raise HTTPException(status_code=400, detail="sound_activity_threshold must be >= 0.")
    confidence_threshold = as_number(settings.get("occupancy_confidence_threshold"), -1)
    if confidence_threshold < 0 or confidence_threshold > 1:
        raise HTTPException(
            status_code=400,
            detail="occupancy_confidence_threshold must be between 0 and 1.",
        )

    for field in [
        "quiet_hours_enabled",
        "ai_recommendations_enabled",
        "auto_control_enabled",
        "notifications_enabled",
        "schedules_enabled",
    ]:
        if not isinstance(settings.get(field), bool):
            raise HTTPException(status_code=400, detail=f"{field} must be a boolean.")

    validate_hhmm(str(settings.get("quiet_hours_start", "")))
    validate_hhmm(str(settings.get("quiet_hours_end", "")))


def settings_summary(settings: dict[str, Any]) -> dict[str, Any]:
    unit = str(settings.get("temperature_unit", "C"))
    suffix = "°F" if unit == "F" else "°C"
    return {
        "currency": settings.get("currency", "BHD"),
        "cost_per_kwh": settings.get("cost_per_kwh", DEFAULT_SETTINGS["cost_per_kwh"]),
        "comfort_range": (
            f"{settings.get('comfort_temperature_min')}-"
            f"{settings.get('comfort_temperature_max')}{suffix}"
        ),
        "high_temperature_threshold": settings.get("high_temperature_threshold"),
        "quiet_hours_enabled": settings.get("quiet_hours_enabled"),
        "occupancy_empty_minutes": settings.get("occupancy_empty_minutes"),
        "sound_activity_threshold": settings.get("sound_activity_threshold"),
    }


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
    settings = ensure_settings(home_id)
    if settings.get("auto_control_enabled") is False:
        raise HTTPException(status_code=403, detail="Automatic control is disabled in settings.")

    automation = ensure_device_automation(home_id, device_id)
    if normalize_bool(automation.get("auto_allowed")) is not True:
        raise HTTPException(status_code=403, detail="Auto control is not allowed for this device.")

    auto_actions = automation.get("auto_actions")
    allowed_actions = auto_actions if isinstance(auto_actions, list) else []
    if command not in allowed_actions:
        raise HTTPException(status_code=403, detail="This auto action is not allowed for this device.")

    if command not in SAFE_AUTO_ACTIONS.get(device_id, set()):
        raise HTTPException(status_code=403, detail="This auto action is blocked by safety rules.")

    if active_emergency_mode(home_id):
        raise HTTPException(status_code=403, detail="Normal automation is paused during emergency mode.")

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
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
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
            "last_auto_action_at_iso": iso_from_ms(timestamp_ms),
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
    control_method = str(raw.get("control_method") or ("tuya_cloud" if device_id.startswith("breaker_") else "")).lower()
    is_home_assistant_device = control_method == "home_assistant"

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
        raw.get("updated_at_ms"),
    )

    online = normalize_bool(status.get("online"))
    if is_home_assistant_device:
        online = normalize_bool(raw.get("local_online"))
        if online is None:
            online = normalize_bool(raw.get("online"))
    is_stale = not isinstance(last_seen_ms, (int, float)) or (
        now_ms() - int(last_seen_ms) > DEVICE_STALE_AFTER_MS
    )
    is_breaker = str(raw.get("type") or DEFAULT_DEVICE_TYPES.get(device_id, "")).lower() in {
        "smart_breaker",
        "breaker",
    } or device_id.startswith("breaker_")
    if online is None:
        online = not is_stale
    elif is_stale and not is_breaker and not is_home_assistant_device:
        online = False
    if is_home_assistant_device:
        is_stale = False

    command_in_progress = bool(normalize_bool(raw.get("command_in_progress")))
    pending_target_state = raw.get("pending_target_state")
    if pending_target_state not in {"on", "off"}:
        pending_target_state = None
    display_state = pending_target_state if command_in_progress and pending_target_state else state
    if not online and not is_home_assistant_device:
        display_state = "off"
    latest_command = as_dict(raw.get("last_command"))
    energy_supported = normalize_bool(raw.get("energy_supported"))
    if energy_supported is None:
        energy_supported = not is_home_assistant_device
    raw_power = first_present(
        raw.get("power_w"),
        metering.get("power_W"),
        metering.get("power"),
        raw.get("power_W"),
        raw.get("currentPower"),
        backend_energy.get("power_W"),
    )
    power_w = None if energy_supported is False or raw_power is None else as_number(raw_power)
    if not online and energy_supported is not False:
        power_w = 0.0

    return {
        "device_id": device_id,
        "name": raw.get("name") or DEFAULT_DEVICE_NAMES.get(device_id, device_id),
        "type": raw.get("type") or DEFAULT_DEVICE_TYPES.get(device_id, "unknown"),
        "branch": raw.get("branch"),
        "control_method": control_method or None,
        "ha_entity_id": raw.get("ha_entity_id"),
        "online": bool(online),
        "local_online": bool(normalize_bool(raw.get("local_online")) if raw.get("local_online") is not None else online),
        "cloud_online": bool(normalize_bool(raw.get("cloud_online")) if raw.get("cloud_online") is not None else not is_home_assistant_device),
        "stale": is_stale,
        "controllable": is_controllable_device(device_id, raw),
        "state": state,
        "display_state": display_state,
        "power_w": power_w,
        "energy_supported": bool(energy_supported),
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


def alert_dedupe_key(item: dict[str, Any]) -> str:
    alert_id = str(first_present(item.get("alert_id"), item.get("id"), item.get("alert_key"), "")).strip()
    alert_type = str(first_present(item.get("alert_type"), item.get("category"), item.get("type"), "")).lower()
    message = str(first_present(item.get("message"), item.get("body"), item.get("title"), "")).lower().strip()
    if alert_id == SMOKE_ALERT_ID or "smoke" in alert_type or "gas" in alert_type or "smoke" in message or "gas" in message:
        return SMOKE_ALERT_ID
    if alert_id:
        return alert_id
    return f"{alert_type}:{message}"


def dedupe_alerts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not is_meaningful_alert(item):
            continue
        key = alert_dedupe_key(item)
        existing = result.get(key)
        if not existing or (
            str(existing.get("message", "")).strip().lower() == "system alert"
            and str(item.get("message", "")).strip().lower() != "system alert"
        ):
            result[key] = item
    return sorted(
        result.values(),
        key=lambda item: int(first_present(item.get("created_at_ms"), item.get("timestamp_ms"), item.get("updated_at_ms"), 0) or 0),
        reverse=True,
    )


def is_meaningful_alert(item: dict[str, Any]) -> bool:
    alert_id = str(first_present(item.get("alert_id"), item.get("id"), item.get("alert_key"), "")).strip()
    alert_type = str(first_present(item.get("alert_type"), item.get("category"), item.get("type"), "")).lower().strip()
    message = str(first_present(item.get("message"), item.get("body"), item.get("title"), "")).lower().strip()
    if alert_id == SMOKE_ALERT_ID or "smoke" in alert_type or "gas" in alert_type or "smoke" in message or "gas" in message:
        return True
    if not message or message == "system alert":
        return alert_type not in {"", "sensorfailure", "sensor_failure", "unknown"}
    return True


def dedupe_action_suggestions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for item in items:
        key = (
            str(item.get("device_id", "")),
            str(item.get("suggested_command", item.get("command", ""))),
            str(item.get("reason", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def read_home_bundle(home_id: str) -> dict[str, Any]:
    home_path = f"/homes/{home_id}"
    home = as_dict(safe_get(home_path, {}))
    backend = as_dict(home.get("backend"))
    backend_dashboard = as_dict(backend.get("dashboard"))
    backend_energy = as_dict(backend.get("energy"))
    backend_ai = as_dict(backend.get("ai"))
    latest_state = as_dict(home.get("latest_state"))

    return {
        "home": home,
        "latest_state": latest_state,
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
        "occupancy_room1": as_dict(as_dict(home.get("occupancy")).get("room1")),
        "safety": as_dict(home.get("safety")),
    }


def build_room(bundle: dict[str, Any]) -> dict[str, Any]:
    latest_room = as_dict(bundle["latest_state"].get("room"))
    esp32 = as_dict(bundle["devices"].get("esp32_01"))
    sensors = as_dict(esp32.get("sensors"))
    status = as_dict(esp32.get("status"))
    dashboard_env = bundle["backend_dashboard_environment"]
    current_state = as_dict(bundle["backend"].get("current_state"))
    occupancy = bundle["occupancy_room1"]
    smoke_state = as_dict(as_dict(bundle["safety"]).get("smoke_state"))
    emergency_mode = as_dict(as_dict(bundle["safety"]).get("emergency_mode"))

    source = {
        **current_state,
        **dashboard_env,
        **sensors,
        **occupancy,
        **latest_room,
    }

    motion_bool = normalize_bool(first_present(source.get("motion"), source.get("occupied")))
    smoke_bool = normalize_bool(source.get("smoke"))
    safety_smoke_active = (
        smoke_state.get("status") in {"pending", "confirmed"}
        or emergency_mode.get("active") is True
        and "smoke" in str(emergency_mode.get("reason", "")).lower()
    )
    if safety_smoke_active:
        smoke_bool = True
    sensor_timestamp_ms = first_present(
        sensors.get("timestamp_ms"),
        latest_room.get("timestamp_ms"),
        latest_room.get("timestampMs"),
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
        "smoke_text": (
            "Detected"
            if safety_smoke_active
            else source.get("smoke_text")
            or ("Smoke/Gas" if smoke_bool else "Clear" if smoke_bool is False else "Unknown")
        ),
        "sound_level": first_present(
            source.get("sound_level"),
            source.get("sound_raw"),
            source.get("latest_sound_raw"),
        ),
        "occupancy": first_present(
            occupancy.get("state"),
            source.get("occupancy"),
            source.get("occupancy_state"),
            status.get("occupancy"),
            default="unknown",
        ),
        "occupancy_state": occupancy.get("state", "unknown"),
        "occupied": bool(occupancy.get("occupied")),
        "occupancy_confidence": occupancy.get("confidence"),
        "occupancy_reason": occupancy.get("reason"),
    }


def build_devices(bundle: dict[str, Any], home_id: str | None = None) -> dict[str, dict[str, Any]]:
    raw_devices = dict(bundle["devices"])
    for device_id, device in as_dict(bundle["latest_state"].get("devices")).items():
        if isinstance(device, dict):
            raw_devices[device_id] = {**as_dict(raw_devices.get(device_id)), **device}
    branches = bundle["backend_branches"]
    health_devices = as_dict(bundle["backend_device_health"].get("devices"))

    for device_id in ["esp32_01", "breaker_01", "breaker_02", *MATTER_DEVICE_IDS]:
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


def build_energy(
    bundle: dict[str, Any],
    devices: dict[str, dict[str, Any]],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dashboard_energy = bundle["backend_dashboard_energy"]
    current_total = bundle["backend_current_total"]
    latest = bundle["dashboard_latest"]
    latest_energy = as_dict(bundle["latest_state"].get("energy"))

    source = {**latest, **dashboard_energy, **current_total, **latest_energy}
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
    tariff = as_number(
        (settings or {}).get("cost_per_kwh"),
        as_number(first_present(source.get("tariff_BHD_per_kWh"), source.get("tariff")), 0.029),
    )
    today_kwh = source_energy if source_energy > 0 else device_energy_total
    calculated_cost = today_kwh * tariff

    return {
        "current_power_w": device_power_total if device_power_total > 0 else source_power,
        "today_kwh": today_kwh,
        "today_cost_bhd": calculated_cost if today_kwh > 0 else source_cost if source_cost > 0 else device_cost_total,
        "tariff_BHD_per_kWh": tariff,
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


def validate_days(days: Any) -> list[str]:
    if not isinstance(days, list) or not days:
        raise HTTPException(status_code=400, detail="days must be a non-empty list.")
    normalized = []
    for day in days:
        text = str(day).strip().title()[:3]
        if text not in VALID_DAYS:
            raise HTTPException(status_code=400, detail=f"Invalid day: {day}.")
        if text not in normalized:
            normalized.append(text)
    return normalized


def calculate_next_run(time_text: str, days: list[str], timezone: str = "Asia/Bahrain") -> tuple[int | None, str | None]:
    validate_hhmm(time_text)
    days = validate_days(days)
    tz = ZoneInfo(timezone)
    now = datetime.now(tz).replace(second=0, microsecond=0)
    hour, minute = [int(part) for part in time_text.split(":")]

    for offset in range(0, 8):
        candidate_date = now.date() + timedelta(days=offset)
        candidate = datetime(
            candidate_date.year,
            candidate_date.month,
            candidate_date.day,
            hour,
            minute,
            tzinfo=tz,
        )
        if candidate <= now:
            continue
        if PY_WEEKDAY_TO_DAY[candidate.weekday()] in days:
            timestamp_ms = int(candidate.timestamp() * 1000)
            return timestamp_ms, iso_from_ms(timestamp_ms)
    return None, None


def schedule_history(
    home_id: str,
    schedule_id: str,
    action: str,
    changed_by: str,
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> None:
    timestamp_ms = now_ms()
    history_id = f"schedule_{timestamp_ms}"
    changed_fields = []
    if previous is not None and current is not None:
        changed_fields = sorted(
            key for key in set(previous) | set(current) if previous.get(key) != current.get(key)
        )
    safe_set(
        f"/homes/{home_id}/schedules_history/{history_id}",
        {
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": iso_from_ms(timestamp_ms),
            "timezone": TIMEZONE,
            "history_id": history_id,
            "schedule_id": schedule_id,
            "action": action,
            "changed_by": changed_by,
            "changed_at_ms": timestamp_ms,
            "changed_at_iso": iso_from_ms(timestamp_ms),
            "previous_schedule": previous,
            "new_schedule": current,
            "changed_fields": changed_fields,
        },
    )


def validate_schedule_payload(home_id: str, payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = {**(existing or {}), **payload}
    name = str(merged.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Schedule name is required.")

    device_id = str(merged.get("device_id", "")).strip()
    device = as_dict(safe_get(f"/homes/{home_id}/devices/{device_id}", {}))
    if not device:
        raise HTTPException(status_code=404, detail="Device does not exist.")
    if not is_controllable_device(device_id, device):
        raise HTTPException(status_code=400, detail="Device is not controllable.")

    command = str(merged.get("command", "")).strip().lower()
    if command not in VALID_COMMANDS:
        raise HTTPException(status_code=400, detail="command must be turn_on or turn_off.")

    time_text = validate_hhmm(str(merged.get("time", "")))
    days = validate_days(merged.get("days"))
    enabled = bool(merged.get("enabled", True))
    timezone = str(merged.get("timezone") or "Asia/Bahrain")
    next_run_ms, next_run_iso = calculate_next_run(time_text, days, timezone) if enabled else (None, None)

    return {
        **merged,
        "name": name,
        "device_id": device_id,
        "device_name": device_message_name(device_id, device),
        "command": command,
        "target_state": command_to_target_state(command),
        "time": time_text,
        "days": days,
        "enabled": enabled,
        "timezone": timezone,
        "next_run_at_ms": next_run_ms,
        "next_run_at_iso": next_run_iso,
    }


def log_schedule_run(
    home_id: str,
    schedule: dict[str, Any],
    status: str,
    message: str,
    command_id: str | None = None,
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    log_id = f"schedule_log_{timestamp_ms}"
    log = {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
        "log_id": log_id,
        "schedule_id": schedule.get("schedule_id"),
        "home_id": home_id,
        "device_id": schedule.get("device_id"),
        "command": schedule.get("command"),
        "target_state": schedule.get("target_state"),
        "status": status,
        "command_id": command_id,
        "message": message,
        "created_at_ms": timestamp_ms,
        "created_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_set(f"/homes/{home_id}/schedule_logs/{log_id}", log)
    return log


def next_schedule_summary(home_id: str) -> dict[str, Any] | None:
    schedules = [
        item for item in object_to_list(safe_get(f"/homes/{home_id}/schedules", {}))
        if item.get("enabled") is True and item.get("deleted") is not True and isinstance(item.get("next_run_at_ms"), (int, float))
    ]
    if not schedules:
        return None
    schedules.sort(key=lambda item: item.get("next_run_at_ms"))
    schedule = schedules[0]
    return {
        "schedule_id": schedule.get("schedule_id") or schedule.get("id"),
        "name": schedule.get("name"),
        "device_id": schedule.get("device_id"),
        "device_name": schedule.get("device_name"),
        "command": schedule.get("command"),
        "time": schedule.get("time"),
        "next_run_at_ms": schedule.get("next_run_at_ms"),
        "next_run_at_iso": schedule.get("next_run_at_iso"),
        "message": f"Next schedule: {schedule.get('name')} at {schedule.get('time')}",
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
        "timezone": TIMEZONE,
    }


@app.post("/api/home/{home_id}/cloud/commands", dependencies=[Depends(require_home_permission("can_control_devices"))])
def create_cloud_remote_command(home_id: str, request: CloudRemoteCommandRequest) -> dict[str, Any]:
    command = request.command.strip().lower()
    device_id = request.device_id.strip()
    if command not in VALID_COMMANDS:
        raise HTTPException(status_code=400, detail="Command must be turn_on or turn_off.")
    if device_id not in CONTROLLABLE_DEVICES:
        raise HTTPException(status_code=400, detail="Unsupported device_id.")

    try:
        command_record = create_remote_command(
            home_id,
            device_id,
            command,
            requested_by=request.requested_by,
            source=request.source,
            emergency=request.emergency,
            alert_id=request.alert_id,
            reason=request.reason,
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"AWS command queue write failed: {error}") from error

    return {
        "success": True,
        "status": "pending",
        "message": "Command queued for the Raspberry Pi.",
        "command_id": command_record["command_id"],
        "device_id": device_id,
        "command": command,
        "target_state": command_record["target_state"],
        "command_record": command_record,
    }


@app.get("/api/home/{home_id}/cloud/commands", dependencies=[Depends(require_home_permission("can_view"))])
def get_cloud_remote_commands(home_id: str, limit: int = Query(25, ge=1, le=100)) -> dict[str, Any]:
    try:
        commands = query_recent_remote_commands(home_id, limit)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"AWS command read failed: {error}") from error
    return {
        "success": True,
        "home_id": home_id,
        "count": len(commands),
        "commands": commands,
    }


@app.get("/api/home/{home_id}/cloud/commands/{command_id}", dependencies=[Depends(require_home_permission("can_view"))])
def get_cloud_remote_command(home_id: str, command_id: str) -> dict[str, Any]:
    try:
        command = find_remote_command(home_id, command_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"AWS command read failed: {error}") from error
    if not command:
        raise HTTPException(status_code=404, detail="Command not found.")
    return {
        "success": True,
        "home_id": home_id,
        "command": command,
    }


@app.get("/api/home/{home_id}/iot/live-config", dependencies=[Depends(require_home_permission("can_view"))])
def get_iot_live_config(home_id: str) -> dict[str, Any]:
    try:
        config = create_iot_websocket_config(home_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"AWS IoT live config failed: {error}") from error
    return {
        "success": True,
        "home_id": home_id,
        "config": config,
    }


@app.get("/api/home/{home_id}/state/current", dependencies=[Depends(require_home_permission("can_view"))])
def get_current_state(home_id: str) -> dict[str, Any]:
    latest = as_dict(safe_get(f"/homes/{home_id}/latest_state", {}))
    if not latest:
        raise HTTPException(status_code=404, detail="No current state has been reported by the Pi yet.")
    return {
        "success": True,
        "home_id": home_id,
        "state": latest,
        "updated_at_ms": latest.get("updated_at_ms"),
        "updated_at_iso": latest.get("updated_at_iso"),
    }


@app.get("/api/home/{home_id}/dashboard", dependencies=[Depends(require_home_permission("can_view"))])
def get_dashboard(home_id: str) -> dict[str, Any]:
    resolve_smoke_emergency_if_clear(home_id)
    bundle = read_home_bundle(home_id)
    devices = build_devices(bundle, home_id)
    timestamp_ms = now_ms()
    control = ensure_control(home_id)
    settings = ensure_settings(home_id)
    control_mode = str(control.get("mode", "assist")).lower()

    alerts = dedupe_alerts(active_only(
        object_to_list(bundle["alerts_active"])
        + object_to_list(bundle["backend_active_alerts"])
        + [
            item
            for item in bundle["latest_state"].get("alerts", [])
            if isinstance(item, dict)
        ]
    ))
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
        "occupancy": bundle["occupancy_room1"],
        "energy": build_energy(bundle, devices, settings),
        "devices": devices,
        "alerts": alerts,
        "critical_alerts": [
            item
            for item in alerts
            if str(first_present(item.get("severity"), item.get("level"))).lower() == "critical"
            or str(item.get("category")).lower() == "safety"
        ],
        "safety": {
            "emergency_mode": as_dict(as_dict(bundle["safety"]).get("emergency_mode")),
            "smoke_state": as_dict(as_dict(bundle["safety"]).get("smoke_state")),
        },
        "recommendations": recommendations,
        "action_suggestions": dedupe_action_suggestions(
            active_only(
                object_to_list(safe_get(f"/homes/{home_id}/action_suggestions/active", {}))
            )
        ),
        "automation_logs": object_to_list(
            safe_get(f"/homes/{home_id}/automation_logs", {})
        )[-10:],
        "ai": build_ai(bundle),
        "ai_daily_summary": as_dict(as_dict(bundle["backend_ai"]).get("daily_summary")),
        "system_health": bundle["system_health"] or bundle["backend_device_health"],
        "settings_summary": settings_summary(settings),
        "next_schedule": next_schedule_summary(home_id),
        "timezone": TIMEZONE,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }


@app.get("/api/home/{home_id}/settings", dependencies=[Depends(require_home_permission("can_view"))])
def get_settings(home_id: str) -> dict[str, Any]:
    settings = ensure_settings(home_id)
    return {"home_id": home_id, "settings": settings, "options": SETTINGS_OPTIONS}


@app.put("/api/home/{home_id}/settings", dependencies=[Depends(require_home_permission("can_change_settings"))])
def update_settings(home_id: str, request: SettingsUpdateRequest) -> dict[str, Any]:
    previous = ensure_settings(home_id)
    updates = request.dict(exclude_unset=True)
    updated_by = str(updates.pop("updated_by", "api"))
    allowed = set(DEFAULT_SETTINGS.keys())
    unknown = sorted(key for key in updates if key not in allowed)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unsupported settings fields: {', '.join(unknown)}")

    merged = {**previous, **updates}
    validate_settings(merged)

    timestamp_ms = now_ms()
    merged.update(
        {
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": iso_from_ms(timestamp_ms),
            "timezone": TIMEZONE,
            "updated_by": updated_by,
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": iso_from_ms(timestamp_ms),
        }
    )
    changed_fields = sorted(key for key in updates if previous.get(key) != merged.get(key))
    history_id = f"settings_{timestamp_ms}"
    safe_update(f"/homes/{home_id}/settings", merged)
    safe_set(
        f"/homes/{home_id}/settings/history/{history_id}",
        {
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": iso_from_ms(timestamp_ms),
            "timezone": TIMEZONE,
            "history_id": history_id,
            "changed_by": updated_by,
            "changed_at_ms": timestamp_ms,
            "changed_at_iso": iso_from_ms(timestamp_ms),
            "previous_settings": previous,
            "new_settings": merged,
            "changed_fields": changed_fields,
        },
    )
    return {"home_id": home_id, "settings": merged, "options": SETTINGS_OPTIONS}


@app.get("/api/home/{home_id}/control", dependencies=[Depends(require_home_permission("can_view"))])
def get_control(home_id: str) -> dict[str, Any]:
    return control_response(home_id, ensure_control(home_id))


@app.put("/api/home/{home_id}/control/mode", dependencies=[Depends(require_home_permission("can_change_control_mode"))])
def update_control_mode(
    home_id: str,
    request: ControlModeUpdateRequest,
) -> dict[str, Any]:
    mode = request.mode.strip().lower()
    if mode not in VALID_CONTROL_MODES:
        raise HTTPException(status_code=400, detail="Mode must be manual, assist, or auto.")

    timestamp_ms = now_ms()
    record = {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
        "mode": mode,
        "updated_by": request.updated_by,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    history_id = f"mode_{timestamp_ms}"

    safe_update(f"/homes/{home_id}/control", record)
    safe_set(
        f"/homes/{home_id}/control/history/{history_id}",
        {
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": iso_from_ms(timestamp_ms),
            "timezone": TIMEZONE,
            "history_id": history_id,
            "home_id": home_id,
            **record,
        },
    )

    return {
        "success": True,
        "home_id": home_id,
        "mode": mode,
        "message": f"Control mode updated to {control_label(mode)} Mode.",
    }


@app.get("/api/home/{home_id}/schedules", dependencies=[Depends(require_home_permission("can_view"))])
def get_schedules(home_id: str) -> dict[str, Any]:
    schedules = [
        item for item in object_to_list(safe_get(f"/homes/{home_id}/schedules", {}))
        if item.get("deleted") is not True
    ]
    schedules.sort(
        key=lambda item: (
            item.get("next_run_at_ms") is None,
            as_number(item.get("next_run_at_ms"), 0),
            str(item.get("name", "")),
        )
    )
    return {"home_id": home_id, "count": len(schedules), "schedules": schedules}


@app.post("/api/home/{home_id}/schedules", dependencies=[Depends(require_home_permission("can_manage_schedules"))])
def create_schedule(home_id: str, request: ScheduleCreateRequest) -> dict[str, Any]:
    timestamp_ms = now_ms()
    schedule_id = f"sch_{timestamp_ms}"
    payload = validate_schedule_payload(home_id, request.dict())
    schedule = {
        **payload,
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
        "schedule_id": schedule_id,
        "home_id": home_id,
        "last_run_at_ms": None,
        "last_run_at_iso": None,
        "created_by": request.created_by,
        "created_at_ms": timestamp_ms,
        "created_at_iso": iso_from_ms(timestamp_ms),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_set(f"/homes/{home_id}/schedules/{schedule_id}", schedule)
    schedule_history(home_id, schedule_id, "created", request.created_by, None, schedule)
    return {"home_id": home_id, "schedule": schedule}


@app.put("/api/home/{home_id}/schedules/{schedule_id}", dependencies=[Depends(require_home_permission("can_manage_schedules"))])
def update_schedule(
    home_id: str,
    schedule_id: str,
    request: ScheduleUpdateRequest,
) -> dict[str, Any]:
    previous = as_dict(safe_get(f"/homes/{home_id}/schedules/{schedule_id}", {}))
    if not previous or previous.get("deleted") is True:
        raise HTTPException(status_code=404, detail="Schedule does not exist.")

    updates = request.dict(exclude_unset=True)
    updated_by = str(updates.pop("updated_by", "api"))
    updated = validate_schedule_payload(home_id, updates, previous)
    timestamp_ms = now_ms()
    updated.update(
        {
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": iso_from_ms(timestamp_ms),
            "timezone": TIMEZONE,
            "schedule_id": schedule_id,
            "home_id": home_id,
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": iso_from_ms(timestamp_ms),
        }
    )
    safe_update(f"/homes/{home_id}/schedules/{schedule_id}", updated)
    schedule_history(home_id, schedule_id, "updated", updated_by, previous, updated)
    return {"home_id": home_id, "schedule": updated}


@app.patch("/api/home/{home_id}/schedules/{schedule_id}/enabled", dependencies=[Depends(require_home_permission("can_manage_schedules"))])
def set_schedule_enabled(
    home_id: str,
    schedule_id: str,
    request: ScheduleEnabledRequest,
) -> dict[str, Any]:
    previous = as_dict(safe_get(f"/homes/{home_id}/schedules/{schedule_id}", {}))
    if not previous or previous.get("deleted") is True:
        raise HTTPException(status_code=404, detail="Schedule does not exist.")
    next_ms, next_iso = (
        calculate_next_run(str(previous.get("time")), validate_days(previous.get("days")), str(previous.get("timezone") or "Asia/Bahrain"))
        if request.enabled
        else (None, None)
    )
    timestamp_ms = now_ms()
    updates = {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
        "enabled": request.enabled,
        "next_run_at_ms": next_ms,
        "next_run_at_iso": next_iso,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    updated = {**previous, **updates}
    safe_update(f"/homes/{home_id}/schedules/{schedule_id}", updates)
    schedule_history(home_id, schedule_id, "enabled_changed", request.updated_by, previous, updated)
    return {"home_id": home_id, "schedule": updated}


@app.delete("/api/home/{home_id}/schedules/{schedule_id}", dependencies=[Depends(require_home_permission("can_manage_schedules"))])
def delete_schedule(home_id: str, schedule_id: str, deleted_by: str = "api") -> dict[str, Any]:
    previous = as_dict(safe_get(f"/homes/{home_id}/schedules/{schedule_id}", {}))
    if not previous or previous.get("deleted") is True:
        raise HTTPException(status_code=404, detail="Schedule does not exist.")
    timestamp_ms = now_ms()
    updates = {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
        "deleted": True,
        "enabled": False,
        "next_run_at_ms": None,
        "next_run_at_iso": None,
        "deleted_at_ms": timestamp_ms,
        "deleted_at_iso": iso_from_ms(timestamp_ms),
        "deleted_by": deleted_by,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    updated = {**previous, **updates}
    safe_update(f"/homes/{home_id}/schedules/{schedule_id}", updates)
    schedule_history(home_id, schedule_id, "deleted", deleted_by, previous, updated)
    return {"success": True, "home_id": home_id, "schedule_id": schedule_id}


def run_schedule(home_id: str, schedule_id: str, manual: bool = False) -> dict[str, Any]:
    settings = ensure_settings(home_id)
    if settings.get("schedules_enabled") is False:
        schedule = as_dict(safe_get(f"/homes/{home_id}/schedules/{schedule_id}", {}))
        log = log_schedule_run(home_id, schedule, "failed", "Schedules are disabled in settings.")
        return {"success": False, "home_id": home_id, "log": log}

    schedule = as_dict(safe_get(f"/homes/{home_id}/schedules/{schedule_id}", {}))
    if not schedule or schedule.get("deleted") is True:
        raise HTTPException(status_code=404, detail="Schedule does not exist.")
    if not manual and active_emergency_mode(home_id):
        timestamp_ms = now_ms()
        next_ms, next_iso = calculate_next_run(
            str(schedule.get("time")),
            validate_days(schedule.get("days")),
            str(schedule.get("timezone") or "Asia/Bahrain"),
        )
        safe_update(
            f"/homes/{home_id}/schedules/{schedule_id}",
            {
                "last_run_at_ms": timestamp_ms,
                "last_run_at_iso": iso_from_ms(timestamp_ms),
                "next_run_at_ms": next_ms,
                "next_run_at_iso": next_iso,
                "updated_at_ms": timestamp_ms,
                "updated_at_iso": iso_from_ms(timestamp_ms),
            },
        )
        log = log_schedule_run(
            home_id,
            schedule,
            "skipped_emergency_mode",
            "Normal schedule skipped while emergency mode is active.",
        )
        return {"success": False, "home_id": home_id, "log": log}
    if not manual and schedule.get("enabled") is not True:
        log = log_schedule_run(home_id, schedule, "failed", "Schedule is disabled.")
        return {"success": False, "home_id": home_id, "log": log}

    device_id = str(schedule.get("device_id", ""))
    device = as_dict(safe_get(f"/homes/{home_id}/devices/{device_id}", {}))
    if not device or not is_controllable_device(device_id, device):
        log = log_schedule_run(home_id, schedule, "failed", "Device is not available or controllable.")
        return {"success": False, "home_id": home_id, "log": log}

    formatted = format_device(device_id, device)
    timestamp_ms = now_ms()
    next_ms, next_iso = calculate_next_run(
        str(schedule.get("time")),
        validate_days(schedule.get("days")),
        str(schedule.get("timezone") or "Asia/Bahrain"),
    )
    schedule_updates = {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
        "last_run_at_ms": timestamp_ms,
        "last_run_at_iso": iso_from_ms(timestamp_ms),
        "next_run_at_ms": next_ms,
        "next_run_at_iso": next_iso,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }

    if formatted.get("online") is not True:
        safe_update(f"/homes/{home_id}/schedules/{schedule_id}", schedule_updates)
        log = log_schedule_run(home_id, schedule, "skipped_offline", "Device is offline. Schedule skipped.")
        return {"success": False, "home_id": home_id, "log": log}
    if normalize_bool(device.get("command_in_progress")) is True:
        safe_update(f"/homes/{home_id}/schedules/{schedule_id}", schedule_updates)
        log = log_schedule_run(home_id, schedule, "failed", "Another command is already in progress.")
        return {"success": False, "home_id": home_id, "log": log}
    if str(formatted.get("state", "")).lower() == str(schedule.get("target_state")):
        safe_update(f"/homes/{home_id}/schedules/{schedule_id}", schedule_updates)
        log = log_schedule_run(home_id, schedule, "already_in_state", "Device is already in the target state.")
        return {"success": True, "home_id": home_id, "log": log}

    response = create_device_command(
        home_id,
        device_id,
        DeviceCommandRequest(
            command=str(schedule.get("command")),
            requested_by="schedule_manual_run" if manual else "schedule",
            reason=f"Schedule: {schedule.get('name')}",
        ),
    )
    safe_update(f"/homes/{home_id}/schedules/{schedule_id}", schedule_updates)
    log = log_schedule_run(
        home_id,
        schedule,
        "command_created",
        "Schedule created command successfully.",
        response.command_id,
    )
    return {
        "success": True,
        "home_id": home_id,
        "schedule_id": schedule_id,
        "command_id": response.command_id,
        "log": log,
    }


@app.post("/api/home/{home_id}/schedules/{schedule_id}/run-now", dependencies=[Depends(require_home_permission("can_manage_schedules"))])
def run_schedule_now(home_id: str, schedule_id: str) -> dict[str, Any]:
    return run_schedule(home_id, schedule_id, manual=True)


@app.post("/api/home/{home_id}/schedules/run-due", dependencies=[Depends(require_home_permission("can_manage_schedules"))])
def run_due_schedules(home_id: str) -> dict[str, Any]:
    now = now_ms()
    schedules = [
        item for item in object_to_list(safe_get(f"/homes/{home_id}/schedules", {}))
        if item.get("enabled") is True
        and item.get("deleted") is not True
        and isinstance(item.get("next_run_at_ms"), (int, float))
        and int(item.get("next_run_at_ms")) <= now
    ]
    results = []
    for schedule in schedules:
        schedule_id = str(schedule.get("schedule_id") or schedule.get("id"))
        try:
            results.append(run_schedule(home_id, schedule_id, manual=False))
        except Exception as error:
            log = log_schedule_run(
                home_id,
                schedule,
                "failed",
                f"Schedule runner failed: {error}",
            )
            results.append({"success": False, "home_id": home_id, "schedule_id": schedule_id, "log": log})
    return {"home_id": home_id, "count": len(results), "results": results}


@app.get("/api/home/{home_id}/action-suggestions/active", dependencies=[Depends(require_home_permission("can_view"))])
def get_active_action_suggestions(home_id: str) -> dict[str, Any]:
    suggestions = dedupe_action_suggestions(
        active_only(
            object_to_list(safe_get(f"/homes/{home_id}/action_suggestions/active", {}))
        )
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


def remove_matching_emergency_suggestions(home_id: str, suggestion: dict[str, Any]) -> None:
    if str(suggestion.get("type", "")).lower() != "emergency_action":
        return
    device_id = str(suggestion.get("device_id", ""))
    source = str(suggestion.get("source", ""))
    active = as_dict(safe_get(f"/homes/{home_id}/action_suggestions/active", {}))
    for active_id, raw_item in active.items():
        item = as_dict(raw_item)
        if (
            str(item.get("type", "")).lower() == "emergency_action"
            and str(item.get("device_id", "")) == device_id
            and str(item.get("source", "")) == source
        ):
            safe_set(f"/homes/{home_id}/action_suggestions/active/{active_id}", None)


@app.post(
    "/api/home/{home_id}/action-suggestions/{suggestion_id}/approve",
    response_model=SuggestionDecisionResponse,
    dependencies=[Depends(require_home_permission("can_control_devices"))],
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
            requested_by="user_emergency_action"
            if suggestion.get("type") == "emergency_action"
            else "user_approved_ai_suggestion",
            reason=str(suggestion.get("reason", "")),
            source_suggestion_id=suggestion_id,
            source="smoke_emergency" if suggestion.get("type") == "emergency_action" else None,
            emergency=suggestion.get("type") == "emergency_action",
            alert_id=SMOKE_ALERT_ID if suggestion.get("type") == "emergency_action" else None,
        ),
    )

    timestamp_ms = now_ms()
    updated = {
        **suggestion,
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
        "status": "approved",
        "approved_at_ms": timestamp_ms,
        "approved_at_iso": iso_from_ms(timestamp_ms),
        "command_id": command_response.command_id,
    }
    safe_set(f"/homes/{home_id}/action_suggestions/history/{suggestion_id}", updated)
    remove_matching_emergency_suggestions(home_id, suggestion)
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
    dependencies=[Depends(require_home_permission("can_acknowledge_alerts"))],
)
def dismiss_action_suggestion(home_id: str, suggestion_id: str) -> SuggestionDecisionResponse:
    suggestion = as_dict(
        safe_get(f"/homes/{home_id}/action_suggestions/active/{suggestion_id}", {})
    )
    if not suggestion:
        return SuggestionDecisionResponse(
            success=True,
            home_id=home_id,
            suggestion_id=suggestion_id,
            status="dismissed",
            message="Action suggestion dismissed.",
        )
    timestamp_ms = now_ms()
    updated = {
        **suggestion,
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
        "status": "dismissed",
        "dismissed_at_ms": timestamp_ms,
        "dismissed_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_set(f"/homes/{home_id}/action_suggestions/history/{suggestion_id}", updated)
    remove_matching_emergency_suggestions(home_id, suggestion)
    safe_set(f"/homes/{home_id}/action_suggestions/active/{suggestion_id}", None)
    return SuggestionDecisionResponse(
        success=True,
        home_id=home_id,
        suggestion_id=suggestion_id,
        status="dismissed",
        message="Action suggestion dismissed.",
    )


@app.post("/api/home/{home_id}/safety/smoke/actions/turn-off-safe-devices", dependencies=[Depends(require_home_permission("can_control_devices"))])
def turn_off_safe_devices(home_id: str) -> dict[str, Any]:
    alert = as_dict(safe_get(f"/homes/{home_id}/alerts/active/{SMOKE_ALERT_ID}", {}))
    if not alert or alert.get("status") != "active":
        raise HTTPException(status_code=409, detail="No active smoke emergency alert exists.")

    devices = as_dict(safe_get(f"/homes/{home_id}/devices", {}))
    commands_created = []
    skipped = []
    for device_id, raw_device in devices.items():
        device = as_dict(raw_device)
        safety = ensure_device_safety(home_id, device_id)
        if safety.get("emergency_shutdown_allowed") is not True:
            skipped.append({"device_id": device_id, "reason": "emergency shutdown not allowed"})
            continue
        if not is_controllable_device(device_id, device):
            skipped.append({"device_id": device_id, "reason": "device not controllable"})
            continue
        formatted = format_device(device_id, device)
        if formatted.get("online") is not True:
            skipped.append({"device_id": device_id, "reason": "device offline"})
            continue
        if str(formatted.get("state", "")).lower() == "off":
            skipped.append({"device_id": device_id, "reason": "already off"})
            continue
        if normalize_bool(device.get("command_in_progress")) is True:
            skipped.append({"device_id": device_id, "reason": "command already in progress"})
            continue
        response = create_device_command(
            home_id,
            device_id,
            DeviceCommandRequest(
                command="turn_off",
                requested_by="user_emergency_action",
                reason="Smoke or gas emergency: turn off safe device.",
                source="smoke_emergency",
                emergency=True,
                alert_id=SMOKE_ALERT_ID,
            ),
        )
        commands_created.append({"device_id": device_id, "command_id": response.command_id})

    safety_event(
        home_id,
        "emergency_shutdown_command_created",
        "User requested emergency shutdown for safe devices.",
        actions_taken=[f"commands_created:{len(commands_created)}"],
    )
    return {
        "success": True,
        "home_id": home_id,
        "commands_created": len(commands_created),
        "commands": commands_created,
        "skipped": skipped,
        "message": "Emergency shutdown commands were created for safe devices.",
    }


@app.post("/api/home/{home_id}/safety/smoke/actions/mark-safe", dependencies=[Depends(require_home_permission("can_acknowledge_alerts"))])
def mark_smoke_safe(home_id: str) -> dict[str, Any]:
    timestamp_ms = now_ms()
    if latest_smoke_is_clear_for(home_id):
        resolve_smoke_emergency_if_clear(home_id)
        safety_event(home_id, "emergency_mode_disabled", "User marked smoke/gas event safe.")
        return {"success": True, "resolved": True, "message": "Smoke/gas alert resolved and emergency mode disabled."}

    smoke_state = as_dict(safe_get(f"/homes/{home_id}/safety/smoke_state", {}))
    current_state = as_dict(safe_get(f"/homes/{home_id}/backend/current_state", {}))
    esp32_sensors = as_dict(safe_get(f"/homes/{home_id}/devices/esp32_01/sensors", {}))
    still_detected = (
        normalize_bool(current_state.get("smoke")) is True
        or normalize_bool(esp32_sensors.get("smoke")) is True
        or smoke_state.get("status") == "confirmed"
        and as_number(smoke_state.get("last_clear_at_ms")) <= 0
    )
    if still_detected:
        safe_update(
            f"/homes/{home_id}/alerts/active/{SMOKE_ALERT_ID}",
            {
                "acknowledged": True,
                "acknowledged_at_ms": timestamp_ms,
                "acknowledged_at_iso": iso_from_ms(timestamp_ms),
                "updated_at_ms": timestamp_ms,
                "updated_at_iso": iso_from_ms(timestamp_ms),
            },
        )
        safety_event(home_id, "smoke_acknowledged", "User checked the room while sensor still reports smoke/gas.")
        return {
            "success": True,
            "resolved": False,
            "message": "Acknowledged, but smoke/gas is still detected. Keep emergency mode active.",
        }

    alert = as_dict(safe_get(f"/homes/{home_id}/alerts/active/{SMOKE_ALERT_ID}", {}))
    if alert:
        safe_set(
            f"/homes/{home_id}/alerts/history/alert_{timestamp_ms}_{SMOKE_ALERT_ID}",
            {
                **alert,
                "status": "resolved",
                "resolved_at_ms": timestamp_ms,
                "resolved_at_iso": iso_from_ms(timestamp_ms),
                "updated_at_ms": timestamp_ms,
                "updated_at_iso": iso_from_ms(timestamp_ms),
            },
        )
        safe_set(f"/homes/{home_id}/alerts/active/{SMOKE_ALERT_ID}", None)
    emergency = as_dict(safe_get(f"/homes/{home_id}/safety/emergency_mode", {}))
    if emergency.get("active") is True:
        safe_update(
            f"/homes/{home_id}/safety/emergency_mode",
            {
                "active": False,
                "ended_at_ms": timestamp_ms,
                "ended_at_iso": iso_from_ms(timestamp_ms),
                "updated_at_ms": timestamp_ms,
                "updated_at_iso": iso_from_ms(timestamp_ms),
            },
        )
    safe_update(
        f"/homes/{home_id}/safety/smoke_state",
        {
            "status": "clear",
            "consecutive_detections": 0,
            "last_clear_at_ms": timestamp_ms,
            "last_clear_at_iso": iso_from_ms(timestamp_ms),
            "notification_sent": False,
            "notification_sent_at_ms": None,
            "notification_sent_at_iso": None,
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": iso_from_ms(timestamp_ms),
        },
    )
    safety_event(home_id, "emergency_mode_disabled", "User marked smoke/gas event safe.")
    return {"success": True, "resolved": True, "message": "Smoke/gas alert resolved and emergency mode disabled."}


@app.post("/api/home/{home_id}/notifications/register-token", dependencies=[Depends(require_home_permission("can_view"))])
def register_notification_token(home_id: str, request: NotificationTokenRequest) -> dict[str, Any]:
    timestamp_ms = now_ms()
    token_id = re.sub(r"[^A-Za-z0-9_-]", "_", request.token[-32:]) or f"token_{timestamp_ms}"
    existing_tokens = as_dict(safe_get(f"/homes/{home_id}/notification_tokens", {}))
    updates: dict[str, Any] = {}
    for existing_id, existing_value in existing_tokens.items():
        existing = as_dict(existing_value)
        if existing_id == token_id or existing.get("active") is not True:
            continue
        same_installation = (
            request.installation_id is not None
            and existing.get("installation_id") == request.installation_id
        )
        same_user_platform = (
            existing.get("user_id") == request.user_id
            and existing.get("platform") == request.platform
        )
        if same_installation or same_user_platform:
            updates[f"{existing_id}/active"] = False
            updates[f"{existing_id}/deactivated_at_ms"] = timestamp_ms
            updates[f"{existing_id}/deactivated_at_iso"] = iso_from_ms(timestamp_ms)
            updates[f"{existing_id}/deactivation_reason"] = "replaced_by_latest_token"
    record = {
        "token": request.token,
        "platform": request.platform,
        "user_id": request.user_id,
        "installation_id": request.installation_id,
        "active": True,
        "created_at_ms": timestamp_ms,
        "created_at_iso": iso_from_ms(timestamp_ms),
        "last_seen_at_ms": timestamp_ms,
        "last_seen_at_iso": iso_from_ms(timestamp_ms),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    if updates:
        safe_update(f"/homes/{home_id}/notification_tokens", updates)
    safe_set(f"/homes/{home_id}/notification_tokens/{token_id}", record)
    return {"success": True, "home_id": home_id, "token_id": token_id}


@app.get("/api/home/{home_id}/notifications", dependencies=[Depends(require_home_permission("can_view"))])
def list_notifications(home_id: str, limit: int = 50, unread_only: bool = False) -> dict[str, Any]:
    raw_notifications = object_to_list(safe_get(f"/homes/{home_id}/notifications", {}))
    notifications = [
        item
        for item in raw_notifications
        if isinstance(item, dict) and (not unread_only or item.get("read") is not True)
    ]
    notifications.sort(key=notification_sort_key, reverse=True)
    limited = notifications[: max(1, min(int(limit), 100))]
    unread_count = sum(1 for item in raw_notifications if isinstance(item, dict) and item.get("read") is not True)
    return {
        "success": True,
        "home_id": home_id,
        "count": len(limited),
        "unread_count": unread_count,
        "notifications": limited,
    }


@app.post("/api/home/{home_id}/notifications/{notification_id}/read", dependencies=[Depends(require_home_permission("can_view"))])
def mark_notification_read(home_id: str, notification_id: str) -> dict[str, Any]:
    timestamp_ms = now_ms()
    safe_update(
        f"/homes/{home_id}/notifications/{notification_id}",
        {"read": True, "read_at_ms": timestamp_ms, "read_at_iso": iso_from_ms(timestamp_ms)},
    )
    return {"success": True, "home_id": home_id, "notification_id": notification_id}


@app.get("/api/home/{home_id}/members")
def get_members(
    home_id: str,
    actor: AuthContext = Depends(require_home_permission("can_manage_users")),
) -> dict[str, Any]:
    members = object_to_list(safe_get(f"/homes/{home_id}/members", {}))
    audit_log(home_id, actor, "members_listed", "home", home_id)
    return {"success": True, "home_id": home_id, "count": len(members), "members": members}


@app.post("/api/home/{home_id}/members")
def add_member(
    home_id: str,
    request: MemberCreateRequest,
    actor: AuthContext = Depends(require_home_permission("can_manage_users")),
) -> dict[str, Any]:
    role = validate_role(request.role)
    if role == "member" and home_member_count(home_id, roles={"member"}) >= HOME_MEMBER_LIMIT:
        raise HTTPException(status_code=409, detail=f"This home already has the maximum {HOME_MEMBER_LIMIT} members.")
    email = request.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email is required.")

    profile = find_user_profile_by_email(email)
    user_uid = str(profile.get("uid") or "")
    user_display_name = str(profile.get("display_name") or email)
    if not user_uid:
        timestamp_ms = now_ms()
        invitation_id = re.sub(r"[^A-Za-z0-9_-]", "_", email)
        safe_set(
            f"/homes/{home_id}/invitations/{invitation_id}",
            {
                "email": email,
                "role": role,
                "status": "pending_signup",
                "created_by": actor.actor_id,
                "created_at_ms": timestamp_ms,
                "created_at_iso": iso_from_ms(timestamp_ms),
            },
        )
        audit_log(home_id, actor, "member_invited_signup_required", "member", email, {"role": role})
        return {
            "success": True,
            "home_id": home_id,
            "status": "pending_signup",
            "message": "User must sign up first. Invitation record created.",
        }

    uid = user_uid
    profile = as_dict(safe_get(f"/users/{uid}", {}))
    display_name = str(profile.get("display_name") or user_display_name or email)
    record = member_record(uid, email, display_name, role)
    safe_set(f"/homes/{home_id}/members/{uid}", record)
    safe_update(
        f"/users/{uid}",
        {
            "uid": uid,
            "email": email,
            "display_name": display_name,
            "default_home_id": profile.get("default_home_id") or home_id,
            "homes": {**as_dict(profile.get("homes")), home_id: {"role": role, **get_permissions_for_role(role)}},
            "updated_at_ms": record["updated_at_ms"],
            "updated_at_iso": record["updated_at_iso"],
        },
    )
    audit_log(home_id, actor, "member_added", "member", uid, {"role": role})
    return {"success": True, "home_id": home_id, "member": record}


@app.put("/api/home/{home_id}/members/{uid}/role")
def update_member_role(
    home_id: str,
    uid: str,
    request: MemberRoleUpdateRequest,
    actor: AuthContext = Depends(require_home_permission("can_manage_users")),
) -> dict[str, Any]:
    role = validate_role(request.role)
    existing = as_dict(safe_get(f"/homes/{home_id}/members/{uid}", {}))
    if not existing:
        raise HTTPException(status_code=404, detail="Member does not exist.")
    if validate_role(str(existing.get("role", "viewer"))) == "home_admin" and role != "home_admin" and admin_count(home_id) <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove the last admin from the home.")

    timestamp_ms = now_ms()
    permissions = get_permissions_for_role(role)
    update = {
        "role": role,
        "permissions": permissions,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_update(f"/homes/{home_id}/members/{uid}", update)
    user_profile = as_dict(safe_get(f"/users/{uid}", {}))
    user_homes = {**as_dict(user_profile.get("homes")), home_id: {"role": role, **permissions}}
    safe_update(f"/users/{uid}/homes/{home_id}", {"role": role, **permissions})
    safe_update(
        f"/users/{uid}",
        {"homes": user_homes, "updated_at_ms": timestamp_ms, "updated_at_iso": iso_from_ms(timestamp_ms)},
    )
    audit_log(home_id, actor, "member_role_changed", "member", uid, {"role": role})
    return {"success": True, "home_id": home_id, "uid": uid, "role": role, "permissions": permissions}


@app.delete("/api/home/{home_id}/members/{uid}")
def remove_member(
    home_id: str,
    uid: str,
    actor: AuthContext = Depends(require_home_permission("can_manage_users")),
) -> dict[str, Any]:
    existing = as_dict(safe_get(f"/homes/{home_id}/members/{uid}", {}))
    if not existing:
        raise HTTPException(status_code=404, detail="Member does not exist.")
    if validate_role(str(existing.get("role", "viewer"))) == "home_admin" and admin_count(home_id) <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove the last admin from the home.")
    safe_set(f"/homes/{home_id}/members/{uid}", None)
    safe_set(f"/users/{uid}/homes/{home_id}", None)
    user_profile = as_dict(safe_get(f"/users/{uid}", {}))
    user_homes = as_dict(user_profile.get("homes"))
    user_homes.pop(home_id, None)
    safe_update(f"/users/{uid}", {"homes": user_homes, "updated_at_ms": now_ms(), "updated_at_iso": iso_from_ms(now_ms())})
    audit_log(home_id, actor, "member_removed", "member", uid)
    return {"success": True, "home_id": home_id, "uid": uid}


@app.get("/api/home/{home_id}/devices", dependencies=[Depends(require_home_permission("can_view"))])
def get_devices(home_id: str) -> dict[str, Any]:
    bundle = read_home_bundle(home_id)
    devices = build_devices(bundle, home_id)
    return {
        "home_id": home_id,
        "count": len(devices),
        "devices": list(devices.values()),
    }


@app.post("/api/home/{home_id}/devices/home-assistant/sync", dependencies=[Depends(require_home_permission("can_view"))])
def sync_home_assistant(home_id: str) -> dict[str, Any]:
    return {"success": True, "home_id": home_id, "results": sync_home_assistant_devices(home_id)}


@app.get("/api/home/{home_id}/alerts/active", dependencies=[Depends(require_home_permission("can_view"))])
def get_active_alerts(home_id: str) -> dict[str, Any]:
    bundle = read_home_bundle(home_id)
    alerts = dedupe_alerts(active_only(
        object_to_list(bundle["alerts_active"])
        + object_to_list(bundle["backend_active_alerts"])
    ))
    return {"home_id": home_id, "count": len(alerts), "alerts": alerts}


@app.post("/api/home/{home_id}/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    home_id: str,
    alert_id: str,
    actor: AuthContext = Depends(require_home_permission("can_acknowledge_alerts")),
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    alert = as_dict(safe_get(f"/homes/{home_id}/alerts/active/{alert_id}", {}))
    if not alert:
        alert = as_dict(safe_get(f"/homes/{home_id}/backend/active_alerts/{alert_id}", {}))
    if not alert:
        raise HTTPException(status_code=404, detail="Alert does not exist.")
    update = {
        "acknowledged": True,
        "acknowledged_by": actor.actor_id,
        "acknowledged_at_ms": timestamp_ms,
        "acknowledged_at_iso": iso_from_ms(timestamp_ms),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_update(f"/homes/{home_id}/alerts/active/{alert_id}", update)
    audit_log(home_id, actor, "alert_acknowledged", "alert", alert_id)
    return {"success": True, "home_id": home_id, "alert_id": alert_id}


@app.get("/api/home/{home_id}/recommendations/active", dependencies=[Depends(require_home_permission("can_view"))])
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


def build_command_record(
    home_id: str,
    device_id: str,
    device_name: str,
    command: str,
    target_state: str,
    current_state: str,
    request: DeviceCommandRequest,
    *,
    control_method: str,
    ha_entity_id: str | None = None,
    status: str = "pending",
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    timestamp_iso = iso_from_ms(timestamp_ms)
    command_id = f"cmd_{timestamp_ms}"
    return {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": timestamp_iso,
        "timezone": TIMEZONE,
        "command_id": command_id,
        "home_id": home_id,
        "device_id": device_id,
        "device_name": device_name,
        "command": command,
        "action": command,
        "target_state": target_state,
        "previous_state": current_state,
        "requested_by": request.requested_by,
        "reason": request.reason,
        "source": request.source,
        "emergency": request.emergency,
        "alert_id": request.alert_id,
        "source_suggestion_id": request.source_suggestion_id,
        "control_method": control_method,
        "ha_entity_id": ha_entity_id,
        "status": status,
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


def write_command_record(
    home_id: str,
    device_id: str,
    command_record: dict[str, Any],
    *,
    pending: bool,
) -> None:
    command_id = str(command_record["command_id"])
    if pending:
        safe_set(f"/homes/{home_id}/commands/pending/{command_id}", command_record)
    else:
        safe_set(f"/homes/{home_id}/commands/pending/{command_id}", None)
    safe_set(f"/homes/{home_id}/commands/history/{command_id}", command_record)
    safe_set(f"/homes/{home_id}/commands/latest_by_device/{device_id}", command_record)
    safe_set(
        f"/homes/{home_id}/commands/{device_id}/latest",
        {
            **command_record,
            "created_at": command_record.get("requested_at_ms"),
            "created_at_ms": command_record.get("requested_at_ms"),
            "created_at_iso": command_record.get("requested_at_iso"),
            "source": command_record.get("requested_by"),
        },
    )


def execute_home_assistant_device_command(
    home_id: str,
    device_id: str,
    device: dict[str, Any],
    request: DeviceCommandRequest,
    command: str,
    requested_by: str,
) -> DeviceCommandResponse:
    entity_id = str(device.get("ha_entity_id") or "").strip()
    if not entity_id:
        error = HomeAssistantError(
            "HA_ENTITY_NOT_FOUND",
            "Matter switch was not found in Home Assistant.",
            "Missing ha_entity_id.",
        )
        mark_ha_device_error(home_id, device_id, error)
        raise HTTPException(status_code=409, detail={"success": False, "status": error.code, "message": error.user_message})

    target_state = command_to_target_state(command)
    device_name = device_message_name(device_id, device)

    try:
        current_state = get_entity_state(entity_id)
        update_ha_device_from_state(home_id, device_id, current_state)
    except HomeAssistantError as error:
        mark_ha_device_error(home_id, device_id, error, state="unknown")
        raise HTTPException(
            status_code=409,
            detail={"success": False, "status": error.code, "message": error.user_message},
        ) from error

    if current_state == target_state:
        already_record = build_command_record(
            home_id,
            device_id,
            device_name,
            command,
            target_state,
            current_state,
            request,
            control_method="home_assistant",
            ha_entity_id=entity_id,
            status="already_in_state",
        )
        already_record["result"] = {
            "success": True,
            "actual_state": current_state,
            "error_code": None,
            "user_message": f"{device_name} is already {target_state}.",
            "raw_error": None,
        }
        write_command_record(home_id, device_id, already_record, pending=False)
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
            write_automation_log(home_id, device_id, device_name, command, already_record["command_id"], request.reason)
        return DeviceCommandResponse(
            success=True,
            no_action=True,
            status="already_in_state",
            device_id=device_id,
            command_id=already_record["command_id"],
            command=command,
            current_state=current_state,
            target_state=target_state,
            message=f"{device_name} is already {target_state}.",
        )

    command_record = build_command_record(
        home_id,
        device_id,
        device_name,
        command,
        target_state,
        current_state,
        request,
        control_method="home_assistant",
        ha_entity_id=entity_id,
    )
    command_id = str(command_record["command_id"])
    write_command_record(home_id, device_id, command_record, pending=True)
    safe_update(
        f"/homes/{home_id}/devices/{device_id}",
        {
            "command_in_progress": True,
            "pending_command_id": command_id,
            "pending_target_state": target_state,
            "last_requested_state": target_state,
            "last_command_status": "pending",
            "last_command_message": "Command sent. Waiting for Matter confirmation.",
            "last_command": {
                "status": "pending",
                "user_message": None,
                "error_code": None,
            },
        },
    )

    sent_at = now_ms()
    command_record.update(
        {
            "timestamp_ms": sent_at,
            "timestamp_iso": iso_from_ms(sent_at),
            "status": "sent",
            "sent_at_ms": sent_at,
            "sent_at_iso": iso_from_ms(sent_at),
        }
    )
    write_command_record(home_id, device_id, command_record, pending=True)

    try:
        execute_home_assistant_command(entity_id, command)
        time.sleep(1.5)
        actual_state = get_entity_state(entity_id)
        if actual_state != target_state:
            raise HomeAssistantError(
                "HA_COMMAND_FAILED",
                "Matter switch command failed. Please try again.",
                f"Expected {target_state}, got {actual_state}.",
            )

        confirmed_at = now_ms()
        message = f"{device_name} turned {target_state} successfully."
        command_record.update(
            {
                "timestamp_ms": confirmed_at,
                "timestamp_iso": iso_from_ms(confirmed_at),
                "status": "confirmed",
                "confirmed_at_ms": confirmed_at,
                "confirmed_at_iso": iso_from_ms(confirmed_at),
                "result": {
                    "success": True,
                    "actual_state": actual_state,
                    "error_code": None,
                    "user_message": message,
                    "raw_error": None,
                },
            }
        )
        write_command_record(home_id, device_id, command_record, pending=False)
        safe_update(
            f"/homes/{home_id}/devices/{device_id}",
            {
                "state": actual_state,
                "display_state": actual_state,
                "online": True,
                "local_online": True,
                "cloud_online": False,
                "command_in_progress": False,
                "pending_command_id": None,
                "pending_target_state": None,
                "last_requested_state": actual_state,
                "last_command_status": "confirmed",
                "last_command_message": message,
                "last_command": {
                    "status": "confirmed",
                    "user_message": message,
                    "error_code": None,
                },
                "updated_at_ms": confirmed_at,
                "updated_at_iso": iso_from_ms(confirmed_at),
            },
        )
        if is_auto_requester(requested_by):
            write_automation_log(home_id, device_id, device_name, command, command_id, request.reason)
        return DeviceCommandResponse(
            success=True,
            no_action=False,
            command_id=command_id,
            device_id=device_id,
            command=command,
            target_state=target_state,
            previous_state=current_state,
            current_state=actual_state,
            status="confirmed",
            message=message,
        )
    except HomeAssistantError as error:
        failed_at = now_ms()
        previous_state = current_state if current_state in {"on", "off"} else device.get("state", "unknown")
        command_record.update(
            {
                "timestamp_ms": failed_at,
                "timestamp_iso": iso_from_ms(failed_at),
                "status": "failed",
                "failed_at_ms": failed_at,
                "failed_at_iso": iso_from_ms(failed_at),
                "result": {
                    "success": False,
                    "actual_state": previous_state,
                    "error_code": error.code,
                    "user_message": error.user_message,
                    "raw_error": str(error.raw_error or error),
                },
            }
        )
        write_command_record(home_id, device_id, command_record, pending=False)
        device_updates = {
            "command_in_progress": False,
            "pending_command_id": None,
            "pending_target_state": None,
            "last_command_status": "failed",
            "last_command_message": error.user_message,
            "last_command": {
                "status": "failed",
                "user_message": error.user_message,
                "error_code": error.code,
            },
            "updated_at_ms": failed_at,
            "updated_at_iso": iso_from_ms(failed_at),
        }
        if error.code in {"HOME_ASSISTANT_UNREACHABLE", "HA_STATE_UNKNOWN", "HA_ENTITY_NOT_FOUND"}:
            device_updates.update({"online": False, "local_online": False})
            if error.code != "HA_COMMAND_FAILED":
                device_updates.update({"state": "unknown", "display_state": "unknown"})
        safe_update(f"/homes/{home_id}/devices/{device_id}", device_updates)
        raise HTTPException(
            status_code=502 if error.code == "HOME_ASSISTANT_UNREACHABLE" else 409,
            detail={"success": False, "status": error.code, "message": error.user_message},
        ) from error


def queue_home_assistant_device_command(
    home_id: str,
    device_id: str,
    device: dict[str, Any],
    request: DeviceCommandRequest,
    command: str,
    requested_by: str,
) -> DeviceCommandResponse:
    entity_id = str(device.get("ha_entity_id") or "").strip()
    if not entity_id:
        raise HTTPException(
            status_code=409,
            detail={
                "success": False,
                "status": "HA_ENTITY_NOT_FOUND",
                "message": "Matter switch was not found in Home Assistant.",
            },
        )

    formatted_device = format_device(device_id, device)
    target_state = command_to_target_state(command)
    current_state = str(formatted_device.get("state", "unknown")).lower()
    device_name = device_message_name(device_id, device)

    if current_state == target_state:
        already_record = build_command_record(
            home_id,
            device_id,
            device_name,
            command,
            target_state,
            current_state,
            request,
            control_method="home_assistant",
            ha_entity_id=entity_id,
            status="already_in_state",
        )
        already_record["result"] = {
            "success": True,
            "actual_state": current_state,
            "error_code": None,
            "user_message": f"{device_name} is already {target_state}.",
            "raw_error": None,
        }
        write_command_record(home_id, device_id, already_record, pending=False)
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
            write_automation_log(home_id, device_id, device_name, command, already_record["command_id"], request.reason)
        return DeviceCommandResponse(
            success=True,
            no_action=True,
            status="already_in_state",
            device_id=device_id,
            command_id=already_record["command_id"],
            command=command,
            current_state=current_state,
            target_state=target_state,
            message=f"{device_name} is already {target_state}.",
        )

    command_record = build_command_record(
        home_id,
        device_id,
        device_name,
        command,
        target_state,
        current_state,
        request,
        control_method="home_assistant",
        ha_entity_id=entity_id,
    )
    command_id = str(command_record["command_id"])
    write_command_record(home_id, device_id, command_record, pending=True)
    safe_update(
        f"/homes/{home_id}/devices/{device_id}",
        {
            "command_in_progress": True,
            "pending_command_id": command_id,
            "pending_target_state": target_state,
            "last_requested_state": target_state,
            "last_command_status": "pending",
            "last_command_message": "Command queued for local Matter controller.",
            "last_command": {
                "status": "pending",
                "user_message": None,
                "error_code": None,
            },
        },
    )
    if is_auto_requester(requested_by):
        write_automation_log(home_id, device_id, device_name, command, command_id, request.reason)
    return DeviceCommandResponse(
        success=True,
        no_action=False,
        command_id=command_id,
        device_id=device_id,
        command=command,
        target_state=target_state,
        previous_state=current_state,
        status="pending",
        message="Command queued for local Matter controller.",
    )


@app.post(
    "/api/home/{home_id}/devices/{device_id}/command",
    response_model=DeviceCommandResponse,
    dependencies=[Depends(require_home_permission("can_control_devices"))],
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

    control_method = str(
        device.get("control_method") or ("tuya_cloud" if device_id.startswith("breaker_") else "")
    ).strip().lower()
    formatted_device = format_device(device_id, device)

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

    if control_method == "home_assistant":
        ha_mode = os.environ.get("HOME_ASSISTANT_COMMAND_MODE", "auto").strip().lower()
        if ha_mode == "queue" or not is_home_assistant_configured():
            return queue_home_assistant_device_command(
                home_id,
                device_id,
                device,
                request,
                command,
                requested_by,
            )
        return execute_home_assistant_device_command(
            home_id,
            device_id,
            device,
            request,
            command,
            requested_by,
        )

    if control_method and control_method != "tuya_cloud":
        raise HTTPException(status_code=400, detail=f"Unsupported control_method: {control_method}.")

    if formatted_device.get("online") is not True:
        raise HTTPException(
            status_code=409,
            detail={
                "success": False,
                "status": "device_offline",
                "message": "Device is offline. Check power or Wi-Fi connection.",
            },
        )

    if current_state == target_state:
        timestamp_ms = now_ms()
        command_id = f"cmd_{timestamp_ms}"
        already_record = {
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": iso_from_ms(timestamp_ms),
            "timezone": TIMEZONE,
            "command_id": command_id,
            "home_id": home_id,
            "device_id": device_id,
            "device_name": device_name,
            "command": command,
            "action": command,
            "target_state": target_state,
            "previous_state": current_state,
            "requested_by": request.requested_by,
            "reason": request.reason,
            "source": request.source,
            "emergency": request.emergency,
            "alert_id": request.alert_id,
            "source_suggestion_id": request.source_suggestion_id,
            "control_method": "tuya_cloud",
            "ha_entity_id": None,
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
        safe_set(f"/homes/{home_id}/commands/history/{command_id}", already_record)
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

    command_record = build_command_record(
        home_id,
        device_id,
        device_name,
        command,
        target_state,
        current_state,
        request,
        control_method="tuya_cloud",
    )
    command_id = str(command_record["command_id"])
    timestamp_ms = int(command_record["requested_at_ms"])
    timestamp_iso = str(command_record["requested_at_iso"])

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
        "created_at_ms": timestamp_ms,
        "created_at_iso": timestamp_iso,
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


def chat_actor_id(actor: AuthContext) -> str:
    return actor.uid or actor.actor_id


def chat_actor_name(actor: AuthContext) -> str:
    if actor.email:
        return actor.email
    return actor.actor_id


def chat_session_ref(home_id: str, session_id: str) -> str:
    return f"/homes/{home_id}/chat/sessions/{session_id}"


def chat_messages_ref(home_id: str, session_id: str) -> str:
    return f"{chat_session_ref(home_id, session_id)}/messages"


def sanitize_chat_title(title: str | None) -> str:
    clean = " ".join(str(title or "").strip().split())
    return clean[:80] if clean else "New Chat"


def title_from_message(message: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", message)
    stop = {
        "what",
        "why",
        "how",
        "is",
        "are",
        "the",
        "a",
        "an",
        "my",
        "me",
        "please",
        "explain",
        "meaning",
        "of",
    }
    picked = [word for word in words if word.lower() not in stop][:4]
    if not picked:
        picked = words[:4]
    title = " ".join(word.capitalize() for word in picked[:5]).strip()
    if not title:
        return "KahrabaIQ Chat"
    if any(word.lower() in {"power", "cost", "energy", "usage"} for word in picked):
        title = f"{title} Explanation" if "explanation" not in title.lower() else title
    return title[:60]


def preview_text(content: str, limit: int = 120) -> str:
    clean = " ".join(content.strip().split())
    return clean if len(clean) <= limit else f"{clean[: limit - 3]}..."


def sorted_chat_messages(messages: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    items = object_to_list(messages)
    items.sort(key=lambda item: as_number(item.get("created_at_ms")))
    if limit is not None and limit > 0:
        return items[-limit:]
    return items


def conversation_history_from_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for item in messages:
        role = str(item.get("role", "")).lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(first_present(item.get("content"), item.get("message"), default="")).strip()
        if not content:
            continue
        history.append({"role": role, "message": content[:2000]})
    return history


def require_chat_session_access(
    home_id: str,
    session_id: str,
    actor: AuthContext,
    *,
    allow_archived: bool = False,
) -> dict[str, Any]:
    session = as_dict(safe_get(chat_session_ref(home_id, session_id), {}))
    if not session:
        raise HTTPException(status_code=404, detail="Chat session does not exist.")
    if session.get("archived") is True and not allow_archived:
        raise HTTPException(status_code=404, detail="Chat session is archived.")
    created_by = str(session.get("created_by") or "")
    if actor.actor_type != "service" and actor.actor_role not in {"home_admin", "platform_admin"} and created_by != chat_actor_id(actor):
        raise HTTPException(status_code=403, detail="You do not have access to this chat session.")
    return session


def create_chat_session_record(
    home_id: str,
    actor: AuthContext,
    title: str | None = None,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    actual_session_id = session_id or f"chat_{timestamp_ms}"
    session = {
        "session_id": actual_session_id,
        "home_id": home_id,
        "title": sanitize_chat_title(title),
        "created_by": chat_actor_id(actor),
        "created_by_name": chat_actor_name(actor),
        "created_at_ms": timestamp_ms,
        "created_at_iso": iso_from_ms(timestamp_ms),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
        "last_message_preview": "",
        "message_count": 0,
        "archived": False,
        "archived_at_ms": None,
        "archived_at_iso": None,
    }
    safe_set(chat_session_ref(home_id, actual_session_id), session)
    audit_log(home_id, actor, "chat_session_created", "chat_session", actual_session_id)
    return session


def default_chat_session(home_id: str, actor: AuthContext) -> dict[str, Any]:
    session_id = f"chat_default_{re.sub(r'[^A-Za-z0-9_-]', '_', chat_actor_id(actor))}"
    session = as_dict(safe_get(chat_session_ref(home_id, session_id), {}))
    if session and session.get("archived") is not True:
        return session
    return create_chat_session_record(home_id, actor, "New Chat", session_id=session_id)


def call_ai_chat_service(home_id: str, request: ChatProxyRequest, history: list[dict[str, str]]) -> dict[str, Any]:
    ai_service_url = os.environ.get("AI_SERVICE_URL", "").strip().rstrip("/")
    if not ai_service_url:
        raise HTTPException(status_code=503, detail="AI_SERVICE_URL is not configured.")
    payload = {
        "message": request.message,
        "home_id": home_id,
        "home_name": request.home_name,
        "scenario_id": request.scenario_id,
        "scenario_name": request.scenario_name,
        "conversation_history": history,
    }
    headers = {}
    internal_token = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
    if internal_token:
        headers["X-Service-Token"] = internal_token
    try:
        response = requests.post(
            f"{ai_service_url}/chat/{home_id}",
            json=payload,
            headers=headers,
            timeout=45,
        )
        data = response.json() if response.content else {}
        if not response.ok:
            raise HTTPException(status_code=response.status_code, detail=data)
        return data
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"AI chat request failed: {error}") from error


def send_chat_session_message(
    home_id: str,
    session_id: str,
    request: ChatSessionMessageRequest,
    actor: AuthContext,
) -> dict[str, Any]:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty.")

    session = require_chat_session_access(home_id, session_id, actor)
    timestamp_ms = now_ms()
    user_message_id = f"msg_{timestamp_ms}_user"
    user_message = {
        "message_id": user_message_id,
        "session_id": session_id,
        "role": "user",
        "content": message,
        "created_by": chat_actor_id(actor),
        "created_at_ms": timestamp_ms,
        "created_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_set(f"{chat_messages_ref(home_id, session_id)}/{user_message_id}", user_message)

    recent_messages = sorted_chat_messages(
        as_dict(safe_get(chat_messages_ref(home_id, session_id), {})),
        limit=20,
    )
    history = conversation_history_from_messages(recent_messages)
    proxy_request = ChatProxyRequest(
        message=message,
        home_name=request.home_name,
        scenario_id=request.scenario_id,
        scenario_name=request.scenario_name,
        conversation_history=history,
    )
    ai_data = call_ai_chat_service(home_id, proxy_request, history)
    answer = str(ai_data.get("answer") or "No chatbot answer was returned.").strip()
    assistant_timestamp_ms = now_ms()
    assistant_message_id = f"msg_{assistant_timestamp_ms}_assistant"
    assistant_message = {
        "message_id": assistant_message_id,
        "session_id": session_id,
        "role": "assistant",
        "content": answer,
        "created_by": "assistant",
        "created_at_ms": assistant_timestamp_ms,
        "created_at_iso": iso_from_ms(assistant_timestamp_ms),
        "model": "gemini",
        "used_home_context": bool(ai_data.get("used_data", True)),
        "used_recent_history_count": len(history),
        "sources": ["dashboard", "alerts", "recommendations", "ai_latest"],
    }
    safe_set(f"{chat_messages_ref(home_id, session_id)}/{assistant_message_id}", assistant_message)

    all_messages = sorted_chat_messages(as_dict(safe_get(chat_messages_ref(home_id, session_id), {})))
    next_title = str(session.get("title") or "New Chat")
    if next_title.strip().lower() == "new chat":
        next_title = title_from_message(message)
    session_update = {
        "title": next_title,
        "updated_at_ms": assistant_timestamp_ms,
        "updated_at_iso": iso_from_ms(assistant_timestamp_ms),
        "last_message_preview": preview_text(answer),
        "message_count": len(all_messages),
    }
    safe_update(chat_session_ref(home_id, session_id), session_update)
    updated_session = {**session, **session_update}
    audit_log(
        home_id,
        actor,
        "chat_message_sent",
        "chat_session",
        session_id,
        {"user_message_id": user_message_id, "assistant_message_id": assistant_message_id},
    )
    return {
        **ai_data,
        "answer": answer,
        "session": updated_session,
        "user_message": user_message,
        "assistant_message": assistant_message,
    }


@app.get("/api/home/{home_id}/chat/sessions")
def list_chat_sessions(
    home_id: str,
    actor: AuthContext = Depends(require_home_permission("can_use_ai_chat")),
) -> dict[str, Any]:
    sessions = object_to_list(safe_get(f"/homes/{home_id}/chat/sessions", {}))
    actor_id = chat_actor_id(actor)
    visible = [
        item
        for item in sessions
        if item.get("archived") is not True
        and (actor.actor_role in {"home_admin", "platform_admin"} or str(item.get("created_by")) == actor_id)
    ]
    visible.sort(key=lambda item: as_number(item.get("updated_at_ms")), reverse=True)
    return {"home_id": home_id, "count": len(visible), "sessions": visible}


@app.post("/api/home/{home_id}/chat/sessions")
def create_chat_session(
    home_id: str,
    request: ChatSessionCreateRequest,
    actor: AuthContext = Depends(require_home_permission("can_use_ai_chat")),
) -> dict[str, Any]:
    session = create_chat_session_record(home_id, actor, request.title or "New Chat")
    return {"home_id": home_id, "session": session}


@app.get("/api/home/{home_id}/chat/sessions/{session_id}/messages")
def get_chat_session_messages(
    home_id: str,
    session_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    actor: AuthContext = Depends(require_home_permission("can_use_ai_chat")),
) -> dict[str, Any]:
    require_chat_session_access(home_id, session_id, actor, allow_archived=True)
    messages = sorted_chat_messages(as_dict(safe_get(chat_messages_ref(home_id, session_id), {})), limit=limit)
    return {"home_id": home_id, "session_id": session_id, "count": len(messages), "messages": messages}


@app.post("/api/home/{home_id}/chat/sessions/{session_id}/message")
def send_chat_message_to_session(
    home_id: str,
    session_id: str,
    request: ChatSessionMessageRequest,
    actor: AuthContext = Depends(require_home_permission("can_use_ai_chat")),
) -> dict[str, Any]:
    return send_chat_session_message(home_id, session_id, request, actor)


@app.patch("/api/home/{home_id}/chat/sessions/{session_id}")
def rename_chat_session(
    home_id: str,
    session_id: str,
    request: ChatSessionRenameRequest,
    actor: AuthContext = Depends(require_home_permission("can_use_ai_chat")),
) -> dict[str, Any]:
    session = require_chat_session_access(home_id, session_id, actor)
    timestamp_ms = now_ms()
    update = {
        "title": sanitize_chat_title(request.title),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_update(chat_session_ref(home_id, session_id), update)
    audit_log(home_id, actor, "chat_session_renamed", "chat_session", session_id)
    return {"home_id": home_id, "session": {**session, **update}}


@app.delete("/api/home/{home_id}/chat/sessions/{session_id}")
def archive_chat_session(
    home_id: str,
    session_id: str,
    actor: AuthContext = Depends(require_home_permission("can_use_ai_chat")),
) -> dict[str, Any]:
    session = require_chat_session_access(home_id, session_id, actor)
    timestamp_ms = now_ms()
    update = {
        "archived": True,
        "archived_at_ms": timestamp_ms,
        "archived_at_iso": iso_from_ms(timestamp_ms),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_update(chat_session_ref(home_id, session_id), update)
    audit_log(home_id, actor, "chat_session_archived", "chat_session", session_id)
    return {"home_id": home_id, "session": {**session, **update}, "archived": True}


@app.post("/api/home/{home_id}/chat/sessions/{session_id}/clear")
def clear_chat_session_messages(
    home_id: str,
    session_id: str,
    actor: AuthContext = Depends(require_home_permission("can_use_ai_chat")),
) -> dict[str, Any]:
    session = require_chat_session_access(home_id, session_id, actor)
    timestamp_ms = now_ms()
    messages = as_dict(safe_get(chat_messages_ref(home_id, session_id), {}))
    if messages:
        safe_set(f"{chat_session_ref(home_id, session_id)}/archived_messages/messages_{timestamp_ms}", messages)
        safe_set(chat_messages_ref(home_id, session_id), None)
    update = {
        "last_message_preview": "",
        "message_count": 0,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_update(chat_session_ref(home_id, session_id), update)
    audit_log(home_id, actor, "chat_session_cleared", "chat_session", session_id)
    return {"home_id": home_id, "session": {**session, **update}, "cleared": True}


@app.post("/api/home/{home_id}/chat")
def chat_with_ai(
    home_id: str,
    request: ChatProxyRequest,
    actor: AuthContext = Depends(require_home_permission("can_use_ai_chat")),
) -> dict[str, Any]:
    session = default_chat_session(home_id, actor)
    session_request = ChatSessionMessageRequest(
        message=request.message,
        home_name=request.home_name,
        scenario_id=request.scenario_id,
        scenario_name=request.scenario_name,
    )
    return send_chat_session_message(home_id, str(session["session_id"]), session_request, actor)


@app.post("/api/home/{home_id}/ai/predict", dependencies=[Depends(require_home_role("admin"))])
def trigger_ai_prediction(home_id: str) -> dict[str, Any]:
    ai_service_url = os.environ.get("AI_SERVICE_URL", "").strip().rstrip("/")
    if not ai_service_url:
        return {
            "success": False,
            "home_id": home_id,
            "message": "AI_SERVICE_URL is not configured.",
        }

    try:
        headers = {}
        internal_token = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
        if internal_token:
            headers["X-Service-Token"] = internal_token
        response = requests.post(f"{ai_service_url}/predict/{home_id}", headers=headers, timeout=30)
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
    dependencies=[Depends(require_home_role("admin"))],
)
def run_scenario(home_id: str, scenario_id: str) -> ScenarioRunResponse:
    timestamp_ms = now_ms()
    request_id = f"scenario_{timestamp_ms}"
    scenario_request = {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
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
