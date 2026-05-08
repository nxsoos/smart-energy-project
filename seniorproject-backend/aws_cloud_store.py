from __future__ import annotations

import os
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

from timestamp_utils import TIMEZONE, ms_to_iso, now_ms


AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-west-1"
AWS_DYNAMODB_SUMMARIES_TABLE = os.environ.get(
    "AWS_DYNAMODB_SUMMARIES_TABLE",
    "SmartEnergySummaries",
)
AWS_IOT_ENDPOINT = os.environ.get("AWS_IOT_ENDPOINT", "").strip()
AWS_IOT_WEBSOCKET_EXPIRES_SECONDS = int(os.environ.get("AWS_IOT_WEBSOCKET_EXPIRES_SECONDS", "900"))


def _table():
    import boto3

    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(AWS_DYNAMODB_SUMMARIES_TABLE)


def _from_dynamodb(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {key: _from_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_dynamodb(item) for item in value]
    return value


def _to_dynamodb(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_dynamodb(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_to_dynamodb(item) for item in value if item is not None]
    return value


def home_pk(home_id: str) -> str:
    return f"HOME#{home_id}"


def summary_prefix(period: str) -> str:
    normalized = period.strip().upper()
    if normalized not in {"HOURLY", "DAILY"}:
        raise ValueError("period must be hourly or daily")
    return f"SUMMARY#{normalized}#"


def query_summaries(home_id: str, period: str, limit: int = 24) -> list[dict[str, Any]]:
    response = _table().query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={
            ":pk": home_pk(home_id),
            ":sk": summary_prefix(period),
        },
        ScanIndexForward=False,
        Limit=max(1, min(int(limit), 100)),
    )
    return [_from_dynamodb(item) for item in response.get("Items", [])]


def latest_summary(home_id: str, period: str = "hourly") -> dict[str, Any]:
    items = query_summaries(home_id, period, limit=1)
    return items[0] if items else {}


def create_remote_command(
    home_id: str,
    device_id: str,
    command: str,
    *,
    requested_by: str = "flutter_app",
    source: str = "cloud_remote_api",
    emergency: bool = False,
    alert_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    timestamp_ms = now_ms()
    command_id = f"cmd_{timestamp_ms}_{device_id}_{uuid.uuid4().hex[:8]}"
    target_state = "on" if command == "turn_on" else "off"
    item = {
        "PK": home_pk(home_id),
        "SK": f"COMMAND#REMOTE#{timestamp_ms}#{command_id}",
        "type": "remote_command",
        "commandId": command_id,
        "command_id": command_id,
        "homeId": home_id,
        "home_id": home_id,
        "deviceId": device_id,
        "device_id": device_id,
        "command": command,
        "action": command,
        "targetState": target_state,
        "target_state": target_state,
        "status": "pending",
        "requestedBy": requested_by,
        "requested_by": requested_by,
        "source": source,
        "emergency": emergency,
        "alertId": alert_id,
        "alert_id": alert_id,
        "reason": reason,
        "requestedAtMs": timestamp_ms,
        "requested_at_ms": timestamp_ms,
        "requestedAt": ms_to_iso(timestamp_ms),
        "requested_at_iso": ms_to_iso(timestamp_ms),
        "timezone": TIMEZONE,
        "result": {
            "success": None,
            "actual_state": None,
            "error_code": None,
            "user_message": None,
        },
    }
    _table().put_item(Item=_to_dynamodb(item))
    return item


def query_recent_remote_commands(home_id: str, limit: int = 50) -> list[dict[str, Any]]:
    response = _table().query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={
            ":pk": home_pk(home_id),
            ":sk": "COMMAND#REMOTE#",
        },
        ScanIndexForward=False,
        Limit=max(1, min(int(limit), 100)),
    )
    return [_from_dynamodb(item) for item in response.get("Items", [])]


def find_remote_command(home_id: str, command_id: str) -> dict[str, Any]:
    for item in query_recent_remote_commands(home_id, limit=100):
        if str(item.get("commandId") or item.get("command_id")) == command_id:
            return item
    return {}


def live_topic(home_id: str) -> str:
    return os.environ.get("AWS_IOT_LIVE_TOPIC", f"homes/{home_id}/live/state")


def create_iot_websocket_config(home_id: str, client_id: str | None = None) -> dict[str, Any]:
    if not AWS_IOT_ENDPOINT:
        raise RuntimeError("AWS_IOT_ENDPOINT is required.")

    import boto3
    from botocore.auth import SigV4QueryAuth
    from botocore.awsrequest import AWSRequest

    session = boto3.Session(region_name=AWS_REGION)
    credentials = session.get_credentials()
    if credentials is None:
        raise RuntimeError("AWS credentials are required to sign the IoT WebSocket URL.")

    request = AWSRequest(method="GET", url=f"wss://{AWS_IOT_ENDPOINT}/mqtt")
    SigV4QueryAuth(
        credentials.get_frozen_credentials(),
        "iotdevicegateway",
        AWS_REGION,
        expires=AWS_IOT_WEBSOCKET_EXPIRES_SECONDS,
    ).add_auth(request)

    signed_url = request.url
    parsed = urlparse(signed_url)
    websocket_path = parsed.path
    if parsed.query:
        websocket_path = f"{websocket_path}?{parsed.query}"

    timestamp_ms = now_ms()
    return {
        "endpoint": AWS_IOT_ENDPOINT,
        "signedUrl": signed_url,
        "websocketPath": websocket_path,
        "topic": live_topic(home_id),
        "clientId": client_id or f"smart-energy-app-{home_id}-{uuid.uuid4().hex[:8]}",
        "expiresInSeconds": AWS_IOT_WEBSOCKET_EXPIRES_SECONDS,
        "createdAtMs": timestamp_ms,
        "createdAt": ms_to_iso(timestamp_ms),
    }
