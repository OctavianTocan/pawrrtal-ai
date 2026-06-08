"""End-to-end Telegram channel verification scenario.

The scenario checks three operator-relevant surfaces without deleting an
existing binding: channel listing, link-code issuance, and the hidden
``/api/v1/channels/telegram/simulate`` route that feeds a synthetic
``/status`` command through the live bot dispatcher. It also verifies
the read-only diagnostic endpoint so a failed bot smoke has a traceable
follow-up path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.cli.paw.config import PersonaState
from app.cli.paw.http import PawClient
from app.cli.paw.verify.scenarios import ScenarioResult

# Provider key the backend uses for ``ChannelBindingRead.provider`` and the
# ``/api/v1/channels/{provider}/link`` path segment. Single source so a
# future Slack/iMessage sibling lands without scattered string literals.
TELEGRAM_PROVIDER = "telegram"
HTTP_OK = 200
HTTP_NOT_FOUND = 404
STATUS_SIMULATION_TEXT = "/status"

# Minimum chars in the plaintext link code surfaced by the backend. The
# generator emits the raw base32-ish code well above this; a few chars is
# enough to catch an empty-string regression without pinning the format.
MIN_LINK_CODE_LENGTH = 4


def _has_telegram_binding(bindings: list[dict[str, Any]]) -> bool:
    """Return True iff one of the listed bindings is for Telegram."""
    return any(isinstance(b, dict) and b.get("provider") == TELEGRAM_PROVIDER for b in bindings)


def _parse_iso8601(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp returned by the API; tolerate ``Z`` suffix.

    Returns ``None`` if the value is missing or malformed so the caller
    can flip the corresponding check to ``passed=False`` with a stable
    detail rather than throwing.
    """
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


async def _list_channels(client: PawClient) -> list[dict[str, Any]]:
    """GET /api/v1/channels and return the bindings list (empty on non-list)."""
    body = (await client.request("GET", "/api/v1/channels")).json()
    if not isinstance(body, list):
        return []
    return [b for b in body if isinstance(b, dict)]


async def _check_baseline(client: PawClient, r: ScenarioResult) -> list[dict[str, Any]]:
    """Snapshot the channels list so the scenario has a known starting point."""
    bindings = await _list_channels(client)
    r.artifacts["baseline_bindings"] = bindings
    r.add("baseline_channels_listed", True, detail=f"count={len(bindings)}")
    return bindings


async def _issue_link_code(client: PawClient, r: ScenarioResult) -> dict[str, Any]:
    """POST a fresh link code and assert on shape + expiry.

    Returns the parsed code envelope so the caller can record artifacts.
    """
    resp = await client.request(
        "POST",
        f"/api/v1/channels/{TELEGRAM_PROVIDER}/link",
        expect=(200, 201),
    )
    parsed = resp.json()
    payload = parsed if isinstance(parsed, dict) else {}
    r.artifacts["link_code_response"] = payload

    code = payload.get("code") if isinstance(payload, dict) else None
    r.add(
        "link_code_issued",
        isinstance(code, str) and len(code) >= MIN_LINK_CODE_LENGTH,
        detail=f"code_len={len(code) if isinstance(code, str) else 'N/A'}",
    )

    expires_at = _parse_iso8601(payload.get("expires_at") if isinstance(payload, dict) else None)
    now = datetime.now(UTC)
    r.add(
        "link_code_expiry_future",
        expires_at is not None and expires_at > now,
        detail=f"expires_at={payload.get('expires_at') if isinstance(payload, dict) else None!r}",
    )
    return payload if isinstance(payload, dict) else {}


async def _check_post_issue_list(client: PawClient, r: ScenarioResult) -> None:
    """After issuing the code the bindings list shape must still be valid.

    The verifier checks for an existing binding separately because issuing
    a link code should not mutate the current binding list.
    """
    bindings = await _list_channels(client)
    r.artifacts["post_issue_bindings"] = bindings
    r.add(
        "post_issue_channels_listed",
        isinstance(bindings, list),
        detail=f"count={len(bindings)}",
    )


async def _simulate_status_command(
    client: PawClient,
    r: ScenarioResult,
    *,
    bindings: list[dict[str, Any]],
) -> None:
    """Feed a deterministic Telegram command through the simulate route."""
    binding_available = _has_telegram_binding(bindings)
    r.add(
        "telegram_binding_available",
        binding_available,
        detail=f"telegram_bindings={sum(1 for row in bindings if row.get('provider') == TELEGRAM_PROVIDER)}",
    )
    if not binding_available:
        r.add(
            "telegram_status_command_simulated",
            False,
            detail="No Telegram binding exists for this user.",
        )
        return

    response = await client.request(
        "POST",
        f"/api/v1/channels/{TELEGRAM_PROVIDER}/simulate",
        json_body={"text": STATUS_SIMULATION_TEXT},
        expect=(HTTP_OK, HTTP_NOT_FOUND),
    )
    if response.status_code == HTTP_NOT_FOUND:
        r.add(
            "telegram_status_command_simulated",
            False,
            detail=f"status=404 body={response.text[:200]}",
        )
        return

    payload = response.json()
    body = payload if isinstance(payload, dict) else {}
    r.artifacts["simulate_status_response"] = body
    r.add(
        "telegram_status_command_simulated",
        body.get("accepted") is True,
        detail=f"response={body}",
    )
    r.add(
        "telegram_simulate_targets_bound_chat",
        bool(body.get("chat_id") and body.get("external_user_id")),
        detail=f"chat_id={body.get('chat_id')!r} external_user_id={body.get('external_user_id')!r}",
    )


async def _check_diagnostics(client: PawClient, r: ScenarioResult) -> None:
    """Verify the operator diagnostic endpoint returns structured state."""
    response = await client.request(
        "GET",
        f"/api/v1/channels/{TELEGRAM_PROVIDER}/diagnose",
        params={"limit": 5},
        expect=(HTTP_OK, HTTP_NOT_FOUND),
    )
    if response.status_code == HTTP_NOT_FOUND:
        r.add(
            "telegram_diagnostics_available",
            False,
            detail=f"status=404 body={response.text[:200]}",
        )
        return

    payload = response.json()
    body = payload if isinstance(payload, dict) else {}
    r.artifacts["diagnostics"] = body
    r.add(
        "telegram_diagnostics_available",
        {"configured", "mode", "bindings", "recent_messages"}.issubset(body.keys()),
        detail=f"keys={sorted(body.keys())}",
    )


async def run_telegram_scenario(
    state: PersonaState,
    client: PawClient,
) -> ScenarioResult:
    """Drive Telegram channel checks without mutating existing bindings."""
    r = ScenarioResult(name="telegram")
    del state  # PersonaState carried by ``client``; kept in signature for parity.

    bindings = await _check_baseline(client, r)
    await _issue_link_code(client, r)
    await _check_post_issue_list(client, r)
    await _simulate_status_command(client, r, bindings=bindings)
    await _check_diagnostics(client, r)

    return r
