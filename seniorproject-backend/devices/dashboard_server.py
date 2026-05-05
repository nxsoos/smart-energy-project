import os
import time
from datetime import datetime, timezone
from typing import Any

import firebase_admin
import requests
from firebase_admin import credentials, db
from flask import Flask, jsonify, render_template, request


SERVICE_ACCOUNT_PATH = os.environ.get("SERVICE_ACCOUNT_PATH", "serviceAccountKey.json")
DATABASE_URL = os.environ.get(
    "FIREBASE_DATABASE_URL",
    "https://seniorproject-energy-default-rtdb.asia-southeast1."
    "firebasedatabase.app",
)

HOME_ID = os.environ.get("HOME_ID", "home_001")
SMART_ENERGY_API_URL = os.environ.get(
    "SMART_ENERGY_API_URL",
    "https://smart-energy-api-qs7uzdqawq-as.a.run.app",
).rstrip("/")
PI_DASHBOARD_TOKEN = os.environ.get("PI_DASHBOARD_TOKEN", "")
ALLOWED_DEVICES = {"breaker_01", "breaker_02"}
ALLOWED_ACTIONS = {"turn_on", "turn_off"}
SENSOR_STALE_AFTER_MS = 2 * 60 * 1000
DEVICE_STALE_AFTER_MS = 45 * 1000

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


def api_headers() -> dict[str, str]:
    return {"X-Device-Token": PI_DASHBOARD_TOKEN} if PI_DASHBOARD_TOKEN else {}


def home_ref(path: str):
    return db.reference(f"/homes/{HOME_ID}/{path}")


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def object_to_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            if isinstance(item, dict):
                items.append({"id": str(key), **item})
        return items
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def active_only(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if str(item.get("status", "active")).lower()
        in {"active", "pending", "open", "waiting_for_user"}
    ]


def normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "on", "yes", "motion", "detected", "smoke", "gas"}:
            return True
        if normalized in {"false", "0", "off", "no", "no motion", "clear"}:
            return False
    return None


def timestamp_ms_from_source(*sources: dict[str, Any]) -> int | None:
    for key in [
        "timestamp_ms",
        "last_seen_ms",
        "lastSeenMs",
        "sensor_timestamp_ms",
    ]:
        for source in sources:
            value = source.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return int(value)
            if isinstance(value, str):
                try:
                    parsed = int(float(value))
                except ValueError:
                    continue
                if parsed > 0:
                    return parsed

    for key in ["timestamp_iso", "last_seen_iso", "sensor_timestamp_iso"]:
        for source in sources:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                try:
                    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
                except ValueError:
                    continue
    return None


