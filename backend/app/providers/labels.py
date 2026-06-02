"""Display labels for ``Host`` and ``Vendor`` enum members.

This is the single source of truth on the backend for how providers
(hosts) and vendors are rendered to users — Telegram inline buttons,
chat picker copy, and any future channel.  Adding a new ``Host`` or
``Vendor`` enum member without a corresponding label here causes
``tests/test_provider_labels.py`` to fail.
"""

from __future__ import annotations

from app.providers.model_id import Host, Vendor

HOST_LABELS: dict[Host, str] = {
    Host.agent_sdk: "Anthropic Agent SDK",
    Host.agy_api: "Antigravity API",
    Host.agy_cli: "Antigravity CLI",
    Host.gemini_cli: "Gemini CLI",
    Host.google_ai: "Gemini API",
    Host.litellm: "LiteLLM",
    Host.opencode_go: "OpenCode Go",
    Host.openai_codex: "Codex SDK",
    Host.xai: "xAI",
}
"""Map from :class:`Host` enum to user-facing display string."""

VENDOR_LABELS: dict[Vendor, str] = {
    Vendor.alibaba: "Alibaba",
    Vendor.anthropic: "Anthropic",
    Vendor.deepseek: "DeepSeek",
    Vendor.google: "Google",
    Vendor.minimax: "MiniMax",
    Vendor.moonshot: "Moonshot",
    Vendor.openai: "OpenAI",
    Vendor.xai: "xAI",
    Vendor.xiaomi: "Xiaomi",
    Vendor.zai: "Z.AI",
}
"""Map from :class:`Vendor` enum to user-facing display string."""


def host_label(host: Host) -> str:
    """Return the display string for ``host``.

    Args:
        host: A :class:`Host` enum member.

    Returns:
        The display label.

    Raises:
        KeyError: If ``host`` is not in :data:`HOST_LABELS` (caught by
            the test that enforces every enum member has a label).
    """
    return HOST_LABELS[host]


def vendor_label(vendor: Vendor) -> str:
    """Return the display string for ``vendor``.

    Args:
        vendor: A :class:`Vendor` enum member.

    Returns:
        The display label.

    Raises:
        KeyError: If ``vendor`` is not in :data:`VENDOR_LABELS`.
    """
    return VENDOR_LABELS[vendor]


def host_label_from_slug(slug: str) -> str:
    """Resolve a host wire-slug (e.g. ``"agent-sdk"``) to its label.

    ``Host(slug)`` raises ``ValueError`` for unknown slugs (StrEnum
    behaviour); this function normalises that to ``KeyError`` so callers
    get a consistent lookup-failure exception from both a bad slug and a
    slug that maps to a host with no label.

    Args:
        slug: The host's wire-form slug.

    Returns:
        The display label.

    Raises:
        KeyError: If ``slug`` is not a known :class:`Host` value.
    """
    try:
        host = Host(slug)
    except ValueError as exc:
        raise KeyError(slug) from exc
    return HOST_LABELS[host]


def vendor_label_from_slug(slug: str) -> str:
    """Resolve a vendor wire-slug (e.g. ``"zai"``) to its label.

    ``Vendor(slug)`` raises ``ValueError`` for unknown slugs (StrEnum
    behaviour); this function normalises that to ``KeyError`` so callers
    get a consistent lookup-failure exception from both a bad slug and a
    slug that maps to a vendor with no label.

    Args:
        slug: The vendor's wire-form slug.

    Returns:
        The display label.

    Raises:
        KeyError: If ``slug`` is not a known :class:`Vendor` value.
    """
    try:
        vendor = Vendor(slug)
    except ValueError as exc:
        raise KeyError(slug) from exc
    return VENDOR_LABELS[vendor]
