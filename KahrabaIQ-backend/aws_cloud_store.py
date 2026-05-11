from __future__ import annotations

import os
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from timestamp_utils import TIMEZONE, ms_to_iso, now_ms


AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-west-1"
AWS_DYNAMODB_SUMMARIES_TABLE = os.environ.get(
    "AWS_DYNAMODB_SUMMARIES_TABLE",
    "SmartEnergySummaries",
)
AWS_DYNAMODB_APP_TABLE = os.environ.get(
    "AWS_DYNAMODB_APP_TABLE",
    "KahrabaIQApp",
)
AWS_IOT_ENDPOINT = os.environ.get("AWS_IOT_ENDPOINT", "").strip()
AWS_IOT_WEBSOCKET_EXPIRES_SECONDS = int(os.environ.get("AWS_IOT_WEBSOCKET_EXPIRES_SECONDS", "900"))
REMOTE_COMMAND_TTL_SECONDS = int(os.environ.get("REMOTE_COMMAND_TTL_SECONDS", "60"))

COMMAND_STATUS_PENDING = "PENDING"
COMMAND_STATUS_CLAIMED = "CLAIMED"
COMMAND_STATUS_EXECUTING = "EXECUTING"
COMMAND_STATUS_SUCCEEDED = "SUCCEEDED"
COMMAND_STATUS_FAILED = "FAILED"
COMMAND_STATUS_EXPIRED = "EXPIRED"
COMMAND_STATUS_CANCELLED = "CANCELLED"
FINAL_COMMAND_STATUSES = {
    COMMAND_STATUS_SUCCEEDED,
    COMMAND_STATUS_FAILED,
    COMMAND_STATUS_EXPIRED,
    COMMAND_STATUS_CANCELLED,
}
ACTIVE_COMMAND_STATUSES = {
    COMMAND_STATUS_PENDING,
    COMMAND_STATUS_CLAIMED,
    COMMAND_STATUS_EXECUTING,
}


def _table():
    import boto3

    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(AWS_DYNAMODB_SUMMARIES_TABLE)


def _app_table():
    import boto3

    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(AWS_DYNAMODB_APP_TABLE)


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


def _normalize_path(path: str) -> str:
    normalized = "/" + path.strip().strip("/")
    return "/" if normalized == "/" else normalized


def _path_sk(path: str) -> str:
    return f"PATH#{_normalize_path(path)}"


def app_get_path(path: str, default: Any = None) -> Any:
    normalized = _normalize_path(path)
    table = _app_table()
    response = table.get_item(Key={"PK": "APP", "SK": _path_sk(normalized)})
    if "Item" in response:
        return _from_dynamodb(response["Item"].get("value"))

    prefix = _path_sk(normalized if normalized == "/" else f"{normalized}/")
    response = table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={":pk": "APP", ":sk": prefix},
    )
    children: dict[str, Any] = {}
    for item in response.get("Items", []):
        child_path = str(item.get("path") or "")
        remainder = child_path[len(normalized.rstrip("/") + "/") :]
        if remainder and "/" not in remainder:
            value = _from_dynamodb(item.get("value"))
            if value is not None:
                children[remainder] = value
    return children if children else default


def app_set_path(path: str, value: Any) -> None:
    normalized = _normalize_path(path)
    table = _app_table()
    key = {"PK": "APP", "SK": _path_sk(normalized)}
    if value is None:
        table.delete_item(Key=key)
        return
    timestamp_ms = now_ms()
    table.put_item(
        Item=_to_dynamodb(
            {
                **key,
                "path": normalized,
                "value": value,
                "updated_at_ms": timestamp_ms,
                "updated_at_iso": ms_to_iso(timestamp_ms),
            }
        )
    )


