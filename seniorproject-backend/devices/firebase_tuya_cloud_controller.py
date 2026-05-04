import time
import traceback
import sys
from pathlib import Path
from typing import Dict, Any

import firebase_admin
from firebase_admin import credentials, db

from tuya_connector import TuyaOpenAPI, TUYA_LOGGER

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from timestamp_utils import TIMEZONE, ms_to_iso, now_ms

# Raspberry Pi hub role:
# This is the default production script to run from main.py. It watches Firebase
# command requests, sends ON/OFF commands to Tuya Cloud, and writes command
# results back to Firebase.

# ============================================================
# Firebase settings
# ============================================================

SERVICE_ACCOUNT_PATH = "serviceAccountKey.json"

DATABASE_URL = (
    "https://seniorproject-energy-default-rtdb.asia-southeast1."
    "firebasedatabase.app"
)

HOME_ID = "home_001"
POLL_INTERVAL_SECONDS = 0.2
COMMAND_MAX_AGE_MS = 2 * 60 * 1000


# ============================================================
# Tuya Cloud settings
# ============================================================

# From Tuya IoT Platform project overview:
TUYA_ACCESS_ID = "wsxgdxhatq8h7jmnr97n"
TUYA_ACCESS_SECRET = "49a3750db4434937a1f725c8b1e28e82"

# Your Tuya project says Central Europe.
TUYA_API_ENDPOINT = "https://openapi.tuyaeu.com"


# ============================================================
# Device settings
# ============================================================

DEVICES = {
    "breaker_01": {
        "name": "Switch Breaker",
        "tuya_device_id": "bfdd92cd1b6554f95c0h2a",
        # Common Tuya switch command codes: "switch", "switch_1"
        # We will try command_code first, then fallback_codes.
        "command_code": "switch",
        "fallback_codes": ["switch_1"],
    },
    "breaker_02": {
        "name": "AC Breaker",
        "tuya_device_id": "bf97ff360135427784mm8v",
        "command_code": "switch",
        "fallback_codes": ["switch_1"],
    },
}


# ============================================================
# Helpers
# ============================================================

def as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def readable_time() -> str:
    return ms_to_iso(now_ms()) or ""


def readable_iso() -> str:
    return ms_to_iso(now_ms()) or ""


def initialize_firebase() -> None:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(
            cred,
            {
                "databaseURL": DATABASE_URL,
            },
        )


def firebase_ref(path: str):
    return db.reference(path)


def get_command_ref(device_id: str):
    return firebase_ref(f"/homes/{HOME_ID}/commands/{device_id}/latest")


def get_pending_commands_ref():
    return firebase_ref(f"/homes/{HOME_ID}/commands/pending")


def get_pending_command_ref(command_id: str):
    return firebase_ref(f"/homes/{HOME_ID}/commands/pending/{command_id}")


def get_latest_by_device_ref(device_id: str):
    return firebase_ref(f"/homes/{HOME_ID}/commands/latest_by_device/{device_id}")


def get_device_status_ref(device_id: str):
    return firebase_ref(f"/homes/{HOME_ID}/devices/{device_id}/status")


def get_device_ref(device_id: str):
    return firebase_ref(f"/homes/{HOME_ID}/devices/{device_id}")


def get_command_history_ref(command_id: str):
    return firebase_ref(f"/homes/{HOME_ID}/commands/history/{command_id}")


def is_valid_command(command: Dict[str, Any], device_id: str) -> bool:
    if not command:
        return False

    if command.get("status") != "pending":
        return False

    if command.get("device_id") != device_id:
        return False

    action = command.get("action") or command.get("command")
    if action not in ["turn_on", "turn_off"]:
        return False

    if not command.get("command_id"):
        return False

    return True


def command_timestamp_ms(command: Dict[str, Any]) -> int:
    return as_int(
        command.get("requested_at_ms")
        or command.get("created_at")
        or command.get("timestamp_ms")
    )


def is_stale_command(command: Dict[str, Any]) -> bool:
    timestamp_ms = command_timestamp_ms(command)
    return timestamp_ms <= 0 or now_ms() - timestamp_ms > COMMAND_MAX_AGE_MS


