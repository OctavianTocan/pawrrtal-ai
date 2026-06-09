# Canonical Model-ID Format and Backend Catalog — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace pawrrtal's three coexisting model-ID shapes (bare, vendor-prefixed, plus an SDK-required bare-only contract) with a single canonical `host:vendor/model` wire form sourced from a backend-owned catalog.

**Architecture:** Backend gains a `model_id` module (parser + enums) and a `catalog` module (the single source of truth for which models exist, with `is_default` on entries). A new `/api/v1/models` endpoint serves the catalog to all clients. Pydantic validators canonicalise model IDs at every API boundary. The frontend deletes its parallel catalog and fetches from the API via a TanStack Query hook. Telegram parses `/model` input structurally on write (shared backend parser; catalog-ignorant) and catches `UnknownModelId` at chat-turn time to auto-clear bad stored values.

**Tech Stack:** Python 3.13 + FastAPI + Pydantic v2 + SQLAlchemy (backend); Next.js 15 + TypeScript + TanStack Query + Zod + Vitest (frontend); pytest + ruff + mypy (backend gates); biome + tsc (frontend gates).

**Spec:** `frontend/content/docs/handbook/decisions/2026-05-14-model-id-canonical-format-and-backend-catalog.md`

**Parent / follow-up beans:** pawrrtal-5854 (parent bugfix), pawrrtal-25yy (deferred Telegram proactive catalog validation).

**Project conventions to honour (every task):**
- One concern per commit. Conventional Commits format. Body explains the *why*.
- Tests ship in the same commit as the feature they cover (`.claude/rules/general/how-we-work-on-pawrrtal.md` Rule 7).
- After every file write: `just check` + `bun run typecheck` (FE) or `uv run pytest <touched test>` (BE). See `.claude/rules/sweep/run-toolchain-after-writes.md`.
- TSDoc on every export. Explicit TS return types. Inline `/** */` per interface property.
- Max 500 LOC / file, max 3 levels of compound-statement nesting per function.
- React: View/Container split for any component with state + hooks (`.claude/rules/react/view-container-split.md`).
- No new `console.error`/`pageerror` on cold-boot routes (`scripts/dev-console-smoke.mjs` gates this).
- Never patch `node_modules`. Never `git stash`. Never switch branches without asking.

---

## Chunk 1: Backend foundations (parser + catalog + endpoint)

Pure-additive backend modules. No consumers wired up yet; nothing currently runs through the new code, so this chunk lands without affecting any live path.

### Task 1: `model_id` module — types, parser, exceptions

**Files:**
- Create: `backend/app/providers/model_id.py`
- Test: `backend/tests/test_model_id.py`

**Concrete content for `model_id.py`** (final shape, top to bottom):

```python
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
    """Who built the model. Extensible; add a member when a new
    vendor's models join the catalog."""

    anthropic = "anthropic"
    google = "google"
    openai = "openai"


class Host(StrEnum):
    """Where the model runs. One vendor's model can be served by
    many hosts (e.g. Claude via Agent SDK, Bedrock, Copilot)."""

    agent_sdk = "agent-sdk"
    google_ai = "google-ai"


CANONICAL_HOST: dict[Vendor, Host] = {
    Vendor.anthropic: Host.agent_sdk,
    Vendor.google: Host.google_ai,
}
"""Per-vendor canonical host used when the input omits ``host:``.

When a deployment changes the canonical host (e.g. ``anthropic`` →
``bedrock``), this is the only place to update.
"""


class InvalidModelId(ValueError):
    """The string does not parse as ``[host:]vendor/model`` against
    the ``Vendor`` / ``Host`` enums."""


class UnknownModelId(LookupError):
    """The string parses but the resulting ``(host, vendor, model)``
    triple is not in the catalog. Raised by ``catalog.find()`` and
    by ``resolve_llm`` when the lookup fails."""


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
```

**Steps:**

- [ ] **Step 1: Open a beans entry for this chunk.**

```bash
beans create "Implement model_id canonical-format module" -t task \
  -s in-progress -p high \
  -d "ADR frontend/content/docs/handbook/decisions/2026-05-14-model-id-canonical-format-and-backend-catalog.md §2. Pure additive: Vendor/Host enums, ParsedModelId, parse_model_id, InvalidModelId, UnknownModelId. No consumers wired yet." \
  --blocked-by pawrrtal-5854
```

- [ ] **Step 2: Write the failing tests.**

Create `backend/tests/test_model_id.py` with all of these tests; the
implementation in step 4 must make every one pass.

```python
"""Tests for :mod:`app.core.providers.model_id`."""

from __future__ import annotations

import pytest

from app.core.providers.model_id import (
    CANONICAL_HOST,
    Host,
    InvalidModelId,
    ParsedModelId,
    Vendor,
    parse_model_id,
)


def test_parse_fully_qualified_anthropic() -> None:
    parsed = parse_model_id("agent-sdk:anthropic/claude-sonnet-4-6")
    assert parsed == ParsedModelId(
        host=Host.agent_sdk,
        vendor=Vendor.anthropic,
        model="claude-sonnet-4-6",
        raw="agent-sdk:anthropic/claude-sonnet-4-6",
    )


def test_parse_fills_canonical_host_when_omitted() -> None:
    parsed = parse_model_id("anthropic/claude-sonnet-4-6")
    assert parsed.host is Host.agent_sdk
    assert parsed.vendor is Vendor.anthropic
    assert parsed.model == "claude-sonnet-4-6"


def test_parse_google_canonical_host() -> None:
    parsed = parse_model_id("google/gemini-3-flash-preview")
    assert parsed.host is Host.google_ai


def test_id_property_round_trips_through_parse() -> None:
    canonical = "agent-sdk:anthropic/claude-sonnet-4-6"
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
```

- [ ] **Step 3: Run tests to verify they all fail.**

```bash
cd backend && uv run pytest tests/test_model_id.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.core.providers.model_id'`.

- [ ] **Step 4: Create the module.**

Write the full content shown above into `backend/app/providers/model_id.py`.

- [ ] **Step 5: Run tests to verify they pass.**

```bash
cd backend && uv run pytest tests/test_model_id.py -v
```

Expected: 12 passed.

- [ ] **Step 6: Toolchain gate.**

```bash
cd backend && uv run ruff format app/providers/model_id.py tests/test_model_id.py
cd backend && uv run ruff check app/providers/model_id.py tests/test_model_id.py
cd backend && uv run mypy app/providers/model_id.py
```

Expected: all clean. If mypy flags an unrelated pre-existing error in another file, that's fine — focus on the touched files.

- [ ] **Step 7: Commit.**

```bash
git add backend/app/providers/model_id.py backend/tests/test_model_id.py
git commit -m "$(cat <<'EOF'
feat(providers): add canonical model-ID parser

Introduces Vendor + Host StrEnums, ParsedModelId value object, and
parse_model_id() — the single backend-side splitter for model IDs in
the canonical "[host:]vendor/model" wire format. No consumers wired
yet; subsequent commits replace _strip_provider_segment in the
factory and apply the parser at every API boundary.

ADR: frontend/content/docs/handbook/decisions/2026-05-14-model-id-canonical-format-and-backend-catalog.md
Beans: pawrrtal-5854 (parent bug)
EOF
)"
```

- [ ] **Step 8: Update bean to mark task complete.**

```bash
beans update <bean-id-from-step-1> -s completed \
  --body-append "## Summary
Module landed: Vendor/Host enums, ParsedModelId, parse_model_id, InvalidModelId, UnknownModelId, CANONICAL_HOST. 12 tests pass; ruff + mypy clean."
```

---

### Task 2: `catalog` module — entries, default invariant, lookup

**Files:**
- Create: `backend/app/providers/catalog.py`
- Test: `backend/tests/test_catalog.py`

**Concrete content for `catalog.py`:**