def app_delete_tree(path: str) -> int:
    normalized = _normalize_path(path)
    table = _app_table()
    keys = [{"PK": "APP", "SK": _path_sk(normalized)}]
    prefix = _path_sk(normalized if normalized == "/" else f"{normalized}/")
    query_kwargs: dict[str, Any] = {
        "KeyConditionExpression": "PK = :pk AND begins_with(SK, :sk)",
        "ExpressionAttributeValues": {":pk": "APP", ":sk": prefix},
    }
    while True:
        response = table.query(**query_kwargs)
        keys.extend({"PK": item["PK"], "SK": item["SK"]} for item in response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        query_kwargs["ExclusiveStartKey"] = last_key

    with table.batch_writer() as batch:
        for key in keys:
            batch.delete_item(Key=key)
    return len(keys)


def app_update_path(path: str, value: dict[str, Any]) -> None:
    existing = app_get_path(path, {})
    if not isinstance(existing, dict):
        existing = {}
    app_set_path(path, {**existing, **value})


def home_pk(home_id: str) -> str:
    return f"HOME#{home_id}"


def summary_prefix(period: str) -> str:
    normalized = period.strip().upper()
    if normalized not in {"HOURLY", "DAILY", "MONTHLY"}:
        raise ValueError("period must be hourly, daily, or monthly")
    return f"SUMMARY#{normalized}#"


def summary_range_key(period: str, timestamp_ms: int) -> str:
    normalized = period.strip().upper()
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=ZoneInfo(TIMEZONE))
    if normalized == "HOURLY":
        return f"SUMMARY#HOURLY#{dt.strftime('%Y-%m-%dT%H')}"
    if normalized == "DAILY":
        return f"SUMMARY#DAILY#{dt.strftime('%Y-%m-%d')}"
    if normalized == "MONTHLY":
        return f"SUMMARY#MONTHLY#{dt.strftime('%Y-%m')}"
    raise ValueError("period must be hourly, daily, or monthly")


def _summary_bucket(period: str, item: dict[str, Any]) -> int:
    return int(
        item.get("startAtMs")
        or item.get("start_at_ms")
        or item.get("timestamp_ms")
        or item.get("updated_at_ms")
        or 0
    )


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


def query_summaries_between(
    home_id: str,
    period: str,
    *,
    start_at_ms: int | None = None,
    end_at_ms: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if start_at_ms is not None and end_at_ms is not None:
        response = _table().query(
            KeyConditionExpression="PK = :pk AND SK BETWEEN :start_sk AND :end_sk",
            ExpressionAttributeValues={
                ":pk": home_pk(home_id),
                ":start_sk": summary_range_key(period, int(start_at_ms)),
                ":end_sk": summary_range_key(period, int(end_at_ms)),
            },
            ScanIndexForward=False,
            Limit=max(1, min(int(limit), 744)),
        )
        items = [_from_dynamodb(item) for item in response.get("Items", [])]
        items.sort(key=lambda item: _summary_bucket(period, item), reverse=True)
        return items

    items = query_summaries(home_id, period, limit=limit)
    filtered = []
    for item in items:
        bucket = _summary_bucket(period, item)
        if start_at_ms is not None and bucket < start_at_ms:
            continue
        if end_at_ms is not None and bucket > end_at_ms:
            continue
        filtered.append(item)
    filtered.sort(key=lambda item: _summary_bucket(period, item), reverse=True)
    return filtered


def latest_summary(home_id: str, period: str = "hourly") -> dict[str, Any]:
    items = query_summaries(home_id, period, limit=1)
    return items[0] if items else {}


def normalize_command_status(status: str | None, *, default: str = COMMAND_STATUS_PENDING) -> str:
    normalized = str(status or "").strip().upper()
    aliases = {
        "PENDING": COMMAND_STATUS_PENDING,
        "CLAIMED": COMMAND_STATUS_CLAIMED,
        "PROCESSING": COMMAND_STATUS_CLAIMED,
        "EXECUTING": COMMAND_STATUS_EXECUTING,
        "RUNNING": COMMAND_STATUS_EXECUTING,
        "SUCCEEDED": COMMAND_STATUS_SUCCEEDED,
        "SUCCESS": COMMAND_STATUS_SUCCEEDED,
        "CONFIRMED": COMMAND_STATUS_SUCCEEDED,
        "COMPLETED": COMMAND_STATUS_SUCCEEDED,
        "FAILED": COMMAND_STATUS_FAILED,
        "ERROR": COMMAND_STATUS_FAILED,
        "EXPIRED": COMMAND_STATUS_EXPIRED,
        "CANCELLED": COMMAND_STATUS_CANCELLED,
        "CANCELED": COMMAND_STATUS_CANCELLED,
    }
    return aliases.get(normalized, default)


def command_sort_key(item: dict[str, Any]) -> int:
    return int(
        item.get("requestedAtMs")
        or item.get("requested_at_ms")
        or item.get("updatedAtMs")
        or item.get("updated_at_ms")
        or 0
    )


def command_sort_key_value(item: dict[str, Any], status: str | None = None) -> str:
    normalized_status = normalize_command_status(status or item.get("status"))
    timestamp_ms = command_sort_key(item)
    command_id = str(item.get("commandId") or item.get("command_id") or uuid.uuid4().hex)
    return f"COMMAND#{normalized_status}#{timestamp_ms:013d}#{command_id}"


def command_is_expired(item: dict[str, Any], *, now_ms_value: int | None = None) -> bool:
    normalized_status = normalize_command_status(item.get("status"))
    if normalized_status in FINAL_COMMAND_STATUSES:
        return False
    expires_at_ms = int(item.get("expiresAtMs") or item.get("expires_at_ms") or 0)
    if expires_at_ms <= 0:
        return False
    if now_ms_value is None:
        now_ms_value = now_ms()
    return now_ms_value >= expires_at_ms


def _query_command_status_items(home_id: str, status: str, limit: int = 50) -> list[dict[str, Any]]:
    response = _table().query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={
            ":pk": home_pk(home_id),
            ":sk": f"COMMAND#{status}#",
        },
        ScanIndexForward=False,
        Limit=max(1, min(int(limit), 100)),
    )
    return [_from_dynamodb(item) for item in response.get("Items", [])]


