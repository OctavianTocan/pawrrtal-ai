"""Typed provider failure shapes for the returns pilot (Phase 3).

Discriminated union of ``@dataclass`` failures consumed by the
``returns``-wrapped provider seam. See
``docs/superpowers/specs/2026-05-28-returns-adoption-grilling.md`` and
``.claude/skills/returns-for-pawrrtal/SKILL.md`` for the decision rubric.

Only the providers in the pilot scope import these names today; other
providers continue to surface raw exceptions or in-band error events.
This module is **shared** between providers so that, when the next
provider migrates, the failure shape stays stable across the seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ProviderAuthError:
    """Upstream rejected the call as unauthenticated/forbidden (HTTP 401/403)."""

    message: str
    kind: Literal["auth"] = "auth"


@dataclass(frozen=True, slots=True)
class ProviderRateLimitError:
    """Upstream rate-limited the call (HTTP 429).

    ``retry_after`` is the number of seconds the upstream suggested
    waiting before retrying when the SDK surfaces a ``Retry-After``
    header; ``None`` if the SDK did not expose one.
    """

    message: str
    retry_after: float | None = None
    kind: Literal["rate_limit"] = "rate_limit"


@dataclass(frozen=True, slots=True)
class ProviderUnsupportedParamError:
    """A request parameter is not supported by this model/provider.

    Typical cause in pawrrtal: a stored ``reasoning_effort`` value is
    forwarded to a non-reasoning model. ``param`` and ``model`` let
    the caller surface a precise UI hint without parsing the message.
    """

    message: str
    param: str
    model: str
    kind: Literal["unsupported_param"] = "unsupported_param"


@dataclass(frozen=True, slots=True)
class ProviderTimeoutError:
    """Connection or read deadline exceeded before any stream chunks arrived."""

    message: str
    kind: Literal["timeout"] = "timeout"


@dataclass(frozen=True, slots=True)
class ProviderUnknownError:
    """Fallback bucket for failures the classifier did not recognise.

    Carries the original message verbatim so the caller can still log
    something useful while the closed set above grows over time.
    """

    message: str
    kind: Literal["unknown"] = "unknown"


ProviderError = (
    ProviderAuthError
    | ProviderRateLimitError
    | ProviderUnsupportedParamError
    | ProviderTimeoutError
    | ProviderUnknownError
)
"""Closed set of provider-seam failure modes the returns pilot surfaces.

Callers ``match`` on the ``kind`` literal (or on the variant directly)
to react differently per failure mode. New variants are additive — add
the dataclass + extend the union, then update every ``match`` site.
"""
