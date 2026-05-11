from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request


load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")
load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
load_dotenv()

HOME_ID = os.environ.get("HOME_ID", "home_001")
PI_ID = os.environ.get("PI_ID", "pi_local_001")
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
ESP32_DISCOVERY_CANDIDATES = [
    item.strip().rstrip("/")
    for item in os.environ.get("ESP32_DISCOVERY_CANDIDATES", "http://kahrabaiq-esp32.local").split(",")
    if item.strip()
]
ESP32_CONNECT_TIMEOUT_SECONDS = int(os.environ.get("ESP32_CONNECT_TIMEOUT_SECONDS", "45"))
HOME_WIFI_CONNECT_TIMEOUT_SECONDS = int(os.environ.get("HOME_WIFI_CONNECT_TIMEOUT_SECONDS", "60"))
ESP32_VERIFY_TIMEOUT_SECONDS = int(os.environ.get("ESP32_VERIFY_TIMEOUT_SECONDS", "30"))

PI_SENSOR_BASE_URL = os.environ.get("PI_SENSOR_BASE_URL", "http://kahrabaiq-pi.local:5000").rstrip("/")
PI_LOCAL_BASE_URL = os.environ.get("PI_LOCAL_BASE_URL", "http://kahrabaiq-pi.local:5001").rstrip("/")
PROVISIONING_MARKER_PATH = Path(os.environ.get("PROVISIONING_MARKER_PATH", "/var/lib/kahrabaiq/provisioned.json"))

app = Flask(__name__)
_state_lock = threading.RLock()
_state: dict[str, Any] = {
    "provisioning": False,
    "provisioned": PROVISIONING_MARKER_PATH.exists(),
    "stage": "ready",
    "message": "Waiting for setup.",
    "last_error": None,
}
_shutdown_requested = threading.Event()


