"""Chat REST + Pub/Sub REST calls over httpx for the Google Chat channel.

Two Google surfaces, one warm HTTP client (same pattern as
:mod:`app.providers.agy_api.client`):

* **Pub/Sub pull/ack** — the inbound transport. The app *pulls* events
  from a subscription (``:pull``) and acknowledges them (``:acknowledge``),
  so no public webhook is required.
* **Chat messages** — the outbound surface. ``create`` posts a message
  into a space; ``patch`` edits one in place (used to fill the
  placeholder with the final answer).

Every call carries the service-account bearer token from
:func:`app.channels.google_chat.auth.get_access_token`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .auth import get_access_token

logger = logging.getLogger(__name__)

_CHAT_BASE_URL = "https://chat.googleapis.com/v1"
_PUBSUB_BASE_URL = "https://pubsub.googleapis.com/v1"
_HTTP_TIMEOUT_SECONDS = 30.0
_HTTP_MAX_CONNECTIONS = 10
_HTTP_MAX_KEEPALIVE_CONNECTIONS = 5
_HTTP_BAD_REQUEST = 400

# Thread a reply into the originating thread, falling back to a new
# thread when that one no longer exists — the Chat-recommended option
# for app replies in spaces (harmless in 1:1 DMs).
_REPLY_OPTION = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"


@dataclass
class _ClientCache:
    client: httpx.AsyncClient | None = None


_CLIENT_CACHE = _ClientCache()


def _client() -> httpx.AsyncClient:
    """Return a warm shared HTTP client for Google API calls."""
    if _CLIENT_CACHE.client is None or _CLIENT_CACHE.client.is_closed:
        _CLIENT_CACHE.client = httpx.AsyncClient(
            http2=True,
            timeout=_HTTP_TIMEOUT_SECONDS,
            limits=httpx.Limits(
                max_connections=_HTTP_MAX_CONNECTIONS,
                max_keepalive_connections=_HTTP_MAX_KEEPALIVE_CONNECTIONS,
            ),
        )
    return _CLIENT_CACHE.client


async def close_google_chat_client() -> None:
    """Close the shared Google Chat HTTP client (lifespan shutdown)."""
    client = _CLIENT_CACHE.client
    _CLIENT_CACHE.client = None
    if client is not None and not client.is_closed:
        await client.aclose()


async def _headers() -> dict[str, str]:
    token = await get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _short_error(response: httpx.Response) -> str:
    """Return a compact, log-safe summary of a non-2xx API response."""
    return f"{response.status_code}: {response.text[:300]}"


async def pull_messages(
    *,
    project_id: str,
    subscription_id: str,
    max_messages: int,
) -> list[dict[str, Any]]:
    """Pull up to ``max_messages`` events from the subscription.

    Returns the raw ``receivedMessages`` list (each entry carries an
    ``ackId`` and a base64 ``message.data`` payload). Returns an empty
    list when the subscription is idle.
    """
    url = f"{_PUBSUB_BASE_URL}/projects/{project_id}/subscriptions/{subscription_id}:pull"
    response = await _client().post(
        url,
        headers=await _headers(),
        json={"maxMessages": max_messages},
    )
    if response.status_code >= _HTTP_BAD_REQUEST:
        logger.warning("GOOGLE_CHAT_PULL_ERR %s", _short_error(response))
        return []
    received = response.json().get("receivedMessages")
    return received if isinstance(received, list) else []


async def acknowledge(
    *,
    project_id: str,
    subscription_id: str,
    ack_ids: list[str],
) -> bool:
    """Acknowledge processed messages so Pub/Sub stops redelivering them."""
    if not ack_ids:
        return True
    url = f"{_PUBSUB_BASE_URL}/projects/{project_id}/subscriptions/{subscription_id}:acknowledge"
    response = await _client().post(url, headers=await _headers(), json={"ackIds": ack_ids})
    if response.status_code >= _HTTP_BAD_REQUEST:
        logger.warning("GOOGLE_CHAT_ACK_ERR %s", _short_error(response))
        return False
    return True


async def create_message(
    *,
    space_name: str,
    text: str,
    thread_name: str | None = None,
) -> str | None:
    """Create a message in *space_name* and return its resource name.

    The returned ``spaces/{space}/messages/{message}`` name is what
    :func:`update_message` later patches. Returns ``None`` on failure so
    the caller can abort the turn instead of patching a message that was
    never created.
    """
    url = f"{_CHAT_BASE_URL}/{space_name}/messages"
    body: dict[str, Any] = {"text": text}
    params: dict[str, str] = {}
    if thread_name:
        body["thread"] = {"name": thread_name}
        params["messageReplyOption"] = _REPLY_OPTION
    response = await _client().post(url, headers=await _headers(), params=params, json=body)
    if response.status_code >= _HTTP_BAD_REQUEST:
        logger.warning("GOOGLE_CHAT_CREATE_ERR %s", _short_error(response))
        return None
    name = response.json().get("name")
    return str(name) if name else None


async def update_message(*, message_name: str, text: str) -> bool:
    """Patch the ``text`` of an existing message; return success.

    Edit-in-place is the only progressive-update mechanism Chat exposes
    (there is no streaming/typing API). Failures are logged and swallowed
    so a transient patch error can't crash the turn.
    """
    url = f"{_CHAT_BASE_URL}/{message_name}"
    response = await _client().patch(
        url,
        headers=await _headers(),
        params={"updateMask": "text"},
        json={"text": text},
    )
    if response.status_code >= _HTTP_BAD_REQUEST:
        logger.warning("GOOGLE_CHAT_UPDATE_ERR %s", _short_error(response))
        return False
    return True


async def create_card_message(
    *,
    space_name: str,
    cards: list[dict[str, Any]],
    thread_name: str | None = None,
) -> str | None:
    """Post a message containing ``cardsV2`` cards; return its resource name.

    Used by the interactive pickers. Returns ``None`` on failure so the
    caller can fall back to a text reply.
    """
    url = f"{_CHAT_BASE_URL}/{space_name}/messages"
    body: dict[str, Any] = {"cardsV2": cards}
    params: dict[str, str] = {}
    if thread_name:
        body["thread"] = {"name": thread_name}
        params["messageReplyOption"] = _REPLY_OPTION
    response = await _client().post(url, headers=await _headers(), params=params, json=body)
    if response.status_code >= _HTTP_BAD_REQUEST:
        logger.warning("GOOGLE_CHAT_CARD_CREATE_ERR %s", _short_error(response))
        return None
    name = response.json().get("name")
    return str(name) if name else None


async def update_card_message(*, message_name: str, cards: list[dict[str, Any]]) -> bool:
    """Patch a message's ``cardsV2`` in place (used to reflect a button click)."""
    url = f"{_CHAT_BASE_URL}/{message_name}"
    response = await _client().patch(
        url,
        headers=await _headers(),
        params={"updateMask": "cardsV2"},
        json={"cardsV2": cards},
    )
    if response.status_code >= _HTTP_BAD_REQUEST:
        logger.warning("GOOGLE_CHAT_CARD_UPDATE_ERR %s", _short_error(response))
        return False
    return True


