"""Canonical model-ID parsing for pawrrtal.

The wire format is ``[host:]vendor/model``. The ``host:`` prefix is
optional on input; ``parse_model_id`` fills it in from the per-vendor
canonical-host table so every internal representation is fully
qualified.

This module knows nothing about the catalog. It enforces the
structural contract (regex + ``Vendor`` / ``Host`` enums) and is the
only place in the backend that splits a model-ID string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Vendor(StrEnum):
    """Who built the model.

    Extensible; add a member when a new vendor's models join the
    catalog.
    """

    alibaba = "alibaba"
    anthropic = "anthropic"
    deepseek = "deepseek"
    google = "google"
    minimax = "minimax"
    moonshot = "moonshot"
    openai = "openai"
    xai = "xai"
    xiaomi = "xiaomi"
    zai = "zai"


class Host(StrEnum):
    """Where the model runs.

    One vendor's model can be served by many hosts (e.g. Claude via
    Agent SDK, Bedrock, Copilot).  ``litellm`` is the in-process
    LiteLLM SDK gateway — any vendor it can route to lives behind
    this single host enum.
    """

    claude_code_pty = "claude-code-pty"
    agy_api = "agy-api"
    agy_cli = "agy-cli"
    google_ai = "google-ai"
    litellm = "litellm"
    opencode_go = "opencode-go"
    xai = "xai"
    openai_codex = "openai-codex"
    """First-class native provider using the official `openai_codex`
    Python SDK (https://github.com/openai/codex/tree/main/sdk/python).

    Distinct from `litellm` (which remains the path for users who
    want standard OpenAI models via LiteLLM). This host gives
    full access to Codex threads, native streaming, app-server
    features, and the ability to drive Codex as a powerful agent.
    """


CANONICAL_HOST: dict[Vendor, Host] = {
    Vendor.anthropic: Host.claude_code_pty,
    Vendor.google: Host.google_ai,
    # OpenAI is gateway-only — there is no native Host.openai (yet).
    # LiteLLM handles the openai-compat protocol for any GPT model.
    Vendor.openai: Host.litellm,
    # xAI has a native Host.xai (gRPC SDK via xai-sdk) with full
    # reasoning + Live Search support. LiteLLM can also route xAI but
    # is feature-incomplete; keep the native host as the canonical
    # so ``xai/<model>`` defaults to the full-featured path.
    Vendor.xai: Host.xai,
    # Every open-weight coding model we ship — z.ai (GLM), Moonshot
    # (Kimi), Xiaomi (MiMo), Alibaba (Qwen), MiniMax, DeepSeek — is
    # served by the OpenCode Go gateway (https://opencode.ai/docs/go),
    # SST's hosted OpenAI-compatible endpoint.
    Vendor.zai: Host.opencode_go,
    Vendor.moonshot: Host.opencode_go,
    Vendor.xiaomi: Host.opencode_go,
    Vendor.alibaba: Host.opencode_go,
    Vendor.minimax: Host.opencode_go,
    Vendor.deepseek: Host.opencode_go,
}
"""Per-vendor canonical host used when the input omits ``host:``.

When a deployment changes the canonical host (e.g. ``anthropic`` →
``bedrock``), this is the only place to update.
"""


class InvalidModelId(ValueError):  # noqa: N818
    """Raised when a model-ID string fails structural parsing.

    The string does not parse as ``[host:]vendor/model`` against the
    :class:`Vendor` / :class:`Host` enums. The ``Error`` suffix is
    intentionally omitted: this is the documented public API name
    used by callers across the backend.
    """


class UnknownModelId(LookupError):  # noqa: N818
    """Raised when a parsed model-ID is not present in the catalog.

    The string parses but the resulting ``(host, vendor, model)``
    triple is not in the catalog. Raised by ``catalog.find()`` and
    by ``resolve_llm`` when the lookup fails. The ``Error`` suffix is
    intentionally omitted: this is the documented public API name
    used by callers across the backend.
    """


_MODEL_ID_RE = re.compile(
    r"^(?:(?P<host>[a-z][a-z0-9-]*):)?"
    r"(?P<vendor>[a-z][a-z0-9-]*)/"
    r"(?P<model>[a-z0-9][a-z0-9.\-_]*)$"
)


@dataclass(frozen=True, slots=True)
class ParsedModelId:
    """A model identifier whose three parts have been validated."""

    host: Host
    vendor: Vendor
    model: str
    raw: str

    @property
    def id(self) -> str:
        """Canonical fully-qualified wire string: ``host:vendor/model``."""
        return f"{self.host.value}:{self.vendor.value}/{self.model}"


def parse_model_id(raw: str) -> ParsedModelId:
    """Parse ``raw`` into a :class:`ParsedModelId`.

    Args:
        raw: A wire-form model identifier, either ``host:vendor/model``
            or the shorter ``vendor/model``.

    Returns:
        A fully-qualified :class:`ParsedModelId`. The ``host`` field
        is filled from :data:`CANONICAL_HOST` when ``raw`` omits the
        ``host:`` prefix.

    Raises:
        InvalidModelId: If ``raw`` does not match the structural
            regex or contains a vendor / host that is not an enum
            member.
    """
    match = _MODEL_ID_RE.match(raw)
    if match is None:
        raise InvalidModelId(f"not a valid model ID: {raw!r}")

    vendor_str = match.group("vendor")
    try:
        vendor = Vendor(vendor_str)
    except ValueError as exc:
        raise InvalidModelId(f"unknown vendor {vendor_str!r} in {raw!r}") from exc

    host_str = match.group("host")
    if host_str is None:
        host = CANONICAL_HOST[vendor]
    else:
        try:
            host = Host(host_str)
        except ValueError as exc:
            raise InvalidModelId(f"unknown host {host_str!r} in {raw!r}") from exc

    return ParsedModelId(host=host, vendor=vendor, model=match.group("model"), raw=raw)
