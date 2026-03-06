import json
from typing import Any

import requests

from config import (
    EXTERNAL_SYNC_ACCOUNT_OPTIONS,
    EXTERNAL_SYNC_API_KEY,
    EXTERNAL_SYNC_DEBUG_LOG,
    EXTERNAL_SYNC_ENABLED,
    EXTERNAL_SYNC_TIMEOUT,
    EXTERNAL_SYNC_URL,
)


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def _print_debug(title: str, payload: Any) -> None:
    if not EXTERNAL_SYNC_DEBUG_LOG:
        return

    print(f"[external_sync][debug] {title}")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload)


def sync_authorized_result(raw_payload: Any) -> bool:
    """Push authorized registration payload to an external application."""
    if not EXTERNAL_SYNC_ENABLED:
        return False

    if not EXTERNAL_SYNC_URL:
        print("[external_sync] enabled=true but url is empty, skip sync")
        return False

    if not isinstance(raw_payload, (dict, list)):
        print("[external_sync] raw_payload must be dict or list, skip sync")
        return False

    headers = {"Content-Type": "application/json"}
    if EXTERNAL_SYNC_API_KEY:
        headers["x-api-key"] = EXTERNAL_SYNC_API_KEY

    body = {
        "raw_payload": raw_payload,
        "account_options": EXTERNAL_SYNC_ACCOUNT_OPTIONS if isinstance(EXTERNAL_SYNC_ACCOUNT_OPTIONS, dict) else {},
    }

    if EXTERNAL_SYNC_DEBUG_LOG:
        debug_headers = dict(headers)
        if "x-api-key" in debug_headers:
            debug_headers["x-api-key"] = _mask_secret(debug_headers["x-api-key"])
        _print_debug("request.url", EXTERNAL_SYNC_URL)
        _print_debug("request.headers", debug_headers)
        _print_debug("request.body", body)

    try:
        response = requests.post(
            EXTERNAL_SYNC_URL,
            headers=headers,
            json=body,
            timeout=EXTERNAL_SYNC_TIMEOUT,
        )
    except Exception as exc:
        print(f"[external_sync] request error: {exc}")
        return False

    if EXTERNAL_SYNC_DEBUG_LOG:
        _print_debug("response.status", response.status_code)
        _print_debug("response.text", response.text)

    if response.ok:
        print(f"[external_sync] sync success (HTTP {response.status_code})")
        return True

    print(f"[external_sync] sync failed (HTTP {response.status_code}): {response.text}")
    return False
