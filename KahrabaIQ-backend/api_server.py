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
import main as ai_engine
from aws_cloud_store import (
    ACTIVE_COMMAND_STATUSES,
    COMMAND_STATUS_CANCELLED,
    COMMAND_STATUS_CLAIMED,
    COMMAND_STATUS_EXECUTING,
    COMMAND_STATUS_EXPIRED,
    COMMAND_STATUS_FAILED,
    COMMAND_STATUS_PENDING,
    COMMAND_STATUS_SUCCEEDED,
    app_delete_tree,
    app_get_path,
    app_set_path,
    app_update_path,
    create_remote_command,
    create_iot_websocket_config,
    get_ai_latest,
    latest_summary,
    find_remote_command,
    normalize_command_status,
    query_ai_history,
    query_ai_notifications,
    query_summaries_between,
    query_recent_remote_commands,
    store_ai_result,
    update_remote_command,
)


load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
load_dotenv()

SERVICE_NAME = "smart_energy_api"
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "aws").strip().lower()
BAHRAIN_TZ = ZoneInfo(TIMEZONE)
DEFAULT_HOME_ID = os.environ.get("DEFAULT_HOME_ID", "home_001")
HOME_MEMBER_LIMIT = int(os.environ.get("HOME_MEMBER_LIMIT", "3"))
PAIRING_TOKEN_TTL_MS = int(os.environ.get("PAIRING_TOKEN_TTL_SECONDS", "900")) * 1000
HOME_INVITE_TTL_MS = int(os.environ.get("HOME_INVITE_TTL_SECONDS", str(7 * 24 * 60 * 60))) * 1000
KIOSK_SESSION_TTL_SECONDS = int(os.environ.get("KIOSK_SESSION_TTL_SECONDS", "600"))
KIOSK_COMMAND_TTL_SECONDS = int(os.environ.get("KIOSK_COMMAND_TTL_SECONDS", "300"))
KIOSK_SESSION_SECRET = os.environ.get("KIOSK_SESSION_SECRET") or os.environ.get("INTERNAL_SERVICE_TOKEN") or "dev-kiosk-session-secret"
KIOSK_ALLOWED_COMMANDS = {"provision_esp32", "discover_esp32", "reset_esp32"}
MATTER_DEVICE_IDS = {"matter_socket_switch", "matter_ac_switch"}
DEVICE_ALIASES = {
    "ac_breaker": "breaker_01",
    "socket_breaker": "breaker_02",
}
CONTROLLABLE_DEVICES = {"breaker_01", "breaker_02", *DEVICE_ALIASES, *MATTER_DEVICE_IDS}
VALID_COMMANDS = {"turn_on", "turn_off"}
DEVICE_STALE_AFTER_MS = 45 * 1000
PI_OFFLINE_AFTER_MS = int(os.environ.get("PI_OFFLINE_AFTER_SECONDS", "120")) * 1000
HA_SYNC_INTERVAL_SECONDS = int(os.environ.get("HA_SYNC_INTERVAL_SECONDS", "30"))
AI_AUTO_PREDICT_ENABLED = os.environ.get("AI_AUTO_PREDICT_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
# AI has three cadences:
# 1. immediate rule alerts run when prediction is requested or important state is handled;
# 2. lightweight routine/anomaly checks can run every 5-10 minutes for demo/normal use;
# 3. full ML prediction should run hourly after a new hourly summary exists.
AI_ROUTINE_CHECK_INTERVAL_SECONDS = max(
    60,
    int(os.environ.get("AI_ROUTINE_CHECK_INTERVAL_SECONDS", os.environ.get("AI_PREDICTION_INTERVAL_SECONDS", "600"))),
)
AI_FULL_PREDICTION_INTERVAL_SECONDS = max(
    300,
    int(os.environ.get("AI_FULL_PREDICTION_INTERVAL_SECONDS", "3600")),
)
AI_PREDICTION_INTERVAL_SECONDS = AI_ROUTINE_CHECK_INTERVAL_SECONDS
AI_PREDICTION_INITIAL_DELAY_SECONDS = max(0, int(os.environ.get("AI_PREDICTION_INITIAL_DELAY_SECONDS", "30")))
AI_PREDICTION_HOME_IDS = [
    item.strip()
    for item in os.environ.get("AI_PREDICTION_HOME_IDS", DEFAULT_HOME_ID).split(",")
    if item.strip()
]
USE_HOME_ASSISTANT_FOR_BREAKERS = os.environ.get("USE_HOME_ASSISTANT_FOR_BREAKERS", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
USE_TUYA_CLOUD_FOR_BREAKERS = os.environ.get("USE_TUYA_CLOUD_FOR_BREAKERS", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
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
    "breaker_01": "AC Breaker",
    "breaker_02": "Socket Breaker",
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


class AiScenarioPredictRequest(BaseModel):
    scenario_id: str
    scenario_name: str
    scenario_description: str | None = None
    room: dict[str, Any] = Field(default_factory=dict)
    energy: dict[str, Any] = Field(default_factory=dict)
    devices: dict[str, Any] = Field(default_factory=dict)
    occupancy: dict[str, Any] = Field(default_factory=dict)
    recent_history: dict[str, Any] = Field(default_factory=dict)
    routine_context: dict[str, Any] = Field(default_factory=dict)
    store: bool = False


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
    context: dict[str, Any] | None = None
    conversation_history: list[dict[str, Any]] | None = None


class ChatSessionCreateRequest(BaseModel):
    title: str | None = None
    mode: str | None = None
    scenario_id: str | None = None
    scenario_name: str | None = None


class ChatSessionRenameRequest(BaseModel):
    title: str


class ChatSessionMessageRequest(BaseModel):
    message: str
    home_name: str | None = None
    mode: str | None = None
    scenario_id: str | None = None
    scenario_name: str | None = None
    context: dict[str, Any] | None = None


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
_ai_prediction_scheduler_started = False
_ai_last_full_prediction_ms_by_home: dict[str, int] = {}


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
    start_ai_prediction_scheduler()


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


def safe_delete_tree(path: str) -> int:
    try:
        return app_delete_tree(path)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to delete DynamoDB path tree {path}: {error}",
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
            "Home Assistant switch was not found.",
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


def home_invited_user_count(home_id: str) -> int:
    return home_member_count(home_id, roles={"member", "viewer"})


def remaining_home_invite_slots(home_id: str) -> int:
    return max(0, HOME_MEMBER_LIMIT - home_invited_user_count(home_id))


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


def remove_home_from_user_profile(uid: str, home_id: str) -> None:
    profile = as_dict(safe_get(f"/users/{uid}", {}))
    user_homes = as_dict(profile.get("homes"))
    user_homes.pop(home_id, None)
    updates: dict[str, Any] = {
        "homes": user_homes,
        "updated_at_ms": now_ms(),
        "updated_at_iso": iso_from_ms(now_ms()),
    }
    if profile.get("default_home_id") == home_id:
        updates["default_home_id"] = next(iter(user_homes), None)
    safe_set(f"/users/{uid}/homes/{home_id}", None)
    safe_update(f"/users/{uid}", updates)


def remove_member_from_home(home_id: str, uid: str, actor: AuthContext, *, allow_last_admin: bool = False) -> dict[str, Any]:
    existing = as_dict(safe_get(f"/homes/{home_id}/members/{uid}", {}))
    if not existing:
        raise HTTPException(status_code=404, detail="Member does not exist.")
    if not allow_last_admin and validate_role(str(existing.get("role", "viewer"))) == "home_admin" and admin_count(home_id) <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove the last admin from the home.")
    safe_set(f"/homes/{home_id}/members/{uid}", None)
    remove_home_from_user_profile(uid, home_id)
    audit_log(home_id, actor, "member_removed", "member", uid)
    return {"success": True, "home_id": home_id, "uid": uid}


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


def command_status_payload(item: dict[str, Any]) -> dict[str, Any]:
    status = normalize_command_status(item.get("status"))
    return {
        **item,
        "status": status,
        "is_final": status not in ACTIVE_COMMAND_STATUSES,
    }


def member_user_ids(home_id: str) -> list[str]:
    user_ids = []
    for uid, raw_member in as_dict(safe_get(f"/homes/{home_id}/members", {})).items():
        member = as_dict(raw_member)
        if member.get("status") == "removed":
            continue
        normalized_uid = str(member.get("uid") or uid).strip()
        if normalized_uid:
            user_ids.append(normalized_uid)
    return user_ids


def user_notification_sort_key(item: dict[str, Any]) -> int:
    return int(
        first_present(
            item.get("created_at_ms"),
            item.get("timestamp_ms"),
            item.get("updated_at_ms"),
            0,
        )
        or 0
    )


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
    active_alerts = [
        alert
        for alert in request.alerts
        if isinstance(alert, dict)
        and str(first_present(alert.get("status"), alert.get("state"), "OPEN")).upper()
        not in {"RESOLVED", "AUTO_RESOLVED", "CLEARED"}
    ][:20]
    latest = {
        "home_id": home_id,
        "pi_id": pi_id,
        "dashboard": request.dashboard,
        "room": request.room,
        "devices": request.devices,
        "energy": request.energy,
        "commands": request.commands,
        "alerts": active_alerts,
        "notifications": [],
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
    if request.occupancy:
        safe_update(f"/homes/{home_id}/occupancy/room1", request.occupancy)
    if request.safety:
        smoke_state = as_dict(request.safety.get("smoke_state"))
        emergency_mode = as_dict(request.safety.get("emergency_mode"))
        if smoke_state:
            safe_update(f"/homes/{home_id}/safety/smoke_state", smoke_state)
        if emergency_mode:
            safe_update(f"/homes/{home_id}/safety/emergency_mode", emergency_mode)
    if request.alerts:
        sync_pi_alerts(home_id, request.alerts, timestamp_ms=timestamp_ms)
    resolve_smoke_emergency_if_clear(home_id)
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
        commands = []
        for command in query_recent_remote_commands(home_id, limit=limit):
            sync_remote_command_projection(home_id, command)
            if normalize_command_status(command.get("status")) == COMMAND_STATUS_PENDING:
                commands.append(command_status_payload(command))
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
    if normalize_command_status(command.get("status")) == COMMAND_STATUS_EXPIRED:
        raise HTTPException(status_code=409, detail="Remote command expired before it could be claimed.")
    if normalize_command_status(command.get("status")) != COMMAND_STATUS_PENDING:
        raise HTTPException(status_code=409, detail="Remote command is no longer pending.")
    timestamp_ms = now_ms()
    try:
        updated = update_remote_command(
            home_id,
            command_id,
            {
                "status": COMMAND_STATUS_CLAIMED,
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
    sync_remote_command_projection(home_id, updated)
    return {"success": True, "home_id": home_id, "pi_id": pi_id, "command": command_status_payload(updated)}


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
        "status": COMMAND_STATUS_SUCCEEDED if success else COMMAND_STATUS_FAILED,
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
    sync_remote_command_projection(home_id, updated)
    return {"success": True, "home_id": home_id, "pi_id": pi_id, "command": command_status_payload(updated)}


@app.post("/api/pi/{pi_id}/remote-commands/{command_id}/executing")
def pi_remote_command_executing(
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
    current_status = normalize_command_status(command.get("status"))
    if current_status not in {COMMAND_STATUS_CLAIMED, COMMAND_STATUS_EXECUTING}:
        raise HTTPException(status_code=409, detail="Remote command cannot move to executing from its current state.")
    timestamp_ms = now_ms()
    try:
        updated = update_remote_command(
            home_id,
            command_id,
            {
                "status": COMMAND_STATUS_EXECUTING,
                "startedAtMs": timestamp_ms,
                "started_at_ms": timestamp_ms,
                "startedAt": iso_from_ms(timestamp_ms),
                "started_at_iso": iso_from_ms(timestamp_ms),
            },
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Remote command update failed: {error}") from error
    sync_remote_command_projection(home_id, updated)
    return {"success": True, "home_id": home_id, "pi_id": pi_id, "command": command_status_payload(updated)}


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
    remaining_slots = remaining_home_invite_slots(home_id)
    if remaining_slots <= 0:
        raise HTTPException(status_code=409, detail=f"This home already has the maximum {HOME_MEMBER_LIMIT} invited users.")
    if request.max_uses > remaining_slots:
        raise HTTPException(status_code=409, detail=f"This home only has {remaining_slots} invite slot{'s' if remaining_slots != 1 else ''} remaining.")
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
        "role": role,
        "max_uses": request.max_uses,
        "remaining_slots": remaining_slots - request.max_uses,
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
    if home_invited_user_count(home_id) >= HOME_MEMBER_LIMIT:
        raise HTTPException(status_code=409, detail=f"This home already has the maximum {HOME_MEMBER_LIMIT} invited users.")
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
    for home in homes:
        home_id = str(home.get("home_id") or home.get("id") or "")
        if home_id:
            home["member_count"] = home_member_count(home_id)
    return {"success": True, "count": len(homes), "homes": homes}


@app.get("/api/admin/homes/{home_id}")
def admin_home_detail(home_id: str, actor: AuthContext = Depends(require_platform_admin)) -> dict[str, Any]:
    home = as_dict(safe_get(f"/homes/{home_id}", {}))
    if not home:
        raise HTTPException(status_code=404, detail="Home does not exist.")
    pi_id = str(home.get("pi_id") or "")
    pi = as_dict(safe_get(f"/pis/{pi_id}", {})) if pi_id else {}
    if pi:
        pi.pop("token_hash", None)
    members = object_to_list(safe_get(f"/homes/{home_id}/members", {}))
    invites = [invite for invite in object_to_list(safe_get("/home_invites", {})) if str(invite.get("home_id") or "") == home_id]
    for invite in invites:
        invite.pop("token_hash", None)
    return {"success": True, "home_id": home_id, "home": {"home_id": home_id, **home}, "pi": pi, "members": members, "invites": invites}


def queue_pi_reset_pairing(pi_id: str, home_id: str, actor: AuthContext) -> str:
    timestamp_ms = now_ms()
    command_id = f"admin_reset_{timestamp_ms}_{secrets.token_hex(3)}"
    safe_set(
        f"/pi_commands/{pi_id}/{command_id}",
        {
            "id": command_id,
            "command_id": command_id,
            "pi_id": pi_id,
            "home_id": home_id,
            "command": "reset_pairing",
            "payload": {"reason": "home_deleted_by_platform_admin", "home_id": home_id},
            "status": "pending",
            "created_by": actor.actor_id,
            "created_at_ms": timestamp_ms,
            "created_at_iso": iso_from_ms(timestamp_ms),
            "expires_at_ms": timestamp_ms + (7 * 24 * 60 * 60 * 1000),
        },
    )
    return command_id


@app.delete("/api/admin/homes/{home_id}/members/{uid}")
def admin_remove_home_member(home_id: str, uid: str, actor: AuthContext = Depends(require_platform_admin)) -> dict[str, Any]:
    if not home_exists(home_id):
        raise HTTPException(status_code=404, detail="Home does not exist.")
    return remove_member_from_home(home_id, uid, actor, allow_last_admin=True)


@app.delete("/api/admin/homes/{home_id}")
def admin_delete_home(home_id: str, actor: AuthContext = Depends(require_platform_admin)) -> dict[str, Any]:
    home = as_dict(safe_get(f"/homes/{home_id}", {}))
    if not home:
        raise HTTPException(status_code=404, detail="Home does not exist.")
    pi_id = str(home.get("pi_id") or "")
    removed_user_count = 0
    member_uids = {str(uid) for uid in as_dict(safe_get(f"/homes/{home_id}/members", {})).keys()}
    for raw_user in object_to_list(safe_get("/users", {})):
        uid = str(raw_user.get("uid") or raw_user.get("id") or "")
        if not uid:
            continue
        if uid in member_uids or home_id in as_dict(raw_user.get("homes")) or raw_user.get("default_home_id") == home_id:
            remove_home_from_user_profile(uid, home_id)
            removed_user_count += 1

    removed_invite_count = 0
    for invite in object_to_list(safe_get("/home_invites", {})):
        invite_id = str(invite.get("invite_id") or invite.get("id") or "")
        if invite_id and str(invite.get("home_id") or "") == home_id:
            safe_set(f"/home_invites/{invite_id}", None)
            removed_invite_count += 1

    removed_pairing_token_count = 0
    if pi_id:
        for token in object_to_list(safe_get("/pi_pairing_tokens", {})):
            token_id = str(token.get("token_id") or token.get("id") or "")
            if token_id and str(token.get("pi_id") or "") == pi_id:
                safe_set(f"/pi_pairing_tokens/{token_id}", None)
                removed_pairing_token_count += 1

    audit_log(home_id, actor, "home_deleted", "home", home_id, {"pi_id": pi_id})
    deleted_path_count = safe_delete_tree(f"/homes/{home_id}")
    reset_command_id = None
    if pi_id:
        pi = as_dict(safe_get(f"/pis/{pi_id}", {}))
        timestamp_ms = now_ms()
        pi_record = {key: value for key, value in pi.items() if key not in {"home_id", "paired_by_uid", "paired_at_ms", "paired_at_iso"}}
        safe_set(
            f"/pis/{pi_id}",
            {
                **pi_record,
                "pi_id": pi_id,
                "status": "unpaired",
                "online_status": pi.get("online_status"),
                "unpaired_reason": "home_deleted_by_platform_admin",
                "unpaired_at_ms": timestamp_ms,
                "unpaired_at_iso": iso_from_ms(timestamp_ms),
                "updated_at_ms": timestamp_ms,
                "updated_at_iso": iso_from_ms(timestamp_ms),
            },
        )
        reset_command_id = queue_pi_reset_pairing(pi_id, home_id, actor)

    return {
        "success": True,
        "home_id": home_id,
        "pi_id": pi_id or None,
        "reset_command_id": reset_command_id,
        "deleted_path_count": deleted_path_count,
        "removed_user_count": removed_user_count,
        "removed_invite_count": removed_invite_count,
        "removed_pairing_token_count": removed_pairing_token_count,
        "message": "Home deleted. Its Pi will return to pairing mode when online." if pi_id else "Home deleted.",
    }


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
                "status": "AUTO_RESOLVED",
                "event": "auto_resolved",
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


def create_notification_record(
    home_id: str,
    title: str,
    body: str,
    *,
    notification_type: str = "critical_alert",
    alert_type: str | None = None,
    severity: str = "critical",
    alert_id: str | None = None,
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    notification_id = f"notif_{timestamp_ms}"
    notification = {
        "notification_id": notification_id,
        "type": notification_type,
        "alert_type": alert_type,
        "severity": severity,
        "title": title,
        "body": body,
        "home_id": home_id,
        "alert_id": alert_id,
        "room_id": "room1",
        "read": False,
        "delivered": False,
        "created_at_ms": timestamp_ms,
        "created_at_iso": iso_from_ms(timestamp_ms),
        "timezone": TIMEZONE,
    }
    safe_set(f"/homes/{home_id}/notifications/{notification_id}", notification)
    for user_id in member_user_ids(home_id):
        safe_set(
            f"/users/{user_id}/notifications/{notification_id}",
            {
                **notification,
                "user_id": user_id,
            },
        )
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


def normalize_alert_status(status: str | None, *, default: str = "OPEN") -> str:
    normalized = str(status or "").strip().upper()
    aliases = {
        "ACTIVE": "OPEN",
        "OPEN": "OPEN",
        "ACK": "ACKNOWLEDGED",
        "ACKNOWLEDGED": "ACKNOWLEDGED",
        "RESOLVED": "RESOLVED",
        "AUTO_RESOLVED": "AUTO_RESOLVED",
    }
    return aliases.get(normalized, default)


def normalize_alert_severity(severity: str | None) -> str:
    normalized = str(severity or "").strip().lower()
    if normalized in {"critical", "warning", "info"}:
        return normalized
    if normalized in {"high", "emergency"}:
        return "critical"
    if normalized in {"medium", "warn"}:
        return "warning"
    return "info"


def cloud_alert_record(home_id: str, alert: dict[str, Any], *, timestamp_ms: int) -> dict[str, Any]:
    alert_id = str(first_present(alert.get("alert_id"), alert.get("id"), alert.get("alert_key"), "")).strip()
    alert_type = str(first_present(alert.get("alert_type"), alert.get("type"), alert.get("category"), "unknown")).strip().lower()
    message = str(first_present(alert.get("message"), alert.get("body"), alert.get("title"), "System alert")).strip()
    title = str(first_present(alert.get("title"), alert.get("message"), "System alert")).strip()
    return {
        **alert,
        "alert_id": alert_id,
        "home_id": home_id,
        "alert_type": alert_type,
        "title": title,
        "message": message,
        "severity": normalize_alert_severity(first_present(alert.get("severity"), alert.get("level"), "warning")),
        "status": normalize_alert_status(alert.get("status"), default="OPEN"),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": iso_from_ms(timestamp_ms),
        "last_seen_at_ms": timestamp_ms,
        "last_seen_at_iso": iso_from_ms(timestamp_ms),
        "created_at_ms": as_number(first_present(alert.get("created_at_ms"), alert.get("timestamp_ms"), timestamp_ms)),
        "created_at_iso": first_present(alert.get("created_at_iso"), alert.get("timestamp_iso"), iso_from_ms(timestamp_ms)),
        "timestamp_ms": as_number(first_present(alert.get("timestamp_ms"), timestamp_ms)),
        "timestamp_iso": first_present(alert.get("timestamp_iso"), iso_from_ms(timestamp_ms)),
        "timezone": TIMEZONE,
    }


def upsert_cloud_alert_from_pi(home_id: str, alert: dict[str, Any], *, timestamp_ms: int) -> dict[str, Any]:
    normalized = cloud_alert_record(home_id, alert, timestamp_ms=timestamp_ms)
    alert_id = normalized["alert_id"]
    if not alert_id:
        return normalized
    path = f"/homes/{home_id}/alerts/active/{alert_id}"
    existing = as_dict(safe_get(path, {}))
    if existing:
        merged = {
            **existing,
            **normalized,
            "status": "OPEN" if normalize_alert_status(existing.get("status")) != "ACKNOWLEDGED" else "ACKNOWLEDGED",
            "created_at_ms": existing.get("created_at_ms") or normalized.get("created_at_ms"),
            "created_at_iso": existing.get("created_at_iso") or normalized.get("created_at_iso"),
        }
        safe_set(path, merged)
        return merged

    safe_set(path, normalized)
    history_id = f"alert_{timestamp_ms}_{alert_id}"
    safe_set(
        f"/homes/{home_id}/alerts/history/{history_id}",
        {
            **normalized,
            "event": "created",
        },
    )
    if normalized["severity"] == "critical":
        create_notification_record(
            home_id,
            normalized["title"],
            normalized["message"],
            notification_type="critical_alert",
            alert_type=normalized["alert_type"],
            severity=normalized["severity"],
            alert_id=alert_id,
        )
    return normalized


def sync_pi_alerts(home_id: str, alerts: list[dict[str, Any]], *, timestamp_ms: int) -> dict[str, dict[str, Any]]:
    active: dict[str, dict[str, Any]] = {}
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        normalized = upsert_cloud_alert_from_pi(home_id, alert, timestamp_ms=timestamp_ms)
        alert_id = str(normalized.get("alert_id") or "").strip()
        if alert_id:
            active[alert_id] = normalized
    return active


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
    default_control_method = (
        "home_assistant"
        if device_id.startswith("breaker_") and USE_HOME_ASSISTANT_FOR_BREAKERS
        else "tuya_cloud"
        if device_id.startswith("breaker_") and USE_TUYA_CLOUD_FOR_BREAKERS
        else ""
    )
    control_method = str(raw.get("control_method") or default_control_method).lower()
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
    if is_home_assistant_device and online is not False:
        is_stale = False
    last_seen_age_seconds = (
        round(max(0, now_ms() - int(last_seen_ms)) / 1000, 3)
        if isinstance(last_seen_ms, (int, float)) and int(last_seen_ms) > 0
        else None
    )
    status_label = "offline" if online is False else "stale" if is_stale else "online"

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
        "status_label": status_label,
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
        "last_seen_age_seconds": last_seen_age_seconds,
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
    canonical_ai_latest = as_dict(get_ai_latest(home_id))

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
        "canonical_ai_latest": canonical_ai_latest,
        "backend_active_alerts": as_dict(backend.get("active_alerts")),
        "backend_recommendations": as_dict(backend.get("recommendations")),
        "backend_latest_prediction": as_dict(backend_ai.get("latest_prediction")),
        "backend_current_total": as_dict(backend_energy.get("current_total")),
        "backend_branches": as_dict(backend_energy.get("branches")),
        "backend_device_health": as_dict(backend.get("device_health")),
        "occupancy_room1": as_dict(as_dict(home.get("occupancy")).get("room1")),
        "safety": as_dict(home.get("safety")),
    }


def build_hub_status(bundle: dict[str, Any]) -> dict[str, Any]:
    home = as_dict(bundle.get("home"))
    latest_state = as_dict(bundle.get("latest_state"))
    pi_id = str(first_present(home.get("pi_id"), latest_state.get("pi_id"), default="") or "")
    pi = as_dict(safe_get(f"/pis/{pi_id}", {})) if pi_id else {}
    last_seen_ms = first_present(
        pi.get("last_heartbeat_at_ms"),
        pi.get("last_state_sync_at_ms"),
        pi.get("last_seen_at_ms"),
        latest_state.get("updated_at_ms"),
        latest_state.get("timestamp_ms"),
    )
    age_seconds = (
        round(max(0, now_ms() - int(last_seen_ms)) / 1000, 3)
        if isinstance(last_seen_ms, (int, float)) and int(last_seen_ms) > 0
        else None
    )
    online = age_seconds is not None and age_seconds * 1000 <= PI_OFFLINE_AFTER_MS
    return {
        "pi_id": pi_id or None,
        "online": online,
        "stale": not online,
        "status_label": "online" if online else "offline",
        "last_seen_ms": last_seen_ms,
        "last_seen_iso": iso_from_ms(last_seen_ms),
        "last_seen_age_seconds": age_seconds,
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


def build_ai(
    bundle: dict[str, Any],
    *,
    smoke_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest = {
        **bundle["ai_latest"],
        **bundle["backend_latest_prediction"],
        **bundle["backend_dashboard_ai"],
        **bundle["canonical_ai_latest"],
    }
    if not latest:
        return {}
    ai_ctx = ai_latest_context(latest)
    smoke_ctx = smoke_context or {}
    if ai_ctx.get("stale") is True:
        print(
            f"[KahrabaIQ AI DASHBOARD] home_ai_latest_stale age_seconds={ai_ctx.get('age_seconds')} "
            f"source={ai_ctx.get('source')} smoke_status={smoke_ctx.get('status')}"
        )
        return stale_ai_dashboard(ai_ctx, smoke_ctx)
    if smoke_ctx and smoke_ctx.get("active") is not True and item_mentions_smoke_or_gas(latest):
        print(
            f"[KahrabaIQ AI DASHBOARD] suppressing_stale_smoke_ai "
            f"ai_age_seconds={ai_ctx.get('age_seconds')} smoke_status={smoke_ctx.get('status')} "
            f"sensor_age_seconds={smoke_ctx.get('age_seconds')}"
        )
        return stale_ai_dashboard(ai_ctx, smoke_ctx)
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
        "ai_status_summary": first_present(
            latest.get("ai_status_summary"),
            latest.get("explanation"),
            latest.get("summary"),
            default="AI is reviewing current energy use.",
        ),
        "ai_action_title": first_present(
            latest.get("ai_action_title"),
            latest.get("recommendation_type"),
            recommendation.get("value"),
            default="Review insight",
        ),
        "recommended_action": first_present(
            latest.get("recommendation_type"),
            recommendation.get("value"),
            nested(latest, "control_suggestion", "action"),
        ),
        "control_suggestion": latest.get("control_suggestion"),
        "updated_at": first_present(latest.get("updated_at"), latest.get("created_at")),
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
    requested_device_id = request.device_id.strip()
    device_id = DEVICE_ALIASES.get(requested_device_id, requested_device_id)
    if command not in VALID_COMMANDS:
        raise HTTPException(status_code=400, detail="Command must be turn_on or turn_off.")
    if requested_device_id not in CONTROLLABLE_DEVICES:
        raise HTTPException(status_code=400, detail="Unsupported device_id.")
    device = as_dict(safe_get(f"/homes/{home_id}/devices/{device_id}", {}))
    if not device:
        raise HTTPException(status_code=404, detail="Device does not exist.")
    result = queue_remote_device_command(
        home_id,
        device_id,
        device,
        DeviceCommandRequest(
            command=command,
            requested_by=request.requested_by,
            reason=request.reason,
            source=request.source,
            emergency=request.emergency,
            alert_id=request.alert_id,
        ),
        command,
        request.requested_by,
    )
    command_record = find_remote_command(home_id, str(result.command_id or ""))

    return {
        "success": True,
        "status": COMMAND_STATUS_PENDING,
        "message": "Command queued for the Raspberry Pi.",
        "command_id": result.command_id,
        "device_id": device_id,
        "command": command,
        "target_state": command_record.get("target_state") or command_record.get("targetState"),
        "command_record": command_status_payload(command_record),
    }


def summary_energy_value(summary: dict[str, Any]) -> float:
    value = summary_energy_raw_value(summary)
    return float(value or 0)


def summary_energy_raw_value(summary: dict[str, Any]) -> float | None:
    energy = as_dict(summary.get("energy"))
    raw = first_present(
        energy.get("total_estimated_energy_kWh"),
        energy.get("total_energy_kWh"),
        energy.get("total_energy_kwh"),
        summary.get("total_estimated_energy_kWh"),
        summary.get("total_energy_kWh"),
        summary.get("total_energy_kwh"),
        summary.get("totalEnergyKwh"),
    )
    if raw is None:
        return None
    return as_number(raw)


def summary_start_value(summary: dict[str, Any]) -> int:
    return int(
        as_number(
            first_present(
                summary.get("startAtMs"),
                summary.get("start_at_ms"),
                summary.get("hour_start"),
                summary.get("timestamp_ms"),
                summary.get("updated_at_ms"),
            ),
            0,
        )
        or 0
    )


def summary_command_success_rate(summaries: list[dict[str, Any]]) -> float | None:
    succeeded = 0
    failed = 0
    for summary in summaries:
        by_status = as_dict(as_dict(summary.get("commandSummary")).get("byStatus"))
        for status, count in by_status.items():
            normalized = normalize_command_status(status, default=str(status).upper())
            amount = int(as_number(count, 0) or 0)
            if normalized == COMMAND_STATUS_SUCCEEDED:
                succeeded += amount
            elif normalized == COMMAND_STATUS_FAILED:
                failed += amount
    total = succeeded + failed
    if total <= 0:
        return None
    return round((succeeded / total) * 100, 1)


def stored_monthly_energy_summary(
    *sources: dict[str, Any],
    tariff: float = 0.029,
) -> dict[str, Any]:
    for source in sources:
        source = as_dict(source)
        month_kwh = first_present(
            source.get("month_kwh"),
            source.get("monthly_kwh"),
            source.get("current_month_kwh"),
            source.get("energyMonth"),
            source.get("monthKwh"),
        )
        if month_kwh is None:
            continue
        month_available = normalize_bool(
            first_present(source.get("month_data_available"), source.get("monthDataAvailable"))
        )
        if month_available is False:
            continue
        month_cost = first_present(
            source.get("month_cost_bhd"),
            source.get("monthly_cost_bhd"),
            source.get("current_month_cost_bhd"),
            source.get("costMonth"),
            source.get("monthCostBhd"),
        )
        return {
            "month_kwh": as_number(month_kwh),
            "month_cost_bhd": as_number(month_cost)
            if month_cost is not None
            else round(as_number(month_kwh) * tariff, 6),
            "month_source": str(
                first_present(source.get("month_source"), source.get("monthSource"), default="stored_monthly")
            ),
            "month_data_available": True,
            "month_summary_count": int(as_number(first_present(source.get("month_summary_count"), source.get("monthly_summary_count")), 0)),
            "monthly_summary_count": int(as_number(first_present(source.get("monthly_summary_count"), source.get("month_summary_count")), 0)),
            "reason_if_unavailable": None,
        }
    return {}


def build_monthly_energy_summary(
    home_id: str,
    settings: dict[str, Any],
    *stored_sources: dict[str, Any],
) -> dict[str, Any]:
    now_dt = datetime.now(BAHRAIN_TZ)
    month_start = datetime(now_dt.year, now_dt.month, 1, tzinfo=BAHRAIN_TZ)
    start_ms = int(month_start.timestamp() * 1000)
    end_ms = now_ms()
    daily = query_summaries_between(
        home_id,
        "daily",
        start_at_ms=start_ms,
        end_at_ms=end_ms,
        limit=45,
    )
    hourly = query_summaries_between(
        home_id,
        "hourly",
        start_at_ms=start_ms,
        end_at_ms=end_ms,
        limit=744,
    )
    monthly = query_summaries_between(
        home_id,
        "monthly",
        start_at_ms=start_ms,
        end_at_ms=end_ms,
        limit=3,
    )

    source = "unavailable"
    summaries: list[dict[str, Any]] = []
    energy_values: list[float] = []
    for candidate_source, candidate_summaries in (
        ("daily_summary", daily),
        ("hourly_summary", hourly),
        ("stored_monthly_summary", monthly),
    ):
        candidate_values = [
            value
            for value in (summary_energy_raw_value(summary) for summary in candidate_summaries)
            if value is not None
        ]
        candidate_total = round(sum(candidate_values), 6)
        if candidate_values and candidate_total > 0:
            source = candidate_source
            summaries = candidate_summaries
            energy_values = candidate_values
            break
    tariff = as_number(settings.get("cost_per_kwh"), 0.029)
    stored = stored_monthly_energy_summary(*stored_sources, tariff=tariff) if not summaries else {}
    if stored:
        stored.update(
            {
                "month_start_ms": start_ms,
                "month_start_iso": iso_from_ms(start_ms),
                "month_end_ms": end_ms,
                "month_end_iso": iso_from_ms(end_ms),
            }
        )
        print(
            "[KahrabaIQ MONTHLY] "
            f"home_id={home_id} source={stored.get('month_source')} "
            f"month_kwh={stored.get('month_kwh')} reason=None",
            flush=True,
        )
        return stored
    month_kwh = round(sum(energy_values), 6)
    reason = None
    if not (daily or hourly or monthly):
        reason = "no current-month daily, hourly, or monthly cloud summaries were found"
    elif not energy_values:
        reason = "current-month summaries exist but do not contain usable energy totals; check breaker energy sensors or summary sync"
    elif month_kwh <= 0:
        reason = "current-month summaries contain only zero energy totals; check breaker energy sensors or Home Assistant energy entity IDs"
    print(
        "[KahrabaIQ MONTHLY] "
        f"home_id={home_id} start={iso_from_ms(start_ms)} end={iso_from_ms(end_ms)} "
        f"daily_count={len(daily)} hourly_count={len(hourly)} monthly_count={len(monthly)} "
        f"selected_source={source} selected_count={len(summaries)} "
        f"energy_value_count={len(energy_values)} month_kwh={month_kwh} reason={reason}",
        flush=True,
    )
    return {
        "month_kwh": month_kwh,
        "month_cost_bhd": round(month_kwh * tariff, 6),
        "month_start_ms": start_ms,
        "month_start_iso": iso_from_ms(start_ms),
        "month_end_ms": end_ms,
        "month_end_iso": iso_from_ms(end_ms),
        "month_source": source,
        "month_data_available": bool(energy_values),
        "month_summary_count": len(summaries),
        "monthly_summary_count": len(summaries),
        "month_energy_value_count": len(energy_values),
        "reason_if_unavailable": reason,
    }


def timestamp_from_ai_item(item: dict[str, Any]) -> int:
    return int(
        as_number(
            first_present(
                item.get("created_at_ms"),
                item.get("created_at"),
                item.get("updated_at_ms"),
                item.get("last_checked_at"),
            ),
            0,
        )
        or 0
    )


def smoke_text_is_active(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text or any(token in text for token in ["clear", "normal", "no smoke", "no gas", "safe"]):
        return False
    return any(token in text for token in ["detect", "smoke", "gas"])


def item_mentions_smoke_or_gas(item: Any) -> bool:
    if isinstance(item, dict):
        text = " ".join(
            str(item.get(key) or "")
            for key in ["id", "title", "message", "category", "type", "explanation", "recommendation_type"]
        ).lower()
    else:
        text = str(item or "").lower()
    return "smoke" in text or "gas" in text


def dashboard_smoke_context(room: dict[str, Any], safety: dict[str, Any]) -> dict[str, Any]:
    timestamp_ms = int(as_number(room.get("sensor_timestamp_ms"), 0) or 0)
    age_seconds = round((now_ms() - timestamp_ms) / 1000, 3) if timestamp_ms > 0 else None
    stale = age_seconds is None or age_seconds > 180
    smoke_state = as_dict(safety.get("smoke_state"))
    emergency_mode = as_dict(safety.get("emergency_mode"))
    room_active = normalize_bool(room.get("smoke")) is True or smoke_text_is_active(room.get("smoke_text"))
    safety_active = str(smoke_state.get("status") or "").lower() in {"pending", "confirmed", "active", "open"}
    emergency_active = emergency_mode.get("active") is True and item_mentions_smoke_or_gas(emergency_mode)
    active = not stale and (room_active or safety_active or emergency_active)
    status = "active" if active else "stale" if stale else "clear"
    return {
        "active": active,
        "stale": stale,
        "status": status,
        "sensor_timestamp_ms": timestamp_ms,
        "age_seconds": age_seconds,
        "room_smoke_text": room.get("smoke_text"),
        "safety_status": smoke_state.get("status"),
    }


def ai_latest_context(latest: dict[str, Any]) -> dict[str, Any]:
    timestamp_ms = timestamp_from_ai_item(latest)
    age_seconds = round((now_ms() - timestamp_ms) / 1000, 3) if timestamp_ms > 0 else None
    stale = age_seconds is None or age_seconds > 15 * 60
    return {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_from_ms(timestamp_ms) if timestamp_ms > 0 else None,
        "age_seconds": age_seconds,
        "stale": stale,
        "status": "stale" if stale else "fresh",
        "source": latest.get("source") or latest.get("input_source") or "unknown",
    }


def stale_ai_dashboard(ai_ctx: dict[str, Any], smoke_ctx: dict[str, Any]) -> dict[str, Any]:
    if smoke_ctx.get("stale"):
        summary = "Room sensor data is stale. Waiting for fresh sensor data before showing safety-critical AI alerts."
        label = "Waiting for sensors"
        action = "Check room sensor"
        status = "needs_fresh_sensor_data"
    else:
        summary = "Latest AI result is stale. Showing live dashboard data while waiting for a fresh prediction."
        label = "AI stale"
        action = "Run fresh AI check"
        status = "stale_ai_result"
    return {
        "status": status,
        "prediction_status": status,
        "confidence": 0,
        "waste_confidence": 0,
        "abnormal_usage_confidence": 0,
        "energy_waste": False,
        "abnormal_usage": "normal",
        "recommendation_type": "check_sensor_data" if smoke_ctx.get("stale") else "refresh_ai_prediction",
        "next_hour_energy_kWh": 0,
        "next_hour_cost_BHD": 0,
        "efficiency_score": 0,
        "summary": summary,
        "ai_status_summary": summary,
        "ai_action_title": action,
        "recommended_action": action,
        "control_suggestion": None,
        "updated_at": ai_ctx.get("timestamp_ms"),
        "ai_status_code": status,
        "ai_status_label": label,
        "ai_status_tone": "warning",
        "ai_freshness_status": ai_ctx.get("status"),
        "ai_age_seconds": ai_ctx.get("age_seconds"),
    }


def build_home_insights(home_id: str) -> dict[str, Any]:
    hourly = query_summaries_between(home_id, "hourly", limit=48)
    daily = query_summaries_between(home_id, "daily", limit=14)
    if not hourly and not daily:
        return {
            "home_id": home_id,
            "generated_at_ms": now_ms(),
            "generated_at_iso": iso_from_ms(now_ms()),
            "insights": [],
        }

    peak_hour = max(hourly, key=summary_energy_value) if hourly else {}
    latest_day = daily[0] if daily else {}
    previous_day = daily[1] if len(daily) > 1 else {}
    latest_day_energy = summary_energy_value(latest_day)
    previous_day_energy = summary_energy_value(previous_day)
    trend_delta = round(latest_day_energy - previous_day_energy, 3) if previous_day else None
    occupancy_waste = []
    repeated_alert_types: dict[str, int] = {}
    for summary in daily or hourly:
        occupancy = as_dict(summary.get("occupancySummary"))
        occupied = as_number(occupancy.get("occupiedCount"), 0) or 0
        samples = as_number(occupancy.get("sampleCount"), 0) or 0
        energy = summary_energy_value(summary)
        if samples > 0 and occupied <= max(1, samples * 0.2) and energy > 0.5:
            occupancy_waste.append(
                {
                    "period_start_ms": first_present(summary.get("startAtMs"), summary.get("start_at_ms")),
                    "energy_kwh": round(energy, 3),
                    "occupied_count": int(occupied),
                    "sample_count": int(samples),
                }
            )
        by_type = as_dict(as_dict(summary.get("alertSummary")).get("byType"))
        for alert_type, count in by_type.items():
            repeated_alert_types[alert_type] = repeated_alert_types.get(alert_type, 0) + int(as_number(count, 0) or 0)

    insights: list[dict[str, Any]] = []
    if peak_hour:
        insights.append(
            {
                "type": "peak_energy_usage",
                "title": "Peak energy usage hour",
                "message": "Highest recent hourly consumption came from the local Pi hourly summaries.",
                "period_start_ms": first_present(peak_hour.get("startAtMs"), peak_hour.get("start_at_ms")),
                "energy_kwh": round(summary_energy_value(peak_hour), 3),
            }
        )
    if trend_delta is not None:
        insights.append(
            {
                "type": "daily_energy_trend",
                "title": "Daily energy trend",
                "message": "Compares the latest daily summary against the previous day.",
                "latest_day_energy_kwh": round(latest_day_energy, 3),
                "previous_day_energy_kwh": round(previous_day_energy, 3),
                "delta_kwh": trend_delta,
            }
        )
    if occupancy_waste:
        insights.append(
            {
                "type": "occupancy_vs_energy_waste",
                "title": "Possible occupancy waste",
                "message": "Energy usage stayed relatively high while occupancy stayed mostly low in one or more recent summary buckets.",
                "periods": occupancy_waste[:5],
            }
        )
    noisy_alerts = [
        {"alert_type": alert_type, "count": count}
        for alert_type, count in sorted(repeated_alert_types.items(), key=lambda item: item[1], reverse=True)
        if count > 1
    ]
    if noisy_alerts:
        insights.append(
            {
                "type": "repeated_alerts",
                "title": "Repeated alerts detected",
                "message": "The same alert types appeared across recent summaries.",
                "alerts": noisy_alerts[:5],
            }
        )
    success_rate = summary_command_success_rate(hourly + daily)
    if success_rate is not None:
        insights.append(
            {
                "type": "command_success_rate",
                "title": "Command execution success rate",
                "message": "Calculated from command summaries synced by the Pi.",
                "success_rate_percent": success_rate,
            }
        )
    latest_state = as_dict(safe_get(f"/homes/{home_id}/latest_state", {}))
    updated_at_ms = as_number(latest_state.get("updated_at_ms"), 0) or 0
    if updated_at_ms > 0:
        offline_minutes = round(max(0, now_ms() - updated_at_ms) / 60000, 1)
        insights.append(
            {
                "type": "device_offline_pattern",
                "title": "Latest Pi/cloud state freshness",
                "message": "Based on the most recent compact state upload from the Pi.",
                "minutes_since_last_state": offline_minutes,
            }
        )
    generated_at = now_ms()
    return {
        "home_id": home_id,
        "generated_at_ms": generated_at,
        "generated_at_iso": iso_from_ms(generated_at),
        "insights": insights,
    }


def build_home_recommendations(home_id: str) -> dict[str, Any]:
    insights_bundle = build_home_insights(home_id)
    recommendations = []
    for insight in insights_bundle["insights"]:
        if insight["type"] == "peak_energy_usage":
            recommendations.append(
                {
                    "type": "shift_usage",
                    "priority": "medium",
                    "title": "Shift heavy loads away from peak hours",
                    "message": "Review the devices running during the highest hourly consumption period and move flexible loads away from that hour when possible.",
                }
            )
        elif insight["type"] == "occupancy_vs_energy_waste":
            recommendations.append(
                {
                    "type": "reduce_empty_room_waste",
                    "priority": "high",
                    "title": "Reduce energy use while rooms are empty",
                    "message": "One or more recent periods show low occupancy with meaningful energy use. Check breakers, AC, and socket switches for idle waste.",
                }
            )
        elif insight["type"] == "repeated_alerts":
            recommendations.append(
                {
                    "type": "investigate_repeated_alerts",
                    "priority": "high",
                    "title": "Investigate repeated alerts",
                    "message": "Repeated alert types suggest an unresolved environmental or device issue that should be checked locally on the Pi side.",
                }
            )
        elif insight["type"] == "command_success_rate" and as_number(insight.get("success_rate_percent"), 100) < 90:
            recommendations.append(
                {
                    "type": "improve_command_reliability",
                    "priority": "high",
                    "title": "Improve command reliability",
                    "message": "Recent command success rate is lower than expected. Check Pi connectivity, Home Assistant/Matter availability, and device online state.",
                }
            )
    recommendations.extend(object_to_list(safe_get(f"/homes/{home_id}/backend/recommendations", {})))
    return {
        "home_id": home_id,
        "generated_at_ms": insights_bundle["generated_at_ms"],
        "generated_at_iso": insights_bundle["generated_at_iso"],
        "recommendations": recommendations,
    }


@app.get("/api/home/{home_id}/cloud/commands", dependencies=[Depends(require_home_permission("can_view"))])
def get_cloud_remote_commands(home_id: str, limit: int = Query(25, ge=1, le=100)) -> dict[str, Any]:
    try:
        commands = query_recent_remote_commands(home_id, limit)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"AWS command read failed: {error}") from error
    for command in commands:
        sync_remote_command_projection(home_id, command)
    return {
        "success": True,
        "home_id": home_id,
        "count": len(commands),
        "commands": [command_status_payload(item) for item in commands],
    }


@app.get("/api/home/{home_id}/cloud/commands/{command_id}", dependencies=[Depends(require_home_permission("can_view"))])
def get_cloud_remote_command(home_id: str, command_id: str) -> dict[str, Any]:
    try:
        command = find_remote_command(home_id, command_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"AWS command read failed: {error}") from error
    if not command:
        raise HTTPException(status_code=404, detail="Command not found.")
    sync_remote_command_projection(home_id, command)
    return {
        "success": True,
        "home_id": home_id,
        "command": command_status_payload(command),
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


@app.get("/api/homes/{home_id}/summaries/hourly", dependencies=[Depends(require_home_permission("can_view"))])
def get_hourly_summaries(
    home_id: str,
    limit: int = Query(24, ge=1, le=168),
    start_at_ms: int | None = None,
    end_at_ms: int | None = None,
) -> dict[str, Any]:
    summaries = query_summaries_between(
        home_id,
        "hourly",
        start_at_ms=start_at_ms,
        end_at_ms=end_at_ms,
        limit=limit,
    )
    return {"success": True, "home_id": home_id, "count": len(summaries), "summaries": summaries}


@app.get("/api/homes/{home_id}/summaries/daily", dependencies=[Depends(require_home_permission("can_view"))])
def get_daily_summaries(
    home_id: str,
    limit: int = Query(7, ge=1, le=90),
    start_at_ms: int | None = None,
    end_at_ms: int | None = None,
) -> dict[str, Any]:
    summaries = query_summaries_between(
        home_id,
        "daily",
        start_at_ms=start_at_ms,
        end_at_ms=end_at_ms,
        limit=limit,
    )
    return {"success": True, "home_id": home_id, "count": len(summaries), "summaries": summaries}


@app.get("/api/homes/{home_id}/insights", dependencies=[Depends(require_home_permission("can_view"))])
def get_home_insights(home_id: str) -> dict[str, Any]:
    return {"success": True, **build_home_insights(home_id)}


@app.get("/api/homes/{home_id}/recommendations", dependencies=[Depends(require_home_permission("can_view"))])
def get_home_recommendations(home_id: str) -> dict[str, Any]:
    return {"success": True, **build_home_recommendations(home_id)}


@app.get("/api/home/{home_id}/dashboard", dependencies=[Depends(require_home_permission("can_view"))])
def get_dashboard(home_id: str) -> dict[str, Any]:
    resolve_smoke_emergency_if_clear(home_id)
    bundle = read_home_bundle(home_id)
    devices = build_devices(bundle, home_id)
    room = build_room(bundle)
    hub_status = build_hub_status(bundle)
    timestamp_ms = now_ms()
    control = ensure_control(home_id)
    settings = ensure_settings(home_id)
    control_mode = str(control.get("mode", "assist")).lower()
    canonical_ai_latest = as_dict(bundle["canonical_ai_latest"])
    smoke_ctx = dashboard_smoke_context(room, as_dict(bundle["safety"]))
    ai_ctx = ai_latest_context(canonical_ai_latest)
    ai_latest_suggestions = object_to_list(canonical_ai_latest.get("suggestions"))
    if smoke_ctx.get("active") is not True:
        ai_latest_suggestions = [item for item in ai_latest_suggestions if not item_mentions_smoke_or_gas(item)]
    current_ai_notifications = [
        item
        for item in object_to_list(canonical_ai_latest.get("notifications"))
        if isinstance(item, dict)
        and str(item.get("status", "active")).lower() in {"active", "open", "pending"}
        and item.get("acknowledged") is not True
        and (smoke_ctx.get("active") is True or not item_mentions_smoke_or_gas(item))
    ]
    energy = build_energy(bundle, devices, settings)
    monthly_energy = build_monthly_energy_summary(
        home_id,
        settings,
        as_dict(bundle["latest_state"].get("energy")),
        bundle["backend_dashboard_energy"],
        bundle["dashboard_latest"],
    )
    energy.update(monthly_energy)

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
        + ai_latest_suggestions
    )
    print(
        f"[KahrabaIQ DASHBOARD] home_id={home_id} ai_age_seconds={ai_ctx.get('age_seconds')} "
        f"ai_status={ai_ctx.get('status')} smoke_status={smoke_ctx.get('status')} "
        f"smoke_active={smoke_ctx.get('active')} sensor_age_seconds={smoke_ctx.get('age_seconds')} "
        f"active_alerts={len(alerts)} active_suggestions={len(ai_latest_suggestions)} "
        f"ai_notifications={len(current_ai_notifications)} month_source={energy.get('month_source')}"
    )

    return {
        "home_id": home_id,
        "control": {
            "mode": control_mode,
            "label": control_label(control_mode),
            "description": control_description(control_mode),
        },
        "room": room,
        "occupancy": bundle["occupancy_room1"],
        "energy": energy,
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
            "smoke_context": smoke_ctx,
        },
        "recommendations": recommendations,
        "action_suggestions": dedupe_action_suggestions(
            active_only(
                object_to_list(safe_get(f"/homes/{home_id}/action_suggestions/active", {}))
                + ai_latest_suggestions
            )
        ),
        "automation_logs": object_to_list(
            safe_get(f"/homes/{home_id}/automation_logs", {})
        )[-10:],
        "ai": build_ai(bundle, smoke_context=smoke_ctx),
        "ai_notifications": current_ai_notifications,
        "ai_alerts": [
            item
            for item in object_to_list(canonical_ai_latest.get("alerts"))
            if smoke_ctx.get("active") is True or not item_mentions_smoke_or_gas(item)
        ],
        "ai_suggestions": ai_latest_suggestions,
        "ai_freshness": ai_ctx,
        "ai_daily_summary": as_dict(as_dict(bundle["backend_ai"]).get("daily_summary")),
        "system_health": bundle["system_health"] or bundle["backend_device_health"],
        "hub_status": hub_status,
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
    if not alert or normalize_alert_status(alert.get("status")) not in {"OPEN", "ACKNOWLEDGED"}:
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
                "status": "ACKNOWLEDGED",
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
                "status": "RESOLVED",
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


@app.get("/api/users/me/notifications")
def list_my_notifications(
    limit: int = Query(50, ge=1, le=100),
    unread_only: bool = False,
    actor: AuthContext = Depends(require_authenticated_user),
) -> dict[str, Any]:
    raw_notifications = object_to_list(safe_get(f"/users/{actor.uid}/notifications", {}))
    notifications = [
        item
        for item in raw_notifications
        if isinstance(item, dict)
        and item.get("dismissed") is not True
        and (not unread_only or item.get("read") is not True)
    ]
    notifications.sort(key=user_notification_sort_key, reverse=True)
    limited = notifications[:limit]
    unread_count = sum(
        1
        for item in raw_notifications
        if isinstance(item, dict) and item.get("dismissed") is not True and item.get("read") is not True
    )
    return {
        "success": True,
        "uid": actor.uid,
        "count": len(limited),
        "unread_count": unread_count,
        "notifications": limited,
    }


@app.post("/api/users/me/notifications/{notification_id}/read")
def mark_my_notification_read(
    notification_id: str,
    actor: AuthContext = Depends(require_authenticated_user),
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    notification = as_dict(safe_get(f"/users/{actor.uid}/notifications/{notification_id}", {}))
    if not notification:
        raise HTTPException(status_code=404, detail="Notification does not exist.")
    safe_update(
        f"/users/{actor.uid}/notifications/{notification_id}",
        {"read": True, "read_at_ms": timestamp_ms, "read_at_iso": iso_from_ms(timestamp_ms)},
    )
    home_id = str(notification.get("home_id") or "")
    if home_id:
        safe_update(
            f"/homes/{home_id}/notifications/{notification_id}",
            {"read": True, "read_at_ms": timestamp_ms, "read_at_iso": iso_from_ms(timestamp_ms)},
        )
    return {"success": True, "notification_id": notification_id}


@app.post("/api/users/me/notifications/{notification_id}/dismiss")
def dismiss_my_notification(
    notification_id: str,
    actor: AuthContext = Depends(require_authenticated_user),
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    notification = as_dict(safe_get(f"/users/{actor.uid}/notifications/{notification_id}", {}))
    if not notification:
        raise HTTPException(status_code=404, detail="Notification does not exist.")
    updates = {
        "dismissed": True,
        "dismissed_at_ms": timestamp_ms,
        "dismissed_at_iso": iso_from_ms(timestamp_ms),
        "read": True,
        "read_at_ms": timestamp_ms,
        "read_at_iso": iso_from_ms(timestamp_ms),
    }
    safe_update(f"/users/{actor.uid}/notifications/{notification_id}", updates)
    home_id = str(notification.get("home_id") or "")
    if home_id:
        safe_update(f"/homes/{home_id}/notifications/{notification_id}", updates)
    return {"success": True, "notification_id": notification_id}


@app.post("/api/users/me/notifications/read-all")
def mark_my_notifications_read_all(actor: AuthContext = Depends(require_authenticated_user)) -> dict[str, Any]:
    timestamp_ms = now_ms()
    notifications = as_dict(safe_get(f"/users/{actor.uid}/notifications", {}))
    updated = 0
    for notification_id, raw_notification in notifications.items():
        notification = as_dict(raw_notification)
        if notification.get("read") is True:
            continue
        updated += 1
        safe_update(
            f"/users/{actor.uid}/notifications/{notification_id}",
            {"read": True, "read_at_ms": timestamp_ms, "read_at_iso": iso_from_ms(timestamp_ms)},
        )
        home_id = str(notification.get("home_id") or "")
        if home_id:
            safe_update(
                f"/homes/{home_id}/notifications/{notification_id}",
                {"read": True, "read_at_ms": timestamp_ms, "read_at_iso": iso_from_ms(timestamp_ms)},
            )
    return {"success": True, "updated": updated}


@app.get("/api/home/{home_id}/notifications", dependencies=[Depends(require_home_permission("can_view"))])
def list_notifications(home_id: str, limit: int = 50, unread_only: bool = False) -> dict[str, Any]:
    raw_notifications = object_to_list(safe_get(f"/homes/{home_id}/notifications", {}))
    notifications = [
        item
        for item in raw_notifications
        if isinstance(item, dict)
        and item.get("dismissed") is not True
        and (not unread_only or item.get("read") is not True)
    ]
    notifications.sort(key=notification_sort_key, reverse=True)
    limited = notifications[: max(1, min(int(limit), 100))]
    unread_count = sum(
        1
        for item in raw_notifications
        if isinstance(item, dict) and item.get("dismissed") is not True and item.get("read") is not True
    )
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
    for user_id in member_user_ids(home_id):
        safe_update(
            f"/users/{user_id}/notifications/{notification_id}",
            {"read": True, "read_at_ms": timestamp_ms, "read_at_iso": iso_from_ms(timestamp_ms)},
        )
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
    if role in {"member", "viewer"} and home_invited_user_count(home_id) >= HOME_MEMBER_LIMIT:
        raise HTTPException(status_code=409, detail=f"This home already has the maximum {HOME_MEMBER_LIMIT} invited users.")
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
    existing_role = validate_role(str(existing.get("role", "viewer")))
    if existing_role == "home_admin" and role != "home_admin" and admin_count(home_id) <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove the last admin from the home.")
    if role in {"member", "viewer"} and existing_role not in {"member", "viewer"} and home_invited_user_count(home_id) >= HOME_MEMBER_LIMIT:
        raise HTTPException(status_code=409, detail=f"This home already has the maximum {HOME_MEMBER_LIMIT} invited users.")

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
    return remove_member_from_home(home_id, uid, actor)


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
        "status": "ACKNOWLEDGED",
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


def queue_remote_device_command(
    home_id: str,
    device_id: str,
    device: dict[str, Any],
    request: DeviceCommandRequest,
    command: str,
    requested_by: str,
) -> DeviceCommandResponse:
    formatted_device = format_device(device_id, device)
    target_state = command_to_target_state(command)
    current_state = str(formatted_device.get("state", "unknown")).lower()
    device_name = device_message_name(device_id, device)
    command_record = create_remote_command(
        home_id,
        device_id,
        command,
        requested_by=requested_by,
        source=request.source or "cloud_remote_api",
        emergency=request.emergency,
        alert_id=request.alert_id,
        reason=request.reason,
    )
    command_id = str(command_record["command_id"])
    pending_record = {
        "timestamp_ms": command_record["requested_at_ms"],
        "timestamp_iso": command_record["requested_at_iso"],
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
        "source": request.source or "cloud_remote_api",
        "emergency": request.emergency,
        "alert_id": request.alert_id,
        "source_suggestion_id": request.source_suggestion_id,
        "control_method": str(formatted_device.get("control_method") or device.get("control_method") or "home_assistant"),
        "ha_entity_id": device.get("ha_entity_id"),
        "status": COMMAND_STATUS_PENDING,
        "requested_at_ms": command_record["requested_at_ms"],
        "requested_at_iso": command_record["requested_at_iso"],
        "expires_at_ms": command_record.get("expires_at_ms"),
        "expires_at_iso": command_record.get("expires_at_iso"),
        "result": command_record.get("result") or {},
    }
    write_command_record(home_id, device_id, pending_record, pending=True)
    safe_update(
        f"/homes/{home_id}/devices/{device_id}",
        {
            "command_in_progress": True,
            "pending_command_id": command_id,
            "pending_target_state": target_state,
            "last_requested_state": target_state,
            "last_command_status": COMMAND_STATUS_PENDING,
            "last_command_message": "Command queued for the Raspberry Pi.",
            "last_command": {
                "status": COMMAND_STATUS_PENDING,
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
        status=COMMAND_STATUS_PENDING,
        message="Command queued for the Raspberry Pi.",
    )


def sync_remote_command_projection(home_id: str, command: dict[str, Any]) -> None:
    command_id = str(command.get("command_id") or command.get("commandId") or "").strip()
    device_id = str(command.get("device_id") or command.get("deviceId") or "").strip()
    if not command_id or not device_id:
        return
    status = normalize_command_status(command.get("status"))
    result = as_dict(command.get("result"))
    message = str(first_present(command.get("message"), result.get("user_message"), "")).strip() or None
    target_state = str(first_present(command.get("target_state"), command.get("targetState"), "")).strip().lower() or None
    actual_state = str(first_present(result.get("actual_state"), target_state, "")).strip().lower() or None
    projection = {
        "timestamp_ms": first_present(command.get("requested_at_ms"), command.get("requestedAtMs"), command.get("updated_at_ms"), now_ms()),
        "timestamp_iso": first_present(command.get("requested_at_iso"), command.get("requestedAt"), command.get("updated_at_iso"), iso_from_ms(now_ms())),
        "timezone": TIMEZONE,
        "command_id": command_id,
        "home_id": home_id,
        "device_id": device_id,
        "device_name": first_present(command.get("device_name"), command.get("deviceName"), device_id),
        "command": first_present(command.get("command"), command.get("action")),
        "action": first_present(command.get("command"), command.get("action")),
        "target_state": target_state,
        "previous_state": first_present(command.get("previous_state"), command.get("previousState"), None),
        "requested_by": first_present(command.get("requested_by"), command.get("requestedBy"), "cloud_remote_api"),
        "reason": command.get("reason"),
        "source": command.get("source"),
        "emergency": bool(command.get("emergency")),
        "alert_id": first_present(command.get("alert_id"), command.get("alertId"), None),
        "control_method": command.get("control_method"),
        "ha_entity_id": command.get("ha_entity_id"),
        "status": status,
        "requested_at_ms": first_present(command.get("requested_at_ms"), command.get("requestedAtMs"), None),
        "requested_at_iso": first_present(command.get("requested_at_iso"), command.get("requestedAt"), None),
        "expires_at_ms": first_present(command.get("expires_at_ms"), command.get("expiresAtMs"), None),
        "expires_at_iso": first_present(command.get("expires_at_iso"), command.get("expiresAt"), None),
        "claimed_at_ms": first_present(command.get("claimed_at_ms"), command.get("claimedAtMs"), None),
        "claimed_at_iso": first_present(command.get("claimed_at_iso"), command.get("claimedAt"), None),
        "started_at_ms": first_present(command.get("started_at_ms"), command.get("startedAtMs"), None),
        "started_at_iso": first_present(command.get("started_at_iso"), command.get("startedAt"), None),
        "completed_at_ms": first_present(command.get("executed_at_ms"), command.get("executedAtMs"), command.get("expired_at_ms"), None),
        "completed_at_iso": first_present(command.get("executed_at_iso"), command.get("executedAt"), command.get("expired_at_iso"), None),
        "result": result,
    }
    write_command_record(home_id, device_id, projection, pending=status in ACTIVE_COMMAND_STATUSES)
    device_updates = {
        "command_in_progress": status in ACTIVE_COMMAND_STATUSES,
        "pending_command_id": command_id if status in ACTIVE_COMMAND_STATUSES else None,
        "pending_target_state": target_state if status in ACTIVE_COMMAND_STATUSES else None,
        "last_requested_state": target_state,
        "last_command_status": status,
        "last_command_message": message,
        "last_command": {
            "status": status,
            "user_message": message,
            "error_code": result.get("error_code"),
        },
    }
    if status == COMMAND_STATUS_SUCCEEDED and actual_state in {"on", "off"}:
        device_updates.update(
            {
                "state": actual_state,
                "display_state": actual_state,
                "is_on": actual_state == "on",
            }
        )
    safe_update(f"/homes/{home_id}/devices/{device_id}", device_updates)


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
            "Home Assistant switch was not found.",
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
                "Home Assistant switch command failed. Please try again.",
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
                "message": "Home Assistant switch was not found.",
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
            "last_command_message": "Command queued for local Home Assistant controller.",
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
        message="Command queued for local Home Assistant controller.",
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
    device_id = DEVICE_ALIASES.get(device_id, device_id)
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
        device.get("control_method")
        or (
            "home_assistant"
            if device_id.startswith("breaker_") and USE_HOME_ASSISTANT_FOR_BREAKERS
            else "tuya_cloud"
            if device_id.startswith("breaker_") and USE_TUYA_CLOUD_FOR_BREAKERS
            else ""
        )
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
        return queue_remote_device_command(
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

    return queue_remote_device_command(
        home_id,
        device_id,
        device,
        request,
        command,
        requested_by,
    )


def chat_actor_id(actor: AuthContext) -> str:
    return actor.uid or actor.actor_id


def chat_actor_name(actor: AuthContext) -> str:
    if actor.email:
        return actor.email
    return actor.actor_id


def normalize_chat_mode(mode: str | None, scenario_id: str | None = None) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized in {"demo", "scenario", "demo_scenario"}:
        return "demo_scenario"
    if normalized == "live":
        return "live"
    return "demo_scenario" if str(scenario_id or "").strip() else "live"


def normalize_chat_scenario_id(scenario_id: str | None) -> str | None:
    clean = str(scenario_id or "").strip()
    return clean or None


def chat_session_mode(session: dict[str, Any]) -> str:
    return normalize_chat_mode(str(session.get("mode") or "live"), session.get("scenario_id"))


def chat_context_matches(session: dict[str, Any], mode: str, scenario_id: str | None) -> bool:
    session_mode = chat_session_mode(session)
    if session_mode != mode:
        return False
    if mode != "demo_scenario":
        return True
    return normalize_chat_scenario_id(session.get("scenario_id")) == normalize_chat_scenario_id(scenario_id)


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
    if actor.actor_type != "service" and created_by != chat_actor_id(actor):
        raise HTTPException(status_code=403, detail="You do not have access to this chat session.")
    return session


def create_chat_session_record(
    home_id: str,
    actor: AuthContext,
    title: str | None = None,
    *,
    session_id: str | None = None,
    mode: str | None = None,
    scenario_id: str | None = None,
    scenario_name: str | None = None,
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    actual_session_id = session_id or f"chat_{timestamp_ms}"
    normalized_scenario_id = normalize_chat_scenario_id(scenario_id)
    normalized_mode = normalize_chat_mode(mode, normalized_scenario_id)
    session = {
        "session_id": actual_session_id,
        "home_id": home_id,
        "mode": normalized_mode,
        "scenario_id": normalized_scenario_id if normalized_mode == "demo_scenario" else None,
        "scenario_name": (str(scenario_name or "").strip() or None) if normalized_mode == "demo_scenario" else None,
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
    if session and session.get("archived") is not True and chat_session_mode(session) == "live":
        return session
    return create_chat_session_record(home_id, actor, "New Chat", session_id=session_id, mode="live")


def default_context_chat_session(
    home_id: str,
    actor: AuthContext,
    *,
    scenario_id: str | None = None,
    scenario_name: str | None = None,
) -> dict[str, Any]:
    normalized_scenario_id = normalize_chat_scenario_id(scenario_id)
    mode = normalize_chat_mode(None, normalized_scenario_id)
    if mode == "live":
        return default_chat_session(home_id, actor)
    actor_key = re.sub(r"[^A-Za-z0-9_-]", "_", chat_actor_id(actor))
    scenario_key = re.sub(r"[^A-Za-z0-9_-]", "_", normalized_scenario_id or "scenario")
    session_id = f"chat_default_{actor_key}_{scenario_key}"
    session = as_dict(safe_get(chat_session_ref(home_id, session_id), {}))
    if session and session.get("archived") is not True and chat_context_matches(session, mode, normalized_scenario_id):
        return session
    return create_chat_session_record(
        home_id,
        actor,
        "New Chat",
        session_id=session_id,
        mode=mode,
        scenario_id=normalized_scenario_id,
        scenario_name=scenario_name,
    )


def call_ai_chat_service(home_id: str, request: ChatProxyRequest, history: list[dict[str, str]]) -> dict[str, Any]:
    ai_request = ai_engine.ChatRequest(
        message=request.message,
        home_id=home_id,
        home_name=request.home_name,
        scenario_id=request.scenario_id,
        scenario_name=request.scenario_name,
        context=request.context,
        conversation_history=history,
    )
    try:
        ai_response = ai_engine.chat_home(home_id, ai_request)
        return ai_response.model_dump() if hasattr(ai_response, "model_dump") else ai_response.dict()
    except HTTPException as error:
        detail = str(error.detail)
        if "GEMINI_API_KEY" not in detail and "Gemini" not in detail:
            raise
        return {
            "home_id": home_id,
            "answer": (
                "Gemini chat is not available from the backend right now. "
                "The EC2 chat session and history are working, but GEMINI_API_KEY or Gemini connectivity must be fixed before I can generate a full answer."
            ),
            "used_data": False,
            "timestamp": now_ms(),
            "model": "gemini_unavailable",
            "error": detail,
        }


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
    requested_scenario_id = normalize_chat_scenario_id(request.scenario_id)
    requested_mode = normalize_chat_mode(request.mode, requested_scenario_id)
    if not chat_context_matches(session, requested_mode, requested_scenario_id):
        raise HTTPException(status_code=409, detail="Chat session belongs to a different mode or scenario.")
    timestamp_ms = now_ms()
    user_message_id = f"msg_{timestamp_ms}_user"
    user_message = {
        "message_id": user_message_id,
        "session_id": session_id,
        "mode": requested_mode,
        "scenario_id": requested_scenario_id if requested_mode == "demo_scenario" else None,
        "scenario_name": request.scenario_name if requested_mode == "demo_scenario" else None,
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
        scenario_id=requested_scenario_id if requested_mode == "demo_scenario" else None,
        scenario_name=request.scenario_name if requested_mode == "demo_scenario" else None,
        context=request.context,
        conversation_history=history,
    )
    ai_data = call_ai_chat_service(home_id, proxy_request, history)
    answer = str(ai_data.get("answer") or "No chatbot answer was returned.").strip()
    assistant_timestamp_ms = now_ms()
    assistant_message_id = f"msg_{assistant_timestamp_ms}_assistant"
    assistant_message = {
        "message_id": assistant_message_id,
        "session_id": session_id,
        "mode": requested_mode,
        "scenario_id": requested_scenario_id if requested_mode == "demo_scenario" else None,
        "scenario_name": request.scenario_name if requested_mode == "demo_scenario" else None,
        "role": "assistant",
        "content": answer,
        "created_by": "assistant",
        "created_at_ms": assistant_timestamp_ms,
        "created_at_iso": iso_from_ms(assistant_timestamp_ms),
        "model": ai_data.get("model") or "gemini",
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
        "mode": requested_mode,
        "scenario_id": requested_scenario_id if requested_mode == "demo_scenario" else None,
        "scenario_name": request.scenario_name if requested_mode == "demo_scenario" else None,
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
    mode: str | None = Query(default="live"),
    scenario_id: str | None = None,
    actor: AuthContext = Depends(require_home_permission("can_use_ai_chat")),
) -> dict[str, Any]:
    sessions = object_to_list(safe_get(f"/homes/{home_id}/chat/sessions", {}))
    actor_id = chat_actor_id(actor)
    requested_scenario_id = normalize_chat_scenario_id(scenario_id)
    requested_mode = normalize_chat_mode(mode, requested_scenario_id)
    visible = [
        item
        for item in sessions
        if item.get("archived") is not True
        and (actor.actor_type == "service" or str(item.get("created_by")) == actor_id)
        and chat_context_matches(item, requested_mode, requested_scenario_id)
    ]
    visible.sort(key=lambda item: as_number(item.get("updated_at_ms")), reverse=True)
    return {"home_id": home_id, "mode": requested_mode, "scenario_id": requested_scenario_id, "count": len(visible), "sessions": visible}


@app.post("/api/home/{home_id}/chat/sessions")
def create_chat_session(
    home_id: str,
    request: ChatSessionCreateRequest,
    actor: AuthContext = Depends(require_home_permission("can_use_ai_chat")),
) -> dict[str, Any]:
    session = create_chat_session_record(
        home_id,
        actor,
        request.title or "New Chat",
        mode=request.mode,
        scenario_id=request.scenario_id,
        scenario_name=request.scenario_name,
    )
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
    session = default_context_chat_session(
        home_id,
        actor,
        scenario_id=request.scenario_id,
        scenario_name=request.scenario_name,
    )
    session_request = ChatSessionMessageRequest(
        message=request.message,
        home_name=request.home_name,
        mode=normalize_chat_mode(None, request.scenario_id),
        scenario_id=request.scenario_id,
        scenario_name=request.scenario_name,
        context=request.context,
    )
    return send_chat_session_message(home_id, str(session["session_id"]), session_request, actor)


def summary_energy_value(summary: dict[str, Any]) -> float:
    energy = as_dict(summary.get("energy"))
    return as_number(
        first_present(
            energy.get("total_estimated_energy_kWh"),
            energy.get("total_energy_kWh"),
            summary.get("total_estimated_energy_kWh"),
            summary.get("total_energy_kWh"),
            summary.get("totalEnergyKwh"),
        )
    )


def summary_power_value(summary: dict[str, Any]) -> float:
    energy = as_dict(summary.get("energy"))
    breaker_summaries = as_dict(summary.get("breakerSummaries"))
    breaker_power = sum(
        as_number(first_present(as_dict(item).get("avgPowerW"), as_dict(item).get("avg_power_W")))
        for item in breaker_summaries.values()
        if isinstance(item, dict)
    )
    return as_number(
        first_present(
            energy.get("total_avg_power_W"),
            energy.get("total_power_W"),
            summary.get("total_avg_power_W"),
            summary.get("total_power_W"),
            breaker_power if breaker_power > 0 else None,
        )
    )


def summary_start_ms(summary: dict[str, Any]) -> int:
    return int(as_number(first_present(summary.get("startAtMs"), summary.get("start_at_ms"), summary.get("hour_start"), summary.get("timestamp_ms")), 0))


def summary_hour(summary: dict[str, Any]) -> int | None:
    raw_hour = first_present(summary.get("hour_of_day"), summary.get("hourOfDay"))
    if raw_hour is not None:
        return int(as_number(raw_hour, -1))
    start_ms = summary_start_ms(summary)
    if start_ms <= 0:
        return None
    return datetime.fromtimestamp(start_ms / 1000, tz=BAHRAIN_TZ).hour


def summary_is_weekend(summary: dict[str, Any]) -> bool:
    start_ms = summary_start_ms(summary)
    if start_ms <= 0:
        return False
    day = datetime.fromtimestamp(start_ms / 1000, tz=BAHRAIN_TZ).strftime("%A")
    return day in {"Friday", "Saturday"}


def summary_ac_usage_minutes(summary: dict[str, Any]) -> float:
    ac = as_dict(as_dict(summary.get("breakerSummaries")).get("breaker_02"))
    samples = as_number(ac.get("switchOnSamples"), 0)
    sample_count = as_number(ac.get("sampleCount"), 0)
    if sample_count <= 0:
        return 0.0
    return round(min(60.0, (samples / sample_count) * 60.0), 3)


def latest_device_context(home_id: str) -> dict[str, Any]:
    latest_state = as_dict(safe_get(f"/homes/{home_id}/latest_state", {}))
    devices = as_dict(latest_state.get("devices"))
    control = ensure_control(home_id)

    def state_for(device_id: str) -> str:
        device = as_dict(devices.get(device_id))
        status = as_dict(device.get("status"))
        return str(first_present(device.get("state"), device.get("display_state"), status.get("state"), status.get("switch"), default="unknown")).lower()

    return {
        "latest_control_mode": str(control.get("mode", "assist")),
        "latest_ac_state": state_for("breaker_02"),
        "latest_socket_state": state_for("breaker_01"),
        "latest_breaker_state": state_for("breaker_01"),
        "latest_state_age_ms": max(0, now_ms() - int(as_number(first_present(latest_state.get("updated_at_ms"), latest_state.get("timestamp_ms")), 0))) if latest_state else None,
    }


def mean_std(values: list[float]) -> tuple[float, float]:
    usable = [value for value in values if value > 0]
    if not usable:
        return 0.0, 0.0
    mean = sum(usable) / len(usable)
    variance = sum((value - mean) ** 2 for value in usable) / len(usable)
    return round(mean, 6), round(variance ** 0.5, 6)


def enrich_ai_payload_with_history(home_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    recent_summaries = query_summaries_between(home_id, "hourly", limit=72)
    energy_values = [summary_energy_value(summary) for summary in recent_summaries]
    power_values = [summary_power_value(summary) for summary in recent_summaries]
    energy_mean, energy_std = mean_std(energy_values)
    power_mean, power_std = mean_std(power_values)
    same_hour_values = [
        summary_energy_value(summary)
        for summary in recent_summaries
        if summary_hour(summary) == int(as_number(payload.get("hour_of_day"), -2))
    ]
    same_hour_mean, same_hour_std = mean_std(same_hour_values)
    same_hour_7_days = same_hour_values[:7]
    same_hour_7_mean, _ = mean_std(same_hour_7_days)
    same_hour_ac_values = [
        summary_ac_usage_minutes(summary)
        for summary in recent_summaries
        if summary_hour(summary) == int(as_number(payload.get("hour_of_day"), -2))
    ][:7]
    same_hour_ac_mean, _ = mean_std(same_hour_ac_values)
    weekday_same_hour_count = sum(
        1
        for summary in recent_summaries
        if summary_hour(summary) == int(as_number(payload.get("hour_of_day"), -2)) and not summary_is_weekend(summary)
    )
    weekend_same_hour_count = sum(
        1
        for summary in recent_summaries
        if summary_hour(summary) == int(as_number(payload.get("hour_of_day"), -2)) and summary_is_weekend(summary)
    )
    recent_commands = query_recent_remote_commands(home_id, limit=50)
    one_hour_ago = now_ms() - 60 * 60 * 1000
    now_value = now_ms()
    recent_command_count = sum(
        1
        for command in recent_commands
        if as_number(first_present(command.get("requestedAtMs"), command.get("requested_at_ms"))) >= one_hour_ago
    )
    failed_command_count = sum(
        1
        for command in recent_commands
        if as_number(first_present(command.get("requestedAtMs"), command.get("requested_at_ms"))) >= one_hour_ago
        and normalize_command_status(command.get("status")) == COMMAND_STATUS_FAILED
    )
    last_command_ms = max(
        [int(as_number(first_present(command.get("requestedAtMs"), command.get("requested_at_ms")), 0)) for command in recent_commands]
        or [0]
    )
    minutes_since_last_command = round((now_value - last_command_ms) / 60000, 3) if last_command_ms > 0 else 999999.0
    device_context = latest_device_context(home_id)
    sensor_staleness_seconds = round(as_number(payload.get("sensor_data_age_ms"), 0) / 1000, 3)
    breaker_staleness_seconds = round(as_number(payload.get("energy_data_age_ms"), 0) / 1000, 3)
    no_occupancy_power_minutes = 60.0 if str(payload.get("occupancy_state")) in {"empty", "probably_empty"} and as_number(payload.get("total_power_for_guardrails_W")) > 50 else 0.0

    enriched = {
        **payload,
        "recent_energy_avg": energy_mean,
        "recent_energy_std": energy_std,
        "recent_power_avg": power_mean,
        "recent_power_std": power_std,
        "same_hour_energy_avg": same_hour_mean,
        "same_hour_energy_std": same_hour_std,
        "previous_hour_energy": energy_values[0] if energy_values else 0.0,
        "recent_usage_avg_kWh": energy_mean,
        "recent_usage_std_kWh": energy_std,
        "recent_power_avg_W": power_mean,
        "recent_power_std_W": power_std,
        "same_hour_usage_avg_kWh": same_hour_mean,
        "same_hour_usage_std_kWh": same_hour_std,
        "previous_hour_energy_kWh": energy_values[0] if energy_values else 0.0,
        "command_frequency_last_hour": recent_command_count,
        "failed_command_count_last_hour": failed_command_count,
        "time_since_last_command_minutes": minutes_since_last_command,
        "ac_on_duration_minutes": round(as_number(payload.get("ac_energy_kWh"), 0) / max(as_number(payload.get("ac_avg_power_W"), 0) / 1000, 0.001) * 60, 3) if as_number(payload.get("ac_energy_kWh"), 0) > 0 else 0.0,
        "socket_on_duration_minutes": round(as_number(payload.get("switch_energy_kWh"), 0) / max(as_number(payload.get("switch_avg_power_W"), 0) / 1000, 0.001) * 60, 3) if as_number(payload.get("switch_energy_kWh"), 0) > 0 else 0.0,
        "device_on_duration_minutes": max(as_number(payload.get("ac_on_duration_minutes"), 0), as_number(payload.get("socket_on_duration_minutes"), 0)),
        "no_occupancy_power_minutes": no_occupancy_power_minutes,
        "device_left_on_without_motion_minutes": no_occupancy_power_minutes,
        "time_since_last_motion_minutes": as_number(payload.get("minutes_since_last_activity"), 999999.0),
        "same_hour_avg_energy_last_7_days": same_hour_7_mean,
        "same_hour_avg_ac_usage_last_7_days": same_hour_ac_mean,
        "weekday_routine_score": min(1.0, weekday_same_hour_count / 3),
        "weekend_routine_score": min(1.0, weekend_same_hour_count / 2),
        "outside_routine_score": 1.0 - min(1.0, (weekday_same_hour_count + weekend_same_hour_count) / 5),
        "sensor_staleness_seconds": sensor_staleness_seconds,
        "breaker_staleness_seconds": breaker_staleness_seconds,
        **device_context,
    }
    enriched["device_on_duration_minutes"] = max(
        as_number(enriched.get("ac_on_duration_minutes")),
        as_number(enriched.get("socket_on_duration_minutes")),
    )
    return enriched


def apply_ec2_ai_routine_rules(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    predictions = result["predictions"]
    total_energy = as_number(payload.get("total_energy_kWh"))
    same_hour_mean = as_number(payload.get("same_hour_usage_avg_kWh"))
    same_hour_std = as_number(payload.get("same_hour_usage_std_kWh"))
    total_power = as_number(payload.get("total_power_for_guardrails_W"))
    power_mean = as_number(payload.get("recent_power_avg_W"))
    power_std = as_number(payload.get("recent_power_std_W"))
    occupancy_state = str(payload.get("occupancy_state") or "unknown")
    unusual_energy = same_hour_mean > 0 and same_hour_std > 0 and total_energy > same_hour_mean + 2 * same_hour_std
    unusual_power = power_mean > 0 and power_std > 0 and total_power > power_mean + 2 * power_std

    if unusual_energy or unusual_power:
        result["energy_waste"] = True
        result["abnormal_usage"] = "statistical_usage_anomaly"
        result["recommendation_type"] = "review_unusual_energy_usage"
        result["efficiency_score"] = min(as_number(result.get("efficiency_score"), 100), 55)
        result["explanation"] = (
            "Energy use is above the recent normal range for this home and time window."
        )
        predictions["waste_event"] = {"value": True, "confidence": 0.9, "source": "ec2_statistical_guardrail"}
        predictions["anomaly_label"] = {"value": "statistical_usage_anomaly", "confidence": 0.9, "source": "ec2_statistical_guardrail"}
        predictions["recommendation_type"] = {"value": "review_unusual_energy_usage", "confidence": 0.9, "source": "ec2_statistical_guardrail"}
        predictions["energy_efficiency_score"] = result["efficiency_score"]
        predictions["explanation"] = result["explanation"]
        result.setdefault("post_processing_rules", []).append("ec2_statistical_usage_anomaly")

    if occupancy_state in {"empty", "probably_empty"} and total_power > 50:
        result["energy_waste"] = True
        result["abnormal_usage"] = "high_power_while_empty"
        result["recommendation_type"] = "turn_off_unused_devices"
        result["explanation"] = "High power is active while the home appears empty."
        predictions["waste_event"] = {"value": True, "confidence": 1.0, "source": "ec2_occupancy_guardrail"}
        predictions["anomaly_label"] = {"value": "high_power_while_empty", "confidence": 1.0, "source": "ec2_occupancy_guardrail"}
        predictions["recommendation_type"] = {"value": "turn_off_unused_devices", "confidence": 1.0, "source": "ec2_occupancy_guardrail"}
        predictions["explanation"] = result["explanation"]
        result.setdefault("post_processing_rules", []).append("ec2_high_power_while_empty")

    return result


def ai_notification(
    home_id: str,
    severity: str,
    category: str,
    title: str,
    message: str,
    *,
    device_id: str | None = None,
    target_type: str | None = None,
    recommendation_type: str | None = None,
    confidence: float | None = None,
    explanation: str | None = None,
    notification_id: str | None = None,
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    notification_id = notification_id or f"ai_{category}_{timestamp_ms}"
    return {
        "id": notification_id,
        "home_id": home_id,
        "severity": severity,
        "category": category,
        "title": title,
        "message": message,
        "device_id": device_id,
        "target_type": target_type,
        "recommendation_type": recommendation_type,
        "created_at": timestamp_ms,
        "created_at_ms": timestamp_ms,
        "created_at_iso": iso_from_ms(timestamp_ms),
        "acknowledged": False,
        "source": "ai",
        "confidence": confidence,
        "explanation": explanation or message,
    }


def run_immediate_safety_checks(home_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    notifications: list[dict[str, Any]] = []
    if as_number(payload.get("smoke_count")) > 0:
        notifications.append(ai_notification(home_id, "critical", "safety", "Gas or smoke detected", "Check the room immediately. Energy saving is secondary to safety.", confidence=1.0, notification_id="smoke_gas_detected"))
    if as_number(payload.get("sensor_staleness_seconds")) > 180 or payload.get("sensor_data_fresh") is False:
        notifications.append(ai_notification(home_id, "medium", "system", "Room sensor data is stale", "The AI confidence is lower because the latest room sensor reading is old.", target_type="sensor", confidence=0.8, notification_id="sensor_data_stale"))
    if as_number(payload.get("breaker_staleness_seconds")) > 180 or payload.get("breaker_data_fresh") is False:
        notifications.append(ai_notification(home_id, "medium", "device", "Breaker data is stale", "The AI is waiting for fresh breaker readings before making strong energy decisions.", target_type="breaker", confidence=0.8, notification_id="breaker_data_stale"))
    if as_number(payload.get("failed_command_count_last_hour")) >= 2:
        notifications.append(ai_notification(home_id, "high", "device", "Repeated command failures", "Device commands failed repeatedly in the last hour. Check Pi connectivity and local controller status.", confidence=0.95, notification_id="repeated_command_failures"))
    if str(payload.get("occupancy_state")) in {"empty", "probably_empty"} and as_number(payload.get("total_power_for_guardrails_W")) > 150:
        notifications.append(ai_notification(home_id, "high", "energy", "High power while empty", "Power is high while occupancy appears low. Review AC, socket, and breaker state.", recommendation_type="turn_off_unused_devices", confidence=0.9, notification_id="high_power_empty_room"))
    return notifications


def run_lightweight_anomaly_checks(home_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    notifications: list[dict[str, Any]] = []
    total_energy = as_number(payload.get("total_energy_kWh"))
    total_power = as_number(payload.get("total_power_for_guardrails_W"))
    same_hour_mean = as_number(payload.get("same_hour_energy_avg"), as_number(payload.get("same_hour_usage_avg_kWh")))
    same_hour_std = as_number(payload.get("same_hour_energy_std"), as_number(payload.get("same_hour_usage_std_kWh")))
    recent_power_mean = as_number(payload.get("recent_power_avg"), as_number(payload.get("recent_power_avg_W")))
    recent_power_std = as_number(payload.get("recent_power_std"), as_number(payload.get("recent_power_std_W")))
    outside_routine_score = as_number(payload.get("outside_routine_score"))
    ac_active = as_number(payload.get("ac_live_power_W"), as_number(payload.get("ac_avg_power_W"))) > 50 or str(payload.get("latest_ac_state")) == "on"

    if same_hour_mean > 0 and total_energy > same_hour_mean + max(0.05, 2 * same_hour_std):
        notifications.append(ai_notification(home_id, "medium", "anomaly", "Energy above usual same-hour pattern", "This hour's energy is higher than recent same-hour usage.", confidence=0.85, explanation=f"Current {total_energy:.3f} kWh vs same-hour average {same_hour_mean:.3f} kWh.", notification_id="same_hour_energy_spike"))
    if recent_power_mean > 0 and total_power > recent_power_mean + max(50, 2 * recent_power_std):
        notifications.append(ai_notification(home_id, "medium", "anomaly", "Power above recent normal range", "Current power is higher than the recent rolling average.", confidence=0.85, explanation=f"Current {total_power:.1f} W vs recent average {recent_power_mean:.1f} W.", notification_id="rolling_power_spike"))
    if ac_active and outside_routine_score >= 0.8 and as_number(payload.get("hour_of_day")) <= 5:
        notifications.append(ai_notification(home_id, "medium", "routine", "AC running outside routine", "The AC appears active during an unusual time compared with recent routine.", device_id="breaker_02", recommendation_type="review_ac_schedule", confidence=0.75, notification_id="ac_outside_routine"))
    if as_number(payload.get("device_left_on_without_motion_minutes")) >= 30:
        notifications.append(ai_notification(home_id, "low", "recommendation", "Device may be left on", "A device has been active without recent motion. Consider turning unused devices off.", recommendation_type="turn_off_unused_devices", confidence=0.8, notification_id="device_left_on_without_motion"))
    return notifications


def build_ai_notifications(home_id: str, result: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    notifications: list[dict[str, Any]] = []
    anomaly = str(result.get("abnormal_usage") or "normal")
    recommendation = str(result.get("recommendation_type") or "none")
    explanation = str(result.get("explanation") or "AI detected an energy condition.")

    if as_number(payload.get("smoke_count")) > 0 or anomaly == "safety_smoke_gas_warning":
        notifications.append(ai_notification(home_id, "critical", "safety", "Gas or smoke detected", "Check the room immediately. Energy recommendations are secondary to safety."))
    if anomaly in {"high_power_while_empty", "empty_room_power_active", "device_left_on_at_night"}:
        notifications.append(ai_notification(home_id, "high", "energy", "Possible energy waste", explanation))
    elif anomaly != "normal":
        notifications.append(ai_notification(home_id, "medium", "anomaly", "Unusual usage detected", explanation))
    if recommendation != "none" and not any(item["category"] == "recommendation" for item in notifications):
        notifications.append(ai_notification(home_id, "low", "recommendation", "AI recommendation", explanation))
    return notifications


def dedupe_ai_notifications(notifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for notification in notifications:
        key = str(notification.get("id") or f"{notification.get('category')}:{notification.get('title')}")
        deduped[key] = notification
    return list(deduped.values())


def normalized_ai_api_response(home_id: str, result: dict[str, Any]) -> dict[str, Any]:
    notifications = object_to_list(result.get("notifications"))
    alerts = object_to_list(result.get("alerts")) or [
        item for item in notifications if str(item.get("severity")).lower() in {"high", "critical"}
    ]
    suggestions = object_to_list(result.get("suggestions")) or [
        item for item in notifications if str(item.get("category")).lower() == "recommendation"
    ]
    return {
        "success": True,
        "home_id": home_id,
        "latest_prediction": result,
        "ai_result": result,
        "active_alerts": alerts,
        "active_suggestions": suggestions,
        "notifications": notifications,
        "model_info": {
            "model_name": result.get("model_name"),
            "model_version": result.get("model_version"),
            "ml_ran": result.get("ml_ran"),
            "levels_ran": result.get("levels_ran", []),
        },
        "created_at": result.get("created_at"),
        "created_at_ms": result.get("created_at_ms"),
        "created_at_iso": result.get("created_at_iso"),
    }


def should_run_full_ml(home_id: str, *, force: bool = False, input_source: str = "") -> bool:
    if force:
        return True
    if "latest_hourly_summary" not in input_source:
        return False
    last_run = _ai_last_full_prediction_ms_by_home.get(home_id, 0)
    return now_ms() - last_run >= AI_FULL_PREDICTION_INTERVAL_SECONDS * 1000


def scenario_device(devices: dict[str, Any], device_id: str) -> dict[str, Any]:
    raw = as_dict(devices.get(device_id))
    if raw:
        return raw
    for item in devices.values():
        candidate = as_dict(item)
        if str(candidate.get("id") or candidate.get("device_id")) == device_id:
            return candidate
    return {}


def build_ai_payload_from_scenario(
    home_id: str,
    request: AiScenarioPredictRequest,
) -> tuple[dict[str, Any], str]:
    timestamp_ms = now_ms()
    bahrain_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=BAHRAIN_TZ)
    room = request.room
    energy = request.energy
    devices = request.devices
    occupancy = request.occupancy
    recent_history = request.recent_history
    routine_context = request.routine_context
    socket = scenario_device(devices, "breaker_01")
    ac = scenario_device(devices, "breaker_02")

    total_power = as_number(first_present(energy.get("power"), energy.get("current_power_w"), energy.get("total_power_W")))
    socket_power = as_number(first_present(socket.get("power"), socket.get("currentPower"), socket.get("current_power_w")))
    ac_power = as_number(first_present(ac.get("power"), ac.get("currentPower"), ac.get("current_power_w")))
    if total_power <= 0:
        total_power = socket_power + ac_power

    occupied = bool(first_present(occupancy.get("occupied"), room.get("motion"), room.get("isOccupied"), default=False))
    occupancy_state = str(first_present(occupancy.get("state"), "occupied" if occupied else "empty"))
    smoke_value = first_present(room.get("smoke"), room.get("smoke_detected"), room.get("smokeStatus"), room.get("smoke_status"), default=0)
    smoke_count = 1.0 if str(smoke_value).lower() in {"true", "1", "smoke/gas", "detected", "alert"} else as_number(smoke_value)
    sensor_staleness = as_number(recent_history.get("sensor_staleness_seconds"), 0)
    breaker_staleness = as_number(recent_history.get("breaker_staleness_seconds"), 0)

    payload = {
        "hour_of_day": int(as_number(routine_context.get("hour_of_day"), bahrain_time.hour)),
        "day_of_week": str(routine_context.get("day_of_week") or bahrain_time.strftime("%A")),
        "is_weekend": bool(routine_context.get("is_weekend", bahrain_time.strftime("%A") in {"Friday", "Saturday"})),
        "sample_count": as_number(recent_history.get("sample_count"), 48),
        "avg_temperature": first_present(room.get("temperature"), room.get("temp"), default=0),
        "avg_humidity": first_present(room.get("humidity"), default=0),
        "avg_sound_raw": first_present(room.get("soundRaw"), room.get("sound_raw"), room.get("sound"), default=0),
        "motion_count": 1.0 if occupied else 0.0,
        "bright_count": 1.0 if str(first_present(room.get("lightStatus"), room.get("light_status"), "")).lower() == "bright" else 0.0,
        "smoke_count": smoke_count,
        "noise_count": as_number(first_present(room.get("noise"), room.get("soundActive")), 1.0 if occupied else 0.0),
        "high_temp_count": 1.0 if as_number(first_present(room.get("temperature"), room.get("temp"))) >= 27 else 0.0,
        "occupancy_score": as_number(occupancy.get("occupancy_score"), 0.8 if occupied else 0.05),
        "occupancy_state": occupancy_state,
        "occupancy_confidence": as_number(occupancy.get("confidence"), 0.85),
        "occupied": occupied,
        "minutes_since_last_activity": as_number(occupancy.get("time_since_last_motion_minutes"), 1 if occupied else 999),
        "motion_recent": occupied,
        "sound_recent": occupied,
        "sound_active": occupied,
        "light_on_while_empty": occupancy_state in {"empty", "probably_empty"} and str(first_present(room.get("lightStatus"), room.get("light_status"), "")).lower() == "bright",
        "device_on_while_empty": occupancy_state in {"empty", "probably_empty"} and total_power > 10,
        "empty_room_power_w": total_power if occupancy_state in {"empty", "probably_empty"} else 0,
        "power_is_low": total_power <= 5,
        "total_power_for_guardrails_W": round(total_power, 3),
        "switch_live_power_W": round(socket_power, 3),
        "ac_live_power_W": round(ac_power, 3),
        "breaker_data_fresh": breaker_staleness <= 180,
        "sensor_data_fresh": sensor_staleness <= 180,
        "energy_data_age_ms": int(breaker_staleness * 1000) if breaker_staleness > 0 else 0,
        "sensor_data_age_ms": int(sensor_staleness * 1000) if sensor_staleness > 0 else 0,
        "switch_avg_power_W": socket_power,
        "switch_peak_power_W": max(socket_power, as_number(socket.get("peak_power_W"))),
        "switch_energy_kWh": as_number(first_present(socket.get("energy"), socket.get("energyToday"), socket.get("energy_kWh"))),
        "ac_avg_power_W": ac_power,
        "ac_peak_power_W": max(ac_power, as_number(ac.get("peak_power_W"))),
        "ac_energy_kWh": as_number(first_present(ac.get("energy"), ac.get("energyToday"), ac.get("energy_kWh"))),
        "total_avg_power_W": total_power,
        "total_peak_power_W": max(total_power, as_number(energy.get("peak_power_W"))),
        "total_energy_kWh": as_number(first_present(energy.get("energyToday"), energy.get("total_energy_kWh"), energy.get("totalEnergyKwh"))),
        "total_cost_BHD": as_number(first_present(energy.get("costToday"), energy.get("total_cost_BHD"))),
        "tariff_BHD_per_kWh": as_number(energy.get("tariff_BHD_per_kWh"), 0.032),
        "latest_control_mode": "demo",
        "latest_ac_state": "on" if bool(ac.get("isOn") or ac.get("is_on")) else "off",
        "latest_socket_state": "on" if bool(socket.get("isOn") or socket.get("is_on")) else "off",
        "latest_breaker_state": "simulation",
        "sensor_staleness_seconds": sensor_staleness,
        "breaker_staleness_seconds": breaker_staleness,
        **recent_history,
        **routine_context,
    }
    payload.setdefault("same_hour_usage_avg_kWh", payload.get("same_hour_energy_avg", 0))
    payload.setdefault("same_hour_usage_std_kWh", payload.get("same_hour_energy_std", 0))
    payload.setdefault("recent_power_avg_W", payload.get("recent_power_avg", 0))
    payload.setdefault("recent_power_std_W", payload.get("recent_power_std", 0))
    payload.setdefault("device_left_on_without_motion_minutes", payload.get("time_since_last_motion_minutes", payload.get("minutes_since_last_activity", 0)))
    payload.setdefault("outside_routine_score", payload.get("outside_routine_score", payload.get("routine_score", 0)))
    return payload, f"demo_scenario:{request.scenario_id}"


def mark_scenario_ai_output(value: Any) -> Any:
    if isinstance(value, dict):
        updated = {key: mark_scenario_ai_output(item) for key, item in value.items()}
        if updated.get("source") == "ai":
            updated["source"] = "scenario_ai"
        return updated
    if isinstance(value, list):
        return [mark_scenario_ai_output(item) for item in value]
    return value


SCENARIO_AI_MESSAGES: dict[str, dict[str, str]] = {
    "ac_left_on_empty": {
        "severity": "high",
        "category": "energy",
        "title": "AC appears left on",
        "message": "AC is drawing high power while no recent motion is detected.",
        "recommendation": "Turn off the AC or enable automatic control if the room is empty.",
        "recommendation_type": "turn_off_ac",
        "status_label": "Likely Waste",
        "status_tone": "danger",
        "action_title": "Turn off AC",
        "anomaly": "ac_left_on_without_occupancy",
        "device_id": "breaker_02",
    },
    "socket_left_on": {
        "severity": "medium",
        "category": "recommendation",
        "title": "Socket may be left on",
        "message": "Socket breaker is active while the home appears empty.",
        "recommendation": "Review the socket load and turn it off if it is not needed.",
        "recommendation_type": "turn_off_socket",
        "status_label": "Possible Waste",
        "status_tone": "warning",
        "action_title": "Turn off socket",
        "anomaly": "socket_left_on_without_occupancy",
        "device_id": "breaker_01",
    },
    "unusual_ac_routine": {
        "severity": "medium",
        "category": "routine",
        "title": "Unusual AC routine detected",
        "message": "AC is active outside the usual weekday pattern.",
        "recommendation": "Confirm whether the AC should stay on or adjust the AC schedule.",
        "recommendation_type": "review_ac_schedule",
        "status_label": "Unusual Routine",
        "status_tone": "warning",
        "action_title": "Confirm AC use",
        "anomaly": "ac_outside_weekday_routine",
        "device_id": "breaker_02",
    },
    "high_energy_consumption": {
        "severity": "medium",
        "category": "anomaly",
        "title": "High energy consumption detected",
        "message": "Current power is higher than the normal same-hour pattern.",
        "recommendation": "Check the AC and socket breakers for unnecessary load.",
        "recommendation_type": "review_unusual_energy_usage",
        "status_label": "Anomaly",
        "status_tone": "warning",
        "action_title": "Inspect breakers",
        "anomaly": "same_hour_energy_spike",
    },
    "smoke_gas_safety": {
        "severity": "critical",
        "category": "safety",
        "title": "Critical safety alert",
        "message": "Smoke or gas is detected in the room.",
        "recommendation": "Check the room immediately and turn off affected devices if safe.",
        "recommendation_type": "check_smoke_gas_sensor",
        "status_label": "Critical Safety",
        "status_tone": "critical",
        "action_title": "Check room now",
        "anomaly": "safety_smoke_gas_warning",
    },
    "stale_sensor_breaker": {
        "severity": "medium",
        "category": "system",
        "title": "Fresh data needed",
        "message": "Sensor or breaker readings are stale, so AI confidence is reduced.",
        "recommendation": "Check the ESP32, Pi agent, and breaker connection.",
        "recommendation_type": "check_sensor_breaker_data",
        "status_label": "Needs Data",
        "status_tone": "warning",
        "action_title": "Check connections",
        "anomaly": "stale_sensor_breaker_data",
    },
}


def apply_scenario_next_hour_fallback(ai_result: dict[str, Any], payload: dict[str, Any]) -> None:
    total_power_w = as_number(payload.get("total_power_for_guardrails_W"), as_number(payload.get("total_avg_power_W")))
    tariff = as_number(payload.get("tariff_BHD_per_kWh"), 0.032)
    fallback_energy = round(max(0.0, total_power_w) / 1000.0, 6)
    fallback_cost = round(fallback_energy * tariff, 6)
    current_energy = as_number(first_present(ai_result.get("next_hour_energy"), ai_result.get("next_hour_total_energy_kWh")), 0)
    if fallback_energy > 0 and current_energy <= 0:
        ai_result["next_hour_energy"] = fallback_energy
        ai_result["next_hour_cost"] = fallback_cost
    else:
        ai_result["next_hour_energy"] = current_energy
        ai_result["next_hour_cost"] = as_number(first_present(ai_result.get("next_hour_cost"), ai_result.get("next_hour_total_cost_BHD")), fallback_cost)
    ai_result["next_hour_total_energy_kWh"] = ai_result["next_hour_energy"]
    ai_result["next_hour_total_cost_BHD"] = ai_result["next_hour_cost"]
    predictions = as_dict(ai_result.get("predictions"))
    predictions["next_hour_total_energy_kWh"] = {
        **as_dict(predictions.get("next_hour_total_energy_kWh")),
        "value": ai_result["next_hour_energy"],
    }
    predictions["next_hour_total_cost_BHD"] = {
        **as_dict(predictions.get("next_hour_total_cost_BHD")),
        "value": ai_result["next_hour_cost"],
    }
    ai_result["predictions"] = predictions


def scenario_specific_notification(home_id: str, scenario_id: str) -> dict[str, Any] | None:
    spec = SCENARIO_AI_MESSAGES.get(scenario_id)
    if not spec:
        return None
    return ai_notification(
        home_id,
        spec["severity"],
        spec["category"],
        spec["title"],
        f"{spec['message']} {spec['recommendation']}",
        device_id=spec.get("device_id"),
        recommendation_type=spec.get("recommendation_type"),
        confidence=0.92 if spec["severity"] in {"high", "critical"} else 0.86,
        explanation=spec["recommendation"],
        notification_id=f"scenario_{scenario_id}",
    )


def apply_scenario_ai_overrides(ai_result: dict[str, Any], request: AiScenarioPredictRequest) -> None:
    spec = SCENARIO_AI_MESSAGES.get(request.scenario_id)
    if not spec:
        return
    recommendation = spec["recommendation"]
    message = spec["message"]
    ai_result["abnormal_usage"] = spec["anomaly"]
    ai_result["recommendation_type"] = spec["recommendation_type"]
    ai_result["ai_status_label"] = spec["status_label"]
    ai_result["ai_status_tone"] = spec["status_tone"]
    ai_result["ai_status_summary"] = message
    ai_result["ai_action_title"] = spec["action_title"]
    ai_result["explanation"] = recommendation
    predictions = as_dict(ai_result.get("predictions"))
    predictions["anomaly_label"] = {"value": spec["anomaly"], "confidence": 0.9, "source": "scenario_ai_override"}
    predictions["recommendation_type"] = {"value": spec["recommendation_type"], "confidence": 0.9, "source": "scenario_ai_override"}
    predictions["explanation"] = recommendation
    ai_result["predictions"] = predictions


def run_scenario_ai_prediction(home_id: str, request: AiScenarioPredictRequest) -> dict[str, Any]:
    payload, input_source = build_ai_payload_from_scenario(home_id, request)
    safety_notifications = run_immediate_safety_checks(home_id, payload)
    routine_notifications = run_lightweight_anomaly_checks(home_id, payload)
    ml_ran = True
    try:
        prediction = ai_engine.run_model(payload)
    except Exception:
        ml_ran = False
        prediction = {
            "model_name": "smart_energy_ai",
            "model_version": "scenario_rule_only",
            "prediction_status": "scenario_rule_checks_only",
            "waste_event": {"value": bool(safety_notifications or routine_notifications), "confidence": 0.75, "source": "scenario_rules"},
            "anomaly_label": {"value": "scenario_rule_based_alert" if safety_notifications or routine_notifications else "normal", "confidence": 0.75, "source": "scenario_rules"},
            "recommendation_type": {"value": "review_ai_notifications" if safety_notifications or routine_notifications else "none", "confidence": 0.75, "source": "scenario_rules"},
            "next_hour_total_energy_kWh": {"value": as_number(payload.get("same_hour_energy_avg"), as_number(payload.get("recent_energy_avg")))},
            "next_hour_total_cost_BHD": {"value": as_number(payload.get("same_hour_energy_avg"), as_number(payload.get("recent_energy_avg"))) * as_number(payload.get("tariff_BHD_per_kWh"), 0.032)},
            "energy_efficiency_score": 70 if safety_notifications or routine_notifications else 95,
            "explanation": "Scenario rule checks ran because the ML model could not be used for this simulated input.",
            "post_processing_rules": ["scenario_rule_checks_without_full_ml"],
        }
    ai_result = ai_engine.build_ai_result(home_id, payload, prediction, input_source, request.scenario_id)
    ai_result = apply_ec2_ai_routine_rules(ai_result, payload)
    apply_scenario_ai_overrides(ai_result, request)
    apply_scenario_next_hour_fallback(ai_result, payload)
    ai_result.update(
        {
            "simulation": True,
            "source": "scenario_ai",
            "input_source": input_source,
            "scenario_id": request.scenario_id,
            "scenario_name": request.scenario_name,
            "scenario_description": request.scenario_description,
            "ml_ran": ml_ran,
            "levels_ran": ["immediate_safety", "lightweight_routine"] + (["full_ml"] if ml_ran else []),
        }
    )
    scenario_notification = scenario_specific_notification(home_id, request.scenario_id)
    notifications = dedupe_ai_notifications(
        ([scenario_notification] if scenario_notification else [])
        + safety_notifications
        + routine_notifications
        + build_ai_notifications(home_id, ai_result, payload)
    )
    notifications = [dict(item, source="scenario_ai", simulation=True) for item in notifications]
    alerts = [item for item in notifications if item["severity"] in {"high", "critical"}]
    suggestions = [item for item in notifications if item["category"] == "recommendation"]
    ai_result["notifications"] = notifications
    ai_result["alerts"] = alerts
    ai_result["suggestions"] = suggestions
    response = normalized_ai_api_response(home_id, ai_result)
    response["simulation"] = True
    response["scenario_id"] = request.scenario_id
    response["scenario_name"] = request.scenario_name
    return mark_scenario_ai_output(response)


def start_ai_prediction_scheduler() -> None:
    global _ai_prediction_scheduler_started
    if _ai_prediction_scheduler_started or not AI_AUTO_PREDICT_ENABLED or not AI_PREDICTION_HOME_IDS:
        return
    _ai_prediction_scheduler_started = True

    def prediction_loop() -> None:
        if AI_PREDICTION_INITIAL_DELAY_SECONDS:
            time.sleep(AI_PREDICTION_INITIAL_DELAY_SECONDS)
        while True:
            for home_id in AI_PREDICTION_HOME_IDS:
                try:
                    result = run_ec2_ai_prediction(home_id)
                    ai_result = as_dict(result.get("ai_result"))
                    print(
                        "[AI SCHEDULER] "
                        f"home={home_id} status={ai_result.get('prediction_status')} "
                        f"summary={ai_result.get('ai_status_summary')}",
                        flush=True,
                    )
                except Exception as error:
                    print(f"[AI SCHEDULER] home={home_id} failed: {error}", flush=True)
            time.sleep(AI_PREDICTION_INTERVAL_SECONDS)

    thread = threading.Thread(target=prediction_loop, name="ai-prediction-scheduler", daemon=True)
    thread.start()


def run_ec2_ai_prediction(home_id: str, *, force_full_ml: bool = False) -> dict[str, Any]:
    payload, input_source = ai_engine.build_ai_payload(home_id)
    payload = enrich_ai_payload_with_history(home_id, payload)
    safety_notifications = run_immediate_safety_checks(home_id, payload)
    routine_notifications = run_lightweight_anomaly_checks(home_id, payload)
    ml_ran = should_run_full_ml(home_id, force=force_full_ml, input_source=input_source)
    if ml_ran:
        prediction = ai_engine.run_model(payload)
        ai_result = ai_engine.build_ai_result(home_id, payload, prediction, input_source)
        ai_result = apply_ec2_ai_routine_rules(ai_result, payload)
        _ai_last_full_prediction_ms_by_home[home_id] = now_ms()
    else:
        prediction = {
            "model_name": "smart_energy_ai",
            "model_version": "rule_only",
            "prediction_status": "rule_checks_only",
            "waste_event": {"value": any(item.get("category") == "energy" for item in safety_notifications + routine_notifications), "confidence": 0.75, "source": "rule_checks"},
            "anomaly_label": {"value": "rule_based_alert" if safety_notifications or routine_notifications else "normal", "confidence": 0.75, "source": "rule_checks"},
            "recommendation_type": {"value": "review_ai_notifications" if safety_notifications or routine_notifications else "none", "confidence": 0.75, "source": "rule_checks"},
            "next_hour_total_energy_kWh": {"value": as_number(payload.get("same_hour_energy_avg"), as_number(payload.get("recent_energy_avg")))},
            "next_hour_total_cost_BHD": {"value": as_number(payload.get("same_hour_energy_avg"), as_number(payload.get("recent_energy_avg"))) * as_number(payload.get("tariff_BHD_per_kWh"), 0.032)},
            "energy_efficiency_score": 70 if safety_notifications or routine_notifications else 95,
            "explanation": "Rule-based AI checks ran. Full ML is scheduled hourly after hourly summaries, not on every live update.",
            "post_processing_rules": ["rule_checks_without_full_ml"],
        }
        ai_result = ai_engine.build_ai_result(home_id, payload, prediction, input_source)
    ai_result["source"] = "ec2_ai_inference"
    ai_result["ml_ran"] = ml_ran
    ai_result["levels_ran"] = ["immediate_safety", "lightweight_routine"] + (["full_ml"] if ml_ran else [])
    ai_result["anomaly_score"] = 1.0 - as_number(ai_result.get("efficiency_score"), 100) / 100
    ai_result["anomaly_label"] = ai_result.get("abnormal_usage")
    ai_result["waste_event"] = ai_result.get("energy_waste")
    ai_result["next_hour_total_energy_kWh"] = ai_result.get("next_hour_energy")
    ai_result["next_hour_total_cost_BHD"] = ai_result.get("next_hour_cost")
    notifications = dedupe_ai_notifications(safety_notifications + routine_notifications + build_ai_notifications(home_id, ai_result, payload))
    alerts = [item for item in notifications if item["severity"] in {"high", "critical"}]
    suggestions = [item for item in notifications if item["category"] == "recommendation"]
    ai_result["notifications"] = notifications
    ai_result["alerts"] = alerts
    ai_result["suggestions"] = suggestions
    stored = store_ai_result(home_id, ai_result, notifications=notifications, alerts=alerts, suggestions=suggestions)
    return normalized_ai_api_response(home_id, stored)


@app.post("/api/home/{home_id}/ai/predict", dependencies=[Depends(require_home_role("admin"))])
def trigger_ai_prediction(home_id: str) -> dict[str, Any]:
    return run_ec2_ai_prediction(home_id, force_full_ml=True)


@app.post("/api/homes/{home_id}/ai/predict", dependencies=[Depends(require_home_role("admin"))])
def trigger_ai_prediction_plural(home_id: str) -> dict[str, Any]:
    return run_ec2_ai_prediction(home_id, force_full_ml=True)


@app.post("/api/homes/{home_id}/ai/scenario-predict", dependencies=[Depends(require_home_permission("can_view"))])
def trigger_ai_scenario_prediction(home_id: str, request: AiScenarioPredictRequest) -> dict[str, Any]:
    return run_scenario_ai_prediction(home_id, request)


@app.get("/api/homes/{home_id}/ai/latest", dependencies=[Depends(require_home_permission("can_view"))])
def get_ai_latest_result(home_id: str) -> dict[str, Any]:
    latest = get_ai_latest(home_id)
    return normalized_ai_api_response(home_id, latest)


@app.get("/api/homes/{home_id}/ai/history", dependencies=[Depends(require_home_permission("can_view"))])
def get_ai_history_results(home_id: str, limit: int = Query(24, ge=1, le=100)) -> dict[str, Any]:
    history = query_ai_history(home_id, limit=limit)
    return {"success": True, "home_id": home_id, "count": len(history), "history": history}


@app.get("/api/homes/{home_id}/ai/notifications", dependencies=[Depends(require_home_permission("can_view"))])
def get_ai_notification_results(
    home_id: str,
    limit: int = Query(50, ge=1, le=100),
    severity: str | None = None,
    category: str | None = None,
    acknowledged: bool | None = None,
) -> dict[str, Any]:
    notifications = query_ai_notifications(home_id, limit=limit)
    if severity:
        notifications = [item for item in notifications if str(item.get("severity")).lower() == severity.lower()]
    if category:
        notifications = [item for item in notifications if str(item.get("category")).lower() == category.lower()]
    if acknowledged is not None:
        notifications = [item for item in notifications if bool(item.get("acknowledged")) is acknowledged]
    return {"success": True, "home_id": home_id, "count": len(notifications), "notifications": notifications}


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
