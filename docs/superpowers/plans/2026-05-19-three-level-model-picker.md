# Three-Level Model Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch both the web chat model selector and the Telegram `/model` picker from a two-level (vendor → models) UI to a three-level (provider/host → vendor → models) UI, collapsing the vendor step automatically when a host has exactly one vendor. Also fixes the existing title-casing bug that renders "Openai", "Xai", "Zai".

**Architecture:** Add one shared label module per side of the stack — `backend/app/providers/labels.py` and `frontend/features/chat/components/model-picker-labels.ts` — that maps `Host` and `Vendor` slugs to display strings. The picker code on each side groups the catalog by host, then by vendor within each host, and renders a one-level menu when a host has a single vendor and a two-level menu when it has multiple. The Telegram callback scheme grows one new shape (`mdl:v:<host>`) and the list shape gains a host segment (`mdl:l:<host>:<vendor>:<page>`); the model-select callback (`mdl:s:<token>:<index>`) is unchanged so in-flight keyboards keep selecting correctly.

**Tech Stack:** Python 3, FastAPI (backend), aiogram (Telegram), TypeScript, React, Vitest (frontend tests), pytest (backend tests), `@octavian-tocan/react-dropdown` (web menu).

---

## Current State (verified by sub-agent read of the code)

- Top-level groups today are **vendors**, not hosts. Web sees "Anthropic / Google / Xai / OpenAI / Zai / Moonshot" (title-cased vendor slug). Telegram sees the same with worse casing ("Openai / Xai / Zai") because Telegram uses `.title()` while web special-cases only `openai`.
- The `host` field exists on every `ModelEntry` but is invisible to the user on both surfaces.
- With today's catalog the host→vendors fan-out is:
  - `agent-sdk` → {anthropic} (1 vendor)
  - `google-ai` → {google} (1 vendor)
  - `xai` → {xai} (1 vendor)
  - `litellm` → {openai} (1 vendor)
  - `opencode-go` → {zai, moonshot} (2 vendors)
- So under "collapse single-vendor hosts", only `opencode-go` keeps the intermediate vendor screen today; everything else jumps straight from host to model list.

## Label Decisions

Host display labels (single source of truth):

| `Host` enum | Slug | Display |
|---|---|---|
| `agent_sdk` | `agent-sdk` | `Anthropic Agent SDK` |
| `google_ai` | `google-ai` | `Gemini API` |
| `litellm` | `litellm` | `LiteLLM` |
| `opencode_go` | `opencode-go` | `OpenCode Go` |
| `xai` | `xai` | `xAI` |

Vendor display labels:

| `Vendor` enum | Slug | Display |
|---|---|---|
| `anthropic` | `anthropic` | `Anthropic` |
| `google` | `google` | `Google` |
| `moonshot` | `moonshot` | `Moonshot` |
| `openai` | `openai` | `OpenAI` |
| `xai` | `xai` | `xAI` |
| `zai` | `zai` | `Z.AI` |

## File Structure

**New files:**

- `backend/app/providers/labels.py` — `HOST_LABELS: dict[Host, str]`, `VENDOR_LABELS: dict[Vendor, str]`, plus typed accessors that raise on unknown enum values. Single source of truth on the Python side.
- `backend/tests/test_provider_labels.py` — covers the accessor functions and asserts every `Host`/`Vendor` enum member has a label (so new enum members fail loudly).
- `frontend/features/chat/components/model-picker-labels.ts` — mirror of the same two maps on the TS side, with typed `hostLabel(slug)` / `vendorLabel(slug)` helpers that fall back to the raw slug on unknown input (the frontend already swallows unknown vendors safely in the picker).
- `frontend/features/chat/components/model-picker-labels.test.ts` — unit tests for the helpers.

**Modified files:**

- `backend/app/integrations/telegram/model_picker.py` — replaces vendor-keyed grouping with host-keyed grouping. New helpers `build_host_keyboard()`, `build_vendor_keyboard(host)`, and the new list-callback shape. `ModelCallback` grows a `host: str | None` field. The old `build_provider_keyboard`, `format_provider_picker_text`, `has_provider` names are kept as the entry-points but their bodies change to host-based logic.
- `backend/app/integrations/telegram/model_picker_runtime.py` — routes the new `mdl:v:<host>` action and threads the host through `_edit_model_list`.
- `backend/tests/test_telegram_model_picker.py` — replaces the two-screen assertions with three-screen assertions, adds a single-vendor-collapse case and a multi-vendor case.
- `frontend/features/chat/components/ModelSelectorPopover.tsx` — `groupModelsByVendor` becomes `groupModelsByHost` which returns `{ host, vendors: { vendor, entries }[] }[]`. The root rows become host rows. Each host row renders either a model submenu directly (single vendor) or a vendor submenu that itself contains model submenus (multi-vendor).
- `frontend/features/chat/components/ModelSelectorPopover.test.tsx` — extend the fixture to include two `opencode-go` vendors (z.ai + moonshot) so the multi-vendor branch is covered; rename the existing "Google" assertion to walk through "Gemini API → Gemini 3.1 Flash Lite".

**Not changed:**

- `backend/app/providers/catalog.py` — already has both `host` and `vendor` on every entry.
- `backend/app/providers/model_id.py` — `Host` and `Vendor` enums are reused as-is.
- `frontend/features/chat/hooks/use-chat-models.ts` — `host` and `vendor` already on `ChatModelOption`.
- `frontend/lib/react-chat-composer/src/model-selector/*` — the submodule's data helpers are not wired into the live composer picker. Leave them alone.
- `backend/app/api/models.py` — labels are mirrored on each side rather than wire-driven. Two maps × 6 entries do not need an API contract.

---

## Task 1: Backend label module (TDD)

**Files:**
- Create: `backend/app/providers/labels.py`
- Test: `backend/tests/test_provider_labels.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_provider_labels.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_provider_labels.py -v`
Expected: ImportError or ModuleNotFoundError on `app.core.providers.labels`.

- [ ] **Step 3: Write the module**

Create `backend/app/providers/labels.py`:

```python
"""Display labels for ``Host`` and ``Vendor`` enum members.

This is the single source of truth on the backend for how providers
(hosts) and vendors are rendered to users — Telegram inline buttons,
chat picker copy, and any future channel.  Adding a new ``Host`` or
``Vendor`` enum member without a corresponding label here causes
``tests/test_provider_labels.py`` to fail.
"""

from __future__ import annotations

from app.core.providers.model_id import Host, Vendor

HOST_LABELS: dict[Host, str] = {
    Host.agent_sdk: "Anthropic Agent SDK",
    Host.google_ai: "Gemini API",
    Host.litellm: "LiteLLM",
    Host.opencode_go: "OpenCode Go",
    Host.xai: "xAI",
}
"""Map from :class:`Host` enum to user-facing display string."""

VENDOR_LABELS: dict[Vendor, str] = {
    Vendor.anthropic: "Anthropic",
    Vendor.google: "Google",
    Vendor.moonshot: "Moonshot",
    Vendor.openai: "OpenAI",
    Vendor.xai: "xAI",
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

    Args:
        slug: The host's wire-form slug.

    Returns:
        The display label.

    Raises:
        KeyError: If ``slug`` is not a known :class:`Host` value.
    """
    return HOST_LABELS[Host(slug)]


def vendor_label_from_slug(slug: str) -> str:
    """Resolve a vendor wire-slug (e.g. ``"zai"``) to its label.

    Args:
        slug: The vendor's wire-form slug.

    Returns:
        The display label.

    Raises:
        KeyError: If ``slug`` is not a known :class:`Vendor` value.
    """
    return VENDOR_LABELS[Vendor(slug)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_provider_labels.py -v`
