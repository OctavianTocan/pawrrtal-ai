"""paw lcm — LCM observability (read-only).

Drives the LCM debug surface exposed by ``backend/app/api/lcm.py``. The
endpoint is a microscope on the existing ``lcm_context_items`` table:
it does not mutate state, does not trigger model calls, and does not
alter compaction. Access is gated per-user via the same conversation
ownership check the rest of the API uses, so a caller can never read
another user's context even if they fabricate a conversation UUID.

Verbs:

- ``paw lcm context <conv_id>``
  GET /api/v1/lcm/conversations/{conversation_id}/context

The single verb returns the assembled pre-turn context — resolved
messages + summaries with ordinal, role, token estimate, summary depth
and source count — so operators can diagnose what the agent actually
saw on the last turn.

The wider LCM CLI surface (``paw lcm memories``, ``paw lcm lineages``,
``paw lcm dream``) is deferred until the backend HTTP surface lands —
tracked in follow-up bean ``pawrrtal-x9u4``. Only ``context`` ships
today because it is the only LCM verb that maps to an existing
endpoint.

Output modes mirror ``paw audit`` / ``paw jobs``: ``--json``,
``--plain``, default human-readable. Exit codes come from
``app.cli.paw.errors``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import typer

from app.cli.paw.config import PersonaState
from app.cli.paw.errors import LocalError
from app.cli.paw.http import PawClient
from app.cli.paw.output import emit_human, emit_json, emit_plain_rows

# Backend constraint from ``app/api/lcm.py``: fresh_tail_count is
# ``Query(ge=0, le=1024)``. Reject out-of-range inputs client-side so
# we surface a friendly hint instead of a 422.
FRESH_TAIL_MIN = 0
FRESH_TAIL_MAX = 1024

# Width budget for the per-item preview rendered in the human view.
# Wide enough to read the first sentence on an 80-col terminal,
# narrow enough that several rows still fit without wrapping.
ITEM_PREVIEW_WIDTH = 60

app = typer.Typer(
    help="LCM observability — inspect the pre-turn assembled context (read-only).",
    no_args_is_help=True,
)


def _require_one_output_mode(*, json_out: bool, plain: bool) -> None:
    """Reject simultaneous --json + --plain. Mutually exclusive by design."""
    if json_out and plain:
        raise LocalError(
            "Pass --json or --plain, not both.",
            hint="--json for machine output, --plain for TSV.",
        )


def _load_state(profile: str) -> PersonaState:
    """Load persona state for ``profile``; surface a friendly hint when absent."""
    try:
        return PersonaState.load(profile)
    except FileNotFoundError as e:
        raise LocalError(
            f"No persona state for profile {profile!r}.",
            hint="Run `paw login` first.",
        ) from e


def _validate_fresh_tail_count(value: int | None) -> None:
    """Reject --fresh-tail-count outside the backend's accepted range."""
    if value is None:
        return
    if value < FRESH_TAIL_MIN or value > FRESH_TAIL_MAX:
        raise LocalError(
            f"Bad --fresh-tail-count {value}: expected {FRESH_TAIL_MIN}..{FRESH_TAIL_MAX}.",
            hint=f"--fresh-tail-count <int between {FRESH_TAIL_MIN} and {FRESH_TAIL_MAX}>",
        )


def _truncate(text: str | None, width: int) -> str:
    """Trim a preview string to ``width`` chars without breaking the table."""
    if not text:
        return ""
    body = text.replace("\n", " ")
    if len(body) <= width:
        return body
    return body[: width - 1] + "…"


