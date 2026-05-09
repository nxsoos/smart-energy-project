from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from tuya_connector import TUYA_LOGGER, TuyaOpenAPI

from local_state_store import home_ref

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")
load_dotenv()

from home_assistant_controller import (  # noqa: E402
    HomeAssistantError,
    execute_home_assistant_command,
    get_entity_state,
)
from timestamp_utils import TIMEZONE, ms_to_iso, now_ms  # noqa: E402


HOME_ID = os.environ.get("HOME_ID", "home_001")
TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID", "")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET", "")
TUYA_API_ENDPOINT = os.environ.get("TUYA_API_ENDPOINT", "https://openapi.tuyaeu.com")
TUYA_VERIFY_ATTEMPTS = int(os.environ.get("TUYA_VERIFY_ATTEMPTS", "7"))
LOCAL_COMMAND_VERIFY_DELAY_SECONDS = float(os.environ.get("LOCAL_COMMAND_VERIFY_DELAY_SECONDS", "1.5"))
LOCAL_HA_STATE_SYNC_INTERVAL_SECONDS = float(os.environ.get("LOCAL_HA_STATE_SYNC_INTERVAL_SECONDS", "5"))

TUYA_DEVICES = {
    "breaker_01": {
        "name": "Switch Breaker",
        "tuya_device_id": os.environ.get("TUYA_BREAKER_01_DEVICE_ID", ""),
        "command_code": "switch",
        "fallback_codes": ["switch_1"],
    },
    "breaker_02": {
        "name": "AC Breaker",
        "tuya_device_id": os.environ.get("TUYA_BREAKER_02_DEVICE_ID", ""),
        "command_code": "switch",
        "fallback_codes": ["switch_1"],
    },
}

HA_ENTITY_ENV = {
    "matter_socket_switch": "MATTER_SOCKET_SWITCH_ENTITY_ID",
    "matter_ac_switch": "MATTER_AC_SWITCH_ENTITY_ID",
}
HA_DEVICE_NAMES = {
    "matter_socket_switch": "Socket Switch",
    "matter_ac_switch": "AC Switch",
}

_TUYA_CLOUD: TuyaOpenAPI | None = None
_LAST_HA_STATE_SYNC_MS = 0


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "on", "yes", "online"}:
            return True
        if normalized in {"false", "0", "off", "no", "offline"}:
            return False
    return None


def target_state_for_action(action: str) -> str:
    return "on" if action == "turn_on" else "off"


def current_state_from_device(device: dict[str, Any]) -> str:
    status = as_dict(device.get("status"))
    switch = normalize_bool(status.get("switch"))
    if switch is True:
        return "on"
    if switch is False:
        return "off"
    state = str(device.get("display_state") or device.get("state") or "").strip().lower()
    return state if state in {"on", "off"} else "unknown"


def device_name(device_id: str, device: dict[str, Any]) -> str:
    return str(device.get("name") or TUYA_DEVICES.get(device_id, {}).get("name") or device_id)


def friendly_error(raw_error: Any, fallback_code: str = "COMMAND_FAILED") -> dict[str, str]:
    text = str(raw_error or "").lower()
    if "offline" in text:
        return {
            "error_code": "DEVICE_OFFLINE",
            "user_message": "Device is offline. Check power or Wi-Fi connection.",
        }
    if "timeout" in text or "timed out" in text:
        return {
            "error_code": "COMMAND_TIMEOUT",
            "user_message": "Device did not respond in time.",
        }
    if "home_assistant_unreachable" in text or "local controller is unavailable" in text:
        return {
            "error_code": "HOME_ASSISTANT_UNREACHABLE",
            "user_message": "Local controller is unavailable.",
        }
    if "ha_entity_not_found" in text:
        return {
            "error_code": "HA_ENTITY_NOT_FOUND",
            "user_message": "Matter switch was not found in Home Assistant.",
        }
    if "ha_state_unknown" in text:
        return {
            "error_code": "HA_STATE_UNKNOWN",
            "user_message": "Matter switch state is unknown.",
        }
    if "permission" in text or "auth" in text or "sign" in text or "token" in text:
        return {
            "error_code": "PERMISSION_ERROR",
            "user_message": "Device control permission failed.",
        }
    if "state did not change" in text or "did not change breaker state" in text:
        return {
            "error_code": "STATE_NOT_CHANGED",
            "user_message": "Command was sent, but the device state did not change.",
        }
    return {
        "error_code": fallback_code,
        "user_message": "Command failed. Please try again.",
    }


