from __future__ import annotations

import os
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

import requests
from local_command_controller import execute_local_command, sync_home_assistant_device_states

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
REMOTE_COMMAND_POLL_SECONDS = float(os.environ.get("REMOTE_COMMAND_POLL_SECONDS", "2"))
REMOTE_COMMAND_QUERY_LIMIT = int(os.environ.get("REMOTE_COMMAND_QUERY_LIMIT", "25"))
REMOTE_COMMAND_SOURCE = os.environ.get("REMOTE_COMMAND_SOURCE", "dynamodb").strip().lower()
REMOTE_COMMAND_EC2_ACK_STATES = os.environ.get("REMOTE_COMMAND_EC2_ACK_STATES", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
KAHRABAIQ_API_URL = os.environ.get("KAHRABAIQ_API_URL", "").rstrip("/")
PI_ID = os.environ.get("PI_ID", "pi_local_001")
PI_DEVICE_TOKEN = os.environ.get("PI_DEVICE_TOKEN", "")
DEVICE_ALIASES = {
    "ac_breaker": "breaker_01",
    "socket_breaker": "breaker_02",
}
ALLOWED_DEVICES = {
    "breaker_01",
    "breaker_02",
    "ac_breaker",
    "socket_breaker",
    "matter_socket_switch",
    "matter_ac_switch",
    "light_switch",
}
ALLOWED_COMMANDS = {"turn_on", "turn_off"}
STATUS_PENDING = "PENDING"
STATUS_CLAIMED = "CLAIMED"
STATUS_EXECUTING = "EXECUTING"
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"


def log(message: str) -> None:
    print(f"[AWS REMOTE COMMANDS] {datetime.now(BAHRAIN_TZ).isoformat()} {message}", flush=True)


def table():
    import boto3

    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(AWS_DYNAMODB_SUMMARIES_TABLE)


def pi_headers() -> dict[str, str]:
    return {"X-Pi-Id": PI_ID, "X-Device-Token": PI_DEVICE_TOKEN}


def api_request(method: str, path: str, **kwargs: Any) -> requests.Response:
    if not KAHRABAIQ_API_URL:
        raise RuntimeError("KAHRABAIQ_API_URL is required when REMOTE_COMMAND_SOURCE=ec2.")
    return requests.request(method, f"{KAHRABAIQ_API_URL}{path}", timeout=15, **kwargs)


def response_json(response: requests.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as error:
        text = (response.text or "").strip()
        raise RuntimeError(f"Non-JSON response from EC2 ({response.status_code}): {text[:240]}") from error
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected EC2 response ({response.status_code}): {data!r}")
    return data


def response_error_message(response: requests.Response, fallback: str | None = None) -> str:
    try:
        data = response.json()
    except ValueError:
        data = {}
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, dict):
            return str(detail.get("message") or detail)
        if detail:
            return str(detail)
        if data.get("message"):
            return str(data["message"])
    return fallback or response.text or f"HTTP {response.status_code}"


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
    if REMOTE_COMMAND_SOURCE == "ec2":
        started = time.time()
        response = api_request(
            "GET",
            f"/api/pi/{PI_ID}/remote-commands",
            headers=pi_headers(),
            params={"limit": REMOTE_COMMAND_QUERY_LIMIT},
        )
        data = response_json(response)
        if not response.ok or data.get("success") is False:
            raise RuntimeError(data.get("detail") or data.get("message") or response.text)
        commands = [
            item
            for item in data.get("commands") or []
            if isinstance(item, dict) and str(item.get("status")).upper() == STATUS_PENDING
        ]
        elapsed_ms = round((time.time() - started) * 1000)
        if elapsed_ms > 1000 or commands:
            log(f"EC2 pending command poll elapsed_ms={elapsed_ms} count={len(commands)}")
        if commands:
            log(
                "Fetched pending command(s) from EC2: "
                + ", ".join(
                    f"{item.get('command_id') or item.get('commandId')}:{item.get('device_id') or item.get('deviceId')}:{item.get('command') or item.get('action')}"
                    for item in commands
                )
            )
        return commands

    response = table().query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={
            ":pk": home_pk(),
            ":sk": "COMMAND#",
        },
        ScanIndexForward=False,
        Limit=max(1, min(REMOTE_COMMAND_QUERY_LIMIT, 100)),
    )
    items = [from_dynamodb(item) for item in response.get("Items", [])]
    commands = [item for item in items if str(item.get("status")).upper() == STATUS_PENDING]
    if commands:
        log(
            "Fetched pending command(s) from DynamoDB: "
            + ", ".join(
                f"{item.get('command_id') or item.get('commandId')}:{item.get('device_id') or item.get('deviceId')}:{item.get('command') or item.get('action')}"
                for item in commands
            )
        )
    return commands


