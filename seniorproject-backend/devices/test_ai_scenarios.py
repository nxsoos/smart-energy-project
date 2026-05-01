from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import firebase_admin
from firebase_admin import credentials, db


BASE_DIR = Path(__file__).resolve().parent
SERVICE_ACCOUNT_PATH = BASE_DIR / "serviceAccountKey.json"
DATABASE_URL = os.environ.get(
    "FIREBASE_DATABASE_URL",
    "https://seniorproject-energy-default-rtdb.asia-southeast1.firebasedatabase.app",
)
DEFAULT_AI_SERVICE_URL = "https://smart-energy-ai-237804589333.asia-southeast1.run.app"
TEST_HOME_ID = "home_test"
TEST_HOME_PATH = f"/homes/{TEST_HOME_ID}"
BAHRAIN_TZ = timezone(timedelta(hours=3))


def now_ms() -> int:
    return int(time.time() * 1000)


def initialize_firebase() -> None:
    if firebase_admin._apps:
        return

    if not SERVICE_ACCOUNT_PATH.exists():
        raise FileNotFoundError(
            f"Firebase service account not found: {SERVICE_ACCOUNT_PATH}. "
            "For local scenario testing, place serviceAccountKey.json in devices/."
        )

    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})


def bahrain_timestamp_for_hour(hour: int) -> int:
    current = datetime.now(BAHRAIN_TZ)
    scenario_time = current.replace(hour=hour, minute=0, second=0, microsecond=0)
    return int(scenario_time.timestamp() * 1000)


def day_name_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=BAHRAIN_TZ).strftime("%A")


def is_weekend_from_ms(timestamp_ms: int) -> bool:
    return day_name_from_ms(timestamp_ms) in {"Friday", "Saturday"}


