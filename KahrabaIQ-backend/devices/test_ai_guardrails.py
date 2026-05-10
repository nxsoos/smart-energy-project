from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from main import apply_post_processing_rules
from aws_cloud_store import ai_alert_sk, ai_prediction_sk, ai_suggestion_sk, home_pk
from api_server import (
    AiScenarioPredictRequest,
    ai_notification,
    build_ai,
    build_ai_payload_from_scenario,
    dashboard_smoke_context,
    apply_scenario_next_hour_fallback,
    run_immediate_safety_checks,
    run_lightweight_anomaly_checks,
    summary_energy_value,
    summary_power_value,
    now_ms,
)


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

    pi_hourly_summary = {
        "startAtMs": 1710000000000,
        "totalEnergyKwh": 0.42,
        "breakerSummaries": {
            "breaker_01": {"avgPowerW": 20, "peakPowerW": 40, "energyDeltaKwh": 0.08},
            "breaker_02": {"avgPowerW": 120, "peakPowerW": 300, "energyDeltaKwh": 0.34},
        },
    }
    check("pi hourly energy is parsed", summary_energy_value(pi_hourly_summary) == 0.42)
    check("pi hourly power is parsed", summary_power_value(pi_hourly_summary) == 140)
    nested_daily_summary = {"energy": {"total_estimated_energy_kWh": 2.4}}
    check("nested summary energy is parsed", summary_energy_value(nested_daily_summary) == 2.4)

    smoke_context = dashboard_smoke_context(
        {"smoke": False, "smoke_text": "Clear", "sensor_timestamp_ms": now_ms()},
        {"smoke_state": {"status": "clear"}},
    )
    stale_smoke_ai = build_ai(
        {
            "ai_latest": {},
            "backend_latest_prediction": {},
            "backend_dashboard_ai": {},
            "canonical_ai_latest": {
                "created_at_ms": now_ms(),
                "ai_status_summary": "Gas or smoke detected: Check the room immediately.",
                "explanation": "Gas or smoke detected.",
            },
        },
        smoke_context=smoke_context,
    )
    check("clear smoke suppresses stale smoke AI", stale_smoke_ai["prediction_status"] in {"stale_ai_result", "needs_fresh_sensor_data"})

    notification = ai_notification(
        "home_001",
        "critical",
        "safety",
        "Gas or smoke detected",
        "Check the room immediately.",
        confidence=1.0,
        explanation="Smoke count was above zero.",
    )
    for key in ["id", "home_id", "severity", "category", "title", "message", "created_at", "acknowledged", "source", "confidence", "explanation"]:
        check(f"notification has {key}", key in notification)

    safety_alerts = run_immediate_safety_checks(
        "home_001",
        {
            "smoke_count": 1,
            "sensor_data_fresh": True,
            "breaker_data_fresh": True,
            "failed_command_count_last_hour": 0,
            "occupancy_state": "occupied",
            "total_power_for_guardrails_W": 0,
        },
    )
    check("smoke safety alert is critical", safety_alerts[0]["severity"] == "critical")

    routine_alerts = run_lightweight_anomaly_checks(
        "home_001",
        {
            "total_energy_kWh": 0.8,
            "same_hour_energy_avg": 0.2,
            "same_hour_energy_std": 0.05,
            "total_power_for_guardrails_W": 350,
            "recent_power_avg": 80,
            "recent_power_std": 20,
            "outside_routine_score": 1,
            "hour_of_day": 2,
            "ac_live_power_W": 200,
            "device_left_on_without_motion_minutes": 45,
        },
    )
    check("routine checks create anomalies", any(item["category"] == "anomaly" for item in routine_alerts))
    check("routine checks create suggestions", any(item["category"] == "recommendation" for item in routine_alerts))

    scenario_request = AiScenarioPredictRequest(
        scenario_id="smoke_demo",
        scenario_name="Smoke Demo",
        room={"temperature": 29, "humidity": 55, "smokeStatus": "Smoke/Gas", "motion": True},
        energy={"power": 420, "energyToday": 0.4, "costToday": 0.012},
        devices={"breaker_01": {"isOn": True, "power": 180}, "breaker_02": {"isOn": False, "power": 0}},
        occupancy={"occupied": True, "state": "occupied"},
        recent_history={"sensor_staleness_seconds": 0, "breaker_staleness_seconds": 0},
    )
    scenario_payload, scenario_source = build_ai_payload_from_scenario("home_001", scenario_request)
    check("scenario input source is demo", scenario_source == "demo_scenario:smoke_demo")
    check("scenario smoke maps to smoke count", scenario_payload["smoke_count"] == 1.0)
    check("scenario does not require live store", scenario_payload["latest_control_mode"] == "demo")

    scenario_result = {"next_hour_energy": 0, "next_hour_cost": 0, "predictions": {}}
    apply_scenario_next_hour_fallback(
        scenario_result,
        {"total_power_for_guardrails_W": 1280, "tariff_BHD_per_kWh": 0.032},
    )
    check("scenario fallback predicts kWh from power", scenario_result["next_hour_energy"] == 1.28)
    check("scenario fallback predicts cost from tariff", scenario_result["next_hour_cost"] == 0.04096)


if __name__ == "__main__":
    run()
