from __future__ import annotations

import os
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

from local_command_controller import execute_local_command

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from timestamp_utils import BAHRAIN_TZ, TIMEZONE, ms_to_iso, now_ms


HOME_ID = os.environ.get("HOME_ID", "home_001")
AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-west-1"
AWS_DYNAMODB_SUMMARIES_TABLE = os.environ.get(
    "AWS_DYNAMODB_SUMMARIES_TABLE",
    "SmartEnergySummaries",
)
REMOTE_COMMAND_POLL_SECONDS = float(os.environ.get("REMOTE_COMMAND_POLL_SECONDS", "5"))
REMOTE_COMMAND_QUERY_LIMIT = int(os.environ.get("REMOTE_COMMAND_QUERY_LIMIT", "25"))
ALLOWED_DEVICES = {"breaker_01", "breaker_02", "matter_socket_switch", "matter_ac_switch"}
ALLOWED_COMMANDS = {"turn_on", "turn_off"}


def log(message: str) -> None:
    print(f"[AWS REMOTE COMMANDS] {datetime.now(BAHRAIN_TZ).isoformat()} {message}", flush=True)


def table():
    import boto3

    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(AWS_DYNAMODB_SUMMARIES_TABLE)


def from_dynamodb(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {key: from_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [from_dynamodb(item) for item in value]
    return value


def to_dynamodb(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: to_dynamodb(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [to_dynamodb(item) for item in value if item is not None]
    return value


def home_pk() -> str:
    return f"HOME#{HOME_ID}"


def query_pending_commands() -> list[dict[str, Any]]:
    response = table().query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={
            ":pk": home_pk(),
            ":sk": "COMMAND#REMOTE#",
        },
        ScanIndexForward=False,
        Limit=max(1, min(REMOTE_COMMAND_QUERY_LIMIT, 100)),
    )
    items = [from_dynamodb(item) for item in response.get("Items", [])]
    return [item for item in items if str(item.get("status")) == "pending"]


def write_command(command: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    updated_at_ms = updates.get("updated_at_ms") or now_ms()
    updated = {
        **command,
        **updates,
        "updatedAtMs": updated_at_ms,
        "updated_at_ms": updated_at_ms,
    }
    table().put_item(Item=to_dynamodb(updated))
    return updated


def mark_processing(command: dict[str, Any]) -> dict[str, Any]:
    timestamp_ms = now_ms()
    return write_command(
        command,
        {
            "status": "processing",
            "claimedBy": "raspberry_pi",
            "claimed_by": "raspberry_pi",
            "claimedAtMs": timestamp_ms,
            "claimed_at_ms": timestamp_ms,
            "claimedAt": ms_to_iso(timestamp_ms),
            "claimed_at_iso": ms_to_iso(timestamp_ms),
            "timezone": TIMEZONE,
        },
    )


def mark_done(command: dict[str, Any], result: dict[str, Any]) -> None:
    timestamp_ms = now_ms()
    write_command(
        command,
        {
            "status": "confirmed" if result.get("success") else "failed",
            "executedAtMs": timestamp_ms,
            "executed_at_ms": timestamp_ms,
            "executedAt": ms_to_iso(timestamp_ms),
            "executed_at_iso": ms_to_iso(timestamp_ms),
            "result": {
                "success": bool(result.get("success")),
                "actual_state": "on" if command.get("command") == "turn_on" else "off",
                "error_code": result.get("error_code"),
                "user_message": result.get("message"),
                "command_id": result.get("command_id"),
                "local_command_id": result.get("command_id"),
                "status": result.get("status"),
                "no_action": bool(result.get("no_action")),
            },
            "message": result.get("message"),
            "localCommandId": result.get("command_id"),
            "local_command_id": result.get("command_id"),
        },
    )


def mark_failed(command: dict[str, Any], error: Any) -> None:
    timestamp_ms = now_ms()
    write_command(
        command,
        {
            "status": "failed",
            "failedAtMs": timestamp_ms,
            "failed_at_ms": timestamp_ms,
            "failedAt": ms_to_iso(timestamp_ms),
            "failed_at_iso": ms_to_iso(timestamp_ms),
            "result": {
                "success": False,
                "actual_state": None,
                "error_code": "PI_COMMAND_RUNNER_ERROR",
                "user_message": "The Raspberry Pi could not execute this remote command.",
                "raw_error": str(error),
            },
            "message": "The Raspberry Pi could not execute this remote command.",
        },
    )


def process_command(command: dict[str, Any]) -> None:
    device_id = str(command.get("device_id") or command.get("deviceId") or "").strip()
    action = str(command.get("command") or command.get("action") or "").strip().lower()
    command_id = str(command.get("command_id") or command.get("commandId") or "")

    if device_id not in ALLOWED_DEVICES or action not in ALLOWED_COMMANDS:
        mark_failed(command, f"Unsupported remote command: {device_id} {action}")
        return

    processing = mark_processing(command)
    log(f"Executing {command_id}: {device_id} {action}")
    try:
        result = execute_local_command(
            device_id,
            action,
            requested_by=str(command.get("requested_by") or command.get("requestedBy") or "cloud_remote_api"),
            source=str(command.get("source") or "cloud_remote_api"),
            emergency=bool(command.get("emergency")),
            alert_id=command.get("alert_id") or command.get("alertId"),
        )
        mark_done(processing, result)
        log(f"Completed {command_id}: {result.get('status')} {result.get('message')}")
    except Exception as error:
        mark_failed(processing, error)
        log(f"Failed {command_id}: {error}")


def run_once() -> int:
    commands = query_pending_commands()
    for command in commands:
        process_command(command)
    return len(commands)


def main() -> int:
    log(f"Started for {HOME_ID}; table={AWS_DYNAMODB_SUMMARIES_TABLE}; region={AWS_REGION}")
    while True:
        started = time.time()
        try:
            count = run_once()
            if count:
                log(f"Processed {count} remote command(s)")
        except ModuleNotFoundError as error:
            log(f"boto3 is required for remote commands: {error}")
        except Exception as error:
            log(f"Remote command polling failed: {error}")
        elapsed = time.time() - started
        time.sleep(max(1, REMOTE_COMMAND_POLL_SECONDS - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
