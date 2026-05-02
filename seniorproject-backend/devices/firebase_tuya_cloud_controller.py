import time
import traceback
from datetime import datetime
from typing import Dict, Any

import firebase_admin
from firebase_admin import credentials, db

from tuya_connector import TuyaOpenAPI, TUYA_LOGGER


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

def now_ms() -> int:
    return int(time.time() * 1000)


def readable_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


def get_device_status_ref(device_id: str):
    return firebase_ref(f"/homes/{HOME_ID}/devices/{device_id}/status")


def get_command_history_ref(command_id: str):
    return firebase_ref(f"/homes/{HOME_ID}/command_history/{command_id}")


def is_valid_command(command: Dict[str, Any], device_id: str) -> bool:
    if not command:
        return False

    if command.get("status") != "pending":
        return False

    if command.get("device_id") != device_id:
        return False

    if command.get("action") not in ["turn_on", "turn_off"]:
        return False

    if not command.get("command_id"):
        return False

    return True


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

def mark_command_done(
    device_id: str,
    command: Dict[str, Any],
    relay_on: bool,
) -> None:
    command_id = command["command_id"]
    executed_at = now_ms()
    readable = readable_time()

    updated_command = {
        **command,
        "status": "done",
        "executed_at": executed_at,
        "executed_readable_time": readable,
    }

    get_command_ref(device_id).update(
        {
            "status": "done",
            "executed_at": executed_at,
            "executed_readable_time": readable,
        }
    )

    get_command_history_ref(command_id).set(updated_command)

    get_device_status_ref(device_id).update(
        {
            "switch": relay_on,
            "relay_status": "on" if relay_on else "off",
            "online": True,
            "lastSeenMs": executed_at,
            "readableTime": readable,
            "last_command_id": command_id,
        }
    )


def mark_command_failed(
    device_id: str,
    command: Dict[str, Any],
    error_message: str,
) -> None:
    command_id = command.get("command_id", f"unknown_{now_ms()}")
    executed_at = now_ms()
    readable = readable_time()

    failed_command = {
        **command,
        "status": "failed",
        "error": error_message,
        "executed_at": executed_at,
        "executed_readable_time": readable,
    }

    get_command_ref(device_id).update(
        {
            "status": "failed",
            "error": error_message,
            "executed_at": executed_at,
            "executed_readable_time": readable,
        }
    )

    get_command_history_ref(command_id).set(failed_command)

    get_device_status_ref(device_id).update(
        {
            "lastSeenMs": executed_at,
            "readableTime": readable,
            "last_error": error_message,
            "last_command_id": command_id,
        }
    )


# ============================================================
# Main command processor
# ============================================================

def process_device_command(cloud, device_id: str) -> None:
    command_ref = get_command_ref(device_id)
    command = command_ref.get()

    if not is_valid_command(command, device_id):
        return

    command_id = command["command_id"]
    action = command["action"]

    print(f"[COMMAND] Pending command found: {device_id} {action} {command_id}")

    try:
        relay_on = action == "turn_on"

        success = send_tuya_cloud_command(cloud, device_id, action)

        if success:
            mark_command_done(device_id, command, relay_on)
            print(f"[SUCCESS] {device_id} {action} completed")
        else:
            mark_command_failed(
                device_id,
                command,
                "Tuya Cloud command returned unsuccessful result",
            )
            print(f"[FAILED] {device_id} {action}")

    except Exception as error:
        error_message = str(error)
        print(f"[ERROR] {device_id}: {error_message}")
        traceback.print_exc()

        mark_command_failed(device_id, command, error_message)


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
        for device_id in DEVICES.keys():
            process_device_command(cloud, device_id)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_controller()
