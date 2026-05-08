import sys
import threading
import hashlib
import hmac
import os
from pathlib import Path
from typing import Any

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, db
from flask import Flask, jsonify, request
from local_state_store import add_history, home_ref as local_home_ref


load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")
load_dotenv()

SERVICE_ACCOUNT_PATH = os.environ.get("SERVICE_ACCOUNT_PATH", "serviceAccountKey.json")
DATABASE_URL = os.environ.get(
    "FIREBASE_DATABASE_URL",
    "https://seniorproject-energy-default-rtdb.asia-southeast1."
    "firebasedatabase.app"
)
FIREBASE_ENABLED = os.environ.get("FIREBASE_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
LOCAL_RAW_HISTORY_ENABLED = os.environ.get(
    "LOCAL_RAW_HISTORY_ENABLED",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}
LOCAL_HISTORY_MAX_RECORDS = int(os.environ.get("LOCAL_HISTORY_MAX_RECORDS", "5000"))

HOME_ID = "home_001"
SOURCE = "raspberry_pi_hub"
ESP32_SOURCE_ID = "room1_esp32"
APP_DEVICE_ID = "esp32_01"
SMOKE_ALERT_ID = "smoke_detected_room1"
SMOKE_CONFIRMATION_COUNT = 2
SMOKE_CONFIRMATION_MS = 7000
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from occupancy_utils import calculate_occupancy, merged_occupancy_settings, should_write_occupancy_history
from timestamp_utils import TIMEZONE, ms_to_iso, now_timestamp

app = Flask(__name__)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def request_has_valid_device_key() -> bool:
    expected_key = os.environ.get("ESP32_DEVICE_KEY", "")
    expected_hash = os.environ.get("ESP32_DEVICE_KEY_HASH", "")
    provided_key = request.headers.get("X-Device-Key", "")
    if not provided_key:
        return False
    if expected_key and hmac.compare_digest(provided_key, expected_key):
        return True
    if expected_hash and hmac.compare_digest(hash_secret(provided_key), expected_hash):
        return True
    return False


def initialize_firebase() -> None:
    if not FIREBASE_ENABLED:
        return
    if firebase_admin._apps:
        return

    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(
        cred,
        {
            "databaseURL": DATABASE_URL,
        },
    )


def home_ref(path: str):
    if not FIREBASE_ENABLED:
        return local_home_ref(HOME_ID, path)
    return db.reference(f"/homes/{HOME_ID}/{path}")


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on", "detected", "smoke", "gas"}
    return False


def smoke_detected_from_payload(history_payload: dict[str, Any]) -> bool:
    return (
        normalize_bool(history_payload.get("smoke"))
        or normalize_bool(history_payload.get("smoke_text"))
        or normalize_bool(history_payload.get("smoke_status"))
    )


def latest_occupancy_history_record() -> dict[str, Any]:
    return as_dict(home_ref("occupancy/room1_latest_history").get())


def write_safety_event(event_type: str, message: str, timestamp_ms: int, actions_taken: list[str] | None = None) -> None:
    event_id = f"safety_{timestamp_ms}_{event_type}"
    home_ref(f"safety/events/{event_id}").set(
        {
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": ms_to_iso(timestamp_ms),
            "timezone": TIMEZONE,
            "event_id": event_id,
            "type": event_type,
            "severity": "critical" if "confirmed" in event_type or "emergency" in event_type else "medium",
            "message": message,
            "source": "mq2",
            "actions_taken": actions_taken or [],
            "created_at_ms": timestamp_ms,
            "created_at_iso": ms_to_iso(timestamp_ms),
        }
    )


def create_emergency_suggestion(device_id: str, device_name: str, reason: str, timestamp_ms: int) -> None:
    suggestion_id = f"smoke_emergency_{device_id}"
    if as_dict(home_ref(f"action_suggestions/active/{suggestion_id}").get()):
        return
    home_ref(f"action_suggestions/active/{suggestion_id}").set(
        {
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": ms_to_iso(timestamp_ms),
            "timezone": TIMEZONE,
            "suggestion_id": suggestion_id,
            "type": "emergency_action",
            "severity": "critical",
            "home_id": HOME_ID,
            "device_id": device_id,
            "device_name": device_name,
            "suggested_command": "turn_off",
            "target_state": "off",
            "reason": reason,
            "source": "safety_rule",
            "status": "waiting_for_user",
            "created_at_ms": timestamp_ms,
            "created_at_iso": ms_to_iso(timestamp_ms),
            "actions": ["approve", "dismiss"],
        }
    )


def create_smoke_emergency(timestamp_ms: int, source_log: str) -> None:
    existing_alert = as_dict(home_ref(f"alerts/active/{SMOKE_ALERT_ID}").get())
    alert = {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": ms_to_iso(timestamp_ms),
        "timezone": TIMEZONE,
        "alert_id": SMOKE_ALERT_ID,
        "alert_type": "smoke_detected",
        "category": "safety",
        "severity": "critical",
        "status": "active",
        "title": "Smoke/Gas Detected",
        "message": "Smoke or gas was detected in Room 1. Check the area immediately.",
        "room_id": "room1",
        "source": "mq2",
        "source_log": source_log,
        "requires_user_attention": True,
        "created_at_ms": existing_alert.get("created_at_ms") or timestamp_ms,
        "created_at_iso": existing_alert.get("created_at_iso") or ms_to_iso(timestamp_ms),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": ms_to_iso(timestamp_ms),
    }
    home_ref(f"alerts/active/{SMOKE_ALERT_ID}").set(alert)
    if not existing_alert:
        home_ref(f"alerts/history/alert_{timestamp_ms}_{SMOKE_ALERT_ID}").set({**alert, "event": "created"})
    home_ref("safety/emergency_mode").set(
        {
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": ms_to_iso(timestamp_ms),
            "timezone": TIMEZONE,
            "active": True,
            "reason": "smoke_detected",
            "severity": "critical",
            "started_at_ms": timestamp_ms,
            "started_at_iso": ms_to_iso(timestamp_ms),
            "ended_at_ms": None,
            "ended_at_iso": None,
            "message": "Smoke or gas was detected. Normal automation is paused.",
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": ms_to_iso(timestamp_ms),
        }
    )
    if not existing_alert:
        notification_id = f"notif_{timestamp_ms}"
        home_ref(f"notifications/{notification_id}").set(
            {
                "timestamp_ms": timestamp_ms,
                "timestamp_iso": ms_to_iso(timestamp_ms),
                "timezone": TIMEZONE,
                "notification_id": notification_id,
                "type": "critical_alert",
                "alert_type": "smoke_detected",
                "severity": "critical",
                "title": "Smoke/Gas Detected",
                "body": "Smoke or gas was detected in Room 1. Check immediately.",
                "home_id": HOME_ID,
                "room_id": "room1",
                "read": False,
                "delivered": False,
                "created_at_ms": timestamp_ms,
                "created_at_iso": ms_to_iso(timestamp_ms),
            }
        )
        create_emergency_suggestion("breaker_01", "Switch Breaker", "Smoke or gas was detected. Turning off this breaker may reduce electrical risk.", timestamp_ms)
        create_emergency_suggestion("breaker_02", "AC Breaker", "Smoke or gas was detected. Turning off AC/fan simulation may help prevent spreading smoke or gas.", timestamp_ms)
    write_safety_event(
        "smoke_confirmed",
        "Smoke or gas was confirmed in Room 1.",
        timestamp_ms,
        ["emergency_mode_enabled"] if existing_alert else ["critical_alert_created", "emergency_mode_enabled", "notification_created", "popup_required"],
    )


def update_smoke_safety(history_payload: dict[str, Any], timestamp_ms: int) -> None:
    detected = smoke_detected_from_payload(history_payload)
    current = as_dict(home_ref("safety/smoke_state").get())
    if detected:
        first_detected_at = timestamp_ms if current.get("status") not in {"pending", "confirmed"} else int(current.get("first_detected_at_ms") or timestamp_ms)
        consecutive = int(current.get("consecutive_detections") or 0) + 1
        confirmed = consecutive >= SMOKE_CONFIRMATION_COUNT or timestamp_ms - first_detected_at >= SMOKE_CONFIRMATION_MS or current.get("status") == "confirmed"
        home_ref("safety/smoke_state").set(
            {
                "timestamp_ms": timestamp_ms,
                "timestamp_iso": ms_to_iso(timestamp_ms),
                "timezone": TIMEZONE,
                "status": "confirmed" if confirmed else "pending",
                "consecutive_detections": consecutive,
                "first_detected_at_ms": first_detected_at,
                "first_detected_at_iso": ms_to_iso(first_detected_at),
                "last_detected_at_ms": timestamp_ms,
                "last_detected_at_iso": ms_to_iso(timestamp_ms),
                "last_clear_at_ms": None,
                "last_clear_at_iso": None,
                "updated_at_ms": timestamp_ms,
                "updated_at_iso": ms_to_iso(timestamp_ms),
            }
        )
        write_safety_event("smoke_confirmed" if confirmed else "smoke_pending", "Smoke or gas was confirmed in Room 1." if confirmed else "Smoke or gas detection is pending confirmation.", timestamp_ms, ["confirmation_threshold_met"] if confirmed else [])
        if confirmed:
            create_smoke_emergency(timestamp_ms, str(history_payload.get("timestamp_key") or f"sensor_{timestamp_ms}"))
        return
    first_clear_at = int(current.get("last_clear_at_ms") or timestamp_ms)
    home_ref("safety/smoke_state").set(
        {
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": ms_to_iso(timestamp_ms),
            "timezone": TIMEZONE,
            "status": "clear",
            "consecutive_detections": 0,
            "first_detected_at_ms": None,
            "first_detected_at_iso": None,
            "last_detected_at_ms": current.get("last_detected_at_ms"),
            "last_detected_at_iso": current.get("last_detected_at_iso"),
            "last_clear_at_ms": first_clear_at,
            "last_clear_at_iso": ms_to_iso(first_clear_at),
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": ms_to_iso(timestamp_ms),
        }
    )


def build_payload(data: dict[str, Any]) -> dict[str, Any]:
    timestamp = now_timestamp()
    timestamp_ms = timestamp["timestamp_ms"]
    sensors = data.get("sensors") if isinstance(data.get("sensors"), dict) else {}
    status = data.get("status") if isinstance(data.get("status"), dict) else {}
    esp32_uptime_ms = sensors.get("timestamp_ms", status.get("lastSeenMs"))
    return {
        **data,
        "sensors": {
            **sensors,
            "timestamp_ms": timestamp_ms,
            "timestamp_iso": timestamp["timestamp_iso"],
            "timezone": TIMEZONE,
            "esp32_uptime_ms": esp32_uptime_ms,
        },
        "status": {
            **status,
            "last_seen_ms": timestamp_ms,
            "last_seen_iso": timestamp["timestamp_iso"],
            "lastSeenMs": timestamp_ms,
        },
        "home_id": HOME_ID,
        "source": SOURCE,
        "esp32_source_id": ESP32_SOURCE_ID,
        **timestamp,
        "created_at_ms": timestamp_ms,
        "created_at_iso": timestamp["timestamp_iso"],
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": timestamp["timestamp_iso"],
        "esp32_uptime_ms": esp32_uptime_ms,
        "timestamp_key": f"sensor_{timestamp_ms}",
    }


def build_history_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sensors = payload.get("sensors")
    status = payload.get("status")

    if not isinstance(sensors, dict):
        sensors = {}

    if not isinstance(status, dict):
        status = {}

    timestamp_ms = payload.get("timestamp_ms")
    timestamp_iso = payload.get("timestamp_iso")
    esp32_uptime_ms = payload.get("esp32_uptime_ms")

    return {
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": timestamp_iso,
        "timezone": TIMEZONE,
        "created_at_ms": timestamp_ms,
        "created_at_iso": timestamp_iso,
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": timestamp_iso,
        "esp32_uptime_ms": esp32_uptime_ms,
        "ntp_synced": status.get("ntp_synced"),
        "temperature": sensors.get("temperature"),
        "humidity": sensors.get("humidity"),
        "aht_ok": sensors.get("aht_ok"),
        "aqi": sensors.get("aqi"),
        "tvoc": sensors.get("tvoc"),
        "eco2": sensors.get("eco2"),
        "ens160_ok": sensors.get("ens160_ok"),
        "light_raw": sensors.get("light_raw"),
        "light_status": sensors.get("light_status"),
        "motion": sensors.get("motion"),
        "motion_text": sensors.get("motion_text"),
        "smoke_raw": sensors.get("smoke_raw"),
        "smoke": sensors.get("smoke"),
        "smoke_text": sensors.get("smoke_text"),
        "smoke_status": sensors.get("smoke_status"),
        "sound_raw": sensors.get("sound_raw"),
        "noise": sensors.get("noise"),
        "noise_text": sensors.get("noise_text"),
        "home_id": payload.get("home_id"),
        "source": payload.get("source"),
        "esp32_source_id": payload.get("esp32_source_id"),
        "received_at_ms": timestamp_ms,
        "received_at_iso": timestamp_iso,
        "timestamp_key": payload.get("timestamp_key"),
    }


def save_sensor_payload(payload: dict[str, Any]) -> None:
    history_key = payload["timestamp_key"]
    history_payload = build_history_payload(payload)
    timestamp_ms = int(payload["timestamp_ms"])

    # Keep the original Firebase structure: latest ESP32 data lives inside
    # devices/esp32_01. History is flattened so backend Firebase Functions can
    # read top-level fields like motion, noise, sound_raw, and light_status.
    home_ref(f"devices/{APP_DEVICE_ID}").set(payload)
    update_smoke_safety(history_payload, timestamp_ms)
    settings = merged_occupancy_settings(as_dict(home_ref("settings").get()))
    previous_occupancy = as_dict(home_ref("occupancy/room1").get())
    breaker_data = as_dict(home_ref("backend/energy/current_total").get())
    occupancy = calculate_occupancy(
        history_payload,
        previous_occupancy,
        settings,
        breaker_data,
        timestamp_ms,
    )
    home_ref("occupancy/room1").set(occupancy)
    latest_history_record = latest_occupancy_history_record()
    if should_write_occupancy_history(
        previous_occupancy,
        as_dict(latest_history_record),
        occupancy,
        settings,
        timestamp_ms,
    ):
        if FIREBASE_ENABLED or LOCAL_RAW_HISTORY_ENABLED:
            home_ref(f"history/occupancy_logs/occ_{timestamp_ms}").set(occupancy)
        else:
            add_history(
                "occupancy_logs",
                f"occ_{timestamp_ms}",
                occupancy,
                max_records=LOCAL_HISTORY_MAX_RECORDS,
            )
        home_ref("occupancy/room1_latest_history").set(occupancy)
    if FIREBASE_ENABLED or LOCAL_RAW_HISTORY_ENABLED:
        home_ref(f"history/sensor_logs/{history_key}").set(history_payload)
    else:
        add_history(
            "sensor_logs",
            history_key,
            history_payload,
            max_records=LOCAL_HISTORY_MAX_RECORDS,
        )


def save_sensor_payload_background(payload: dict[str, Any]) -> None:
    try:
        save_sensor_payload(payload)
        print(
            f"[ESP32 RECEIVER] Saved locally: {payload.get('timestamp_key')}",
            flush=True,
        )
    except Exception as error:
        print(f"[ESP32 RECEIVER BACKGROUND ERROR] {error}", flush=True)


@app.post("/api/sensors/room1")
def receive_room1_sensors():
    try:
        if not request_has_valid_device_key():
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Missing or invalid ESP32 device key",
                    }
                ),
                401,
            )

        data = request.get_json(silent=True)
        if data is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Invalid request: JSON body is required",
                    }
                ),
                400,
            )

        if not isinstance(data, dict) or not data:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Invalid request: JSON object cannot be empty",
                    }
                ),
                400,
            )

        print(
            f"[ESP32 RECEIVER] Data received from {ESP32_SOURCE_ID}",
            flush=True,
        )

        payload = build_payload(data)
        threading.Thread(
            target=save_sensor_payload_background,
            args=(payload,),
            daemon=True,
        ).start()

        return jsonify(
            {
                "success": True,
                "message": "Sensor data received by Raspberry Pi hub",
                "timestamp_key": payload.get("timestamp_key"),
            }
        )

    except Exception as error:
        print(f"[ESP32 RECEIVER ERROR] {error}", flush=True)
        return (
            jsonify(
                {
                    "success": False,
                    "message": str(error),
                }
            ),
            500,
        )


if __name__ == "__main__":
    initialize_firebase()
    app.run(host="0.0.0.0", port=5000)