Expected: 6 tests pass.

- [ ] **Step 5: Run the project gates**

Run: `just check && python3 scripts/check-no-tools-in-providers.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/providers/labels.py backend/tests/test_provider_labels.py
git commit -m "feat(providers): add Host and Vendor display-label module"
```

---

## Task 2: Frontend label module (TDD)

**Files:**
- Create: `frontend/features/chat/components/model-picker-labels.ts`
- Test: `frontend/features/chat/components/model-picker-labels.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/features/chat/components/model-picker-labels.test.ts`:

```typescript
/**
 * Tests for the picker's host/vendor display-label helpers.
 */

import { describe, expect, it } from 'vitest';
import { hostLabel, vendorLabel } from './model-picker-labels';

describe('hostLabel', () => {
	it('returns the canonical label for known host slugs', () => {
		expect(hostLabel('agent-sdk')).toBe('Anthropic Agent SDK');
		expect(hostLabel('google-ai')).toBe('Gemini API');
		expect(hostLabel('litellm')).toBe('LiteLLM');
		expect(hostLabel('opencode-go')).toBe('OpenCode Go');
		expect(hostLabel('xai')).toBe('xAI');
	});

	it('returns the raw slug for unknown hosts (no crash)', () => {
		expect(hostLabel('totally-new-host')).toBe('totally-new-host');
	});
});

describe('vendorLabel', () => {
	it('returns the canonical label for known vendor slugs', () => {
		expect(vendorLabel('anthropic')).toBe('Anthropic');
		expect(vendorLabel('openai')).toBe('OpenAI');
		expect(vendorLabel('google')).toBe('Google');
		expect(vendorLabel('xai')).toBe('xAI');
		expect(vendorLabel('zai')).toBe('Z.AI');
		expect(vendorLabel('moonshot')).toBe('Moonshot');
	});

	it('returns the raw slug for unknown vendors (no crash)', () => {
		expect(vendorLabel('brand-new')).toBe('brand-new');
	});
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && bun run test -- features/chat/components/model-picker-labels.test.ts`
Expected: Module-not-found error.

- [ ] **Step 3: Write the module**

Create `frontend/features/chat/components/model-picker-labels.ts`:

```typescript
/**
 * Display labels for model-catalog `host` and `vendor` slugs.
 *
 * @fileoverview Mirrors the backend's `app.core.providers.labels`
 * module. Two small maps don't justify an API round-trip; if either
 * side adds a new entry, the new slug falls back to itself instead
 * of throwing so the picker keeps rendering.
 */

const HOST_LABELS: Readonly<Record<string, string>> = {
	'agent-sdk': 'Anthropic Agent SDK',
	'google-ai': 'Gemini API',
	litellm: 'LiteLLM',
	'opencode-go': 'OpenCode Go',
	xai: 'xAI',
};

const VENDOR_LABELS: Readonly<Record<string, string>> = {
	anthropic: 'Anthropic',
	google: 'Google',
	moonshot: 'Moonshot',
	openai: 'OpenAI',
	xai: 'xAI',
	zai: 'Z.AI',
};

/**
 * Return the display label for a host wire-slug.
 *
 * @param slug - The host's wire-form slug (e.g. `'agent-sdk'`).
 * @returns The display label, or the slug itself when unknown.
 */
export function hostLabel(slug: string): string {
	return HOST_LABELS[slug] ?? slug;
}

/**
 * Return the display label for a vendor wire-slug.
 *
 * @param slug - The vendor's wire-form slug (e.g. `'zai'`).
 * @returns The display label, or the slug itself when unknown.
 */
export function vendorLabel(slug: string): string {
	return VENDOR_LABELS[slug] ?? slug;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && bun run test -- features/chat/components/model-picker-labels.test.ts`
Expected: all tests pass.

- [ ] **Step 5: Run the project gates**

Run: `cd frontend && bun run check && bunx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/features/chat/components/model-picker-labels.ts frontend/features/chat/components/model-picker-labels.test.ts
git commit -m "feat(chat): add host/vendor display-label helpers"
```

---

## Task 3: Telegram picker — extend the callback model (TDD)

**Files:**
- Modify: `backend/app/integrations/telegram/model_picker.py`
- Test: `backend/tests/test_telegram_model_picker.py`

This task focuses *only* on the parse/serialize layer so the keyboard refactor in Task 4 can lean on a tested foundation.

- [ ] **Step 1: Add the failing callback tests**

Append to `backend/tests/test_telegram_model_picker.py`:

```python
from app.integrations.telegram.model_picker import (
    _list_callback,
    _vendor_callback,
)


def test_vendor_callback_serializes_with_host_slug() -> None:
    assert _vendor_callback("opencode-go") == "mdl:v:opencode-go"


def test_list_callback_serializes_with_host_and_vendor() -> None:
    assert _list_callback("opencode-go", "zai", 1) == "mdl:l:opencode-go:zai:1"


def test_parse_vendor_callback_round_trips_host() -> None:
    parsed = parse_model_callback_data("mdl:v:opencode-go")
    assert parsed is not None
    assert parsed.action == "vendors"
    assert parsed.host == "opencode-go"


def test_parse_list_callback_round_trips_host_and_vendor() -> None:
    parsed = parse_model_callback_data("mdl:l:opencode-go:zai:2")
    assert parsed is not None
    assert parsed.action == "list"
    assert parsed.host == "opencode-go"
    assert parsed.provider == "zai"
    assert parsed.page == 2


def test_parse_legacy_list_callback_without_host_returns_none() -> None:
    """Old keyboards from before the host segment was added must be treated as stale.

    Selection callbacks (``mdl:s:<token>:<index>``) still resolve correctly
    because the catalog-token guards them; list keyboards are cheap to
    re-open so we don't keep backwards-compat parsing for them.
    """
    assert parse_model_callback_data("mdl:l:anthropic:1") is None
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_telegram_model_picker.py -v -k 'vendor_callback or list_callback or round_trips or legacy'`
Expected: ImportError on `_vendor_callback`, plus assertion failures on the parse cases.

- [ ] **Step 3: Update `ModelCallback` and the parser**

In `backend/app/integrations/telegram/model_picker.py`, replace the `ModelCallback` dataclass and the parse helpers:

```python
_CALLBACK_LIST_PARTS = 5  # mdl:l:<host>:<vendor>:<page>
_CALLBACK_SELECT_PARTS = 4  # mdl:s:<token>:<index>
_CALLBACK_VENDOR_PARTS = 3  # mdl:v:<host>


@dataclass(frozen=True)
class ModelCallback:
    """Parsed Telegram callback payload for the model picker."""

    action: str
    host: str | None = None
    provider: str | None = None
    page: int = 1
    index: int | None = None
    catalog_token: str | None = None


def parse_model_callback_data(data: str | None) -> ModelCallback | None:
    """Parse Telegram callback data generated by this module.

    Returns ``None`` for unrecognised payloads (including pre-three-level
    list callbacks that did not carry a ``host`` segment — those keyboards
    are stale and the runtime treats them the same as any other stale
    payload).
    """
    if data == _providers_callback() or data == "mdl:b":
        return ModelCallback(action="providers")
    if data is None or not data.startswith(MODEL_CALLBACK_PREFIX):
        return None

    parts = data.split(":")
    if len(parts) == _CALLBACK_VENDOR_PARTS and parts[1] == "v":
        return ModelCallback(action="vendors", host=parts[2])
    if len(parts) == _CALLBACK_LIST_PARTS and parts[1] == "l":
        return _parse_list_callback(parts)
    if len(parts) == _CALLBACK_SELECT_PARTS and parts[1] == "s":
        return _parse_select_callback(parts)
    return None


def _vendor_callback(host: str) -> str:
    return f"mdl:v:{host}"


def _list_callback(host: str, vendor: str, page: int) -> str:
    return f"mdl:l:{host}:{vendor}:{page}"


def _parse_list_callback(parts: list[str]) -> ModelCallback | None:
    try:
        page = int(parts[4])
    except ValueError:
        return None
    if page < 1:
        return None
    return ModelCallback(action="list", host=parts[2], provider=parts[3], page=page)
```