SETUP_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KahrabaIQ Setup</title>
  <style>
    :root { color-scheme: dark; --bg:#050816; --panel:#111827; --text:#f8fafc; --muted:#94a3b8; --cyan:#22d3ee; --red:#fb7185; --green:#34d399; }
    * { box-sizing: border-box; }
    body { margin:0; min-height:100vh; display:grid; place-items:center; padding:24px; background:radial-gradient(circle at top,#164e63,var(--bg) 46%); color:var(--text); font-family:Inter,system-ui,sans-serif; }
    main { width:min(720px,100%); background:rgba(17,24,39,.94); border:1px solid rgba(34,211,238,.35); border-radius:24px; padding:28px; box-shadow:0 30px 90px rgba(0,0,0,.4); }
    h1 { margin:0 0 8px; font-size:clamp(32px,6vw,56px); }
    p { color:var(--muted); line-height:1.5; }
    label { display:block; margin-top:16px; color:var(--muted); font-weight:700; }
    input { width:100%; margin-top:8px; border:1px solid rgba(148,163,184,.4); border-radius:14px; padding:14px 16px; background:#020617; color:var(--text); font-size:16px; }
    button { width:100%; margin-top:22px; border:0; border-radius:999px; padding:15px 18px; background:linear-gradient(135deg,#06b6d4,#22c55e); color:#001018; font-weight:900; font-size:16px; }
    button:disabled { opacity:.55; }
    .status { margin-top:18px; padding:16px; border-radius:16px; background:#020617; color:var(--muted); }
    .error { color:var(--red); } .ok { color:var(--green); }
  </style>
</head>
<body>
  <main>
    <h1>KahrabaIQ Setup</h1>
    <p>Connect the Pi and ESP32 to the same home Wi-Fi before the dashboard starts. The setup hotspot will turn off after success.</p>
    <form id="form">
      <label>Home Wi-Fi SSID<input name="ssid" autocomplete="off" required></label>
      <label>Home Wi-Fi Password<input name="password" type="password" required></label>
      <label>Home ID<input name="home_id" value="__HOME_ID__" required></label>
      <label>Pi ID<input name="pi_id" value="__PI_ID__" required></label>
      <label>ESP32 Device ID<input name="device_id" value="__ESP32_DEVICE_ID__" required></label>
      <label>ESP32 Device Key<input name="device_key" value="__ESP32_DEVICE_KEY__" required></label>
      <button id="submit" type="submit">Provision Pi and ESP32</button>
    </form>
    <div class="status" id="status">Ready. Keep the ESP32 in setup mode.</div>
  </main>
  <script>
    const statusNode = document.getElementById('status');
    const submit = document.getElementById('submit');
    function show(text, klass = '') { statusNode.className = `status ${klass}`; statusNode.textContent = text; }
    async function refresh() {
      try {
        const response = await fetch('/api/status', { cache: 'no-store' });
        const data = await response.json();
        show(`${data.stage}: ${data.message}`, data.last_error ? 'error' : (data.provisioned ? 'ok' : ''));
        if (data.provisioned) submit.disabled = true;
      } catch (_) {}
    }
    document.getElementById('form').addEventListener('submit', async (event) => {
      event.preventDefault();
      submit.disabled = true;
      show('Provisioning started. This setup Wi-Fi may disconnect while the Pi configures the ESP32.');
      const payload = Object.fromEntries(new FormData(event.target).entries());
      const response = await fetch('/api/provision', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok || data.success === false) {
        submit.disabled = false;
        show(data.message || 'Provisioning failed.', 'error');
      } else {
        show('Provisioning complete. The setup hotspot will turn off and the dashboard will start.', 'ok');
      }
    });
    setInterval(refresh, 2000);
    refresh();
  </script>
</body>
</html>
"""


def set_state(**updates: Any) -> None:
    with _state_lock:
        _state.update(updates)


def get_state() -> dict[str, Any]:
    with _state_lock:
        state = dict(_state)
    state["marker_path"] = str(PROVISIONING_MARKER_PATH)
    state["home_wifi_interface"] = HOME_WIFI_INTERFACE
    state["setup_wifi_interface"] = SETUP_WIFI_INTERFACE
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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        "connection",
        "add",
        "type",
        "wifi",
        "ifname",
        SETUP_WIFI_INTERFACE,
        "con-name",
        SETUP_AP_CONNECTION,
        "autoconnect",
        "no",
        "ssid",
        SETUP_AP_SSID,
    ])
    run_nmcli([
        "connection",
        "modify",
        SETUP_AP_CONNECTION,
        "802-11-wireless.mode",
        "ap",
        "802-11-wireless.band",
        "bg",
        "ipv4.method",
        "shared",
        "wifi-sec.key-mgmt",
        "wpa-psk",
        "wifi-sec.psk",
        SETUP_AP_PASSWORD,
    ])
    run_nmcli(["connection", "up", SETUP_AP_CONNECTION], timeout=45)
    set_state(stage="setup-ready", message=f"Setup hotspot active: {SETUP_AP_SSID}.")


def stop_setup_interface() -> None:
    set_state(stage="setup-interface-off", message=f"Turning off {SETUP_WIFI_INTERFACE}.")
    run_nmcli(["connection", "down", SETUP_AP_CONNECTION], timeout=20, check=False)
    run_nmcli(["device", "disconnect", SETUP_WIFI_INTERFACE], timeout=20, check=False)
    run_command(["ip", "link", "set", SETUP_WIFI_INTERFACE, "down"], timeout=10, check=False)


def connect_home_wifi(ssid: str, password: str) -> str:
    set_state(stage="home-wifi", message=f"Connecting {HOME_WIFI_INTERFACE} to home Wi-Fi.", last_error=None)
    run_nmcli(["device", "set", HOME_WIFI_INTERFACE, "managed", "yes"], check=False)
    run_nmcli(["device", "wifi", "rescan", "ifname", HOME_WIFI_INTERFACE], timeout=20, check=False)
    run_nmcli([
        "device",
        "wifi",
        "connect",
        ssid,
        "password",
        password,
        "ifname",
        HOME_WIFI_INTERFACE,
    ], timeout=HOME_WIFI_CONNECT_TIMEOUT_SECONDS)
    ip = wait_for_ip(HOME_WIFI_INTERFACE, HOME_WIFI_CONNECT_TIMEOUT_SECONDS)
    set_state(stage="home-wifi", message=f"{HOME_WIFI_INTERFACE} connected to {ssid} at {ip}.")
    return ip


def connect_esp32_setup_wifi() -> None:
    set_state(stage="esp32-wifi", message=f"Connecting {SETUP_WIFI_INTERFACE} to {ESP32_SETUP_SSID}.")
    run_nmcli(["connection", "down", SETUP_AP_CONNECTION], timeout=20, check=False)
    run_command(["ip", "link", "set", SETUP_WIFI_INTERFACE, "up"], timeout=10, check=False)
    run_nmcli(["device", "set", SETUP_WIFI_INTERFACE, "managed", "yes"], check=False)
    run_nmcli(["device", "wifi", "rescan", "ifname", SETUP_WIFI_INTERFACE], timeout=20, check=False)
    run_nmcli([
        "device",
        "wifi",
        "connect",
        ESP32_SETUP_SSID,
        "password",
        ESP32_SETUP_PASSWORD,
        "ifname",
        SETUP_WIFI_INTERFACE,
    ], timeout=ESP32_CONNECT_TIMEOUT_SECONDS)
    wait_for_ip(SETUP_WIFI_INTERFACE, ESP32_CONNECT_TIMEOUT_SECONDS)


def provision_esp32(payload: dict[str, str]) -> dict[str, Any]:
    connect_esp32_setup_wifi()
    setup_url = esp32_setup_base_url()
    body = {
        "ssid": payload["ssid"],
        "password": payload["password"],
        "pi_base_url": PI_LOCAL_BASE_URL,
        "pi_sensor_url": f"{PI_SENSOR_BASE_URL}/api/sensors/room1",
        "home_id": payload.get("home_id") or HOME_ID,
        "pi_id": payload.get("pi_id") or PI_ID,
        "device_id": payload.get("device_id") or ESP32_DEVICE_ID,
        "device_key": payload.get("device_key") or ESP32_DEVICE_KEY,
    }
    set_state(stage="esp32-provision", message=f"Sending Wi-Fi credentials to ESP32 at {setup_url}.")
    response = requests.post(f"{setup_url}/provision", json=body, timeout=20)
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
    if not response.ok or data.get("success") is False:
        raise RuntimeError(data.get("message") or response.text)
    return {"setup_url": setup_url, "response": data}


def verify_esp32() -> dict[str, Any] | None:
    set_state(stage="esp32-verify", message="Checking ESP32 on home Wi-Fi.")
    deadline = time.time() + ESP32_VERIFY_TIMEOUT_SECONDS
    candidates = ESP32_DISCOVERY_CANDIDATES
    while time.time() < deadline:
        for base_url in candidates:
            try:
                response = requests.get(f"{base_url.rstrip('/')}/status", timeout=3)
                data = response.json()
                if response.ok and data.get("wifi_connected"):
                    return {"base_url": base_url.rstrip("/"), "status": data}
            except Exception:
                pass
        time.sleep(3)
    return None


def write_marker(payload: dict[str, str], home_ip: str, esp32_result: dict[str, Any], esp32_verified: dict[str, Any] | None) -> None:
    PROVISIONING_MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    marker = {
        "provisioned": True,
        "home_id": payload.get("home_id") or HOME_ID,
        "pi_id": payload.get("pi_id") or PI_ID,
        "wifi_ssid": payload["ssid"],
        "home_wifi_interface": HOME_WIFI_INTERFACE,
        "home_wifi_ip": home_ip,
        "setup_wifi_interface": SETUP_WIFI_INTERFACE,
        "esp32_device_id": payload.get("device_id") or ESP32_DEVICE_ID,
        "esp32_provisioned": True,
        "esp32_verified": bool(esp32_verified),
        "esp32_verify": esp32_verified,
        "esp32_provision_response": esp32_result,
        "created_at_iso": now_iso(),
    }
    PROVISIONING_MARKER_PATH.write_text(json.dumps(marker, indent=2, sort_keys=True), encoding="utf-8")


def provision(payload: dict[str, Any]) -> dict[str, Any]:
    required = ["ssid", "password"]
    missing = [key for key in required if not str(payload.get(key) or "").strip()]
    if missing:
        raise RuntimeError(f"Missing required fields: {', '.join(missing)}")
    safe_payload = {key: str(value or "").strip() for key, value in payload.items()}
    safe_payload["password"] = str(payload.get("password") or "")
    safe_payload["device_key"] = str(payload.get("device_key") or ESP32_DEVICE_KEY)

    set_state(provisioning=True, stage="starting", message="Provisioning started.", last_error=None)
    try:
        home_ip = connect_home_wifi(safe_payload["ssid"], safe_payload["password"])
        esp32_result = provision_esp32(safe_payload)
        stop_setup_interface()
        esp32_verified = verify_esp32()
        write_marker(safe_payload, home_ip, esp32_result, esp32_verified)
        set_state(
            provisioning=False,
            provisioned=True,
            stage="complete",
            message="Provisioning complete. Dashboard services can start.",
            last_error=None,
        )
        _shutdown_requested.set()
        return {"success": True, "esp32_verified": bool(esp32_verified)}
    except Exception as error:
        set_state(provisioning=False, stage="failed", message="Provisioning failed.", last_error=str(error))
        try:
            start_setup_hotspot()
        except Exception as hotspot_error:
            set_state(last_error=f"{error}; failed to restore setup hotspot: {hotspot_error}")
        raise


def delayed_exit() -> None:
    _shutdown_requested.wait()
    time.sleep(4)
    os._exit(0)


@app.get("/")
@app.get("/setup")
def setup_page() -> Response:
    html = (
        SETUP_HTML.replace("__HOME_ID__", HOME_ID)
        .replace("__PI_ID__", PI_ID)
        .replace("__ESP32_DEVICE_ID__", ESP32_DEVICE_ID)
        .replace("__ESP32_DEVICE_KEY__", ESP32_DEVICE_KEY)
    )
    return Response(html, mimetype="text/html")


@app.get("/api/status")
def status() -> Any:
    return jsonify(get_state())


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
    if get_state().get("provisioning"):
        return jsonify({"success": False, "message": "Provisioning is already running."}), 409
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(provision(payload))
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 500


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
