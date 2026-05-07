import os
import time
import base64
import io
from datetime import datetime, timezone
from typing import Any

import firebase_admin
import requests
from firebase_admin import credentials, db
from flask import Flask, jsonify, render_template, request
from local_command_controller import execute_local_command, sync_home_assistant_device_states
from local_state_store import home_ref as local_home_ref, home_snapshot


SERVICE_ACCOUNT_PATH = os.environ.get("SERVICE_ACCOUNT_PATH", "serviceAccountKey.json")
DATABASE_URL = os.environ.get(
    "FIREBASE_DATABASE_URL",
    "https://seniorproject-energy-default-rtdb.asia-southeast1."
    "firebasedatabase.app",
)
FIREBASE_ENABLED = os.environ.get("FIREBASE_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
CLOUD_BACKEND_ENABLED = os.environ.get(
    "CLOUD_BACKEND_ENABLED",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}

HOME_ID = os.environ.get("HOME_ID", "home_001")
PI_ID = os.environ.get("PI_ID", "pi_local_001")
PI_DEVICE_TOKEN = os.environ.get("PI_DEVICE_TOKEN", "")
KIOSK_ADMIN_PASSWORD_HASH = os.environ.get("KIOSK_ADMIN_PASSWORD_HASH", "")
KIOSK_ADMIN_PASSWORD = os.environ.get("KIOSK_ADMIN_PASSWORD", "")
KAHRABAIQ_API_URL = os.environ.get(
    "KAHRABAIQ_API_URL",
    os.environ.get(
        "SMART_ENERGY_API_URL",
        "https://smart-energy-api-qs7uzdqawq-as.a.run.app",
    ),
).rstrip("/")
PI_DASHBOARD_TOKEN = os.environ.get("PI_DASHBOARD_TOKEN", "")
ALLOWED_DEVICES = {"breaker_01", "breaker_02", "matter_socket_switch", "matter_ac_switch"}
ALLOWED_ACTIONS = {"turn_on", "turn_off"}
ALLOWED_CONTROL_MODES = {"assist", "auto", "manual"}
EMERGENCY_SAFE_DEVICE_IDS = [
    item.strip()
    for item in os.environ.get("EMERGENCY_SAFE_DEVICE_IDS", "breaker_01,matter_ac_switch").split(",")
    if item.strip()
]
SENSOR_STALE_AFTER_MS = 2 * 60 * 1000
DEVICE_STALE_AFTER_MS = 45 * 1000
DEFAULT_SETTINGS = {
    "cost_per_kwh": 0.029,
    "comfort_temperature_min": 22,
    "comfort_temperature_max": 25,
    "high_temperature_threshold": 28,
    "light_waste_minutes": 5,
    "occupancy_empty_minutes": 10,
    "motion_recent_seconds": 90,
    "sound_recent_seconds": 120,
    "sound_activity_threshold": 45,
    "occupancy_confidence_threshold": 0.65,
    "device_offline_minutes": 2,
    "quiet_hours_enabled": True,
    "ai_recommendations_enabled": False,
    "auto_control_enabled": False,
    "notifications_enabled": False,
    "schedules_enabled": True,
}

app = Flask(__name__)

try:
    import qrcode
except Exception:  # pragma: no cover - optional Pi dependency
    qrcode = None


def sha256_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def kiosk_password_valid(password: str) -> bool:
    if KIOSK_ADMIN_PASSWORD_HASH:
        return sha256_text(password) == KIOSK_ADMIN_PASSWORD_HASH
    return bool(KIOSK_ADMIN_PASSWORD) and password == KIOSK_ADMIN_PASSWORD


def qr_data_url(payload: str) -> str | None:
    if not qrcode or not payload:
        return None
    image = qrcode.make(payload)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


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


def api_headers() -> dict[str, str]:
    return {"X-Device-Token": PI_DASHBOARD_TOKEN} if PI_DASHBOARD_TOKEN else {}


def home_ref(path: str):
    if not FIREBASE_ENABLED:
        return local_home_ref(HOME_ID, path)
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
    control_method = str(device.get("control_method") or ("tuya_cloud" if device_id.startswith("breaker_") else "")).lower()
    is_home_assistant_device = control_method == "home_assistant"
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
    last_seen_ms = status.get("lastSeenMs") or status.get("last_seen_ms") or device.get("updated_at_ms")
    is_stale = not isinstance(last_seen_ms, (int, float)) or (
        int(time.time() * 1000) - int(last_seen_ms) > DEVICE_STALE_AFTER_MS
    )
    online = normalize_bool(status.get("online"))
    if is_home_assistant_device:
        online = normalize_bool(device.get("local_online"))
        if online is None:
            online = normalize_bool(device.get("online"))
    is_breaker = str(device.get("type", "")).lower() in {"smart_breaker", "breaker"} or device_id.startswith("breaker_")
    if online is None:
        online = not is_stale
    elif is_stale and not is_breaker and not is_home_assistant_device:
        online = False
    if is_home_assistant_device:
        is_stale = False
    if not online:
        display_state = "unknown" if is_home_assistant_device else "off"
    energy_supported = normalize_bool(device.get("energy_supported"))
    if energy_supported is None:
        energy_supported = not is_home_assistant_device
    power_w = None if energy_supported is False else metering.get("power_W", device.get("power_w", 0))
    if not online and energy_supported is not False:
        power_w = 0

    return {
        "device_id": device_id,
        "name": device.get("name", device_id),
        "type": device.get("type", "unknown"),
        "branch": device.get("branch"),
        "control_method": control_method or None,
        "ha_entity_id": device.get("ha_entity_id"),
        "online": bool(online),
        "local_online": bool(normalize_bool(device.get("local_online")) if device.get("local_online") is not None else online),
        "cloud_online": bool(normalize_bool(device.get("cloud_online")) if device.get("cloud_online") is not None else not is_home_assistant_device),
        "stale": is_stale,
        "controllable": normalize_bool(device.get("controllable")) is not False,
        "state": state,
        "display_state": display_state,
        "power_w": power_w,
        "voltage_v": metering.get("voltage_V"),
        "current_a": metering.get("current_A"),
        "current_ma": metering.get("current_mA"),
        "energy_kwh": metering.get("energy_kWh"),
        "energy_supported": bool(energy_supported),
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
    if FIREBASE_ENABLED:
        home = as_dict(db.reference(f"/homes/{HOME_ID}").get())
    else:
        home = home_snapshot(HOME_ID)
    esp32 = as_dict(as_dict(home.get("devices")).get("esp32_01"))
    live_devices = as_dict(home.get("devices"))
    room = format_live_room(esp32) if esp32 else {}
    devices = {
        device_id: format_live_device(device_id, as_dict(device))
        for device_id, device in live_devices.items()
        if device_id.startswith("breaker_") or device_id.startswith("matter_") or device_id == "esp32_01"
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


def local_control_payload(mode: str) -> dict[str, Any]:
    labels = {
        "assist": "Assist",
        "auto": "Auto",
        "manual": "Manual",
    }


def local_settings() -> dict[str, Any]:
    return {**DEFAULT_SETTINGS, **as_dict(home_ref("settings").get())}


def local_schedule_list() -> list[dict[str, Any]]:
    schedules = active_only(object_to_list(home_ref("schedules").get()))
    schedules.sort(key=lambda item: str(item.get("time", "99:99")))
    return schedules


def local_schedule_payload(raw: dict[str, Any], schedule_id: str | None = None) -> dict[str, Any]:
    timestamp_ms = int(time.time() * 1000)
    device_id = str(raw.get("device_id", "")).strip()
    command = str(raw.get("command", raw.get("action", ""))).strip()
    return {
        "schedule_id": schedule_id or f"schedule_{timestamp_ms}",
        "name": str(raw.get("name") or "Local schedule").strip(),
        "device_id": device_id,
        "device_name": str(raw.get("device_name") or device_id).strip(),
        "command": command,
        "time": str(raw.get("time") or "23:30").strip(),
        "days": raw.get("days") if isinstance(raw.get("days"), list) else [],
        "enabled": normalize_bool(raw.get("enabled")) is not False,
        "status": "active",
        "created_by": str(raw.get("created_by") or raw.get("updated_by") or "pi_dashboard"),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": datetime.now(timezone.utc).isoformat(),
    }
    descriptions = {
        "assist": "The system suggests actions and asks before controlling devices.",
        "auto": "The Pi can run approved local automation rules automatically.",
        "manual": "The system only shows data; users control devices manually.",
    }
    timestamp_ms = int(time.time() * 1000)
    return {
        "mode": mode,
        "label": labels[mode],
        "description": descriptions[mode],
        "updated_by": "pi_dashboard",
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/kiosk/state")
def kiosk_state():
    pi_status = "paired" if HOME_ID else "unpaired"
    pairing_payload = None
    token_expires_at_ms = None
    if CLOUD_BACKEND_ENABLED and PI_DEVICE_TOKEN:
        try:
            response = requests.post(
                f"{KAHRABAIQ_API_URL}/api/pairing/pi-token",
                headers={"X-Pi-Id": PI_ID, "X-Device-Token": PI_DEVICE_TOKEN},
                json={"display_name": PI_ID, "dashboard_version": "local-kiosk"},
                timeout=10,
            )
            data = response.json()
            if response.ok:
                pairing_payload = data.get("qr_payload")
                token_expires_at_ms = data.get("expires_at_ms")
        except Exception as error:
            print(f"[PAIRING TOKEN ERROR] {error}", flush=True)
    if not pairing_payload:
        pairing_payload = f"kahrabaiq://pair?pi_id={PI_ID}&token=configure-cloud-token"
    return jsonify(
        {
            "success": True,
            "pi_id": PI_ID,
            "home_id": HOME_ID,
            "paired": pi_status == "paired",
            "status": pi_status,
            "cloud_enabled": CLOUD_BACKEND_ENABLED,
            "cloud_status": "configured" if CLOUD_BACKEND_ENABLED else "local-only",
            "pairing_payload": pairing_payload,
            "pairing_qr_data_url": qr_data_url(pairing_payload),
            "pairing_expires_at_ms": token_expires_at_ms,
            "admin_unlock_configured": bool(KIOSK_ADMIN_PASSWORD_HASH or KIOSK_ADMIN_PASSWORD),
        }
    )


@app.post("/api/kiosk/unlock")
def kiosk_unlock():
    data = request.get_json(silent=True) or {}
    if not kiosk_password_valid(str(data.get("password", ""))):
        return jsonify({"success": False, "message": "Invalid admin password."}), 403
    return jsonify({"success": True, "message": "Kiosk admin unlocked."})


@app.get("/api/latest")
def latest():
    try:
        if not CLOUD_BACKEND_ENABLED:
            sync_home_assistant_device_states()

        if CLOUD_BACKEND_ENABLED:
            try:
                response = requests.get(
                    f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/dashboard",
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
        else:
            data = local_firebase_dashboard("Local Pi mode: cloud backend disabled.")

        esp32 = as_dict(home_ref("devices/esp32_01").get())
        live_devices = as_dict(home_ref("devices").get())
        if esp32:
            data["room"] = {**as_dict(data.get("room")), **format_live_room(esp32)}
        if live_devices:
            formatted_devices = as_dict(data.get("devices")).copy()
            for device_id, device in live_devices.items():
                if device_id.startswith("breaker_") or device_id.startswith("matter_"):
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

        if not CLOUD_BACKEND_ENABLED:
            result = execute_local_command(
                device_id,
                action,
                requested_by="user_emergency_action" if data.get("emergency") else "pi_dashboard",
                source="smoke_emergency" if data.get("emergency") else "pi_dashboard",
                emergency=bool(data.get("emergency")),
                alert_id="smoke_detected_room1" if data.get("emergency") else None,
            )
            return jsonify(result), 200 if result.get("success") else 500

        response = requests.post(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/devices/{device_id}/command",
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
        if not CLOUD_BACKEND_ENABLED:
            results = []
            for device_id in EMERGENCY_SAFE_DEVICE_IDS:
                if device_id not in ALLOWED_DEVICES:
                    continue
                results.append(
                    execute_local_command(
                        device_id,
                        "turn_off",
                        requested_by="user_emergency_action",
                        source="smoke_emergency",
                        emergency=True,
                        alert_id="smoke_detected_room1",
                    )
                )
            failed = [item for item in results if not item.get("success")]
            return jsonify(
                {
                    "success": not failed,
                    "message": (
                        "Emergency local shutdown completed."
                        if not failed
                        else "Some emergency shutdown commands failed."
                    ),
                    "results": results,
                }
            ), 200 if not failed else 500

        response = requests.post(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/safety/smoke/actions/turn-off-safe-devices",
            headers=api_headers(),
            timeout=10,
        )
        return jsonify(response.json()), response.status_code
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.post("/api/safety/smoke/actions/mark-safe")
def mark_smoke_safe():
    try:
        if not CLOUD_BACKEND_ENABLED:
            timestamp_ms = int(time.time() * 1000)
            timestamp_iso = datetime.now(timezone.utc).isoformat()
            home_ref("safety/emergency_mode").set(
                {
                    "active": False,
                    "reason": None,
                    "message": "Smoke emergency was marked safe from the Pi dashboard.",
                    "updated_at_ms": timestamp_ms,
                    "updated_at_iso": timestamp_iso,
                    "updated_by": "pi_dashboard",
                }
            )
            home_ref("safety/smoke_state").update(
                {
                    "status": "clear",
                    "last_clear_at_ms": timestamp_ms,
                    "last_clear_at_iso": timestamp_iso,
                    "updated_at_ms": timestamp_ms,
                    "updated_at_iso": timestamp_iso,
                }
            )
            home_ref("alerts/active/smoke_detected_room1").delete()
            return jsonify({"success": True, "message": "Smoke emergency marked safe locally."})

        response = requests.post(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/safety/smoke/actions/mark-safe",
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
        if mode not in ALLOWED_CONTROL_MODES:
            return jsonify({"success": False, "message": "Unsupported control mode"}), 400

        if not CLOUD_BACKEND_ENABLED:
            payload = local_control_payload(mode)
            home_ref("control").set(payload)
            return jsonify(
                {
                    "success": True,
                    "message": f"Control mode changed to {payload['label']}.",
                    "control": payload,
                }
            )

        response = requests.put(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/control/mode",
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
        if not CLOUD_BACKEND_ENABLED:
            if decision == "dismiss":
                return jsonify(dismiss_suggestion_locally(suggestion_id))

            suggestion = as_dict(home_ref(f"action_suggestions/active/{suggestion_id}").get())
            if not suggestion:
                return jsonify({"success": False, "message": "Action suggestion not found"}), 404
            result = execute_local_command(
                str(suggestion.get("device_id", "")),
                str(suggestion.get("suggested_command", suggestion.get("command", ""))),
                requested_by="pi_dashboard_action_suggestion",
                source="assist_mode",
                emergency=False,
                alert_id=None,
            )
            if result.get("success"):
                dismissed = dismiss_suggestion_locally(suggestion_id)
                return jsonify(
                    {
                        "success": True,
                        "message": result.get("message") or dismissed.get("message"),
                        "command_id": result.get("command_id"),
                    }
                )
            return jsonify(result), 500

        response = requests.post(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/action-suggestions/{suggestion_id}/{decision}",
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
        if not CLOUD_BACKEND_ENABLED:
            return jsonify(
                {
                    "success": True,
                    "home_id": HOME_ID,
                    "settings": local_settings(),
                    "options": {},
                }
            )

        response = requests.get(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/settings",
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
        if not CLOUD_BACKEND_ENABLED:
            timestamp_ms = int(time.time() * 1000)
            merged = {
                **local_settings(),
                **data,
                "updated_at_ms": timestamp_ms,
                "updated_at_iso": datetime.now(timezone.utc).isoformat(),
            }
            home_ref("settings").set(merged)
            home_ref("settings_summary").set(
                {
                    "control_mode": as_dict(home_ref("control").get()).get("mode", "assist"),
                    "schedules_enabled": merged.get("schedules_enabled"),
                    "auto_control_enabled": merged.get("auto_control_enabled"),
                    "updated_at_ms": timestamp_ms,
                }
            )
            return jsonify({"success": True, "home_id": HOME_ID, "settings": merged})

        response = requests.put(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/settings",
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
        if not CLOUD_BACKEND_ENABLED:
            schedules = local_schedule_list()
            return jsonify(
                {
                    "success": True,
                    "home_id": HOME_ID,
                    "count": len(schedules),
                    "schedules": schedules,
                }
            )

        response = requests.get(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/schedules",
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
        if not CLOUD_BACKEND_ENABLED:
            schedule = local_schedule_payload(data)
            if schedule["device_id"] not in ALLOWED_DEVICES:
                return jsonify({"success": False, "message": "Unsupported device_id"}), 400
            if schedule["command"] not in ALLOWED_ACTIONS:
                return jsonify({"success": False, "message": "Unsupported command"}), 400
            home_ref(f"schedules/{schedule['schedule_id']}").set(schedule)
            return jsonify({"success": True, "home_id": HOME_ID, "schedule": schedule})

        response = requests.post(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/schedules",
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
        if not CLOUD_BACKEND_ENABLED:
            schedule = as_dict(home_ref(f"schedules/{schedule_id}").get())
            if not schedule:
                return jsonify({"success": False, "message": "Schedule not found"}), 404
            updates = {
                "enabled": normalize_bool(data.get("enabled")) is True,
                "updated_by": "pi_dashboard",
                "updated_at_ms": int(time.time() * 1000),
                "updated_at_iso": datetime.now(timezone.utc).isoformat(),
            }
            home_ref(f"schedules/{schedule_id}").update(updates)
            return jsonify(
                {
                    "success": True,
                    "home_id": HOME_ID,
                    "schedule": {**schedule, **updates},
                }
            )

        response = requests.patch(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/schedules/{schedule_id}/enabled",
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
        if not CLOUD_BACKEND_ENABLED:
            schedule = as_dict(home_ref(f"schedules/{schedule_id}").get())
            if not schedule:
                return jsonify({"success": False, "message": "Schedule not found"}), 404
            result = execute_local_command(
                str(schedule.get("device_id", "")),
                str(schedule.get("command", "")),
                requested_by="local_schedule_run_now",
                source="pi_dashboard_schedule",
                emergency=False,
                alert_id=None,
            )
            log = {
                "schedule_id": schedule_id,
                "status": "completed" if result.get("success") else "failed",
                "message": result.get("message"),
                "command_id": result.get("command_id"),
                "created_at_ms": int(time.time() * 1000),
                "created_at_iso": datetime.now(timezone.utc).isoformat(),
            }
            home_ref(f"schedule_logs/{schedule_id}_{log['created_at_ms']}").set(log)
            return jsonify({"success": bool(result.get("success")), "home_id": HOME_ID, "log": log})

        response = requests.post(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/schedules/{schedule_id}/run-now",
            headers=api_headers(),
            timeout=10,
        )
        return jsonify(response.json()), response.status_code
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.delete("/api/schedules/<schedule_id>")
def delete_schedule(schedule_id: str):
    try:
        if not CLOUD_BACKEND_ENABLED:
            schedule = as_dict(home_ref(f"schedules/{schedule_id}").get())
            if not schedule:
                return jsonify({"success": False, "message": "Schedule not found"}), 404
            updates = {
                "status": "deleted",
                "enabled": False,
                "deleted_by": request.args.get("deleted_by", "pi_dashboard"),
                "deleted_at_ms": int(time.time() * 1000),
                "deleted_at_iso": datetime.now(timezone.utc).isoformat(),
            }
            home_ref(f"schedules/{schedule_id}").update(updates)
            return jsonify({"success": True, "home_id": HOME_ID, "schedule": {**schedule, **updates}})

        response = requests.delete(
            f"{KAHRABAIQ_API_URL}/api/home/{HOME_ID}/schedules/{schedule_id}",
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