def format_live_room(esp32: dict[str, Any]) -> dict[str, Any]:
    sensors = as_dict(esp32.get("sensors"))
    status = as_dict(esp32.get("status"))
    source = {**sensors, **status}
    motion = normalize_bool(source.get("motion"))
    smoke = normalize_bool(source.get("smoke"))
    timestamp_ms = timestamp_ms_from_source(sensors, status)
    age_ms = None
    if isinstance(timestamp_ms, (int, float)):
        age_ms = int(time.time() * 1000) - int(timestamp_ms)

    feed_online = normalize_bool(source.get("online"))
    if age_ms is not None and age_ms <= SENSOR_STALE_AFTER_MS:
        feed_online = True
    elif age_ms is not None and age_ms > SENSOR_STALE_AFTER_MS:
        feed_online = False
    elif feed_online is None:
        feed_online = age_ms is not None and age_ms <= SENSOR_STALE_AFTER_MS

    feed_online = bool(feed_online)

    return {
        "sensor_timestamp_ms": timestamp_ms,
        "sensor_timestamp_iso": source.get("timestamp_iso") or source.get("last_seen_iso"),
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
    state = (
        "on"
        if switch is True
        else "off" if switch is False else relay_status or str(device.get("state", "unknown")).lower()
    )
    command_in_progress = bool(normalize_bool(device.get("command_in_progress")))
    pending_target_state = device.get("pending_target_state")
    if pending_target_state not in {"on", "off"}:
        pending_target_state = None
    display_state = pending_target_state if command_in_progress and pending_target_state else state
    last_seen_ms = status.get("lastSeenMs")
    is_stale = not isinstance(last_seen_ms, (int, float)) or (
        int(time.time() * 1000) - int(last_seen_ms) > DEVICE_STALE_AFTER_MS
    )
    online = normalize_bool(status.get("online"))
    is_breaker = str(device.get("type", "")).lower() in {"smart_breaker", "breaker"} or device_id.startswith("breaker_")
    if online is None:
        online = not is_stale
    elif is_stale and not is_breaker:
        online = False
    if not online:
        display_state = "off"
    power_w = metering.get("power_W", 0)
    if not online:
        power_w = 0

    return {
        "device_id": device_id,
        "name": device.get("name", device_id),
        "type": device.get("type", "unknown"),
        "online": bool(online),
        "stale": is_stale,
        "controllable": normalize_bool(device.get("controllable")) is not False,
        "state": state,
        "display_state": display_state,
        "power_w": power_w,
        "today_kwh": metering.get("energy_kWh", 0),
        "today_cost_bhd": metering.get("cost_BHD", 0),
        "last_seen_ms": last_seen_ms,
        "command_in_progress": command_in_progress,
        "pending_command_id": device.get("pending_command_id"),
        "pending_target_state": pending_target_state,
        "last_requested_state": device.get("last_requested_state"),
        "last_command": {
            "status": device.get("last_command_status"),
            "user_message": device.get("last_command_message"),
            "error_code": as_dict(device.get("last_command")).get("error_code"),
        },
    }


def local_firebase_dashboard(message: str) -> dict[str, Any]:
    home = as_dict(db.reference(f"/homes/{HOME_ID}").get())
    esp32 = as_dict(as_dict(home.get("devices")).get("esp32_01"))
    live_devices = as_dict(home.get("devices"))
    room = format_live_room(esp32) if esp32 else {}
    devices = {
        device_id: format_live_device(device_id, as_dict(device))
        for device_id, device in live_devices.items()
        if device_id.startswith("breaker_") or device_id == "esp32_01"
    }
    safety = as_dict(home.get("safety"))
    alerts = active_only(object_to_list(as_dict(home.get("alerts")).get("active")))
    return {
        "home_id": HOME_ID,
        "fallback": True,
        "fallback_message": message,
        "room": room,
        "occupancy": as_dict(as_dict(home.get("occupancy")).get("room1")),
        "devices": devices,
        "energy": as_dict(as_dict(home.get("backend")).get("energy")),
        "alerts": alerts,
        "critical_alerts": [
            alert
            for alert in alerts
            if str(alert.get("severity", alert.get("level", ""))).lower() == "critical"
            or str(alert.get("category", "")).lower() == "safety"
        ],
        "recommendations": active_only(object_to_list(as_dict(home.get("recommendations")).get("active"))),
        "control": as_dict(home.get("control")),
        "action_suggestions": active_only(object_to_list(as_dict(home.get("action_suggestions")).get("active"))),
        "automation_logs": object_to_list(home.get("automation_logs"))[-10:],
        "settings_summary": as_dict(home.get("settings_summary")),
        "next_schedule": None,
        "ai": {},
        "safety": {
            "emergency_mode": as_dict(safety.get("emergency_mode")),
            "smoke_state": as_dict(safety.get("smoke_state")),
        },
    }


def dismiss_suggestion_locally(suggestion_id: str) -> dict[str, Any]:
    suggestion = as_dict(home_ref(f"action_suggestions/active/{suggestion_id}").get())
    if not suggestion:
        return {"success": True, "message": "Action suggestion dismissed."}

    timestamp_ms = int(time.time() * 1000)
    dismissed = {
        **suggestion,
        "status": "dismissed",
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": datetime.now(timezone.utc).isoformat(),
        "dismissed_at_ms": timestamp_ms,
        "dismissed_at_iso": datetime.now(timezone.utc).isoformat(),
    }
    home_ref(f"action_suggestions/history/{suggestion_id}").set(dismissed)

    active = as_dict(home_ref("action_suggestions/active").get())
    device_id = str(suggestion.get("device_id", ""))
    command = str(suggestion.get("suggested_command", suggestion.get("command", "")))
    reason = str(suggestion.get("reason", ""))
    for active_id, raw_item in active.items():
        item = as_dict(raw_item)
        if (
            active_id == suggestion_id
            or (
                str(item.get("device_id", "")) == device_id
                and str(item.get("suggested_command", item.get("command", ""))) == command
                and str(item.get("reason", "")) == reason
            )
        ):
            home_ref(f"action_suggestions/active/{active_id}").delete()

    return {"success": True, "message": "Action suggestion dismissed."}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/latest")
def latest():
    try:
        try:
            response = requests.get(
                f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/dashboard",
                headers=api_headers(),
                timeout=10,
            )
            data = response.json()
            if not response.ok:
                message = data.get("detail", "Backend API request failed")
                print(f"[DASHBOARD FALLBACK] API returned {response.status_code}: {message}", flush=True)
                data = local_firebase_dashboard(str(message))
        except Exception as api_error:
            print(f"[DASHBOARD FALLBACK] API unavailable: {api_error}", flush=True)
            data = local_firebase_dashboard(str(api_error))

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
                "fallback": bool(data.get("fallback")),
                "message": data.get("fallback_message"),
                "room": data.get("room", {}),
                "occupancy": data.get("occupancy", {}),
                "devices": data.get("devices", {}),
                "energy": data.get("energy", {}),
                "alerts": data.get("alerts", []),
                "recommendations": data.get("recommendations", []),
                "control": data.get("control", {}),
                "action_suggestions": data.get("action_suggestions", []),
                "automation_logs": data.get("automation_logs", []),
                "settings_summary": data.get("settings_summary", {}),
                "next_schedule": data.get("next_schedule"),
                "ai": data.get("ai", {}),
                "safety": data.get("safety", {}),
                "critical_alerts": data.get("critical_alerts", []),
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
            headers=api_headers(),
            json={
                "command": action,
                "requested_by": "user_emergency_action" if data.get("emergency") else "pi_dashboard",
                "source": "smoke_emergency" if data.get("emergency") else "pi_dashboard",
                "emergency": bool(data.get("emergency")),
                "alert_id": "smoke_detected_room1" if data.get("emergency") else None,
            },
            timeout=10,
        )
        result = response.json()
        if not response.ok:
            detail = result.get("detail", "Command failed")
            if isinstance(detail, dict):
                detail = detail.get("message", "Command failed")
            return jsonify({"success": False, "message": detail}), response.status_code

        return jsonify(
            {
                "success": True,
                "no_action": bool(result.get("no_action")),
                "status": result.get("status"),
                "message": result.get("message", "Command sent"),
                "command_id": result.get("command_id"),
            }
        )
    except Exception as error:
        print(f"[DASHBOARD ERROR] {error}", flush=True)
        return jsonify({"success": False, "message": str(error)}), 500


