"""``/api/v1/completions`` — short-lived inline completion suggestions.

Used by the chat composer to fetch IDE-style ghost-text predictions
as the user types. Reuses the same provider-agnostic streaming
infrastructure as ``/api/v1/chat`` (``resolve_llm`` + ``provider.stream``);
the only difference is that the response is collected internally and
returned as a single JSON blob rather than streamed to the client.

This endpoint is intentionally lean: no history, no tools, no
persistence, no cost-budget gate. Autocomplete is a soft UI affordance
— any transient failure collapses to an empty suggestion so the
frontend always has something safe to render.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import Depends
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field

from app.core.providers import resolve_llm
from app.db import User
from app.users import get_allowed_user

logger = logging.getLogger(__name__)

# Model used for ghost-text autocomplete. Flash-Lite preview is the
# fastest Gemini tier and accepts ``reasoning_effort="minimal"``, so
# total round-trip stays in the low hundreds of milliseconds for the
# short prefixes a composer typically sends.
AUTOCOMPLETE_MODEL_ID = "google-ai:google/gemini-3.1-flash-lite"

# Hard cap on how long the provider can stream before we give up.
# Autocomplete is a low-stakes hot path — a suggestion that isn't
# ready inside this window is stale by the time it would render.
AUTOCOMPLETE_TIMEOUT_SECONDS = 4.0

# Hard cap on suggestion length to keep the overlay narrow and the
# round-trip cheap. 80 chars ≈ 12 short words; longer suggestions
# read as intrusive rather than helpful in a chat composer.
MAX_SUGGESTION_CHARS = 80

# Minimum prefix length before we attempt a completion. Shorter
# prefixes have too little context to produce useful guesses and
# just burn API calls during the first few keystrokes of a message.
MIN_PREFIX_CHARS = 3

# Upper bound on incoming draft text. Anything longer is almost
# certainly a paste rather than typing, and ghost completions stop
# being useful past this length anyway.
MAX_PREFIX_CHARS = 4000

AUTOCOMPLETE_SYSTEM_PROMPT = (
    "You are a ghost-text autocomplete engine inside a chat input box. "
    "The user is in the middle of typing a message to an AI assistant. "
    "Your job: predict the most natural continuation of their text.\n"
    "Rules:\n"
    "- Output ONLY the continuation — never echo what the user already typed.\n"
    "- Keep it short: 1 to 12 words.\n"
    "- If the user's text already ends with a complete thought, return an empty string.\n"
    "- If the user's text ends mid-word, complete that word naturally.\n"
    "- Match the user's tone and language.\n"
    "- Continue naturally. If there's no space after the user's last word, make sure your suggestion starts with a space.\n"
    "- Start with capital letter if it is the beginning of the sentence. Basically, write normally."
)


class AutocompleteRequest(BaseModel):
    """Request body for ``POST /api/v1/completions/autocomplete``."""

    text: str = Field(
        ...,
        max_length=MAX_PREFIX_CHARS,
        description="User's in-progress chat draft.",
    )


class AutocompleteResponse(BaseModel):
    """Suggested continuation of the user's draft text."""

    suggestion: str


def _clean_suggestion(raw: str) -> str:
    """Trim stray quoting from a model-generated suggestion.

    Flash-Lite occasionally wraps its output in matching quotes or
    backticks despite the system prompt. Truncate to ``MAX_SUGGESTION_CHARS``.
    """
    return raw.strip().strip("\"'`")[:MAX_SUGGESTION_CHARS]


async def _collect_suggestion(*, text: str, user_id: uuid.UUID) -> str:
    """Stream a one-shot completion and accumulate the delta text.

    Returns the (possibly empty) suggestion. A timeout or canceled
    stream returns an empty string — autocomplete is a soft affordance
    and never raises to the caller. Non-timeout exceptions from the
    provider are intentionally allowed to propagate so they surface
    as 500s and are caught by upstream monitoring; the frontend
    treats any non-2xx as "no suggestion this turn".
    """
    provider = resolve_llm(AUTOCOMPLETE_MODEL_ID)
    pieces: list[str] = []
    char_budget = MAX_SUGGESTION_CHARS

    async def consume() -> None:
        async for event in provider.stream(
            question=text,
            # Throwaway UUID — we intentionally do NOT reuse the chat
            # conversation_id here. Each autocomplete call is a stateless
            # one-shot; reusing the chat session would pollute Gemini's
            # session cache with thousands of micro-turns per message.
            conversation_id=uuid.uuid4(),
            user_id=user_id,
            system_prompt=AUTOCOMPLETE_SYSTEM_PROMPT,
            reasoning_effort="minimal",
        ):
            if event.get("type") != "delta":
                continue
            content = event.get("content", "")
            if not content:
                continue
            pieces.append(content)
            if sum(len(p) for p in pieces) >= char_budget:
                break

    try:
        await asyncio.wait_for(consume(), timeout=AUTOCOMPLETE_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.info(
            "AUTOCOMPLETE_TIMEOUT user_id=%s text_len=%d",
            user_id,
            len(text),
        )
        return ""

    return _clean_suggestion("".join(pieces))


def get_completions_router() -> APIRouter:
    """Build the ``/api/v1/completions`` router.

    Returns:
        An ``APIRouter`` exposing ``POST /api/v1/completions/autocomplete``
        behind the standard authed-user dependency.
    """
    router = APIRouter(prefix="/api/v1/completions", tags=["completions"])

    @router.post("/autocomplete", response_model=AutocompleteResponse)
    async def autocomplete(
        body: AutocompleteRequest,
        user: User = Depends(get_allowed_user),
    ) -> AutocompleteResponse:
        """Return a ghost-text suggestion for the user's draft text.

        Empty or very short prefixes short-circuit to an empty
        suggestion without hitting the provider — Gemini cannot
        usefully predict from a one- or two-character prompt and the
        round-trip would only add latency to the next keystroke.
        """
        # Strip trailing whitespace so a draft like ``"hello "`` still
        # counts the 5 visible characters but lets the model see the
        # trailing space (it informs whether the next token should
        # start with a space or continue a word).
        if len(body.text.rstrip()) < MIN_PREFIX_CHARS:
            return AutocompleteResponse(suggestion="")

        suggestion = await _collect_suggestion(text=body.text, user_id=user.id)
        return AutocompleteResponse(suggestion=suggestion)

    return router
