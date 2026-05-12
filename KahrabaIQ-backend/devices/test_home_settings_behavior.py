from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import api_server


def assert_true(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(name)


def test_settings_validation() -> None:
    settings = api_server.default_settings_record()
    settings["monthly_cost_limit_bhd"] = 10
    settings["daily_cost_limit_bhd"] = 1
    api_server.validate_settings(settings)
    invalid = {**settings, "comfort_temperature_min": 28, "comfort_temperature_max": 24}
    try:
        api_server.validate_settings(invalid)
    except Exception:
        assert_true("invalid comfort range rejected", True)
    else:
        raise AssertionError("invalid comfort range should fail")


def test_budget_status() -> None:
    settings = {
        **api_server.DEFAULT_SETTINGS,
        "monthly_cost_limit_bhd": 2,
        "monthly_energy_limit_kwh": 60,
        "daily_cost_limit_bhd": 0.2,
        "daily_energy_limit_kwh": 5,
        "high_usage_warning_percent": 80,
    }
    status = api_server.budget_status_from_energy(
        {
            "month_cost_bhd": 1.7,
            "month_kwh": 40,
            "today_cost_bhd": 0.25,
            "today_kwh": 2,
        },
        settings,
    )
    assert_true("monthly warning threshold is detected", status["monthly_cost_warning_reached"] is True)
    assert_true("daily cost limit is detected", status["daily_cost_limit_exceeded"] is True)
    assert_true("monthly cost is not exceeded", status["monthly_cost_limit_exceeded"] is False)


def test_notification_preferences() -> None:
    settings = {**api_server.DEFAULT_SETTINGS, "notifications_enabled": False}
    allowed, reason = api_server.notification_allowed_by_settings(settings, "cost_limit", "warning")
    assert_true("non-safety notifications can be disabled", allowed is False and reason == "notifications_disabled")
    allowed, _ = api_server.notification_allowed_by_settings(settings, "safety", "critical", urgent=True)
    assert_true("urgent safety notifications bypass global mute", allowed is True)
    settings = {**api_server.DEFAULT_SETTINGS, "ai_notifications_enabled": False}
    allowed, reason = api_server.notification_allowed_by_settings(settings, "ai_anomaly", "medium")
    assert_true("ai notifications respect settings", allowed is False and reason == "ai_notifications_enabled_disabled")


def main() -> None:
    test_settings_validation()
    test_budget_status()
    test_notification_preferences()


if __name__ == "__main__":
    main()