def build_home_payload(
    *,
    scenario_name: str,
    scenario_description: str,
    timestamp_ms: int,
    motion: int | None,
    light_status: str | None,
    temperature: float | None,
    humidity: float | None,
    sound_raw: int | None,
    noise: int | None,
    smoke: int | None,
    switch_power_w: float,
    ac_power_w: float,
    switch_on: bool,
    ac_on: bool,
    expected: dict[str, Any],
    omit_environment_fields: list[str] | None = None,
    room_devices: list[dict[str, Any]] | None = None,
    ac_setpoint_c: float | None = None,
    ac_mode: str = "cool",
    ac_fan_speed: str = "auto",
    room_area_m2: float = 16.0,
    occupancy_count: int | None = None,
) -> dict[str, Any]:
    written_at = now_ms()
    omit_environment_fields = omit_environment_fields or []
    occupancy_count = occupancy_count if occupancy_count is not None else (1 if motion == 1 else 0)
    room_devices = room_devices or [
        {
            "name": "Room lighting and small devices",
            "category": "mixed_load",
            "power_w": switch_power_w,
            "breaker_id": "breaker_01",
            "is_on": switch_on,
        },
        {
            "name": "Split AC unit",
            "category": "air_conditioner",
            "power_w": ac_power_w,
            "breaker_id": "breaker_02",
            "is_on": ac_on,
            "setpoint_c": ac_setpoint_c,
            "mode": ac_mode,
            "fan_speed": ac_fan_speed,
        },
    ]
    switch_room_devices = [
        device for device in room_devices if device.get("breaker_id") == "breaker_01"
    ]
    ac_room_devices = [
        device for device in room_devices if device.get("breaker_id") == "breaker_02"
    ]
    ac_details = {
        "type": "split_ac",
        "capacity_btu": 18000,
        "mode": ac_mode,
        "fan_speed": ac_fan_speed,
        "setpoint_c": ac_setpoint_c,
        "measured_power_w": ac_power_w,
        "estimated_current_a": round(ac_power_w / 230, 3) if ac_power_w else 0,
        "room_area_m2": room_area_m2,
    }

    environment = {
        "updated_at": written_at,
        "temperature": temperature,
        "humidity": humidity,
        "sound_raw": sound_raw,
        "noise": noise,
        "noise_text": "Noise" if noise == 1 else "Quiet",
        "motion": motion,
        "light_status": light_status,
        "smoke": smoke,
        "occupancy_state": "occupied" if motion == 1 else "possibly_empty",
        "occupancy_count": occupancy_count,
        "waste_risk": "possible" if motion == 0 and (switch_power_w + ac_power_w) > 20 else "low",
        "recommendation": "Scenario test data",
        "last_log_id": f"scenario_{scenario_name}_{written_at}",
    }

    for field in omit_environment_fields:
        environment.pop(field, None)

    total_power_w = round(switch_power_w + ac_power_w, 2)
    switch_energy_kwh = round(switch_power_w / 1000, 6)
    ac_energy_kwh = round(ac_power_w / 1000, 6)
    total_energy_kwh = round(switch_energy_kwh + ac_energy_kwh, 6)
    total_cost_bhd = round(total_energy_kwh * 0.032, 6)
    current_a = round(total_power_w / 230, 3) if total_power_w else 0

    branches = {
        "breaker_01": {
            "name": "Switch Breaker",
            "power_W": switch_power_w,
            "voltage_V": 230,
            "current_A": round(switch_power_w / 230, 3) if switch_power_w else 0,
            "estimated_energy_kWh": switch_energy_kwh,
            "estimated_cost_BHD": round(switch_energy_kwh * 0.032, 6),
            "switch": switch_on,
            "relay_status": "on" if switch_on else "off",
            "last_seen_at": written_at,
            "connected_devices": switch_room_devices,
        },
        "breaker_02": {
            "name": "AC Breaker",
            "power_W": ac_power_w,
            "voltage_V": 230,
            "current_A": round(ac_power_w / 230, 3) if ac_power_w else 0,
            "estimated_energy_kWh": ac_energy_kwh,
            "estimated_cost_BHD": round(ac_energy_kwh * 0.032, 6),
            "switch": ac_on,
            "relay_status": "on" if ac_on else "off",
            "last_seen_at": written_at,
            "connected_devices": ac_room_devices,
            "ac_details": ac_details,
        },
    }

    dashboard_energy = {
        "updated_at": written_at,
        "total_power_W": total_power_w,
        "total_avg_power_W": total_power_w,
        "total_peak_power_W": total_power_w,
        "total_estimated_energy_kWh": total_energy_kwh,
        "total_estimated_cost_BHD": total_cost_bhd,
        "tariff_BHD_per_kWh": 0.032,
        "branches": branches,
    }

    latest_hourly_summary = {
        "hour_id": datetime.fromtimestamp(timestamp_ms / 1000, tz=BAHRAIN_TZ).strftime(
            "%Y-%m-%d_%H"
        ),
        "hour_start": timestamp_ms,
        "hour_end": timestamp_ms + (60 * 60 * 1000) - 1,
        "sample_count": 60,
        "avg_temperature": temperature,
        "avg_humidity": humidity,
        "avg_sound_raw": sound_raw,
        "motion_count": 35 if motion == 1 else 0,
        "bright_count": 50 if light_status == "Bright" else 5,
        "smoke_count": 1 if smoke == 1 else 0,
        "noise_count": 10 if noise == 1 else 0,
        "high_temp_count": 40 if temperature is not None and temperature >= 27 else 0,
        "energy": {
            "total_avg_power_W": total_power_w,
            "total_peak_power_W": total_power_w,
            "total_estimated_energy_kWh": total_energy_kwh,
            "total_estimated_cost_BHD": total_cost_bhd,
            "tariff_BHD_per_kWh": 0.032,
            "branches": {
                "breaker_01": {
                    "name": "Switch Breaker",
                    "avg_power_W": switch_power_w,
                    "peak_power_W": switch_power_w,
                    "min_power_W": switch_power_w,
                    "sample_count": 60,
                    "estimated_energy_kWh": switch_energy_kwh,
                    "estimated_cost_BHD": round(switch_energy_kwh * 0.032, 6),
                },
                "breaker_02": {
                    "name": "AC Breaker",
                    "avg_power_W": ac_power_w,
                    "peak_power_W": ac_power_w,
                    "min_power_W": ac_power_w,
                    "sample_count": 60,
                    "estimated_energy_kWh": ac_energy_kwh,
                    "estimated_cost_BHD": round(ac_energy_kwh * 0.032, 6),
                },
            },
        },
        "created_at": written_at,
        "status": "completed",
    }

    if omit_environment_fields:
        # Force dashboard fallback for missing-sensor tests, so omitted fields
        # are visible to the AI instead of hidden by complete hourly values.
        latest_hourly_summary = {}

    ai_efficiency_score = expected.get("expected_efficiency_score")
    if ai_efficiency_score is None:
        ai_efficiency_score = 55 if expected.get("expected_energy_waste") else 88
    ai_recommendation_type = expected.get("expected_recommendation_type", "none")
    ai_explanation = expected.get("expected_description", "Demo scenario data.")
    ai_energy_waste = bool(expected.get("expected_energy_waste"))
    ai_abnormal = expected.get("expected_abnormal_usage") != "normal"

    return {
        "scenario": {
            "scenario_id": scenario_name,
            "scenario_name": scenario_name.replace("_", " ").title(),
            "scenario_description": scenario_description,
            "timestamp": timestamp_ms,
        },
        "device_control_enabled": False,
        "current_power_w": total_power_w,
        "energy_today_kwh": total_energy_kwh,
        "total_energy_kwh": total_energy_kwh,
        "voltage_v": 230,
        "current_a": current_a,
        "cost_today_bd": total_cost_bhd,
        "tariff_bd_per_kwh": 0.032,
        "temperature_c": temperature,
        "humidity_percent": humidity,
        "air_quality_status": "Good",
        "aqi": 1,
        "tvoc": 0,
        "eco2": 400,
        "light_raw": 0,
        "light_status": light_status,
        "motion": motion,
        "motion_text": "Motion detected" if motion == 1 else "No motion",
        "noise_level": sound_raw,
        "noise_status": "Noise" if noise == 1 else "Quiet",
        "smoke": smoke,
        "smoke_text": "Warning" if smoke == 1 else "Clear",
        "room_area_m2": room_area_m2,
        "occupancy_count": occupancy_count,
        "room_devices": room_devices,
        "ac_details": ac_details,
        "ai_efficiency_score": ai_efficiency_score,
        "ai_recommendation": expected.get("expected_recommendation_type"),
        "ai_summary": expected.get("expected_description"),
        "waste_events_count": 1 if expected.get("expected_energy_waste") else 0,
        "abnormal_usage_count": 0
        if expected.get("expected_abnormal_usage") == "normal"
        else 1,
        "device_states": {
            "breaker_01": {"is_on": switch_on, "power_w": switch_power_w},
            "breaker_02": {"is_on": ac_on, "power_w": ac_power_w},
        },
        "devices": {
            "esp32_01": {
                "type": "sensor_node",
                "name": "Scenario ESP32",
                "status": {
                    "online": True,
                    "health_status": "online",
                    "lastSeenMs": written_at,
                },
            },
            "breaker_01": {
                "type": "smart_breaker",
                "name": "Switch Breaker",
                "status": {
                    "online": True,
                    "switch": switch_on,
                    "relay_status": "on" if switch_on else "off",
                    "lastSeenMs": written_at,
                },
            },
            "breaker_02": {
                "type": "smart_breaker",
                "name": "AC Breaker",
                "status": {
                    "online": True,
                    "switch": ac_on,
                    "relay_status": "on" if ac_on else "off",
                    "lastSeenMs": written_at,
                },
            },
        },
        "backend": {
            "dashboard": {
                "environment": environment,
                "energy": dashboard_energy,
                "ai": {
                    "updated_at": written_at,
                    "source": "Smart Energy AI Demo",
                    "model_name": "demo_scenario",
                    "model_version": "home_test",
                    "input_source": "demo_scenario_data",
                    "energy_waste": ai_energy_waste,
                    "waste_confidence": 0.85 if ai_energy_waste else 0.15,
                    "abnormal_usage": ai_abnormal,
                    "abnormal_usage_confidence": 0.82 if ai_abnormal else 0.10,
                    "recommendation_type": ai_recommendation_type,
                    "next_hour_energy_kWh": total_energy_kwh,
                    "next_hour_cost_BHD": total_cost_bhd,
                    "efficiency_score": ai_efficiency_score,
                    "explanation": ai_explanation,
                    "control_suggestion": "Demo mode only. Device control is disabled.",
                },
            },
            "energy": {
                "current_total": dashboard_energy,
                "branches": branches,
            },
            "current_state": {
                "last_processed_at": written_at,
                "occupancy_state": environment.get("occupancy_state"),
                "waste_risk": environment.get("waste_risk"),
                "latest_temperature": environment.get("temperature"),
                "latest_humidity": environment.get("humidity"),
                "latest_sound_raw": environment.get("sound_raw"),
                "motion": environment.get("motion"),
                "light_status": environment.get("light_status"),
                "smoke": environment.get("smoke"),
            },
            "latest_hourly_summary": latest_hourly_summary,
            "device_health": {
                "updated_at": written_at,
                "devices": {
                    "esp32_01": {"online": True, "health_status": "online"},
                    "breaker_01": {"online": True, "health_status": "online"},
                    "breaker_02": {"online": True, "health_status": "online"},
                },
            },
            "recommendations": {
                "ai_energy_insight": {
                    "recommendation_id": f"demo_{scenario_name}",
                    "type": "ai_energy_insight",
                    "priority": "high" if ai_energy_waste or ai_abnormal else "low",
                    "title": scenario_name.replace("_", " ").title(),
                    "message": ai_explanation,
                    "source": "Smart Energy AI Demo",
                    "recommendation_type": ai_recommendation_type,
                    "status": "active",
                    "created_at": written_at,
                    "updated_at": written_at,
                }
            },
            "active_alerts": {
                "ai_abnormal_usage": {
                    "id": f"demo_alert_{scenario_name}",
                    "type": "ai_abnormal_usage",
                    "priority": "high" if ai_abnormal else "low",
                    "title": "Demo AI abnormal usage",
                    "message": ai_explanation,
                    "source": "Smart Energy AI Demo",
                    "created_at": written_at,
                    "updated_at": written_at,
                    "energy_waste": ai_energy_waste,
                    "abnormal_usage": ai_abnormal,
                }
            }
            if ai_energy_waste or ai_abnormal
            else {},
            "ai": {
                "daily_summary": {
                    "day_id": datetime.fromtimestamp(
                        timestamp_ms / 1000, tz=BAHRAIN_TZ
                    ).strftime("%Y-%m-%d"),
                    "updated_at": written_at,
                    "source": "Smart Energy AI Demo",
                    "prediction_count": 1,
                    "waste_prediction_count": 1 if ai_energy_waste else 0,
                    "abnormal_prediction_count": 1 if ai_abnormal else 0,
                    "average_efficiency_score": ai_efficiency_score,
                    "predicted_next_hour_energy_total_kWh": total_energy_kwh,
                    "predicted_next_hour_cost_total_BHD": total_cost_bhd,
                    "latest_explanation": ai_explanation,
                    "summary": ai_explanation,
                },
                "test_expected": expected,
                "test_metadata": {
                    "scenario_id": scenario_name,
                    "scenario_name": scenario_name.replace("_", " ").title(),
                    "scenario_description": scenario_description,
                    "active_scenario": scenario_name,
                    "written_at": written_at,
                    "written_by": "devices/test_ai_scenarios.py",
                    "notes": "Controlled AI scenario test data. Safe test home only.",
                },
            },
        },
        "history": {
            "sensor_logs": {
                f"scenario_{written_at}": {
                    "timestamp_ms": timestamp_ms,
                    **{
                        key: value
                        for key, value in environment.items()
                        if key
                        in {
                            "temperature",
                            "humidity",
                            "sound_raw",
                            "noise",
                            "motion",
                            "light_status",
                            "smoke",
                        }
                    },
                }
            }
        },
    }


