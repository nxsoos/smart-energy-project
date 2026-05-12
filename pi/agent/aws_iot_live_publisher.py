from __future__ import annotations

import json
import os
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from local_state_store import home_snapshot, latest_history, set_path
from timestamp_utils import BAHRAIN_TZ, TIMEZONE, ms_to_iso, now_ms


load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")
load_dotenv()

HOME_ID = os.environ.get("HOME_ID", "home_001")
AWS_IOT_ENDPOINT = os.environ.get("AWS_IOT_ENDPOINT", "").strip()
AWS_IOT_CLIENT_ID = os.environ.get("AWS_IOT_CLIENT_ID", f"smart-energy-pi-{HOME_ID}")
AWS_IOT_LIVE_TOPIC = os.environ.get("AWS_IOT_LIVE_TOPIC", f"homes/{HOME_ID}/live/state")
AWS_IOT_LIVE_INTERVAL_SECONDS = float(os.environ.get("AWS_IOT_LIVE_INTERVAL_SECONDS", "3"))
AWS_IOT_CERT_PATH = os.environ.get("AWS_IOT_CERT_PATH", "certs/device.pem.crt")
AWS_IOT_KEY_PATH = os.environ.get("AWS_IOT_KEY_PATH", "certs/private.pem.key")
AWS_IOT_CA_PATH = os.environ.get("AWS_IOT_CA_PATH", "certs/AmazonRootCA1.pem")
AWS_IOT_RETAIN_LIVE_STATE = os.environ.get("AWS_IOT_RETAIN_LIVE_STATE", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
AWS_IOT_PUBLISH_LOG_EVERY = max(1, int(os.environ.get("AWS_IOT_PUBLISH_LOG_EVERY", "10")))
ESP32_DEVICE_ID = os.environ.get("ESP32_DEVICE_ID", "esp32_01")
SENSOR_STALE_AFTER_SECONDS = float(os.environ.get("SENSOR_STALE_AFTER_SECONDS", "45"))
SMOKE_ALERT_ID = "smoke_detected_room1"
SMOKE_CLEAR_CONFIRMATION_MS = int(os.environ.get("SMOKE_CLEAR_CONFIRMATION_MS", "15000"))
USE_HOME_ASSISTANT_FOR_BREAKERS = os.environ.get("USE_HOME_ASSISTANT_FOR_BREAKERS", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

DEVICE_ORDER = (
    "matter_socket_switch",
    "matter_ac_switch",
    "light_switch",
    "breaker_01",
    "breaker_02",
)
DEVICE_DEFAULTS = {
    "matter_socket_switch": {
        "id": "matter_socket_switch",
        "name": "Socket Switch",
        "type": "matter_switch",
        "branch": "Main",
        "control_method": "home_assistant",
        "energy_supported": False,
        "cloud_online": False,
        "controllable": True,
    },
    "matter_ac_switch": {
        "id": "matter_ac_switch",
        "name": "AC Switch",
        "type": "matter_switch",
        "branch": "Main",
        "control_method": "home_assistant",
        "energy_supported": False,
        "cloud_online": False,
        "controllable": True,
    },
    "light_switch": {
        "id": "light_switch",
        "name": "Light Switch",
        "type": "light_switch",
        "branch": "Light",
        "control_method": "home_assistant",
        "energy_supported": False,
        "cloud_online": False,
        "controllable": True,
    },
    "breaker_01": {
        "id": "breaker_01",
        "name": "AC Breaker",
        "type": "smart_breaker",
        "branch": "AC",
        "control_method": "home_assistant",
        "energy_supported": True,
        "cloud_online": False,
        "controllable": True,
    },
    "breaker_02": {
        "id": "breaker_02",
        "name": "Socket Breaker",
        "type": "smart_breaker",
        "branch": "Socket",
        "control_method": "home_assistant",
        "energy_supported": True,
        "cloud_online": False,
        "controllable": True,
    },
}


def log(message: str) -> None:
    print(f"[AWS IOT LIVE] {datetime.now(BAHRAIN_TZ).isoformat()} {message}", flush=True)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return fallback
    return fallback


def as_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on", "online"}:
            return True
        if normalized in {"false", "0", "no", "off", "offline"}:
            return False
    return fallback


def smoke_text_is_active(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    if any(token in text for token in ("no smoke", "no gas", "clear", "normal", "safe", "not detected")):
        return False
    return "detect" in text or "smoke" in text or "gas" in text or text in {"1", "true", "yes", "on", "alarm"}


def first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [json_safe(item) for item in value if item is not None]
    return value


def compact_dict(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source and source[key] is not None}


def compact_status(status: dict[str, Any]) -> dict[str, Any]:
    return compact_dict(
        status,
        (
            "online",
            "switch",
            "relay_status",
            "lastSeenMs",
            "last_seen_ms",
            "last_seen_iso",
            "error_code",
            "message",
        ),
    )


def compact_sensor_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return compact_dict(
        payload,
        (
            "device_id",
            "home_id",
            "pi_id",
            "temperature",
            "humidity",
            "heatIndex",
            "heat_index",
            "gasResistance",
            "gas_resistance",
            "airQuality",
            "air_quality",
            "airQualityLabel",
            "air_quality_label",
            "smokeDetected",
            "smoke_detected",
            "gasDetected",
            "gas_detected",
            "motionDetected",
            "motion_detected",
            "soundLevel",
            "sound_level",
            "lightLevel",
            "light_level",
            "occupancy",
            "occupied",
            "online",
            "sensorOnline",
            "sensor_online",
            "stale",
            "ahtOk",
            "ens160Ok",
            "timestampMs",
            "timestamp_ms",
            "timestampIso",
            "timestamp_iso",
            "readableTime",
            "readable_time",
        ),
    )


def latest_sensor_payload(home: dict[str, Any]) -> dict[str, Any]:
    devices = as_dict(home.get("devices"))
    esp32 = as_dict(devices.get(ESP32_DEVICE_ID))
    sensors = as_dict(esp32.get("sensors"))
    if sensors:
        return annotate_sensor_freshness(sensors)
    return annotate_sensor_freshness(latest_history("sensor_logs"))


def sensor_timestamp_ms(payload: dict[str, Any]) -> int:
    value = first_present(
        payload.get("timestampMs"),
        payload.get("timestamp_ms"),
        payload.get("timestamp"),
        payload.get("readable_time"),
        payload.get("timestampIso"),
        payload.get("timestamp_iso"),
    )
    if isinstance(value, (int, float)):
        integer = int(value)
        return integer if integer > 1000000000000 else integer * 1000
    if isinstance(value, str):
        maybe_int = value.strip()
        if maybe_int.isdigit():
            integer = int(maybe_int)
            return integer if integer > 1000000000000 else integer * 1000
        try:
            parsed = datetime.fromisoformat(maybe_int.replace("Z", "+00:00"))
            return int(parsed.timestamp() * 1000)
        except ValueError:
            return 0
    return 0


def annotate_sensor_freshness(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {
            "online": False,
            "sensorOnline": False,
            "sensor_online": False,
            "stale": True,
            "ahtOk": False,
            "ens160Ok": False,
        }
    timestamp_ms = sensor_timestamp_ms(payload)
    stale = not timestamp_ms or now_ms() - timestamp_ms > SENSOR_STALE_AFTER_SECONDS * 1000
    return compact_sensor_payload({
        **payload,
        "timestampMs": timestamp_ms or payload.get("timestampMs"),
        "timestamp_ms": timestamp_ms or payload.get("timestamp_ms"),
        "online": not stale,
        "sensorOnline": not stale,
        "sensor_online": not stale,
        "stale": stale,
    })


def normalize_device(device_id: str, raw_device: dict[str, Any]) -> dict[str, Any]:
    defaults = DEVICE_DEFAULTS.get(device_id, {"id": device_id, "name": device_id})
    device = {**defaults, **raw_device, "id": raw_device.get("id") or defaults.get("id") or device_id}
    status = as_dict(device.get("status"))
    metering = as_dict(device.get("metering"))
    if device_id.startswith("breaker_") and USE_HOME_ASSISTANT_FOR_BREAKERS:
        device["control_method"] = "home_assistant"
        device["cloud_online"] = False
        if str(device.get("name") or "").lower() in {"switch breaker", "ac breaker"}:
            device["name"] = defaults.get("name") or device.get("name")
        if str(device.get("branch") or "").lower().startswith("branch"):
            device["branch"] = defaults.get("branch") or device.get("branch")
    state = str(first_present(device.get("state"), device.get("display_state"), "")).lower()
    switch = first_present(status.get("switch"), status.get("relay_status"), device.get("switch"))
    switch_on = as_bool(switch, fallback=state == "on")
    online = as_bool(first_present(status.get("online"), device.get("online")), fallback=True)
    local_online = as_bool(device.get("local_online"), fallback=online)

    power_w = as_number(
        first_present(device.get("power_W"), device.get("power_w"), device.get("currentPower"), metering.get("power_W"), metering.get("power_w"), metering.get("power"))
    )
    voltage_v = as_number(
        first_present(device.get("voltage_V"), device.get("voltage_v"), metering.get("voltage_V"), metering.get("voltage"))
    )
    current_a = as_number(
        first_present(device.get("current_A"), device.get("current_a"), metering.get("current_A"), metering.get("current"))
    )
    energy_kwh = as_number(
        first_present(device.get("energy_kWh"), device.get("energy_kwh"), device.get("today_kwh"), metering.get("energy_kWh"), metering.get("energy_kwh"))
    )

    normalized_status = compact_status({
        **compact_status(status),
        "switch": switch_on,
        "relay_status": "on" if switch_on else "off",
        "online": online,
    })
    normalized_metering = {
        "power_W": round(power_w, 3),
        "voltage_V": round(voltage_v, 3),
        "current_A": round(current_a, 3),
        "energy_kWh": round(energy_kwh, 6),
    }
    return {
        "name": device.get("name") or device.get("label") or device_id,
        "id": device_id,
        "device_id": device_id,
        "type": device.get("type") or defaults.get("type", "device"),
        "branch": device.get("branch") or defaults.get("branch", "Main"),
        "state": "on" if switch_on else "off",
        "display_state": "on" if switch_on else "off",
        "status": normalized_status,
        "metering": normalized_metering,
        "online": online,
        "local_online": local_online,
        "cloud_online": as_bool(device.get("cloud_online"), fallback=defaults.get("cloud_online", True)),
        "controllable": as_bool(device.get("controllable"), fallback=True),
        "energy_supported": as_bool(device.get("energy_supported"), fallback=defaults.get("energy_supported", True)),
        "power_W": round(power_w, 3),
        "voltage_V": round(voltage_v, 3),
        "current_A": round(current_a, 3),
        "energy_kWh": round(energy_kwh, 6),
        "ha_entity_id": device.get("ha_entity_id"),
        "last_command_status": device.get("last_command_status"),
        "last_command_message": str(device.get("last_command_message") or "")[:160] or None,
    }


def collect_devices(home: dict[str, Any]) -> dict[str, Any]:
    raw_devices = as_dict(home.get("devices"))
    devices: dict[str, Any] = {}
    for device_id in DEVICE_ORDER:
        devices[device_id] = normalize_device(device_id, as_dict(raw_devices.get(device_id)))
    for device_id in sorted(raw_devices):
        if device_id in devices or device_id == ESP32_DEVICE_ID:
            continue
        devices[device_id] = normalize_device(device_id, as_dict(raw_devices.get(device_id)))
    if ESP32_DEVICE_ID in raw_devices:
        esp32 = as_dict(raw_devices.get(ESP32_DEVICE_ID))
        devices[ESP32_DEVICE_ID] = {
            "id": ESP32_DEVICE_ID,
            "device_id": ESP32_DEVICE_ID,
            "name": "Room Sensor",
            "type": "sensor_hub",
            "online": as_bool(first_present(as_dict(esp32.get("status")).get("online"), esp32.get("online")), fallback=False),
            "status": compact_status(as_dict(esp32.get("status"))),
            "sensors": compact_sensor_payload(as_dict(esp32.get("sensors"))),
        }
    return devices


def energy_summary(devices: dict[str, Any], home: dict[str, Any]) -> dict[str, Any]:
    backend = as_dict(as_dict(home.get("backend")).get("energy"))
    current_total = as_dict(backend.get("current_total"))
    dashboard_energy = as_dict(as_dict(home.get("dashboard")).get("energy"))
    total_power = 0.0
    total_energy = 0.0
    voltage_values: list[float] = []
    current_values: list[float] = []

    for device_id, device in devices.items():
        if device_id == ESP32_DEVICE_ID:
            continue
        metering = as_dict(device.get("metering"))
        total_power += as_number(metering.get("power_W"))
        total_energy += as_number(metering.get("energy_kWh"))
        voltage = as_number(metering.get("voltage_V"))
        current = as_number(metering.get("current_A"))
        if voltage > 0:
            voltage_values.append(voltage)
        if current > 0:
            current_values.append(current)

    voltage = sum(voltage_values) / len(voltage_values) if voltage_values else 0.0
    current = sum(current_values) / len(current_values) if current_values else 0.0
    tariff = as_number(first_present(dashboard_energy.get("tariff"), home.get("tariff_bhd_per_kwh")), 0.003)
    energy_today = as_number(
        first_present(
            current_total.get("total_estimated_energy_kWh"),
            current_total.get("total_energy_kWh"),
            dashboard_energy.get("energyTodayKwh"),
        ),
        total_energy,
    )
    power = as_number(
        first_present(
            current_total.get("total_power_W"),
            current_total.get("current_power_w"),
            dashboard_energy.get("currentPowerW"),
        ),
        total_power,
    )

    return {
        "timestampMs": now_ms(),
        "timestampIso": ms_to_iso(now_ms()),
        "currentPowerW": round(power, 3),
        "powerW": round(power, 3),
        "energyTodayKwh": round(energy_today, 6),
        "totalEnergyKwh": round(energy_today, 6),
        "costToday": round(energy_today * tariff, 6),
        "tariff": tariff,
        "voltageV": round(as_number(first_present(current_total.get("voltage_V"), dashboard_energy.get("voltageV")), voltage), 3),
        "currentA": round(as_number(first_present(current_total.get("current_A"), dashboard_energy.get("currentA")), current), 3),
    }


def command_summary(home: dict[str, Any]) -> dict[str, Any]:
    return {}


def smoke_is_clear_for(home: dict[str, Any], timestamp_ms: int) -> bool:
    devices = as_dict(home.get("devices"))
    esp32 = as_dict(devices.get(ESP32_DEVICE_ID))
    sensors = as_dict(esp32.get("sensors"))
    smoke_state = as_dict(as_dict(home.get("safety")).get("smoke_state"))
    if str(smoke_state.get("status", "")).lower() != "clear":
        return False
    if as_bool(sensors.get("smoke")) or smoke_text_is_active(sensors.get("smoke_text")) or smoke_text_is_active(sensors.get("smoke_status")):
        return False
    clear_started_at_ms = int(as_number(smoke_state.get("last_clear_at_ms"), 0))
    return clear_started_at_ms > 0 and timestamp_ms - clear_started_at_ms >= SMOKE_CLEAR_CONFIRMATION_MS


def clear_stale_smoke_alert_if_needed(home: dict[str, Any], timestamp_ms: int) -> dict[str, Any]:
    if not smoke_is_clear_for(home, timestamp_ms):
        return home
    safety = dict(as_dict(home.get("safety")))
    emergency_mode = dict(as_dict(safety.get("emergency_mode")))
    if emergency_mode.get("active") is True:
        emergency_mode.update(
            {
                "active": False,
                "ended_at_ms": timestamp_ms,
                "ended_at_iso": ms_to_iso(timestamp_ms),
                "updated_at_ms": timestamp_ms,
                "updated_at_iso": ms_to_iso(timestamp_ms),
            }
        )
        safety["emergency_mode"] = emergency_mode
        set_path(f"homes/{HOME_ID}/safety/emergency_mode", emergency_mode)
    set_path(f"homes/{HOME_ID}/alerts/active/{SMOKE_ALERT_ID}", None)
    alerts = dict(as_dict(home.get("alerts")))
    active = dict(as_dict(alerts.get("active")))
    active.pop(SMOKE_ALERT_ID, None)
    alerts["active"] = active
    return {**home, "alerts": alerts, "safety": safety}


def compact_alerts(home: dict[str, Any]) -> list[dict[str, Any]]:
    active = as_dict(as_dict(home.get("alerts")).get("active"))
    alerts: list[dict[str, Any]] = []
    for alert_id, alert in list(active.items())[:10]:
        compact = compact_dict(
            as_dict(alert),
            (
                "id",
                "alert_id",
                "type",
                "alert_type",
                "severity",
                "status",
                "title",
                "message",
                "timestamp_ms",
                "timestamp_iso",
                "updated_at_ms",
                "updated_at_iso",
            ),
        )
        compact["id"] = str(compact.get("id") or compact.get("alert_id") or alert_id)
        if "message" in compact:
            compact["message"] = str(compact["message"])[:180]
        if "title" in compact:
            compact["title"] = str(compact["title"])[:80]
        alerts.append(compact)
    return alerts


def compact_safety(home: dict[str, Any]) -> dict[str, Any]:
    safety = as_dict(home.get("safety"))
    return {
        "smoke_state": compact_dict(
            as_dict(safety.get("smoke_state")),
            (
                "status",
                "active",
                "smoke_detected",
                "gas_detected",
                "consecutive_detections",
                "last_detected_at_ms",
                "last_detected_at_iso",
                "last_clear_at_ms",
                "last_clear_at_iso",
                "updated_at_ms",
                "updated_at_iso",
            ),
        ),
        "emergency_mode": compact_dict(
            as_dict(safety.get("emergency_mode")),
            ("active", "reason", "started_at_ms", "started_at_iso", "ended_at_ms", "ended_at_iso", "updated_at_ms", "updated_at_iso"),
        ),
    }


def compact_control(home: dict[str, Any]) -> dict[str, Any]:
    return compact_dict(
        as_dict(home.get("control")),
        (
            "mode",
            "updated_at_ms",
            "updated_at_iso",
        ),
    )


def compact_occupancy(home: dict[str, Any]) -> dict[str, Any]:
    return compact_dict(
        as_dict(as_dict(home.get("occupancy")).get("room1")),
        (
            "occupied",
            "is_occupied",
            "confidence",
            "motion_recent",
            "sound_recent",
            "light_level",
            "updated_at_ms",
            "updated_at_iso",
        ),
    )


def build_live_payload() -> dict[str, Any]:
    timestamp_ms = now_ms()
    home = clear_stale_smoke_alert_if_needed(home_snapshot(HOME_ID), timestamp_ms)
    devices = collect_devices(home)
    room = latest_sensor_payload(home)
    occupancy = compact_occupancy(home)
    safety = compact_safety(home)
    return json_safe(
        {
            "schema": "smart_energy_live_state_v1",
            "homeId": HOME_ID,
            "home_id": HOME_ID,
            "timestampMs": timestamp_ms,
            "timestamp_ms": timestamp_ms,
            "timestampIso": ms_to_iso(timestamp_ms),
            "timestamp_iso": ms_to_iso(timestamp_ms),
            "timezone": TIMEZONE,
            "source": "raspberry_pi_local_state",
            "room": room,
            "devices": devices,
            "energy": energy_summary(devices, home),
            "commands": command_summary(home),
            "alerts": compact_alerts(home),
            "occupancy": occupancy,
            "safety": safety,
            "control": compact_control(home),
        }
    )


def validate_config() -> None:
    missing = [
        name
        for name, value in {
            "AWS_IOT_ENDPOINT": AWS_IOT_ENDPOINT,
            "AWS_IOT_CERT_PATH": AWS_IOT_CERT_PATH,
            "AWS_IOT_KEY_PATH": AWS_IOT_KEY_PATH,
            "AWS_IOT_CA_PATH": AWS_IOT_CA_PATH,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required AWS IoT settings: {', '.join(missing)}")
    for path in (AWS_IOT_CERT_PATH, AWS_IOT_KEY_PATH, AWS_IOT_CA_PATH):
        if not Path(path).exists():
            raise RuntimeError(f"AWS IoT certificate file not found: {path}")


def create_connection():
    from awscrt import mqtt
    from awsiot import mqtt_connection_builder

    connection = mqtt_connection_builder.mtls_from_path(
        endpoint=AWS_IOT_ENDPOINT,
        cert_filepath=AWS_IOT_CERT_PATH,
        pri_key_filepath=AWS_IOT_KEY_PATH,
        ca_filepath=AWS_IOT_CA_PATH,
        client_id=AWS_IOT_CLIENT_ID,
        clean_session=False,
        keep_alive_secs=30,
    )
    return connection, mqtt


def wait_for_publish(result: Any) -> None:
    # awsiotsdk versions differ: some return a Future, others return (Future, packet_id).
    future = result[0] if isinstance(result, tuple) else result
    if hasattr(future, "result"):
        future.result()


def main() -> int:
    validate_config()
    log(
        f"Started for {HOME_ID}; topic={AWS_IOT_LIVE_TOPIC}; "
        f"endpoint={AWS_IOT_ENDPOINT}; interval={AWS_IOT_LIVE_INTERVAL_SECONDS}s"
    )
    connection, mqtt = create_connection()
    connection.connect().result()
    log("Connected to AWS IoT Core")
    publish_count = 0
    try:
        while True:
            started = time.time()
            payload = build_live_payload()
            encoded = json.dumps(payload, separators=(",", ":"), default=str)
            wait_for_publish(
                connection.publish(
                    topic=AWS_IOT_LIVE_TOPIC,
                    payload=encoded,
                    qos=mqtt.QoS.AT_LEAST_ONCE,
                    retain=AWS_IOT_RETAIN_LIVE_STATE,
                )
            )
            publish_count += 1
            if publish_count == 1 or publish_count % AWS_IOT_PUBLISH_LOG_EVERY == 0:
                log(
                    f"Published {publish_count} message(s) to {AWS_IOT_LIVE_TOPIC}; "
                    f"bytes={len(encoded)}; retain={AWS_IOT_RETAIN_LIVE_STATE}"
                )
            elapsed = time.time() - started
            time.sleep(max(1, AWS_IOT_LIVE_INTERVAL_SECONDS - elapsed))
    finally:
        connection.disconnect().result()


if __name__ == "__main__":
    raise SystemExit(main())
