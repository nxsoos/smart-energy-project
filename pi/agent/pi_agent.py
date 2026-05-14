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
from flask import Flask, Response, jsonify, request, send_from_directory

from local_state_store import get_path, home_snapshot, set_path
try:
    from local_command_controller import (
        execute_local_command,
        sync_home_assistant_device_states,
    )
except Exception:
    execute_local_command = None
    sync_home_assistant_device_states = None

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
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
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
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as error:
        return {
            "command": args,
            "returncode": -1,
            "stdout": "",
            "stderr": str(error),
            "success": False,
        }
    return {
        "command": args,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "success": result.returncode == 0,
    }


def read_service_logs(lines: int = 160) -> dict[str, Any]:
    count = str(max(20, min(int(lines or 160), 500)))
    services = [
        "kahrabaiq-agent.service",
        "kahrabaiq-kiosk-browser.service",
        "kahrabaiq-sensor-receiver.service",
        "kahrabaiq-iot-live-publisher.service",
        "kahrabaiq-command-runner.service",
        "kahrabaiq-summary-sync.service",
    ]
    args = [
        "sudo",
        "-n",
        "/usr/bin/journalctl",
        "--no-pager",
        "--utc",
        "-n",
        count,
    ]
    for service in services:
        args.extend(["-u", service])
    result = run_admin_command(args, timeout=12)
    if result["success"] or result["stdout"] or result["stderr"]:
        return {"lines": int(count), "services": services, **result}
    fallback = run_admin_command(["/usr/bin/journalctl", "--no-pager", "--utc", "-n", count], timeout=12)
    return {"lines": int(count), "services": services, **fallback}


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