def get_scenarios() -> dict[str, dict[str, Any]]:
    base_timestamp = now_ms()

    return {
        "normal_usage": {
            "description": "Occupied room with normal temperature and moderate power.",
            "expected": {
                "scenario_name": "normal_usage",
                "expected_energy_waste": False,
                "expected_abnormal_usage": "normal",
                "expected_recommendation_type": "none",
                "expected_description": "AI should classify this as normal usage.",
            },
            "data": {
                "timestamp_ms": base_timestamp,
                "motion": 1,
                "light_status": "Dim",
                "temperature": 24.5,
                "humidity": 55.0,
                "sound_raw": 520,
                "noise": 0,
                "smoke": 0,
                "switch_power_w": 20,
                "ac_power_w": 25,
                "switch_on": True,
                "ac_on": True,
            },
        },
        "empty_room_energy_waste": {
            "description": "No motion, low sound, bright room, and high power.",
            "expected": {
                "scenario_name": "empty_room_energy_waste",
                "expected_energy_waste": True,
                "expected_abnormal_usage": "ac_running_while_empty",
                "expected_recommendation_type": "reduce_ac_fan_usage",
                "expected_description": "AI should detect likely waste while the room appears empty.",
            },
            "data": {
                "timestamp_ms": base_timestamp,
                "motion": 0,
                "light_status": "Bright",
                "temperature": 25.0,
                "humidity": 52.0,
                "sound_raw": 120,
                "noise": 0,
                "smoke": 0,
                "switch_power_w": 55,
                "ac_power_w": 90,
                "switch_on": True,
                "ac_on": True,
            },
        },
        "abnormal_high_power": {
            "description": "Very high total power compared with normal pattern.",
            "expected": {
                "scenario_name": "abnormal_high_power",
                "expected_energy_waste": True,
                "expected_abnormal_usage": "high_total_power",
                "expected_recommendation_type": "check_connected_devices",
                "expected_description": "AI should flag unusually high total power.",
            },
            "data": {
                "timestamp_ms": base_timestamp,
                "motion": 1,
                "light_status": "Bright",
                "temperature": 26.0,
                "humidity": 50.0,
                "sound_raw": 650,
                "noise": 1,
                "smoke": 0,
                "switch_power_w": 180,
                "ac_power_w": 220,
                "switch_on": True,
                "ac_on": True,
            },
        },
        "realistic_single_room_peak_load": {
            "description": "Occupied single room with AC, TV, gaming laptop, lights, and chargers active.",
            "expected": {
                "scenario_name": "realistic_single_room_peak_load",
                "expected_energy_waste": True,
                "expected_abnormal_usage": "high_single_room_load",
                "expected_recommendation_type": "reduce_ac_and_device_load",
                "expected_description": "AI should explain that the room load is high because the AC compressor and several plug loads are running together.",
                "expected_efficiency_score": 42,
            },
            "data": {
                "timestamp_ms": bahrain_timestamp_for_hour(16),
                "motion": 1,
                "light_status": "Bright",
                "temperature": 30.2,
                "humidity": 61.0,
                "sound_raw": 820,
                "noise": 1,
                "smoke": 0,
                "switch_power_w": 515,
                "ac_power_w": 1580,
                "switch_on": True,
                "ac_on": True,
                "ac_setpoint_c": 18,
                "ac_mode": "cool",
                "ac_fan_speed": "high",
                "room_area_m2": 18.0,
                "occupancy_count": 2,
                "room_devices": [
                    {
                        "name": "LED ceiling lights",
                        "category": "lighting",
                        "power_w": 45,
                        "breaker_id": "breaker_01",
                        "is_on": True,
                    },
                    {
                        "name": "Gaming laptop",
                        "category": "computer",
                        "power_w": 180,
                        "breaker_id": "breaker_01",
                        "is_on": True,
                    },
                    {
                        "name": "TV / monitor",
                        "category": "entertainment",
                        "power_w": 140,
                        "breaker_id": "breaker_01",
                        "is_on": True,
                    },
                    {
                        "name": "Phone and accessory chargers",
                        "category": "charging",
                        "power_w": 35,
                        "breaker_id": "breaker_01",
                        "is_on": True,
                    },
                    {
                        "name": "Mini fridge / small appliance",
                        "category": "appliance",
                        "power_w": 115,
                        "breaker_id": "breaker_01",
                        "is_on": True,
                    },
                    {
                        "name": "Split AC compressor running",
                        "category": "air_conditioner",
                        "power_w": 1580,
                        "breaker_id": "breaker_02",
                        "is_on": True,
                        "setpoint_c": 18,
                        "mode": "cool",
                        "fan_speed": "high",
                    },
                ],
            },
        },
        "realistic_ac_startup_surge": {
            "description": "AC compressor startup surge in a hot occupied room.",
            "expected": {
                "scenario_name": "realistic_ac_startup_surge",
                "expected_energy_waste": False,
                "expected_abnormal_usage": "ac_startup_surge",
                "expected_recommendation_type": "monitor_ac_startup_current",
                "expected_description": "AI should identify a short high AC load that can happen when the compressor starts, not a normal steady load.",
                "expected_efficiency_score": 58,
            },
            "data": {
                "timestamp_ms": bahrain_timestamp_for_hour(15),
                "motion": 1,
                "light_status": "Dim",
                "temperature": 31.0,
                "humidity": 58.0,
                "sound_raw": 610,
                "noise": 0,
                "smoke": 0,
                "switch_power_w": 95,
                "ac_power_w": 2350,
                "switch_on": True,
                "ac_on": True,
                "ac_setpoint_c": 20,
                "ac_mode": "cool",
                "ac_fan_speed": "auto",
                "room_area_m2": 18.0,
                "occupancy_count": 1,
                "room_devices": [
                    {
                        "name": "Desk light and chargers",
                        "category": "mixed_load",
                        "power_w": 95,
                        "breaker_id": "breaker_01",
                        "is_on": True,
                    },
                    {
                        "name": "Split AC compressor startup",
                        "category": "air_conditioner",
                        "power_w": 2350,
                        "breaker_id": "breaker_02",
                        "is_on": True,
                        "setpoint_c": 20,
                        "mode": "cool",
                        "fan_speed": "auto",
                    },
                ],
            },
        },
        "realistic_empty_room_ac_left_on": {
            "description": "Empty room where the AC and small electronics were left running.",
            "expected": {
                "scenario_name": "realistic_empty_room_ac_left_on",
                "expected_energy_waste": True,
                "expected_abnormal_usage": "ac_running_while_empty",
                "expected_recommendation_type": "turn_off_ac_when_empty",
                "expected_description": "AI should flag clear energy waste because no motion or noise is detected while AC power remains high.",
                "expected_efficiency_score": 35,
            },
            "data": {
                "timestamp_ms": bahrain_timestamp_for_hour(13),
                "motion": 0,
                "light_status": "Dark",
                "temperature": 23.0,
                "humidity": 49.0,
                "sound_raw": 75,
                "noise": 0,
                "smoke": 0,
                "switch_power_w": 85,
                "ac_power_w": 1320,
                "switch_on": True,
                "ac_on": True,
                "ac_setpoint_c": 19,
                "ac_mode": "cool",
                "ac_fan_speed": "medium",
                "room_area_m2": 18.0,
                "occupancy_count": 0,
                "room_devices": [
                    {
                        "name": "TV standby and chargers",
                        "category": "standby_load",
                        "power_w": 85,
                        "breaker_id": "breaker_01",
                        "is_on": True,
                    },
                    {
                        "name": "Split AC cooling empty room",
                        "category": "air_conditioner",
                        "power_w": 1320,
                        "breaker_id": "breaker_02",
                        "is_on": True,
                        "setpoint_c": 19,
                        "mode": "cool",
                        "fan_speed": "medium",
                    },
                ],
            },
        },
        "realistic_night_sleep_ac_efficient": {
            "description": "Night occupied room with efficient AC cycling and low plug load.",
            "expected": {
                "scenario_name": "realistic_night_sleep_ac_efficient",
                "expected_energy_waste": False,
                "expected_abnormal_usage": "normal",
                "expected_recommendation_type": "none",
                "expected_description": "AI should classify this as acceptable night use because power is moderate and the room appears occupied.",
                "expected_efficiency_score": 86,
            },
            "data": {
                "timestamp_ms": bahrain_timestamp_for_hour(2),
                "motion": 1,
                "light_status": "Dark",
                "temperature": 24.0,
                "humidity": 52.0,
                "sound_raw": 230,
                "noise": 0,
                "smoke": 0,
                "switch_power_w": 18,
                "ac_power_w": 520,
                "switch_on": True,
                "ac_on": True,
                "ac_setpoint_c": 24,
                "ac_mode": "cool",
                "ac_fan_speed": "low",
                "room_area_m2": 18.0,
                "occupancy_count": 1,
                "room_devices": [
                    {
                        "name": "Phone charger",
                        "category": "charging",
                        "power_w": 18,
                        "breaker_id": "breaker_01",
                        "is_on": True,
                    },
                    {
                        "name": "Split AC cycling at night",
                        "category": "air_conditioner",
                        "power_w": 520,
                        "breaker_id": "breaker_02",
                        "is_on": True,
                        "setpoint_c": 24,
                        "mode": "cool",
                        "fan_speed": "low",
                    },
                ],
            },
        },
        "bright_room_lights_on": {
            "description": "Bright room with switch breaker active and no motion.",
            "expected": {
                "scenario_name": "bright_room_lights_on",
                "expected_energy_waste": True,
                "expected_abnormal_usage": "light_on_no_motion",
                "expected_recommendation_type": "turn_off_lights",
                "expected_description": "AI should recommend lighting savings.",
            },
            "data": {
                "timestamp_ms": base_timestamp,
                "motion": 0,
                "light_status": "Bright",
                "temperature": 24.0,
                "humidity": 57.0,
                "sound_raw": 160,
                "noise": 0,
                "smoke": 0,
                "switch_power_w": 80,
                "ac_power_w": 0,
                "switch_on": True,
                "ac_on": False,
            },
        },
        "night_device_left_on": {
            "description": "Night scenario with no motion and medium device power.",
            "expected": {
                "scenario_name": "night_device_left_on",
                "expected_energy_waste": True,
                "expected_abnormal_usage": "device_left_on_at_night",
                "expected_recommendation_type": "turn_off_unused_devices",
                "expected_description": "AI should detect a likely device left on overnight.",
            },
            "data": {
                "timestamp_ms": bahrain_timestamp_for_hour(2),
                "motion": 0,
                "light_status": "Dim",
                "temperature": 23.5,
                "humidity": 60.0,
                "sound_raw": 100,
                "noise": 0,
                "smoke": 0,
                "switch_power_w": 65,
                "ac_power_w": 20,
                "switch_on": True,
                "ac_on": True,
            },
        },
        "occupied_high_temperature": {
            "description": "Occupied room with high temperature and moderate power.",
            "expected": {
                "scenario_name": "occupied_high_temperature",
                "expected_energy_waste": False,
                "expected_abnormal_usage": "normal",
                "expected_recommendation_type": "comfort_balance",
                "expected_description": "AI should avoid waste alert but may suggest comfort balancing.",
            },
            "data": {
                "timestamp_ms": base_timestamp,
                "motion": 1,
                "light_status": "Dim",
                "temperature": 29.5,
                "humidity": 62.0,
                "sound_raw": 580,
                "noise": 0,
                "smoke": 0,
                "switch_power_w": 25,
                "ac_power_w": 45,
                "switch_on": True,
                "ac_on": True,
            },
        },
        "occupied_lights_off": {
            "description": "Occupied room with dark light status and normal power.",
            "expected": {
                "scenario_name": "occupied_lights_off",
                "expected_energy_waste": False,
                "expected_abnormal_usage": "normal",
                "expected_recommendation_type": "lighting_comfort",
                "expected_description": "AI should note that the room is occupied but lights are off or very dim.",
            },
            "data": {
                "timestamp_ms": base_timestamp,
                "motion": 1,
                "light_status": "Dark",
                "temperature": 24.5,
                "humidity": 54.0,
                "sound_raw": 540,
                "noise": 0,
                "smoke": 0,
                "switch_power_w": 0,
                "ac_power_w": 35,
                "switch_on": False,
                "ac_on": True,
            },
        },
        "smoke_gas_warning": {
            "description": "Smoke/gas warning with occupied room and active power.",
            "expected": {
                "scenario_name": "smoke_gas_warning",
                "expected_energy_waste": False,
                "expected_abnormal_usage": "safety_warning",
                "expected_recommendation_type": "check_smoke_gas_sensor",
                "expected_description": "AI should clearly explain that smoke/gas safety is handled by rule-based alerts.",
            },
            "data": {
                "timestamp_ms": base_timestamp,
                "motion": 1,
                "light_status": "Bright",
                "temperature": 25.0,
                "humidity": 50.0,
                "sound_raw": 700,
                "noise": 1,
                "smoke": 1,
                "switch_power_w": 30,
                "ac_power_w": 45,
                "switch_on": True,
                "ac_on": True,
            },
        },
        "low_power_empty_room": {
            "description": "Empty room with very low power and low light.",
            "expected": {
                "scenario_name": "low_power_empty_room",
                "expected_energy_waste": False,
                "expected_abnormal_usage": "normal",
                "expected_recommendation_type": "none",
                "expected_description": "AI should treat this as normal because power is low.",
            },
            "data": {
                "timestamp_ms": base_timestamp,
                "motion": 0,
                "light_status": "Dark",
                "temperature": 24.0,
                "humidity": 56.0,
                "sound_raw": 90,
                "noise": 0,
                "smoke": 0,
                "switch_power_w": 1,
                "ac_power_w": 0,
                "switch_on": False,
                "ac_on": False,
            },
        },
        "missing_sensor_data": {
            "description": "Dashboard fallback with missing sound and humidity fields.",
            "expected": {
                "scenario_name": "missing_sensor_data",
                "expected_energy_waste": False,
                "expected_abnormal_usage": "normal",
                "expected_recommendation_type": "none",
                "expected_description": "AI should handle missing sensor fields without crashing.",
            },
            "data": {
                "timestamp_ms": base_timestamp,
                "motion": 1,
                "light_status": "Dim",
                "temperature": 24.5,
                "humidity": None,
                "sound_raw": None,
                "noise": 0,
                "smoke": 0,
                "switch_power_w": 15,
                "ac_power_w": 15,
                "switch_on": True,
                "ac_on": True,
                "omit_environment_fields": ["humidity", "sound_raw"],
            },
        },
    }


