from __future__ import annotations

import os
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify

from local_state_store import get_path, home_snapshot, set_path
try:
    from aws_iot_live_publisher import build_live_payload
except Exception:
    build_live_payload = None


load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")
load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
load_dotenv()

PI_ID = os.environ.get("PI_ID", "pi_local_001")
PI_DEVICE_TOKEN = os.environ.get("PI_DEVICE_TOKEN", "")
HOME_ID = os.environ.get("HOME_ID", "")
KAHRABAIQ_API_URL = os.environ.get("KAHRABAIQ_API_URL", "").rstrip("/")
PI_AGENT_PORT = int(os.environ.get("PI_AGENT_PORT", "5010"))
AGENT_VERSION = os.environ.get("PI_AGENT_VERSION", "local-agent-1")
HEARTBEAT_INTERVAL_SECONDS = float(os.environ.get("PI_HEARTBEAT_INTERVAL_SECONDS", "45"))
LIVE_SYNC_INTERVAL_SECONDS = float(os.environ.get("PI_LIVE_SYNC_INTERVAL_SECONDS", "10"))
COMMAND_POLL_SECONDS = float(os.environ.get("PI_COMMAND_POLL_SECONDS", "3"))
KIOSK_TOKEN_REFRESH_MARGIN_SECONDS = float(os.environ.get("KIOSK_TOKEN_REFRESH_MARGIN_SECONDS", "240"))
ESP32_SETUP_URL = os.environ.get("ESP32_SETUP_URL", "http://192.168.4.1").rstrip("/")
ESP32_DEVICE_ID = os.environ.get("ESP32_DEVICE_ID", "esp32_01")
ESP32_DISCOVERY_CANDIDATES = [
    item.strip().rstrip("/")
    for item in os.environ.get(
        "ESP32_DISCOVERY_CANDIDATES",
        "http://kahrabaiq-esp32.local,http://192.168.4.1",
    ).split(",")
    if item.strip()
]
PI_SENSOR_BASE_URL = os.environ.get("PI_SENSOR_BASE_URL", "http://kahrabaiq-pi.local:5000").rstrip("/")
PI_LOCAL_BASE_URL = os.environ.get("PI_LOCAL_BASE_URL", "http://kahrabaiq-pi.local:5001").rstrip("/")

app = Flask(__name__)
_state_lock = threading.RLock()
_agent_state: dict[str, Any] = {
    "kiosk_token": None,
    "kiosk_expires_at_ms": 0,
    "last_error": None,
    "last_heartbeat_at_ms": None,
    "last_live_sync_at_ms": None,
    "last_command_poll_at_ms": None,
}


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def headers() -> dict[str, str]:
    return {"X-Pi-Id": PI_ID, "X-Device-Token": PI_DEVICE_TOKEN}


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return ""


def current_wifi_ssid() -> str:
    try:
        import subprocess

        result = subprocess.run(["iwgetid", "-r"], capture_output=True, text=True, timeout=2, check=False)
        return result.stdout.strip()
    except Exception:
        return ""


def api_request(method: str, path: str, **kwargs: Any) -> requests.Response:
    if not KAHRABAIQ_API_URL:
        raise RuntimeError("KAHRABAIQ_API_URL is required for Pi agent.")
    return requests.request(method, f"{KAHRABAIQ_API_URL}{path}", timeout=12, **kwargs)


def refresh_kiosk_token(force: bool = False) -> dict[str, Any]:
    with _state_lock:
        expires_at_ms = int(_agent_state.get("kiosk_expires_at_ms") or 0)
        if not force and _agent_state.get("kiosk_token") and expires_at_ms - now_ms() > KIOSK_TOKEN_REFRESH_MARGIN_SECONDS * 1000:
            return dict(_agent_state)

    response = api_request("POST", "/api/pi/kiosk-session", headers=headers())
    data = response.json()
    if not response.ok or data.get("success") is False:
        raise RuntimeError(data.get("detail") or data.get("message") or "Failed to create kiosk session.")
    with _state_lock:
        _agent_state.update(
            {
                "kiosk_token": data.get("kiosk_token"),
                "kiosk_expires_at_ms": int(data.get("expires_at_ms") or 0),
                "home_id": data.get("home_id"),
                "paired": data.get("paired"),
                "last_error": None,
            }
        )
        return dict(_agent_state)


def esp32_link() -> dict[str, Any]:
    value = get_path(f"homes/{HOME_ID or 'home_001'}/devices/{ESP32_DEVICE_ID}/link", {})
    return value if isinstance(value, dict) else {}