def target_state_for_action(action: str) -> str:
    return "on" if action == "turn_on" else "off"


def action_for_command(command: Dict[str, Any]) -> str:
    return str(command.get("action") or command.get("command") or "").strip()


def command_message(device_id: str, state: str) -> str:
    name = DEVICES.get(device_id, {}).get("name", device_id)
    return f"{name} turned {state} successfully."


def friendly_error(raw_error: Any, fallback_code: str = "COMMAND_FAILED") -> Dict[str, Any]:
    text = str(raw_error or "").lower()
    if "offline" in text or "no breaker voltage" in text:
        return {
            "error_code": "DEVICE_OFFLINE",
            "user_message": "Device is offline. Check power or Wi-Fi connection.",
        }
    if "timeout" in text or "timed out" in text:
        return {
            "error_code": "COMMAND_TIMEOUT",
            "user_message": "Device did not respond in time.",
        }
    if "permission" in text or "auth" in text or "sign" in text or "token" in text:
        return {
            "error_code": "PERMISSION_ERROR",
            "user_message": "Device control permission failed.",
        }
    if "state did not change" in text or "did not change breaker state" in text:
        return {
            "error_code": "STATE_NOT_CHANGED",
            "user_message": "Command was sent, but the breaker state did not change.",
        }
    if fallback_code == "STATE_NOT_CHANGED":
        return {
            "error_code": "STATE_NOT_CHANGED",
            "user_message": "Command was sent, but the breaker state did not change.",
        }
    return {
        "error_code": fallback_code,
        "user_message": "Command failed. Please try again.",
    }


# ============================================================
# Tuya Cloud
# ============================================================

def initialize_tuya_cloud():
    TUYA_LOGGER.setLevel("INFO")
    cloud = TuyaOpenAPI(TUYA_API_ENDPOINT, TUYA_ACCESS_ID, TUYA_ACCESS_SECRET)
    cloud.connect()

    return cloud


def fetch_tuya_status(cloud, tuya_device_id: str) -> Dict[str, Any]:
    response = cloud.get(f"/v1.0/devices/{tuya_device_id}/status")

    if not isinstance(response, dict) or response.get("success") is not True:
        raise RuntimeError(f"Tuya status read failed: {response}")

    raw: Dict[str, Any] = {}
    for item in response.get("result", []):
        if isinstance(item, dict) and "code" in item:
            raw[str(item["code"])] = item.get("value")

    return raw


def fetch_tuya_device_online(cloud, tuya_device_id: str) -> bool:
    response = cloud.get(f"/v1.0/devices/{tuya_device_id}")
    if not isinstance(response, dict) or response.get("success") is not True:
        raise RuntimeError(f"Tuya device read failed: {response}")

    result = response.get("result") or {}
    return result.get("online") is True


def ensure_tuya_device_powered(cloud, tuya_device_id: str) -> Dict[str, Any]:
    if not fetch_tuya_device_online(cloud, tuya_device_id):
        raise RuntimeError("Device offline")

    return fetch_tuya_status(cloud, tuya_device_id)


def send_tuya_command_with_code(
    cloud,
    tuya_device_id: str,
    code: str,
    turn_on: bool,
) -> Dict[str, Any]:
    commands = {
        "commands": [
            {
                "code": code,
                "value": turn_on,
            }
        ]
    }

    print(
        f"[TUYA CLOUD] Sending command tuya_id={tuya_device_id}, "
        f"code={code}, value={turn_on}"
    )

    response = cloud.post(f"/v1.0/devices/{tuya_device_id}/commands", commands)
    print(f"[TUYA CLOUD] Command response: {response}")

    if not isinstance(response, dict) or response.get("success") is not True:
        raise RuntimeError(f"Tuya command API failed for code={code}: {response}")

    return response


def wait_for_tuya_switch_state(
    cloud,
    tuya_device_id: str,
    expected_state: bool,
    switch_code: str,
) -> bool:
    for attempt in range(1, 8):
        time.sleep(1)
        status = fetch_tuya_status(cloud, tuya_device_id)
        actual_state = status.get(switch_code)

        if actual_state is None and switch_code != "switch":
            actual_state = status.get("switch")

        print(
            f"[TUYA CLOUD] Verify attempt {attempt}: "
            f"{switch_code}={actual_state}, all_status={status}"
        )

        if actual_state is expected_state:
            return True

    return False