def kiosk_home_invite_qr() -> dict[str, Any]:
    response = api_request("POST", "/api/dashboard/home-invite")
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
  <link rel="icon" href="/assets/favicon.ico" sizes="any">
  <style>
    :root {
      color-scheme: dark;
      --bg: #050505;
      --panel: #101010;
      --panel-2: #181818;
      --panel-3: #1f1f1f;
      --text: #e8eaed;
      --muted: #7c838d;
      --muted-2: #4b5563;
      --cyan: #ff2d2d;
      --cyan-bright: #ff5555;
      --green: #22c55e;
      --yellow: #f59e0b;
      --red: #ff5c7a;
      --border: rgba(255, 255, 255, 0.075);
      --border-strong: rgba(255, 45, 45, 0.34);
      --glow: rgba(255, 45, 45, 0.18);
    }

    * { box-sizing: border-box; }

    [hidden] { display: none !important; }

    html { background: var(--bg); }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle 46rem at 78% -12%, rgba(255, 45, 45, 0.13), transparent 58%),
        radial-gradient(circle 38rem at 10% 16%, rgba(255, 107, 26, 0.07), transparent 55%),
        linear-gradient(180deg, #080808 0%, var(--bg) 58%, #070505 100%);
      color: var(--text);
      font-family: Sora, Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
      text-rendering: geometricPrecision;
      -webkit-font-smoothing: antialiased;
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      z-index: -1;
      pointer-events: none;
      background: linear-gradient(rgba(255, 255, 255, 0.025) 1px, transparent 1px);
      background-size: 100% 4px;
      opacity: 0.18;
    }

    .ambient-grid {
      position: fixed;
      inset: auto -10vw 0;
      z-index: -1;
      height: 46vh;
      pointer-events: none;
      transform: perspective(700px) rotateX(56deg) scale(1.25);
      transform-origin: bottom center;
      background-image:
        linear-gradient(to right, rgba(255, 255, 255, 0.055) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(255, 45, 45, 0.14) 1px, transparent 1px);
      background-size: 64px 64px;
      mask-image: linear-gradient(to top, rgba(0, 0, 0, 0.88), transparent 72%);
      opacity: 0.7;
    }

    .shell {
      width: min(1220px, calc(100vw - 36px));
      margin: 0 auto;
      padding: 24px 0 42px;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      min-height: 92px;
      margin-bottom: 22px;
      padding: 16px 18px;
      border: 1px solid var(--border);
      border-radius: 22px;
      background: rgba(10, 10, 10, 0.78);
      box-shadow: 0 28px 80px rgba(0, 0, 0, 0.36), inset 0 1px 0 rgba(191, 195, 201, 0.08);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 16px;
      min-width: 0;
    }

    .brand-mark {
      width: clamp(128px, 16vw, 176px);
      height: auto;
      flex: 0 0 auto;
      object-fit: contain;
      filter: drop-shadow(0 0 22px var(--glow));
    }

    .brand-copy {
      min-width: 0;
    }

    h1 {
      margin: 0;
      font-family: Orbitron, Sora, Inter, sans-serif;
      font-size: 24px;
      font-weight: 700;
      line-height: 1;
      letter-spacing: -0.02em;
    }

    .eyebrow {
      margin: 0 0 8px;
      color: var(--cyan-bright);
      font-family: Orbitron, Sora, Inter, sans-serif;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.18em;
      text-transform: uppercase;
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
      border: 1px solid var(--border-strong);
      border-radius: 999px;
      background: rgba(255, 45, 45, 0.1);
      color: var(--text);
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 13px;
      font-weight: 800;
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
      position: relative;
      overflow: hidden;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.045), transparent 38%),
        var(--panel);
      border: 1px solid var(--border);
      border-radius: 22px;
      padding: 22px;
      box-shadow: 0 20px 64px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(191, 195, 201, 0.055);
    }

    .hero::after {
      content: "";
      position: absolute;
      right: -80px;
      bottom: -120px;
      width: 320px;
      height: 320px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(255, 45, 45, 0.2), transparent 68%);
      pointer-events: none;
    }

    .hero { grid-column: span 7; }
    .room { grid-column: span 5; }
    .sensors { grid-column: span 6; }
    .notes { grid-column: span 6; }
    .wide { grid-column: span 12; }

    .metric-row {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-top: 18px;
    }

    .metric {
      min-height: 108px;
      border: 1px solid rgba(255, 255, 255, 0.055);
      border-radius: 14px;
      background: rgba(5, 5, 5, 0.48);
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
      font-size: clamp(56px, 8vw, 104px);
      font-weight: 800;
      letter-spacing: -0.08em;
      line-height: 0.92;
      color: var(--text);
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

    .section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 16px;
    }

    .section-title {
      color: var(--cyan-bright);
      font-family: Orbitron, Sora, Inter, sans-serif;
      font-size: 15px;
      font-weight: 900;
      letter-spacing: .04em;
      text-transform: uppercase;
    }

    .muted {
      color: var(--muted);
    }

    .reading-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(138px, 1fr));
      gap: 12px;
    }

    .reading {
      min-height: 92px;
      border: 1px solid rgba(255, 255, 255, 0.055);
      border-radius: 14px;
      background: rgba(5, 5, 5, 0.48);
      padding: 14px;
    }

    .devices {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }

    .device {
      border: 1px solid rgba(255, 255, 255, 0.055);
      border-radius: 14px;
      background: rgba(5, 5, 5, 0.48);
      padding: 18px;
      min-height: 138px;
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

    .state.stale {
      background: rgba(255, 176, 32, 0.14);
      color: var(--yellow);
    }

    .command-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
    }

    .command-actions button {
      border: 1px solid rgba(255, 45, 45, 0.28);
      border-radius: 999px;
      min-height: 40px;
      padding: 0 16px;
      background: rgba(255, 45, 45, 0.1);
      color: var(--text);
      font-weight: 900;
    }

    .command-actions button.primary {
      background: var(--cyan);
      color: var(--text);
    }

    .command-actions button.danger {
      background: rgba(255, 92, 122, 0.16);
      color: #fecaca;
      border-color: rgba(255, 92, 122, 0.35);
    }

    .command-actions button:disabled {
      opacity: .45;
    }

    .command-status {
      margin-top: 10px;
      min-height: 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.35;
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

    .notes-list {
      display: grid;
      gap: 10px;
      line-height: 1.45;
    }

    .note {
      border-radius: 12px;
      background: rgba(5, 5, 5, 0.48);
      padding: 12px 14px;
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
      background: #101010;
      border: 1px solid rgba(255, 45, 45, 0.34);
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
      background: rgba(255, 45, 45, 0.12);
      color: var(--text);
      font-weight: 800;
    }

    .admin-panel button.primary { background: var(--cyan); color: var(--text); }
    .admin-panel button.danger { background: var(--red); color: white; }
    .admin-log {
      max-height: 340px;
      margin-top: 14px;
      overflow: auto;
      color: var(--muted);
      white-space: pre-wrap;
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
    }

    .invite-card {
      grid-column: span 12;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 240px;
      gap: 18px;
      align-items: center;
    }

    .invite-copy {
      color: var(--muted);
      line-height: 1.5;
      margin: 0 0 14px;
    }

    .invite-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }

    .invite-actions button {
      border: none;
      border-radius: 999px;
      padding: 12px 16px;
      background: var(--cyan);
      color: var(--text);
      font-weight: 900;
    }

    .invite-status {
      color: var(--muted);
      font-size: 13px;
      font-weight: 800;
    }

    .invite-qr {
      min-height: 220px;
      display: grid;
      place-items: center;
      border-radius: 18px;
      background: #f7f4ef;
      color: #111827;
      padding: 12px;
      overflow: hidden;
      font-weight: 900;
    }

    .invite-qr svg {
      width: 100%;
      height: auto;
      display: block;
    }

    @media (max-width: 820px) {
      header { align-items: flex-start; flex-direction: column; }
      .brand { align-items: flex-start; flex-direction: column; gap: 12px; }
      .brand-mark { width: 132px; }
      .hero, .room, .sensors, .notes { grid-column: span 12; }
      .invite-card { grid-template-columns: 1fr; }
      .invite-qr { width: min(240px, 100%); margin: 0 auto; }
      .metric-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="ambient-grid" aria-hidden="true"></div>
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
          <button type="button" id="viewLogsButton">View Logs</button>
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
        <img class="brand-mark" src="/assets/kahrabaiq-wordmark.png" alt="KahrabaIQ logo">
        <div class="brand-copy">
          <p class="eyebrow">Home Energy Command</p>
          <h1>Live Dashboard</h1>
          <div class="sub" id="subtitle">Loading dashboard...</div>
        </div>
      </div>
      <div class="pill"><span class="dot"></span><span id="statusText">Connecting</span></div>
    </header>

    <section class="grid">
      <article class="card hero">
        <div class="section-head">
          <div class="section-title">Live Energy</div>
          <div class="muted" id="energyTimestamp">Waiting for update</div>
        </div>
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
        <div class="section-head">
          <div class="section-title">Room Status</div>
          <div class="state" id="roomStatus">Unknown</div>
        </div>
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
        <div class="section-head">
          <div class="section-title">Breakers & Controls</div>
          <div class="muted">Meter readings are shown only for metered breakers.</div>
        </div>
        <div class="devices" id="devices"></div>
      </article>

      <article class="card sensors">
        <div class="section-head">
          <div class="section-title">Sensor Data</div>
          <div class="muted" id="sensorUpdated">No timestamp</div>
        </div>
        <div class="reading-grid">
          <div class="reading">
            <div class="label">AQI</div>
            <div class="small-value" id="aqi">--</div>
          </div>
          <div class="reading">
            <div class="label">eCO2</div>
            <div class="small-value" id="eco2">--</div>
          </div>
          <div class="reading">
            <div class="label">TVOC</div>
            <div class="small-value" id="tvoc">--</div>
          </div>
          <div class="reading">
            <div class="label">Light</div>
            <div class="small-value" id="light">--</div>
          </div>
          <div class="reading">
            <div class="label">Sound</div>
            <div class="small-value" id="sound">--</div>
          </div>
          <div class="reading">
            <div class="label">Feed</div>
            <div class="small-value" id="sensorFeed">--</div>
          </div>
        </div>
      </article>

      <article class="card notes">
        <div class="section-head">
          <div class="section-title">Alerts & Notes</div>
          <div class="muted">Active items only</div>
        </div>
        <div id="alerts">No active alerts.</div>
      </article>

      <article class="card invite-card">
        <div>
          <div class="section-title">Mobile App Access</div>
          <p class="invite-copy">Generate a one-use QR code. When scanned in the KahrabaIQ app, the user joins this dashboard home.</p>
          <div class="invite-actions">
            <button type="button" id="generateInviteQrButton">Show QR Code</button>
            <span class="invite-status" id="inviteQrStatus">QR not generated yet.</span>
          </div>
        </div>
        <div class="invite-qr" id="inviteQrBox">QR</div>
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

    function firstPresent(...values) {
      for (const value of values) {
        if (value !== null && value !== undefined && value !== "") return value;
      }
      return undefined;
    }

    function boolValue(value) {
      if (typeof value === "boolean") return value;
      if (typeof value === "number") return value !== 0;
      if (typeof value === "string") return ["true", "1", "yes", "on", "detected", "motion", "smoke", "gas"].includes(value.trim().toLowerCase());
      return false;
    }

    function valueOrDash(value, suffix = "") {
      if (value === null || value === undefined || value === "") return "--";
      const parsed = Number(value);
      if (!Number.isFinite(parsed)) return String(value);
      return `${fmt.format(parsed)}${suffix}`;
    }

    function currentSensorValue(online, value, suffix = "") {
      return online ? valueOrDash(value, suffix) : "Unavailable";
    }

    function timestampText(value) {
      const ms = number(value, 0);
      if (!ms) return "No timestamp";
      return new Date(ms).toLocaleString();
    }

    function deviceState(device) {
      if (!device.online) return "offline";
      return device.display_state || device.state || "unknown";
    }

    function deviceStatusClass(device, state) {
      if (state === "offline") return "offline";
      if (device.stale) return "stale";
      return "";
    }

    function hasMeterReadings(device) {
      const type = String(device.type || "");
      return type === "smart_breaker" && device.energy_supported !== false;
    }

    function canControl(device) {
      return device.controllable === true;
    }

    function sensorDevice(devices) {
      return Object.values(devices).find((device) => {
        const type = String(device.type || "");
        const id = String(device.id || device.device_id || "");
        return type === "sensor_hub" || type === "esp32_sensor" || id.startsWith("esp32");
      }) || {};
    }

    function render(data) {
      const dashboard = data.dashboard || {};
      const energy = dashboard.energy || {};
      const room = dashboard.room || {};
      const devices = dashboard.devices || {};
      const sensorHub = sensorDevice(devices);
      const sensorPayload = Object.keys(sensorHub.sensors || {}).length ? sensorHub.sensors : room;
      const sensorStatus = sensorHub.status || {};
      const sensorTimestamp = firstPresent(sensorPayload.timestamp_ms, sensorPayload.timestampMs, sensorStatus.last_seen_ms, sensorStatus.lastSeenMs, room.timestamp_ms, room.timestampMs);
      const sensorOnline = boolValue(firstPresent(sensorHub.online, sensorPayload.sensorOnline, sensorPayload.sensor_online, sensorPayload.online, room.sensorOnline, room.sensor_online, room.online)) && sensorPayload.stale !== true && room.stale !== true;
      const deviceList = Object.values(devices).filter((device) => {
        const type = String(device.type || "");
        const id = String(device.id || device.device_id || "");
        return type !== "sensor_hub" && type !== "esp32_sensor" && !id.startsWith("esp32");
      });
      const breakers = deviceList.filter((device) => String(device.type || "").includes("breaker"));
      const activeBreakers = breakers.filter((device) => deviceState(device) === "on").length;

      text("subtitle", `${data.home_id || "home"} - ${dashboard.updated_at_iso || "waiting for live state"}`);
      text("statusText", data.paired ? "Live" : "Unpaired");
      text("energyTimestamp", timestampText(energy.timestampMs || energy.timestamp_ms || dashboard.updated_at_ms));
      text("power", fmt.format(number(energy.currentPowerW ?? energy.powerW)));
      text("energyToday", `${fmt.format(number(energy.energyTodayKwh ?? energy.totalEnergyKwh))} kWh`);
      text("costToday", `${number(energy.costToday).toFixed(3)} BD`);
      text("breakerCount", `${activeBreakers}/${breakers.length || 0}`);
      text("roomStatus", sensorOnline ? "Online" : room.stale ? "Stale" : "Offline");
      document.getElementById("roomStatus").className = `state ${sensorOnline ? "" : room.stale ? "stale" : "offline"}`;
      text("temperature", currentSensorValue(sensorOnline, firstPresent(sensorPayload.temperature, room.temperature), " C"));
      text("humidity", currentSensorValue(sensorOnline, firstPresent(sensorPayload.humidity, room.humidity), " %"));
      text("motion", sensorOnline ? (firstPresent(sensorPayload.motion_text, room.motion_text) || (boolValue(firstPresent(sensorPayload.motion, sensorPayload.motionDetected, sensorPayload.motion_detected, room.motion)) ? "Motion" : "Clear")) : "Unavailable");
      text("smoke", sensorOnline ? (firstPresent(sensorPayload.smoke_text, sensorPayload.smoke_status, room.smoke_text, room.smoke_status) || (boolValue(firstPresent(sensorPayload.smoke, sensorPayload.smokeDetected, sensorPayload.smoke_detected, sensorPayload.gasDetected, sensorPayload.gas_detected, room.smoke)) ? "Detected" : "Clear")) : "Unavailable");
      text("sensorUpdated", timestampText(sensorTimestamp));
      text("aqi", currentSensorValue(sensorOnline, firstPresent(sensorPayload.aqi, sensorPayload.airQuality, sensorPayload.air_quality, room.aqi, room.airQuality, room.air_quality)));
      text("eco2", currentSensorValue(sensorOnline, firstPresent(sensorPayload.eco2, room.eco2), " ppm"));
      text("tvoc", currentSensorValue(sensorOnline, firstPresent(sensorPayload.tvoc, room.tvoc), " ppb"));
      text("light", currentSensorValue(sensorOnline, firstPresent(sensorPayload.light_raw, sensorPayload.lightLevel, sensorPayload.light_level, room.light_raw, room.lightLevel, room.light_level)));
      text("sound", currentSensorValue(sensorOnline, firstPresent(sensorPayload.sound_raw, sensorPayload.soundLevel, sensorPayload.sound_level, sensorPayload.noise, room.sound_raw, room.soundLevel, room.sound_level, room.noise)));
      text("sensorFeed", sensorOnline ? "Online" : room.stale ? "Stale" : "Offline");

      const devicesNode = document.getElementById("devices");
      devicesNode.innerHTML = "";
      if (!deviceList.length) {
        devicesNode.textContent = "No devices are available.";
      } else {
        for (const device of deviceList) {
          const state = deviceState(device);
          const card = document.createElement("div");
          card.className = "device";
          const readings = hasMeterReadings(device)
            ? `
              <div class="two-col">
                <div><div class="label">Power</div><div class="small-value">${valueOrDash(device.power_W, " W")}</div></div>
                <div><div class="label">Energy</div><div class="small-value">${valueOrDash(device.energy_kWh, " kWh")}</div></div>
                <div><div class="label">Voltage</div><div class="small-value">${valueOrDash(device.voltage_V, " V")}</div></div>
                <div><div class="label">Current</div><div class="small-value">${valueOrDash(device.current_A, " A")}</div></div>
              </div>
            `
            : `
              <div class="muted">Control state only. This device does not report power, energy, voltage, or current readings.</div>
            `;
          const commandActions = canControl(device)
            ? `
              <div class="command-actions" data-device-id="${device.device_id || device.id}">
                <button class="primary" type="button" data-command="turn_on">Turn On</button>
                <button class="danger" type="button" data-command="turn_off">Turn Off</button>
              </div>
              <div class="command-status" id="commandStatus-${device.device_id || device.id}"></div>
            `
            : "";
          card.innerHTML = `
            <div class="device-head">
              <div>
                <div class="device-name">${device.name || device.id || "Device"}</div>
                <div class="label">${device.branch || device.control_method || ""}</div>
              </div>
              <div class="state ${deviceStatusClass(device, state)}">${state}</div>
            </div>
            ${readings}
            ${commandActions}
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
      for (const alert of alerts) {
        notes.push(`<span class="error">${alert.title || alert.message || "Active alert"}</span>`);
      }
      for (const notification of aiNotifications.filter((item) => {
        const severity = String(item.severity || "info").toLowerCase();
        return severity === "critical" || severity === "high";
      }).slice(0, 3)) {
        const severity = String(notification.severity || "info").toLowerCase();
        const klass = severity === "critical" || severity === "high" ? "error" : "warn";
        notes.push(`<span class="${klass}">AI: ${notification.title || notification.message || "Notification"}</span>`);
      }
      document.getElementById("alerts").innerHTML = notes.length ? `<div class="notes-list">${notes.map((note) => `<div class="note">${note}</div>`).join("")}</div>` : "No active alerts.";

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

    async function generateInviteQr() {
      const button = document.getElementById("generateInviteQrButton");
      const status = document.getElementById("inviteQrStatus");
      const qrBox = document.getElementById("inviteQrBox");
      button.disabled = true;
      status.textContent = "Generating QR...";
      qrBox.textContent = "Loading";
      try {
        const response = await fetch("/api/kiosk/home-invite-qr", { method: "POST", cache: "no-store" });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
          throw new Error(data.message || data.detail || "Could not generate QR.");
        }
        qrBox.innerHTML = data.qr_svg || "QR unavailable";
        const expiry = data.expires_at_ms ? new Date(data.expires_at_ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
        status.textContent = expiry ? `Ready. Expires at ${expiry}.` : "Ready.";
      } catch (error) {
        qrBox.textContent = "--";
        status.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    }

    async function executeDeviceCommand(deviceId, command, container) {
      const buttons = Array.from(container.querySelectorAll("button"));
      const status = document.getElementById(`commandStatus-${deviceId}`);
      buttons.forEach((button) => button.disabled = true);
      if (status) status.textContent = `${command === "turn_on" ? "Turning on" : "Turning off"}...`;
      try {
        const response = await fetch("/api/kiosk/device-command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_id: deviceId, command }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
          throw new Error(data.message || data.detail || "Command failed");
        }
        if (status) status.textContent = data.message || "Command completed.";
        setTimeout(refresh, 600);
      } catch (error) {
        if (status) status.textContent = error.message;
      } finally {
        buttons.forEach((button) => button.disabled = false);
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

    document.getElementById("devices").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-command]");
      if (!button) return;
      const container = button.closest(".command-actions");
      if (!container) return;
      executeDeviceCommand(container.dataset.deviceId, button.dataset.command, container);
    });

    document.getElementById("lockDashboardButton").onclick = async () => {
      try {
        await adminFetch("/api/admin/lock", { method: "POST" });
      } catch (_) {}
      adminToken = "";
      sessionStorage.removeItem("kahrabaiqAdminToken");
      hideAdminOverlay();
    };
    document.getElementById("refreshAdminStatusButton").onclick = refreshAdminStatus;
    document.getElementById("viewLogsButton").onclick = async () => {
      const data = await adminFetch("/api/admin/logs?lines=180");
      const output = [
        data.stdout || "",
        data.stderr ? `\n[stderr]\n${data.stderr}` : "",
      ].join("").trim();
      adminLog(output || "No service logs returned.");
    };
    document.getElementById("restartDashboardButton").onclick = async () => adminLog(await adminFetch("/api/admin/services/restart-dashboard", { method: "POST" }));
    document.getElementById("exitKioskButton").onclick = async () => adminLog(await adminFetch("/api/admin/kiosk/exit", { method: "POST" }));
    document.getElementById("returnKioskButton").onclick = async () => adminLog(await adminFetch("/api/admin/kiosk/start", { method: "POST" }));
    document.getElementById("generateInviteQrButton").onclick = generateInviteQr;
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


@app.get("/api/admin/logs")
def admin_logs() -> Any:
    ok, message = require_admin()
    if not ok:
        return jsonify({"success": False, "message": message}), 401
    try:
        lines = int(request.args.get("lines", "160"))
    except ValueError:
        lines = 160
    logs = read_service_logs(lines)
    command_success = bool(logs.pop("success", False))
    return jsonify({"success": True, "command_success": command_success, **logs})


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
        if sync_home_assistant_device_states is not None:
            sync_home_assistant_device_states(force=True)
        return jsonify(kiosk_dashboard_data())
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 503


@app.post("/api/kiosk/home-invite-qr")
def local_kiosk_home_invite_qr() -> Any:
    try:
        return jsonify(kiosk_home_invite_qr())
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 503


@app.post("/api/kiosk/device-command")
def local_kiosk_device_command() -> Any:
    if execute_local_command is None:
        return jsonify({"success": False, "message": "Local command controller is not available."}), 503
    payload = request.get_json(silent=True) or {}
    device_id = str(payload.get("device_id") or "").strip()
    command = str(payload.get("command") or "").strip()
    if not device_id:
        return jsonify({"success": False, "message": "device_id is required."}), 400
    if command not in {"turn_on", "turn_off"}:
        return jsonify({"success": False, "message": "Unsupported command."}), 400
    if sync_home_assistant_device_states is not None:
        sync_home_assistant_device_states(force=True)
    result = execute_local_command(
        device_id,
        command,
        requested_by="pi_dashboard",
        source="pi_dashboard",
    )
    status_code = 200 if result.get("success") else 409
    return jsonify(result), status_code


@app.get("/dashboard")
def local_dashboard() -> Response:
    return Response(KIOSK_DASHBOARD_HTML, mimetype="text/html")


@app.get("/assets/<path:filename>")
def local_dashboard_asset(filename: str) -> Any:
    return send_from_directory(ASSETS_DIR, filename)


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