def send_heartbeat() -> None:
    payload = {
        "status": "online",
        "agent_version": AGENT_VERSION,
        "local_ip": local_ip(),
        "wifi_ssid": current_wifi_ssid(),
        "esp32": esp32_link(),
    }
    response = api_request("POST", f"/api/pi/{PI_ID}/heartbeat", headers=headers(), json=payload)
    if not response.ok:
        raise RuntimeError(response.text)
    with _state_lock:
        _agent_state["last_heartbeat_at_ms"] = now_ms()


def build_live_state() -> dict[str, Any]:
    home_id = HOME_ID or str(_agent_state.get("home_id") or "home_001")
    if build_live_payload is not None:
        payload = build_live_payload()
        return {
            "home_id": home_id,
            "dashboard": payload.get("dashboard") if isinstance(payload.get("dashboard"), dict) else {},
            "room": payload.get("room") if isinstance(payload.get("room"), dict) else {},
            "devices": payload.get("devices") if isinstance(payload.get("devices"), dict) else {},
            "energy": payload.get("energy") if isinstance(payload.get("energy"), dict) else {},
            "commands": payload.get("commands") if isinstance(payload.get("commands"), dict) else {},
            "alerts": list((payload.get("alerts") or {}).get("active", {}).values())
            if isinstance(payload.get("alerts"), dict)
            else payload.get("alerts", []),
            "occupancy": payload.get("occupancy") if isinstance(payload.get("occupancy"), dict) else {},
            "safety": payload.get("safety") if isinstance(payload.get("safety"), dict) else {},
            "updated_at_ms": payload.get("timestamp_ms") or payload.get("timestampMs") or now_ms(),
        }
    home = home_snapshot(home_id)
    devices = home.get("devices") if isinstance(home.get("devices"), dict) else {}
    esp32 = devices.get(ESP32_DEVICE_ID) if isinstance(devices.get(ESP32_DEVICE_ID), dict) else {}
    return {
        "home_id": home_id,
        "dashboard": home.get("dashboard") if isinstance(home.get("dashboard"), dict) else {},
        "room": esp32.get("sensors") if isinstance(esp32.get("sensors"), dict) else {},
        "devices": devices,
        "alerts": list((home.get("alerts") or {}).get("active", {}).values()) if isinstance(home.get("alerts"), dict) else [],
        "occupancy": (home.get("occupancy") or {}).get("room1", {}) if isinstance(home.get("occupancy"), dict) else {},
        "safety": home.get("safety") if isinstance(home.get("safety"), dict) else {},
        "updated_at_ms": now_ms(),
    }


def sync_live_state() -> None:
    payload = build_live_state()
    if not payload.get("home_id"):
        return
    response = api_request("POST", f"/api/pi/{PI_ID}/sensor-state", headers=headers(), json=payload)
    if not response.ok:
        raise RuntimeError(response.text)
    with _state_lock:
        _agent_state["last_live_sync_at_ms"] = now_ms()