```python
"""Single source of truth for which models pawrrtal supports.

Catalog entries carry the canonical ``host:vendor/model`` identity
plus display metadata. Adding a model is a one-file change here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from .model_id import (
    Host,
    InvalidModelId,
    ParsedModelId,
    UnknownModelId,
    Vendor,
    parse_model_id,
)


@dataclass(frozen=True, slots=True)
class ModelEntry:
    """One supported model.

    The ``id`` property is the canonical wire form used by the API,
    DB, logs, and frontend.
    """

    host: Host
    vendor: Vendor
    model: str
    display_name: str
    short_name: str
    description: str
    is_default: bool

    @property
    def id(self) -> str:
        """Canonical wire string: ``host:vendor/model``."""
        return f"{self.host.value}:{self.vendor.value}/{self.model}"


MODEL_CATALOG: tuple[ModelEntry, ...] = (
    ModelEntry(
        host=Host.agent_sdk,
        vendor=Vendor.anthropic,
        model="claude-opus-4-7",
        display_name="Claude Opus 4.7",
        short_name="Claude Opus 4.7",
        description="Most capable for ambitious work",
        is_default=False,
    ),
    ModelEntry(
        host=Host.agent_sdk,
        vendor=Vendor.anthropic,
        model="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        short_name="Claude Sonnet 4.6",
        description="Balanced for everyday tasks",
        is_default=False,
    ),
    ModelEntry(
        host=Host.agent_sdk,
        vendor=Vendor.anthropic,
        model="claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        short_name="Claude Haiku 4.5",
        description="Fastest for quick answers",
        is_default=False,
    ),
    ModelEntry(
        host=Host.google_ai,
        vendor=Vendor.google,
        model="gemini-3-flash-preview",
        display_name="Gemini 3 Flash Preview",
        short_name="Gemini 3 Flash",
        description="Google's frontier multimodal",
        is_default=True,
    ),
    ModelEntry(
        host=Host.google_ai,
        vendor=Vendor.google,
        model="gemini-3.1-flash-lite-preview",
        display_name="Gemini 3.1 Flash Lite Preview",
        short_name="Gemini Flash Lite",
        description="Light and fast Gemini",
        is_default=False,
    ),
)


# Module-import-time invariant: exactly one default.
# Explicit raise (not ``assert``) so ``python -O`` cannot strip it.
_default_count = sum(1 for e in MODEL_CATALOG if e.is_default)
if _default_count != 1:
    raise ValueError(
        f"MODEL_CATALOG must have exactly one default; found {_default_count}"
    )


def _hash_catalog(catalog: tuple[ModelEntry, ...]) -> str:
    """Stable hash of the catalog used as the HTTP ``ETag`` value."""
    payload = json.dumps(
        [asdict(e) for e in catalog],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


CATALOG_ETAG: str = _hash_catalog(MODEL_CATALOG)
"""Catalog hash, computed once at import. Exposed via the ``ETag``
response header so clients can revalidate cheaply with
``If-None-Match``."""


def default_model() -> ModelEntry:
    """Return the entry marked ``is_default=True``.

    Returns:
        The single default entry. The module-import-time invariant
        guarantees exactly one exists.
    """
    return next(e for e in MODEL_CATALOG if e.is_default)


def find(parsed: ParsedModelId) -> ModelEntry | None:
    """Look up a catalog entry by parsed identifier.

    Args:
        parsed: Pre-parsed identifier (callers go through
            :func:`parse_model_id` first).

    Returns:
        The matching :class:`ModelEntry` or ``None``.
    """
    for entry in MODEL_CATALOG:
        if (
            entry.host is parsed.host
            and entry.vendor is parsed.vendor
            and entry.model == parsed.model
        ):
            return entry
    return None


def is_known(parsed: ParsedModelId) -> bool:
    """Return whether ``parsed`` is in :data:`MODEL_CATALOG`."""
    return find(parsed) is not None


def require_known(model_id: str) -> ModelEntry:
    """Parse ``model_id`` and look it up; raise on either failure.

    Args:
        model_id: Wire-form model identifier (any of the accepted
            input shapes — see :func:`parse_model_id`).

    Returns:
        The catalog entry.

    Raises:
        InvalidModelId: If the string fails to parse.
        UnknownModelId: If the string parses but isn't in the
            catalog.
    """
    parsed = parse_model_id(model_id)
    entry = find(parsed)
    if entry is None:
        raise UnknownModelId(f"model not in catalog: {parsed.id}")
    return entry
```

**Steps:**

- [ ] **Step 1: Beans entry.**

```bash
beans create "Implement backend model catalog" -t task -s in-progress -p high \
  -d "ADR §3. ModelEntry, MODEL_CATALOG, CATALOG_ETAG, default_model, find, is_known, require_known. Module-import-time invariant: exactly one default." \
  --blocked-by <bean-id-from-task-1>
```

- [ ] **Step 2: Write the failing tests.**

Create `backend/tests/test_catalog.py`:

```python
"""Tests for :mod:`app.core.providers.catalog`."""

from __future__ import annotations

import pytest

from app.core.providers.catalog import (
    CATALOG_ETAG,
    MODEL_CATALOG,
    ModelEntry,
    default_model,
    find,
    is_known,
    require_known,
)
from app.core.providers.model_id import (
    Host,
    InvalidModelId,
    UnknownModelId,
    Vendor,
    parse_model_id,
)


def test_catalog_not_empty() -> None:
    assert len(MODEL_CATALOG) > 0


def test_every_entry_id_round_trips_through_parser() -> None:
    for entry in MODEL_CATALOG:
        parsed = parse_model_id(entry.id)
        assert parsed.host is entry.host
        assert parsed.vendor is entry.vendor
        assert parsed.model == entry.model
        assert parsed.id == entry.id


def test_exactly_one_default() -> None:
    defaults = [e for e in MODEL_CATALOG if e.is_default]
    assert len(defaults) == 1


def test_default_model_returns_the_default_entry() -> None:
    entry = default_model()
    assert entry.is_default is True


def test_find_returns_entry_for_known_id() -> None:
    target = default_model()
    parsed = parse_model_id(target.id)
    assert find(parsed) is target


def test_find_returns_none_for_unknown_model() -> None:
    parsed = parse_model_id("google/gemini-9999-future-preview")
    assert find(parsed) is None


def test_is_known_matches_find() -> None:
    target = default_model()
    parsed = parse_model_id(target.id)
    assert is_known(parsed) is True
    unknown = parse_model_id("google/gemini-9999-future-preview")
    assert is_known(unknown) is False


def test_require_known_returns_entry() -> None:
    target = default_model()
    assert require_known(target.id) is target


def test_require_known_raises_invalid_for_bad_format() -> None:
    with pytest.raises(InvalidModelId):
        require_known("not a model id")


def test_require_known_raises_unknown_for_well_formed_miss() -> None:
    with pytest.raises(UnknownModelId):
        require_known("google/gemini-9999-future-preview")


def test_etag_is_stable() -> None:
    assert isinstance(CATALOG_ETAG, str)
    assert len(CATALOG_ETAG) == 16
    # Importing twice yields the same hash (module-level computation).
    from app.core.providers.catalog import CATALOG_ETAG as etag_again

    assert CATALOG_ETAG == etag_again


def test_catalog_module_import_rejects_zero_or_many_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The invariant assertion at module import should fire if the
    tuple has 0 or 2+ defaults. We can't re-import the live module,
    so we exercise the same code path against a synthetic tuple."""
    bad_catalog: tuple[ModelEntry, ...] = (
        ModelEntry(
            host=Host.google_ai, vendor=Vendor.google, model="x",
            display_name="x", short_name="x", description="x",
            is_default=False,
        ),
    )
    count = sum(1 for e in bad_catalog if e.is_default)
    assert count == 0
    # The module-level guard turns this into ValueError. Simulate:
    with pytest.raises(ValueError, match="exactly one default"):
        if count != 1:
            raise ValueError(f"MODEL_CATALOG must have exactly one default; found {count}")
```

- [ ] **Step 3: Run tests to verify they fail.**

```bash
cd backend && uv run pytest tests/test_catalog.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.core.providers.catalog'`.

- [ ] **Step 4: Create the module.** Write the content shown above.

- [ ] **Step 5: Run tests.**

```bash
cd backend && uv run pytest tests/test_catalog.py -v
```

Expected: 12 passed.

- [ ] **Step 6: Toolchain gate.**

```bash
cd backend && uv run ruff format app/providers/catalog.py tests/test_catalog.py \
  && uv run ruff check app/providers/catalog.py tests/test_catalog.py \
  && uv run mypy app/providers/catalog.py
```

- [ ] **Step 7: Commit.**