def write_scenario(scenario_name: str, preserve_ai_state: bool = False) -> dict[str, Any]:
    scenarios = get_scenarios()
    if scenario_name not in scenarios:
        raise ValueError(f"Unknown scenario: {scenario_name}")

    scenario = scenarios[scenario_name]
    data = scenario["data"]
    expected = scenario["expected"]

    payload = build_home_payload(
        scenario_name=scenario_name,
        scenario_description=scenario["description"],
        expected=expected,
        **data,
    )

    preserved_ai_state = None
    if preserve_ai_state:
        preserved_ai_state = db.reference(f"{TEST_HOME_PATH}/backend/ai").get()

    db.reference(TEST_HOME_PATH).set(payload)

    if preserve_ai_state and isinstance(preserved_ai_state, dict):
        preserved_ai_state["test_expected"] = payload["backend"]["ai"]["test_expected"]
        preserved_ai_state["test_metadata"] = payload["backend"]["ai"]["test_metadata"]
        db.reference(f"{TEST_HOME_PATH}/backend/ai").set(preserved_ai_state)

    return scenario


def write_scenario_catalog() -> None:
    scenarios = get_scenarios()
    catalog: dict[str, Any] = {}

    for scenario_name, scenario in scenarios.items():
        data = scenario["data"]
        catalog[scenario_name] = build_home_payload(
            scenario_name=scenario_name,
            scenario_description=scenario["description"],
            expected=scenario["expected"],
            **data,
        )

    db.reference(f"{TEST_HOME_PATH}/demo_scenarios").set(catalog)
    print(f"Wrote {len(catalog)} demo scenarios to {TEST_HOME_PATH}/demo_scenarios")


