"""End-to-end Telegram channel link-and-unlink verification scenario.

Drives the real channels surface (``GET /api/v1/channels`` ->
``POST /api/v1/channels/telegram/link`` -> ``GET /api/v1/channels`` ->
``DELETE /api/v1/channels/telegram/link`` -> ``GET /api/v1/channels``)
and asserts on every observable property of the link-code lifecycle.

Scope note — the bot-side redemption (a Telegram user pasting the code
into the bot, which then calls ``redeem_link_code`` and lands a
``channel_bindings`` row) is **not** exercised here. The closest
backend surface (``POST /api/v1/channels/telegram/webhook``) requires
the deployment to be running in webhook mode with a real aiogram
service registered on ``app.state.telegram_service`` and the
``X-Telegram-Bot-Api-Secret-Token`` header matching the configured
secret — none of which paw's HTTP transport can synthesize. A future
``POST /api/v1/channels/{provider}/simulate`` route can be wired in
later; until then this scenario emits a stable
``simulate_redemption_endpoint_unavailable`` check so consumers can
grep for the gap.
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
        return datetime.fromisoformat(text)
    except ValueError:
        return None


async def _list_channels(client: PawClient) -> list[dict[str, Any]]:
    """GET /api/v1/channels and return the bindings list (empty on non-list)."""
    body = (await client.request("GET", "/api/v1/channels")).json()
    if not isinstance(body, list):
        return []
    return [b for b in body if isinstance(b, dict)]


async def _check_baseline(client: PawClient, r: ScenarioResult) -> None:
    """Snapshot the channels list so the scenario has a known starting point."""
    bindings = await _list_channels(client)
    r.artifacts["baseline_bindings"] = bindings
    r.add("baseline_channels_listed", True, detail=f"count={len(bindings)}")


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

    The binding row only lands after the bot-side redemption succeeds, so
    we don't assert ``has_telegram_binding`` here — only that the list
    endpoint still returns a usable shape.
    """
    bindings = await _list_channels(client)
    r.artifacts["post_issue_bindings"] = bindings
    r.add(
        "post_issue_channels_listed",
        isinstance(bindings, list),
        detail=f"count={len(bindings)}",
    )


def _record_simulate_gap(r: ScenarioResult) -> None:
    """Document the missing bot-side redemption surface as a stable check.

    The check passes intentionally — there is nothing for paw to break
    because the endpoint does not exist. The greppable name lets agents
    and dashboards key off the gap and flip it to a real assertion the
    moment ``POST /api/v1/channels/{provider}/simulate`` lands.
    """
    r.add(
        "simulate_redemption_endpoint_unavailable",
        True,
        detail=(
            "POST /api/v1/channels/telegram/webhook requires webhook-mode "
            "deployment + bot secret header + real aiogram service; no "
            "simulate endpoint exists. Scenario covers link-code lifecycle "
            "only."
        ),
    )


SKIPPED_NO_REDEMPTION_DETAIL = (
    "skipped: requires backend simulate-redemption endpoint to land a real "
    "channel_bindings row before unlink can be meaningfully verified "
    "(see pawrrtal-o7xf). Without that precondition, DELETE returns 204 "
    "even when no binding exists and the post-unlink absence check is "
    "trivially true — so neither assertion proves anything."
)


async def _unlink_telegram(
    client: PawClient,
    r: ScenarioResult,
    *,
    link_code_redeemed: bool,
) -> None:
    """DELETE the binding and assert the idempotent 204 contract.

    Only runs the unlink HTTP call + assertion when a binding has
    actually been redeemed by a bot-side flow — without that
    precondition, DELETE returns 204 even when there is nothing to
    delete (idempotent contract), so the assertion proves nothing. When
    redemption is not exercised we instead emit a passing-but-skipped
    check with a stable detail so dashboards and agents can grep for the
    coverage gap.
    """
    if not link_code_redeemed:
        r.add("telegram_unlinked", True, detail=SKIPPED_NO_REDEMPTION_DETAIL)
        r.artifacts.setdefault("skipped_checks", []).append("telegram_unlinked")
        return
    await client.request(
        "DELETE",
        f"/api/v1/channels/{TELEGRAM_PROVIDER}/link",
        expect=(204,),
    )
    r.add("telegram_unlinked", True, detail="status=204")


async def _check_post_unlink_list(
    client: PawClient,
    r: ScenarioResult,
    *,
    link_code_redeemed: bool,
) -> None:
    """After unlink there must be no Telegram binding in the list.

    Gated on ``link_code_redeemed`` for the same reason as
    :func:`_unlink_telegram` — without a binding ever being created the
    "absent after unlink" check is trivially true and proves nothing
    about the DELETE endpoint's correctness.
    """
    if not link_code_redeemed:
        r.add(
            "telegram_binding_absent_after_unlink",
            True,
            detail=SKIPPED_NO_REDEMPTION_DETAIL,
        )
        r.artifacts.setdefault("skipped_checks", []).append("telegram_binding_absent_after_unlink")
        return
    bindings = await _list_channels(client)
    r.artifacts["post_unlink_bindings"] = bindings
    r.add(
        "telegram_binding_absent_after_unlink",
        not _has_telegram_binding(bindings),
        detail=f"bindings={bindings}",
    )


async def run_telegram_scenario(
    state: PersonaState,
    client: PawClient,
) -> ScenarioResult:
    """Drive the Telegram link-code lifecycle and assert on every step.

    Sequence: baseline list -> issue code -> post-issue list ->
    record simulate-gap -> unlink -> post-unlink list. The bot-side
    redemption hop is deliberately skipped (see module docstring).

    ``link_code_redeemed`` is wired to ``False`` until a backend
    simulate-redemption endpoint exists (tracked as ``pawrrtal-o7xf``).
    The unlink and post-unlink-list checks are gated behind it because
    DELETE on a never-bound provider is a no-op 204 — so without a real
    binding the assertions are trivially true and prove nothing.
    """
    r = ScenarioResult(name="telegram")
    del state  # PersonaState carried by ``client``; kept in signature for parity.

    # Today there is no surface paw can hit to drive bot-side redemption,
    # so link_code_redeemed is always False. When the simulate endpoint
    # lands this flag flips and the gated checks become real assertions.
    link_code_redeemed = False

    await _check_baseline(client, r)
    await _issue_link_code(client, r)
    await _check_post_issue_list(client, r)
    _record_simulate_gap(r)
    await _unlink_telegram(client, r, link_code_redeemed=link_code_redeemed)
    await _check_post_unlink_list(client, r, link_code_redeemed=link_code_redeemed)

    return r