```bash
git add backend/app/providers/catalog.py backend/tests/test_catalog.py
git commit -m "$(cat <<'EOF'
feat(providers): add backend-owned model catalog

Single source of truth for which models pawrrtal exposes. Entries
carry the canonical host:vendor/model identity plus display
metadata; exactly one entry has is_default=True (enforced at
import). CATALOG_ETAG is the SHA-256 prefix used by the upcoming
GET /api/v1/models route as an ETag header.

The frontend's PAWRRTAL_MODELS catalog disappears in a later
commit; this is the source it'll fetch from.

ADR §3.
EOF
)"
```

- [ ] **Step 8: Mark bean complete.**

---

### Task 3: `GET /api/v1/models` endpoint (auth + ETag)

**Files:**
- Modify: `backend/app/api/models.py` (replace placeholder body)
- Test: `backend/tests/test_models_api.py` (new)

**Concrete content for `backend/app/api/models.py`:**

```python
"""``/api/v1/models`` — exposes the backend catalog to clients."""

from __future__ import annotations

from fastapi import Depends, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from pydantic import BaseModel

from app.core.providers.catalog import CATALOG_ETAG, MODEL_CATALOG, ModelEntry
from app.models import User
from app.users import get_allowed_user


class ModelOption(BaseModel):
    """One model returned by ``GET /api/v1/models``."""

    id: str
    host: str
    vendor: str
    model: str
    display_name: str
    short_name: str
    description: str
    is_default: bool


class ModelsResponse(BaseModel):
    """Envelope for the catalog response."""

    models: list[ModelOption]


def _to_option(entry: ModelEntry) -> ModelOption:
    return ModelOption(
        id=entry.id,
        host=entry.host.value,
        vendor=entry.vendor.value,
        model=entry.model,
        display_name=entry.display_name,
        short_name=entry.short_name,
        description=entry.description,
        is_default=entry.is_default,
    )


def get_models_router() -> APIRouter:
    """Build the ``/api/v1/models`` router.

    Returns:
        An ``APIRouter`` exposing ``GET /api/v1/models`` behind the
        standard authed-user dependency.
    """
    router = APIRouter(prefix="/api/v1/models", tags=["models"])

    @router.get("")
    def list_models(
        request: Request,
        _user: User = Depends(get_allowed_user),
    ) -> Response:
        """Return the catalog with ``ETag`` caching.

        A ``304 Not Modified`` (empty body) is returned when the
        client's ``If-None-Match`` matches the in-memory catalog
        hash. Use ``Response(status_code=304)`` rather than
        ``HTTPException(304)`` so the response has no body — FastAPI
        serialises ``HTTPException`` with a ``detail`` payload,
        which violates RFC 7232.
        """
        if request.headers.get("if-none-match") == CATALOG_ETAG:
            return Response(
                status_code=status.HTTP_304_NOT_MODIFIED,
                headers={"ETag": CATALOG_ETAG},
            )
        body = ModelsResponse(models=[_to_option(e) for e in MODEL_CATALOG])
        return JSONResponse(
            content=body.model_dump(),
            headers={
                "ETag": CATALOG_ETAG,
                "Cache-Control": "private, must-revalidate",
            },
        )

    return router
```

**Concrete content for `backend/tests/test_models_api.py`:**

`backend/tests/conftest.py` provides a single authed `client` fixture
(an `httpx.AsyncClient` bound to a `FastAPI` instance with the
`get_allowed_user` dependency overridden to return the `test_user`).
The endpoint inherits that override, so no per-test cookie plumbing
is needed.

```python
"""Tests for ``GET /api/v1/models``."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.providers.catalog import CATALOG_ETAG, MODEL_CATALOG


@pytest.mark.anyio
async def test_models_endpoint_returns_catalog(client: AsyncClient) -> None:
    response = await client.get("/api/v1/models")
    assert response.status_code == 200
    body = response.json()
    assert "models" in body
    assert len(body["models"]) == len(MODEL_CATALOG)
    first = body["models"][0]
    for key in ("id", "host", "vendor", "model", "display_name", "is_default"):
        assert key in first


@pytest.mark.anyio
async def test_models_endpoint_sets_etag(client: AsyncClient) -> None:
    response = await client.get("/api/v1/models")
    assert response.headers["etag"] == CATALOG_ETAG
    assert "private" in response.headers["cache-control"]


@pytest.mark.anyio
async def test_models_endpoint_returns_304_when_etag_matches(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/models",
        headers={"If-None-Match": CATALOG_ETAG},
    )
    assert response.status_code == 304
    assert response.content == b""  # 304 must have empty body


@pytest.mark.anyio
async def test_default_entry_present(client: AsyncClient) -> None:
    response = await client.get("/api/v1/models")
    defaults = [m for m in response.json()["models"] if m["is_default"]]
    assert len(defaults) == 1
```

The "unauthenticated → 401" test that would normally guard the auth
posture is omitted here because `backend/tests/conftest.py:108` ships
the `client` with the auth dependency pre-overridden — the only way
to test the unauthed path is a separate fixture that uses the raw
`FastAPI` instance without overrides. If you want that coverage, add
a `client_unauthed` fixture alongside `client` in conftest as a
separate concern; it's out of scope for this task.

**Steps:**

- [ ] **Step 1: Beans entry.**

- [ ] **Step 2: Inspect existing test conftest** to confirm fixture names for the authed HTTP client.

```bash
grep -n "@pytest.fixture\|def async_client\|def authed_cookie\|def authed_client" backend/tests/conftest.py | head -20
```

If the fixture names differ, adjust the test imports and arguments accordingly. Common alternatives: `client`, `test_user`, `auth_cookies`.

- [ ] **Step 3: Write the failing tests.** Copy the content above (adjusting fixture names if needed).

- [ ] **Step 4: Run tests.**

```bash
cd backend && uv run pytest tests/test_models_api.py -v
```

Expected: 5 failures pointing at the placeholder response shape.

- [ ] **Step 5: Replace the placeholder.** Write the full `backend/app/api/models.py` content shown above.

- [ ] **Step 6: Run tests.** Expected: 5 passed.

- [ ] **Step 7: Toolchain gate.**

```bash
cd backend && uv run ruff format app/api/models.py tests/test_models_api.py \
  && uv run ruff check app/api/models.py tests/test_models_api.py \
  && uv run mypy app/api/models.py
```

- [ ] **Step 8: Smoke test end-to-end** with a running dev server.

```bash
just dev  # in a separate terminal; wait for ready
curl -i http://localhost:8000/api/v1/models  # expect 401
# Then with a valid cookie from a dev login, confirm 200 + ETag.
```

- [ ] **Step 9: Commit.**

```bash
git add backend/app/api/models.py backend/tests/test_models_api.py
git commit -m "$(cat <<'EOF'
feat(api): expose the model catalog via GET /api/v1/models

Replaces the placeholder router with a real catalog endpoint. Sits
behind get_allowed_user (consistent with every other /api/v1/*
route). Sets ETag (CATALOG_ETAG) + Cache-Control: private,
must-revalidate so the frontend can revalidate cheaply.

ADR §4.
EOF
)"
```

- [ ] **Step 10: Mark bean complete.**

---

## Chunk 2: Backend integration (validators + factory + consumers)

This chunk wires the new modules into existing code paths. Each commit narrows or removes a vestigial concept.

### Task 4: Pydantic `CanonicalModelId` validator on all schemas

**Files:**
- Modify: `backend/app/schemas.py` (add `CanonicalModelId` Annotated type; apply to `ChatRequest.model_id:226`, `ConversationUpdate.model_id:86`, `ConversationResponse.model_id:69`). `ConversationCreate` (line 44) does NOT carry `model_id` today and stays unchanged.
- Modify: `backend/app/infrastructure/config.py` (add `strict_conversation_read_validation: bool = True`)
- Test: `backend/tests/test_providers_and_schemas.py` (deferred to Task 5 — Task 4 only adds schema-side tests)
- Test: `backend/tests/test_conversation_read.py` (new — exercises the `ConversationResponse.model_id` read-validator behaviour with the strict / permissive flag)

**Steps:**

- [ ] **Step 1: Beans entry.**

- [ ] **Step 2: Read current schemas.** Open `backend/app/schemas.py` and locate every `model_id` field. Already known: line 69 (`ConversationResponse.model_id`), line 86 (`ChatRequest.model_id`); confirm `ConversationCreate` / `ConversationUpdate`.

