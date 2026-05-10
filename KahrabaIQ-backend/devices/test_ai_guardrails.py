from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from main import apply_post_processing_rules
from aws_cloud_store import ai_alert_sk, ai_prediction_sk, ai_suggestion_sk, home_pk


def base_model_result() -> dict:
    return {
        "model_name": "test",
        "model_version": "guardrail",
        "waste_event": {"value": True, "confidence": 0.91},
        "anomaly_label": {"value": "light_on_no_motion", "confidence": 0.88},
        "recommendation_type": {"value": "turn_off_lights", "confidence": 0.86},
        "next_hour_total_energy_kWh": {"value": 0.05},
        "next_hour_total_cost_BHD": {"value": 0.0015},
        "energy_efficiency_score": 30,
        "explanation": "Model predicted waste.",
    }


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(name)


def run() -> None:
    low_power = apply_post_processing_rules(
        base_model_result(),
        {
            "breaker_data_fresh": True,
            "power_is_low": True,
            "avg_temperature": 25,
            "avg_humidity": 45,
            "avg_sound_raw": 10,
            "motion_count": 0,
            "bright_count": 0,
        },
    )
    check("low power forces no waste", low_power["waste_event"]["value"] is False)
    check("low power is normal", low_power["anomaly_label"]["value"] == "normal")

    stale_breaker = apply_post_processing_rules(
        base_model_result(),
        {
            "breaker_data_fresh": False,
            "power_is_low": False,
            "avg_temperature": 25,
            "avg_humidity": 45,
            "avg_sound_raw": 10,
            "motion_count": 0,
            "bright_count": 80,
        },
    )
    check("stale breaker needs data", stale_breaker["prediction_status"] == "needs_fresh_breaker_data")
    check("stale breaker forces no waste", stale_breaker["waste_event"]["value"] is False)

    smoke_alert = apply_post_processing_rules(
        base_model_result(),
        {
            "breaker_data_fresh": True,
            "power_is_low": False,
            "avg_temperature": 25,
            "avg_humidity": 45,
            "avg_sound_raw": 10,
            "motion_count": 1,
            "bright_count": 10,
            "smoke_count": 1,
            "occupancy_state": "occupied",
        },
    )
    check("smoke creates safety anomaly", smoke_alert["anomaly_label"]["value"] == "safety_smoke_gas_warning")
    check("smoke is not energy-first waste", smoke_alert["waste_event"]["value"] is False)

    check("home pk is canonical", home_pk("home_001") == "HOME#home_001")
    check("ai prediction sk is canonical", ai_prediction_sk(42) == "AI#PREDICTION#0000000000042")
    check("ai alert sk is canonical", ai_alert_sk(42, "gas") == "AI#ALERT#0000000000042#gas")
    check("ai suggestion sk is canonical", ai_suggestion_sk(42, "save") == "AI#SUGGESTION#0000000000042#save")


if __name__ == "__main__":
    run()
