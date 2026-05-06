from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, db

from predict_ai import predict


BASE_DIR = Path(__file__).resolve().parent

SERVICE_ACCOUNT_PATH = Path(
    os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH", BASE_DIR / "serviceAccountKey.json")
)

DATABASE_URL = os.environ.get(
    "FIREBASE_DATABASE_URL",
    "https://seniorproject-energy-default-rtdb.asia-southeast1.firebasedatabase.app",
)

DEFAULT_HOME_ID = os.environ.get("HOME_ID", "home_001")
BAHRAIN_TZ = timezone(timedelta(hours=3))


def now_ms() -> int:
    return int(time.time() * 1000)


def now_iso(timestamp_ms: int | None = None) -> str:
    return datetime.fromtimestamp((timestamp_ms or now_ms()) / 1000, tz=BAHRAIN_TZ).isoformat()


def initialize_firebase() -> None:
    if firebase_admin._apps:
        return

    if not SERVICE_ACCOUNT_PATH.exists():
        raise FileNotFoundError(f"Firebase service account not found: {SERVICE_ACCOUNT_PATH}")

    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})


def as_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(default)

    if isinstance(value, (int, float)):
        return float(value)

    return float(default)


def get_time_features(summary: dict[str, Any]) -> dict[str, Any]:
    timestamp_ms = summary.get("hour_start")

    if not isinstance(timestamp_ms, (int, float)):
        timestamp_ms = now_ms()

    bahrain_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=BAHRAIN_TZ)

    return {
        "hour_of_day": bahrain_time.hour,
        "day_of_week": bahrain_time.strftime("%A"),
        "is_weekend": bahrain_time.strftime("%A") in {"Friday", "Saturday"},
    }


def get_branch_energy(
    branches: dict[str, Any],
    breaker_id: str,
) -> dict[str, float]:
    branch = branches.get(breaker_id)
    if not isinstance(branch, dict):
        branch = {}

    return {
        "avg_power_W": as_number(branch.get("avg_power_W", branch.get("power_W"))),
        "peak_power_W": as_number(branch.get("peak_power_W", branch.get("power_W"))),
        "energy_kWh": as_number(
            branch.get("estimated_energy_kWh", branch.get("estimated_energy_kWh"))
        ),
    }


def calculate_occupancy_score(
    motion_count: Any,
    noise_count: Any,
    sample_count: Any,
) -> float:
    usable_sample_count = as_number(sample_count)
    denominator = usable_sample_count if 0 < usable_sample_count <= 1 else 48.0
    motion_score = as_number(motion_count) / denominator
    noise_score = as_number(noise_count) / denominator
    return round(min(1.0, max(motion_score, noise_score)), 4)