async def download_attachment(*, resource_name: str, max_bytes: int) -> bytes | None:
    """Download an ``UPLOADED_CONTENT`` attachment's bytes via the media endpoint.

    Hits ``GET /v1/media/{resourceName}?alt=media`` with the app's bearer
    token (``chat.bot`` scope). Returns ``None`` on HTTP failure or when the
    payload exceeds ``max_bytes`` — so an oversized upload (Chat allows up to
    200 MB) can't blow the memory budget. ``DRIVE_FILE`` attachments are not
    served here; the caller annotates those instead.
    """
    url = f"{_CHAT_BASE_URL}/media/{resource_name}"
    async with _client().stream(
        "GET",
        url,
        headers=await _headers(),
        params={"alt": "media"},
    ) as response:
        if response.status_code >= _HTTP_BAD_REQUEST:
            logger.warning("GOOGLE_CHAT_MEDIA_ERR %s", await _short_stream_error(response))
            return None
        declared = _content_length(response)
        if declared is not None and declared > max_bytes:
            logger.warning("GOOGLE_CHAT_MEDIA_TOO_LARGE bytes=%d cap=%d", declared, max_bytes)
            return None
        return await _read_limited_response(response, max_bytes=max_bytes)


def _content_length(response: httpx.Response) -> int | None:
    raw = response.headers.get("content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _read_limited_response(response: httpx.Response, *, max_bytes: int) -> bytes | None:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            logger.warning("GOOGLE_CHAT_MEDIA_TOO_LARGE bytes=%d cap=%d", total, max_bytes)
            return None
        chunks.append(chunk)
    return b"".join(chunks)


async def _short_stream_error(response: httpx.Response) -> str:
    body = await response.aread()
    return f"{response.status_code}: {body[:300].decode('utf-8', errors='replace')}"
