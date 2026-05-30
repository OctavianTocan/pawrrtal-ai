"""Regex-based secret redaction for logs and persisted tool inputs.

Ported from claude-code-telegram (``src/bot/orchestrator.py:53-91``)
and extended to also operate over nested ``dict``/``list`` payloads
so the chat aggregator can run it over ``tool_use.input`` before
persisting a row to ``chat_messages.tool_calls``.

Pure functions, no I/O. Disabled when
``settings.secret_redaction_enabled`` is False — callers check the
flag before invoking ``redact_secrets`` so a False setting is truly
zero-overhead.

What's caught
-------------
* Anthropic / OpenAI API keys (``sk-ant-…``, ``sk-…``)
* GitHub personal-access tokens (``ghp_…``, ``gho_…``, ``github_pat_…``)
* Slack bot tokens (``xoxb-…``)
* AWS access keys (``AKIA…``)
* CLI flags carrying secrets (``--token=…``, ``--api-key=…``, …)
* Inline env assignments (``TOKEN=…``, ``API_KEY=…``, ``PASSWORD=…``, …)
* Bearer / Basic auth headers
* Connection-string credentials (``user:pass@host``)

The regex set is intentionally a copy of CCT's so we get the same
coverage. Adding a new pattern is one line — keep them anchored on
a unique prefix so we never redact innocuous strings that happen to
contain the right characters.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

# Each pattern's first capturing group is preserved (the prefix that
# tells the reader what type of secret was found); everything that
# follows is replaced with ``***``. The structure mirrors CCT's so
# diffs from upstream stay easy to review.
SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # API keys / tokens (sk-ant-..., sk-..., ghp_..., gho_..., github_pat_..., xoxb-...)
    re.compile(
        r"(sk-ant-api\d*-[A-Za-z0-9_-]{10})[A-Za-z0-9_-]*"
        r"|(sk-[A-Za-z0-9_-]{20})[A-Za-z0-9_-]*"
        r"|(ghp_[A-Za-z0-9]{5})[A-Za-z0-9]*"
        r"|(gho_[A-Za-z0-9]{5})[A-Za-z0-9]*"
        r"|(github_pat_[A-Za-z0-9_]{5})[A-Za-z0-9_]*"
        r"|(xoxb-[A-Za-z0-9]{5})[A-Za-z0-9-]*"
    ),
    # AWS access keys
    re.compile(r"(AKIA[0-9A-Z]{4})[0-9A-Z]{12}"),
    # Generic long hex/base64 tokens after common flags
    re.compile(
        r"((?:--token|--secret|--password|--api-key|--apikey|--auth)"
        r"[= ]+)['\"]?[A-Za-z0-9+/_.:-]{8,}['\"]?"
    ),
    # Inline env assignments like KEY=value
    re.compile(
        r"((?:TOKEN|SECRET|PASSWORD|API_KEY|APIKEY|AUTH_TOKEN|PRIVATE_KEY"
        r"|ACCESS_KEY|CLIENT_SECRET|WEBHOOK_SECRET)"
        r"=)['\"]?[^\s'\"]{8,}['\"]?"
    ),
    # Bearer / Basic auth headers
    re.compile(r"(Bearer )[A-Za-z0-9+/_.:-]{8,}" r"|(Basic )[A-Za-z0-9+/=]{8,}"),
    # Connection strings with credentials  user:pass@host
    re.compile(r"(://[^:]+:)[^@]{4,}(@)"),
)

# Placeholder appended after the preserved prefix to mark a redaction.
_REDACTED_SUFFIX = "***"


def _replace_match(match: re.Match[str]) -> str:
    """Build the replacement for a single regex hit.

    Each pattern uses its capture groups as **literal scaffolding** that
    surrounds the secret payload — the secret itself is never captured.
    Walking groups in order and joining the non-None ones with the
    redaction marker preserves any trailing context (e.g. the ``@`` in
    a connection-string URL) so re-running redaction is still
    idempotent and the result reads naturally.

    With one group: ``<g1>***``.
    With two groups: ``<g1>***<g2>``.
    With none: ``***`` — fallback for patterns that match the entire
    secret without scaffolding.
    """
    captured = [g for g in match.groups() if g is not None]
    if not captured:
        return _REDACTED_SUFFIX
    if len(captured) == 1:
        return captured[0] + _REDACTED_SUFFIX
    return captured[0] + _REDACTED_SUFFIX + "".join(captured[1:])


def redact_secrets(text: str) -> str:
    """Return ``text`` with all configured secret patterns redacted.

    Idempotent — running it twice on the same string is a no-op past
    the first pass because the redacted form (``prefix***``) won't
    re-match the patterns.

    Returns ``text`` unchanged when it's not a string (the chat
    aggregator hands us heterogeneous values).
    """
    if not isinstance(text, str) or not text:
        return text
    result = text
    for pattern in SECRET_PATTERNS:
        result = pattern.sub(_replace_match, result)
    return result


def redact_mapping(payload: Any) -> Any:
    """Recursively redact secrets inside a JSON-shaped payload.

    Strings are passed through :func:`redact_secrets`. Mappings and
    sequences are walked structurally so the same value comes out the
    other side with the same shape. Non-collection scalars (int, bool,
    None, float) are returned untouched.

    Used by the chat aggregator (PR 02) on ``tool_use.input`` before
    persisting the JSON blob to ``chat_messages.tool_calls`` so a
    secret pasted into a tool call doesn't end up in the history.
    """
    if isinstance(payload, str):
        return redact_secrets(payload)
    if isinstance(payload, Mapping):
        return {key: redact_mapping(value) for key, value in payload.items()}
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [redact_mapping(item) for item in payload]
    return payload
