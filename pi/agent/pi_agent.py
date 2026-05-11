from __future__ import annotations

import os
import hashlib
import hmac
import secrets
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request

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
LIVE_SYNC_INTERVAL_SECONDS = float(os.environ.get("PI_LIVE_SYNC_INTERVAL_SECONDS", "5"))
COMMAND_POLL_SECONDS = float(os.environ.get("PI_COMMAND_POLL_SECONDS", "3"))
KIOSK_TOKEN_REFRESH_MARGIN_SECONDS = float(os.environ.get("KIOSK_TOKEN_REFRESH_MARGIN_SECONDS", "240"))
PI_CLOUD_ADMIN_UNLOCK_ENABLED = os.environ.get("PI_CLOUD_ADMIN_UNLOCK_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
COGNITO_REGION = os.environ.get("COGNITO_REGION") or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "")
COGNITO_APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")
ESP32_SETUP_URL = os.environ.get("ESP32_SETUP_URL", "").rstrip("/")
ESP32_DEVICE_ID = os.environ.get("ESP32_DEVICE_ID", "esp32_01")
ESP32_DISCOVERY_CANDIDATES = [
    item.strip().rstrip("/")
    for item in os.environ.get(
        "ESP32_DISCOVERY_CANDIDATES",
        "http://kahrabaiq-esp32.local",
    ).split(",")
    if item.strip()
]
PI_SENSOR_PORT = int(os.environ.get("PI_SENSOR_PORT", "5000"))
PI_SENSOR_BASE_URL = os.environ.get("PI_SENSOR_BASE_URL", "").rstrip("/")
PI_LOCAL_BASE_URL = os.environ.get("PI_LOCAL_BASE_URL", "").rstrip("/")
PROVISIONING_MARKER_PATH = Path(os.environ.get("PROVISIONING_MARKER_PATH", "/var/lib/kahrabaiq/provisioned.json"))
KIOSK_ADMIN_USERNAME = os.environ.get("KIOSK_ADMIN_USERNAME", "admin")
KIOSK_ADMIN_PASSWORD = os.environ.get("KIOSK_ADMIN_PASSWORD", "")
KIOSK_ADMIN_PASSWORD_HASH = os.environ.get("KIOSK_ADMIN_PASSWORD_HASH", "")
KIOSK_ADMIN_PIN = os.environ.get("KIOSK_ADMIN_PIN", "")
KIOSK_ADMIN_PIN_HASH = os.environ.get("KIOSK_ADMIN_PIN_HASH", "")
KIOSK_ADMIN_SESSION_SECONDS = int(os.environ.get("KIOSK_ADMIN_SESSION_SECONDS", "1800"))

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
_admin_sessions: dict[str, int] = {}