```bash
grep -n "model_id" backend/app/schemas.py
```

- [ ] **Step 3: Add `CanonicalModelId` to `schemas.py`.**

Near the imports (note: `logging` is required because the permissive
read-validator logs the bad row; `default_model` is hoisted to module
scope since `schemas.py → catalog.py → model_id.py` is acyclic):

```python
import logging
from typing import Annotated

from pydantic import AfterValidator

from app.core.config import settings
from app.core.providers.catalog import default_model
from app.core.providers.model_id import InvalidModelId, parse_model_id

logger = logging.getLogger(__name__)


def _canonicalise_model_id(raw: str | None) -> str | None:
    """Pydantic validator that rewrites any accepted input shape to
    canonical ``host:vendor/model`` form. ``None`` passes through.

    Raises:
        ValueError: If the string fails to parse (FastAPI maps this
            to HTTP 422).
    """
    if raw is None:
        return None
    try:
        return parse_model_id(raw).id
    except InvalidModelId as exc:
        # Re-raise as ValueError so Pydantic generates a clean 422.
        raise ValueError(str(exc)) from exc


def _canonicalise_model_id_for_read(raw: str | None) -> str | None:
    """Output validator for ``ConversationResponse.model_id``.

    Defaults to strict (matches the input contract). When
    ``settings.strict_conversation_read_validation`` is ``False``,
    a non-canonical stored value falls back to the catalog default
    and is logged. Operator escape hatch, not a documented contract.
    """
    if raw is None:
        return None
    try:
        return parse_model_id(raw).id
    except InvalidModelId as exc:
        if settings.strict_conversation_read_validation:
            raise ValueError(str(exc)) from exc
        logger.warning(
            "CONVERSATION_READ_FALLBACK bad_model_id=%r error=%s",
            raw, exc,
        )
        return default_model().id


CanonicalModelId = Annotated[str | None, AfterValidator(_canonicalise_model_id)]
CanonicalModelIdForRead = Annotated[
    str | None, AfterValidator(_canonicalise_model_id_for_read)
]
```

Replace `model_id: str | None = None` in `ChatRequest:226` and `ConversationUpdate:86` with `model_id: CanonicalModelId = None`.

Replace `model_id: str | None = None` in `ConversationResponse:69` with `model_id: CanonicalModelIdForRead = None`. (`ConversationCreate` does not carry `model_id` today and is left untouched.)

- [ ] **Step 4: Add the feature-flag setting.**

In `backend/app/infrastructure/config.py`, add inside the `Settings` class:

```python
strict_conversation_read_validation: bool = True
"""When True, ConversationResponse 422s on a non-canonical stored
model_id. When False (operator escape hatch), the bad value falls
back to ``catalog.default_model().id`` and the row is logged."""
```

- [ ] **Step 5: Write the validator tests** in `backend/tests/test_conversation_read.py`:

```python
"""ConversationResponse.model_id validator behaviour with the strict /
permissive feature flag."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.core.providers.catalog import default_model
from app.schemas import ConversationResponse


def _read_row(model_id: str | None) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "user_id": str(uuid4()),
        "title": "x",
        "status": "active",
        "labels": [],
        "model_id": model_id,
    }


def test_canonical_value_passes_through_unchanged() -> None:
    canonical = default_model().id
    read = ConversationResponse.model_validate(_read_row(canonical))
    assert read.model_id == canonical


def test_strict_mode_rejects_bare_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "strict_conversation_read_validation", True)
    with pytest.raises(ValidationError):
        ConversationResponse.model_validate(_read_row("gemini-3-flash-preview"))


def test_permissive_mode_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "strict_conversation_read_validation", False)
    read = ConversationResponse.model_validate(_read_row("gemini-3-flash-preview"))
    assert read.model_id == default_model().id
    assert any("CONVERSATION_READ_FALLBACK" in r.message for r in caplog.records)


def test_canonicalises_bare_form_on_input() -> None:
    """ChatRequest accepts the vendor-only form and rewrites to canonical."""
    from app.schemas import ChatRequest

    req = ChatRequest(question="hi", model_id="anthropic/claude-sonnet-4-6")
    assert req.model_id == "agent-sdk:anthropic/claude-sonnet-4-6"


def test_rejects_bare_on_input() -> None:
    from app.schemas import ChatRequest

    with pytest.raises(ValidationError):
        ChatRequest(question="hi", model_id="claude-sonnet-4-6")
```

Adjust the field set in `_read_row` to whatever `ConversationResponse` actually requires; consult `backend/app/schemas.py`.

- [ ] **Step 6: Run the validator tests** in isolation.

```bash
cd backend && uv run pytest tests/test_conversation_read.py -v
```

Expected: 5 passed. The factory-test rewrite that *also* lives in `test_providers_and_schemas.py` is intentionally deferred to Task 5 — landing it now would leave failing tests in the tree across the Task 4 commit boundary (violates the tests-in-same-commit rule).

- [ ] **Step 7: Toolchain gate** the touched files.

```bash
cd backend && uv run ruff format app/schemas.py app/infrastructure/config.py tests/test_conversation_read.py \
  && uv run ruff check app/schemas.py app/infrastructure/config.py tests/test_conversation_read.py \
  && uv run mypy app/schemas.py app/infrastructure/config.py
```

- [ ] **Step 8: Commit.**

```bash
git add backend/app/schemas.py backend/app/infrastructure/config.py backend/tests/test_conversation_read.py
git commit -m "$(cat <<'EOF'
feat(schemas): canonicalise model_id at every API boundary

Adds CanonicalModelId / CanonicalModelIdForRead Annotated types and
applies them to ChatRequest.model_id, ConversationUpdate.model_id,
and ConversationResponse.model_id. Inputs in the vendor-only form
(anthropic/...) are rewritten to the canonical host:vendor/model on
the way in. Read-side validation matches input strictness; an
operator-only STRICT_CONVERSATION_READ_VALIDATION flag opens an
escape hatch that falls back to catalog default + logs the bad row.

ADR §2a, §9.
EOF
)"
```

- [ ] **Step 9: Mark bean complete.**

---

### Task 5: Factory rewrite + delete vestigial strip helper

**Files:**
- Modify: `backend/app/providers/factory.py` — replace prefix routing with `HOST_TO_PROVIDER` map; resolve_llm takes `str | ParsedModelId | None`; delete `_strip_provider_segment`, `_GEMINI_PREFIXES`, `_CLAUDE_PREFIXES`, `_PROVIDER_SEGMENTS`, `_DEFAULT_MODEL`
- Modify: `backend/app/providers/claude_provider.py` — no structural change, but factory now passes bare `parsed.model` to constructor (already what `_model_id` stores); document the contract in the docstring
- Modify: `backend/app/providers/agno_provider.py` — same contract update
- Test: `backend/tests/test_providers_and_schemas.py` — rewrite from Task 4 lands here

**Concrete content for `factory.py`:**

```python
"""Provider factory — resolves a canonical model ID to an :class:`AILLM`."""

from __future__ import annotations

import uuid

from app.core.config import settings

from .agno_provider import AgnoLLM
from .base import AILLM
from .claude_provider import ClaudeLLM, ClaudeLLMConfig
from .gemini_provider import GeminiLLM
from .model_id import Host, ParsedModelId, parse_model_id


HOST_TO_PROVIDER: dict[Host, type[AILLM]] = {
    Host.agent_sdk: ClaudeLLM,
    Host.google_ai: GeminiLLM,
}


def resolve_llm(
    model_id: str | ParsedModelId | None,
    *,
    user_id: uuid.UUID | None = None,
) -> AILLM:
    """Return the correct :class:`AILLM` for ``model_id``.

    Args:
        model_id: Canonical wire string (``host:vendor/model``) or a
            pre-parsed identifier. ``None`` defaults to the catalog's
            default model.
        user_id: Authenticated user UUID, used to resolve per-workspace
            API-key overrides. ``None`` falls back to the global key.

    Returns:
        A provider instance ready to ``stream()``.

    Raises:
        InvalidModelId: If ``model_id`` is a string that doesn't parse.
        KeyError: If ``parsed.host`` has no provider class registered
            (programming error; should not happen at runtime once
            the catalog and ``HOST_TO_PROVIDER`` agree).
    """
    if isinstance(model_id, ParsedModelId):
        parsed = model_id
    else:
        # Local import: avoid a hard import cycle (catalog imports model_id;
        # factory uses catalog only for the default fallback).
        from .catalog import default_model

        raw = model_id if model_id is not None else default_model().id
        parsed = parse_model_id(raw)

    provider_cls = HOST_TO_PROVIDER[parsed.host]
    if provider_cls is ClaudeLLM:
        config = ClaudeLLMConfig(
            oauth_token=settings.claude_code_oauth_token or None,
        )
        return ClaudeLLM(parsed.model, config=config, user_id=user_id)
    return provider_cls(parsed.model, user_id=user_id)
```