def clear_test_home(yes: bool) -> None:
    if not yes:
        confirmation = input(
            f"This will delete {TEST_HOME_PATH}. Type 'home_test' to continue: "
        )
        if confirmation.strip() != TEST_HOME_ID:
            print("Clear cancelled.")
            return

    db.reference(TEST_HOME_PATH).delete()
    print(f"Cleared {TEST_HOME_PATH}")


def call_ai_service(home_id: str, scenario_id: str | None = None) -> dict[str, Any] | None:
    service_url = os.environ.get("AI_SERVICE_URL", DEFAULT_AI_SERVICE_URL).rstrip("/")

    if scenario_id:
        url = f"{service_url}/predict/{home_id}/scenario/{scenario_id}"
    else:
        url = f"{service_url}/predict/{home_id}"
    print(f"\nCalling AI service: {url}")

    request = Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            raw_body = response.read().decode("utf-8")
            body = json.loads(raw_body)
            print(f"\nAI API status: {response.status}")
            print("AI response JSON:")
            print(json.dumps(body, indent=2))
            print(
                "latest_prediction path:",
                body.get(
                    "firebase_path_written",
                    f"/homes/{home_id}/backend/ai/latest_prediction",
                ),
            )
            return body
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        print(f"AI API failed with HTTP {error.code}: {error_body}")
    except URLError as error:
        print(f"AI API connection failed: {error}")
    except TimeoutError:
        print("AI API call timed out.")
    except json.JSONDecodeError as error:
        print(f"AI API returned invalid JSON: {error}")

    return None


