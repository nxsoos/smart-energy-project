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
            "device_id": "breaker_02",
            "action": "turn_off",
            "priority": "high",
            "requires_user_approval": True,
            "reason": "AC power is active while occupancy appears low.",
        }

    if (
        waste_detected
        and anomaly == "light_on_no_motion"
        and payload.get("switch_avg_power_W", 0) > 0
    ):
        return {
            "device_id": "breaker_01",
            "action": "turn_off",
            "priority": "medium",
            "requires_user_approval": True,
            "reason": "Switch Breaker is active while motion appears low.",
        }

    return None


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
