"""Tests for :mod:`app.providers.model_id`."""

from __future__ import annotations

import pytest

from app.providers.model_id import (
    CANONICAL_HOST,
    Host,
    InvalidModelId,
    ParsedModelId,
    Vendor,
    parse_model_id,
)


def test_parse_fully_qualified_anthropic() -> None:
    parsed = parse_model_id("claude-code-pty:anthropic/claude-sonnet-4-6")
    assert parsed == ParsedModelId(
        host=Host.claude_code_pty,
        vendor=Vendor.anthropic,
        model="claude-sonnet-4-6",
        raw="claude-code-pty:anthropic/claude-sonnet-4-6",
    )


def test_parse_fills_canonical_host_when_omitted() -> None:
    parsed = parse_model_id("anthropic/claude-sonnet-4-6")
    assert parsed.host is Host.claude_code_pty
    assert parsed.vendor is Vendor.anthropic
    assert parsed.model == "claude-sonnet-4-6"


def test_parse_google_canonical_host() -> None:
    parsed = parse_model_id("google/gemini-3-flash-preview")
    assert parsed.host is Host.google_ai


def test_parse_xai_canonical_host() -> None:
    """``xai/grok-4.3`` canonicalises to ``xai:xai/grok-4.3``.

    xAI defaults to the native ``Host.xai`` provider (PRs #314/#324)
    not the LiteLLM gateway — ``Host.xai`` has full reasoning and
    Live Search support, LiteLLM does not.  Override via the
    fully-qualified ``litellm:xai/<model>`` form if needed.
    """
    parsed = parse_model_id("xai/grok-4.3")
    assert parsed.host is Host.xai
    assert parsed.vendor is Vendor.xai
    assert parsed.model == "grok-4.3"
    assert parsed.id == "xai:xai/grok-4.3"


def test_parse_openai_canonical_host_is_litellm() -> None:
    """``openai/<model>`` defaults to ``litellm`` — no native OpenAI host."""
    parsed = parse_model_id("openai/gpt-4o")
    assert parsed.host is Host.litellm
    assert parsed.vendor is Vendor.openai


def test_parse_fully_qualified_litellm_openai_id() -> None:
    """Explicit ``litellm:openai/<model>`` form parses identically to the bare form."""
    parsed = parse_model_id("litellm:openai/gpt-4o")
    assert parsed.host is Host.litellm
    assert parsed.vendor is Vendor.openai
    assert parsed.model == "gpt-4o"


def test_parse_fully_qualified_litellm_xai_id() -> None:
    """``litellm:xai/<model>`` is the explicit opt-in to route xAI via LiteLLM.

    Without the ``litellm:`` prefix, the canonical host for xAI is the
    native ``Host.xai`` provider — this test guards the opt-out path
    for callers that need LiteLLM routing for xAI specifically.
    """
    parsed = parse_model_id("litellm:xai/grok-4.3")
    assert parsed.host is Host.litellm
    assert parsed.vendor is Vendor.xai
    assert parsed.model == "grok-4.3"


def test_id_property_round_trips_through_parse() -> None:
    canonical = "claude-code-pty:anthropic/claude-sonnet-4-6"
    assert parse_model_id(canonical).id == canonical
    # Bare form canonicalises to the host-prefixed form.
    assert parse_model_id("anthropic/claude-sonnet-4-6").id == canonical


def test_parse_rejects_bare_model_id() -> None:
    with pytest.raises(InvalidModelId):
        parse_model_id("claude-sonnet-4-6")


def test_parse_rejects_empty_string() -> None:
    with pytest.raises(InvalidModelId):
        parse_model_id("")


def test_parse_rejects_whitespace() -> None:
    with pytest.raises(InvalidModelId):
        parse_model_id("anthropic / claude-sonnet-4-6")
    with pytest.raises(InvalidModelId):
        parse_model_id(" anthropic/claude-sonnet-4-6")


def test_parse_rejects_uppercase() -> None:
    with pytest.raises(InvalidModelId):
        parse_model_id("Anthropic/claude-sonnet-4-6")


def test_parse_rejects_unknown_vendor() -> None:
    with pytest.raises(InvalidModelId, match="unknown vendor"):
        parse_model_id("mistral/mixtral-8x7b")


def test_parse_rejects_unknown_host() -> None:
    with pytest.raises(InvalidModelId, match="unknown host"):
        parse_model_id("bedrock:anthropic/claude-sonnet-4-6")


def test_canonical_host_covers_every_vendor() -> None:
    """If a Vendor enum member has no canonical host, parsing the
    bare form would KeyError. This invariant guards against
    forgetting to update CANONICAL_HOST when adding a vendor."""
    for vendor in Vendor:
        assert vendor in CANONICAL_HOST


def test_parsed_model_id_is_frozen() -> None:
    parsed = parse_model_id("anthropic/claude-sonnet-4-6")
    with pytest.raises(AttributeError):
        parsed.host = Host.google_ai  # type: ignore[misc]