def write_command(command: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    if REMOTE_COMMAND_SOURCE == "ec2":
        return {**command, **updates}
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
    if REMOTE_COMMAND_SOURCE == "ec2":
        if not REMOTE_COMMAND_EC2_ACK_STATES:
            return {**command, "status": STATUS_CLAIMED}
        command_id = str(command.get("command_id") or command.get("commandId") or "")
        response = api_request(
            "POST",
            f"/api/pi/{PI_ID}/remote-commands/{command_id}/claim",
            headers=pi_headers(),
        )
        if response.status_code == 404:
            log(
                f"EC2 backend does not support remote command claim for {command_id}; "
                "executing command without claim step"
            )
            return {**command, "status": STATUS_CLAIMED}
        data = response_json(response)
        if not response.ok or data.get("success") is False:
            raise RuntimeError(response_error_message(response))
        claimed = data.get("command")
        return claimed if isinstance(claimed, dict) else {**command, "status": STATUS_CLAIMED}

    return write_command(
        command,
        {
            "status": STATUS_CLAIMED,
            "claimedBy": "raspberry_pi",
            "claimed_by": "raspberry_pi",
            "claimedAtMs": timestamp_ms,
            "claimed_at_ms": timestamp_ms,
            "claimedAt": ms_to_iso(timestamp_ms),
            "claimed_at_iso": ms_to_iso(timestamp_ms),
            "timezone": TIMEZONE,
        },
    )


def mark_executing(command: dict[str, Any]) -> dict[str, Any]:
    timestamp_ms = now_ms()
    if REMOTE_COMMAND_SOURCE == "ec2":
        if not REMOTE_COMMAND_EC2_ACK_STATES:
            return {**command, "status": STATUS_EXECUTING}
        command_id = str(command.get("command_id") or command.get("commandId") or "")
        response = api_request(
            "POST",
            f"/api/pi/{PI_ID}/remote-commands/{command_id}/executing",
            headers=pi_headers(),
        )
        if response.status_code == 404:
            log(
                f"EC2 backend does not support remote command executing state for {command_id}; "
                "continuing with local execution"
            )
            return {**command, "status": STATUS_EXECUTING}
        data = response_json(response)
        if not response.ok or data.get("success") is False:
            raise RuntimeError(response_error_message(response))
        updated = data.get("command")
        return updated if isinstance(updated, dict) else {**command, "status": STATUS_EXECUTING}

    return write_command(
        command,
        {
            "status": STATUS_EXECUTING,
            "startedAtMs": timestamp_ms,
            "started_at_ms": timestamp_ms,
            "startedAt": ms_to_iso(timestamp_ms),
            "started_at_iso": ms_to_iso(timestamp_ms),
            "timezone": TIMEZONE,
        },
    )


def mark_done(command: dict[str, Any], result: dict[str, Any]) -> None:
    timestamp_ms = now_ms()
    payload = {
        "success": bool(result.get("success")),
        "message": result.get("message"),
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
    }
    if REMOTE_COMMAND_SOURCE == "ec2":
        command_id = str(command.get("command_id") or command.get("commandId") or "")
        started = time.time()
        response = api_request(
            "POST",
            f"/api/pi/{PI_ID}/remote-commands/{command_id}/complete",
            headers=pi_headers(),
            json=payload,
        )
        data = response_json(response)
        if not response.ok or data.get("success") is False:
            raise RuntimeError(response_error_message(response))
        elapsed_ms = round((time.time() - started) * 1000)
        log(f"EC2 command complete write elapsed_ms={elapsed_ms} id={command_id}")
        return

    write_command(
        command,
        {
            "status": STATUS_SUCCEEDED if result.get("success") else STATUS_FAILED,
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
    payload = {
        "success": False,
        "message": "The Raspberry Pi could not execute this remote command.",
        "result": {
            "success": False,
            "actual_state": None,
            "error_code": "PI_COMMAND_RUNNER_ERROR",
            "user_message": "The Raspberry Pi could not execute this remote command.",
            "raw_error": str(error),
        },
    }
    if REMOTE_COMMAND_SOURCE == "ec2":
        command_id = str(command.get("command_id") or command.get("commandId") or "")
        response = api_request(
            "POST",
            f"/api/pi/{PI_ID}/remote-commands/{command_id}/complete",
            headers=pi_headers(),
            json=payload,
        )
        data = response_json(response)
        if not response.ok or data.get("success") is False:
            raise RuntimeError(response_error_message(response))
        return

    write_command(
        command,
        {
            "status": STATUS_FAILED,
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
    raw_device_id = str(command.get("device_id") or command.get("deviceId") or "").strip()
    device_id = DEVICE_ALIASES.get(raw_device_id, raw_device_id)
    action = str(command.get("command") or command.get("action") or "").strip().lower()
    command_id = str(command.get("command_id") or command.get("commandId") or "")
    requested_at_ms = command.get("requested_at_ms") or command.get("requestedAtMs")
    try:
        queue_age_ms = now_ms() - int(requested_at_ms) if requested_at_ms is not None else None
    except (TypeError, ValueError):
        queue_age_ms = None
    log(
        "Received command "
        f"id={command_id or '<missing>'} device={raw_device_id or '<missing>'} "
        f"canonical_device={device_id or '<missing>'} "
        f"action={action or '<missing>'} source={command.get('source')} "
        f"requested_by={command.get('requested_by') or command.get('requestedBy')} "
        f"queue_age_ms={queue_age_ms if queue_age_ms is not None else '<unknown>'}"
    )

    if raw_device_id not in ALLOWED_DEVICES or action not in ALLOWED_COMMANDS:
        log(f"Rejecting unsupported command id={command_id}: {raw_device_id} {action}")
        mark_failed(command, f"Unsupported remote command: {raw_device_id} {action}")
        return

    processing = mark_processing(command)
    executing = mark_executing(processing)
    execute_started = time.time()
    log(f"Executing {command_id}: {device_id} {action}")
    try:
        result = execute_local_command(
            device_id,
            action,
            requested_by=str(executing.get("requested_by") or executing.get("requestedBy") or "cloud_remote_api"),
            source=str(executing.get("source") or "cloud_remote_api"),
            emergency=bool(executing.get("emergency")),
            alert_id=executing.get("alert_id") or executing.get("alertId"),
        )
        mark_done(executing, result)
        elapsed_ms = round((time.time() - execute_started) * 1000)
        log(f"Completed {command_id}: {result.get('status')} elapsed_ms={elapsed_ms} {result.get('message')}")
    except Exception as error:
        mark_failed(executing, error)
        log(f"Failed {command_id}: {error}")


def run_once() -> int:
    commands = query_pending_commands()
    if not commands:
        sync_home_assistant_device_states()
        return 0
    for command in commands:
        process_command(command)
    return len(commands)


def main() -> int:
    log(
        "Started for "
        f"{HOME_ID}; source={REMOTE_COMMAND_SOURCE}; table={AWS_DYNAMODB_SUMMARIES_TABLE}; region={AWS_REGION}"
    )
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