@app.after_request
def add_local_admin_cors(response: Response) -> Response:
    if request.path.startswith("/api/admin/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Admin-Token"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


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


def url_with_scheme(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if text and not text.startswith(("http://", "https://")):
        text = f"http://{text}"
    return text


def pi_local_base_url(ip: str | None = None) -> str:
    if PI_LOCAL_BASE_URL:
        return url_with_scheme(PI_LOCAL_BASE_URL)
    current_ip = ip or local_ip()
    if not current_ip:
        raise RuntimeError("Pi local IP is unavailable.")
    return f"http://{current_ip}:{PI_AGENT_PORT}"


def pi_sensor_base_url(ip: str | None = None) -> str:
    if PI_SENSOR_BASE_URL:
        return url_with_scheme(PI_SENSOR_BASE_URL)
    current_ip = ip or local_ip()
    if not current_ip:
        raise RuntimeError("Pi local IP is unavailable.")
    return f"http://{current_ip}:{PI_SENSOR_PORT}"


def pi_sensor_endpoint(ip: str | None = None) -> str:
    return f"{pi_sensor_base_url(ip)}/api/sensors/room1"


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def secret_matches(provided: str, plain: str, hashed: str) -> bool:
    if hashed and hmac.compare_digest(hash_secret(provided), hashed):
        return True
    return bool(plain) and hmac.compare_digest(provided, plain)


def recovery_pin_ok(pin: str) -> bool:
    return bool(pin) and secret_matches(pin, KIOSK_ADMIN_PIN, KIOSK_ADMIN_PIN_HASH)


def local_admin_password_ok(username: str, password: str) -> bool:
    return bool(username and password) and username == KIOSK_ADMIN_USERNAME and secret_matches(password, KIOSK_ADMIN_PASSWORD, KIOSK_ADMIN_PASSWORD_HASH)


def cognito_password_login(email: str, password: str) -> str:
    if not COGNITO_REGION or not COGNITO_APP_CLIENT_ID:
        raise RuntimeError("Cognito app client is not configured for Pi cloud admin unlock.")
    try:
        import boto3
    except Exception as error:
        raise RuntimeError("boto3 is required for Pi cloud admin unlock.") from error
    client = boto3.client("cognito-idp", region_name=COGNITO_REGION)
    response = client.initiate_auth(
        ClientId=COGNITO_APP_CLIENT_ID,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    token = str(response.get("AuthenticationResult", {}).get("IdToken") or "")
    if not token:
        raise RuntimeError("Cognito did not return an ID token.")
    return token


def authorize_platform_admin(id_token: str) -> dict[str, Any]:
    response = api_request("GET", "/api/pi/admin-authorize", headers={"Authorization": f"Bearer {id_token}"})
    data = response.json()
    if not response.ok or data.get("success") is False or data.get("can_unlock_pi") is not True:
        raise RuntimeError(data.get("detail") or data.get("message") or "Platform admin authorization failed.")
    return data


def cloud_admin_password_ok(email: str, password: str) -> dict[str, Any]:
    if not PI_CLOUD_ADMIN_UNLOCK_ENABLED:
        raise RuntimeError("Pi cloud admin unlock is disabled.")
    if not email or not password:
        raise RuntimeError("Email and password are required for platform admin unlock.")
    id_token = cognito_password_login(email, password)
    return authorize_platform_admin(id_token)


def create_admin_session() -> dict[str, Any]:
    token = secrets.token_urlsafe(32)
    expires_at_ms = now_ms() + (KIOSK_ADMIN_SESSION_SECONDS * 1000)
    with _state_lock:
        _admin_sessions[token] = expires_at_ms
    return {"token": token, "expires_at_ms": expires_at_ms}


def admin_token() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.removeprefix("Bearer ").strip()
    return request.headers.get("X-Admin-Token", "").strip()


def require_admin() -> tuple[bool, str]:
    token = admin_token()
    if not token:
        return False, "Missing admin token."
    with _state_lock:
        expires_at_ms = int(_admin_sessions.get(token) or 0)
        if expires_at_ms <= now_ms():
            _admin_sessions.pop(token, None)
            return False, "Admin session expired."
    return True, token


def run_admin_command(args: list[str], timeout: int = 20) -> dict[str, Any]:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    return {
        "command": args,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "success": result.returncode == 0,
    }


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
    ip = local_ip()
    payload = {
        "status": "online",
        "agent_version": AGENT_VERSION,
        "local_ip": ip,
        "local_base_url": pi_local_base_url(ip),
        "sensor_base_url": pi_sensor_base_url(ip),
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
            "notifications": [],
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
        "notifications": [],
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


def kiosk_dashboard_data() -> dict[str, Any]:
    session = refresh_kiosk_token()
    token = session.get("kiosk_token")
    if not token:
        raise RuntimeError("Kiosk token is unavailable.")
    response = api_request(
        "GET",
        "/api/kiosk/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = response.json()
    if not response.ok or data.get("success") is False:
        raise RuntimeError(data.get("detail") or data.get("message") or response.text)
    return data


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
    if not setup_url:
        raise RuntimeError("ESP32 setup URL is unavailable. Use first-boot provisioning or provide setup_url explicitly.")
    ssid = str(payload.get("ssid") or "").strip()
    password = str(payload.get("password") or "")
    if not ssid or not password:
        raise RuntimeError("ssid and password are required.")
    body = {
        "ssid": ssid,
        "password": password,
        "pi_base_url": pi_local_base_url(),
        "pi_sensor_url": pi_sensor_endpoint(),
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
    if not base:
        raise RuntimeError("ESP32 base URL is unavailable. Discover the ESP32 first or provide base_url explicitly.")
    response = requests.post(f"{base}/reset", timeout=8)
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
    if not response.ok:
        raise RuntimeError(data.get("message") or response.text)
    return {"base_url": base, "response": data}


def reset_pairing(payload: dict[str, Any]) -> dict[str, Any]:
    marker_deleted = False
    if PROVISIONING_MARKER_PATH.exists():
        PROVISIONING_MARKER_PATH.unlink()
        marker_deleted = True
    with _state_lock:
        _agent_state["home_id"] = None
        _agent_state["kiosk_token"] = None
        _agent_state["kiosk_expires_at_ms"] = 0
    set_path("pi/pairing", {"status": "unpaired", "reason": payload.get("reason") or "reset_pairing", "updated_at_ms": now_ms()})

    esp32_reset: dict[str, Any] | None = None
    try:
        esp32_reset = reset_esp32({})
    except Exception as error:
        esp32_reset = {"success": False, "message": str(error)}

    service_commands = [
        run_admin_command(["sudo", "-n", "/usr/bin/systemctl", "stop", "kahrabaiq-kiosk-browser.service"], timeout=20),
        run_admin_command(["sudo", "-n", "/usr/bin/systemctl", "start", "kahrabaiq-provisioning.service"], timeout=20),
        run_admin_command(["sudo", "-n", "/usr/bin/systemctl", "start", "kahrabaiq-setup-screen.service"], timeout=20),
    ]
    return {
        "marker_deleted": marker_deleted,
        "marker_path": str(PROVISIONING_MARKER_PATH),
        "esp32_reset": esp32_reset,
        "services": service_commands,
        "message": "Pi returned to pairing mode.",
    }


def execute_command(command: dict[str, Any]) -> dict[str, Any]:
    name = str(command.get("command") or "")
    payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
    if name == "provision_esp32":
        return provision_esp32(payload)
    if name == "discover_esp32":
        return {"esp32": discover_esp32()}
    if name == "reset_esp32":
        return reset_esp32(payload)
    if name == "reset_pairing":
        return reset_pairing(payload)
    raise RuntimeError(f"Unsupported command: {name}")


KIOSK_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KahrabaIQ Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #04061b;
      --panel: #15182b;
      --panel-2: #1c2238;
      --text: #f7f8ff;
      --muted: #9da3b8;
      --cyan: #11d9ff;
      --green: #12c48b;
      --yellow: #ffb020;
      --red: #ff5c7a;
      --border: rgba(17, 217, 255, 0.28);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: radial-gradient(circle at 50% -20%, #1b2a57 0, var(--bg) 42%);
      color: var(--text);
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .shell {
      width: min(1180px, calc(100vw - 40px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 24px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 16px;
      min-width: 0;
    }

    .brand-mark {
      width: 62px;
      height: 62px;
      flex: 0 0 auto;
      filter: drop-shadow(0 0 22px rgba(17, 217, 255, 0.24));
    }

    .brand-copy {
      min-width: 0;
    }

    h1 {
      margin: 0;
      font-size: clamp(30px, 4vw, 54px);
      line-height: 1;
    }

    .sub {
      margin-top: 10px;
      color: var(--muted);
      font-size: 16px;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 0 14px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(17, 217, 255, 0.08);
      color: var(--cyan);
      font-weight: 700;
      white-space: nowrap;
    }

    .dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: var(--green);
      box-shadow: 0 0 16px var(--green);
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 16px;
    }

    .card {
      background: linear-gradient(145deg, rgba(28, 34, 56, 0.98), rgba(14, 18, 34, 0.98));
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 22px;
      box-shadow: 0 18px 50px rgba(0, 0, 0, 0.22);
    }

    .hero { grid-column: span 7; }
    .room { grid-column: span 5; }
    .wide { grid-column: span 12; }

    .metric-row {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-top: 18px;
    }

    .metric {
      min-height: 108px;
      border-radius: 14px;
      background: rgba(4, 6, 27, 0.5);
      padding: 16px;
    }

    .label {
      color: var(--muted);
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 12px;
    }

    .value {
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: clamp(28px, 4vw, 48px);
      font-weight: 900;
      letter-spacing: 0;
    }

    .unit {
      margin-left: 6px;
      color: var(--muted);
      font-size: 20px;
    }

    .small-value {
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 24px;
      font-weight: 800;
    }

    .devices {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }

    .device {
      border-radius: 14px;
      background: rgba(4, 6, 27, 0.5);
      padding: 18px;
      min-height: 160px;
    }

    .device-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 18px;
    }

    .device-name {
      font-size: 20px;
      font-weight: 900;
    }

    .state {
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(18, 196, 139, 0.14);
      color: var(--green);
      font-weight: 800;
      text-transform: capitalize;
    }

    .state.offline,
    .state.failed {
      background: rgba(255, 92, 122, 0.14);
      color: var(--red);
    }

    .two-col {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }

    .warn {
      color: var(--yellow);
    }

    .error {
      color: var(--red);
    }

    .overlay {
      position: fixed;
      inset: 0;
      background: rgba(4, 6, 27, 0.82);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      z-index: 20;
    }

    .overlay.visible {
      display: flex;
    }

    .modal {
      width: min(520px, 100%);
      background: #111827;
      border: 1px solid rgba(248, 113, 113, 0.5);
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 30px 80px rgba(0, 0, 0, 0.45);
      text-align: center;
    }

    .modal h2 {
      margin: 0 0 12px;
      color: #fecaca;
    }

    .modal p {
      margin: 0 0 18px;
      line-height: 1.5;
      color: #e5e7eb;
    }

    .modal button {
      border: none;
      border-radius: 999px;
      padding: 12px 18px;
      background: #dc2626;
      color: white;
      font-weight: 700;
    }

    .admin-hotspot {
      position: fixed;
      top: 0;
      right: 0;
      width: 96px;
      height: 96px;
      z-index: 10;
    }

    .admin-panel {
      width: min(620px, 100%);
      background: #0f172a;
      border: 1px solid rgba(17, 217, 255, 0.42);
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 30px 80px rgba(0, 0, 0, 0.45);
    }

    .admin-panel h2 { margin: 0 0 10px; }
    .admin-panel p { color: var(--muted); line-height: 1.5; }
    .admin-panel input {
      width: 100%;
      margin: 8px 0 12px;
      border: 1px solid rgba(157, 163, 184, 0.35);
      border-radius: 12px;
      padding: 12px 14px;
      background: #020617;
      color: var(--text);
      font-size: 16px;
    }

    .admin-actions {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin-top: 14px;
    }

    .admin-panel button {
      border: none;
      border-radius: 999px;
      padding: 12px 16px;
      background: rgba(17, 217, 255, 0.16);
      color: var(--text);
      font-weight: 800;
    }

    .admin-panel button.primary { background: var(--cyan); color: #001018; }
    .admin-panel button.danger { background: var(--red); color: white; }
    .admin-log { margin-top: 14px; color: var(--muted); white-space: pre-wrap; font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }

    @media (max-width: 820px) {
      header { align-items: flex-start; flex-direction: column; }
      .brand-mark { width: 52px; height: 52px; }
      .hero, .room { grid-column: span 12; }
      .metric-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="admin-hotspot" id="adminHotspot" aria-label="Admin unlock area"></div>
  <div class="overlay" id="alertOverlay">
    <div class="modal">
      <h2>Smoke/Gas Detected</h2>
      <p id="alertOverlayMessage">Smoke or gas was detected. Check the area immediately.</p>
      <button type="button" id="alertOverlayButton">I understand</button>
    </div>
  </div>
  <div class="overlay" id="adminOverlay">
    <div class="admin-panel">
      <h2>Admin Access</h2>
      <p id="adminCopy">Use platform admin credentials to unlock Pi maintenance. Use local recovery PIN only if cloud unlock is unavailable.</p>
      <div id="adminLogin">
        <input id="adminEmail" placeholder="Platform admin email" autocomplete="username">
        <input id="adminPassword" placeholder="Password" type="password" autocomplete="current-password">
        <input id="adminPin" placeholder="Recovery PIN optional" type="password" inputmode="numeric">
        <button class="primary" type="button" id="adminLoginButton">Unlock</button>
      </div>
      <div id="adminControls" style="display:none">
        <div class="admin-actions">
          <button class="primary" type="button" id="lockDashboardButton">Lock Dashboard</button>
          <button type="button" id="refreshAdminStatusButton">Refresh Status</button>
          <button type="button" id="restartDashboardButton">Restart Dashboard</button>
          <button type="button" id="exitKioskButton">Exit Kiosk To Desktop</button>
          <button type="button" id="returnKioskButton">Return To Kiosk</button>
          <button class="danger" type="button" id="maintenanceButton">Enter Maintenance</button>
        </div>
        <div class="admin-log" id="adminLog">Admin mode unlocked.</div>
      </div>
    </div>
  </div>
  <main class="shell">
    <header>
      <div class="brand">
        <svg class="brand-mark" viewBox="0 0 64 64" role="img" aria-label="KahrabaIQ logo">
          <defs>
            <linearGradient id="brandBolt" x1="10" y1="8" x2="54" y2="58" gradientUnits="userSpaceOnUse">
              <stop stop-color="#11d9ff" />
              <stop offset="1" stop-color="#12c48b" />
            </linearGradient>
          </defs>
          <rect x="5" y="5" width="54" height="54" rx="17" fill="#071024" stroke="rgba(17,217,255,.42)" stroke-width="2" />
          <path d="M35.4 8.8 16.8 35.1h13.4l-3.5 20.1 20.5-28H33.9l1.5-18.4Z" fill="url(#brandBolt)" />
          <path d="M22.5 39.7c4.9 5.3 13.5 5.7 18.9.8" fill="none" stroke="#f7f8ff" stroke-opacity=".82" stroke-width="3" stroke-linecap="round" />
        </svg>
        <div class="brand-copy">
          <h1>KahrabaIQ</h1>
          <div class="sub" id="subtitle">Loading dashboard...</div>
        </div>
      </div>
      <div class="pill"><span class="dot"></span><span id="statusText">Connecting</span></div>
    </header>

    <section class="grid">
      <article class="card hero">
        <div class="label">Live Power</div>
        <div><span class="value" id="power">--</span><span class="unit">W</span></div>
        <div class="metric-row">
          <div class="metric">
            <div class="label">Today</div>
            <div class="small-value" id="energyToday">-- kWh</div>
          </div>
          <div class="metric">
            <div class="label">Cost</div>
            <div class="small-value" id="costToday">-- BD</div>
          </div>
          <div class="metric">
            <div class="label">Breakers</div>
            <div class="small-value" id="breakerCount">--</div>
          </div>
        </div>
      </article>

      <article class="card room">
        <div class="label">Room Sensors</div>
        <div class="two-col">
          <div class="metric">
            <div class="label">Temperature</div>
            <div class="small-value" id="temperature">-- C</div>
          </div>
          <div class="metric">
            <div class="label">Humidity</div>
            <div class="small-value" id="humidity">-- %</div>
          </div>
          <div class="metric">
            <div class="label">Motion</div>
            <div class="small-value" id="motion">--</div>
          </div>
          <div class="metric">
            <div class="label">Smoke/Gas</div>
            <div class="small-value" id="smoke">--</div>
          </div>
        </div>
      </article>

      <article class="card wide">
        <div class="label">Devices</div>
        <div class="devices" id="devices"></div>
      </article>

      <article class="card wide">
        <div class="label">Alerts & Notes</div>
        <div id="alerts">No active alerts.</div>
      </article>
    </section>
  </main>

  <script>
    const fmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
    let overlayDismissedForAlertId = null;
    let adminToken = sessionStorage.getItem("kahrabaiqAdminToken") || "";
    let adminPressTimer = null;

    function text(id, value) {
      document.getElementById(id).textContent = value;
    }

    function number(value, fallback = 0) {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : fallback;
    }

    function deviceState(device) {
      if (!device.online) return "offline";
      return device.display_state || device.state || "unknown";
    }

    function render(data) {
      const dashboard = data.dashboard || {};
      const energy = dashboard.energy || {};
      const room = dashboard.room || {};
      const devices = dashboard.devices || {};
      const deviceList = Object.values(devices).filter((device) => {
        const type = String(device.type || "");
        return type !== "esp32_sensor" && !String(device.id || "").startsWith("esp32");
      });
      const breakers = deviceList.filter((device) => String(device.type || "").includes("breaker"));
      const activeBreakers = breakers.filter((device) => deviceState(device) === "on").length;

      text("subtitle", `${data.home_id || "home"} - ${dashboard.updated_at_iso || "waiting for live state"}`);
      text("statusText", data.paired ? "Live" : "Unpaired");
      text("power", fmt.format(number(energy.currentPowerW ?? energy.powerW)));
      text("energyToday", `${fmt.format(number(energy.energyTodayKwh ?? energy.totalEnergyKwh))} kWh`);
      text("costToday", `${number(energy.costToday).toFixed(3)} BD`);
      text("breakerCount", `${activeBreakers}/${breakers.length || 0}`);
      text("temperature", room.online === false ? "Offline" : `${fmt.format(number(room.temperature))} C`);
      text("humidity", room.online === false ? "Offline" : `${fmt.format(number(room.humidity))} %`);
      text("motion", room.motion_text || (number(room.motion) ? "Motion" : "Clear"));
      text("smoke", room.smoke_text || (number(room.smoke) ? "Detected" : "Clear"));

      const devicesNode = document.getElementById("devices");
      devicesNode.innerHTML = "";
      if (!deviceList.length) {
        devicesNode.textContent = "No devices are available.";
      } else {
        for (const device of deviceList) {
          const state = deviceState(device);
          const card = document.createElement("div");
          card.className = "device";
          card.innerHTML = `
            <div class="device-head">
              <div>
                <div class="device-name">${device.name || device.id || "Device"}</div>
                <div class="label">${device.branch || device.control_method || ""}</div>
              </div>
              <div class="state ${state === "offline" ? "offline" : ""}">${state}</div>
            </div>
            <div class="two-col">
              <div><div class="label">Power</div><div class="small-value">${fmt.format(number(device.power_W))} W</div></div>
              <div><div class="label">Energy</div><div class="small-value">${fmt.format(number(device.energy_kWh))} kWh</div></div>
              <div><div class="label">Voltage</div><div class="small-value">${fmt.format(number(device.voltage_V))} V</div></div>
              <div><div class="label">Current</div><div class="small-value">${fmt.format(number(device.current_A))} A</div></div>
            </div>
          `;
          devicesNode.appendChild(card);
        }
      }

      const alerts = dashboard.alerts || [];
      const aiNotifications = dashboard.ai_notifications || [];
      const ai = dashboard.ai || {};
      const notes = [];
      if (ai.ai_status_summary || ai.summary) {
        notes.push(`<span class="warn">AI: ${ai.ai_status_summary || ai.summary}</span>`);
      }
      if (room.stale || room.online === false) {
        notes.push('<span class="warn">Room sensors are offline or stale.</span>');
      }
      for (const device of deviceList) {
        if (device.last_command_status === "failed" || device.last_command_message) {
          notes.push(`<span class="warn">${device.name || device.id}: ${device.last_command_message || "Last command failed."}</span>`);
        }
      }
      for (const alert of alerts) {
        notes.push(`<span class="error">${alert.title || alert.message || "Active alert"}</span>`);
      }
      for (const notification of aiNotifications.slice(0, 3)) {
        const severity = String(notification.severity || "info").toLowerCase();
        const klass = severity === "critical" || severity === "high" ? "error" : "warn";
        notes.push(`<span class="${klass}">AI: ${notification.title || notification.message || "Notification"}</span>`);
      }
      document.getElementById("alerts").innerHTML = notes.length ? notes.join("<br>") : "No active alerts.";

      const overlay = document.getElementById("alertOverlay");
      const overlayMessage = document.getElementById("alertOverlayMessage");
      const criticalAlert = [...alerts, ...aiNotifications].find((alert) => {
        const severity = String(alert.severity || alert.level || "").toLowerCase();
        const alertType = String(alert.alert_type || alert.type || alert.category || "").toLowerCase();
        const message = String(alert.message || alert.title || "").toLowerCase();
        return severity === "critical" || alertType.includes("smoke") || alertType.includes("gas") || message.includes("smoke") || message.includes("gas");
      });
      if (!criticalAlert) {
        overlay.classList.remove("visible");
        overlayDismissedForAlertId = null;
      } else {
        const alertId = String(criticalAlert.alert_id || criticalAlert.id || "critical_alert");
        overlayMessage.textContent = criticalAlert.message || criticalAlert.title || "Smoke or gas was detected. Check the area immediately.";
        if (overlayDismissedForAlertId !== alertId) {
          overlay.classList.add("visible");
        }
        document.getElementById("alertOverlayButton").onclick = () => {
          overlayDismissedForAlertId = alertId;
          overlay.classList.remove("visible");
        };
      }
    }

    async function refresh() {
      try {
        const response = await fetch("/api/kiosk/dashboard-data", { cache: "no-store" });
        const data = await response.json();
        if (!response.ok || data.success === false) {
          throw new Error(data.message || data.detail || "Dashboard request failed");
        }
        render(data);
      } catch (error) {
        text("statusText", "Offline");
        document.getElementById("alerts").innerHTML = `<span class="error">${error.message}</span>`;
      }
    }

    function showAdminOverlay() {
      document.getElementById("adminOverlay").classList.add("visible");
      document.getElementById("adminLogin").style.display = adminToken ? "none" : "block";
      document.getElementById("adminControls").style.display = adminToken ? "block" : "none";
      if (adminToken) refreshAdminStatus();
    }

    function hideAdminOverlay() {
      document.getElementById("adminOverlay").classList.remove("visible");
    }

    async function adminFetch(path, options = {}) {
      const headers = { ...(options.headers || {}) };
      if (adminToken) headers.Authorization = `Bearer ${adminToken}`;
      const response = await fetch(path, { ...options, headers });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success === false) {
        throw new Error(data.message || data.detail || "Admin request failed");
      }
      return data;
    }

    function adminLog(value) {
      document.getElementById("adminLog").textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    }

    async function refreshAdminStatus() {
      try {
        adminLog(await adminFetch("/api/admin/status"));
      } catch (error) {
        adminLog(error.message);
      }
    }

    document.getElementById("adminHotspot").addEventListener("pointerdown", () => {
      clearTimeout(adminPressTimer);
      adminPressTimer = setTimeout(showAdminOverlay, 5000);
    });
    document.getElementById("adminHotspot").addEventListener("pointerup", () => clearTimeout(adminPressTimer));
    document.getElementById("adminHotspot").addEventListener("pointercancel", () => clearTimeout(adminPressTimer));
    document.addEventListener("keydown", (event) => {
      if (event.ctrlKey && event.altKey && event.key.toLowerCase() === "a") showAdminOverlay();
      if (event.key === "Escape") hideAdminOverlay();
    });

    document.getElementById("adminLoginButton").onclick = async () => {
      try {
        const payload = {
          email: document.getElementById("adminEmail").value,
          password: document.getElementById("adminPassword").value,
          pin: document.getElementById("adminPin").value,
        };
        const data = await adminFetch("/api/admin/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        adminToken = data.token;
        sessionStorage.setItem("kahrabaiqAdminToken", adminToken);
        showAdminOverlay();
      } catch (error) {
        document.getElementById("adminCopy").textContent = error.message;
      }
    };

    document.getElementById("lockDashboardButton").onclick = async () => {
      try {
        await adminFetch("/api/admin/lock", { method: "POST" });
      } catch (_) {}
      adminToken = "";
      sessionStorage.removeItem("kahrabaiqAdminToken");
      hideAdminOverlay();
    };
    document.getElementById("refreshAdminStatusButton").onclick = refreshAdminStatus;
    document.getElementById("restartDashboardButton").onclick = async () => adminLog(await adminFetch("/api/admin/services/restart-dashboard", { method: "POST" }));
    document.getElementById("exitKioskButton").onclick = async () => adminLog(await adminFetch("/api/admin/kiosk/exit", { method: "POST" }));
    document.getElementById("returnKioskButton").onclick = async () => adminLog(await adminFetch("/api/admin/kiosk/start", { method: "POST" }));
    document.getElementById("maintenanceButton").onclick = async () => {
      if (!confirm("This will stop the dashboard and return the Pi to setup mode. Continue?")) return;
      adminLog(await adminFetch("/api/admin/maintenance/start", { method: "POST" }));
    };

    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>
"""


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


@app.post("/api/admin/login")
def admin_login() -> Any:
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or payload.get("username") or "").strip()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    pin = str(payload.get("pin") or "")
    auth_source = ""
    try:
        if recovery_pin_ok(pin):
            auth_source = "local_recovery_pin"
        elif local_admin_password_ok(username, password):
            auth_source = "local_password"
        else:
            cloud_admin_password_ok(email, password)
            auth_source = "platform_admin"
    except Exception:
        return jsonify({"success": False, "message": "Invalid admin credentials."}), 401
    session = create_admin_session()
    return jsonify({"success": True, "auth_source": auth_source, **session})


@app.post("/api/admin/logout")
def admin_logout() -> Any:
    ok, token = require_admin()
    if ok:
        with _state_lock:
            _admin_sessions.pop(token, None)
    return jsonify({"success": True})


@app.get("/api/admin/session")
def admin_session() -> Any:
    ok, token = require_admin()
    if not ok:
        return jsonify({"success": False, "authenticated": False}), 401
    with _state_lock:
        expires_at_ms = int(_admin_sessions.get(token) or 0)
    return jsonify({"success": True, "authenticated": True, "expires_at_ms": expires_at_ms})


@app.post("/api/admin/lock")
def admin_lock() -> Any:
    ok, token = require_admin()
    if not ok:
        return jsonify({"success": False, "message": token}), 401
    with _state_lock:
        _admin_sessions.pop(token, None)
    return jsonify({"success": True, "locked": True})


@app.get("/api/admin/status")
def admin_status() -> Any:
    ok, message = require_admin()
    if not ok:
        return jsonify({"success": False, "message": message}), 401
    return jsonify(
        {
            "success": True,
            "pi_id": PI_ID,
            "home_id": HOME_ID,
            "local_ip": local_ip(),
            "wifi_ssid": current_wifi_ssid(),
            "provisioned": PROVISIONING_MARKER_PATH.exists(),
            "provisioning_marker_path": str(PROVISIONING_MARKER_PATH),
            "agent_state": dict(_agent_state),
            "esp32": esp32_link(),
        }
    )


@app.post("/api/admin/maintenance/start")
def admin_start_maintenance() -> Any:
    ok, message = require_admin()
    if not ok:
        return jsonify({"success": False, "message": message}), 401
    commands = [
        run_admin_command(["sudo", "-n", "/usr/bin/systemctl", "stop", "kahrabaiq-kiosk-browser.service"], timeout=20),
        run_admin_command(["sudo", "-n", "/usr/bin/rm", "-f", str(PROVISIONING_MARKER_PATH)], timeout=10),
        run_admin_command(["sudo", "-n", "/usr/bin/systemctl", "start", "kahrabaiq-provisioning.service"], timeout=20),
        run_admin_command(["sudo", "-n", "/usr/bin/systemctl", "start", "kahrabaiq-setup-screen.service"], timeout=20),
    ]
    return jsonify({"success": all(item["success"] for item in commands), "commands": commands})


@app.post("/api/admin/services/restart-dashboard")
def admin_restart_dashboard() -> Any:
    ok, message = require_admin()
    if not ok:
        return jsonify({"success": False, "message": message}), 401
    command = run_admin_command(["sudo", "-n", "/usr/bin/systemctl", "restart", "kahrabaiq-kiosk-browser.service"], timeout=20)
    return jsonify({"success": command["success"], "command": command})


@app.post("/api/admin/kiosk/exit")
def admin_exit_kiosk() -> Any:
    ok, message = require_admin()
    if not ok:
        return jsonify({"success": False, "message": message}), 401
    commands = [
        run_admin_command(["sudo", "-n", "/usr/bin/systemctl", "stop", "kahrabaiq-kiosk-browser.service"], timeout=20),
        run_admin_command(["sudo", "-n", "/usr/bin/systemctl", "stop", "kahrabaiq-setup-screen.service"], timeout=20),
    ]
    return jsonify(
        {
            "success": all(item["success"] for item in commands),
            "message": "Kiosk stopped. Raspberry Pi OS desktop is available if the session is unlocked.",
            "commands": commands,
        }
    )


@app.post("/api/admin/kiosk/start")
def admin_start_kiosk() -> Any:
    ok, message = require_admin()
    if not ok:
        return jsonify({"success": False, "message": message}), 401
    provisioned = PROVISIONING_MARKER_PATH.exists()
    service = "kahrabaiq-kiosk-browser.service" if provisioned else "kahrabaiq-setup-screen.service"
    command = run_admin_command(["sudo", "-n", "/usr/bin/systemctl", "start", service], timeout=20)
    return jsonify({"success": command["success"], "mode": "dashboard" if provisioned else "setup", "command": command})


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


@app.get("/api/kiosk/dashboard-data")
def local_kiosk_dashboard_data() -> Any:
    try:
        return jsonify(kiosk_dashboard_data())
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 503


@app.get("/dashboard")
def local_dashboard() -> Response:
    return Response(KIOSK_DASHBOARD_HTML, mimetype="text/html")


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
