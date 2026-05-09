from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests


HA_TIMEOUT_SECONDS = float(os.environ.get("HOME_ASSISTANT_TIMEOUT_SECONDS", "5"))


def _log(message: str) -> None:
    print(f"[HOME ASSISTANT] {datetime.now().isoformat()} {message}", flush=True)


class HomeAssistantError(RuntimeError):
    def __init__(self, code: str, user_message: str, raw_error: Any | None = None) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.raw_error = raw_error


def _home_assistant_url() -> str:
    return os.environ.get("HOME_ASSISTANT_URL", "").strip().rstrip("/")


def _home_assistant_token() -> str:
    token = os.environ.get("HOME_ASSISTANT_TOKEN", "").strip()
    if token == "<long_lived_access_token>":
        return ""
    return token


def is_home_assistant_configured() -> bool:
    return bool(_home_assistant_url() and _home_assistant_token())


def _headers() -> dict[str, str]:
    token = _home_assistant_token()
    if not _home_assistant_url() or not token:
        raise HomeAssistantError(
            "HOME_ASSISTANT_UNREACHABLE",
            "Local controller is unavailable.",
            "HOME_ASSISTANT_URL or HOME_ASSISTANT_TOKEN is not configured.",
        )
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, *, json: dict[str, Any] | None = None) -> Any:
    url = f"{_home_assistant_url()}{path}"
    _log(f"{method} {url} body={json or {}}")
    try:
        response = requests.request(
            method,
            url,
            headers=_headers(),
            json=json,
            timeout=HA_TIMEOUT_SECONDS,
        )
    except requests.Timeout as error:
        raise HomeAssistantError(
            "HOME_ASSISTANT_UNREACHABLE",
            "Local controller is unavailable.",
            str(error),
        ) from error
    except requests.RequestException as error:
        raise HomeAssistantError(
            "HOME_ASSISTANT_UNREACHABLE",
            "Local controller is unavailable.",
            str(error),
        ) from error

    if response.status_code == 404:
        _log(f"{method} {url} -> 404 {response.text[:500]}")
        raise HomeAssistantError(
            "HA_ENTITY_NOT_FOUND",
            "Home Assistant switch was not found.",
            response.text,
        )
    if not response.ok:
        _log(f"{method} {url} -> {response.status_code} {response.text[:500]}")
        raise HomeAssistantError(
            "HA_COMMAND_FAILED",
            "Home Assistant switch command failed. Please try again.",
            response.text,
        )
    _log(f"{method} {url} -> {response.status_code}")
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def normalize_ha_state(state: Any) -> str:
    normalized = str(state or "").strip().lower()
    if normalized == "on":
        return "on"
    if normalized == "off":
        return "off"
    if normalized in {"unavailable", "unknown", "none", ""}:
        return "unknown"
    return "unknown"


def get_entity_payload(entity_id: str) -> dict[str, Any]:
    entity = quote(entity_id, safe="")
    payload = _request("GET", f"/api/states/{entity}")
    return payload if isinstance(payload, dict) else {}


def get_entity_state(entity_id: str) -> str:
    payload = get_entity_payload(entity_id)
    state = normalize_ha_state(payload.get("state") if isinstance(payload, dict) else None)
    if state == "unknown":
        raise HomeAssistantError(
            "HA_STATE_UNKNOWN",
            "Home Assistant switch state is unknown.",
            payload,
        )
    return state


def turn_on(entity_id: str) -> Any:
    return _request(
        "POST",
        "/api/services/switch/turn_on",
        json={"entity_id": entity_id},
    )


def turn_off(entity_id: str) -> Any:
    return _request(
        "POST",
        "/api/services/switch/turn_off",
        json={"entity_id": entity_id},
    )


def execute_home_assistant_command(entity_id: str, command: str) -> Any:
    normalized = command.strip().lower()
    if normalized == "turn_on":
        return turn_on(entity_id)
    if normalized == "turn_off":
        return turn_off(entity_id)
    raise HomeAssistantError(
        "HA_COMMAND_FAILED",
        "Home Assistant switch command failed. Please try again.",
        f"Unsupported command: {command}",
    )