Notes on the constructor contract: `ClaudeLLM.__init__(model_id, ...)` and `GeminiLLM.__init__(model_id, ...)` both currently take a bare slug. The factory passes `parsed.model` (e.g. `"claude-sonnet-4-6"`) — matching `_MODEL_MAP` keys in `claude_provider.py:87`, which stay bare.

**Steps:**

- [ ] **Step 1: Beans entry.**

- [ ] **Step 2: Rewrite the factory tests** in `backend/tests/test_providers_and_schemas.py`. Delete:

```python
def test_resolve_llm_strips_google_provider_segment() -> None: ...
def test_resolve_llm_strips_anthropic_provider_segment() -> None: ...
def test_resolve_llm_preserves_bare_model_id() -> None: ...
```

Replace with parse-based tests:

```python
def test_resolve_llm_accepts_canonical_anthropic_id() -> None:
    provider = resolve_llm("agent-sdk:anthropic/claude-sonnet-4-6")
    assert isinstance(provider, ClaudeLLM)
    assert provider._model_id == "claude-sonnet-4-6"


def test_resolve_llm_canonicalises_vendor_only_form() -> None:
    provider = resolve_llm("anthropic/claude-sonnet-4-6")
    assert isinstance(provider, ClaudeLLM)
    assert provider._model_id == "claude-sonnet-4-6"


def test_resolve_llm_rejects_bare_model_id() -> None:
    from app.core.providers.model_id import InvalidModelId

    with pytest.raises(InvalidModelId):
        resolve_llm("claude-sonnet-4-6")


def test_resolve_llm_routes_google_via_host_table() -> None:
    provider = resolve_llm("google/gemini-3-flash-preview")
    assert isinstance(provider, GeminiLLM)
    assert provider._model_id == "gemini-3-flash-preview"
```

- [ ] **Step 3: Run tests to confirm they fail.**

```bash
cd backend && uv run pytest tests/test_providers_and_schemas.py -v
```

Expected: the new tests fail because `_strip_provider_segment` is still in place and the host-routing isn't.

- [ ] **Step 4: Replace `factory.py`** with the content above. Delete `_PROVIDER_SEGMENTS`, `_strip_provider_segment`, `_GEMINI_PREFIXES`, `_CLAUDE_PREFIXES`, `_DEFAULT_MODEL`.

- [ ] **Step 5: Update provider docstrings** to document the bare-slug contract.

In `claude_provider.py:174` add to the `__init__` docstring: "``model_id`` is the bare vendor slug (e.g. ``claude-sonnet-4-6``), not the canonical wire form. The factory calls ``parse_model_id`` first and hands the unwrapped slug here."

Same change in `agno_provider.py:18`.

- [ ] **Step 6: Run tests.**

```bash
cd backend && uv run pytest tests/test_providers_and_schemas.py tests/test_telegram_channel.py tests/test_chat_api.py tests/test_claude_provider.py -v
```

Expected: all green. If `test_telegram_channel.py` or `test_chat_api.py` fail because they pass bare IDs, that's expected — Tasks 6 and 7 will update them.

- [ ] **Step 7: Toolchain gate** the touched files.

- [ ] **Step 8: Commit.**

```bash
git add backend/app/providers/factory.py \
        backend/app/providers/claude_provider.py \
        backend/app/providers/agno_provider.py \
        backend/tests/test_providers_and_schemas.py
git commit -m "$(cat <<'EOF'
refactor(providers): route on Host enum, delete strip helper

resolve_llm now accepts a canonical wire ID (or pre-parsed
ParsedModelId), dispatches via HOST_TO_PROVIDER, and passes the
bare vendor slug to provider constructors. The morning's
_strip_provider_segment() and the _GEMINI_PREFIXES /
_CLAUDE_PREFIXES tuples are gone; their job moved into
parse_model_id().

The bug fixed by pawrrtal-5854 is now structurally impossible —
a non-canonical model_id 422s at the Pydantic boundary; a
canonical one routes by host.

ADR §5, §5b.
EOF
)"
```

- [ ] **Step 9: Mark bean complete.**

---

### Task 6: Chat router + utility callers source default from catalog

**Files:**
- Modify: `backend/app/chat/router.py` — delete `_DEFAULT_MODEL`; use `catalog.default_model().id`
- Modify: `backend/app/agents/` — drop the `gemini-3.1-flash-lite-preview` default; require model from caller
- Modify: `backend/app/conversations/title.py` — drop `_DEFAULT_MODEL = "gemini-2.0-flash"`; require model from caller (or accept `None` and fetch from catalog)

> ⚠️ **Heads-up:** the three `_DEFAULT_MODEL` constants currently disagree:
> `chat.py:50` = `"gemini-3-flash-preview"`,
> `factory.py:18` = `"gemini-2.5-flash-preview-05-20"`,
> `gemini_utils.py:10` = `"gemini-2.0-flash"`.
> All three collapse to one source: `catalog.default_model()`. The catalog's `is_default=True` entry is `google/gemini-3-flash-preview` (see Task 2). Do not cargo-cult the value from any individual file — read it from the catalog.
- Test: `backend/tests/test_chat_api.py` — verify the catalog default flows through when request omits model_id

**Steps:**

- [ ] **Step 1: Beans entry.**

- [ ] **Step 2: Inspect every caller of `agents.create_agent` and `gemini_utils.generate_text_once`.**

```bash
grep -rn "create_agent\|generate_text_once" backend/app backend/tests | grep -v "\.pyc"
```

- [ ] **Step 3: Update `gemini_utils.py`.**

Change the signature from `model_id: str = _DEFAULT_MODEL` to `model_id: str | None = None`; inside, if `model_id is None`, call `catalog.default_model().model` (bare slug — the function passes it directly to the Gemini SDK). Delete the module-level `_DEFAULT_MODEL`.

Update every caller in `backend/app/` to pass an explicit model, or accept the default by passing `None` explicitly. Audit shows this is used for title/auto-summary generation; both callers should pass `catalog.default_model().model` explicitly so changes to the catalog default propagate uniformly.

- [ ] **Step 4: Update `agents.py`.**

Change the signature from `model_id: str = "gemini-3.1-flash-lite-preview"` to `model_id: str` (required, no default). Every caller must now pass a model; audit them and update.

- [ ] **Step 5: Update `chat.py`.**

Delete `_DEFAULT_MODEL = "gemini-3-flash-preview"` at line 50. Replace the `model_id = request.model_id or conversation.model_id or _DEFAULT_MODEL` line with:

```python
from app.core.providers.catalog import default_model

# ...

model_id = (
    request.model_id  # already canonical (Pydantic validator)
    or conversation.model_id  # already canonical
    or default_model().id
)
```

- [ ] **Step 6: Add a chat-API test** that asserts the catalog default flows through when neither request nor conversation supplies a model. In `backend/tests/test_chat_api.py`:

```python
@pytest.mark.anyio
async def test_chat_falls_back_to_catalog_default_when_no_model_id_given(...) -> None:
    """A POST with no model_id and a fresh conversation uses catalog.default_model().id."""
    # ... existing fixtures + assertions on the saved conversation row
```

- [ ] **Step 7: Run all touched tests.**

```bash
cd backend && uv run pytest tests/test_chat_api.py tests/test_providers_and_schemas.py -v
```

- [ ] **Step 8: Toolchain gate.**

- [ ] **Step 9: Commit.**

