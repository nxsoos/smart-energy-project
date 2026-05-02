from datetime import datetime, timezone
from typing import Any

import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, jsonify, render_template, request


SERVICE_ACCOUNT_PATH = "serviceAccountKey.json"
DATABASE_URL = (
    "https://seniorproject-energy-default-rtdb.asia-southeast1."
    "firebasedatabase.app"
)

HOME_ID = "home_001"
ALLOWED_DEVICES = {"breaker_01", "breaker_02"}
ALLOWED_ACTIONS = {"turn_on", "turn_off"}

app = Flask(__name__)


def initialize_firebase() -> None:
    if firebase_admin._apps:
        return

    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(
        cred,
        {
            "databaseURL": DATABASE_URL,
        },
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def command_id(now: datetime) -> str:
    return f"cmd_{now.strftime('%Y%m%d_%H%M%S_%f')}"


def home_ref(path: str):
    return db.reference(f"/homes/{HOME_ID}/{path}")


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/latest")
def latest():
    try:
        esp32 = as_dict(home_ref("devices/esp32_01").get())
        devices = as_dict(home_ref("devices").get())

        return jsonify(
            {
                "success": True,
                "esp32": esp32,
                "devices": devices,
            }
        )
    except Exception as error:
        print(f"[DASHBOARD ERROR] {error}", flush=True)
        return (
            jsonify(
                {
                    "success": False,
                    "message": str(error),
                    "esp32": {},
                    "devices": {},
                }
            ),
            500,
        )


@app.post("/api/command")
def send_command():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "JSON body is required"}), 400

        device_id = str(data.get("device_id", "")).strip()
        action = str(data.get("action", "")).strip()

        if device_id not in ALLOWED_DEVICES:
            return jsonify({"success": False, "message": "Unsupported device_id"}), 400

        if action not in ALLOWED_ACTIONS:
            return jsonify({"success": False, "message": "Unsupported action"}), 400

        created = now_utc()
        cmd_id = command_id(created)
        command = {
            "command_id": cmd_id,
            "device_id": device_id,
            "action": action,
            "status": "pending",
            "source": "pi_dashboard",
            "created_at": created.isoformat(),
        }

        # firebase_tuya_cloud_controller.py watches this path.
        home_ref(f"commands/{device_id}/latest").set(command)

        # Mirror requested command-id path for dashboard-side traceability.
        home_ref(f"commands/{cmd_id}").set(command)

        print(
            f"[DASHBOARD] Command sent: {device_id} {action} {cmd_id}",
            flush=True,
        )
        return jsonify(
            {
                "success": True,
                "message": "Command sent",
                "command_id": cmd_id,
            }
        )
    except Exception as error:
        print(f"[DASHBOARD ERROR] {error}", flush=True)
        return jsonify({"success": False, "message": str(error)}), 500


if __name__ == "__main__":
    initialize_firebase()
    app.run(host="0.0.0.0", port=5001)
