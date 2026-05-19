"""Tests for the backend's Host/Vendor display-label module."""

from __future__ import annotations

import pytest

from app.core.providers.labels import (
    HOST_LABELS,
    VENDOR_LABELS,
    host_label,
    vendor_label,
)
from app.core.providers.model_id import Host, Vendor


def test_every_host_enum_has_a_label() -> None:
    """Adding a new Host without a label must fail loudly."""
    missing = [h for h in Host if h not in HOST_LABELS]
    assert missing == []


def test_every_vendor_enum_has_a_label() -> None:
    """Adding a new Vendor without a label must fail loudly."""
    missing = [v for v in Vendor if v not in VENDOR_LABELS]
    assert missing == []


def test_host_label_returns_expected_strings() -> None:
    assert host_label(Host.agent_sdk) == "Anthropic Agent SDK"
    assert host_label(Host.google_ai) == "Gemini API"
    assert host_label(Host.litellm) == "LiteLLM"
    assert host_label(Host.opencode_go) == "OpenCode Go"
    assert host_label(Host.xai) == "xAI"


def test_vendor_label_returns_expected_strings() -> None:
    assert vendor_label(Vendor.anthropic) == "Anthropic"
    assert vendor_label(Vendor.openai) == "OpenAI"
    assert vendor_label(Vendor.google) == "Google"
    assert vendor_label(Vendor.xai) == "xAI"
    assert vendor_label(Vendor.zai) == "Z.AI"
    assert vendor_label(Vendor.moonshot) == "Moonshot"


def test_host_label_from_slug_helper_round_trip() -> None:
    """``host_label`` accepts both the enum and the wire slug."""
    from app.core.providers.labels import host_label_from_slug

    assert host_label_from_slug("agent-sdk") == "Anthropic Agent SDK"
    assert host_label_from_slug("opencode-go") == "OpenCode Go"
    with pytest.raises(KeyError):
        host_label_from_slug("not-a-host")


def test_vendor_label_from_slug_helper_round_trip() -> None:
    """``vendor_label`` accepts both the enum and the wire slug."""
    from app.core.providers.labels import vendor_label_from_slug

    assert vendor_label_from_slug("zai") == "Z.AI"
    with pytest.raises(KeyError):
        vendor_label_from_slug("not-a-vendor")
