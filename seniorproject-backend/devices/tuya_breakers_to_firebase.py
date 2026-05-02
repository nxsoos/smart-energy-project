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
def normalize_status(result):
    raw = {}
    for item in result:
        raw[item["code"]] = item["value"]

    return {
        "timestamp": int(time.time() * 1000),

        "switch": raw.get("switch"),
        "online_state": raw.get("online_state"),
        "relay_status": raw.get("relay_status"),

        "current_raw_mA": raw.get("cur_current"),
        "current_mA": raw.get("cur_current"),
        "current_A": round(raw["cur_current"] / 1000.0, 3) if "cur_current" in raw and raw["cur_current"] is not None else None,

        "power_raw": raw.get("cur_power"),
        "power_W": round(raw["cur_power"] / 10.0, 1) if "cur_power" in raw and raw["cur_power"] is not None else None,

        "voltage_raw": raw.get("cur_voltage"),
        "voltage_V": round(raw["cur_voltage"] / 10.0, 1) if "cur_voltage" in raw and raw["cur_voltage"] is not None else None,

        "energy_raw": raw.get("add_ele"),
        "energy_kWh": round(raw["add_ele"] / 1000.0, 3) if "add_ele" in raw and raw["add_ele"] is not None else None,

        "fault": raw.get("fault"),
        "all_raw_codes": raw
    }

def build_device_payload(breaker_name, device_id, data):
    return {
        "type": "smart_breaker",
        "name": breaker_name,
        "tuya_device_id": device_id,
        "status": {
            "online": data.get("online_state") == "online",
            "switch": data.get("switch"),
            "relay_status": data.get("relay_status"),
            "fault": data.get("fault"),
            "lastSeen": data.get("timestamp")
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
    r = requests.put(url, json=payload, timeout=15)
    r.raise_for_status()

def write_device_history(firebase_key, data):
    payload = build_history_payload(data)
    ts = str(data["timestamp"])
    url = f"{FIREBASE_DB_URL}/homes/{HOME_ID}/history/{firebase_key}/{ts}.json"
    r = requests.put(url, json=payload, timeout=15)
    r.raise_for_status()

def fetch_breaker_status(device_id):
    response = openapi.get(f"/v1.0/devices/{device_id}/status")

    if not response.get("success"):
        raise Exception(f"Tuya API error for {device_id}: {response}")

    return response["result"]

# =========================================================
# MAIN LOOP
# =========================================================
if __name__ == "__main__":
    while True:
        try:
            for breaker in BREAKERS:
                firebase_key = breaker["firebase_key"]
                breaker_name = breaker["name"]
                device_id = breaker["device_id"]

                status_result = fetch_breaker_status(device_id)
                parsed = normalize_status(status_result)

                write_device_latest(firebase_key, breaker_name, device_id, parsed)
                write_device_history(firebase_key, parsed)

                print(f"\n===== {breaker_name} ({firebase_key}) =====")
                print(json.dumps(parsed, indent=2))

        except Exception as e:
            print("ERROR:", e)

        time.sleep(10)