Also remove the old single-arg `_list_callback(provider, page)` signature — Task 4 will rewire callers.

- [ ] **Step 4: Run the parse tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_telegram_model_picker.py -v -k 'vendor_callback or list_callback or round_trips or legacy'`
Expected: 5 new tests pass. Some pre-existing tests in this file will still fail because they call `build_provider_keyboard` / `build_models_keyboard` whose internals are about to change — that's Task 4.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/telegram/model_picker.py backend/tests/test_telegram_model_picker.py
git commit -m "refactor(telegram): extend model-picker callback schema with host segment"
```

---

## Task 4: Telegram picker — keyboard builders (TDD)

**Files:**
- Modify: `backend/app/integrations/telegram/model_picker.py`
- Test: `backend/tests/test_telegram_model_picker.py`

- [ ] **Step 1: Rewrite the existing keyboard tests + add the three-level cases**

Replace the body of `backend/tests/test_telegram_model_picker.py` with:

```python
"""Tests for Telegram's catalog-backed inline model picker."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.providers.catalog import MODEL_CATALOG, default_model
from app.core.providers.model_id import Host
from app.integrations.telegram.handlers import TelegramSender
from app.integrations.telegram.model_picker import (
    ModelCallback,
    build_host_keyboard,
    build_models_keyboard,
    build_vendor_keyboard,
    format_host_picker_text,
    format_models_picker_text,
    format_vendor_picker_text,
    get_model_picker_state,
    has_host,
    has_vendor_in_host,
    parse_model_callback_data,
    resolve_model_selection,
)


def _flatten(rows: list[list[object]]) -> list[object]:
    return [button for row in rows for button in row]


def test_host_keyboard_lists_all_hosts_with_friendly_labels() -> None:
    buttons = _flatten(build_host_keyboard())
    labels = [button.text for button in buttons]

    assert "Anthropic Agent SDK (3)" in labels
    assert "Gemini API (2)" in labels
    assert "xAI (1)" in labels
    assert "LiteLLM (5)" in labels
    assert "OpenCode Go (2)" in labels
    # Title-casing bug from before: must not contain the broken labels.
    assert "Openai (5)" not in labels
    assert "Xai (1)" not in labels
    assert "Zai (1)" not in labels
    assert all(len(button.callback_data.encode("utf-8")) <= 64 for button in buttons)


def test_host_button_for_single_vendor_jumps_to_model_list() -> None:
    """Hosts with exactly one vendor must skip the vendor screen."""
    button = next(b for b in _flatten(build_host_keyboard()) if b.text.startswith("Anthropic Agent SDK"))
    parsed = parse_model_callback_data(button.callback_data)

    assert parsed is not None
    assert parsed.action == "list"
    assert parsed.host == Host.agent_sdk.value
    assert parsed.provider == "anthropic"
    assert parsed.page == 1


def test_host_button_for_multi_vendor_opens_vendor_screen() -> None:
    """Hosts with multiple vendors must open the vendor screen."""
    button = next(b for b in _flatten(build_host_keyboard()) if b.text.startswith("OpenCode Go"))
    parsed = parse_model_callback_data(button.callback_data)

    assert parsed is not None
    assert parsed.action == "vendors"
    assert parsed.host == Host.opencode_go.value


def test_vendor_keyboard_lists_vendors_for_a_host() -> None:
    rows = build_vendor_keyboard(host=Host.opencode_go.value)
    labels = [b.text for b in _flatten(rows)]

    assert "Z.AI (1)" in labels
    assert "Moonshot (1)" in labels


def test_vendor_keyboard_back_button_returns_to_host_screen() -> None:
    rows = build_vendor_keyboard(host=Host.opencode_go.value)
    back_button = rows[-1][0]

    assert back_button.text == "Back to providers"
    parsed = parse_model_callback_data(back_button.callback_data)
    assert parsed is not None
    assert parsed.action == "providers"


def test_model_keyboard_marks_current_and_resolves_selection() -> None:
    current = default_model()
    rows = build_models_keyboard(
        host=current.host.value,
        vendor=current.vendor.value,
        page=1,
        current_model_id=current.id,
    )
    buttons = _flatten(rows)
    current_button = next(b for b in buttons if current.display_name in b.text)

    assert current_button.text.startswith("Selected: ")
    parsed = parse_model_callback_data(current_button.callback_data)
    assert parsed is not None
    assert resolve_model_selection(parsed) == current


def test_model_keyboard_back_button_for_multi_vendor_goes_to_vendor_screen() -> None:
    """OpenCode Go has multiple vendors — back must land on the vendor screen."""
    rows = build_models_keyboard(
        host=Host.opencode_go.value,
        vendor="zai",
        page=1,
        current_model_id="",
    )
    back_button = rows[-1][0]

    assert back_button.text == "Back to vendors"
    parsed = parse_model_callback_data(back_button.callback_data)
    assert parsed is not None
    assert parsed.action == "vendors"
    assert parsed.host == Host.opencode_go.value


def test_model_keyboard_back_button_for_single_vendor_goes_to_host_screen() -> None:
    """Anthropic Agent SDK has one vendor — back skips the vendor screen."""
    rows = build_models_keyboard(
        host=Host.agent_sdk.value,
        vendor="anthropic",
        page=1,
        current_model_id="",
    )
    back_button = rows[-1][0]

    assert back_button.text == "Back to providers"
    parsed = parse_model_callback_data(back_button.callback_data)
    assert parsed is not None
    assert parsed.action == "providers"


def test_stale_model_selection_is_rejected() -> None:
    stale = ModelCallback(action="select", index=0, catalog_token="deadbeef")
    assert resolve_model_selection(stale) is None


def test_has_host_and_has_vendor_in_host_guards() -> None:
    assert has_host(Host.agent_sdk.value) is True
    assert has_host("totally-fake") is False
    assert has_vendor_in_host(host=Host.opencode_go.value, vendor="zai") is True
    assert has_vendor_in_host(host=Host.opencode_go.value, vendor="anthropic") is False


def test_host_picker_text_displays_known_model_name() -> None:
    text = format_host_picker_text(default_model().id)
    assert default_model().display_name in text
    assert default_model().id not in text


def test_vendor_picker_text_includes_host_label() -> None:
    text = format_vendor_picker_text(host=Host.opencode_go.value)
    assert "OpenCode Go" in text


def test_models_picker_text_includes_host_and_vendor_labels() -> None:
    text = format_models_picker_text(
        host=Host.opencode_go.value,
        vendor="zai",
        page=1,
    )
    assert "OpenCode Go" in text
    assert "Z.AI" in text


@pytest.mark.anyio
async def test_get_model_picker_state_returns_none_for_unbound_sender() -> None:
    sender = TelegramSender(user_id=1, chat_id=1, username=None, full_name=None)

    with patch(
        "app.integrations.telegram.model_picker.get_user_id_for_external",
        new=AsyncMock(return_value=None),
    ):
        state = await get_model_picker_state(sender=sender, session=AsyncMock())

    assert state is None


@pytest.mark.anyio
async def test_get_model_picker_state_reads_conversation_override() -> None:
    sender = TelegramSender(user_id=2, chat_id=2, username=None, full_name=None, thread_id=9)
    override = MODEL_CATALOG[0].id
    conversation = SimpleNamespace(model_id=override)

    with (
        patch(
            "app.integrations.telegram.model_picker.get_user_id_for_external",
            new=AsyncMock(return_value=uuid.uuid4()),
        ),
        patch(
            "app.integrations.telegram.model_picker.get_or_create_telegram_conversation_full",
            new=AsyncMock(return_value=conversation),
        ),
    ):
        state = await get_model_picker_state(sender=sender, session=AsyncMock())

    assert state is not None
    assert state.current_model_id == override
```