def send_tuya_cloud_command(
    cloud,
    project_device_id: str,
    action: str,
) -> bool:
    """Send ON/OFF command to Tuya Cloud and verify the physical switch state."""

    if project_device_id not in DEVICES:
        raise ValueError(f"Unknown device_id: {project_device_id}")

    device_config = DEVICES[project_device_id]

    tuya_device_id = device_config["tuya_device_id"]
    main_code = device_config["command_code"]
    fallback_codes = device_config.get("fallback_codes", [])

    turn_on = action == "turn_on"

    codes_to_try = []
    for code in [main_code] + fallback_codes:
        if code not in codes_to_try:
            codes_to_try.append(code)

    last_response = None
    last_status = None

    for code in codes_to_try:
        try:
            last_response = send_tuya_command_with_code(
                cloud,
                tuya_device_id,
                code,
                turn_on,
            )
            if wait_for_tuya_switch_state(cloud, tuya_device_id, turn_on, code):
                return True
            last_status = fetch_tuya_status(cloud, tuya_device_id)
            print(
                f"[TUYA CLOUD] Command accepted but state did not change "
                f"for code={code}."
            )
        except Exception as error:
            last_response = str(error)
            print(f"[TUYA CLOUD] code={code} failed: {error}")
            continue

    if last_status is None:
        try:
            last_status = fetch_tuya_status(cloud, tuya_device_id)
        except Exception as error:
            last_status = f"status read failed: {error}"

    raise RuntimeError(
        "Tuya command did not change breaker state. "
        f"Last response: {last_response}. Latest status: {last_status}"
    )


# ============================================================
# Firebase update logic
# ============================================================

def write_command_state(
    device_id: str,
    command: Dict[str, Any],
    updates: Dict[str, Any],
    remove_pending: bool = False,
) -> None:
    command_id = command.get("command_id")
    if not command_id:
        return

    updated_command = {
        **command,
        **updates,
    }

    pending_ref = get_pending_command_ref(command_id)
    if remove_pending:
        pending_ref.delete()
    else:
        pending_ref.update(updates)

    get_command_history_ref(command_id).set(updated_command)
    get_latest_by_device_ref(device_id).set(updated_command)

    legacy_updates = {
        **updates,
        "action": action_for_command(command),
    }
    get_command_ref(device_id).update(legacy_updates)


def mark_command_sent(device_id: str, command: Dict[str, Any]) -> Dict[str, Any]:
    sent_at = now_ms()
    sent_at_iso = ms_to_iso(sent_at)
    updates = {
        "timestamp_ms": sent_at,
        "timestamp_iso": sent_at_iso,
        "timezone": TIMEZONE,
        "status": "sent",
        "sent_at_ms": sent_at,
        "sent_at_iso": sent_at_iso,
    }
    write_command_state(device_id, command, updates)
    return {**command, **updates}


def mark_command_done(
    device_id: str,
    command: Dict[str, Any],
    relay_on: bool,
) -> None:
    command_id = command["command_id"]
    confirmed_at = now_ms()
    confirmed_at_iso = ms_to_iso(confirmed_at)
    readable = confirmed_at_iso or readable_time()
    state = "on" if relay_on else "off"
    message = command_message(device_id, state)

    updates = {
        "timestamp_ms": confirmed_at,
        "timestamp_iso": confirmed_at_iso,
        "timezone": TIMEZONE,
        "status": "confirmed",
        "confirmed_at_ms": confirmed_at,
        "confirmed_at_iso": confirmed_at_iso,
        "executed_at": confirmed_at,
        "executed_at_ms": confirmed_at,
        "executed_at_iso": confirmed_at_iso,
        "executed_readable_time": readable,
        "result": {
            **command.get("result", {}),
            "success": True,
            "actual_state": state,
            "error_code": None,
            "user_message": message,
            "raw_error": None,
        },
    }

    write_command_state(device_id, command, updates, remove_pending=True)

    get_device_ref(device_id).update(
        {
            "state": state,
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
        }
    )

    get_device_status_ref(device_id).update(
        {
            "switch": relay_on,
            "relay_status": state,
            "online": True,
            "lastSeenMs": confirmed_at,
            "last_seen_ms": confirmed_at,
            "last_seen_iso": confirmed_at_iso,
            "readableTime": readable,
            "last_command_id": command_id,
        }
    )


