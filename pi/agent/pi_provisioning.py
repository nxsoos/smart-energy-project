from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request

try:
    import qrcode
    import qrcode.image.svg
except Exception:  # pragma: no cover - optional runtime dependency checked by endpoint
    qrcode = None


load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")
load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
load_dotenv()

HOME_ID = os.environ.get("HOME_ID", "")
PI_ID = os.environ.get("PI_ID", "pi_local_001")
PI_DEVICE_TOKEN = os.environ.get("PI_DEVICE_TOKEN", "")
KAHRABAIQ_API_URL = os.environ.get("KAHRABAIQ_API_URL", "").rstrip("/")
AGENT_VERSION = os.environ.get("PI_AGENT_VERSION", "local-agent-1")
ESP32_DEVICE_ID = os.environ.get("ESP32_DEVICE_ID", "esp32_01")
ESP32_DEVICE_KEY = os.environ.get("ESP32_DEVICE_KEY", "")

HOME_WIFI_INTERFACE = os.environ.get("PI_HOME_WIFI_INTERFACE", "wlan0")
SETUP_WIFI_INTERFACE = os.environ.get("PI_SETUP_WIFI_INTERFACE", "wlan1")
SETUP_AP_SSID = os.environ.get("PI_SETUP_AP_SSID", "KahrabaIQ-Pi-Setup")
SETUP_AP_PASSWORD = os.environ.get("PI_SETUP_AP_PASSWORD", "kahrabaiq-setup")
SETUP_AP_CONNECTION = os.environ.get("PI_SETUP_AP_CONNECTION", "kahrabaiq-setup-ap")
SETUP_PORT = int(os.environ.get("PI_PROVISIONING_PORT", "8080"))

ESP32_SETUP_SSID = os.environ.get("ESP32_SETUP_SSID", "KahrabaIQ-ESP32-Setup")
ESP32_SETUP_PASSWORD = os.environ.get("ESP32_SETUP_PASSWORD", "kahrabaiq123")
ESP32_SETUP_URL = os.environ.get("ESP32_SETUP_URL", "").rstrip("/")
ESP32_CONNECT_TIMEOUT_SECONDS = int(os.environ.get("ESP32_CONNECT_TIMEOUT_SECONDS", "45"))
HOME_WIFI_CONNECT_TIMEOUT_SECONDS = int(os.environ.get("HOME_WIFI_CONNECT_TIMEOUT_SECONDS", "60"))
ESP32_VERIFY_TIMEOUT_SECONDS = int(os.environ.get("ESP32_VERIFY_TIMEOUT_SECONDS", "30"))
PAIRING_POLL_SECONDS = float(os.environ.get("PI_PAIRING_POLL_SECONDS", "2"))
PAIRING_WAIT_TIMEOUT_SECONDS = int(os.environ.get("PI_PAIRING_WAIT_TIMEOUT_SECONDS", "900"))

ESP32_DISCOVERY_CANDIDATES = [
    item.strip().rstrip("/")
    for item in os.environ.get("ESP32_DISCOVERY_CANDIDATES", "http://kahrabaiq-esp32.local").split(",")
    if item.strip()
]
PI_SENSOR_BASE_URL = os.environ.get("PI_SENSOR_BASE_URL", "http://kahrabaiq-pi.local:5000").rstrip("/")
PI_LOCAL_BASE_URL = os.environ.get("PI_LOCAL_BASE_URL", "http://kahrabaiq-pi.local:5001").rstrip("/")
PROVISIONING_MARKER_PATH = Path(os.environ.get("PROVISIONING_MARKER_PATH", "/var/lib/kahrabaiq/provisioned.json"))