- [ ] **Step 2: Run the rewritten test file to verify the new behaviour fails**

Run: `cd backend && uv run pytest tests/test_telegram_model_picker.py -v`
Expected: ImportError on the new `build_host_keyboard` / `build_vendor_keyboard` / `format_host_picker_text` / `format_vendor_picker_text` / `has_host` / `has_vendor_in_host` names.

- [ ] **Step 3: Rewrite the picker module**

Replace `backend/app/integrations/telegram/model_picker.py` with the three-level implementation. Full file:

```python
"""Catalog-backed Telegram model picker helpers.

The picker is a three-level walk: provider (host) → vendor → models.
Hosts that serve a single vendor collapse to two levels (host → models),
because forcing a single-button vendor screen is just an extra tap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from html import escape
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.providers.catalog import CATALOG_ETAG, MODEL_CATALOG, ModelEntry, default_model
from app.core.providers.labels import HOST_LABELS, host_label_from_slug, vendor_label_from_slug
from app.core.providers.model_id import Host, Vendor
from app.crud.channel import get_or_create_telegram_conversation_full, get_user_id_for_external

PROVIDER = "telegram"
MODEL_CALLBACK_PREFIX = "mdl:"
_CATALOG_TOKEN = CATALOG_ETAG[:8]
_MODEL_PAGE_SIZE = 8
_HOST_BUTTONS_PER_ROW = 2
_VENDOR_BUTTONS_PER_ROW = 2
_CALLBACK_VENDOR_PARTS = 3  # mdl:v:<host>
_CALLBACK_LIST_PARTS = 5    # mdl:l:<host>:<vendor>:<page>
_CALLBACK_SELECT_PARTS = 4  # mdl:s:<token>:<index>

_PICKER_NOT_BOUND_MESSAGE = "Connect your account first before changing models."
_PICKER_STALE_MESSAGE = "That model picker is out of date. Open /models again."


class TelegramSenderLike(Protocol):
    """Subset of ``TelegramSender`` used by picker state resolution."""

    user_id: int
    thread_id: int | None


@dataclass(frozen=True)
class ModelButton:
    """One Telegram inline keyboard button."""

    text: str
    callback_data: str


@dataclass(frozen=True)
class ModelPickerState:
    """Current catalog state for one Telegram conversation."""

    current_model_id: str


@dataclass(frozen=True)
class ModelCallback:
    """Parsed Telegram callback payload for the model picker."""

    action: str
    host: str | None = None
    provider: str | None = None  # vendor slug; name kept for runtime compatibility
    page: int = 1
    index: int | None = None
    catalog_token: str | None = None


async def get_model_picker_state(
    *,
    sender: TelegramSenderLike,
    session: AsyncSession,
) -> ModelPickerState | None:
    """Resolve the current model for a Telegram sender.

    Returns ``None`` when the Telegram sender is not bound to a user.
    """
    nexus_user_id = await get_user_id_for_external(
        provider=PROVIDER,
        external_user_id=str(sender.user_id),
        session=session,
    )
    if nexus_user_id is None:
        return None

    conversation = await get_or_create_telegram_conversation_full(
        user_id=nexus_user_id,
        session=session,
        thread_id=sender.thread_id,
    )
    return ModelPickerState(current_model_id=conversation.model_id or default_model().id)


def build_host_keyboard() -> list[list[ModelButton]]:
    """Build a two-column host picker from the catalog."""
    rows: list[list[ModelButton]] = []
    current_row: list[ModelButton] = []
    for host, vendors in _host_to_vendors().items():
        total = sum(len(entries) for entries in vendors.values())
        current_row.append(
            ModelButton(
                text=f"{host_label_from_slug(host)} ({total})",
                callback_data=_host_button_callback(host=host, vendors=vendors),
            )
        )
        if len(current_row) == _HOST_BUTTONS_PER_ROW:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    return rows


def build_vendor_keyboard(*, host: str) -> list[list[ModelButton]]:
    """Build the vendor keyboard for a host that has multiple vendors.

    For single-vendor hosts the caller should jump straight to
    :func:`build_models_keyboard`; this function still works in that
    case but produces a one-button screen.
    """
    vendors = _host_to_vendors().get(host, {})
    rows: list[list[ModelButton]] = []
    current_row: list[ModelButton] = []
    for vendor, entries in vendors.items():
        current_row.append(
            ModelButton(
                text=f"{vendor_label_from_slug(vendor)} ({len(entries)})",
                callback_data=_list_callback(host=host, vendor=vendor, page=1),
            )
        )
        if len(current_row) == _VENDOR_BUTTONS_PER_ROW:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([ModelButton(text="Back to providers", callback_data=_providers_callback())])
    return rows


def build_models_keyboard(
    *,
    host: str,
    vendor: str,
    page: int,
    current_model_id: str,
) -> list[list[ModelButton]]:
    """Build a paginated model keyboard for one host+vendor pair.

    The trailing "Back to ..." row collapses to "Back to providers" when
    the host has a single vendor, since the vendor screen was skipped on
    the way in.
    """
    vendors = _host_to_vendors().get(host, {})
    entries = vendors.get(vendor, [])
    page_count = _page_count(entries)
    page = _clamped_page(page, page_count)
    page_entries = _page_entries(entries, page)

    rows: list[list[ModelButton]] = [
        [
            ModelButton(
                text=_model_label(entry, current_model_id),
                callback_data=_select_callback(_catalog_index(entry)),
            )
        ]
        for entry in page_entries
    ]
    rows.extend(_pagination_rows(host=host, vendor=vendor, page=page, page_count=page_count))
    if len(vendors) > 1:
        rows.append(
            [ModelButton(text="Back to vendors", callback_data=_vendor_callback(host))]
        )
    else:
        rows.append(
            [ModelButton(text="Back to providers", callback_data=_providers_callback())]
        )
    return rows


def has_host(host: str) -> bool:
    """Return whether the catalog has at least one model for ``host``."""
    return host in _host_to_vendors()


def has_vendor_in_host(*, host: str, vendor: str) -> bool:
    """Return whether ``vendor`` has at least one model under ``host``."""
    return vendor in _host_to_vendors().get(host, {})


def format_host_picker_text(current_model_id: str) -> str:
    """Render the host picker message in Telegram HTML."""
    current = _display_name_for_model(current_model_id)
    return f"Choose a provider for this Telegram conversation.\n\nCurrent: <b>{escape(current)}</b>"


def format_vendor_picker_text(*, host: str) -> str:
    """Render the vendor screen header in Telegram HTML."""
    return f"Select a vendor for <b>{escape(host_label_from_slug(host))}</b>."


def format_models_picker_text(*, host: str, vendor: str, page: int) -> str:
    """Render the model page header in Telegram HTML."""
    entries = _host_to_vendors().get(host, {}).get(vendor, [])
    page_count = _page_count(entries)
    page = _clamped_page(page, page_count)
    return (
        f"Select a {escape(vendor_label_from_slug(vendor))} model "
        f"on <b>{escape(host_label_from_slug(host))}</b>.\nPage {page}/{page_count}"
    )


def parse_model_callback_data(data: str | None) -> ModelCallback | None:
    """Parse Telegram callback data generated by this module."""
    if data == _providers_callback() or data == "mdl:b":
        return ModelCallback(action="providers")
    if data is None or not data.startswith(MODEL_CALLBACK_PREFIX):
        return None

    parts = data.split(":")
    if len(parts) == _CALLBACK_VENDOR_PARTS and parts[1] == "v":
        return ModelCallback(action="vendors", host=parts[2])
    if len(parts) == _CALLBACK_LIST_PARTS and parts[1] == "l":
        return _parse_list_callback(parts)
    if len(parts) == _CALLBACK_SELECT_PARTS and parts[1] == "s":
        return _parse_select_callback(parts)
    return None


def resolve_model_selection(callback: ModelCallback) -> ModelEntry | None:
    """Resolve a parsed selection callback to a catalog entry."""
    if callback.action != "select" or callback.catalog_token != _CATALOG_TOKEN:
        return None
    if callback.index is None or callback.index < 0:
        return None
    if callback.index >= len(MODEL_CATALOG):
        return None
    return MODEL_CATALOG[callback.index]


def picker_not_bound_message() -> str:
    return _PICKER_NOT_BOUND_MESSAGE


def picker_stale_message() -> str:
    return _PICKER_STALE_MESSAGE


def _host_to_vendors() -> dict[str, dict[str, list[ModelEntry]]]:
    """Group the catalog as ``{host_slug: {vendor_slug: [entries]}}``.

    Both layers preserve a stable, alphabetised order so the keyboards
    are deterministic.
    """
    grouped: dict[str, dict[str, list[ModelEntry]]] = {}
    for entry in MODEL_CATALOG:
        host_bucket = grouped.setdefault(entry.host.value, {})
        host_bucket.setdefault(entry.vendor.value, []).append(entry)
    return {
        host: dict(sorted(vendors.items()))
        for host, vendors in sorted(grouped.items())
    }


def _host_button_callback(*, host: str, vendors: dict[str, list[ModelEntry]]) -> str:
    """Callback for a host button — collapses single-vendor hosts to the model list."""
    if len(vendors) == 1:
        only_vendor = next(iter(vendors))
        return _list_callback(host=host, vendor=only_vendor, page=1)
    return _vendor_callback(host)


def _model_label(entry: ModelEntry, current_model_id: str) -> str:
    prefix = "Selected: " if entry.id == current_model_id else ""
    return f"{prefix}{entry.display_name}"


def _display_name_for_model(model_id: str) -> str:
    for entry in MODEL_CATALOG:
        if entry.id == model_id:
            return entry.display_name
    return model_id


def _catalog_index(entry: ModelEntry) -> int:
    return MODEL_CATALOG.index(entry)


def _providers_callback() -> str:
    return "mdl:p"


def _vendor_callback(host: str) -> str:
    return f"mdl:v:{host}"


def _list_callback(*, host: str, vendor: str, page: int) -> str:
    return f"mdl:l:{host}:{vendor}:{page}"


def _select_callback(index: int) -> str:
    return f"mdl:s:{_CATALOG_TOKEN}:{index}"


def _parse_list_callback(parts: list[str]) -> ModelCallback | None:
    try:
        page = int(parts[4])
    except ValueError:
        return None
    if page < 1:
        return None
    return ModelCallback(
        action="list",
        host=parts[2],
        provider=parts[3],
        page=page,
    )


def _parse_select_callback(parts: list[str]) -> ModelCallback | None:
    try:
        index = int(parts[3])
    except ValueError:
        return None
    return ModelCallback(
        action="select",
        index=index,
        catalog_token=parts[2],
    )


def _page_count(entries: list[ModelEntry]) -> int:
    return max(1, math.ceil(len(entries) / _MODEL_PAGE_SIZE))


def _clamped_page(page: int, page_count: int) -> int:
    return min(max(page, 1), page_count)


def _page_entries(entries: list[ModelEntry], page: int) -> list[ModelEntry]:
    start = (page - 1) * _MODEL_PAGE_SIZE
    return entries[start : start + _MODEL_PAGE_SIZE]


def _pagination_rows(
    *,
    host: str,
    vendor: str,
    page: int,
    page_count: int,
) -> list[list[ModelButton]]:
    if page_count <= 1:
        return []
    row = [
        ModelButton(
            text="< Prev",
            callback_data=_list_callback(host=host, vendor=vendor, page=page - 1),
        ),
        ModelButton(
            text=f"{page}/{page_count}",
            callback_data=_list_callback(host=host, vendor=vendor, page=page),
        ),
        ModelButton(
            text="Next >",
            callback_data=_list_callback(host=host, vendor=vendor, page=page + 1),
        ),
    ]
    return [row]


__all__ = [
    "MODEL_CALLBACK_PREFIX",
    "ModelButton",
    "ModelCallback",
    "ModelPickerState",
    "build_host_keyboard",
    "build_models_keyboard",
    "build_vendor_keyboard",
    "format_host_picker_text",
    "format_models_picker_text",
    "format_vendor_picker_text",
    "get_model_picker_state",
    "has_host",
    "has_vendor_in_host",
    "parse_model_callback_data",
    "picker_not_bound_message",
    "picker_stale_message",
    "resolve_model_selection",
]
```