```bash
git add backend/app/chat/router.py backend/app/agents/ backend/app/conversations/title.py backend/tests/test_chat_api.py
git commit -m "$(cat <<'EOF'
refactor(api): source default model from catalog everywhere

Removes the three independent _DEFAULT_MODEL constants in chat.py,
agents.py, and gemini_utils.py. The catalog is now the only place
that names "the default model." chat.py reads via
catalog.default_model().id; utility callers in agents.py /
gemini_utils.py require the caller to pass an explicit model (or
read the catalog themselves).

ADR §5b, §10.
EOF
)"
```

- [ ] **Step 10: Mark bean complete.**

---

## Chunk 3: Telegram path

### Task 7: Telegram `/model` parse-on-write + bot adapter UnknownModelId auto-clear

**Files:**
- Modify: `backend/app/integrations/telegram/handlers.py` — delete `_DEFAULT_MODEL` and `_VALID_MODEL_PREFIXES`; `/model` calls `parse_model_id` on user input; stores `parsed.id`; reply copy rewritten; inline TODO with bean reference
- Modify: `backend/app/integrations/telegram/bot.py` — wrap the `resolve_llm` call in `try / except UnknownModelId`; on failure call `update_conversation_model(..., None, ...)` and retry with `catalog.default_model().id`
- Test: `backend/tests/test_telegram_channel.py` — `/model` malformed/known/unknown paths; auto-clear on UnknownModelId; subsequent turn cleanly uses default

**Steps:**

- [ ] **Step 1: Beans entry.**

- [ ] **Step 2: Write the failing tests.**

In `backend/tests/test_telegram_channel.py`, add (or rewrite):

```python
@pytest.mark.anyio
async def test_model_command_rejects_malformed_input(...) -> None:
    """/model bogus → user-facing error, nothing stored."""


@pytest.mark.anyio
async def test_model_command_stores_canonical_form_for_well_formed_input(...) -> None:
    """/model anthropic/claude-sonnet-4-6 stores agent-sdk:anthropic/claude-sonnet-4-6."""


@pytest.mark.anyio
async def test_chat_turn_auto_clears_unknown_stored_model(...) -> None:
    """A stored well-formed but unknown ID raises UnknownModelId at chat
    time; bot adapter replies + clears model_id; next turn uses default."""


@pytest.mark.anyio
async def test_following_turn_uses_catalog_default_after_clear(...) -> None:
    """After the auto-clear path runs once, subsequent turns proceed normally."""


@pytest.mark.anyio
async def test_valid_model_after_clear_restores_user_choice(...) -> None:
    """User can re-set with a known /model and chat resumes with their choice."""
```

Fixture setup likely needs a way to write a "bogus stored model_id" directly into the test DB to simulate the case where the parse-on-write was bypassed (e.g. row predates this commit). Use the existing `db_session` fixture and write the row through SQLAlchemy directly.

- [ ] **Step 3: Run tests to confirm failure.**

- [ ] **Step 4: Rewrite the `/model` handler.**

Delete `_DEFAULT_MODEL` and `_VALID_MODEL_PREFIXES`. The handler body becomes (sketch):

```python
async def handle_model_command(
    raw: str, sender: TelegramSender, session: AsyncSession,
) -> str:
    # TODO(pawrrtal-25yy): once we add catalog.is_known() here, the
    # auto-clear path in bot.py becomes a backstop instead of the
    # primary error surface. For now, stay catalog-ignorant.
    try:
        parsed = parse_model_id(raw)
    except InvalidModelId as exc:
        return _MODEL_INVALID_MESSAGE.format(raw=raw, reason=str(exc))

    binding = await get_user_id_for_external(sender.user_id, session)
    if binding is None:
        return _MODEL_NOT_BOUND_MESSAGE

    conversation = await get_or_create_telegram_conversation_full(
        binding.user_id, session, sender.thread_id,
    )
    await update_conversation_model(conversation.id, parsed.id, session)
    return _MODEL_OK_MESSAGE.format(model_id=parsed.id)
```

Rewrite `_MODEL_MISSING_MESSAGE` / new `_MODEL_INVALID_MESSAGE` copy to not enumerate hardcoded prefixes.

- [ ] **Step 5: Rewrite the bot adapter** in `bot.py`. Find the `resolve_llm(context.model_id)` call (line 199) and wrap:

```python
from app.core.providers.catalog import default_model
from app.core.providers.model_id import InvalidModelId, UnknownModelId

# ...

try:
    parsed = parse_model_id(context.model_id)
    catalog.require_known(parsed.id)  # raises UnknownModelId on miss
    provider = resolve_llm(parsed, user_id=context.user_id)
except (InvalidModelId, UnknownModelId) as exc:
    await _send_reply(
        bot, sender,
        f"Model `{context.model_id}` isn't usable: {exc}. "
        f"Switching you back to the default.",
    )
    await update_conversation_model(conversation_id, None, session)
    # This turn uses the default; the stored row is now NULL so future
    # turns read the default cleanly.
    provider = resolve_llm(default_model().id, user_id=context.user_id)
```

- [ ] **Step 6: Run tests.**

```bash
cd backend && uv run pytest tests/test_telegram_channel.py -v
```

- [ ] **Step 7: Toolchain gate.**

- [ ] **Step 8: Commit.**

```bash
git add backend/app/integrations/telegram/handlers.py \
        backend/app/integrations/telegram/bot.py \
        backend/tests/test_telegram_channel.py
git commit -m "$(cat <<'EOF'
refactor(telegram): drop per-channel model catalog + add safety net

Telegram stops carrying _DEFAULT_MODEL and _VALID_MODEL_PREFIXES.
/model now calls parse_model_id() on user input and stores the
canonical form; only the structural parser is shared (Telegram is
catalog-ignorant per design).

The chat-turn path wraps resolve_llm in a try/except for
InvalidModelId and UnknownModelId. On either, the bot replies with
the bad ID and clears the stored model_id to NULL so the *next*
turn reads catalog.default_model() cleanly — no
"every-turn-fails-forever" UX trap.

Inline TODO references bean pawrrtal-25yy (proactive catalog
validation at /model time, future).

ADR §7.
EOF
)"
```

- [ ] **Step 9: Mark bean complete.**

---

## Chunk 4: Frontend (delete duplicate catalog, fetch + adapt)

### Task 8: `useChatModels` hook + Zod validation + canonical-ID matcher

**Files:**
- Create: `frontend/features/chat/hooks/use-chat-models.ts`
- Create: `frontend/features/chat/hooks/use-chat-models.test.ts`
- Create: `frontend/features/chat/lib/is-canonical-model-id.ts`
- Create: `frontend/features/chat/lib/is-canonical-model-id.test.ts`

**Concrete content for `is-canonical-model-id.ts`:**

```ts
/**
 * Pure regex matcher for the canonical pawrrtal model-ID wire form
 * (mirrors the backend's `parse_model_id` regex). Used as the
 * `usePersistedState` validator for `chat-composer:selected-model-id`.
 */

const CANONICAL_MODEL_ID_RE = /^([a-z][a-z0-9-]*:)?[a-z][a-z0-9-]*\/[a-z0-9][a-z0-9.\-_]*$/;

/**
 * Returns true if `s` matches the canonical model-ID structure.
 * Does not check catalog membership — that's a server concern.
 */
export function isCanonicalModelId(s: unknown): s is string {
	return typeof s === 'string' && CANONICAL_MODEL_ID_RE.test(s);
}
```

**Concrete content for `use-chat-models.ts`:**

`useAuthedQuery` (`frontend/hooks/use-authed-query.ts`) does **not**
accept a `validate` option — its full surface is
`{ enabled?, staleTime? }`. The hook below uses `useQuery` directly
with `useAuthedFetch` inside the `queryFn` and runs the Zod parse
there. Mirrors the pattern in `frontend/hooks/get-conversations.ts`.