@app.command("context")
def lcm_context(
    conversation_id: str = typer.Argument(
        ...,
        help="Conversation UUID to inspect (must belong to the authenticated persona).",
    ),
    fresh_tail_count: int | None = typer.Option(
        None,
        "--fresh-tail-count",
        help=(
            f"Override the configured fresh-tail window ({FRESH_TAIL_MIN}..{FRESH_TAIL_MAX}). "
            "Re-applies the cap to stored items for preview; does not mutate live assembly."
        ),
    ),
    profile: str = typer.Option("default", "--profile"),
    json_out: bool = typer.Option(False, "--json"),
    plain: bool = typer.Option(False, "--plain"),
) -> None:
    """Return the assembled LCM context for one conversation.

    The response describes what the agent saw on the most recent turn —
    item ordinal, kind (``message`` / ``summary``), role, token estimate
    plus summary depth / kind / source count for compacted rows.

    Examples:
      paw lcm context 6c87aa72-1b3c-4f0e-9f4d-2b8a7c5a1d11
      paw lcm context 6c87... --fresh-tail-count 32 --json
      paw lcm context 6c87... --plain
    """
    _require_one_output_mode(json_out=json_out, plain=plain)
    _validate_fresh_tail_count(fresh_tail_count)
    state = _load_state(profile)
    response = asyncio.run(
        _fetch_context(state, conversation_id, fresh_tail_count=fresh_tail_count)
    )

    if json_out:
        emit_json(response)
        return
    if plain:
        emit_plain_rows(
            (
                item.get("ordinal"),
                item.get("item_kind"),
                item.get("item_id"),
                item.get("role") or "-",
                item.get("token_count") if item.get("token_count") is not None else "-",
                item.get("summary_depth") if item.get("summary_depth") is not None else "-",
                item.get("summary_kind") or "-",
                item.get("source_count") if item.get("source_count") is not None else "-",
                _truncate(item.get("preview"), ITEM_PREVIEW_WIDTH),
            )
            for item in response.get("items", [])
        )
        return

    _emit_context_human(response)


def _emit_context_human(response: dict[str, Any]) -> None:
    """Human view: summary header + one line per assembled row."""
    settings = response.get("settings") or {}
    emit_human(
        f"Context for conversation {response.get('conversation_id')}\n"
        f"  lcm_enabled:      {response.get('lcm_enabled')}\n"
        f"  fresh_tail_count: {response.get('fresh_tail_count')}\n"
        f"  items:            {response.get('item_count')} "
        f"({response.get('message_count')} message / "
        f"{response.get('summary_count')} summary)\n"
        f"  estimated_tokens: {response.get('estimated_tokens')}\n"
        f"  settings:         leaf_chunk_tokens={settings.get('leaf_chunk_tokens')} "
        f"incremental_max_depth={settings.get('incremental_max_depth')}"
    )
    items = response.get("items") or []
    if not items:
        emit_human("  (no LCM context items yet)")
        return
    emit_human("")
    emit_human(f"{'ORD':>4}  {'KIND':<8}  {'ROLE':<10}  {'TOK':>5}  PREVIEW")
    for item in items:
        ordinal = item.get("ordinal")
        kind = str(item.get("item_kind") or "")[:8]
        role = str(item.get("role") or "-")[:10]
        tokens = item.get("token_count")
        token_str = str(tokens) if tokens is not None else "-"
        preview = _truncate(item.get("preview"), ITEM_PREVIEW_WIDTH)
        emit_human(f"{ordinal!s:>4}  {kind:<8}  {role:<10}  {token_str:>5}  {preview}")


async def _fetch_context(
    state: PersonaState,
    conversation_id: str,
    *,
    fresh_tail_count: int | None,
) -> dict[str, Any]:
    """GET /api/v1/lcm/conversations/{id}/context; returns the debug payload."""
    params: dict[str, Any] = {}
    if fresh_tail_count is not None:
        params["fresh_tail_count"] = fresh_tail_count
    async with PawClient(state) as client:
        resp = await client.request(
            "GET",
            f"/api/v1/lcm/conversations/{conversation_id}/context",
            params=params or None,
            expect=(200,),
        )
    body = resp.json()
    return body if isinstance(body, dict) else {}
