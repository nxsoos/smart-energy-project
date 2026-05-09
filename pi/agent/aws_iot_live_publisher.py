from __future__ import annotations

import json
import os
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from local_state_store import home_snapshot, latest_history
from timestamp_utils import BAHRAIN_TZ, TIMEZONE, ms_to_iso, now_ms


load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")
load_dotenv()

HOME_ID = os.environ.get("HOME_ID", "home_001")
AWS_IOT_ENDPOINT = os.environ.get("AWS_IOT_ENDPOINT", "").strip()
AWS_IOT_CLIENT_ID = os.environ.get("AWS_IOT_CLIENT_ID", f"smart-energy-pi-{HOME_ID}")
AWS_IOT_LIVE_TOPIC = os.environ.get("AWS_IOT_LIVE_TOPIC", f"homes/{HOME_ID}/live/state")
AWS_IOT_LIVE_INTERVAL_SECONDS = float(os.environ.get("AWS_IOT_LIVE_INTERVAL_SECONDS", "15"))
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

DEVICE_ORDER = (
    "matter_socket_switch",
    "matter_ac_switch",
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
    "breaker_01": {
        "id": "breaker_01",
        "name": "Switch Breaker",
        "type": "smart_breaker",
        "branch": "Branch 1",
        "control_method": "tuya_cloud",
        "energy_supported": True,
        "cloud_online": True,
        "controllable": True,
    },
    "breaker_02": {
        "id": "breaker_02",
        "name": "AC Breaker",
        "type": "smart_breaker",
        "branch": "Branch 2",
        "control_method": "tuya_cloud",
        "energy_supported": True,
        "cloud_online": True,
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
    return {
        **payload,
        "timestampMs": timestamp_ms or payload.get("timestampMs"),
        "timestamp_ms": timestamp_ms or payload.get("timestamp_ms"),
        "online": not stale,
        "sensorOnline": not stale,
        "sensor_online": not stale,
        "stale": stale,
    }


def normalize_device(device_id: str, raw_device: dict[str, Any]) -> dict[str, Any]:
    defaults = DEVICE_DEFAULTS.get(device_id, {"id": device_id, "name": device_id})
    device = {**defaults, **raw_device, "id": raw_device.get("id") or defaults.get("id") or device_id}
    status = as_dict(device.get("status"))
    metering = as_dict(device.get("metering"))
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

    normalized_status = {
        **status,
        "switch": switch_on,
        "relay_status": "on" if switch_on else "off",
        "online": online,
    }
    normalized_metering = {
        **metering,
        "power_W": round(power_w, 3),
        "voltage_V": round(voltage_v, 3),
        "current_A": round(current_a, 3),
        "energy_kWh": round(energy_kwh, 6),
    }
    return {
        **device,
        "name": device.get("name") or device.get("label") or device_id,
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
        devices[ESP32_DEVICE_ID] = as_dict(raw_devices.get(ESP32_DEVICE_ID))
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
    latest = as_dict(as_dict(home.get("commands")).get("latest_by_device"))
    return {device_id: {"latest": as_dict(value)} for device_id, value in latest.items()}


def build_live_payload() -> dict[str, Any]:
    timestamp_ms = now_ms()
    home = home_snapshot(HOME_ID)
    devices = collect_devices(home)
    room = latest_sensor_payload(home)
    occupancy = as_dict(as_dict(home.get("occupancy")).get("room1"))
    safety = as_dict(home.get("safety"))
    dashboard = as_dict(home.get("dashboard"))
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
            "alerts": as_dict(home.get("alerts")),
            "occupancy": occupancy,
            "safety": safety,
            "control": as_dict(home.get("control")),
            "settings": as_dict(home.get("settings")),
            "ai": as_dict(dashboard.get("ai")),
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