def call_ai_for_scenario_catalog() -> None:
    scenarios = get_scenarios()
    failures: list[str] = []

    for scenario_name in scenarios:
        result = call_ai_service(TEST_HOME_ID, scenario_name)
        if result is None:
            failures.append(scenario_name)

    if failures:
        raise RuntimeError(
            "AI prediction failed for scenarios: " + ", ".join(failures)
        )

    print(f"\nAI predictions completed for {len(scenarios)} demo scenarios.")


def print_scenario_summary(scenario_name: str, scenario: dict[str, Any]) -> None:
    expected = scenario["expected"]

    print("\nScenario written successfully")
    print("=============================")
    print(f"Scenario: {scenario_name}")
    print(f"Description: {scenario['description']}")
    print(f"Firebase path: {TEST_HOME_PATH}")
    print("\nExpected result:")
    print(f"- energy_waste: {expected['expected_energy_waste']}")
    print(f"- abnormal_usage: {expected['expected_abnormal_usage']}")
    print(f"- recommendation_type: {expected['expected_recommendation_type']}")
    print(f"- notes: {expected['expected_description']}")
    print("\nRun Cloud Run manually:")
    print(f"curl -X POST -H \"Content-Type: application/json\" -d '{{}}' \"$AI_SERVICE_URL/predict/{TEST_HOME_ID}\"")


