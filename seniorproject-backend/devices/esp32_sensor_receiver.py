import sys
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, jsonify, request


SERVICE_ACCOUNT_PATH = "serviceAccountKey.json"
DATABASE_URL = (
    "https://seniorproject-energy-default-rtdb.asia-southeast1."
    "firebasedatabase.app"
)

HOME_ID = "home_001"
SOURCE = "raspberry_pi_hub"
ESP32_SOURCE_ID = "room1_esp32"
APP_DEVICE_ID = "esp32_01"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from occupancy_utils import calculate_occupancy, merged_occupancy_settings, should_write_occupancy_history
from timestamp_utils import TIMEZONE, now_timestamp

app = Flask(__name__)


def initialize_firebase() -> None:
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
    return db.reference(f"/homes/{HOME_ID}/{path}")


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def save_to_firebase(payload: dict[str, Any]) -> None:
    history_key = payload["timestamp_key"]
    history_payload = build_history_payload(payload)
    timestamp_ms = int(payload["timestamp_ms"])

    # Keep the original Firebase structure: latest ESP32 data lives inside
    # devices/esp32_01. History is flattened so backend Firebase Functions can
    # read top-level fields like motion, noise, sound_raw, and light_status.
    home_ref(f"devices/{APP_DEVICE_ID}").set(payload)
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
    latest_history = as_dict(home_ref("history/occupancy_logs").order_by_child("updated_at_ms").limit_to_last(1).get())
    latest_history_record = next(iter(latest_history.values()), {}) if latest_history else {}
    if should_write_occupancy_history(
        previous_occupancy,
        as_dict(latest_history_record),
        occupancy,
        settings,
        timestamp_ms,
    ):
        home_ref(f"history/occupancy_logs/occ_{timestamp_ms}").set(occupancy)
    home_ref(f"history/sensor_logs/{history_key}").set(history_payload)


@app.post("/api/sensors/room1")
def receive_room1_sensors():
    try:
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
        save_to_firebase(payload)

        print("[ESP32 RECEIVER] Saved to Firebase", flush=True)
        return jsonify(
            {
                "success": True,
                "message": "Sensor data received and saved to Firebase",
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
