import os
import time
from datetime import datetime, timezone
from typing import Any

import firebase_admin
import requests
from firebase_admin import credentials, db
from flask import Flask, jsonify, render_template, request


SERVICE_ACCOUNT_PATH = "serviceAccountKey.json"
DATABASE_URL = (
    "https://seniorproject-energy-default-rtdb.asia-southeast1."
    "firebasedatabase.app"
)

HOME_ID = "home_001"
SMART_ENERGY_API_URL = os.environ.get(
    "SMART_ENERGY_API_URL",
    "https://smart-energy-api-qs7uzdqawq-as.a.run.app",
).rstrip("/")
ALLOWED_DEVICES = {"breaker_01", "breaker_02"}
ALLOWED_ACTIONS = {"turn_on", "turn_off"}
SENSOR_STALE_AFTER_MS = 2 * 60 * 1000

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


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def command_id(now: datetime) -> str:
    return f"cmd_{now.strftime('%Y%m%d_%H%M%S_%f')}"


def home_ref(path: str):
    return db.reference(f"/homes/{HOME_ID}/{path}")


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "on", "yes", "motion", "detected"}:
            return True
        if normalized in {"false", "0", "off", "no", "no motion", "clear"}:
            return False
    return None


def format_live_room(esp32: dict[str, Any]) -> dict[str, Any]:
    sensors = as_dict(esp32.get("sensors"))
    status = as_dict(esp32.get("status"))
    source = {**sensors, **status}
    motion = normalize_bool(source.get("motion"))
    smoke = normalize_bool(source.get("smoke"))
    timestamp_ms = source.get("timestamp_ms") or source.get("lastSeenMs")
    age_ms = None
    if isinstance(timestamp_ms, (int, float)):
        age_ms = int(time.time() * 1000) - int(timestamp_ms)

    feed_online = normalize_bool(source.get("online"))
    if age_ms is not None and age_ms > SENSOR_STALE_AFTER_MS:
        feed_online = False
    elif feed_online is None:
        feed_online = age_ms is not None and age_ms <= SENSOR_STALE_AFTER_MS

    feed_online = bool(feed_online)

    return {
        "sensor_timestamp_ms": timestamp_ms,
        "sensor_age_ms": age_ms,
        "feed_online": feed_online,
        "temperature": source.get("temperature"),
        "humidity": source.get("humidity"),
        "aht_ok": feed_online and bool(source.get("aht_ok", True)),
        "ens160_ok": feed_online and bool(source.get("ens160_ok", True)),
        "aqi": source.get("aqi"),
        "tvoc": source.get("tvoc"),
        "eco2": source.get("eco2"),
        "light_raw": source.get("light_raw"),
        "light_status": source.get("light_status", "Unknown"),
        "motion": bool(motion) if motion is not None else False,
        "motion_text": source.get("motion_text")
        or ("Motion" if motion else "No motion" if motion is False else "Unknown"),
        "smoke": bool(smoke) if smoke is not None else False,
        "smoke_text": source.get("smoke_text")
        or ("Smoke/Gas" if smoke else "Clear" if smoke is False else "Unknown"),
        "sound_level": source.get("sound_raw"),
        "noise": source.get("noise"),
        "noise_text": source.get("noise_text"),
        "occupancy": "occupied" if motion else "unknown",
    }


def format_live_device(device_id: str, device: dict[str, Any]) -> dict[str, Any]:
    status = as_dict(device.get("status"))
    metering = as_dict(device.get("metering"))
    switch = normalize_bool(status.get("switch"))
    relay_status = status.get("relay_status")
    state = "on" if switch is True else "off" if switch is False else relay_status or "unknown"

    return {
        "device_id": device_id,
        "name": device.get("name", device_id),
        "type": device.get("type", "unknown"),
        "online": bool(normalize_bool(status.get("online"))),
        "state": state,
        "power_w": metering.get("power_W", 0),
        "today_kwh": metering.get("energy_kWh", 0),
        "today_cost_bhd": metering.get("cost_BHD", 0),
        "last_seen_ms": status.get("lastSeenMs"),
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/latest")
def latest():
    try:
        response = requests.get(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/dashboard",
            timeout=10,
        )
        data = response.json()
        if not response.ok:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": data.get("detail", "Backend API request failed"),
                        "dashboard": {},
                    }
                ),
                response.status_code,
            )

        # Keep the local touchscreen feeling live by reading fast-changing
        # sensor/device values straight from Firebase, while AI/alerts/summary
        # still come from the shared API layer.
        esp32 = as_dict(home_ref("devices/esp32_01").get())
        live_devices = as_dict(home_ref("devices").get())
        if esp32:
            data["room"] = {**as_dict(data.get("room")), **format_live_room(esp32)}
        if live_devices:
            formatted_devices = as_dict(data.get("devices")).copy()
            for device_id, device in live_devices.items():
                if device_id.startswith("breaker_"):
                    formatted_devices[device_id] = format_live_device(
                        device_id,
                        as_dict(device),
                    )
            data["devices"] = formatted_devices

        return jsonify(
            {
                "success": True,
                "dashboard": data,
                "room": data.get("room", {}),
                "devices": data.get("devices", {}),
                "energy": data.get("energy", {}),
                "alerts": data.get("alerts", []),
                "recommendations": data.get("recommendations", []),
                "ai": data.get("ai", {}),
            }
        )
    except Exception as error:
        print(f"[DASHBOARD ERROR] {error}", flush=True)
        return (
            jsonify(
                {
                    "success": False,
                    "message": str(error),
                    "esp32": {},
                    "devices": {},
                }
            ),
            500,
        )


@app.post("/api/command")
def send_command():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "JSON body is required"}), 400

        device_id = str(data.get("device_id", "")).strip()
        action = str(data.get("action", "")).strip()

        if device_id not in ALLOWED_DEVICES:
            return jsonify({"success": False, "message": "Unsupported device_id"}), 400

        if action not in ALLOWED_ACTIONS:
            return jsonify({"success": False, "message": "Unsupported action"}), 400

        response = requests.post(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/devices/{device_id}/command",
            json={
                "command": action,
                "requested_by": "pi_dashboard",
            },
            timeout=10,
        )
        result = response.json()
        if not response.ok:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": result.get("detail", "Command failed"),
                    }
                ),
                response.status_code,
            )

        print(
            f"[DASHBOARD] Command sent through API: {device_id} {action}",
            flush=True,
        )
        return jsonify(
            {
                "success": True,
                "message": result.get("message", "Command sent"),
                "command_id": result.get("command_id"),
            }
        )
    except Exception as error:
        print(f"[DASHBOARD ERROR] {error}", flush=True)
        return jsonify({"success": False, "message": str(error)}), 500


if __name__ == "__main__":
    initialize_firebase()
    app.run(host="0.0.0.0", port=5001)