app = Flask(__name__)
_state_lock = threading.RLock()
_setup_thread: threading.Thread | None = None
_shutdown_requested = threading.Event()
_setup_context: dict[str, str] = {}
_state: dict[str, Any] = {
    "running": False,
    "wifi_configured": False,
    "internet_ready": False,
    "paired": False,
    "home_id": HOME_ID or None,
    "pi_id": PI_ID,
    "pairing_payload": None,
    "pairing_expires_at_ms": None,
    "esp32_provisioned": False,
    "esp32_verified": False,
    "setup_complete": PROVISIONING_MARKER_PATH.exists(),
    "stage": "complete" if PROVISIONING_MARKER_PATH.exists() else "wifi_setup",
    "message": "Setup is complete." if PROVISIONING_MARKER_PATH.exists() else "Waiting for home Wi-Fi credentials.",
    "last_error": None,
    "updated_at_iso": None,
}


SETUP_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KahrabaIQ Setup</title>
  <style>
    :root { color-scheme: dark; --bg:#050816; --panel:#111827; --muted:#94a3b8; --text:#f8fafc; --cyan:#22d3ee; --green:#34d399; --yellow:#fbbf24; --red:#fb7185; }
    * { box-sizing: border-box; }
    body { margin:0; min-height:100vh; display:grid; place-items:center; padding:24px; background:radial-gradient(circle at top,#164e63,var(--bg) 48%); color:var(--text); font-family:Inter,system-ui,sans-serif; }
    main { width:min(860px,100%); background:rgba(17,24,39,.95); border:1px solid rgba(34,211,238,.35); border-radius:26px; padding:28px; box-shadow:0 30px 90px rgba(0,0,0,.42); }
    h1 { margin:0 0 8px; font-size:clamp(32px,6vw,58px); }
    h2 { margin:0 0 10px; }
    p { color:var(--muted); line-height:1.5; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; margin:18px 0; }
    .step { border:1px solid rgba(148,163,184,.25); border-radius:18px; padding:16px; background:#020617; }
    .step strong { display:block; margin-bottom:8px; }
    .done { color:var(--green); } .active { color:var(--cyan); } .wait { color:var(--yellow); } .error { color:var(--red); }
    label { display:block; margin-top:14px; color:var(--muted); font-weight:800; }
    input { width:100%; margin-top:8px; border:1px solid rgba(148,163,184,.4); border-radius:14px; padding:14px 16px; background:#020617; color:var(--text); font-size:16px; }
    button { width:100%; margin-top:20px; border:0; border-radius:999px; padding:15px 18px; background:linear-gradient(135deg,#06b6d4,#22c55e); color:#001018; font-weight:900; font-size:16px; }
    button:disabled { opacity:.55; }
    .panel { margin-top:18px; padding:18px; border-radius:18px; background:#020617; border:1px solid rgba(148,163,184,.22); }
    .qr { width:min(280px,80vw); min-height:280px; display:grid; place-items:center; margin:12px auto; background:#fff; border-radius:18px; padding:12px; }
    .qr img { width:100%; height:auto; }
    code { display:block; overflow-wrap:anywhere; color:#bae6fd; background:#0f172a; padding:12px; border-radius:12px; }
  </style>
</head>
<body>
  <main>
    <h1>KahrabaIQ Setup</h1>
    <p id="lead">Connect this Pi to home Wi-Fi first. After internet is ready, scan the QR in the mobile app. Sensor setup starts only after the Pi receives the real home ID.</p>
    <div class="grid">
      <div class="step"><strong>1. Wi-Fi</strong><span id="wifiState" class="active">Waiting</span></div>
      <div class="step"><strong>2. Mobile Pairing</strong><span id="pairState" class="wait">Waiting for Wi-Fi</span></div>
      <div class="step"><strong>3. Sensors</strong><span id="sensorState" class="wait">Waiting for pairing</span></div>
      <div class="step"><strong>4. Dashboard</strong><span id="dashState" class="wait">Locked</span></div>
    </div>

    <section class="panel" id="wifiPanel">
      <h2>Connect Pi To Wi-Fi</h2>
      <p>Connect your phone or laptop to <strong>__SETUP_AP_SSID__</strong> using password <strong>__SETUP_AP_PASSWORD__</strong>, then enter the home Wi-Fi below.</p>
      <form id="wifiForm">
        <label>Home Wi-Fi SSID<input name="ssid" autocomplete="off" required></label>
        <label>Home Wi-Fi Password<input name="password" type="password" required></label>
        <label>ESP32 Device ID<input name="device_id" value="__ESP32_DEVICE_ID__"></label>
        <label>ESP32 Device Key<input name="device_key" value="__ESP32_DEVICE_KEY__"></label>
        <button id="submit" type="submit">Connect Wi-Fi And Start Setup</button>
      </form>
    </section>

    <section class="panel" id="qrPanel" style="display:none">
      <h2>Pair This Pi</h2>
      <p>Open the KahrabaIQ mobile app, tap <strong>Pair home</strong>, and scan this QR. The scanning user becomes the home admin.</p>
      <div class="qr" id="qrBox"><span class="wait">Generating QR...</span></div>
      <p>Manual pairing code:</p>
      <code id="manualCode">Waiting for QR payload...</code>
    </section>

    <section class="panel" id="sensorPanel" style="display:none">
      <h2>Waiting For Sensors</h2>
      <p id="sensorCopy">Home paired successfully. Waiting for sensors to connect to the Pi. Keep the ESP32 powered on and in setup mode.</p>
    </section>

    <section class="panel" id="statusPanel"><span id="statusText">Loading...</span></section>
  </main>
  <script>
    const submit = document.getElementById('submit');
    const statusText = document.getElementById('statusText');
    const wifiPanel = document.getElementById('wifiPanel');
    const qrPanel = document.getElementById('qrPanel');
    const sensorPanel = document.getElementById('sensorPanel');
    function setText(id, value, klass) { const el = document.getElementById(id); el.textContent = value; el.className = klass || ''; }
    function showStatus(data) {
      statusText.textContent = `${data.stage}: ${data.message || ''}${data.last_error ? ' - ' + data.last_error : ''}`;
      statusText.className = data.last_error ? 'error' : '';
      setText('wifiState', data.wifi_configured ? 'Connected' : (data.running ? 'Connecting' : 'Waiting'), data.wifi_configured ? 'done' : 'active');
      setText('pairState', data.paired ? 'Paired' : (data.pairing_payload ? 'Scan QR' : 'Waiting'), data.paired ? 'done' : (data.pairing_payload ? 'active' : 'wait'));
      setText('sensorState', data.esp32_provisioned ? 'Connected' : (data.paired ? 'Waiting for sensors' : 'Waiting for pairing'), data.esp32_provisioned ? 'done' : (data.paired ? 'active' : 'wait'));
      setText('dashState', data.setup_complete ? 'Opening' : 'Locked', data.setup_complete ? 'done' : 'wait');
      wifiPanel.style.display = data.wifi_configured ? 'none' : 'block';
      qrPanel.style.display = data.wifi_configured && !data.paired ? 'block' : 'none';
      sensorPanel.style.display = data.paired && !data.esp32_provisioned ? 'block' : 'none';
      if (data.pairing_payload) {
        document.getElementById('manualCode').textContent = data.pairing_payload;
        document.getElementById('qrBox').innerHTML = `<img alt="Pairing QR" src="/api/pairing/qr.svg?ts=${Date.now()}">`;
      }
      if (data.setup_complete) {
        statusText.textContent = 'Setup complete. The locked dashboard will open automatically.';
      }
    }
    async function refresh() {
      try {
        const response = await fetch('/api/status', { cache: 'no-store' });
        showStatus(await response.json());
      } catch (error) { statusText.textContent = error.message; statusText.className = 'error'; }
    }
    document.getElementById('wifiForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      submit.disabled = true;
      statusText.textContent = 'Connecting Wi-Fi. Keep this page open until the setup finishes.';
      const payload = Object.fromEntries(new FormData(event.target).entries());
      const response = await fetch('/api/provision', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok || data.success === false) {
        submit.disabled = false;
        statusText.textContent = data.message || 'Setup failed.';
        statusText.className = 'error';
      }
    });
    setInterval(refresh, 2000);
    refresh();
  </script>
</body>
</html>
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_ms() -> int:
    return int(time.time() * 1000)


def set_state(**updates: Any) -> None:
    with _state_lock:
        updates.setdefault("updated_at_iso", now_iso())
        _state.update(updates)


def get_state() -> dict[str, Any]:
    with _state_lock:
        state = dict(_state)
    state["marker_path"] = str(PROVISIONING_MARKER_PATH)
    state["home_wifi_interface"] = HOME_WIFI_INTERFACE
    state["setup_wifi_interface"] = SETUP_WIFI_INTERFACE
    state["setup_ap_ssid"] = SETUP_AP_SSID
    return state


def run_nmcli(args: list[str], timeout: int = 30, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["nmcli", *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as error:
        if check:
            raise RuntimeError("nmcli is required. Install and enable NetworkManager on the Pi.") from error
        return subprocess.CompletedProcess(command, 127, "", str(error))
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "nmcli command failed").strip()
        raise RuntimeError(f"{' '.join(command)}: {detail}")
    return result


def run_command(args: list[str], timeout: int = 15, check: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as error:
        if check:
            raise RuntimeError(f"{args[0]} is required.") from error
        return subprocess.CompletedProcess(args, 127, "", str(error))
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise RuntimeError(f"{' '.join(args)}: {detail}")
    return result


def api_request(method: str, path: str, **kwargs: Any) -> requests.Response:
    if not KAHRABAIQ_API_URL:
        raise RuntimeError("KAHRABAIQ_API_URL is required for QR pairing.")
    return requests.request(method, f"{KAHRABAIQ_API_URL}{path}", timeout=12, **kwargs)


def pi_headers() -> dict[str, str]:
    return {"X-Pi-Id": PI_ID, "X-Device-Token": PI_DEVICE_TOKEN}


def interface_ip(interface: str) -> str:
    result = run_command(["ip", "-4", "addr", "show", "dev", interface], timeout=5)
    for line in result.stdout.splitlines():
        text = line.strip()
        if text.startswith("inet "):
            return text.split()[1].split("/")[0]
    return ""


def wait_for_ip(interface: str, timeout_seconds: int) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        ip = interface_ip(interface)
        if ip:
            return ip
        time.sleep(2)
    raise RuntimeError(f"{interface} did not receive an IPv4 address.")


def normalize_base_url(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if text and not text.startswith(("http://", "https://")):
        text = f"http://{text}"
    return text


def gateway_from_nmcli(interface: str) -> str:
    result = run_nmcli(["-g", "IP4.GATEWAY", "device", "show", interface], timeout=10, check=False)
    for line in result.stdout.splitlines():
        gateway = line.strip()
        if gateway:
            return gateway
    return ""


def gateway_from_ip_route(interface: str) -> str:
    result = run_command(["ip", "route", "show", "dev", interface], timeout=10, check=False)
    for line in result.stdout.splitlines():
        parts = line.split()
        if "via" in parts:
            index = parts.index("via")
            if index + 1 < len(parts):
                return parts[index + 1]
    return ""


def detect_setup_gateway(interface: str) -> str:
    return gateway_from_nmcli(interface) or gateway_from_ip_route(interface)


def esp32_setup_base_url() -> str:
    if ESP32_SETUP_URL:
        return normalize_base_url(ESP32_SETUP_URL)
    gateway = detect_setup_gateway(SETUP_WIFI_INTERFACE)
    if not gateway:
        raise RuntimeError(
            f"Could not detect ESP32 setup gateway on {SETUP_WIFI_INTERFACE}. "
            "Make sure the Pi is connected to the ESP32 setup hotspot."
        )
    return f"http://{gateway}"


def start_setup_hotspot() -> None:
    set_state(stage="setup-hotspot", message=f"Starting {SETUP_AP_SSID} on {SETUP_WIFI_INTERFACE}.", last_error=None)
    run_nmcli(["connection", "down", SETUP_AP_CONNECTION], check=False)
    run_nmcli(["connection", "delete", SETUP_AP_CONNECTION], check=False)
    run_nmcli([
        "connection", "add", "type", "wifi", "ifname", SETUP_WIFI_INTERFACE,
        "con-name", SETUP_AP_CONNECTION, "autoconnect", "no", "ssid", SETUP_AP_SSID,
    ])
    run_nmcli([
        "connection", "modify", SETUP_AP_CONNECTION,
        "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
        "ipv4.method", "shared", "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", SETUP_AP_PASSWORD,
    ])
    run_nmcli(["connection", "up", SETUP_AP_CONNECTION], timeout=45)
    set_state(stage="wifi_setup", message=f"Setup hotspot active: {SETUP_AP_SSID}.")


def stop_setup_interface() -> None:
    set_state(stage="setup-interface-off", message=f"Turning off {SETUP_WIFI_INTERFACE}.")
    run_nmcli(["connection", "down", SETUP_AP_CONNECTION], timeout=20, check=False)
    run_nmcli(["device", "disconnect", SETUP_WIFI_INTERFACE], timeout=20, check=False)
    run_command(["ip", "link", "set", SETUP_WIFI_INTERFACE, "down"], timeout=10, check=False)


def connect_home_wifi(ssid: str, password: str) -> str:
    set_state(stage="home-wifi", message=f"Connecting {HOME_WIFI_INTERFACE} to home Wi-Fi.", last_error=None)
    run_nmcli(["device", "set", HOME_WIFI_INTERFACE, "managed", "yes"], check=False)
    run_nmcli(["device", "wifi", "rescan", "ifname", HOME_WIFI_INTERFACE], timeout=20, check=False)
    run_nmcli(["device", "wifi", "connect", ssid, "password", password, "ifname", HOME_WIFI_INTERFACE], timeout=HOME_WIFI_CONNECT_TIMEOUT_SECONDS)
    ip = wait_for_ip(HOME_WIFI_INTERFACE, HOME_WIFI_CONNECT_TIMEOUT_SECONDS)
    set_state(wifi_configured=True, internet_ready=True, stage="internet-ready", message=f"{HOME_WIFI_INTERFACE} connected to {ssid} at {ip}.")
    return ip


def create_pairing_token() -> dict[str, Any]:
    set_state(stage="pairing-token", message="Generating QR pairing token.")
    response = api_request(
        "POST",
        "/api/pairing/pi-token",
        headers=pi_headers(),
        json={"display_name": f"KahrabaIQ Pi {PI_ID}", "dashboard_version": AGENT_VERSION},
    )
    data = response.json()
    if not response.ok or data.get("success") is False:
        raise RuntimeError(data.get("detail") or data.get("message") or response.text)
    set_state(
        stage="waiting_for_pairing",
        message="Scan the QR code in the KahrabaIQ mobile app.",
        pairing_payload=data.get("qr_payload"),
        pairing_expires_at_ms=data.get("expires_at_ms"),
    )
    return data


def pairing_status() -> dict[str, Any]:
    response = api_request("GET", f"/api/pairing/pi-status/{PI_ID}")
    data = response.json()
    if not response.ok or data.get("success") is False:
        raise RuntimeError(data.get("detail") or data.get("message") or response.text)
    return data


def wait_for_pairing() -> str:
    create_pairing_token()
    deadline = time.time() + PAIRING_WAIT_TIMEOUT_SECONDS
    while time.time() < deadline:
        data = pairing_status()
        pi = data.get("pi") if isinstance(data.get("pi"), dict) else {}
        home_id = str(pi.get("home_id") or "")
        if pi.get("status") == "paired" and home_id:
            set_state(paired=True, home_id=home_id, stage="paired", message="Home paired successfully. Waiting for sensors to connect to the Pi.")
            return home_id
        expires_at_ms = int(get_state().get("pairing_expires_at_ms") or 0)
        if expires_at_ms and expires_at_ms - now_ms() < 60_000:
            create_pairing_token()
        time.sleep(PAIRING_POLL_SECONDS)
    raise RuntimeError("Pairing timed out. Refresh setup and scan the new QR code.")


def connect_esp32_setup_wifi() -> None:
    set_state(stage="esp32-wifi", message=f"Connecting {SETUP_WIFI_INTERFACE} to {ESP32_SETUP_SSID}.")
    run_nmcli(["connection", "down", SETUP_AP_CONNECTION], timeout=20, check=False)
    run_command(["ip", "link", "set", SETUP_WIFI_INTERFACE, "up"], timeout=10, check=False)
    run_nmcli(["device", "set", SETUP_WIFI_INTERFACE, "managed", "yes"], check=False)
    run_nmcli(["device", "wifi", "rescan", "ifname", SETUP_WIFI_INTERFACE], timeout=20, check=False)
    run_nmcli(["device", "wifi", "connect", ESP32_SETUP_SSID, "password", ESP32_SETUP_PASSWORD, "ifname", SETUP_WIFI_INTERFACE], timeout=ESP32_CONNECT_TIMEOUT_SECONDS)
    wait_for_ip(SETUP_WIFI_INTERFACE, ESP32_CONNECT_TIMEOUT_SECONDS)


def provision_esp32(home_id: str) -> dict[str, Any]:
    ssid = _setup_context.get("ssid", "")
    password = _setup_context.get("password", "")
    if not ssid or not password:
        raise RuntimeError("Wi-Fi credentials are no longer available. Re-enter Wi-Fi setup to provision ESP32.")
    if not home_id:
        raise RuntimeError("ESP32 provisioning requires a paired home_id.")
    connect_esp32_setup_wifi()
    setup_url = esp32_setup_base_url()
    body = {
        "ssid": ssid,
        "password": password,
        "pi_base_url": PI_LOCAL_BASE_URL,
        "pi_sensor_url": f"{PI_SENSOR_BASE_URL}/api/sensors/room1",
        "home_id": home_id,
        "pi_id": PI_ID,
        "device_id": _setup_context.get("device_id") or ESP32_DEVICE_ID,
        "device_key": _setup_context.get("device_key") or ESP32_DEVICE_KEY,
    }
    set_state(stage="esp32-provision", message=f"Sending Wi-Fi and home settings to ESP32 at {setup_url}.")
    response = requests.post(f"{setup_url}/provision", json=body, timeout=20)
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
    if not response.ok or data.get("success") is False:
        raise RuntimeError(data.get("message") or response.text)
    return {"setup_url": setup_url, "response": data}


def verify_esp32() -> dict[str, Any] | None:
    set_state(stage="esp32-verify", message="Checking ESP32 on home Wi-Fi.")
    deadline = time.time() + ESP32_VERIFY_TIMEOUT_SECONDS
    while time.time() < deadline:
        for base_url in ESP32_DISCOVERY_CANDIDATES:
            try:
                response = requests.get(f"{base_url.rstrip('/')}/status", timeout=3)
                data = response.json()
                if response.ok and data.get("wifi_connected"):
                    return {"base_url": base_url.rstrip("/"), "status": data}
            except Exception:
                pass
        time.sleep(3)
    return None


def write_marker(home_ip: str, esp32_result: dict[str, Any], esp32_verified: dict[str, Any] | None) -> None:
    state = get_state()
    PROVISIONING_MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    marker = {
        "setup_complete": True,
        "wifi_configured": True,
        "internet_ready": True,
        "paired": True,
        "pairing_source": "qr",
        "home_id": state.get("home_id"),
        "pi_id": PI_ID,
        "wifi_ssid": _setup_context.get("ssid"),
        "home_wifi_interface": HOME_WIFI_INTERFACE,
        "home_wifi_ip": home_ip,
        "setup_wifi_interface": SETUP_WIFI_INTERFACE,
        "esp32_device_id": _setup_context.get("device_id") or ESP32_DEVICE_ID,
        "esp32_provisioned": True,
        "esp32_verified": bool(esp32_verified),
        "esp32_verify": esp32_verified,
        "esp32_provision_response": esp32_result,
        "stage": "complete",
        "created_at_iso": now_iso(),
    }
    PROVISIONING_MARKER_PATH.write_text(json.dumps(marker, indent=2, sort_keys=True), encoding="utf-8")


def setup_flow(payload: dict[str, Any]) -> None:
    try:
        ssid = str(payload.get("ssid") or "").strip()
        password = str(payload.get("password") or "")
        if not ssid or not password:
            raise RuntimeError("ssid and password are required.")
        _setup_context.clear()
        _setup_context.update(
            {
                "ssid": ssid,
                "password": password,
                "device_id": str(payload.get("device_id") or ESP32_DEVICE_ID).strip(),
                "device_key": str(payload.get("device_key") or ESP32_DEVICE_KEY),
            }
        )
        set_state(running=True, stage="starting", message="Setup started.", last_error=None)
        home_ip = connect_home_wifi(ssid, password)
        home_id = wait_for_pairing()
        set_state(stage="esp32_waiting", message="Home paired successfully. Waiting for sensors to connect to the Pi.")
        esp32_result = provision_esp32(home_id)
        stop_setup_interface()
        esp32_verified = verify_esp32()
        write_marker(home_ip, esp32_result, esp32_verified)
        run_command(["systemctl", "stop", "kahrabaiq-setup-screen.service"], timeout=10, check=False)
        _setup_context.clear()
        set_state(
            running=False,
            paired=True,
            esp32_provisioned=True,
            esp32_verified=bool(esp32_verified),
            setup_complete=True,
            stage="complete",
            message="Setup complete. Dashboard services can start.",
            last_error=None,
        )
        _shutdown_requested.set()
    except Exception as error:
        set_state(running=False, stage="failed", message="Setup failed.", last_error=str(error))
        try:
            start_setup_hotspot()
        except Exception as hotspot_error:
            set_state(last_error=f"{error}; failed to restore setup hotspot: {hotspot_error}")


def delayed_exit() -> None:
    _shutdown_requested.wait()
    time.sleep(4)
    os._exit(0)


@app.get("/")
@app.get("/setup")
@app.get("/setup-screen")
def setup_page() -> Response:
    html = (
        SETUP_HTML.replace("__SETUP_AP_SSID__", SETUP_AP_SSID)
        .replace("__SETUP_AP_PASSWORD__", SETUP_AP_PASSWORD)
        .replace("__ESP32_DEVICE_ID__", ESP32_DEVICE_ID)
        .replace("__ESP32_DEVICE_KEY__", ESP32_DEVICE_KEY)
    )
    return Response(html, mimetype="text/html")


@app.get("/api/status")
def status() -> Any:
    return jsonify(get_state())


@app.get("/api/pairing/qr.svg")
def pairing_qr() -> Response:
    payload = str(get_state().get("pairing_payload") or "")
    if not payload:
        return Response("QR payload is not available yet.", status=404, mimetype="text/plain")
    if qrcode is None:
        return Response("QR renderer is unavailable. Use the manual pairing code.", status=503, mimetype="text/plain")
    image = qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    return Response(buffer.getvalue(), mimetype="image/svg+xml")


@app.get("/api/wifi/scan")
def wifi_scan() -> Any:
    try:
        run_nmcli(["device", "wifi", "rescan", "ifname", HOME_WIFI_INTERFACE], timeout=20, check=False)
        result = run_nmcli(["-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "ifname", HOME_WIFI_INTERFACE], check=False)
        networks = []
        for line in result.stdout.splitlines():
            parts = line.split(":")
            if parts and parts[0]:
                networks.append({"ssid": parts[0], "signal": parts[1] if len(parts) > 1 else "", "security": parts[2] if len(parts) > 2 else ""})
        return jsonify({"success": True, "networks": networks})
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


@app.post("/api/provision")
def provision_api() -> Any:
    global _setup_thread
    if get_state().get("running"):
        return jsonify({"success": False, "message": "Setup is already running."}), 409
    payload = request.get_json(silent=True) or {}
    _setup_thread = threading.Thread(target=setup_flow, args=(payload,), daemon=True, name="kahrabaiq-setup-flow")
    _setup_thread.start()
    return jsonify({"success": True, "message": "Setup started."})


def main() -> None:
    if PROVISIONING_MARKER_PATH.exists():
        stop_setup_interface()
        print(f"Provisioning marker exists: {PROVISIONING_MARKER_PATH}")
        return
    start_setup_hotspot()
    threading.Thread(target=delayed_exit, daemon=True).start()
    app.run(host="0.0.0.0", port=SETUP_PORT)


if __name__ == "__main__":
    main()