def mark_command_failed(
    device_id: str,
    command: Dict[str, Any],
    error_message: str,
    actual_state: str | None = None,
    status: str = "failed",
) -> None:
    command_id = command.get("command_id", f"unknown_{now_ms()}")
    failed_at = now_ms()
    failed_at_iso = ms_to_iso(failed_at)
    readable = failed_at_iso or readable_time()
    mapped = friendly_error(error_message)
    state_update = actual_state or command.get("previous_state")

    updates = {
        "timestamp_ms": failed_at,
        "timestamp_iso": failed_at_iso,
        "timezone": TIMEZONE,
        "status": status,
        "error": mapped["user_message"],
        "failed_at_ms": failed_at if status == "failed" else command.get("failed_at_ms"),
        "failed_at_iso": failed_at_iso if status == "failed" else command.get("failed_at_iso"),
        "timeout_at_ms": failed_at if status == "timeout" else command.get("timeout_at_ms"),
        "timeout_at_iso": failed_at_iso if status == "timeout" else command.get("timeout_at_iso"),
        "executed_at": failed_at,
        "executed_at_ms": failed_at,
        "executed_at_iso": failed_at_iso,
        "executed_readable_time": readable,
        "result": {
            **command.get("result", {}),
            "success": False,
            "actual_state": state_update,
            "error_code": mapped["error_code"],
            "user_message": mapped["user_message"],
            "raw_error": error_message,
        },
    }

    write_command_state(device_id, command, updates, remove_pending=True)

    device_updates = {
        "command_in_progress": False,
        "pending_command_id": None,
        "pending_target_state": None,
        "last_command_status": status,
        "last_command_message": mapped["user_message"],
        "last_command": {
            "status": status,
            "user_message": mapped["user_message"],
            "error_code": mapped["error_code"],
        },
    }
    if state_update in {"on", "off", "unknown"}:
        device_updates["state"] = state_update
    if mapped["error_code"] == "DEVICE_OFFLINE":
        device_updates["state"] = "off"

    get_device_ref(device_id).update(device_updates)

    status_updates = {
        "lastSeenMs": failed_at,
        "last_seen_ms": failed_at,
        "last_seen_iso": failed_at_iso,
        "readableTime": readable,
        "last_error": mapped["user_message"],
        "last_command_id": command_id,
    }
    if mapped["error_code"] == "DEVICE_OFFLINE":
        status_updates.update(
            {
                "online": False,
                "switch": False,
                "relay_status": "off",
            }
        )
    get_device_status_ref(device_id).update(status_updates)


def mark_command_cancelled(
    device_id: str,
    command: Dict[str, Any],
    message: str,
) -> None:
    cancelled_at = now_ms()
    cancelled_at_iso = ms_to_iso(cancelled_at)
    updates = {
        "timestamp_ms": cancelled_at,
        "timestamp_iso": cancelled_at_iso,
        "timezone": TIMEZONE,
        "status": "cancelled",
        "cancelled_at_ms": cancelled_at,
        "cancelled_at_iso": cancelled_at_iso,
        "result": {
            **command.get("result", {}),
            "success": False,
            "actual_state": command.get("previous_state"),
            "error_code": "COMMAND_CANCELLED",
            "user_message": message,
            "raw_error": None,
        },
    }
    write_command_state(device_id, command, updates, remove_pending=True)

    current = get_device_ref(device_id).get()
    should_clear_device = not isinstance(current, dict) or current.get(
        "pending_command_id"
    ) == command.get("command_id")
    if should_clear_device:
        get_device_ref(device_id).update(
            {
                "command_in_progress": False,
                "pending_command_id": None,
                "pending_target_state": None,
                "last_command_status": "cancelled",
                "last_command_message": message,
                "last_command": {
                    "status": "cancelled",
                    "user_message": message,
                    "error_code": "COMMAND_CANCELLED",
                },
            }
        )


