from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import requests

from local_state_store import (
    history_between,
    home_ref,
    mark_summary_sync_failed,
    mark_summary_synced,
    pending_summaries,
    summaries_between,
    upsert_summary,
)

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from timestamp_utils import BAHRAIN_TZ, TIMEZONE, ms_to_iso


HOME_ID = os.environ.get("HOME_ID", "home_001")
AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-west-1"
AWS_DYNAMODB_SUMMARIES_TABLE = os.environ.get(
    "AWS_DYNAMODB_SUMMARIES_TABLE",
    "SmartEnergySummaries",
)
SUMMARY_LOOKBACK_HOURS = int(os.environ.get("SUMMARY_LOOKBACK_HOURS", "48"))
SUMMARY_LOOKBACK_DAYS = int(os.environ.get("SUMMARY_LOOKBACK_DAYS", "7"))
SUMMARY_SYNC_BATCH_SIZE = int(os.environ.get("SUMMARY_SYNC_BATCH_SIZE", "25"))
AWS_SUMMARY_SYNC_INTERVAL_SECONDS = int(os.environ.get("AWS_SUMMARY_SYNC_INTERVAL_SECONDS", "300"))
SUMMARY_SYNC_DESTINATION = os.environ.get("SUMMARY_SYNC_DESTINATION", "ec2").strip().lower()
KAHRABAIQ_API_URL = os.environ.get("KAHRABAIQ_API_URL", "").rstrip("/")
PI_ID = os.environ.get("PI_ID", "pi_home_001")
PI_DEVICE_TOKEN = os.environ.get("PI_DEVICE_TOKEN", "")


def log(message: str) -> None:
    print(f"[AWS SUMMARY SYNC] {datetime.now(BAHRAIN_TZ).isoformat()} {message}", flush=True)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on", "motion", "detected", "smoke", "gas"}:
            return True
        if normalized in {"false", "0", "no", "off", "clear", "no motion"}:
            return False
    return None


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def numeric_values(records: list[dict[str, Any]], key: str) -> list[float]:
    values = []
    for record in records:
        value = as_number(record.get(key))
        if value is not None:
            values.append(value)
    return values


def bool_count(records: list[dict[str, Any]], *keys: str) -> int:
    count = 0
    for record in records:
        for key in keys:
            value = as_bool(record.get(key))
            if value is not None:
                count += 1 if value else 0
                break
    return count


def first_last_delta(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    delta = values[-1] - values[0]
    if delta < 0:
        return None
    return round(delta, 6)


def timestamp_in_window(item: dict[str, Any], start_at_ms: int, end_at_ms: int) -> bool:
    for key in (
        "timestamp_ms",
        "created_at_ms",
        "requested_at_ms",
        "executed_at_ms",
        "updated_at_ms",
    ):
        value = as_number(item.get(key))
        if value is not None:
            return start_at_ms <= int(value) < end_at_ms
    return False


def object_values_from_state(path: str) -> list[dict[str, Any]]:
    value = home_ref(HOME_ID, path).get()
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, dict)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def pi_headers() -> dict[str, str]:
    return {"X-Pi-Id": PI_ID, "X-Device-Token": PI_DEVICE_TOKEN}


def api_request(method: str, path: str, **kwargs: Any) -> requests.Response:
    if not KAHRABAIQ_API_URL:
        raise RuntimeError("KAHRABAIQ_API_URL is required when SUMMARY_SYNC_DESTINATION=ec2.")
    return requests.request(method, f"{KAHRABAIQ_API_URL}{path}", timeout=30, **kwargs)