def build_ai_payload(home_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    home_ref = db.reference(f"/homes/{home_id}")
    backend_ref = db.reference(f"/homes/{home_id}/backend")

    latest_summary = backend_ref.child("latest_hourly_summary").get()
    if not isinstance(latest_summary, dict):
        latest_summary = {}

    dashboard_energy = backend_ref.child("dashboard/energy").get()
    if not isinstance(dashboard_energy, dict):
        dashboard_energy = {}

    dashboard_environment = backend_ref.child("dashboard/environment").get()
    if not isinstance(dashboard_environment, dict):
        dashboard_environment = {}

    current_state = backend_ref.child("current_state").get()
    if not isinstance(current_state, dict):
        current_state = {}

    occupancy = home_ref.child("occupancy/room1").get()
    if not isinstance(occupancy, dict):
        occupancy = {}

    energy = latest_summary.get("energy")
    if not isinstance(energy, dict):
        energy = dashboard_energy

    branches = energy.get("branches")
    if not isinstance(branches, dict):
        branches = {}

    switch_branch = get_branch_energy(branches, "breaker_01")
    ac_branch = get_branch_energy(branches, "breaker_02")

    using_hourly_summary = bool(latest_summary.get("hour_id"))

    sample_count = as_number(latest_summary.get("sample_count"), 1.0)
    if sample_count <= 0 and dashboard_environment:
        sample_count = 1.0

    motion_count = as_number(latest_summary.get("motion_count"))
    if not using_hourly_summary:
        motion_count = 1.0 if dashboard_environment.get("motion") == 1 else 0.0

    light_is_bright = dashboard_environment.get("light_status") == "Bright"
    occupancy_state = str(occupancy.get("state", "unknown"))
    occupancy_empty = occupancy_state in {"empty", "probably_empty"}
    derived_light_on = bool(occupancy.get("light_on")) or light_is_bright
    temperature = latest_summary.get("avg_temperature")
    humidity = latest_summary.get("avg_humidity")
    sound_raw = latest_summary.get("avg_sound_raw")

    if temperature is None:
        temperature = dashboard_environment.get("temperature")

    if humidity is None:
        humidity = dashboard_environment.get("humidity")

    if sound_raw is None:
        sound_raw = dashboard_environment.get("sound_raw")

    noise_count = (
        as_number(latest_summary.get("noise_count"))
        if using_hourly_summary
        else as_number(dashboard_environment.get("noise"))
    )

    payload = {
        **get_time_features(latest_summary),
        "sample_count": sample_count,
        "avg_temperature": temperature,
        "avg_humidity": humidity,
        "avg_sound_raw": sound_raw,
        "motion_count": motion_count,
        "bright_count": (
            as_number(latest_summary.get("bright_count"))
            if using_hourly_summary
            else 1.0 if light_is_bright else 0.0
        ),
        "smoke_count": (
            as_number(latest_summary.get("smoke_count"))
            if using_hourly_summary
            else as_number(dashboard_environment.get("smoke"))
        ),
        "noise_count": noise_count,
        "high_temp_count": (
            as_number(latest_summary.get("high_temp_count"))
            if using_hourly_summary
            else 1.0 if as_number(temperature) >= 27 else 0.0
        ),
        "occupancy_score": calculate_occupancy_score(
            motion_count,
            noise_count,
            sample_count,
        ),
        "occupancy_state": occupancy_state,
        "occupancy_confidence": as_number(occupancy.get("confidence")),
        "occupied": bool(occupancy.get("occupied")),
        "minutes_since_last_activity": as_number(occupancy.get("minutes_since_last_activity")),
        "motion_recent": bool(occupancy.get("motion_recent")),
        "sound_recent": bool(occupancy.get("sound_recent")),
        "sound_active": bool(occupancy.get("sound_active")),
        "light_on_while_empty": occupancy_empty and derived_light_on,
        "device_on_while_empty": occupancy_empty
        and as_number(energy.get("total_avg_power_W", energy.get("total_power_W"))) > 10,
        "empty_room_power_w": (
            as_number(energy.get("total_avg_power_W", energy.get("total_power_W")))
            if occupancy_empty
            else 0
        ),
        "switch_avg_power_W": switch_branch["avg_power_W"],
        "switch_peak_power_W": switch_branch["peak_power_W"],
        "switch_energy_kWh": switch_branch["energy_kWh"],
        "ac_avg_power_W": ac_branch["avg_power_W"],
        "ac_peak_power_W": ac_branch["peak_power_W"],
        "ac_energy_kWh": ac_branch["energy_kWh"],
        "total_avg_power_W": as_number(
            energy.get("total_avg_power_W", energy.get("total_power_W"))
        ),
        "total_peak_power_W": as_number(
            energy.get("total_peak_power_W", energy.get("total_power_W"))
        ),
        "total_energy_kWh": as_number(
            energy.get("total_estimated_energy_kWh", energy.get("total_energy_kWh"))
        ),
        "total_cost_BHD": as_number(
            energy.get("total_estimated_cost_BHD", energy.get("total_cost_BHD"))
        ),
        "tariff_BHD_per_kWh": as_number(energy.get("tariff_BHD_per_kWh"), 0.032),
    }

    source = {
        "input_source": "latest_hourly_summary" if using_hourly_summary else "dashboard_fallback",
        "latest_hourly_summary": latest_summary,
        "dashboard_energy": dashboard_energy,
        "dashboard_environment": dashboard_environment,
        "current_state": current_state,
        "occupancy": occupancy,
    }

    return payload, source


def make_control_suggestion(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    waste_detected = bool(result["waste_event"]["value"])
    anomaly = result["anomaly_label"]["value"]

    if (
        waste_detected
        and anomaly == "ac_running_while_empty"
        and payload.get("ac_avg_power_W", 0) > 0
    ):
        return {
            "device_id": "matter_ac_switch",
            "action": "turn_off",
            "priority": "high",
            "requires_user_approval": True,
            "reason": "AC Switch is active while occupancy appears low.",
        }

    if (
        waste_detected
        and anomaly in {"light_on_no_motion", "empty_room_power_active"}
        and payload.get("switch_avg_power_W", 0) > 0
    ):
        return {
            "device_id": "matter_socket_switch",
            "action": "turn_off",
            "priority": "medium",
            "requires_user_approval": True,
            "reason": "Socket Switch is active while the room appears empty.",
        }

    return None


def command_to_target_state(command: str) -> str:
    return "on" if command == "turn_on" else "off"


def device_display_name(device_id: str) -> str:
    return {
        "breaker_01": "Switch Breaker",
        "breaker_02": "AC Breaker",
        "matter_socket_switch": "Socket Switch",
        "matter_ac_switch": "AC Switch",
    }.get(device_id, device_id)


def read_control_mode(home_id: str) -> str:
    control_ref = db.reference(f"/homes/{home_id}/control")
    control = control_ref.get()
    if not isinstance(control, dict) or control.get("mode") not in {"manual", "assist", "auto"}:
        timestamp_ms = now_ms()
        control = {
            "mode": "assist",
            "updated_by": "system_default",
            "updated_at_ms": timestamp_ms,
            "updated_at_iso": now_iso(timestamp_ms),
        }
        control_ref.set(control)
    return str(control.get("mode", "assist"))


def default_automation(device_id: str) -> dict[str, Any]:
    if device_id == "breaker_01":
        return {
            "manual_allowed": True,
            "assist_allowed": True,
            "auto_allowed": True,
            "auto_actions": ["turn_off"],
            "requires_confirmation": False,
            "cooldown_ms": 5 * 60 * 1000,
        }
    if device_id == "breaker_02":
        return {
            "manual_allowed": True,
            "assist_allowed": True,
            "auto_allowed": True,
            "auto_actions": ["turn_on", "turn_off"],
            "requires_confirmation": False,
            "comfort_min_temp": 22,
            "comfort_max_temp": 25,
            "cooldown_ms": 10 * 60 * 1000,
        }
    if device_id == "matter_socket_switch":
        return {
            "manual_allowed": True,
            "assist_allowed": True,
            "auto_allowed": True,
            "auto_actions": ["turn_off"],
            "requires_confirmation": False,
            "cooldown_ms": 5 * 60 * 1000,
        }
    if device_id == "matter_ac_switch":
        return {
            "manual_allowed": True,
            "assist_allowed": True,
            "auto_allowed": True,
            "auto_actions": ["turn_on", "turn_off"],
            "requires_confirmation": False,
            "comfort_min_temp": 22,
            "comfort_max_temp": 25,
            "cooldown_ms": 10 * 60 * 1000,
        }
    return {
        "manual_allowed": True,
        "assist_allowed": False,
        "auto_allowed": False,
        "auto_actions": [],
        "requires_confirmation": True,
    }


def ensure_automation(home_id: str, device_id: str) -> dict[str, Any]:
    ref = db.reference(f"/homes/{home_id}/devices/{device_id}/automation")
    value = ref.get()
    if isinstance(value, dict):
        return value
    value = default_automation(device_id)
    ref.set(value)
    return value


def create_action_suggestion(home_id: str, suggestion: dict[str, Any]) -> None:
    active_ref = db.reference(f"/homes/{home_id}/action_suggestions/active")
    active = active_ref.get()
    if isinstance(active, dict):
        for item in active.values():
            if (
                isinstance(item, dict)
                and item.get("device_id") == suggestion["device_id"]
                and item.get("suggested_command") == suggestion["action"]
                and item.get("status") == "waiting_for_user"
            ):
                return

    timestamp_ms = now_ms()
    suggestion_id = f"sug_{timestamp_ms}"
    active_ref.child(suggestion_id).set(
        {
            "suggestion_id": suggestion_id,
            "home_id": home_id,
            "device_id": suggestion["device_id"],
            "device_name": device_display_name(suggestion["device_id"]),
            "suggested_command": suggestion["action"],
            "target_state": command_to_target_state(suggestion["action"]),
            "reason": suggestion["reason"],
            "source": "ai",
            "status": "waiting_for_user",
            "created_at_ms": timestamp_ms,
            "created_at_iso": now_iso(timestamp_ms),
            "actions": ["approve", "dismiss"],
        }
    )


def maybe_create_auto_command(home_id: str, suggestion: dict[str, Any]) -> bool:
    device_id = suggestion["device_id"]
    action = suggestion["action"]
    automation = ensure_automation(home_id, device_id)
    if automation.get("auto_allowed") is not True:
        return False
    if action not in automation.get("auto_actions", []):
        return False
    if automation.get("requires_confirmation") is True:
        return False
    if device_id in {"breaker_01", "matter_socket_switch"} and action != "turn_off":
        return False

    device = db.reference(f"/homes/{home_id}/devices/{device_id}").get()
    if not isinstance(device, dict):
        return False
    status = device.get("status") if isinstance(device.get("status"), dict) else {}
    local_online = device.get("local_online")
    if (
        status.get("online") is False
        or local_online is False
        or device.get("command_in_progress") is True
    ):
        return False

    current_state = db.reference(f"/homes/{home_id}/backend/current_state").get()
    esp32_sensors = db.reference(f"/homes/{home_id}/devices/esp32_01/sensors").get()
    if (
        isinstance(current_state, dict)
        and current_state.get("smoke") in {1, True, "1", "true"}
    ) or (
        isinstance(esp32_sensors, dict)
        and esp32_sensors.get("smoke") in {1, True, "1", "true"}
    ):
        return False

    automation_state = db.reference(f"/homes/{home_id}/automation_state/{device_id}").get()
    if isinstance(automation_state, dict):
        cooldown_until_ms = automation_state.get("cooldown_until_ms")
        if isinstance(cooldown_until_ms, (int, float)) and now_ms() < cooldown_until_ms:
            return False

    timestamp_ms = now_ms()
    command_id = f"cmd_{timestamp_ms}"
    device_name = device_display_name(device_id)
    command_record = {
        "command_id": command_id,
        "home_id": home_id,
        "device_id": device_id,
        "device_name": device_name,
        "command": action,
        "action": action,
        "target_state": command_to_target_state(action),
        "previous_state": str(device.get("state") or ("on" if status.get("switch") is True else "off")).lower(),
        "control_method": str(device.get("control_method") or ("tuya_cloud" if device_id.startswith("breaker_") else "")),
        "ha_entity_id": device.get("ha_entity_id"),
        "requested_by": "ai",
        "reason": suggestion["reason"],
        "status": "pending",
        "requested_at_ms": timestamp_ms,
        "requested_at_iso": now_iso(timestamp_ms),
        "sent_at_ms": None,
        "sent_at_iso": None,
        "confirmed_at_ms": None,
        "confirmed_at_iso": None,
        "failed_at_ms": None,
        "failed_at_iso": None,
        "timeout_at_ms": None,
        "timeout_at_iso": None,
        "result": {
            "success": None,
            "actual_state": None,
            "error_code": None,
            "user_message": None,
            "raw_error": None,
        },
        "retry_count": 0,
        "max_retries": 1,
    }
    root_ref = db.reference(f"/homes/{home_id}")
    root_ref.update(
        {
            f"commands/pending/{command_id}": command_record,
            f"commands/history/{command_id}": command_record,
            f"commands/latest_by_device/{device_id}": command_record,
            f"commands/{device_id}/latest": {
                **command_record,
                "created_at": timestamp_ms,
                "source": "ai",
            },
            f"devices/{device_id}/command_in_progress": True,
            f"devices/{device_id}/pending_command_id": command_id,
            f"devices/{device_id}/pending_target_state": command_to_target_state(action),
            f"devices/{device_id}/last_requested_state": command_to_target_state(action),
            f"devices/{device_id}/last_command_status": "pending",
            f"devices/{device_id}/last_command_message": "Automatic command accepted.",
        }
    )
    cooldown_ms = int(automation.get("cooldown_ms") or (10 * 60 * 1000 if device_id == "breaker_02" else 5 * 60 * 1000))
    log_id = f"auto_{timestamp_ms}"
    root_ref.update(
        {
            f"automation_state/{device_id}": {
                "last_auto_action": action,
                "last_auto_action_at_ms": timestamp_ms,
                "cooldown_until_ms": timestamp_ms + cooldown_ms,
            },
            f"automation_logs/{log_id}": {
                "log_id": log_id,
                "home_id": home_id,
                "device_id": device_id,
                "device_name": device_name,
                "command": action,
                "target_state": command_to_target_state(action),
                "reason": suggestion["reason"],
                "source": "ai",
                "command_id": command_id,
                "created_at_ms": timestamp_ms,
                "created_at_iso": now_iso(timestamp_ms),
            },
        }
    )
    return True


def apply_control_mode_behavior(home_id: str, result: dict[str, Any]) -> None:
    suggestion = result.get("control_suggestion")
    if not isinstance(suggestion, dict):
        return

    mode = read_control_mode(home_id)
    if mode == "manual":
        result["control_action_status"] = "recommendation_only"
        return
    if mode == "assist":
        create_action_suggestion(home_id, suggestion)
        result["control_action_status"] = "waiting_for_user"
        return
    if maybe_create_auto_command(home_id, suggestion):
        result["control_action_status"] = "automatic_command_created"
    else:
        result["control_action_status"] = "auto_not_allowed_recommendation_only"


def build_firebase_result(
    home_id: str,
    payload: dict[str, Any],
    prediction: dict[str, Any],
    input_source: str,
) -> dict[str, Any]:
    created_at = now_ms()
    control_suggestion = make_control_suggestion(prediction, payload)

    return {
        "home_id": home_id,
        "created_at": created_at,
        "model_name": prediction["model_name"],
        "model_version": prediction["model_version"],
        "input_source": input_source,
        "inputs": payload,
        "predictions": {
            "waste_event": prediction["waste_event"],
            "anomaly_label": prediction["anomaly_label"],
            "recommendation_type": prediction["recommendation_type"],
            "next_hour_total_energy_kWh": prediction["next_hour_total_energy_kWh"],
            "next_hour_total_cost_BHD": prediction["next_hour_total_cost_BHD"],
            "energy_efficiency_score": prediction["energy_efficiency_score"],
            "explanation": prediction["explanation"],
        },
        "control_suggestion": control_suggestion,
    }


def write_ai_result(home_id: str, result: dict[str, Any]) -> None:
    ai_ref = db.reference(f"/homes/{home_id}/backend/ai")
    prediction_id = f"prediction_{result['created_at']}"

    apply_control_mode_behavior(home_id, result)

    updates = {
        "latest_prediction": result,
        f"prediction_history/{prediction_id}": result,
    }

    ai_ref.update(updates)


def run(home_id: str, dry_run: bool) -> dict[str, Any]:
    initialize_firebase()

    payload, source = build_ai_payload(home_id)
    prediction = predict(payload)
    firebase_result = build_firebase_result(
        home_id,
        payload,
        prediction,
        source["input_source"],
    )

    if not dry_run:
        write_ai_result(home_id, firebase_result)

    return firebase_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read Firebase data, run Smart Energy AI, and write the result back."
    )
    parser.add_argument("--home-id", default=DEFAULT_HOME_ID)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the AI result without writing it to Firebase.",
    )
    args = parser.parse_args()

    result = run(args.home_id, args.dry_run)
    print(json.dumps(result, indent=2))

    if args.dry_run:
        print("\nDry run only. Firebase was not updated.")
    else:
        print(f"\nAI prediction written to /homes/{args.home_id}/backend/ai/latest_prediction")


if __name__ == "__main__":
    main()