def clear_stuck_command_state(device_id: str, command: Dict[str, Any]) -> None:
    current = get_device_ref(device_id).get()
    if isinstance(current, dict) and current.get("pending_command_id") == command.get("command_id"):
        get_device_ref(device_id).update(
            {
                "command_in_progress": False,
                "pending_command_id": None,
                "pending_target_state": None,
            }
        )


# ============================================================
# Main command processor
# ============================================================

def process_device_command(cloud, device_id: str, command: Dict[str, Any]) -> None:
    if not command:
        return

    if is_stale_command(command):
        if command.get("status") == "pending":
            print(
                f"[COMMAND] Cancelling stale pending command: "
                f"{device_id} {command.get('command_id')}"
            )
            mark_command_cancelled(
                device_id,
                command,
                "Old pending command was cancelled and was not sent to the breaker.",
            )
        return

    if not is_valid_command(command, device_id):
        return

    current_device = get_device_ref(device_id).get()
    if isinstance(current_device, dict):
        pending_command_id = current_device.get("pending_command_id")
        if pending_command_id and pending_command_id != command.get("command_id"):
            print(
                f"[COMMAND] Ignoring unclaimed command for {device_id}: "
                f"{command.get('command_id')}"
            )
            return

    command_id = command["command_id"]
    action = action_for_command(command)

    print(f"[COMMAND] Pending command found: {device_id} {action} {command_id}")

    try:
        relay_on = action == "turn_on"
        device_config = DEVICES[device_id]
        ensure_tuya_device_powered(cloud, device_config["tuya_device_id"])

        command = mark_command_sent(device_id, command)
        success = send_tuya_cloud_command(cloud, device_id, action)

        if success:
            mark_command_done(device_id, command, relay_on)
            print(f"[SUCCESS] {device_id} {action} completed")
        else:
            mark_command_failed(
                device_id,
                command,
                "Tuya Cloud command returned unsuccessful result",
                actual_state=command.get("previous_state"),
            )
            print(f"[FAILED] {device_id} {action}")

    except Exception as error:
        error_message = str(error)
        print(f"[ERROR] {device_id}: {error_message}")
        traceback.print_exc()

        actual_state = command.get("previous_state")
        try:
            config = DEVICES.get(device_id, {})
            status = fetch_tuya_status(cloud, config["tuya_device_id"])
            raw_switch = status.get(config.get("command_code", "switch"))
            if raw_switch is None:
                raw_switch = status.get("switch")
            if raw_switch is True:
                actual_state = "on"
            elif raw_switch is False:
                actual_state = "off"
        except Exception:
            pass

        mark_command_failed(device_id, command, error_message, actual_state=actual_state)
    finally:
        clear_stuck_command_state(device_id, command)


def process_pending_commands(cloud) -> None:
    pending = get_pending_commands_ref().get()
    if isinstance(pending, dict) and pending:
        for _, command in pending.items():
            if not isinstance(command, dict):
                continue
            device_id = str(command.get("device_id", ""))
            process_device_command(cloud, device_id, command)
        return

    # Backward compatibility: older clients wrote only /commands/{device_id}/latest.
    for device_id in DEVICES.keys():
        command = get_command_ref(device_id).get()
        process_device_command(cloud, device_id, command)


def run_controller() -> None:
    initialize_firebase()
    cloud = initialize_tuya_cloud()

    print("======================================")
    print("Firebase Tuya Cloud Controller Started")
    print(f"Home ID: {HOME_ID}")
    print(f"Tuya API endpoint: {TUYA_API_ENDPOINT}")
    print(f"Polling every {POLL_INTERVAL_SECONDS} seconds")
    print("Watching devices:")
    for device_id, config in DEVICES.items():
        print(f"- {device_id}: {config['name']}")
    print("======================================")

    while True:
        process_pending_commands(cloud)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_controller()