def response_json(response: requests.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as error:
        text = (response.text or "").strip()
        raise RuntimeError(f"Non-JSON response from EC2 ({response.status_code}): {text[:240]}") from error
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected EC2 response ({response.status_code}): {data!r}")
    return data


def summarize_sensors(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sampleCount": len(records),
        "avgTemperatureC": average(numeric_values(records, "temperature")),
        "avgHumidity": average(numeric_values(records, "humidity")),
        "avgAqi": average(numeric_values(records, "aqi")),
        "avgTvoc": average(numeric_values(records, "tvoc")),
        "avgEco2": average(numeric_values(records, "eco2")),
        "avgLightRaw": average(numeric_values(records, "light_raw")),
        "avgSoundRaw": average(numeric_values(records, "sound_raw")),
        "motionDetectedCount": bool_count(records, "motion", "motion_text"),
        "smokeDetectedCount": bool_count(records, "smoke", "smoke_text", "smoke_status"),
    }


def summarize_breaker(records: list[dict[str, Any]]) -> dict[str, Any]:
    power_values = numeric_values(records, "power_W")
    energy_values = numeric_values(records, "energy_kWh")
    return {
        "sampleCount": len(records),
        "avgPowerW": average(power_values),
        "peakPowerW": round(max(power_values), 3) if power_values else None,
        "avgVoltageV": average(numeric_values(records, "voltage_V")),
        "avgCurrentA": average(numeric_values(records, "current_A")),
        "energyDeltaKwh": first_last_delta(energy_values),
        "onlineSamples": sum(1 for record in records if str(record.get("online_state", "")).lower() == "online"),
        "switchOnSamples": bool_count(records, "switch"),
    }


def summarize_breakers(start_at_ms: int, end_at_ms: int) -> tuple[dict[str, Any], float | None]:
    breaker_summaries = {}
    total_energy = 0.0
    has_energy = False
    for breaker_id in ("breaker_01", "breaker_02"):
        records = history_between(breaker_id, start_at_ms, end_at_ms)
        summary = summarize_breaker(records)
        breaker_summaries[breaker_id] = summary
        energy = as_number(summary.get("energyDeltaKwh"))
        if energy is not None:
            total_energy += energy
            has_energy = True
    return breaker_summaries, round(total_energy, 6) if has_energy else None


def summarize_commands(start_at_ms: int, end_at_ms: int) -> dict[str, Any]:
    commands = [
        command
        for command in object_values_from_state("commands/history")
        if timestamp_in_window(command, start_at_ms, end_at_ms)
    ]
    by_status: dict[str, int] = {}
    by_device: dict[str, int] = {}
    emergency_count = 0
    for command in commands:
        status = str(command.get("status") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        device_id = str(command.get("device_id") or "unknown")
        by_device[device_id] = by_device.get(device_id, 0) + 1
        if as_bool(command.get("emergency")):
            emergency_count += 1
    return {
        "count": len(commands),
        "byStatus": by_status,
        "byDevice": by_device,
        "emergencyCount": emergency_count,
    }


def summarize_alerts(start_at_ms: int, end_at_ms: int) -> dict[str, Any]:
    alert_records = [
        *object_values_from_state("alerts/history"),
        *object_values_from_state("safety/events"),
    ]
    alerts = [item for item in alert_records if timestamp_in_window(item, start_at_ms, end_at_ms)]
    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for alert in alerts:
        severity = str(alert.get("severity") or "unknown")
        alert_type = str(alert.get("alert_type") or alert.get("type") or "unknown")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_type[alert_type] = by_type.get(alert_type, 0) + 1
    return {
        "count": len(alerts),
        "bySeverity": by_severity,
        "byType": by_type,
    }


def weighted_average_from_summaries(
    summaries: list[dict[str, Any]],
    section: str,
    value_key: str,
    weight_key: str = "sampleCount",
) -> float | None:
    total = 0.0
    weight_total = 0.0
    for summary in summaries:
        bucket = as_dict(summary.get(section))
        value = as_number(bucket.get(value_key))
        weight = as_number(bucket.get(weight_key))
        if value is None or weight is None or weight <= 0:
            continue
        total += value * weight
        weight_total += weight
    if weight_total <= 0:
        return None
    return round(total / weight_total, 3)


def sum_section_number(summaries: list[dict[str, Any]], section: str, key: str) -> float | None:
    total = 0.0
    found = False
    for summary in summaries:
        value = as_number(as_dict(summary.get(section)).get(key))
        if value is not None:
            total += value
            found = True
    return round(total, 6) if found else None


def sum_nested_counts(summaries: list[dict[str, Any]], section: str, key: str) -> dict[str, int]:
    totals: dict[str, int] = {}
    for summary in summaries:
        values = as_dict(as_dict(summary.get(section)).get(key))
        for item_key, raw_value in values.items():
            value = as_number(raw_value)
            if value is not None:
                totals[str(item_key)] = totals.get(str(item_key), 0) + int(value)
    return totals


def daily_summary_from_hourlies(
    start_at_ms: int,
    end_at_ms: int,
    hourlies: list[dict[str, Any]],
) -> dict[str, Any]:
    base = {
        "type": "daily_summary",
        "homeId": HOME_ID,
        "period": "daily",
        "summaryVersion": 1,
        "startAtMs": start_at_ms,
        "endAtMs": end_at_ms,
        "startTime": ms_to_iso(start_at_ms),
        "endTime": ms_to_iso(end_at_ms),
        "timezone": TIMEZONE,
        "source": "raspberry_pi_hourly_rollup",
        "hourlySummaryCount": len(hourlies),
    }
    sensor_sample_count = int(sum_section_number(hourlies, "sensorSummary", "sampleCount") or 0)
    occupancy_sample_count = int(sum_section_number(hourlies, "occupancySummary", "sampleCount") or 0)
    breaker_summaries = {}
    total_energy = 0.0
    has_energy = False
    for breaker_id in ("breaker_01", "breaker_02"):
        breaker_hourlies = [
            {"breaker": as_dict(as_dict(summary.get("breakerSummaries")).get(breaker_id))}
            for summary in hourlies
        ]
        energy = sum_section_number(breaker_hourlies, "breaker", "energyDeltaKwh")
        if energy is not None:
            total_energy += energy
            has_energy = True
        peaks = [
            value
            for summary in breaker_hourlies
            if (value := as_number(as_dict(summary.get("breaker")).get("peakPowerW"))) is not None
        ]
        breaker_summaries[breaker_id] = {
            "sampleCount": int(sum_section_number(breaker_hourlies, "breaker", "sampleCount") or 0),
            "avgPowerW": weighted_average_from_summaries(breaker_hourlies, "breaker", "avgPowerW"),
            "peakPowerW": round(max(peaks), 3) if peaks else None,
            "avgVoltageV": weighted_average_from_summaries(breaker_hourlies, "breaker", "avgVoltageV"),
            "avgCurrentA": weighted_average_from_summaries(breaker_hourlies, "breaker", "avgCurrentA"),
            "energyDeltaKwh": energy,
            "onlineSamples": int(sum_section_number(breaker_hourlies, "breaker", "onlineSamples") or 0),
            "switchOnSamples": int(sum_section_number(breaker_hourlies, "breaker", "switchOnSamples") or 0),
        }

    return {
        **base,
        "sensorSummary": {
            "sampleCount": sensor_sample_count,
            "avgTemperatureC": weighted_average_from_summaries(hourlies, "sensorSummary", "avgTemperatureC"),
            "avgHumidity": weighted_average_from_summaries(hourlies, "sensorSummary", "avgHumidity"),
            "avgAqi": weighted_average_from_summaries(hourlies, "sensorSummary", "avgAqi"),
            "avgTvoc": weighted_average_from_summaries(hourlies, "sensorSummary", "avgTvoc"),
            "avgEco2": weighted_average_from_summaries(hourlies, "sensorSummary", "avgEco2"),
            "avgLightRaw": weighted_average_from_summaries(hourlies, "sensorSummary", "avgLightRaw"),
            "avgSoundRaw": weighted_average_from_summaries(hourlies, "sensorSummary", "avgSoundRaw"),
            "motionDetectedCount": int(sum_section_number(hourlies, "sensorSummary", "motionDetectedCount") or 0),
            "smokeDetectedCount": int(sum_section_number(hourlies, "sensorSummary", "smokeDetectedCount") or 0),
        },
        "occupancySummary": {
            "sampleCount": occupancy_sample_count,
            "occupiedCount": int(sum_section_number(hourlies, "occupancySummary", "occupiedCount") or 0),
            "avgConfidence": weighted_average_from_summaries(hourlies, "occupancySummary", "avgConfidence"),
        },
        "breakerSummaries": breaker_summaries,
        "totalEnergyKwh": round(total_energy, 6) if has_energy else None,
        "commandSummary": {
            "count": int(sum_section_number(hourlies, "commandSummary", "count") or 0),
            "byStatus": sum_nested_counts(hourlies, "commandSummary", "byStatus"),
            "byDevice": sum_nested_counts(hourlies, "commandSummary", "byDevice"),
            "emergencyCount": int(sum_section_number(hourlies, "commandSummary", "emergencyCount") or 0),
        },
        "alertSummary": {
            "count": int(sum_section_number(hourlies, "alertSummary", "count") or 0),
            "bySeverity": sum_nested_counts(hourlies, "alertSummary", "bySeverity"),
            "byType": sum_nested_counts(hourlies, "alertSummary", "byType"),
        },
    }


def build_summary(period: str, start_at_ms: int, end_at_ms: int) -> dict[str, Any]:
    sensor_records = history_between("sensor_logs", start_at_ms, end_at_ms)
    occupancy_records = history_between("occupancy_logs", start_at_ms, end_at_ms)
    breaker_summaries, total_energy_kwh = summarize_breakers(start_at_ms, end_at_ms)
    return {
        "type": f"{period}_summary",
        "homeId": HOME_ID,
        "period": period,
        "summaryVersion": 1,
        "startAtMs": start_at_ms,
        "endAtMs": end_at_ms,
        "startTime": ms_to_iso(start_at_ms),
        "endTime": ms_to_iso(end_at_ms),
        "timezone": TIMEZONE,
        "source": "raspberry_pi_local_summary",
        "sensorSummary": summarize_sensors(sensor_records),
        "occupancySummary": {
            "sampleCount": len(occupancy_records),
            "occupiedCount": sum(
                1
                for record in occupancy_records
                if str(record.get("status") or record.get("occupancy") or "").lower()
                in {"occupied", "likely_occupied"}
            ),
            "avgConfidence": average(numeric_values(occupancy_records, "confidence")),
        },
        "breakerSummaries": breaker_summaries,
        "totalEnergyKwh": total_energy_kwh,
        "commandSummary": summarize_commands(start_at_ms, end_at_ms),
        "alertSummary": summarize_alerts(start_at_ms, end_at_ms),
    }


def hour_start(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def day_start(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def dt_to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def hourly_summary_id(start: datetime) -> str:
    return f"SUMMARY#HOURLY#{start.strftime('%Y-%m-%dT%H')}"


def daily_summary_id(start: datetime) -> str:
    return f"SUMMARY#DAILY#{start.strftime('%Y-%m-%d')}"


def generate_recent_summaries() -> None:
    now = datetime.now(BAHRAIN_TZ)
    latest_complete_hour = hour_start(now)
    for offset in range(1, max(1, SUMMARY_LOOKBACK_HOURS) + 1):
        start = latest_complete_hour - timedelta(hours=offset)
        end = start + timedelta(hours=1)
        upsert_summary(
            hourly_summary_id(start),
            HOME_ID,
            "hourly",
            dt_to_ms(start),
            dt_to_ms(end),
            build_summary("hourly", dt_to_ms(start), dt_to_ms(end)),
        )

    latest_complete_day = day_start(now)
    for offset in range(1, max(1, SUMMARY_LOOKBACK_DAYS) + 1):
        start = latest_complete_day - timedelta(days=offset)
        end = start + timedelta(days=1)
        start_ms = dt_to_ms(start)
        end_ms = dt_to_ms(end)
        hourly_summaries = summaries_between("hourly", start_ms, end_ms)
        value = (
            daily_summary_from_hourlies(start_ms, end_ms, hourly_summaries)
            if hourly_summaries
            else build_summary("daily", start_ms, end_ms)
        )
        upsert_summary(
            daily_summary_id(start),
            HOME_ID,
            "daily",
            start_ms,
            end_ms,
            value,
        )


def dynamodb_safe(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: dynamodb_safe(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [dynamodb_safe(item) for item in value if item is not None]
    return value


def dynamodb_table():
    import boto3

    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(AWS_DYNAMODB_SUMMARIES_TABLE)


def sync_pending_summaries() -> int:
    if SUMMARY_SYNC_DESTINATION == "ec2":
        return sync_pending_summaries_to_ec2()
    if SUMMARY_SYNC_DESTINATION != "dynamodb":
        raise RuntimeError("SUMMARY_SYNC_DESTINATION must be ec2 or dynamodb")
    return sync_pending_summaries_to_dynamodb()


def sync_pending_summaries_to_ec2() -> int:
    summaries = pending_summaries(SUMMARY_SYNC_BATCH_SIZE)
    if not summaries:
        return 0
    payload = {
        "home_id": HOME_ID,
        "summaries": [
            {
                "summary_id": summary["summary_id"],
                "period": summary["period"],
                "start_at_ms": summary["start_at_ms"],
                "end_at_ms": summary["end_at_ms"],
                "value": summary["value"],
                "local_created_at_ms": summary["created_at_ms"],
                "local_updated_at_ms": summary["updated_at_ms"],
            }
            for summary in summaries
        ],
    }
    response = api_request(
        "POST",
        f"/api/pi/{PI_ID}/summaries",
        headers=pi_headers(),
        json=payload,
    )
    data = response_json(response)
    if not response.ok or data.get("success") is False:
        raise RuntimeError(data.get("detail") or data.get("message") or response.text)
    synced_ids = data.get("summary_ids")
    if not isinstance(synced_ids, list):
        synced_ids = [summary["summary_id"] for summary in summaries]
    synced_id_set = {str(item) for item in synced_ids}
    for summary in summaries:
        if summary["summary_id"] in synced_id_set:
            mark_summary_synced(summary["summary_id"])
    return len(synced_id_set)


def sync_pending_summaries_to_dynamodb() -> int:
    table = dynamodb_table()
    synced = 0
    for summary in pending_summaries(SUMMARY_SYNC_BATCH_SIZE):
        value = summary["value"]
        item = {
            "PK": f"HOME#{summary['home_id']}",
            "SK": summary["summary_id"],
            **value,
            "summaryId": summary["summary_id"],
            "localCreatedAtMs": summary["created_at_ms"],
            "localUpdatedAtMs": summary["updated_at_ms"],
        }
        try:
            table.put_item(Item=dynamodb_safe(item))
            mark_summary_synced(summary["summary_id"])
            synced += 1
        except Exception as error:
            mark_summary_sync_failed(summary["summary_id"], error)
            raise
    return synced


def run_once() -> int:
    generate_recent_summaries()
    return sync_pending_summaries()


def main() -> int:
    log(
        f"Started for {HOME_ID}; destination={SUMMARY_SYNC_DESTINATION}; "
        f"table={AWS_DYNAMODB_SUMMARIES_TABLE}; region={AWS_REGION}"
    )
    while True:
        started = time.time()
        try:
            synced = run_once()
            if synced:
                log(f"Synced {synced} summary item(s)")
        except ModuleNotFoundError as error:
            log(f"boto3 is required for AWS sync: {error}")
        except Exception as error:
            log(f"Summary sync failed: {error}")

        elapsed = time.time() - started
        time.sleep(max(30, AWS_SUMMARY_SYNC_INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