Note: the `Host` / `Vendor` imports are kept even though they're only used by tests' callers — the lint may complain. If it does, drop them from this file (`labels` does the conversion) and keep the imports in the test file only.

- [ ] **Step 4: Run the model_picker tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_telegram_model_picker.py -v`
Expected: every test passes.

- [ ] **Step 5: Run the full backend test suite to catch fallout**

Run: `cd backend && uv run pytest -x`
Expected: all green. The runtime test file imports old symbols (`build_provider_keyboard`, `has_provider`, `format_provider_picker_text`) which no longer exist — those will fail. Move on to Task 5 to fix them before re-running.

- [ ] **Step 6: Commit**

```bash
git add backend/app/integrations/telegram/model_picker.py backend/tests/test_telegram_model_picker.py
git commit -m "feat(telegram): three-level model picker (host -> vendor -> models)"
```

---

## Task 5: Telegram picker runtime — wire to the new actions

**Files:**
- Modify: `backend/app/integrations/telegram/model_picker_runtime.py`

- [ ] **Step 1: Update the runtime imports and handler logic**

Replace `backend/app/integrations/telegram/model_picker_runtime.py` with:

```python
"""aiogram runtime glue for the Telegram model picker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db import async_session_maker
from app.integrations.telegram.handlers import TelegramSender, handle_model_command
from app.integrations.telegram.model_picker import (
    ModelButton,
    ModelCallback,
    build_host_keyboard,
    build_models_keyboard,
    build_vendor_keyboard,
    format_host_picker_text,
    format_models_picker_text,
    format_vendor_picker_text,
    get_model_picker_state,
    has_host,
    has_vendor_in_host,
    parse_model_callback_data,
    picker_not_bound_message,
    picker_stale_message,
    resolve_model_selection,
)

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message


async def answer_model_command(*, message: Message, model_arg: str) -> None:
    """Answer ``/model`` with either the picker or typed-model update."""
    if _opens_picker(model_arg):
        await answer_model_picker(message=message)
        return

    sender = _sender_from_message(message)
    async with async_session_maker() as session:
        reply = await handle_model_command(sender=sender, model_arg=model_arg, session=session)
    await message.answer(reply, reply_parameters=_reply_parameters(message.message_id))


async def answer_model_picker(*, message: Message) -> None:
    """Open the host picker for ``/models`` or empty ``/model``."""
    sender = _sender_from_message(message)
    async with async_session_maker() as session:
        state = await get_model_picker_state(sender=sender, session=session)

    if state is None:
        await message.answer(
            picker_not_bound_message(),
            reply_parameters=_reply_parameters(message.message_id),
        )
        return

    await message.answer(
        format_host_picker_text(state.current_model_id),
        reply_markup=_inline_keyboard(build_host_keyboard()),
        reply_parameters=_reply_parameters(message.message_id),
    )


async def handle_model_picker_callback(*, callback: CallbackQuery) -> None:
    """Handle inline keyboard callbacks produced by the model picker."""
    parsed = parse_model_callback_data(callback.data)
    if parsed is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    if parsed.action == "select":
        await _handle_model_select(callback=callback, parsed=parsed)
        return

    sender = _sender_from_callback(callback)
    async with async_session_maker() as session:
        state = await get_model_picker_state(sender=sender, session=session)
    if state is None:
        await callback.answer(picker_not_bound_message(), show_alert=True)
        return

    if parsed.action == "vendors" and parsed.host is not None:
        await _edit_vendor_list(callback=callback, parsed=parsed)
        return
    if parsed.action == "list" and parsed.host is not None and parsed.provider is not None:
        await _edit_model_list(
            callback=callback, parsed=parsed, current_model_id=state.current_model_id
        )
        return

    await _edit_host_list(callback=callback, current_model_id=state.current_model_id)


def _opens_picker(model_arg: str) -> bool:
    return model_arg.strip().lower() in {"", "list"}


async def _handle_model_select(*, callback: CallbackQuery, parsed: ModelCallback) -> None:
    entry = resolve_model_selection(parsed)
    if entry is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    sender = _sender_from_callback(callback)
    async with async_session_maker() as session:
        reply = await handle_model_command(sender=sender, model_arg=entry.id, session=session)
    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return
    await message.edit_text(reply)
    await callback.answer(f"Model set: {entry.short_name}")


async def _edit_vendor_list(*, callback: CallbackQuery, parsed: ModelCallback) -> None:
    if parsed.host is None or not has_host(parsed.host):
        await callback.answer(picker_stale_message(), show_alert=True)
        return
    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return
    await message.edit_text(
        format_vendor_picker_text(host=parsed.host),
        reply_markup=_inline_keyboard(build_vendor_keyboard(host=parsed.host)),
    )
    await callback.answer()


async def _edit_model_list(
    *,
    callback: CallbackQuery,
    parsed: ModelCallback,
    current_model_id: str,
) -> None:
    if (
        parsed.host is None
        or parsed.provider is None
        or not has_vendor_in_host(host=parsed.host, vendor=parsed.provider)
    ):
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return

    await message.edit_text(
        format_models_picker_text(host=parsed.host, vendor=parsed.provider, page=parsed.page),
        reply_markup=_inline_keyboard(
            build_models_keyboard(
                host=parsed.host,
                vendor=parsed.provider,
                page=parsed.page,
                current_model_id=current_model_id,
            )
        ),
    )
    await callback.answer()


async def _edit_host_list(*, callback: CallbackQuery, current_model_id: str) -> None:
    message = _callback_message(callback)
    if message is None:
        await callback.answer(picker_stale_message(), show_alert=True)
        return
    await message.edit_text(
        format_host_picker_text(current_model_id),
        reply_markup=_inline_keyboard(build_host_keyboard()),
    )
    await callback.answer()


def _inline_keyboard(rows: list[list[ModelButton]]) -> object:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup  # noqa: PLC0415

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=button.text, callback_data=button.callback_data)
                for button in row
            ]
            for row in rows
        ]
    )


def _sender_from_message(message: Message) -> TelegramSender:
    user = message.from_user
    if user is None:
        raise RuntimeError("Telegram message has no from_user; refusing to dispatch.")
    return TelegramSender(
        user_id=user.id,
        chat_id=message.chat.id,
        username=user.username,
        full_name=user.full_name,
        thread_id=message.message_thread_id,
    )


def _sender_from_callback(callback: CallbackQuery) -> TelegramSender:
    message = _callback_message(callback)
    if message is None:
        raise RuntimeError("Telegram callback has no accessible message.")
    user = callback.from_user
    return TelegramSender(
        user_id=user.id,
        chat_id=message.chat.id,
        username=user.username,
        full_name=user.full_name,
        thread_id=message.message_thread_id,
    )


def _callback_message(callback: CallbackQuery) -> Message | None:
    message = callback.message
    if message is None or not hasattr(message, "edit_text"):
        return None
    return message


def _reply_parameters(message_id: int) -> object:
    from aiogram.types import ReplyParameters  # noqa: PLC0415

    return ReplyParameters(message_id=message_id)
```

- [ ] **Step 2: Run the full backend suite to confirm nothing else used the old API**

Run: `cd backend && uv run pytest -x`
Expected: green. If any test still imports `build_provider_keyboard`, `format_provider_picker_text`, or `has_provider`, update it to use the new names (`build_host_keyboard` / `format_host_picker_text` / `has_host`).

- [ ] **Step 3: Run the project gates**

Run: `just check && python3 scripts/check-no-tools-in-providers.py && python3 scripts/check-nesting.py`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add backend/app/integrations/telegram/model_picker_runtime.py
git commit -m "refactor(telegram): route host/vendor/list callbacks through new picker API"
```

---

## Task 6: Frontend picker — three-level submenu (TDD)

**Files:**
- Modify: `frontend/features/chat/components/ModelSelectorPopover.tsx`
- Test: `frontend/features/chat/components/ModelSelectorPopover.test.tsx`

- [ ] **Step 1: Extend the test fixture and add three-level cases**

Replace the `FIXTURE_MODELS` constant in `frontend/features/chat/components/ModelSelectorPopover.test.tsx` and add two new test cases. The full new fixture + tests:

```typescript
/**
 * Fixture catalog passed via the `models` prop. Now exercises the
 * three-level walk: most hosts have a single vendor (collapsed path)
 * and OpenCode Go carries two vendors (uncollapsed path).
 */
const FIXTURE_MODELS: ChatModelOption[] = [
	{
		id: 'agent-sdk:anthropic/claude-sonnet-4-6',
		host: 'agent-sdk',
		vendor: 'anthropic',
		model: 'claude-sonnet-4-6',
		display_name: 'Claude Sonnet 4.6',
		short_name: 'Claude Sonnet 4.6',
		description: 'Balanced for everyday tasks',
		is_default: false,
	},
	{
		id: 'agent-sdk:anthropic/claude-opus-4-7',
		host: 'agent-sdk',
		vendor: 'anthropic',
		model: 'claude-opus-4-7',
		display_name: 'Claude Opus 4.7',
		short_name: 'Claude Opus 4.7',
		description: 'Most capable for ambitious work',
		is_default: false,
	},
	{
		id: 'google-ai:google/gemini-3-flash-preview',
		host: 'google-ai',
		vendor: 'google',
		model: 'gemini-3-flash-preview',
		display_name: 'Gemini 3 Flash Preview',
		short_name: 'Gemini 3 Flash',
		description: "Google's frontier multimodal",
		is_default: true,
	},
	{
		id: 'google-ai:google/gemini-3.1-flash-lite-preview',
		host: 'google-ai',
		vendor: 'google',
		model: 'gemini-3.1-flash-lite-preview',
		display_name: 'Gemini 3.1 Flash Lite Preview',
		short_name: 'Gemini 3.1 Flash Lite',
		description: "Google's fast preview model",
		is_default: false,
	},
	{
		id: 'opencode-go:zai/glm-5.1',
		host: 'opencode-go',
		vendor: 'zai',
		model: 'glm-5.1',
		display_name: 'GLM-5.1',
		short_name: 'GLM-5.1',
		description: 'Open coding model via OpenCode Go',
		is_default: false,
	},
	{
		id: 'opencode-go:moonshot/kimi-k2.6',
		host: 'opencode-go',
		vendor: 'moonshot',
		model: 'kimi-k2.6',
		display_name: 'Kimi K2.6',
		short_name: 'Kimi K2.6',
		description: 'Long-context coding model via OpenCode Go',
		is_default: false,
	},
];
```

Add the following tests inside the existing `describe('ModelSelectorPopover', ...)` block:

```typescript
it('renders host rows at the root level with friendly labels', () => {
	render(<ModelSelectorPopover {...DEFAULT_PROPS} />);
	fireEvent.click(screen.getByRole('button', { name: /select model/i }));

	expect(screen.getByText('Anthropic Agent SDK')).toBeTruthy();
	expect(screen.getByText('Gemini API')).toBeTruthy();
	expect(screen.getByText('OpenCode Go')).toBeTruthy();
});

it('collapses single-vendor hosts straight to the model list', () => {
	vi.useFakeTimers();
	const onSelectModel = vi.fn();
	render(<ModelSelectorPopover {...DEFAULT_PROPS} onSelectModel={onSelectModel} />);

	fireEvent.click(screen.getByRole('button', { name: /select model/i }));
	const geminiHost = closestButton(screen.getByText('Gemini API'));
	fireEvent.pointerEnter(geminiHost);
	act(() => {
		vi.advanceTimersByTime(120);
	});

	// Gemini API has one vendor (Google), so the model list appears
	// directly without an intermediate "Google" submenu trigger.
	const dottedGeminiRow = closestButton(screen.getByText('Gemini 3.1 Flash Lite'));
	fireEvent.pointerDown(dottedGeminiRow, { button: 0 });
	fireEvent.click(dottedGeminiRow);

	expect(onSelectModel).toHaveBeenCalledTimes(1);
	expect(onSelectModel).toHaveBeenCalledWith(
		'google-ai:google/gemini-3.1-flash-lite-preview'
	);
});

it('shows a vendor submenu for multi-vendor hosts (OpenCode Go)', () => {
	vi.useFakeTimers();
	const onSelectModel = vi.fn();
	render(<ModelSelectorPopover {...DEFAULT_PROPS} onSelectModel={onSelectModel} />);

	fireEvent.click(screen.getByRole('button', { name: /select model/i }));
	const opencodeHost = closestButton(screen.getByText('OpenCode Go'));
	fireEvent.pointerEnter(opencodeHost);
	act(() => {
		vi.advanceTimersByTime(120);
	});

	// Vendor screen: Z.AI and Moonshot both render here.
	expect(screen.getByText('Z.AI')).toBeTruthy();
	const zaiVendor = closestButton(screen.getByText('Z.AI'));
	fireEvent.pointerEnter(zaiVendor);
	act(() => {
		vi.advanceTimersByTime(120);
	});

	const glmRow = closestButton(screen.getByText('GLM-5.1'));
	fireEvent.pointerDown(glmRow, { button: 0 });
	fireEvent.click(glmRow);

	expect(onSelectModel).toHaveBeenCalledTimes(1);
	expect(onSelectModel).toHaveBeenCalledWith('opencode-go:zai/glm-5.1');
});
```

Also remove the old "selects a dotted Gemini model from the vendor submenu on pointer-down" test (it expected a top-level "Google" submenu row; the new behaviour is host → models directly).

- [ ] **Step 2: Run the test file to verify the new cases fail**

Run: `cd frontend && bun run test -- features/chat/components/ModelSelectorPopover.test.tsx`
Expected: the new tests fail because the component still groups by vendor at the root.

- [ ] **Step 3: Update the component**

In `frontend/features/chat/components/ModelSelectorPopover.tsx`:

1. Replace the top-of-file `vendorLabel` helper with imports from the new labels module:

```typescript
import { hostLabel, vendorLabel } from './model-picker-labels';
```

   Delete the inline `vendorLabel` function (lines 41-47) — it's now imported.

2. Replace `RootRow`, `rootRowKey`, and `groupModelsByVendor` with host-based grouping:

```typescript
/** One vendor bucket inside a host group. */
interface VendorGroup {
	/** Vendor wire slug. */
	vendor: string;
	/** Models authored by this vendor, in catalog order. */
	entries: readonly ChatModelOption[];
}

/** One host group: a provider + the vendors it serves. */
interface HostGroup {
	/** Host wire slug. */
	host: string;
	/** Vendors served by this host, in catalog order. */
	vendors: readonly VendorGroup[];
}

/** Discriminated union of root-menu rows. */
type RootRow = { kind: 'host'; host: string } | { kind: 'thinking' };

/** Stable React key for each root row. */
function rootRowKey(row: RootRow): string {
	return row.kind === 'host' ? `host:${row.host}` : 'thinking';
}

/** Models grouped by host, then by vendor inside each host. */
function groupModelsByHost(models: readonly ChatModelOption[]): readonly HostGroup[] {
	const hostOrder: string[] = [];
	const hostBuckets = new Map<string, { vendorOrder: string[]; byVendor: Map<string, ChatModelOption[]> }>();

	for (const model of models) {
		if (typeof model.host !== 'string' || model.host.length === 0) continue;
		if (typeof model.vendor !== 'string' || model.vendor.length === 0) continue;

		let host = hostBuckets.get(model.host);
		if (!host) {
			host = { vendorOrder: [], byVendor: new Map() };
			hostBuckets.set(model.host, host);
			hostOrder.push(model.host);
		}
		let vendor = host.byVendor.get(model.vendor);
		if (!vendor) {
			vendor = [];
			host.byVendor.set(model.vendor, vendor);
			host.vendorOrder.push(model.vendor);
		}
		vendor.push(model);
	}

	return hostOrder.map((host) => {
		const bucket = hostBuckets.get(host)!;
		return {
			host,
			vendors: bucket.vendorOrder.map((vendor) => ({
				vendor,
				entries: bucket.byVendor.get(vendor) ?? [],
			})),
		};
	});
}
```

3. Replace the body of `ModelSelectorPopover` (specifically the `groupedVendors`, `rootRows`, and `renderItem` callback) with a host-driven version. Diff against the current code, with these blocks substituted:

```typescript
const groupedHosts = groupModelsByHost(models);

// Discriminated union of every root-level row currently in the menu.
const rootRows: RootRow[] = [
	...groupedHosts.map((group) => ({ kind: 'host', host: group.host }) satisfies RootRow),
	{ kind: 'thinking' },
];

// Type-ahead display string for each root row — host label primary.
function rootRowDisplay(row: RootRow): string {
	return row.kind === 'host' ? hostLabel(row.host) : 'Thinking';
}
```

   and the `renderItem` becomes:

```typescript
renderItem={(row) => {
	if (row.kind === 'host') {
		const group = groupedHosts.find((entry) => entry.host === row.host);
		if (!group || group.vendors.length === 0) return null;
		const isActiveHost = selectedModel?.host === row.host;

		// Single-vendor host: skip the intermediate vendor screen and
		// render the model list directly inside this submenu.
		if (group.vendors.length === 1) {
			const onlyVendor = group.vendors[0];
			if (!onlyVendor) return null;
			return (
				<DropdownSubmenu>
					<DropdownSubmenuTrigger
						className={cn(
							'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
							isActiveHost && 'bg-foreground/[0.07]'
						)}
					>
						<VendorLogo vendor={onlyVendor.vendor} />
						<span className="min-w-0 flex-1 truncate text-left">
							{hostLabel(row.host)}
						</span>
					</DropdownSubmenuTrigger>
					<DropdownSubmenuContent className="chat-composer-dropdown-menu popover-styled p-1 min-w-64">
						{onlyVendor.entries.map((model) => (
							<ModelRow
								key={model.id}
								model={model}
								isSelected={selectedModelId === model.id}
								onSelect={onSelectModel}
							/>
						))}
					</DropdownSubmenuContent>
				</DropdownSubmenu>
			);
		}

		// Multi-vendor host: nested submenu — host → vendor → model.
		return (
			<DropdownSubmenu>
				<DropdownSubmenuTrigger
					className={cn(
						'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
						isActiveHost && 'bg-foreground/[0.07]'
					)}
				>
					<span className="min-w-0 flex-1 truncate text-left">
						{hostLabel(row.host)}
					</span>
				</DropdownSubmenuTrigger>
				<DropdownSubmenuContent className="chat-composer-dropdown-menu popover-styled p-1 min-w-56">
					{group.vendors.map((vendorGroup) => {
						const isActiveVendor =
							selectedModel?.host === row.host &&
							selectedModel?.vendor === vendorGroup.vendor;
						return (
							<DropdownSubmenu key={vendorGroup.vendor}>
								<DropdownSubmenuTrigger
									className={cn(
										'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
										isActiveVendor && 'bg-foreground/[0.07]'
									)}
								>
									<VendorLogo vendor={vendorGroup.vendor} />
									<span className="min-w-0 flex-1 truncate text-left">
										{vendorLabel(vendorGroup.vendor)}
									</span>
								</DropdownSubmenuTrigger>
								<DropdownSubmenuContent className="chat-composer-dropdown-menu popover-styled p-1 min-w-64">
									{vendorGroup.entries.map((model) => (
										<ModelRow
											key={model.id}
											model={model}
											isSelected={selectedModelId === model.id}
											onSelect={onSelectModel}
										/>
									))}
								</DropdownSubmenuContent>
							</DropdownSubmenu>
						);
					})}
				</DropdownSubmenuContent>
			</DropdownSubmenu>
		);
	}
	// 'thinking' row — unchanged
	return (
		<DropdownSubmenu>
			<DropdownSubmenuTrigger className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]">
				<div className="flex min-w-0 flex-1 flex-col text-left">
					<span className="truncate text-foreground">
						Thinking: {reasoningLabel}
					</span>
					<span className="truncate text-[11px] text-muted-foreground">
						Extended reasoning depth
					</span>
				</div>
			</DropdownSubmenuTrigger>
			<DropdownSubmenuContent className="chat-composer-dropdown-menu popover-styled p-1 min-w-32">
				{REASONING_OPTIONS.map((option) => (
					<ReasoningRow
						key={option.id}
						option={option}
						isSelected={selectedReasoning === option.id}
						onSelect={onSelectReasoning}
					/>
				))}
			</DropdownSubmenuContent>
		</DropdownSubmenu>
	);
}}
```

4. Update the malformed-vendor test guard: the current `ignores malformed vendor values instead of crashing` test passes `vendor: undefined`. `groupModelsByHost` already filters that case, so the assertion still holds. Leave it.

- [ ] **Step 4: Run the test file to verify everything passes**

Run: `cd frontend && bun run test -- features/chat/components/ModelSelectorPopover.test.tsx`
Expected: all tests green.

- [ ] **Step 5: Run the project gates**

Run: `cd frontend && bun run check && bunx tsc --noEmit && node scripts/check-nesting.mjs`
Expected: clean. The nesting checker is the most likely to complain — if it does, extract the host-row and vendor-row rendering into helper components in the same file (`HostRow`, `VendorSubmenuRow`) and call them from `renderItem`.

- [ ] **Step 6: Commit**

```bash
git add frontend/features/chat/components/ModelSelectorPopover.tsx frontend/features/chat/components/ModelSelectorPopover.test.tsx
git commit -m "feat(chat): three-level model selector (provider -> vendor -> models)"
```

---

## Task 7: Smoke check both surfaces end-to-end

**Files:** none (manual + automated final gate)

- [ ] **Step 1: Frontend visual smoke (manual)**

Run: `just dev` (in a separate terminal — leaves servers running). Open `http://localhost:3001/`, open the model picker. Verify the root rows read "Anthropic Agent SDK", "Gemini API", "xAI", "LiteLLM", "OpenCode Go". Hover "OpenCode Go" → vendor row reads "Z.AI" / "Moonshot". Hover each → model rows render. Hover "Anthropic Agent SDK" → models appear directly (no extra "Anthropic" submenu). Reload the page and confirm the persisted-model trigger label is unchanged (still `short_name`).

- [ ] **Step 2: Run the dev-console smoke**

Run: `cd frontend && node scripts/dev-console-smoke.mjs`
Expected: clean (no console errors from the new render tree).

- [ ] **Step 3: Run the full local gate**

Run: `just check-all && cd frontend && bunx tsc --noEmit && bun run test && cd ../backend && uv run pytest -x`
Expected: green everywhere. Sentrux is also fine since no new cross-layer imports were introduced (`labels.py` lives in `core/providers`, same layer as the catalog and model_id modules).

- [ ] **Step 4: Commit any test-fixture or doc fallout, then push**

```bash
git status
# If there are uncommitted changes from the smoke runs, stage them and commit.
git push
```

---

## Self-review (run by the plan author before handing off)

1. **Spec coverage:** Host-grouping, vendor-grouping, single-vendor-collapse, friendly labels, and the title-casing bug are each covered by either Task 1 (labels), Task 4 (Telegram), or Task 6 (Web). ✓
2. **Placeholder scan:** No `TBD`, `implement later`, or "add appropriate error handling" anywhere. Every code block is concrete. ✓
3. **Type consistency:** `ModelCallback.host`, `ModelCallback.provider`, `build_models_keyboard(host=, vendor=, page=, current_model_id=)`, `build_vendor_keyboard(host=)`, `format_vendor_picker_text(host=)`, `format_models_picker_text(host=, vendor=, page=)` are all consistent between Task 3, Task 4, Task 5, and the test file. The frontend `groupModelsByHost` return shape (`{ host, vendors: { vendor, entries }[] }`) is consistent between Task 6 declarations and the renderer's `group.vendors[0]` access. ✓
4. **Compatibility:** The select callback (`mdl:s:<token>:<index>`) is unchanged, so model selections from any in-flight pre-three-level keyboard still work. Pre-three-level list callbacks (`mdl:l:<vendor>:<page>`) are intentionally treated as stale because list keyboards are cheap to re-open and the alternative is parsing two shapes forever. The user pressing a stale Prev/Next button gets the standard "picker is out of date" message and reopens `/model`. ✓