def _query_command_items(home_id: str, limit: int = 50) -> list[dict[str, Any]]:
    statuses = [
        COMMAND_STATUS_PENDING,
        COMMAND_STATUS_CLAIMED,
        COMMAND_STATUS_EXECUTING,
        COMMAND_STATUS_SUCCEEDED,
        COMMAND_STATUS_FAILED,
        COMMAND_STATUS_EXPIRED,
        COMMAND_STATUS_CANCELLED,
    ]
    by_id: dict[str, dict[str, Any]] = {}
    for status in statuses:
        for item in _query_command_status_items(home_id, status, limit=limit):
            command_id = str(item.get("commandId") or item.get("command_id") or item.get("SK"))
            by_id[command_id] = item
    items = list(by_id.values())
    items.sort(key=command_sort_key, reverse=True)
    return items[: max(1, min(int(limit), 100))]


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
    expires_at_ms = timestamp_ms + REMOTE_COMMAND_TTL_SECONDS * 1000
    item = {
        "PK": home_pk(home_id),
        "SK": f"COMMAND#{COMMAND_STATUS_PENDING}#{timestamp_ms:013d}#{command_id}",
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
        "status": COMMAND_STATUS_PENDING,
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
        "expiresAtMs": expires_at_ms,
        "expires_at_ms": expires_at_ms,
        "expiresAt": ms_to_iso(expires_at_ms),
        "expires_at_iso": ms_to_iso(expires_at_ms),
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
    items = _query_command_items(home_id, limit=limit)
    now_ms_value = now_ms()
    normalized_items = []
    for item in items:
        normalized = {**item, "status": normalize_command_status(item.get("status"))}
        if command_is_expired(normalized, now_ms_value=now_ms_value):
            normalized = update_remote_command(
                home_id,
                str(normalized.get("commandId") or normalized.get("command_id") or ""),
                {
                    "status": COMMAND_STATUS_EXPIRED,
                    "result": {
                        **_from_dynamodb(normalized.get("result") or {}),
                        "success": False,
                        "error_code": "COMMAND_EXPIRED",
                        "user_message": "Command expired before the Raspberry Pi claimed it.",
                    },
                    "message": "Command expired before the Raspberry Pi claimed it.",
                    "expiredAtMs": now_ms_value,
                    "expired_at_ms": now_ms_value,
                    "expiredAt": ms_to_iso(now_ms_value),
                    "expired_at_iso": ms_to_iso(now_ms_value),
                },
            )
        normalized_items.append(normalized)
    normalized_items.sort(key=command_sort_key, reverse=True)
    return normalized_items


def find_remote_command(home_id: str, command_id: str) -> dict[str, Any]:
    for item in _query_command_items(home_id, limit=100):
        if str(item.get("commandId") or item.get("command_id")) == command_id:
            return {**item, "status": normalize_command_status(item.get("status"))}
    return {}


def update_remote_command(home_id: str, command_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    command = find_remote_command(home_id, command_id)
    if not command:
        return {}
    timestamp_ms = now_ms()
    normalized_status = normalize_command_status(updates.get("status") or command.get("status"))
    updated = {
        **command,
        **updates,
        "status": normalized_status,
        "updatedAtMs": timestamp_ms,
        "updated_at_ms": timestamp_ms,
        "updatedAt": ms_to_iso(timestamp_ms),
        "updated_at_iso": ms_to_iso(timestamp_ms),
    }
    previous_key = {"PK": command["PK"], "SK": command["SK"]}
    updated["SK"] = command_sort_key_value(updated, normalized_status)
    _table().put_item(Item=_to_dynamodb(updated))
    if updated["SK"] != command["SK"]:
        _table().delete_item(Key=previous_key)
    return updated


def live_topic(home_id: str) -> str:
    return os.environ.get("AWS_IOT_LIVE_TOPIC", f"homes/{home_id}/live/state")


def ai_prediction_sk(timestamp_ms: int) -> str:
    return f"AI#PREDICTION#{timestamp_ms:013d}"


def ai_alert_sk(timestamp_ms: int, alert_id: str) -> str:
    return f"AI#ALERT#{timestamp_ms:013d}#{alert_id}"


def ai_suggestion_sk(timestamp_ms: int, suggestion_id: str) -> str:
    return f"AI#SUGGESTION#{timestamp_ms:013d}#{suggestion_id}"


def store_ai_result(
    home_id: str,
    result: dict[str, Any],
    *,
    notifications: list[dict[str, Any]] | None = None,
    alerts: list[dict[str, Any]] | None = None,
    suggestions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    timestamp_ms = int(result.get("created_at_ms") or result.get("created_at") or now_ms())
    pk = home_pk(home_id)
    base_item = {
        **result,
        "PK": pk,
        "home_id": home_id,
        "type": "ai_result",
        "source": result.get("source") or "ec2_ai_inference",
        "notifications": notifications or result.get("notifications") or [],
        "alerts": alerts or result.get("alerts") or [],
        "suggestions": suggestions or result.get("suggestions") or [],
        "updated_at_ms": timestamp_ms,
        "updated_at_iso": ms_to_iso(timestamp_ms),
    }

    table = _app_table()
    latest_item = {**base_item, "SK": "AI#LATEST"}
    history_item = {**base_item, "SK": ai_prediction_sk(timestamp_ms)}
    table.put_item(Item=_to_dynamodb(latest_item))
    table.put_item(Item=_to_dynamodb(history_item))

    for notification in notifications or []:
        notification_id = str(notification.get("id") or uuid.uuid4().hex)
        table.put_item(
            Item=_to_dynamodb(
                {
                    **notification,
                    "PK": pk,
                    "SK": ai_alert_sk(timestamp_ms, notification_id),
                    "type": "ai_notification",
                    "home_id": home_id,
                    "source": "ai",
                }
            )
        )

    for alert in alerts or []:
        alert_id = str(alert.get("id") or alert.get("alert_id") or uuid.uuid4().hex)
        table.put_item(
            Item=_to_dynamodb(
                {
                    **alert,
                    "PK": pk,
                    "SK": ai_alert_sk(timestamp_ms, alert_id),
                    "type": "ai_alert",
                    "home_id": home_id,
                    "source": "ai",
                }
            )
        )

    for suggestion in suggestions or []:
        suggestion_id = str(suggestion.get("id") or suggestion.get("suggestion_id") or uuid.uuid4().hex)
        table.put_item(
            Item=_to_dynamodb(
                {
                    **suggestion,
                    "PK": pk,
                    "SK": ai_suggestion_sk(timestamp_ms, suggestion_id),
                    "type": "ai_suggestion",
                    "home_id": home_id,
                    "source": "ai",
                }
            )
        )

    return _from_dynamodb(latest_item)


def get_ai_latest(home_id: str) -> dict[str, Any]:
    response = _app_table().get_item(Key={"PK": home_pk(home_id), "SK": "AI#LATEST"})
    return _from_dynamodb(response.get("Item", {}))


def query_ai_history(home_id: str, limit: int = 24) -> list[dict[str, Any]]:
    response = _app_table().query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={":pk": home_pk(home_id), ":sk": "AI#PREDICTION#"},
        ScanIndexForward=False,
        Limit=max(1, min(int(limit), 100)),
    )
    return [_from_dynamodb(item) for item in response.get("Items", [])]


def query_ai_notifications(home_id: str, limit: int = 50) -> list[dict[str, Any]]:
    response = _app_table().query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={":pk": home_pk(home_id), ":sk": "AI#ALERT#"},
        ScanIndexForward=False,
        Limit=max(1, min(int(limit), 100)),
    )
    return [_from_dynamodb(item) for item in response.get("Items", [])]


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