```ts
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';

/** One model returned by `GET /api/v1/models`. */
export interface ChatModelOption {
	/** Canonical wire form: `host:vendor/model`. */
	id: string;
	/** Where the model runs (e.g. `agent-sdk`, `google-ai`). */
	host: string;
	/** Vendor segment (e.g. `anthropic`, `google`, `openai`). */
	vendor: string;
	/** Vendor's own slug (e.g. `claude-sonnet-4-6`). */
	model: string;
	/** Long display name shown in the picker. */
	display_name: string;
	/** Short label for mobile / compact contexts. */
	short_name: string;
	description: string;
	is_default: boolean;
}

/** `useChatModels()` return shape. */
export interface UseChatModelsResult {
	/** Catalog entries, empty array during initial fetch. */
	models: readonly ChatModelOption[];
	/** The entry with `is_default: true`. `null` while loading. */
	default: ChatModelOption | null;
	isLoading: boolean;
	error: Error | null;
}

const ModelOptionSchema = z.object({
	id: z.string(),
	host: z.string(),
	vendor: z.string(),
	model: z.string(),
	display_name: z.string(),
	short_name: z.string(),
	description: z.string(),
	is_default: z.boolean(),
});

const ModelsResponseSchema = z.object({
	models: z.array(ModelOptionSchema),
});

/**
 * Fetches the backend model catalog via TanStack Query.
 *
 * `staleTime: Infinity` keeps the catalog cached for the session; the
 * HTTP route exposes an ETag and the fetch wrapper sends
 * `If-None-Match`, so revalidation is cheap when it does happen
 * (e.g. on `window.focus`).
 */
export function useChatModels(): UseChatModelsResult {
	const authedFetch = useAuthedFetch();
	const query = useQuery({
		queryKey: ['models'],
		staleTime: Number.POSITIVE_INFINITY,
		queryFn: async (): Promise<{ models: ChatModelOption[] }> => {
			const res = await authedFetch('/api/v1/models');
			if (!res.ok) throw new Error(`models fetch failed: ${res.status}`);
			return ModelsResponseSchema.parse(await res.json());
		},
	});

	const models = query.data?.models ?? [];
	const defaultEntry = useMemo(
		() => models.find((m) => m.is_default) ?? null,
		[models],
	);

	return {
		models,
		default: defaultEntry,
		isLoading: query.isLoading,
		error: query.error ?? null,
	};
}
```

**Steps:**

- [ ] **Step 1: Beans entry.**

- [ ] **Step 2: Check the existing `useAuthedQuery` contract.**

```bash
sed -n '1,60p' frontend/hooks/use-authed-query.ts
grep -rn "useAuthedQuery" frontend/ | head -10
```

Adapt the hook draft above to match. If the existing pattern is `useAuthedQuery<T>(key, path)` without a validate option, do the Zod parse inside the queryFn via a small wrapper.

- [ ] **Step 3: Write the matcher.**

Create `frontend/features/chat/lib/is-canonical-model-id.ts` with the content above.

- [ ] **Step 4: Write tests for the matcher.**

`frontend/features/chat/lib/is-canonical-model-id.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { isCanonicalModelId } from './is-canonical-model-id';

describe('isCanonicalModelId', () => {
	it('accepts host-prefixed canonical', () => {
		expect(isCanonicalModelId('agent-sdk:anthropic/claude-sonnet-4-6')).toBe(true);
	});

	it('accepts vendor-only form', () => {
		expect(isCanonicalModelId('anthropic/claude-sonnet-4-6')).toBe(true);
	});

	it('rejects bare slug', () => {
		expect(isCanonicalModelId('claude-sonnet-4-6')).toBe(false);
	});

	it('rejects empty string', () => {
		expect(isCanonicalModelId('')).toBe(false);
	});

	it('rejects whitespace', () => {
		expect(isCanonicalModelId('anthropic / claude-sonnet-4-6')).toBe(false);
	});

	it('rejects non-strings', () => {
		expect(isCanonicalModelId(undefined)).toBe(false);
		expect(isCanonicalModelId(null)).toBe(false);
		expect(isCanonicalModelId(123)).toBe(false);
	});
});
```

- [ ] **Step 5: Run matcher tests.**

```bash
cd frontend && bun run test --run -- features/chat/lib/is-canonical-model-id.test.ts
```

Expected: 6 passed.

- [ ] **Step 6: Write the hook.**

Adapt the `use-chat-models.ts` content above to the codebase's `useAuthedQuery` shape.

- [ ] **Step 7: Write tests for the hook.**

