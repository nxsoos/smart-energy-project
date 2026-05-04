import json
import time
import logging
import requests
from tuya_connector import TuyaOpenAPI, TUYA_LOGGER

# Raspberry Pi hub role:
# This optional telemetry poller reads Tuya breaker metering/status data and
# writes latest/history values to Firebase. Leave it disabled in main.py until
# we confirm continuous Tuya polling is needed alongside the command controller.

# =========================================================
# TUYA CONFIG
# =========================================================
ACCESS_ID = "wsxgdxhatq8h7jmnr97n"
ACCESS_KEY = "49a3750db4434937a1f725c8b1e28e82"
API_ENDPOINT = "https://openapi.tuyaeu.com"   # Central Europe

# =========================================================
# FIREBASE CONFIG
# =========================================================
FIREBASE_DB_URL = "https://seniorproject-energy-default-rtdb.asia-southeast1.firebasedatabase.app"
HOME_ID = "home_001"
POLL_INTERVAL_SECONDS = 5
OFFLINE_AFTER_FAILURES = 2

# =========================================================
# BREAKERS CONFIG
# Replace the device IDs with your actual Tuya breaker IDs
# =========================================================
BREAKERS = [
    {
        "firebase_key": "breaker_01",
        "name": "Switch Breaker",
        "device_id": "bfdd92cd1b6554f95c0h2a"
    },
    {
        "firebase_key": "breaker_02",
        "name": "AC Breaker",
        "device_id": "bf97ff360135427784mm8v"
    }
]

breaker_health = {
    breaker["firebase_key"]: {
        "offline_count": 0,
        "last_success_at": None,
        "last_failure_at": None,
    }
    for breaker in BREAKERS
}

# =========================================================
# LOGGING
# =========================================================
TUYA_LOGGER.setLevel(logging.INFO)

# =========================================================
# CONNECT TO TUYA
# =========================================================
openapi = TuyaOpenAPI(API_ENDPOINT, ACCESS_ID, ACCESS_KEY)
openapi.connect()

# =========================================================
# HELPERS
# =========================================================
def normalize_status(result, online):
    raw = {}
    for item in result:
        raw[item["code"]] = item["value"]

    voltage_v = round(raw["cur_voltage"] / 10.0, 1) if "cur_voltage" in raw and raw["cur_voltage"] is not None else None
    current_a = round(raw["cur_current"] / 1000.0, 3) if "cur_current" in raw and raw["cur_current"] is not None else None
    power_w = round(raw["cur_power"] / 10.0, 1) if "cur_power" in raw and raw["cur_power"] is not None else None
    voltage_present = voltage_v is not None and voltage_v > 0

    return {
        "timestamp": int(time.time() * 1000),

        "switch": raw.get("switch"),
        "online": online,
        "voltage_present": voltage_present,
        "online_state": "online" if online else "offline",
        "relay_status": raw.get("relay_status"),

        "current_raw_mA": raw.get("cur_current"),
        "current_mA": raw.get("cur_current"),
        "current_A": current_a,

        "power_raw": raw.get("cur_power"),
        "power_W": power_w,

        "voltage_raw": raw.get("cur_voltage"),
        "voltage_V": voltage_v,

        "energy_raw": raw.get("add_ele"),
        "energy_kWh": round(raw["add_ele"] / 1000.0, 3) if "add_ele" in raw and raw["add_ele"] is not None else None,

        "fault": raw.get("fault"),
        "all_raw_codes": raw
    }

def build_device_payload(breaker_name, device_id, data):
    online = data.get("online") is True
    relay_on = data.get("switch") is True
    state = "on" if online and relay_on else "off"
    return {
        "type": "smart_breaker",
        "name": breaker_name,
        "tuya_device_id": device_id,
        "state": state,
        "status": {
            "online": online,
            "voltage_present": data.get("voltage_present") is True,
            "switch": data.get("switch") if online else False,
            "relay_status": data.get("relay_status") if online else "off",
            "fault": data.get("fault"),
            "lastSeen": data.get("timestamp"),
            "lastSeenMs": data.get("timestamp"),
        },
        "metering": {
            "voltage_V": data.get("voltage_V"),
            "current_A": data.get("current_A"),
            "current_mA": data.get("current_mA"),
            "power_W": data.get("power_W"),
            "energy_kWh": data.get("energy_kWh")
        },
        "raw": {
            "cur_voltage": data.get("voltage_raw"),
            "cur_current": data.get("current_raw_mA"),
            "cur_power": data.get("power_raw"),
            "add_ele": data.get("energy_raw")
        }
    }