@app.post("/api/safety/smoke/actions/turn-off-safe-devices")
def turn_off_safe_devices():
    try:
        response = requests.post(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/safety/smoke/actions/turn-off-safe-devices",
            headers=api_headers(),
            timeout=10,
        )
        return jsonify(response.json()), response.status_code
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.post("/api/safety/smoke/actions/mark-safe")
def mark_smoke_safe():
    try:
        response = requests.post(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/safety/smoke/actions/mark-safe",
            headers=api_headers(),
            timeout=10,
        )
        return jsonify(response.json()), response.status_code
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.put("/api/control/mode")
def update_control_mode():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "JSON body is required"}), 400

        mode = str(data.get("mode", "")).strip().lower()
        response = requests.put(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/control/mode",
            headers=api_headers(),
            json={"mode": mode, "updated_by": "pi_dashboard"},
            timeout=10,
        )
        result = response.json()
        if not response.ok:
            return jsonify({"success": False, "message": result.get("detail", "Control mode update failed")}), response.status_code
        return jsonify(result)
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.post("/api/action-suggestions/<suggestion_id>/<decision>")
def decide_action_suggestion(suggestion_id: str, decision: str):
    if decision not in {"approve", "dismiss"}:
        return jsonify({"success": False, "message": "Unsupported decision"}), 400
    try:
        response = requests.post(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/action-suggestions/{suggestion_id}/{decision}",
            headers=api_headers(),
            timeout=10,
        )
        result = response.json()
        if not response.ok:
            if decision == "dismiss":
                return jsonify(dismiss_suggestion_locally(suggestion_id))
            detail = result.get("detail", "Action suggestion update failed")
            if isinstance(detail, dict):
                detail = detail.get("message", "Action suggestion update failed")
            return jsonify({"success": False, "message": detail}), response.status_code
        return jsonify(result)
    except Exception as error:
        if decision == "dismiss":
            return jsonify(dismiss_suggestion_locally(suggestion_id))
        return jsonify({"success": False, "message": str(error)}), 500


@app.get("/api/settings")
def get_settings():
    try:
        response = requests.get(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/settings",
            headers=api_headers(),
            timeout=10,
        )
        return jsonify(response.json()), response.status_code
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.put("/api/settings")
def update_settings():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "JSON body is required"}), 400
        data["updated_by"] = "pi_dashboard"
        response = requests.put(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/settings",
            headers=api_headers(),
            json=data,
            timeout=10,
        )
        return jsonify(response.json()), response.status_code
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.get("/api/schedules")
def get_schedules():
    try:
        response = requests.get(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/schedules",
            headers=api_headers(),
            timeout=10,
        )
        return jsonify(response.json()), response.status_code
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.post("/api/schedules")
def create_schedule():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "JSON body is required"}), 400
        data["created_by"] = "pi_dashboard"
        response = requests.post(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/schedules",
            headers=api_headers(),
            json=data,
            timeout=10,
        )
        return jsonify(response.json()), response.status_code
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.patch("/api/schedules/<schedule_id>/enabled")
def update_schedule_enabled(schedule_id: str):
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "JSON body is required"}), 400
        data["updated_by"] = "pi_dashboard"
        response = requests.patch(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/schedules/{schedule_id}/enabled",
            headers=api_headers(),
            json=data,
            timeout=10,
        )
        return jsonify(response.json()), response.status_code
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.post("/api/schedules/<schedule_id>/run-now")
def run_schedule_now(schedule_id: str):
    try:
        response = requests.post(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/schedules/{schedule_id}/run-now",
            headers=api_headers(),
            timeout=10,
        )
        return jsonify(response.json()), response.status_code
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.delete("/api/schedules/<schedule_id>")
def delete_schedule(schedule_id: str):
    try:
        response = requests.delete(
            f"{SMART_ENERGY_API_URL}/api/home/{HOME_ID}/schedules/{schedule_id}",
            headers=api_headers(),
            params={"deleted_by": "pi_dashboard"},
            timeout=10,
        )
        return jsonify(response.json()), response.status_code
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


if __name__ == "__main__":
    initialize_firebase()
    app.run(host="0.0.0.0", port=5001)