`use-chat-models.test.ts` — mock fetch (or the project's MSW setup if used) and verify:
- happy path returns the catalog
- empty `models` array yields `default: null`
- Zod failure surfaces as the hook's `error`
- the `default` is the entry with `is_default: true`

- [ ] **Step 8: Run hook tests.**

```bash
cd frontend && bun run test --run -- features/chat/hooks/use-chat-models.test.ts
```

- [ ] **Step 9: Toolchain gate.**

```bash
cd frontend && bun run check && bun run typecheck
```

- [ ] **Step 10: Commit.**

```bash
git add frontend/features/chat/hooks/use-chat-models.ts \
        frontend/features/chat/hooks/use-chat-models.test.ts \
        frontend/features/chat/lib/is-canonical-model-id.ts \
        frontend/features/chat/lib/is-canonical-model-id.test.ts
git commit -m "$(cat <<'EOF'
feat(chat): add useChatModels hook + canonical-ID matcher

TanStack Query wrapper around GET /api/v1/models. Zod-validates the
response per validate-response-shape-at-boundary. staleTime is
Infinity; the ETag plumbing on the server lets refetches short-
circuit cheaply when revalidation does fire.

isCanonicalModelId() mirrors the backend regex for client-side
sanity-checking of stored localStorage values.

ADR §6.
EOF
)"
```

- [ ] **Step 11: Mark bean complete.**

---

### Task 9: Extract `VendorLogos` + refactor `ModelSelectorPopover` to props-driven

**Files:**
- Create: `frontend/features/chat/components/VendorLogos.tsx`
- Modify: `frontend/features/chat/components/ModelSelectorPopover.tsx` — delete the local `CHAT_MODEL_IDS` + `ChatModelId`; receive catalog data via props; use `VendorLogos`
- Modify: `frontend/features/chat/components/ModelSelectorPopover.test.tsx` — inject mock catalog via props

**Steps:**

- [ ] **Step 1: Beans entry.**

- [ ] **Step 2: Read the current popover** end-to-end so the props-driven rewrite preserves behaviour.

```bash
wc -l frontend/features/chat/components/ModelSelectorPopover.tsx
sed -n '1,50p' frontend/features/chat/components/ModelSelectorPopover.tsx
```

- [ ] **Step 3: Extract `VendorLogos.tsx`.** Move whatever vendor-→-icon mapping the popover currently has (look for inline lucide / brand icons keyed off the `provider` field) into a dedicated file:

```tsx
import type { ComponentType, SVGProps } from 'react';
import { AnthropicGlyph, GoogleGlyph, OpenAIGlyph } from '@/components/brand-icons';

/** Vendor → icon component map. UI concern; not a source of truth for the catalog. */
export const VENDOR_LOGOS: Record<string, ComponentType<SVGProps<SVGSVGElement>>> = {
	anthropic: AnthropicGlyph,
	google: GoogleGlyph,
	openai: OpenAIGlyph,
};

/** Returns the icon component for a vendor, falling back to a generic glyph. */
export function vendorLogo(vendor: string): ComponentType<SVGProps<SVGSVGElement>> {
	return VENDOR_LOGOS[vendor] ?? VENDOR_LOGOS.anthropic;
}
```

Adjust import paths to whatever brand-icon module the repo actually has.

- [ ] **Step 4: Rewrite `ModelSelectorPopover.tsx`.**

Remove the local `CHAT_MODEL_IDS` (line 24) and `ChatModelId` (line 35). Change the component's props to:

```tsx
import type { ChatModelOption } from '../hooks/use-chat-models';

interface ModelSelectorPopoverProps {
	models: readonly ChatModelOption[];
	selectedModelId: string;
	onSelectModel: (id: string) => void;
	isLoading?: boolean;
}
```

Every internal reference to `ChatModelId` becomes `string` (the canonical wire form). Grouping by vendor uses `model.vendor` directly. Logo lookup goes through `vendorLogo(model.vendor)`.

If the file blows past the 500-LOC budget, split into `ModelSelectorPopoverView.tsx` (props-only View) and the existing file as the Container — per `.claude/rules/react/view-container-split.md`.

- [ ] **Step 5: Rewrite the popover test.**

`ModelSelectorPopover.test.tsx` — replace `CHAT_MODEL_IDS` imports with a fixture array of `ChatModelOption` passed via props.

- [ ] **Step 6: Run tests.**

```bash
cd frontend && bun run test --run -- features/chat/components/ModelSelectorPopover.test.tsx
```

- [ ] **Step 7: Toolchain gate.**

```bash
cd frontend && bun run check && bun run typecheck
```

- [ ] **Step 8: Commit.**

```bash
git add frontend/features/chat/components/VendorLogos.tsx \
        frontend/features/chat/components/ModelSelectorPopover.tsx \
        frontend/features/chat/components/ModelSelectorPopover.test.tsx
git commit -m "$(cat <<'EOF'
refactor(chat): popover becomes props-driven, kills duplicate catalog

Deletes the in-component CHAT_MODEL_IDS / ChatModelId at the top of
ModelSelectorPopover.tsx (a parallel list that had already drifted
from constants.ts). The picker now receives ChatModelOption[] via
props from useChatModels(); the catalog is server-owned.

Vendor logo lookup moves to VendorLogos.tsx — a UI concern, not a
source-of-truth duplication.

ADR §6.
EOF
)"
```

- [ ] **Step 9: Mark bean complete.**

---

### Task 10: Delete frontend catalog + wire `ChatContainer` to `useChatModels`

**Files:**
- Modify: `frontend/features/chat/constants.ts` — delete `PAWRRTAL_MODELS`, `ChatModelId`, `CHAT_MODEL_IDS`, `DEFAULT_CHAT_MODEL_ID`
- Modify: the chat container (locate via `grep -rln "PAWRRTAL_MODELS\|DEFAULT_CHAT_MODEL_ID" frontend/`)
- Modify: `frontend/features/chat/hooks/use-chat.ts` — already sends `model_id` over the wire (line 130); ensure the value is the canonical form
- Modify: `frontend/features/chat/hooks/use-chat.test.ts` — update fixtures to canonical IDs
- Modify: `usePersistedState` consumer that validates `chat-composer:selected-model-id` — swap the union-allowlist validator for `isCanonicalModelId`

**Steps:**

- [ ] **Step 1: Beans entry.**

- [ ] **Step 2: Map every consumer.**

```bash
grep -rln "PAWRRTAL_MODELS\|DEFAULT_CHAT_MODEL_ID\|CHAT_MODEL_IDS\|ChatModelId" frontend/
```

Expected hits: `constants.ts` (definitions), `ChatContainer` (or equivalent), `use-chat.ts`/`.test.ts`, `ModelSelectorPopover.tsx`/`.test.tsx` (already migrated in Task 9).

- [ ] **Step 3: Update the container** to:
  - Call `useChatModels()`.
  - Pass `models` and `default.id` (with a loading guard) to the picker.
  - Read the stored selection from `usePersistedState` whose validator is now `isCanonicalModelId`.
  - When the stored value isn't a canonical ID, fall back to `default?.id`.

If `useChatModels` is still loading on first render, the composer is disabled. Once `default` is non-null, the selected model resolves to either the stored canonical value or the default.

- [ ] **Step 4: Update `use-chat.ts`** to ensure the `model_id` it POSTs is the canonical wire form (it will be — the container passes it through unchanged). Confirm no transformation is needed.

- [ ] **Step 5: Delete the constants.**

In `frontend/features/chat/constants.ts`, remove:
- `PAWRRTAL_MODELS` (lines 29–79)
- `ChatModelId` (line 82)
- `CHAT_MODEL_IDS` (line 85)
- `DEFAULT_CHAT_MODEL_ID` (line 118)
- the `ChatModelOption` type import

Keep: `CHAT_STORAGE_KEYS`, reasoning levels, safety modes, `FALLBACK_TITLE_MAX_LENGTH`.

- [ ] **Step 6: Update tests.**

`use-chat.test.ts` — replace `'gpt-5.5'` with a canonical fixture like `'agent-sdk:anthropic/claude-sonnet-4-6'`.

- [ ] **Step 7: Smoke the dev server.**

```bash
just dev  # in another terminal
# Hit localhost:3001 with browser, watch console
```

The frontend should render the picker, fetch the catalog, and let you send a message. Watch for `console.error` / `pageerror` — those are gated by `scripts/dev-console-smoke.mjs`.

- [ ] **Step 8: Run the smoke script.**

```bash
node scripts/dev-console-smoke.mjs
```

Expected: clean exit.

- [ ] **Step 9: Toolchain gate.**

```bash
cd frontend && bun run check && bun run typecheck && bun run test --run
```

- [ ] **Step 10: Commit.**

```bash
git add frontend/features/chat/constants.ts \
        frontend/features/chat/<container-file> \
        frontend/features/chat/hooks/use-chat.ts \
        frontend/features/chat/hooks/use-chat.test.ts
git commit -m "$(cat <<'EOF'
refactor(chat): drop frontend catalog, fetch from /api/v1/models

PAWRRTAL_MODELS, ChatModelId, CHAT_MODEL_IDS, and
DEFAULT_CHAT_MODEL_ID are deleted from features/chat/constants.ts.
ChatContainer now reads the live catalog through useChatModels()
and feeds the popover. The stored localStorage selection is
validated against isCanonicalModelId(); non-canonical values fall
back silently to the catalog default on first render.

ADR §6, §10.
EOF
)"
```

- [ ] **Step 11: Mark bean complete.**

---

## Chunk 5: DB reset + integration verification

### Task 11: Wipe the dev DB, run migrations, smoke-test end-to-end

**Files:**
- Delete + recreate: `backend/pawrrtal.db`
- No code change in this task

**Steps:**

- [ ] **Step 1: Confirm `pawrrtal.db` is gitignored** (it is per CLAUDE.md's recent commits) and that wiping it locally won't affect any teammate.

- [ ] **Step 2: Stop all running dev processes.**

- [ ] **Step 3: Wipe and recreate.**

```bash
rm -f backend/pawrrtal.db
cd backend && uv run alembic upgrade head
```

- [ ] **Step 4: Start dev stack.**

```bash
just dev
```

- [ ] **Step 5: Manual smoke checklist** (mark each item):
  - [ ] Web app loads, picker shows all catalog models.
  - [ ] Selecting a Gemini model + sending a message gets a streamed reply.
  - [ ] Selecting a Claude model + sending a message gets a streamed reply.
  - [ ] Page reload restores the selected model.
  - [ ] Telegram bot answers a chat with no prior conversation (catalog default).
  - [ ] `/model anthropic/claude-sonnet-4-6` confirms the switch; next turn uses the new model.
  - [ ] `/model bogus` produces a structural error reply, nothing stored.
  - [ ] `/model bedrock:anthropic/foo` stores canonical-looking ID; next turn replies with the auto-clear message and falls back to default; the turn after that uses default cleanly.

- [ ] **Step 6: Run the full check matrix.**

```bash
just check
cd backend && uv run pytest
cd frontend && bun run test --run
cd frontend && bun run typecheck
node scripts/dev-console-smoke.mjs
```

Expected: all green.

- [ ] **Step 7: Update the parent bean** `pawrrtal-5854` to point at the new design as the canonical fix.

```bash
beans update pawrrtal-5854 --body-append "## Resolution
ADR frontend/content/docs/handbook/decisions/2026-05-14-model-id-canonical-format-and-backend-catalog.md shipped via plan docs/plans/2026-05-14-model-id-canonical-format-and-catalog.md. The morning's _strip_provider_segment workaround is gone; parse_model_id is now the only splitter and the format mismatch is structurally impossible."
```

- [ ] **Step 8: Confirm `pawrrtal-25yy` (deferred follow-up)** still has the correct cross-reference.

- [ ] **Step 9: No commit needed** unless the manual smoke turned up a fix. If a fix was needed, commit it as its own concern.

---

## Post-implementation: open the PR

Use the `pr-to-branch` skill (or `gh pr create` directly). PR title: `feat(chat): canonical model-ID format + backend-owned catalog`.

Body should:
1. Link to the ADR and this plan.
2. List every consumer touched (§5b of the ADR is the source).
3. Note the DB wipe.
4. Note the deferred bean `pawrrtal-25yy`.
5. Call out the `STRICT_CONVERSATION_READ_VALIDATION` flag in the deployment notes.

## Done criteria

- Every checkbox in tasks 1–11 ticked.
- `just check` + `bun run typecheck` + `bun run test --run` + `uv run pytest` all green.
- `pawrrtal.db` recreated; manual smoke passes.
- Beans pawrrtal-5854 and pawrrtal-25yy updated.
- PR opened.
