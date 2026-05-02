from datetime import datetime, timezone
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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_key(now: datetime) -> str:
    return now.strftime("%Y%m%d_%H%M%S_%f")


def home_ref(path: str):
    return db.reference(f"/homes/{HOME_ID}/{path}")


def build_payload(data: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    return {
        **data,
        "home_id": HOME_ID,
        "source": SOURCE,
        "esp32_source_id": ESP32_SOURCE_ID,
        "timestamp": now.isoformat(),
        "timestamp_key": timestamp_key(now),
    }


def build_history_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sensors = payload.get("sensors")
    status = payload.get("status")

    if not isinstance(sensors, dict):
        sensors = {}

    if not isinstance(status, dict):
        status = {}

    timestamp = sensors.get("timestamp", status.get("lastSeen"))
    timestamp_ms = sensors.get("timestamp_ms", status.get("lastSeenMs"))
    readable_time = sensors.get("readable_time", status.get("readableTime"))

    return {
        "timestamp": timestamp,
        "timestamp_ms": timestamp_ms,
        "readable_time": readable_time,
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
        "received_at": payload.get("timestamp"),
        "timestamp_key": payload.get("timestamp_key"),
    }


def save_to_firebase(payload: dict[str, Any]) -> None:
    history_key = payload["timestamp_key"]
    history_payload = build_history_payload(payload)

    # Keep the original Firebase structure: latest ESP32 data lives inside
    # devices/esp32_01. History is flattened so backend Firebase Functions can
    # read top-level fields like motion, noise, sound_raw, and light_status.
    home_ref(f"devices/{APP_DEVICE_ID}").set(payload)
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