def build_history_payload(data):
    return {
        "timestamp": data.get("timestamp"),
        "timestamp_ms": data.get("timestamp"),
        "switch": data.get("switch"),
        "online_state": data.get("online_state"),
        "relay_status": data.get("relay_status"),
        "fault": data.get("fault"),
        "voltage_V": data.get("voltage_V"),
        "current_A": data.get("current_A"),
        "current_mA": data.get("current_mA"),
        "power_W": data.get("power_W"),
        "energy_kWh": data.get("energy_kWh"),
        "raw": {
            "cur_voltage": data.get("voltage_raw"),
            "cur_current": data.get("current_raw_mA"),
            "cur_power": data.get("power_raw"),
            "add_ele": data.get("energy_raw")
        }
    }

def write_device_latest(firebase_key, breaker_name, device_id, data):
    payload = build_device_payload(breaker_name, device_id, data)
    url = f"{FIREBASE_DB_URL}/homes/{HOME_ID}/devices/{firebase_key}.json"
    r = requests.patch(url, json=payload, timeout=15)
    r.raise_for_status()

def write_device_history(firebase_key, data):
    payload = build_history_payload(data)
    ts = str(data["timestamp"])
    url = f"{FIREBASE_DB_URL}/homes/{HOME_ID}/history/{firebase_key}/{ts}.json"
    r = requests.put(url, json=payload, timeout=15)
    r.raise_for_status()

def write_device_offline(firebase_key, breaker_name, device_id, error):
    timestamp = int(time.time() * 1000)
    payload = {
        "type": "smart_breaker",
        "name": breaker_name,
        "tuya_device_id": device_id,
        "status": {
            "online": False,
            "voltage_present": False,
            "switch": False,
            "relay_status": "off",
            "lastSeenMs": timestamp,
            "lastSeen": timestamp,
            "last_error": str(error),
        },
        "metering": {
            "voltage_V": 0,
            "current_A": 0,
            "current_mA": 0,
            "power_W": 0,
        },
        "state": "off",
    }
    url = f"{FIREBASE_DB_URL}/homes/{HOME_ID}/devices/{firebase_key}.json"
    r = requests.patch(url, json=payload, timeout=15)
    r.raise_for_status()

def write_poll_error(firebase_key, error):
    timestamp = int(time.time() * 1000)
    payload = {
        "status": {
            "last_poll_error": str(error),
            "last_poll_error_at": timestamp,
        }
    }
    url = f"{FIREBASE_DB_URL}/homes/{HOME_ID}/devices/{firebase_key}.json"
    r = requests.patch(url, json=payload, timeout=15)
    r.raise_for_status()

def remember_success(firebase_key):
    state = breaker_health[firebase_key]
    state["offline_count"] = 0
    state["last_success_at"] = int(time.time() * 1000)

def remember_failure(firebase_key):
    state = breaker_health[firebase_key]
    state["offline_count"] += 1
    state["last_failure_at"] = int(time.time() * 1000)
    return state["offline_count"]

def fetch_breaker_status(device_id):
    response = openapi.get(f"/v1.0/devices/{device_id}/status")

    if not response.get("success"):
        raise Exception(f"Tuya API error for {device_id}: {response}")

    return response["result"]

def fetch_breaker_online(device_id):
    response = openapi.get(f"/v1.0/devices/{device_id}")
    if not response.get("success"):
        raise Exception(f"Tuya device read failed for {device_id}: {response}")
    result = response.get("result") or {}
    return result.get("online") is True

# =========================================================
# MAIN LOOP
# =========================================================
if __name__ == "__main__":
    while True:
        for breaker in BREAKERS:
            firebase_key = breaker["firebase_key"]
            breaker_name = breaker["name"]
            device_id = breaker["device_id"]

            try:
                online = fetch_breaker_online(device_id)
                status_result = fetch_breaker_status(device_id)
                parsed = normalize_status(status_result, online)

                if not online:
                    failures = remember_failure(firebase_key)
                    print(
                        f"\n===== {breaker_name} ({firebase_key}) offline check "
                        f"{failures}/{OFFLINE_AFTER_FAILURES}; tuya_online={online} ====="
                    )
                    if failures >= OFFLINE_AFTER_FAILURES:
                        write_device_offline(
                            firebase_key,
                            breaker_name,
                            device_id,
                            "Tuya reports device offline",
                        )
                    continue

                write_device_latest(firebase_key, breaker_name, device_id, parsed)
                write_device_history(firebase_key, parsed)
                remember_success(firebase_key)

                print(f"\n===== {breaker_name} ({firebase_key}) =====")
                print(json.dumps(parsed, indent=2))

            except Exception as e:
                print(f"ERROR {breaker_name} ({firebase_key}):", e)
                failures = remember_failure(firebase_key)
                if failures >= OFFLINE_AFTER_FAILURES:
                    try:
                        write_poll_error(firebase_key, e)
                    except Exception as write_error:
                        print(f"ERROR writing poll error for {firebase_key}:", write_error)

        time.sleep(POLL_INTERVAL_SECONDS)