def normalize_url(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if text and not text.startswith(("http://", "https://")):
        text = f"http://{text}"
    return text


def esp32_status(base_url: str, timeout: float = 3.0) -> dict[str, Any]:
    base = normalize_url(base_url)
    response = requests.get(f"{base}/status", timeout=timeout)
    data = response.json()
    if not response.ok:
        raise RuntimeError(data.get("message") or response.text)
    return {
        "device_id": str(data.get("device_id") or ESP32_DEVICE_ID),
        "ip": base.replace("http://", "").replace("https://", "").split(":")[0],
        "base_url": base,
        "status": data,
        "last_seen_at_ms": now_ms(),
        "last_seen_at_iso": iso_now(),
    }


def save_esp32_link(record: dict[str, Any]) -> None:
    home_id = HOME_ID or str(_agent_state.get("home_id") or "home_001")
    set_path(f"homes/{home_id}/devices/{record.get('device_id') or ESP32_DEVICE_ID}/link", record)
    api_request("POST", f"/api/pi/{PI_ID}/esp32/link", headers=headers(), json=record)


def discover_esp32() -> dict[str, Any]:
    candidates = []
    linked = esp32_link()
    if linked.get("base_url"):
        candidates.append(str(linked["base_url"]))
    candidates.extend(ESP32_DISCOVERY_CANDIDATES)
    seen = set()
    for candidate in candidates:
        base = normalize_url(candidate)
        if not base or base in seen:
            continue
        seen.add(base)
        try:
            record = esp32_status(base)
            save_esp32_link(record)
            return record
        except Exception:
            continue
    raise RuntimeError("ESP32 was not found on this network.")


def provision_esp32(payload: dict[str, Any]) -> dict[str, Any]:
    setup_url = normalize_url(str(payload.get("setup_url") or ESP32_SETUP_URL))
    ssid = str(payload.get("ssid") or "").strip()
    password = str(payload.get("password") or "")
    if not ssid or not password:
        raise RuntimeError("ssid and password are required.")
    body = {
        "ssid": ssid,
        "password": password,
        "pi_base_url": PI_LOCAL_BASE_URL,
        "pi_sensor_url": f"{PI_SENSOR_BASE_URL}/api/sensors/room1",
        "home_id": HOME_ID or str(_agent_state.get("home_id") or ""),
        "pi_id": PI_ID,
        "device_id": str(payload.get("device_id") or ESP32_DEVICE_ID),
        "device_key": str(payload.get("device_key") or os.environ.get("ESP32_DEVICE_KEY", "")),
    }
    response = requests.post(f"{setup_url}/provision", json=body, timeout=15)
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
    if not response.ok:
        raise RuntimeError(data.get("message") or response.text)
    return {"setup_url": setup_url, "response": data}


def reset_esp32(payload: dict[str, Any]) -> dict[str, Any]:
    base = normalize_url(str(payload.get("base_url") or esp32_link().get("base_url") or ESP32_SETUP_URL))
    response = requests.post(f"{base}/reset", timeout=8)
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
    if not response.ok:
        raise RuntimeError(data.get("message") or response.text)
    return {"base_url": base, "response": data}


def execute_command(command: dict[str, Any]) -> dict[str, Any]:
    name = str(command.get("command") or "")
    payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
    if name == "provision_esp32":
        return provision_esp32(payload)
    if name == "discover_esp32":
        return {"esp32": discover_esp32()}
    if name == "reset_esp32":
        return reset_esp32(payload)
    raise RuntimeError(f"Unsupported command: {name}")


def poll_commands() -> None:
    response = api_request("GET", f"/api/pi/{PI_ID}/commands", headers=headers())
    data = response.json()
    if not response.ok:
        raise RuntimeError(response.text)
    for command in data.get("commands") or []:
        command_id = command.get("command_id") or command.get("id")
        if not command_id:
            continue
        try:
            result = execute_command(command)
            complete = {"success": True, "result": result}
        except Exception as error:
            complete = {"success": False, "message": str(error)}
        api_request("POST", f"/api/pi/{PI_ID}/commands/{command_id}/complete", headers=headers(), json=complete)
    with _state_lock:
        _agent_state["last_command_poll_at_ms"] = now_ms()


def loop_worker(name: str, interval: float, fn) -> None:
    while True:
        started = time.time()
        try:
            fn()
            with _state_lock:
                _agent_state["last_error"] = None
        except Exception as error:
            with _state_lock:
                _agent_state["last_error"] = f"{name}: {error}"
        elapsed = time.time() - started
        time.sleep(max(1.0, interval - elapsed))


@app.get("/api/kiosk/session")
def kiosk_session() -> Any:
    try:
        session = refresh_kiosk_token()
        return jsonify(
            {
                "success": True,
                "pi_id": PI_ID,
                "home_id": session.get("home_id"),
                "paired": session.get("paired"),
                "kiosk_token": session.get("kiosk_token"),
                "expires_at_ms": session.get("kiosk_expires_at_ms"),
            }
        )
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 503


@app.get("/api/agent/status")
def agent_status() -> Any:
    with _state_lock:
        return jsonify({"success": True, "pi_id": PI_ID, "state": dict(_agent_state)})


def start_background_threads() -> None:
    refresh_kiosk_token(force=True)
    workers = [
        ("kiosk-token", max(60, KIOSK_TOKEN_REFRESH_MARGIN_SECONDS / 2), lambda: refresh_kiosk_token(force=False)),
        ("heartbeat", HEARTBEAT_INTERVAL_SECONDS, send_heartbeat),
        ("live-sync", LIVE_SYNC_INTERVAL_SECONDS, sync_live_state),
        ("commands", COMMAND_POLL_SECONDS, poll_commands),
    ]
    for name, interval, fn in workers:
        thread = threading.Thread(target=loop_worker, args=(name, interval, fn), daemon=True, name=f"kahrabaiq-{name}")
        thread.start()


if __name__ == "__main__":
    start_background_threads()
    app.run(host="127.0.0.1", port=PI_AGENT_PORT)