def list_scenarios() -> None:
    print("Available scenarios:")
    for name, scenario in get_scenarios().items():
        print(f"- {name}: {scenario['description']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write controlled AI test scenarios to Firebase.")
    parser.add_argument("--scenario", help="Scenario name to write to /homes/home_test.")
    parser.add_argument("--list", action="store_true", help="List available scenarios.")
    parser.add_argument("--clear", action="store_true", help="Clear /homes/home_test.")
    parser.add_argument(
        "--write-catalog",
        action="store_true",
        help="Write all demo scenarios under /homes/home_test/demo_scenarios.",
    )
    parser.add_argument(
        "--predict-catalog",
        action="store_true",
        help="Call real AI prediction for every /homes/home_test/demo_scenarios entry.",
    )
    parser.add_argument("--yes", action="store_true", help="Skip confirmation for --clear.")
    parser.add_argument(
        "--call-ai",
        action="store_true",
        help="Call POST {AI_SERVICE_URL}/predict/home_test after writing the scenario.",
    )
    parser.add_argument(
        "--preserve-ai-state",
        action="store_true",
        help="Preserve /backend/ai outputs while replacing scenario input data.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list:
        list_scenarios()
        return

    if (
        not args.scenario
        and not args.clear
        and not args.write_catalog
        and not args.predict_catalog
    ):
        print(
            "Use --list, --scenario SCENARIO_NAME, --write-catalog, "
            "--predict-catalog, or --clear."
        )
        sys.exit(1)

    initialize_firebase()

    if args.clear:
        clear_test_home(args.yes)
        return

    if args.write_catalog:
        write_scenario_catalog()
        if not args.scenario and not args.predict_catalog:
            return

    if args.predict_catalog:
        call_ai_for_scenario_catalog()
        if not args.scenario:
            return

    scenario = write_scenario(args.scenario, preserve_ai_state=args.preserve_ai_state)
    print_scenario_summary(args.scenario, scenario)

    if args.call_ai:
        call_ai_service(TEST_HOME_ID)
    else:
        print("\nAI was not called. Use --call-ai to run the deployed AI service.")


if __name__ == "__main__":
    main()
