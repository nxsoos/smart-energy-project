from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from tuya_connector import TUYA_LOGGER, TuyaOpenAPI

from local_state_store import add_history, home_ref
from timestamp_utils import BAHRAIN_TZ, TIMEZONE, ms_to_iso, now_ms


load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")
load_dotenv()

HOME_ID = os.environ.get("HOME_ID", "home_001")
TUYA_ACCESS_ID = os.environ.get("TUYA_ACCESS_ID", "")
TUYA_ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET", "")
TUYA_API_ENDPOINT = os.environ.get("TUYA_API_ENDPOINT", "https://openapi.tuyaeu.com")
TUYA_BREAKER_POLL_SECONDS = float(os.environ.get("TUYA_BREAKER_POLL_SECONDS", "15"))
LOCAL_HISTORY_MAX_RECORDS = int(os.environ.get("LOCAL_HISTORY_MAX_RECORDS", "5000"))
USE_TUYA_CLOUD_FOR_BREAKERS = os.environ.get("USE_TUYA_CLOUD_FOR_BREAKERS", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

BREAKERS = {
    "breaker_01": {
        "name": "Switch Breaker",
        "branch": "Branch 1",
        "tuya_device_id": os.environ.get("TUYA_BREAKER_01_DEVICE_ID", ""),
    },
    "breaker_02": {
        "name": "AC Breaker",
        "branch": "Branch 2",
        "tuya_device_id": os.environ.get("TUYA_BREAKER_02_DEVICE_ID", ""),
    },
}


def log(message: str) -> None:
    print(f"[TUYA BREAKER POLLER] {datetime.now(BAHRAIN_TZ).isoformat()} {message}", flush=True)


def as_number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
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


def status_map(items: Any) -> dict[str, Any]:
    if not isinstance(items, list):
        return {}
    return {
        str(item["code"]): item.get("value")
        for item in items
        if isinstance(item, dict) and "code" in item
    }


def pick(status: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in status and status[key] is not None:
            return status[key]
    return None


def scaled_power_w(value: Any) -> float:
    number = as_number(value)
    if number > 100000:
        return number / 1000
    if number > 10000:
        return number / 10
    return number


def scaled_voltage_v(value: Any) -> float:
    number = as_number(value)
    if number > 1000:
        return number / 10
    return number


def scaled_current_a(value: Any) -> float:
    number = as_number(value)
    if number > 100:
        return number / 1000
    return number


def scaled_energy_kwh(value: Any) -> float:
    number = as_number(value)
    if number > 10000:
        return number / 1000
    if number > 100:
        return number / 100
    return number


def create_cloud() -> TuyaOpenAPI:
    if not TUYA_ACCESS_ID or not TUYA_ACCESS_SECRET:
        raise RuntimeError("TUYA_ACCESS_ID and TUYA_ACCESS_SECRET are required.")
    TUYA_LOGGER.setLevel("INFO")
    cloud = TuyaOpenAPI(TUYA_API_ENDPOINT, TUYA_ACCESS_ID, TUYA_ACCESS_SECRET)
    cloud.connect()
    return cloud


def fetch_breaker(cloud: TuyaOpenAPI, device_id: str, config: dict[str, Any]) -> dict[str, Any]:
    tuya_device_id = str(config.get("tuya_device_id") or "")
    if not tuya_device_id:
        raise RuntimeError(f"Missing Tuya device ID for {device_id}")

    info_response = cloud.get(f"/v1.0/devices/{tuya_device_id}")
    status_response = cloud.get(f"/v1.0/devices/{tuya_device_id}/status")
    if not isinstance(status_response, dict) or status_response.get("success") is not True:
        raise RuntimeError(f"Tuya status read failed for {device_id}: {status_response}")

    info = info_response.get("result") if isinstance(info_response, dict) else {}
    if not isinstance(info, dict):
        info = {}
    status = status_map(status_response.get("result"))
    timestamp_ms = now_ms()
    switch_on = as_bool(pick(status, "switch", "switch_1", "relay_status"))
    online = as_bool(info.get("online"), fallback=True)
    power_w = scaled_power_w(pick(status, "cur_power", "power", "add_ele", "power_w", "power_W"))
    voltage_v = scaled_voltage_v(pick(status, "cur_voltage", "voltage", "voltage_v", "voltage_V"))
    current_a = scaled_current_a(pick(status, "cur_current", "current", "current_a", "current_A"))
    energy_kwh = scaled_energy_kwh(pick(status, "add_ele", "energy", "energy_kwh", "energy_kWh", "total_energy"))

    return {
        "id": device_id,
        "type": "smart_breaker",
        "name": config["name"],
        "branch": config["branch"],
        "control_method": "tuya_cloud",
        "tuya_device_id": tuya_device_id,
        "online": online,
        "local_online": online,
        "cloud_online": online,
        "controllable": True,
        "energy_supported": True,
        "state": "on" if switch_on else "off",
        "display_state": "on" if switch_on else "off",
        "status": {
            "online": online,
            "switch": switch_on,
            "relay_status": "on" if switch_on else "off",
            "lastSeenMs": timestamp_ms,
            "last_seen_ms": timestamp_ms,
            "last_seen_iso": ms_to_iso(timestamp_ms),
            "raw": status,
        },
        "metering": {
            "power_W": round(power_w, 3),
            "voltage_V": round(voltage_v, 3),
            "current_A": round(current_a, 3),
            "energy_kWh": round(energy_kwh, 6),
        },
        "power_W": round(power_w, 3),
        "voltage_V": round(voltage_v, 3),
        "current_A": round(current_a, 3),
        "energy_kWh": round(energy_kwh, 6),
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": ms_to_iso(timestamp_ms),
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": ms_to_iso(timestamp_ms),
        "timezone": TIMEZONE,
    }


def save_breaker(device_id: str, payload: dict[str, Any]) -> None:
    home_ref(HOME_ID, f"devices/{device_id}").update(payload)
    add_history(device_id, f"{device_id}_{payload['timestamp_ms']}", payload, max_records=LOCAL_HISTORY_MAX_RECORDS)


def poll_once(cloud: TuyaOpenAPI) -> int:
    updated = 0
    for device_id, config in BREAKERS.items():
        try:
            payload = fetch_breaker(cloud, device_id, config)
            save_breaker(device_id, payload)
            updated += 1
        except Exception as error:
            timestamp_ms = now_ms()
            home_ref(HOME_ID, f"devices/{device_id}").update(
                {
                    "id": device_id,
                    "type": "smart_breaker",
                    "name": config["name"],
                    "branch": config["branch"],
                    "control_method": "tuya_cloud",
                    "online": False,
                    "local_online": False,
                    "cloud_online": False,
                    "last_command_message": str(error),
                    "updated_at_ms": timestamp_ms,
                    "updated_at_iso": ms_to_iso(timestamp_ms),
                }
            )
            log(f"{device_id} poll failed: {error}")
    return updated


def main() -> int:
    if not USE_TUYA_CLOUD_FOR_BREAKERS:
        log("Tuya Cloud breaker polling is disabled. Stop/disable this service for the Home Assistant breaker path.")
        while True:
            time.sleep(3600)
    log(f"Started for {HOME_ID}; endpoint={TUYA_API_ENDPOINT}; interval={TUYA_BREAKER_POLL_SECONDS}s")
    cloud = create_cloud()
    while True:
        started = time.time()
        try:
            updated = poll_once(cloud)
            if updated:
                log(f"Updated {updated} breaker(s)")
        except Exception as error:
            log(f"Polling failed: {error}; reconnecting")
            cloud = create_cloud()
        elapsed = time.time() - started
        time.sleep(max(1, TUYA_BREAKER_POLL_SECONDS - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
