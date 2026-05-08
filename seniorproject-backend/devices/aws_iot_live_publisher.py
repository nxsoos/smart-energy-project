from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any

from local_state_store import home_snapshot

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from timestamp_utils import BAHRAIN_TZ, TIMEZONE, ms_to_iso, now_ms


HOME_ID = os.environ.get("HOME_ID", "home_001")
AWS_IOT_ENDPOINT = os.environ.get("AWS_IOT_ENDPOINT", "").strip()
AWS_IOT_CERT_PATH = os.environ.get("AWS_IOT_CERT_PATH", "certs/device.pem.crt")
AWS_IOT_KEY_PATH = os.environ.get("AWS_IOT_KEY_PATH", "certs/private.pem.key")
AWS_IOT_CA_PATH = os.environ.get("AWS_IOT_CA_PATH", "certs/AmazonRootCA1.pem")
AWS_IOT_CLIENT_ID = os.environ.get("AWS_IOT_CLIENT_ID", f"smart-energy-pi-{HOME_ID}")
AWS_IOT_LIVE_TOPIC = os.environ.get("AWS_IOT_LIVE_TOPIC", f"homes/{HOME_ID}/live/state")
AWS_IOT_LIVE_INTERVAL_SECONDS = float(os.environ.get("AWS_IOT_LIVE_INTERVAL_SECONDS", "3"))
AWS_IOT_RETAIN_LIVE_STATE = os.environ.get("AWS_IOT_RETAIN_LIVE_STATE", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
AWS_IOT_PUBLISH_LOG_EVERY = int(os.environ.get("AWS_IOT_PUBLISH_LOG_EVERY", "10"))


def log(message: str) -> None:
    print(f"[AWS IOT LIVE] {datetime.now(BAHRAIN_TZ).isoformat()} {message}", flush=True)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on", "online", "motion", "detected", "smoke", "gas"}:
            return True
        if normalized in {"false", "0", "no", "off", "offline", "clear", "no motion"}:
            return False
    return None


def pick(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


def compact_room(esp32: dict[str, Any]) -> dict[str, Any]:
    sensors = as_dict(esp32.get("sensors"))
    status = as_dict(esp32.get("status"))
    source = {**sensors, **status}
    return {
        "timestampMs": pick(source, "timestamp_ms", "last_seen_ms", "lastSeenMs"),
        "timestampIso": pick(source, "timestamp_iso", "last_seen_iso"),
        "temperature": pick(source, "temperature"),
        "humidity": pick(source, "humidity"),
        "aqi": pick(source, "aqi"),
        "tvoc": pick(source, "tvoc"),
        "eco2": pick(source, "eco2"),
        "lightRaw": pick(source, "light_raw"),
        "lightStatus": pick(source, "light_status"),
        "motion": normalize_bool(pick(source, "motion", "motion_text")),
        "motionText": pick(source, "motion_text"),
        "smoke": normalize_bool(pick(source, "smoke", "smoke_text", "smoke_status")),
        "smokeRaw": pick(source, "smoke_raw"),
        "smokeText": pick(source, "smoke_text", "smoke_status"),
        "soundRaw": pick(source, "sound_raw"),
        "noise": pick(source, "noise"),
        "noiseText": pick(source, "noise_text"),
        "ahtOk": normalize_bool(pick(source, "aht_ok")),
        "ens160Ok": normalize_bool(pick(source, "ens160_ok")),
    }


def compact_device(device_id: str, device: dict[str, Any]) -> dict[str, Any]:
    status = as_dict(device.get("status"))
    metering = as_dict(device.get("metering"))
    state = str(device.get("display_state") or device.get("state") or status.get("relay_status") or "unknown").lower()
    switch = normalize_bool(status.get("switch"))
    if switch is True:
        state = "on"
    elif switch is False:
        state = "off"
    return {
        "deviceId": device_id,
        "name": device.get("name") or device_id,
        "type": device.get("type"),
        "state": state,
        "online": normalize_bool(status.get("online") if status else device.get("online")),
        "localOnline": normalize_bool(device.get("local_online")),
        "cloudOnline": normalize_bool(device.get("cloud_online")),
        "controlMethod": device.get("control_method"),
        "powerW": pick(metering, "power_W", "power_w") or device.get("power_w"),
        "voltageV": pick(metering, "voltage_V", "voltage_v"),
        "currentA": pick(metering, "current_A", "current_a"),
        "energyKwh": pick(metering, "energy_kWh", "energy_kwh"),
        "lastSeenMs": pick(status, "lastSeenMs", "last_seen_ms") or device.get("updated_at_ms"),
        "commandInProgress": normalize_bool(device.get("command_in_progress")),
        "pendingTargetState": device.get("pending_target_state"),
        "lastCommandStatus": device.get("last_command_status"),
        "lastCommandMessage": device.get("last_command_message"),
    }


def build_live_state() -> dict[str, Any]:
    timestamp_ms = now_ms()
    home = home_snapshot(HOME_ID)
    devices = as_dict(home.get("devices"))
    esp32 = as_dict(devices.get("esp32_01"))
    live_devices = {
        device_id: compact_device(device_id, as_dict(device))
        for device_id, device in devices.items()
        if device_id.startswith("breaker_") or device_id.startswith("matter_")
    }
    total_power = sum(float(device.get("powerW") or 0) for device in live_devices.values())
    total_energy = sum(float(device.get("energyKwh") or 0) for device in live_devices.values())
    voltage_values = [
        float(device.get("voltageV"))
        for device in live_devices.values()
        if isinstance(device.get("voltageV"), (int, float)) and float(device.get("voltageV")) > 0
    ]
    current_values = [
        float(device.get("currentA"))
        for device in live_devices.values()
        if isinstance(device.get("currentA"), (int, float)) and float(device.get("currentA")) > 0
    ]
    average_voltage = sum(voltage_values) / len(voltage_values) if voltage_values else 0
    total_current = sum(current_values)
    alerts = as_dict(as_dict(home.get("alerts")).get("active"))
    return {
        "schema": "smart_energy_live_state_v1",
        "homeId": HOME_ID,
        "timestampMs": timestamp_ms,
        "timestampIso": ms_to_iso(timestamp_ms),
        "timezone": TIMEZONE,
        "source": "raspberry_pi_local_state",
        "room": compact_room(esp32),
        "devices": live_devices,
        "energy": {
            "currentPowerW": round(total_power, 3),
            "voltageV": round(average_voltage, 3),
            "currentA": round(total_current, 3),
            "energyTodayKwh": round(total_energy, 6),
            "totalEnergyKwh": round(total_energy, 6),
        },
        "safety": as_dict(home.get("safety")),
        "alerts": [
            {"id": alert_id, **as_dict(alert)}
            for alert_id, alert in alerts.items()
            if isinstance(alert, dict)
        ],
        "control": as_dict(home.get("control")),
    }


def create_connection():
    from awscrt import io, mqtt
    from awsiot import mqtt_connection_builder

    if not AWS_IOT_ENDPOINT:
        raise RuntimeError("AWS_IOT_ENDPOINT is required.")

    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
    connection = mqtt_connection_builder.mtls_from_path(
        endpoint=AWS_IOT_ENDPOINT,
        cert_filepath=AWS_IOT_CERT_PATH,
        pri_key_filepath=AWS_IOT_KEY_PATH,
        ca_filepath=AWS_IOT_CA_PATH,
        client_bootstrap=client_bootstrap,
        client_id=AWS_IOT_CLIENT_ID,
        clean_session=False,
        keep_alive_secs=30,
    )
    return connection, mqtt


def publish_once(connection: Any, mqtt: Any) -> int:
    payload = json.dumps(build_live_state(), separators=(",", ":"), default=str)
    publish_result = connection.publish(
        topic=AWS_IOT_LIVE_TOPIC,
        payload=payload,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        retain=AWS_IOT_RETAIN_LIVE_STATE,
    )
    publish_future = publish_result[0] if isinstance(publish_result, tuple) else publish_result
    if hasattr(publish_future, "result"):
        publish_future.result(timeout=10)
    return len(payload)


def main() -> int:
    log(f"Started for {HOME_ID}; topic={AWS_IOT_LIVE_TOPIC}; endpoint={AWS_IOT_ENDPOINT}")
    connection, mqtt = create_connection()
    connection.connect().result()
    log("Connected to AWS IoT Core")
    publish_count = 0
    try:
        while True:
            started = time.time()
            try:
                payload_bytes = publish_once(connection, mqtt)
                publish_count += 1
                if publish_count == 1 or (
                    AWS_IOT_PUBLISH_LOG_EVERY > 0
                    and publish_count % AWS_IOT_PUBLISH_LOG_EVERY == 0
                ):
                    log(
                        f"Published {publish_count} message(s) to "
                        f"{AWS_IOT_LIVE_TOPIC}; bytes={payload_bytes}; "
                        f"retain={AWS_IOT_RETAIN_LIVE_STATE}"
                    )
            except Exception as error:
                log(f"Publish failed: {error}")
            elapsed = time.time() - started
            time.sleep(max(1, AWS_IOT_LIVE_INTERVAL_SECONDS - elapsed))
    finally:
        connection.disconnect().result()


if __name__ == "__main__":
    raise SystemExit(main())
