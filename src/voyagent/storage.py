"""Small key-value store for finished plans and checked opening hours.

Render's free plan has no persistent disk, so files written there vanish on
every restart or redeploy, and with them every shared plan link. When
``UPSTASH_REDIS_REST_URL`` and ``UPSTASH_REDIS_REST_TOKEN`` are set (Upstash's
free Redis tier, no card), records are also written there over its REST API.
Local files stay as a fast cache and as the only store when Upstash isn't set
up (local development).

A storage outage never breaks a plan: remote errors are logged and skipped.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import requests

log = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("VOYAGENT_DATA_DIR", "data"))
REQUEST_TIMEOUT_SECONDS = 10
_KEY = re.compile(r"^[0-9a-z_-]{1,64}$")


def _remote() -> tuple[str, str] | None:
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
    return (url, token) if url and token else None


def _redis(*command: str):
    """Run one Redis command over Upstash's REST API; ``None`` on any failure."""
    remote = _remote()
    if remote is None:
        return None
    url, token = remote
    try:
        response = requests.post(
            url,
            json=list(command),
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json().get("result")
    except (requests.RequestException, ValueError) as exc:
        log.warning("Upstash %s failed: %s", command[0], exc)
        return None


def _path(kind: str, key: str) -> Path:
    return DATA_DIR / kind / f"{key}.json"


def _check(kind: str, key: str) -> None:
    if not (_KEY.match(kind) and _KEY.match(key)):
        raise ValueError(f"Invalid storage key: {kind}/{key}")


def save(kind: str, key: str, data: dict, ttl_seconds: int | None = None) -> None:
    """Store ``data`` under ``kind``/``key`` locally and, if configured, in Upstash."""
    _check(kind, key)
    text = json.dumps(data, ensure_ascii=False)
    path = _path(kind, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        log.warning("Local save of %s/%s failed: %s", kind, key, exc)
    command = ["SET", f"reeltrip:{kind}:{key}", text]
    if ttl_seconds:
        command += ["EX", str(int(ttl_seconds))]
    _redis(*command)


def load(kind: str, key: str) -> dict | None:
    """Return the record, from the local cache first, then from Upstash."""
    _check(kind, key)
    path = _path(kind, key)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    text = _redis("GET", f"reeltrip:{kind}:{key}")
    if not isinstance(text, str):
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    try:  # warm the local cache so the next read skips the network
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return data


def is_remote() -> bool:
    """Whether records survive a restart (Upstash configured)."""
    return _remote() is not None