def local_ref(path: str):
    return home_ref(HOME_ID, path)


def write_command_state(
    device_id: str,
    command: dict[str, Any],
    updates: dict[str, Any],
    *,
    remove_pending: bool = False,
) -> dict[str, Any]:
    command_id = str(command.get("command_id") or "")
    if not command_id:
        return command

    updated_command = {**command, **updates}
    if remove_pending:
        local_ref(f"commands/pending/{command_id}").delete()
    else:
        local_ref(f"commands/pending/{command_id}").update(updates)

    local_ref(f"commands/history/{command_id}").set(updated_command)
    local_ref(f"commands/latest_by_device/{device_id}").set(updated_command)
    local_ref(f"commands/{device_id}/latest").set(
        {
            **updated_command,
            "created_at": updated_command.get("created_at_ms"),
        }
    )
    return updated_command


def create_pending_command(
    device_id: str,
    action: str,
    *,
    requested_by: str,
    source: str,
    emergency: bool,
    alert_id: str | None,
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    timestamp_iso = ms_to_iso(timestamp_ms)
    device = as_dict(local_ref(f"devices/{device_id}").get())
    command_id = f"cmd_{timestamp_ms}_{device_id}"
    target_state = target_state_for_action(action)
    previous_state = current_state_from_device(device)
    control_method = str(
        device.get("control_method")
        or ("tuya_cloud" if device_id.startswith("breaker_") else "home_assistant")
    ).lower()

    command = {
        "command_id": command_id,
        "home_id": HOME_ID,
        "device_id": device_id,
        "device_name": device_name(device_id, device),
        "command": action,
        "action": action,
        "target_state": target_state,
        "previous_state": previous_state,
        "requested_by": requested_by,
        "source": source,
        "emergency": emergency,
        "alert_id": alert_id,
        "control_method": control_method,
        "ha_entity_id": device.get("ha_entity_id"),
        "status": "pending",
        "requested_at_ms": timestamp_ms,
        "requested_at_iso": timestamp_iso,
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": timestamp_iso,
        "timezone": TIMEZONE,
        "sent_at_ms": None,
        "sent_at_iso": None,
        "confirmed_at_ms": None,
        "confirmed_at_iso": None,
        "failed_at_ms": None,
        "failed_at_iso": None,
        "result": {
            "success": None,
            "actual_state": None,
            "error_code": None,
            "user_message": None,
            "raw_error": None,
        },
    }

    local_ref(f"commands/pending/{command_id}").set(command)
    local_ref(f"commands/history/{command_id}").set(command)
    local_ref(f"commands/latest_by_device/{device_id}").set(command)
    local_ref(f"commands/{device_id}/latest").set({**command, "created_at": timestamp_ms})
    local_ref(f"devices/{device_id}").update(
        {
            "command_in_progress": True,
            "pending_command_id": command_id,
            "pending_target_state": target_state,
            "last_requested_state": target_state,
            "last_command_status": "pending",
            "last_command_message": "Command accepted locally.",
            "last_command": {
                "status": "pending",
                "user_message": "Command accepted locally.",
                "error_code": None,
            },
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": timestamp_iso,
        }
    )
    return command


def mark_command_sent(device_id: str, command: dict[str, Any]) -> dict[str, Any]:
    timestamp_ms = now_ms()
    return write_command_state(
        device_id,
        command,
        {
            "status": "sent",
            "sent_at_ms": timestamp_ms,
            "sent_at_iso": ms_to_iso(timestamp_ms),
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": ms_to_iso(timestamp_ms),
            "timezone": TIMEZONE,
        },
    )


def mark_command_done(
    device_id: str,
    command: dict[str, Any],
    relay_on: bool,
    *,
    no_action: bool = False,
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    timestamp_iso = ms_to_iso(timestamp_ms)
    state = "on" if relay_on else "off"
    message = (
        f"{command.get('device_name', device_id)} already {state}."
        if no_action
        else f"{command.get('device_name', device_id)} turned {state} successfully."
    )
    updates = {
        "status": "confirmed",
        "confirmed_at_ms": timestamp_ms,
        "confirmed_at_iso": timestamp_iso,
        "executed_at_ms": timestamp_ms,
        "executed_at_iso": timestamp_iso,
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": timestamp_iso,
        "timezone": TIMEZONE,
        "no_action": no_action,
        "result": {
            **as_dict(command.get("result")),
            "success": True,
            "actual_state": state,
            "error_code": None,
            "user_message": message,
            "raw_error": None,
        },
    }
    updated_command = write_command_state(device_id, command, updates, remove_pending=True)
    current_device = as_dict(local_ref(f"devices/{device_id}").get())
    current_status = as_dict(current_device.get("status"))
    next_status = {
        **current_status,
        "switch": relay_on,
        "relay_status": state,
        "online": True,
        "lastSeenMs": timestamp_ms,
        "last_seen_ms": timestamp_ms,
        "last_seen_iso": timestamp_iso,
        "last_command_id": command.get("command_id"),
    }
    local_ref(f"devices/{device_id}").update(
        {
            "state": state,
            "display_state": state,
            "status": next_status,
            "command_in_progress": False,
            "pending_command_id": None,
            "pending_target_state": None,
            "last_requested_state": state,
            "last_command_status": "confirmed",
            "last_command_message": message,
            "last_command": {
                "status": "confirmed",
                "user_message": message,
                "error_code": None,
            },
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": timestamp_iso,
        }
    )
    return updated_command


def mark_command_failed(
    device_id: str,
    command: dict[str, Any],
    error_message: Any,
    *,
    actual_state: str | None = None,
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    timestamp_iso = ms_to_iso(timestamp_ms)
    mapped = friendly_error(error_message)
    state_update = actual_state or command.get("previous_state") or "unknown"
    updates = {
        "status": "failed",
        "error": mapped["user_message"],
        "failed_at_ms": timestamp_ms,
        "failed_at_iso": timestamp_iso,
        "executed_at_ms": timestamp_ms,
        "executed_at_iso": timestamp_iso,
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": timestamp_iso,
        "timezone": TIMEZONE,
        "result": {
            **as_dict(command.get("result")),
            "success": False,
            "actual_state": state_update,
            "error_code": mapped["error_code"],
            "user_message": mapped["user_message"],
            "raw_error": str(error_message),
        },
    }
    updated_command = write_command_state(device_id, command, updates, remove_pending=True)
    local_ref(f"devices/{device_id}").update(
        {
            "state": state_update if state_update in {"on", "off", "unknown"} else "unknown",
            "display_state": state_update if state_update in {"on", "off", "unknown"} else "unknown",
            "command_in_progress": False,
            "pending_command_id": None,
            "pending_target_state": None,
            "last_command_status": "failed",
            "last_command_message": mapped["user_message"],
            "last_command": {
                "status": "failed",
                "user_message": mapped["user_message"],
                "error_code": mapped["error_code"],
            },
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": timestamp_iso,
        }
    )
    return updated_command


def initialize_tuya_cloud() -> TuyaOpenAPI:
    global _TUYA_CLOUD
    if _TUYA_CLOUD is None:
        TUYA_LOGGER.setLevel("INFO")
        cloud = TuyaOpenAPI(TUYA_API_ENDPOINT, TUYA_ACCESS_ID, TUYA_ACCESS_SECRET)
        cloud.connect()
        _TUYA_CLOUD = cloud
    return _TUYA_CLOUD


def fetch_tuya_status(cloud: TuyaOpenAPI, tuya_device_id: str) -> dict[str, Any]:
    response = cloud.get(f"/v1.0/devices/{tuya_device_id}/status")
    if not isinstance(response, dict) or response.get("success") is not True:
        raise RuntimeError(f"Tuya status read failed: {response}")
    return {
        str(item["code"]): item.get("value")
        for item in response.get("result", [])
        if isinstance(item, dict) and "code" in item
    }


def fetch_tuya_device_online(cloud: TuyaOpenAPI, tuya_device_id: str) -> bool:
    response = cloud.get(f"/v1.0/devices/{tuya_device_id}")
    if not isinstance(response, dict) or response.get("success") is not True:
        raise RuntimeError(f"Tuya device read failed: {response}")
    return normalize_bool(as_dict(response.get("result")).get("online")) is True


def send_tuya_command_with_code(
    cloud: TuyaOpenAPI,
    tuya_device_id: str,
    code: str,
    turn_on: bool,
) -> None:
    response = cloud.post(
        f"/v1.0/devices/{tuya_device_id}/commands",
        {"commands": [{"code": code, "value": turn_on}]},
    )
    if not isinstance(response, dict) or response.get("success") is not True:
        raise RuntimeError(f"Tuya command API failed for code={code}: {response}")


def wait_for_tuya_switch_state(
    cloud: TuyaOpenAPI,
    tuya_device_id: str,
    expected_state: bool,
    switch_code: str,
) -> bool:
    for _ in range(TUYA_VERIFY_ATTEMPTS):
        time.sleep(1)
        status = fetch_tuya_status(cloud, tuya_device_id)
        actual_state = status.get(switch_code)
        if actual_state is None and switch_code != "switch":
            actual_state = status.get("switch")
        if actual_state is expected_state:
            return True
    return False


def execute_tuya_command(device_id: str, action: str, command: dict[str, Any]) -> tuple[bool, bool]:
    if device_id not in TUYA_DEVICES:
        raise RuntimeError(f"Unknown Tuya device_id: {device_id}")
    config = TUYA_DEVICES[device_id]
    cloud = initialize_tuya_cloud()
    tuya_device_id = config["tuya_device_id"]
    if not fetch_tuya_device_online(cloud, tuya_device_id):
        raise RuntimeError("Device offline")

    turn_on = action == "turn_on"
    status = fetch_tuya_status(cloud, tuya_device_id)
    switch_code = config["command_code"]
    current = status.get(switch_code)
    if current is None:
        current = status.get("switch")
    if current is turn_on:
        mark_command_done(device_id, command, turn_on, no_action=True)
        return True, True

    sent_command = mark_command_sent(device_id, command)
    codes_to_try = []
    for code in [config["command_code"], *config.get("fallback_codes", [])]:
        if code not in codes_to_try:
            codes_to_try.append(code)

    last_error: Any = None
    for code in codes_to_try:
        try:
            send_tuya_command_with_code(cloud, tuya_device_id, code, turn_on)
            if wait_for_tuya_switch_state(cloud, tuya_device_id, turn_on, code):
                mark_command_done(device_id, sent_command, turn_on)
                return True, False
            last_error = f"Tuya command accepted but state did not change for code={code}"
        except Exception as error:
            last_error = error

    raise RuntimeError(last_error or "Tuya command did not change breaker state")


def ha_entity_for_device(device_id: str, device: dict[str, Any]) -> str:
    entity_id = str(device.get("ha_entity_id") or "").strip()
    if entity_id:
        return entity_id
    env_key = HA_ENTITY_ENV.get(device_id)
    return os.environ.get(env_key, "").strip() if env_key else ""


def log_ha_config(device_id: str, entity_id: str) -> None:
    env_key = HA_ENTITY_ENV.get(device_id, "")
    print(
        "[LOCAL HA DEBUG] "
        f"device={device_id} env_key={env_key or '<none>'} "
        f"entity={entity_id or '<missing>'} "
        f"ha_url_configured={bool(os.environ.get('HOME_ASSISTANT_URL', '').strip())} "
        f"ha_token_configured={bool(os.environ.get('HOME_ASSISTANT_TOKEN', '').strip())}",
        flush=True,
    )


def sync_home_assistant_device_states(force: bool = False) -> None:
    global _LAST_HA_STATE_SYNC_MS

    current_ms = now_ms()
    if (
        not force
        and current_ms - _LAST_HA_STATE_SYNC_MS < LOCAL_HA_STATE_SYNC_INTERVAL_SECONDS * 1000
    ):
        return
    _LAST_HA_STATE_SYNC_MS = current_ms

    for device_id, env_key in HA_ENTITY_ENV.items():
        timestamp_ms = now_ms()
        timestamp_iso = ms_to_iso(timestamp_ms)
        current_device = as_dict(local_ref(f"devices/{device_id}").get())
        entity_id = ha_entity_for_device(device_id, current_device)
        base_payload = {
            "type": "matter_switch",
            "name": current_device.get("name") or HA_DEVICE_NAMES.get(device_id, device_id),
            "control_method": "home_assistant",
            "ha_entity_id": entity_id or os.environ.get(env_key, "").strip(),
            "cloud_online": False,
            "energy_supported": False,
            "controllable": True,
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": timestamp_iso,
        }

        if not base_payload["ha_entity_id"]:
            local_ref(f"devices/{device_id}").update(
                {
                    **base_payload,
                    "online": False,
                    "local_online": False,
                    "state": "unknown",
                    "display_state": "unknown",
                    "last_command_message": f"{env_key} is not configured.",
                    "last_command": {
                        "status": "failed",
                        "user_message": f"{env_key} is not configured.",
                        "error_code": "HA_ENTITY_NOT_FOUND",
                    },
                }
            )
            continue

        try:
            state = get_entity_state(str(base_payload["ha_entity_id"]))
            switch_on = state == "on"
            local_ref(f"devices/{device_id}").update(
                {
                    **base_payload,
                    "online": True,
                    "local_online": True,
                    "state": state,
                    "display_state": state,
                    "status": {
                        **as_dict(current_device.get("status")),
                        "online": True,
                        "switch": switch_on,
                        "relay_status": state,
                        "lastSeenMs": timestamp_ms,
                        "last_seen_ms": timestamp_ms,
                        "last_seen_iso": timestamp_iso,
                    },
                }
            )
        except HomeAssistantError as error:
            local_ref(f"devices/{device_id}").update(
                {
                    **base_payload,
                    "online": False,
                    "local_online": False,
                    "state": "unknown",
                    "display_state": "unknown",
                    "last_command_message": error.user_message,
                    "last_command": {
                        "status": "failed",
                        "user_message": error.user_message,
                        "error_code": error.code,
                    },
                }
            )


def execute_ha_command(device_id: str, action: str, command: dict[str, Any]) -> tuple[bool, bool]:
    device = as_dict(local_ref(f"devices/{device_id}").get())
    entity_id = ha_entity_for_device(device_id, device)
    log_ha_config(device_id, entity_id)
    if not entity_id:
        raise HomeAssistantError(
            "HA_ENTITY_NOT_FOUND",
            "Matter switch was not found in Home Assistant.",
            "Missing ha_entity_id or entity-id environment variable.",
        )

    target_state = target_state_for_action(action)
    print(
        f"[LOCAL HA DEBUG] command={command.get('command_id')} "
        f"device={device_id} action={action} target={target_state} entity={entity_id}",
        flush=True,
    )
    current_state = get_entity_state(entity_id)
    print(
        f"[LOCAL HA DEBUG] current_state device={device_id} entity={entity_id} state={current_state}",
        flush=True,
    )
    if current_state == target_state:
        mark_command_done(device_id, command, action == "turn_on", no_action=True)
        return True, True

    sent_command = mark_command_sent(device_id, command)
    execute_home_assistant_command(entity_id, action)
    time.sleep(LOCAL_COMMAND_VERIFY_DELAY_SECONDS)
    actual_state = get_entity_state(entity_id)
    print(
        f"[LOCAL HA DEBUG] verified_state device={device_id} entity={entity_id} state={actual_state}",
        flush=True,
    )
    if actual_state != target_state:
        raise HomeAssistantError(
            "HA_COMMAND_FAILED",
            "Matter switch command failed. Please try again.",
            f"Expected {target_state}, got {actual_state}.",
        )
    mark_command_done(device_id, sent_command, action == "turn_on")
    return True, False


def execute_local_command(
    device_id: str,
    action: str,
    *,
    requested_by: str = "pi_dashboard",
    source: str = "pi_dashboard",
    emergency: bool = False,
    alert_id: str | None = None,
) -> dict[str, Any]:
    if device_id.startswith("matter_"):
        sync_home_assistant_device_states(force=True)
    command = create_pending_command(
        device_id,
        action,
        requested_by=requested_by,
        source=source,
        emergency=emergency,
        alert_id=alert_id,
    )
    control_method = str(command.get("control_method") or "").lower()

    try:
        if control_method == "home_assistant":
            success, no_action = execute_ha_command(device_id, action, command)
        elif control_method == "tuya_cloud":
            success, no_action = execute_tuya_command(device_id, action, command)
        else:
            raise RuntimeError(f"Unsupported control_method: {control_method}")

        latest = as_dict(local_ref(f"commands/latest_by_device/{device_id}").get())
        message = as_dict(latest.get("result")).get("user_message") or "Command completed."
        return {
            "success": success,
            "no_action": no_action,
            "status": "confirmed",
            "message": message,
            "command_id": command["command_id"],
        }
    except Exception as error:
        error_message = f"{error.code}: {error.user_message}" if isinstance(error, HomeAssistantError) else str(error)
        print(f"[LOCAL COMMAND ERROR] {device_id} {action}: {error_message}", flush=True)
        traceback.print_exc()
        failed = mark_command_failed(device_id, command, error_message)
        result = as_dict(failed.get("result"))
        return {
            "success": False,
            "status": "failed",
            "message": result.get("user_message") or "Command failed.",
            "command_id": command["command_id"],
            "error_code": result.get("error_code"),
        }
