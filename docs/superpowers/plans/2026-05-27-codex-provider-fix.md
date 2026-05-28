# Codex SDK Provider Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `OpenAICodexProvider` actually work end-to-end on the latest Codex SDK (cli-bin 0.134.0), eliminate the two stacked bugs (`ReasoningSummary.auto` and the missing codex binary), close the security gap from the SDK's auto-accept default approval handler, stop the openai_codex package's import-time side effects from leaking into other providers, and unskip the previously-`xfail`'d test suite so regressions are caught.

**Architecture:** The `openai_codex` provider wraps the official OpenAI Codex Python SDK (vendored at `backend/vendor/codex/sdk/python/src/openai_codex`, JSON-RPC over stdio with a `codex app-server` subprocess). The Python SDK source is not on PyPI — only the runtime wheel `openai-codex-cli-bin` is — so we keep using the git submodule for the Python source and pin the matching cli-bin wheel for the binary. Discovery prefers the wheel-bundled binary; a `shutil.which("codex")` dev fallback is added but disabled in production. Approvals default to **deny-all** (the SDK's library default is *accept-all*, which is a footgun). Provider imports are made lazy so module-load failures cannot bleed into non-Codex chat turns. Tests mock at the `AsyncCodex.thread_start` / `AsyncTurnHandle.stream` seam — not at the binary — so they are deterministic and don't need a real codex process.

**Tech Stack:** Python 3.13, FastAPI, `uv`, pytest + `anyio`, Pydantic v2, SQLAlchemy async, vendored `openai_codex==0.134.0` (git submodule at `backend/vendor/codex`), `openai-codex-cli-bin==0.134.0` (PyPI wheel), Alembic migrations, Conventional Commits.

---

## Pre-flight: Read These Files Before Starting

You **must** read these before touching code. They are the contracts you're working against.

- `backend/app/core/providers/openai_codex/__init__.py` — package surface, vendor bootstrap, re-exports.
- `backend/app/core/providers/openai_codex/_vendor.py` — SDK import shim + `discover_vendored_codex_bin`.
- `backend/app/core/providers/openai_codex/provider.py` — the `OpenAICodexProvider.stream(...)` body (the two bugs live here).
- `backend/app/core/providers/openai_codex/auth.py` — `build_app_server_config` (currently hands back a dict that the provider reads to construct `AppServerConfig`).
- `backend/app/core/providers/openai_codex/events.py` — `Notification` → `StreamEvent` mapper.
- `backend/app/core/providers/openai_codex/inputs.py` — history → `RunInput` translation.
- `backend/app/core/providers/factory.py:30-40,206` — registration of `Host.openai_codex`.
- `backend/app/core/providers/catalog/openai.py:79-94` — single catalog row (`openai-codex:openai/gpt-5.5`).
- `backend/app/channels/turn_runner.py:121,371,386,619-658` — codex_thread_id persistence.
- `backend/tests/test_openai_codex_provider.py:73-80` — the file-scope `xfail` wrapper.
- `backend/vendor/codex/sdk/python/src/openai_codex/api.py:277-401` — real `AsyncCodex` + `AsyncCodex.thread_start` signatures.
- `backend/vendor/codex/sdk/python/src/openai_codex/api.py:600-680` — `AsyncThread.turn` signature.
- `backend/vendor/codex/sdk/python/src/openai_codex/client.py:91-170` — `_resolve_codex_bin` + `_installed_codex_path`.
- `backend/vendor/codex/sdk/python/src/openai_codex/client.py:186-244` — `AppServerClient.__init__` + `start` (note that `approval_handler` is a constructor param, but `AsyncAppServerClient.__init__` in `async_client.py:46-51` does **not** forward it — this is the security blocker).
- `backend/vendor/codex/sdk/python/src/openai_codex/client.py:597-604` — `_default_approval_handler` (auto-accepts shell + file changes).
- `backend/vendor/codex/sdk/python/src/openai_codex/generated/v2_all.py:2685-2700` — `ReasoningSummary` and `ReasoningSummaryValue` definitions (RootModel, not Enum).
- `backend/vendor/codex/sdk/python/examples/12_turn_params_kitchen_sink/async.py:36,54` — canonical `ReasoningSummary.model_validate("concise")` usage.
- `.beans/pawrrtal-pu63--fix-live-codex-sdk-provider-binary-discovery-reaso.md` — parent bean.
- `.beans/pawrrtal-t5j8--investigate-codex-related-errors-appearing-in-other.md` — cross-provider bleed sibling bean.

---

## Background: Confirmed Failures (from live exercise on 2026-05-27)

Two stacked bugs reproduce 100% of the time when streaming through the provider:

1. **No codex binary discoverable.** `backend/pyproject.toml` does not pin `openai-codex-cli-bin`. `_vendor.discover_vendored_codex_bin` only checks vendored Rust target dirs (not built). SDK fallback raises `FileNotFoundError: Unable to locate the pinned Codex runtime…`.

2. **`ReasoningSummary.auto` crash.** `provider.py:185` treats a Pydantic `RootModel` as an Enum: `summary=ReasoningSummary.auto` → `AttributeError: auto` after `thread_start` succeeds.

The SDK's default approval handler (`client.py:597-604`) auto-accepts shell exec and file changes. Once the binary works, this lets the model write to `workspace_root` unattended. **This is a BLOCKER for shipping any other change**, per the adversarial review.

PyPI status verified 2026-05-27:
- `openai-codex-cli-bin==0.134.0` has wheels for `macosx_11_0_arm64`, `macosx_10_9_x86_64`, `manylinux_2_17_aarch64`, `manylinux_2_17_x86_64`, `win_amd64`, `win_arm64` — covers our deploy targets.
- The Python SDK (`openai-codex`) is **not** on PyPI; only the cli-bin is. We keep the git submodule for Python source.

---

## File Structure (what changes and why)

| Path | Action | Responsibility |
|---|---|---|
| `backend/app/core/providers/openai_codex/provider.py` | Modify | Add approval handler override, lazy ReasoningSummary, drop SDK private call. |
| `backend/app/core/providers/openai_codex/_vendor.py` | Modify | Add `shutil.which("codex")` fallback (off in production). |
| `backend/app/core/providers/openai_codex/__init__.py` | Modify | Tolerate vendor-bootstrap failure (don't poison module graph for other providers). |
| `backend/app/core/providers/factory.py` | Modify | Replace top-level `from .openai_codex import …` with lazy import inside `resolve_llm`. |
| `backend/pyproject.toml` | Modify | Add `openai-codex-cli-bin>=0.134.0,<0.135` dependency. |
| `backend/vendor/codex` (submodule) | Bump | Move HEAD to the upstream tag matching cli-bin 0.134.0. |
| `backend/tests/test_openai_codex_provider.py` | Rewrite (significant) | Remove file-scope `xfail`, replace fake-binary tests with `AsyncCodex.thread_start` / `handle.stream` mocks. |
| `backend/tests/test_openai_codex_import_isolation.py` | Create | Regression test: importing `factory` with the SDK unavailable must not raise. |
| `backend/scripts/smoke_codex_provider.py` | Create | Manual smoke test against a real Codex install. Documented, not gated. |
| `docs/design/codex-oauth-text-provider.md` | Modify | Update status section: live for text, version pin, approval policy, deferred items linked to follow-up beans. |
| `.beans/pawrrtal-pu63-*.md` | Update via beans CLI | Tick todos, append `## Summary of Changes`. |
| `.beans/pawrrtal-t5j8-*.md` | Update via beans CLI | Resolve or document findings of the cross-provider investigation. |

---

## Task 0: Cross-Provider Bleed Investigation (BLOCKING)

**Why first:** The user reported that Codex-related errors surface when messaging *other* providers. If true, the openai_codex package's import-time side effects are poisoning the chat path for everyone. Fix before anything else, because (a) it's a worse user-visible bug than the Codex provider being broken, and (b) the lazy-import fix changes how Steps 2–6 verify themselves.

**Files:**
- Read: `backend/app/core/providers/factory.py`, `backend/app/channels/turn_runner.py`, `backend/app/plugins/openai_codex_image_gen/plugin.py`, `backend/app/core/providers/openai_codex/__init__.py`, `backend/app/core/tools/image_gen.py`.
- Create (test): `backend/tests/test_openai_codex_import_isolation.py`
- Modify: `backend/app/core/providers/factory.py:30` (lazy-load openai_codex)
- Modify: `backend/app/core/providers/openai_codex/__init__.py` (downgrade vendor-bootstrap failure to a logged warning when no caller is asking for OpenAICodexProvider)

### Steps

- [ ] **Step 0.1: Capture the actual error symptom**

Run the backend dev server and trigger a chat turn against a non-Codex provider (Claude, Gemini, xAI). Capture the exact log lines. If you cannot reproduce immediately, search for recent log entries:

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
grep -RIn "openai_codex\|codex_thread_id\|OpenAICodex" backend/logs/ 2>/dev/null | head -30 || true
```

Look in `~/.codex/log` and `backend/.logs` if they exist. Document the captured traceback verbatim in the bean `pawrrtal-t5j8` body via `beans update`. If no error surfaces in logs, replicate by sending a chat turn through `/api/v1/chats/*/messages` with model `agent-sdk:anthropic/claude-...` and `litellm:openai/gpt-5.5`.

- [ ] **Step 0.2: Write failing isolation test**

Create `backend/tests/test_openai_codex_import_isolation.py`:

```python
"""Regression: importing the provider factory must not fail when the
openai_codex package's runtime (codex binary / cli-bin wheel) is unavailable.

If this test fails, it means a cold-import problem in openai_codex/
will surface as an exception during *every* chat turn — even for chats
using Claude / Gemini / xAI / LiteLLM — which is the bug behind bean
pawrrtal-t5j8.
"""
from __future__ import annotations

import importlib
import sys


def test_factory_imports_without_codex_runtime(monkeypatch):
    """
    Re-import `app.core.providers.factory` after removing the openai_codex
    package and forcing the vendor bootstrap to fail. The factory must still
    import successfully and expose HOST_TO_PROVIDER for non-Codex hosts.
    """
    # Force any later "import openai_codex" to fail.
    for mod in list(sys.modules):
        if mod.startswith("openai_codex") or mod.startswith(
            "app.core.providers.openai_codex"
        ) or mod == "app.core.providers.factory":
            sys.modules.pop(mod, None)

    def _raise(*_a, **_kw):
        raise RuntimeError("openai_codex SDK forced unavailable for this test")

    # Patch the vendor bootstrap so the import would blow up if eagerly used.
    monkeypatch.setattr(
        "app.core.providers.openai_codex._vendor.ensure_openai_codex_available",
        _raise,
    )

    factory = importlib.import_module("app.core.providers.factory")

    # Non-Codex hosts must still be registered and resolvable.
    from app.core.providers.model_id import Host

    assert Host.agent_sdk in factory.HOST_TO_PROVIDER
    assert Host.litellm in factory.HOST_TO_PROVIDER
    # Codex registration is OK as long as merely importing factory.py
    # does not eagerly construct or call into the SDK.
    assert Host.openai_codex in factory.HOST_TO_PROVIDER
```

- [ ] **Step 0.3: Run test, confirm it fails**

```bash
cd backend
uv run pytest tests/test_openai_codex_import_isolation.py -x -v
```

Expected: **FAIL** because `factory.py:30` does `from .openai_codex import OpenAICodexProvider` at module scope, which forces `ensure_openai_codex_available()` and now raises.

- [ ] **Step 0.4: Make `factory.py` import lazy for the Codex provider**

Replace `backend/app/core/providers/factory.py:30`:

```python
from .openai_codex import OpenAICodexProvider
```

with a deferred resolver. Edit `backend/app/core/providers/factory.py`:

1. Delete the top-level import on line 30.
2. Replace the `HOST_TO_PROVIDER` table entry `Host.openai_codex: OpenAICodexProvider` (line ~40) with a lazy proxy. Two options — use Option B for least disturbance:

   **Option B (recommended):** Keep the table populated by a sentinel object that resolves on call. Change `HOST_TO_PROVIDER` to map host → `Callable[[], type[AILLM]]` only for codex, and resolve at construction time in `resolve_llm`. Concretely:

```python
# Near the top, after other imports — DO NOT import openai_codex at module scope.
from typing import Callable

def _load_openai_codex_provider_cls() -> type[AILLM]:
    # Local import so a missing codex binary / wheel doesn't poison
    # non-Codex chat turns (regression: bean pawrrtal-t5j8).
    from .openai_codex import OpenAICodexProvider  # noqa: PLC0415
    return OpenAICodexProvider
```

   In `HOST_TO_PROVIDER` (line ~32), keep the type comment but populate Codex from a deferred call inside `resolve_llm`:

```python
HOST_TO_PROVIDER: dict[Host, type[AILLM] | None] = {
    Host.agent_sdk: ClaudeLLM,
    Host.agy_cli: AgyCliLLM,
    Host.gemini_cli: GeminiCliLLM,
    Host.google_ai: GeminiLLM,
    Host.litellm: LiteLLMLLM,
    Host.opencode_go: OpencodeGoLLM,
    Host.xai: XaiLLM,
    Host.openai_codex: None,  # resolved lazily in resolve_llm
}
```

   In `resolve_llm`, replace:

```python
    provider_cls = HOST_TO_PROVIDER[parsed.host]
```

   with:

```python
    provider_cls = HOST_TO_PROVIDER[parsed.host]
    if parsed.host is Host.openai_codex and provider_cls is None:
        provider_cls = _load_openai_codex_provider_cls()
```

   Update the `_missing_hosts` check (line ~147) so `None` values don't count as missing:

```python
_missing_hosts = {h for h in Host if h not in HOST_TO_PROVIDER}
if _missing_hosts:
    raise ValueError(f"HOST_TO_PROVIDER missing entries for: {_missing_hosts}")
```

   Update the `isinstance` check (line ~206):

```python
    if provider_cls in {AgyCliLLM, GeminiLLM, GeminiCliLLM, XaiLLM} or (
        parsed.host is Host.openai_codex
    ):
        return provider_cls(parsed.model, workspace_root=workspace_root)  # type: ignore[call-arg]
```

- [ ] **Step 0.5: Make `openai_codex/__init__.py` tolerate runtime failure**

The current `__init__.py` calls `ensure_openai_codex_available()` at module load and unconditionally accesses `_openai_codex.Codex`, `.AsyncCodex`, etc. (lines ~30–60). If the wheel is missing or the submodule is broken, *every* import of this package raises.

Refactor to a lazy `__getattr__` so the only thing that always runs is the bootstrap *attempt*; symbol resolution happens on first access. This preserves the public surface while letting `factory.py` survive even if codex is unusable.

Edit `backend/app/core/providers/openai_codex/__init__.py`:

```python
"""Pawrrtal openai_codex provider package."""
from __future__ import annotations

import logging
from typing import Any

from ._vendor import ensure_openai_codex_available, get_openai_codex_module

logger = logging.getLogger(__name__)

# We re-export these public symbol names. They are resolved lazily via
# __getattr__ so that *just importing this package* does not require a
# working Codex runtime. The Pawrrtal provider's stream(...) path is where
# we actually need the SDK; that path will raise loudly if the runtime is
# missing.
_SDK_TOP_LEVEL = (
    "Codex", "AsyncCodex", "AppServerConfig",
    "TextInput", "Input", "InputItem", "RunInput",
    "ImageInput", "LocalImageInput",
)
_SDK_DEEP = (
    "ReasoningEffort", "ReasoningSummary", "ApprovalMode", "SandboxMode",
    "Thread", "AsyncThread", "TurnHandle", "AsyncTurnHandle", "TurnResult",
    "AppServerError", "AppServerRpcError",
    "TransportClosedError", "RetryLimitExceededError",
)


def _resolve_sdk_symbol(name: str) -> Any:
    mod = get_openai_codex_module()
    val = getattr(mod, name, None)
    if val is not None:
        return val
    v2 = getattr(getattr(mod, "generated", None), "v2_all", None)
    if v2 is not None:
        return getattr(v2, name, None)
    return None


def __getattr__(name: str) -> Any:
    # Allow these to be imported by name only when the caller actually
    # needs them. Raises a clear RuntimeError when the SDK is unavailable.
    if name in _SDK_TOP_LEVEL or name in _SDK_DEEP:
        val = _resolve_sdk_symbol(name)
        if val is None:
            raise AttributeError(
                f"openai_codex SDK does not expose {name!r} "
                "in this version (vendored or installed)."
            )
        return val
    if name == "OpenAICodexProvider":
        # Local import to avoid eager Codex SDK resolution at package import.
        from .provider import OpenAICodexProvider  # noqa: PLC0415
        return OpenAICodexProvider
    if name == "resolve_openai_codex_auth":
        from .auth import resolve_openai_codex_auth  # noqa: PLC0415
        return resolve_openai_codex_auth
    if name == "OpenAICodexAuthError":
        from .auth import OpenAICodexAuthError  # noqa: PLC0415
        return OpenAICodexAuthError
    raise AttributeError(name)


__all__ = [
    "ensure_openai_codex_available",
    "get_openai_codex_module",
    *_SDK_TOP_LEVEL,
    *_SDK_DEEP,
    "OpenAICodexProvider",
    "resolve_openai_codex_auth",
    "OpenAICodexAuthError",
]
```

Crucially: the top of `__init__.py` no longer calls `ensure_openai_codex_available()` eagerly. That call now happens in `_resolve_sdk_symbol` only when a caller actually reads a symbol.

- [ ] **Step 0.6: Re-run the isolation test, confirm it passes**

```bash
cd backend
uv run pytest tests/test_openai_codex_import_isolation.py -x -v
```

Expected: **PASS**.

- [ ] **Step 0.7: Verify nothing else broke**

```bash
cd backend
uv run pytest tests/test_provider_labels.py tests/test_openai_codex_provider.py -x -v 2>&1 | tail -40
```

Tests in `test_openai_codex_provider.py` are still `xfail` at file scope at this point (that's fixed in Task 5). We want zero new failures. Provider-label tests must stay green.

- [ ] **Step 0.8: Commit**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
git add backend/app/core/providers/factory.py \
        backend/app/core/providers/openai_codex/__init__.py \
        backend/tests/test_openai_codex_import_isolation.py
git commit -m "fix(openai_codex): make package import lazy so SDK failures don't poison other providers

The openai_codex package previously ran ensure_openai_codex_available() at
import time and dereferenced SDK symbols on the module object during
__init__.py execution. Because factory.py imports OpenAICodexProvider at
the top level, every chat turn — Claude, Gemini, xAI, LiteLLM — paid the
cost of the Codex SDK bootstrap, and any failure (missing codex binary,
broken vendored submodule) surfaced as an error inside an unrelated
turn.

Move SDK symbol resolution behind module-level __getattr__ so it's lazy,
and have factory.py resolve OpenAICodexProvider via a local import inside
resolve_llm only when a Codex model is actually requested.

Regression test in test_openai_codex_import_isolation.py."
```

---

## Task 1: Approval Handler Security Fix (BLOCKER)

**Why next:** The Codex SDK's default approval handler auto-accepts arbitrary shell exec and file writes against `cwd=workspace_root` (`vendor/codex/sdk/python/src/openai_codex/client.py:597-604`). The async client (`AsyncAppServerClient.__init__` in `async_client.py:46-51`) does not forward an `approval_handler` parameter at all — only the sync client accepts it. We must reach into the sync client and replace the handler with deny-all before any turn runs. Until we do, every fix below makes the security worse.

**Files:**
- Modify: `backend/app/core/providers/openai_codex/provider.py` (in `_ensure_codex`, install a deny-all handler on `self._codex._client._sync._approval_handler` — explicit private surface poke, with a TODO bean reference).
- Modify: `backend/tests/test_openai_codex_provider.py` — add a unit test asserting the deny-all handler is installed before `_ensure_initialized()` is called.

### Steps

- [ ] **Step 1.1: Write failing test**

Add a new test in `backend/tests/test_openai_codex_provider.py` (above the existing image-plugin block):

```python
@pytest.mark.anyio
async def test_provider_installs_deny_all_approval_handler(monkeypatch):
    """
    REGRESSION: The SDK's default approval handler accepts all
    shell-exec and file-change requests. The provider MUST install a
    deny-all handler before the codex app-server starts.
    See client.py:_default_approval_handler — accepts by default.
    """
    if OpenAICodexProvider is None:
        pytest.skip("provider not importable")

    provider = OpenAICodexProvider("gpt-5.5", workspace_root=None)

    # Don't actually spawn a real binary.
    class _FakeSyncClient:
        def __init__(self):
            self._approval_handler = None
    class _FakeClient:
        def __init__(self):
            self._sync = _FakeSyncClient()
    class _FakeCodex:
        def __init__(self):
            self._client = _FakeClient()
        async def _ensure_initialized(self):
            return None

    fake = _FakeCodex()
    # Skip the actual AsyncCodex(...) construction.
    monkeypatch.setattr(provider, "_codex", fake)

    # Call the (now-extracted) handler installer directly. This will
    # become a real method on the provider in step 1.2.
    provider._install_deny_all_approval_handler()

    handler = fake._client._sync._approval_handler
    assert handler is not None
    assert handler(
        "item/commandExecution/requestApproval", {"command": "rm -rf /"}
    ) == {"decision": "deny"}
    assert handler(
        "item/fileChange/requestApproval", {"path": "/etc/passwd"}
    ) == {"decision": "deny"}
```

- [ ] **Step 1.2: Run test, confirm it fails**

```bash
cd backend
uv run pytest tests/test_openai_codex_provider.py::test_provider_installs_deny_all_approval_handler -x -v
```

Expected: **FAIL** with `AttributeError: 'OpenAICodexProvider' object has no attribute '_install_deny_all_approval_handler'`.

- [ ] **Step 1.3: Implement the deny-all installer in `provider.py`**

Edit `backend/app/core/providers/openai_codex/provider.py`. Add the helper method to the class and call it from `_ensure_codex` *immediately after* `AsyncCodex(...)` returns, *before* `_ensure_initialized()` is called.

```python
# Add near the top of the file, with the other helpers:
_DENY_ALL_DECISION: dict[str, str] = {"decision": "deny"}


def _deny_all_approval_handler(method: str, params: dict | None) -> dict:
    """Reject every escalation request.

    The SDK's default (vendor/codex/sdk/python/src/openai_codex/client.py:597)
    is to *accept* shell exec and file writes. Pawrrtal turns must not let
    the spawned codex app-server modify the workspace silently. Per-tool
    approvals are handled by the chat router's tool composition (see
    .claude/rules/architecture/no-tools-in-providers.md). Once the tool
    bridge lands (bean pawrrtal-roi0), this handler should be replaced with
    one that consults the agent loop.
    """
    if method == "item/commandExecution/requestApproval":
        return _DENY_ALL_DECISION
    if method == "item/fileChange/requestApproval":
        return _DENY_ALL_DECISION
    return {}
```

Inside the `OpenAICodexProvider` class, add:

```python
def _install_deny_all_approval_handler(self) -> None:
    """Install the deny-all approval handler on the underlying sync client.

    AsyncCodex / AsyncAppServerClient (vendored 0.134.0) do not currently
    accept an approval_handler kwarg, so we reach into the wrapped sync
    client to override its default. Tracked in bean pawrrtal-roi0 (tool
    bridge) which will replace this with a proper handler.
    """
    if self._codex is None:
        return
    # Tolerant access in case the SDK ever renames internals.
    client = getattr(self._codex, "_client", None)
    sync = getattr(client, "_sync", None)
    if sync is None:
        logger.warning(
            "openai_codex: could not reach sync client to install approval handler "
            "— falling back to SDK default which AUTO-ACCEPTS shell + file changes."
        )
        return
    sync._approval_handler = _deny_all_approval_handler
```

In `_ensure_codex`, after the `self._codex = AsyncCodex(config=config)` line and *before* returning, call:

```python
        self._codex = AsyncCodex(config=config)
        self._install_deny_all_approval_handler()
        return self._codex
```

- [ ] **Step 1.4: Run test, confirm it passes**

```bash
cd backend
uv run pytest tests/test_openai_codex_provider.py::test_provider_installs_deny_all_approval_handler -x -v
```

Expected: **PASS**.

- [ ] **Step 1.5: Commit**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
git add backend/app/core/providers/openai_codex/provider.py \
        backend/tests/test_openai_codex_provider.py
git commit -m "fix(openai_codex): install deny-all approval handler before first turn

The Codex SDK's default approval handler (client.py:_default_approval_handler)
auto-accepts shell exec and file-change escalations from the spawned
app-server binary. With cwd=workspace_root, this would let the model
modify the user's workspace unattended.

AsyncCodex doesn't expose approval_handler at construction time, so we
reach into AsyncAppServerClient._sync to install a deny-all override
immediately after constructing the client and before initialize().

When the tool bridge lands (bean pawrrtal-roi0), this will be replaced
with an agent-loop-aware handler."
```

---

## Task 2: Fix `ReasoningSummary.auto` (lazy resolution)

**Why this order:** Smallest, most contained bug, but it must land before the binary works so first-turn smoke succeeds. Lazy resolution (not module-scope) so an SDK version drift can't crash backend startup.

**Files:**
- Modify: `backend/app/core/providers/openai_codex/provider.py` — replace `ReasoningSummary.auto` with lazy `ReasoningSummary.model_validate("auto")`.
- Modify: `backend/tests/test_openai_codex_provider.py` — add a unit test mocking `AsyncCodex.thread_start` and asserting `summary` is a valid SDK value.

### Steps

- [ ] **Step 2.1: Write failing test**

Add to `backend/tests/test_openai_codex_provider.py`:

```python
@pytest.mark.anyio
async def test_provider_passes_validated_reasoning_summary(monkeypatch):
    """
    REGRESSION: provider used `ReasoningSummary.auto` which is invalid
    because ReasoningSummary is a Pydantic RootModel, not an Enum.
    Confirm the provider now passes a model-validated instance whose
    `.root` is the `auto` value.
    """
    if OpenAICodexProvider is None:
        pytest.skip("provider not importable")

    from app.core.providers.openai_codex import ReasoningSummary
    from app.core.providers.openai_codex.provider import (
        _get_default_reasoning_summary,
    )

    summary = _get_default_reasoning_summary()
    assert isinstance(summary, ReasoningSummary)
    # RootModel exposes the inner value as .root
    assert getattr(summary.root, "value", summary.root) == "auto"
```

- [ ] **Step 2.2: Run test, confirm it fails**

```bash
cd backend
uv run pytest tests/test_openai_codex_provider.py::test_provider_passes_validated_reasoning_summary -x -v
```

Expected: **FAIL** with `ImportError: cannot import name '_get_default_reasoning_summary'`.

- [ ] **Step 2.3: Implement lazy resolver in `provider.py`**

Add to `backend/app/core/providers/openai_codex/provider.py`, near the top:

```python
_DEFAULT_REASONING_SUMMARY: Any | None = None


def _get_default_reasoning_summary() -> Any:
    """Lazily build a validated ReasoningSummary("auto") on first use.

    ReasoningSummary is a Pydantic RootModel (see
    vendor/codex/sdk/python/src/openai_codex/generated/v2_all.py:2685).
    Canonical SDK usage is ReasoningSummary.model_validate("auto")
    (see vendor/codex/sdk/python/examples/12_turn_params_kitchen_sink/async.py).

    We resolve lazily — not at module import — so an SDK enum/RootModel
    drift in a future cli-bin bump surfaces as a clear runtime error on
    a Codex turn, not as a backend startup crash that takes down
    every other provider.
    """
    global _DEFAULT_REASONING_SUMMARY
    if _DEFAULT_REASONING_SUMMARY is None:
        from . import ReasoningSummary  # noqa: PLC0415 — lazy by design
        _DEFAULT_REASONING_SUMMARY = ReasoningSummary.model_validate("auto")
    return _DEFAULT_REASONING_SUMMARY
```

Then in `OpenAICodexProvider.stream(...)`, replace (currently at provider.py:182-186):

```python
            handle = await thread.turn(
                run_input,
                effort=effort,
                summary=ReasoningSummary.auto,
            )
```

with:

```python
            handle = await thread.turn(
                run_input,
                effort=effort,
                summary=_get_default_reasoning_summary(),
            )
```

Also remove the now-unused top-level import `from . import (..., ReasoningSummary, ...)` in the import block at the top — keep the import out of module scope so it can't blow up on package load.

- [ ] **Step 2.4: Run test, confirm it passes**

```bash
cd backend
uv run pytest tests/test_openai_codex_provider.py::test_provider_passes_validated_reasoning_summary -x -v
```

Expected: **PASS**.

- [ ] **Step 2.5: Commit**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
git add backend/app/core/providers/openai_codex/provider.py \
        backend/tests/test_openai_codex_provider.py
git commit -m "fix(openai_codex): resolve ReasoningSummary lazily and via model_validate

ReasoningSummary is a Pydantic RootModel, not an Enum, so the prior
\`ReasoningSummary.auto\` access raised AttributeError on every turn
after thread_start. Canonical SDK usage (per the official example at
vendor/codex/sdk/python/examples/12_turn_params_kitchen_sink/async.py)
is ReasoningSummary.model_validate(\"auto\").

The validator is wrapped in a lazy resolver so future SDK drift only
breaks Codex turns, not the whole backend startup graph."
```

---

## Task 3: Bump Vendored Submodule to Latest (0.134.0)

**Why:** User direction: "use the latest Codex SDK version." Latest stable `openai-codex-cli-bin` on PyPI is `0.134.0` (2026-05-27). The Python SDK only ships from git (`backend/vendor/codex/sdk/python/src/openai_codex`), so we bump the submodule HEAD to the upstream tag that matches the cli-bin version, then pin the matching cli-bin wheel.

**Files:**
- Modify: `backend/vendor/codex` (submodule, via `git -C`)
- Modify: `.gitmodules` (verify branch/tag fields; usually no change)
- Modify: `backend/app/core/providers/openai_codex/_vendor.py:57` — adjust vendored path if the upstream restructured `sdk/python/src`.

### Steps

- [ ] **Step 3.1: Identify the upstream tag**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai/backend/vendor/codex
git fetch --tags origin
git tag --list 'rust-v0.134.*' 'v0.134.*' 'sdk-python-v0.134.*' 'cli-v0.134.*' 2>&1 | sort -V | tail -20
```

The codex repo's tag convention is `rust-v<X.Y.Z>` for the runtime and the SDKs publish under sub-tags. Read the README of the chosen tag to confirm the Python SDK source ships at version 0.134.0. If the matching tag is not present, fall back to the closest `rust-v0.134.0` tag and check `sdk/python/pyproject.toml` for `version = "0.134.0"`.

- [ ] **Step 3.2: Check out the chosen tag**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai/backend/vendor/codex
git checkout rust-v0.134.0   # adjust to actual tag found in step 3.1
git submodule update --init --recursive
cat sdk/python/pyproject.toml | head -25
```

Confirm `version = "0.134.0"` in `sdk/python/pyproject.toml`. If absent (different tag layout), abort and re-investigate the tag scheme.

- [ ] **Step 3.3: Sanity-check the Python SDK still has the symbols we depend on**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
grep -n "^class ReasoningSummary\b\|^class AsyncCodex\b\|^class AppServerConfig\b\|^class AsyncThread\b\|^class AsyncTurnHandle\b\|^class Notification\b" \
  backend/vendor/codex/sdk/python/src/openai_codex/api.py \
  backend/vendor/codex/sdk/python/src/openai_codex/client.py \
  backend/vendor/codex/sdk/python/src/openai_codex/models.py \
  backend/vendor/codex/sdk/python/src/openai_codex/generated/v2_all.py 2>&1 | head -20
```

If any symbol moved, you'll need to fix `__init__.py:_resolve_sdk_symbol` and `events.py:_get_sdk_type` accordingly. Capture every mismatch before moving on.

- [ ] **Step 3.4: Check that `AsyncCodex.__init__` *now* accepts `approval_handler`**

```bash
grep -n "def __init__\|approval_handler" backend/vendor/codex/sdk/python/src/openai_codex/api.py \
  backend/vendor/codex/sdk/python/src/openai_codex/async_client.py | head -20
```

If 0.134.0 added an `approval_handler` kwarg to `AsyncCodex` or `AsyncAppServerClient`, **prefer that over the private-attr injection from Task 1**. Update `provider.py` to:

```python
self._codex = AsyncCodex(
    config=config,
    approval_handler=_deny_all_approval_handler,
)
```

and delete the `_install_deny_all_approval_handler` helper (but keep the test — it should pass either way). If 0.134.0 still doesn't expose it, keep the private-attr injection and add a TODO in `provider.py` linking to the upstream issue if one exists.

- [ ] **Step 3.5: Confirm the `gpt-5.5` model id is valid for the bumped binary**

After Task 4 installs the wheel you can run the smoke script (Task 6) — but at this step, you can pre-flight by checking the bundled docs:

```bash
grep -RIn "gpt-5\.5\|model.*='gpt" backend/vendor/codex/sdk/python/docs/ backend/vendor/codex/sdk/python/examples/ 2>&1 | head -10
```

If `gpt-5` is the only OpenAI-side model id the examples use, you may need to update `backend/app/core/providers/catalog/openai.py:86` from `model="gpt-5.5"` to whatever the bumped binary actually accepts. **Do not silently change the catalog row** — surface the question and decide explicitly.

- [ ] **Step 3.6: Stage the submodule bump**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
git add backend/vendor/codex
git status backend/vendor/codex
```

`git status` should show the new submodule SHA. Do not commit yet — combine with Task 4.

---

## Task 4: Add `openai-codex-cli-bin` Wheel Pin

**Why:** Without this, the SDK's `_installed_codex_path()` raises `FileNotFoundError`. With it, the wheel ships the platform-native `codex` binary and the SDK resolves it automatically.

**Files:**
- Modify: `backend/pyproject.toml` — add the dep in the main dependencies array.

### Steps

- [ ] **Step 4.1: Find the right place to add the dep**

```bash
grep -n "^dependencies\|openai-codex" backend/pyproject.toml | head -10
```

`dependencies = [...]` is the array. Add the new pin alphabetically.

- [ ] **Step 4.2: Edit `backend/pyproject.toml`**

Add (substituting the version your submodule resolved to in Step 3.2):

```toml
    # OpenAI Codex CLI runtime. Ships the platform-native `codex` binary
    # required by the openai_codex Python SDK (vendored at
    # backend/vendor/codex). Keep the version aligned with the submodule
    # tag picked in backend/vendor/codex (see CHANGELOG / submodule bump
    # commit for the exact pin).
    "openai-codex-cli-bin==0.134.0",
```

- [ ] **Step 4.3: Sync**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai/backend
uv sync 2>&1 | tail -20
```

If `uv` complains about prerelease resolution, the chosen cli-bin version is a pre-release alpha and you'll need to add `--prerelease=allow` or pin to a stable release. The wheels for 0.134.0 stable were confirmed available on PyPI on 2026-05-27 — if a newer stable exists, use it. Avoid alpha pins.

- [ ] **Step 4.4: Confirm the bundled binary is now resolvable**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai/backend
DATABASE_URL="sqlite+aiosqlite:///:memory:" uv run python -c "
import os; os.environ['DATABASE_URL']='sqlite+aiosqlite:///:memory:'
from codex_cli_bin import bundled_codex_path
print('bundled codex bin:', bundled_codex_path())
print('exists:', bundled_codex_path().exists())
"
```

Expected: a path inside the wheel under `.venv/lib/.../codex_cli_bin/` that exists.

- [ ] **Step 4.5: Verify cross-platform wheels exist for our CI targets**

```bash
curl -s https://pypi.org/pypi/openai-codex-cli-bin/0.134.0/json \
  | python3 -c "
import sys, json
files = json.load(sys.stdin)['urls']
for f in files: print(f['filename'])
"
```

You must see, at minimum: `macosx_11_0_arm64` (local dev), `manylinux_2_17_x86_64` (CI/runtime), `manylinux_2_17_aarch64` (ARM container builds). If any are missing, **do not** ship this — drop a comment in the parent bean and switch to the `shutil.which` fallback as primary (Task 5).

- [ ] **Step 4.6: Commit (combined with Task 3 submodule bump)**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
git add backend/vendor/codex backend/pyproject.toml backend/uv.lock
git commit -m "feat(openai_codex): bump SDK to 0.134.0 and pin matching cli-bin wheel

Submodule backend/vendor/codex moved from rust-v0.131.0a4 -> rust-v0.134.0.
Added openai-codex-cli-bin==0.134.0 to backend/pyproject.toml so the SDK's
_installed_codex_path() resolves to the wheel-bundled binary instead of
raising FileNotFoundError.

Wheel manifest confirmed on PyPI for macosx_11_0_arm64, manylinux_2_17_x86_64,
manylinux_2_17_aarch64, win_amd64, win_arm64 — covers local dev + Linux CI/prod
deploy."
```

---

## Task 5: Discovery Fallback via `shutil.which("codex")`

**Why:** If a developer has the wheel uninstalled (sync race, fresh clone) but has `codex` on PATH (Homebrew, npm `@openai/codex`, etc.), the provider should still work locally. In production we never want this fallback because version skew between PATH-installed and pinned cli-bin would silently misbehave. Guard behind explicit settings flag.

**Files:**
- Modify: `backend/app/core/providers/openai_codex/_vendor.py` — extend `discover_vendored_codex_bin` with a `shutil.which` arm, gated by `settings.openai_codex_allow_path_fallback` (new bool, default False).
- Modify: `backend/app/core/config.py` — add the new setting.

### Steps

- [ ] **Step 5.1: Add the settings flag**

In `backend/app/core/config.py`, find the `Settings` class. Add:

```python
    openai_codex_allow_path_fallback: bool = Field(
        default=False,
        description=(
            "Dev-only fallback: if the openai-codex-cli-bin wheel is not "
            "installed and the vendored codex Rust binary is not built, "
            "fall back to PATH-resolved `codex`. Risks silent SDK/binary "
            "version skew; never enable in production."
        ),
    )
```

(Match the existing field style; if Settings uses `BaseSettings` from pydantic-settings, the field is auto-wired to env var `OPENAI_CODEX_ALLOW_PATH_FALLBACK`.)

- [ ] **Step 5.2: Write failing test**

Add to `backend/tests/test_openai_codex_provider.py`:

```python
def test_discover_vendored_codex_bin_returns_none_without_fallback_flag(
    monkeypatch, tmp_path
):
    """Without the dev-fallback flag, discovery must NOT return a PATH match."""
    from app.core.providers.openai_codex import _vendor

    monkeypatch.setattr(_vendor, "_vendored_sdk_src_path", lambda: tmp_path / "nope")
    monkeypatch.setenv("OPENAI_CODEX_ALLOW_PATH_FALLBACK", "false")

    # PATH has codex available locally on most dev machines via Homebrew,
    # so we explicitly do NOT mock shutil.which here. If the flag is off,
    # discovery returns None even if PATH would resolve.
    result = _vendor.discover_vendored_codex_bin()
    assert result is None


def test_discover_vendored_codex_bin_uses_path_when_flag_enabled(
    monkeypatch, tmp_path
):
    """With the flag on, fall back to PATH-resolved codex if no vendored binary."""
    from app.core.providers.openai_codex import _vendor

    fake_bin = tmp_path / "fake-codex"
    fake_bin.write_text("#!/bin/sh\necho 0.0.0\n")
    fake_bin.chmod(0o755)

    monkeypatch.setattr(_vendor, "_vendored_sdk_src_path", lambda: tmp_path / "nope")
    monkeypatch.setenv("OPENAI_CODEX_ALLOW_PATH_FALLBACK", "true")
    monkeypatch.setattr(_vendor, "_shutil_which", lambda name: str(fake_bin))

    result = _vendor.discover_vendored_codex_bin()
    assert result == fake_bin
```

- [ ] **Step 5.3: Run tests, confirm both fail**

```bash
cd backend
uv run pytest tests/test_openai_codex_provider.py::test_discover_vendored_codex_bin_returns_none_without_fallback_flag \
              tests/test_openai_codex_provider.py::test_discover_vendored_codex_bin_uses_path_when_flag_enabled -x -v
```

Expected: **FAIL** (current implementation does not consult any flag and does not have `_shutil_which`).

- [ ] **Step 5.4: Implement the fallback**

Edit `backend/app/core/providers/openai_codex/_vendor.py`. Add at the top:

```python
import os
import shutil


def _shutil_which(name: str) -> str | None:
    """Indirection seam so tests can monkeypatch."""
    return shutil.which(name)


def _path_fallback_enabled() -> bool:
    # We read the env var directly (not settings.py) so the bootstrap path
    # has no dependency on the app config module. Acceptable values: any
    # truthy string; default is False.
    raw = os.environ.get("OPENAI_CODEX_ALLOW_PATH_FALLBACK", "").strip().lower()
    return raw in ("1", "true", "yes", "on")
```

Then modify `discover_vendored_codex_bin`:

```python
def discover_vendored_codex_bin() -> Path | None:
    """Locate a Codex binary for local development.

    Resolution order (most pinned first):
        1. Vendored Cargo target dirs (backend/vendor/codex/codex-rs/target/{release,debug})
        2. (Dev only, opt-in) shutil.which("codex") — gated by
           OPENAI_CODEX_ALLOW_PATH_FALLBACK to prevent silent version skew
           with a system codex differing from the pinned cli-bin wheel.

    Returns None if neither path yields a binary; in production the SDK
    will then resolve via `codex_cli_bin.bundled_codex_path()`.
    """
    try:
        backend_dir = _vendored_sdk_src_path().parents[3]
        codex_root = backend_dir / "vendor" / "codex"
        candidates = [
            codex_root / "codex-rs" / "target" / "release" / "codex",
            codex_root / "codex-rs" / "target" / "debug" / "codex",
            codex_root / "target" / "release" / "codex",
            codex_root / "target" / "debug" / "codex",
        ]
        for p in candidates:
            if p.exists() and p.is_file():
                logger.info("openai_codex: discovered vendored codex binary at %s", p)
                return p
    except Exception as exc:  # noqa: BLE001 — best-effort discovery
        logger.debug("openai_codex: vendored binary discovery failed: %s", exc)

    if _path_fallback_enabled():
        path_match = _shutil_which("codex")
        if path_match:
            logger.warning(
                "openai_codex: using PATH-resolved codex at %s "
                "(OPENAI_CODEX_ALLOW_PATH_FALLBACK enabled). "
                "Production deployments should rely on the pinned "
                "openai-codex-cli-bin wheel instead.",
                path_match,
            )
            return Path(path_match)

    return None
```

- [ ] **Step 5.5: Run tests, confirm both pass**

```bash
cd backend
uv run pytest tests/test_openai_codex_provider.py::test_discover_vendored_codex_bin_returns_none_without_fallback_flag \
              tests/test_openai_codex_provider.py::test_discover_vendored_codex_bin_uses_path_when_flag_enabled -x -v
```

Expected: **PASS**.

- [ ] **Step 5.6: Commit**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
git add backend/app/core/providers/openai_codex/_vendor.py \
        backend/app/core/config.py \
        backend/tests/test_openai_codex_provider.py
git commit -m "feat(openai_codex): opt-in PATH fallback for local codex binary discovery

Adds OPENAI_CODEX_ALLOW_PATH_FALLBACK gate (default off). When enabled,
_vendor.discover_vendored_codex_bin falls back to shutil.which(\"codex\")
after the vendored Cargo target dirs.

Off in production so the pinned cli-bin wheel is the only binary source
— a system codex differing in version could silently introduce JSON-RPC
schema drift. On for developers who have Homebrew codex but no built
submodule."
```

---

## Task 6: Test Suite Cleanup — Remove File-Scope `xfail`

**Why:** The adversarial reviewer flagged that `test_openai_codex_provider.py` blanket-`xfail`s every test. With the live bugs fixed and a proper mocking strategy in place, the file should run strict. Image-plugin tests stay `xfail` until the plugin's activation story is done (bean pawrrtal-roi0 / image plugin).

**Files:**
- Modify: `backend/tests/test_openai_codex_provider.py:73-80` — remove `pytestmark`. Apply `xfail` narrowly to specific tests that depend on the image plugin.
- Possibly modify: individual tests in the file that were assuming a real binary or untouched defaults; some will need to be rewritten to mock at `AsyncCodex.thread_start` / `AsyncTurnHandle.stream`.

### Steps

- [ ] **Step 6.1: Read the full test file once and bucket tests by category**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai/backend
grep -n "^def test_\|^async def test_" tests/test_openai_codex_provider.py
```

Bucket each test as one of:

  - **Auth/discovery unit** — should pass with no fixtures (e.g. `test_auth_resolution_prefers_override`).
  - **Event mapper unit** — pure function over `Notification` payloads (no SDK runtime).
  - **Provider contract unit** — needs `AsyncCodex` mocked at the seam.
  - **Image plugin** — currently uses `generate_image_with_codex_agent` from the not-yet-activated plugin; keep `xfail`.

Write the bucketing as a comment block at the top of the file (you'll delete the file-scope `xfail` in the next step).

- [ ] **Step 6.2: Remove the file-scope `xfail`**

Open `backend/tests/test_openai_codex_provider.py`. Delete lines 73-80:

```python
pytestmark = pytest.mark.xfail(
    reason="Some image plugin tests remain guarded (openai_codex_image_gen plugin activation). Core provider is fully wired.",
    strict=False,
)
```

In its place, add a comment explaining the policy and a narrow marker for image-plugin tests:

```python
# Test buckets:
# - Auth/discovery, event mapper, and provider-contract tests run strict.
# - Image plugin tests are gated by the plugin's own activation story
#   (bean pawrrtal-roi0 / openai_codex_image_gen) and stay xfail until
#   that work lands.

IMAGE_PLUGIN_XFAIL = pytest.mark.xfail(
    reason="openai_codex_image_gen plugin activation pending (bean pawrrtal-roi0)",
    strict=False,
)
```

- [ ] **Step 6.3: Tag the image-plugin tests with the new marker**

For each test in the file that imports or calls `generate_image_with_codex_agent`, add `@IMAGE_PLUGIN_XFAIL` directly above its `def` line.

- [ ] **Step 6.4: Run the whole file and bucket failures**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai/backend
uv run pytest tests/test_openai_codex_provider.py -v --tb=short 2>&1 | tail -80
```

For each non-image-plugin **failure**, decide whether to:

  - **Fix the test** — usually by replacing real SDK calls with mocks at the `AsyncCodex.thread_start` / `AsyncTurnHandle.stream` seam (sample below).
  - **Delete the test** — if it was always speculative (e.g. asserting against fictional internal APIs from the original "commented plan" PR).
  - **Mark `xfail` narrowly** — only if it's a real feature gap tracked by an existing bean (link the bean in the reason). Never use `strict=False` on a fix-this-now failure.

Worked example — replacing a "fake binary" pattern with a clean SDK mock:

```python
@pytest.mark.anyio
async def test_provider_stream_emits_codex_thread_created_event(monkeypatch):
    if OpenAICodexProvider is None:
        pytest.skip("provider not importable")

    from app.core.providers.openai_codex import provider as provider_mod

    class _FakeThread:
        id = "thr_test_123"
        async def turn(self, run_input, **kw):
            class _Handle:
                async def stream(self_):
                    if False:
                        yield None  # async generator with no events; provider should still emit done at end
            return _Handle()

    class _FakeCodex:
        async def _ensure_initialized(self_): return None
        async def thread_start(self_, **kw): return _FakeThread()
        async def thread_resume(self_, tid, **kw):
            t = _FakeThread()
            t.id = tid
            return t
        async def close(self_): return None
        _client = type("_", (), {"_sync": type("_", (), {"_approval_handler": None})()})()

    async def _fake_ensure_codex(self):
        self._codex = _FakeCodex()
        return self._codex

    monkeypatch.setattr(provider_mod.OpenAICodexProvider, "_ensure_codex", _fake_ensure_codex)

    provider = provider_mod.OpenAICodexProvider("gpt-5.5")
    events = []
    async for ev in provider.stream("hi", uuid.uuid4(), uuid.uuid4()):
        events.append(ev)

    kinds = [(e.get("type"), e.get("kind")) for e in events]
    assert ("internal", "codex_thread_created") in kinds
```

Apply the same pattern to any test that was previously relying on a fake binary subprocess.

- [ ] **Step 6.5: Re-run, target zero non-xfail failures**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai/backend
uv run pytest tests/test_openai_codex_provider.py -v
```

Expected: zero failures. `xfail`s only on image-plugin tests.

- [ ] **Step 6.6: Commit**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
git add backend/tests/test_openai_codex_provider.py
git commit -m "test(openai_codex): unxfail provider/auth/mapper tests, narrow xfail to image plugin

The file used to blanket-xfail every test in it, hiding the
ReasoningSummary and binary-discovery bugs. Strict tests now cover
auth, discovery, the event mapper, and the provider's stream contract
(mocked at the AsyncCodex.thread_start / AsyncTurnHandle.stream seam).

Image plugin tests stay xfail until bean pawrrtal-roi0 lands."
```

---

## Task 7: Live Smoke Script (Optional, Manual)

**Why:** Automated tests mock the SDK. We still want a one-shot way to verify the binary really works end-to-end against the user's `~/.codex/auth.json`. This is not a CI gate — it's a documented local check before merging.

**Files:**
- Create: `backend/scripts/smoke_codex_provider.py`

### Steps

- [ ] **Step 7.1: Create the smoke script**

Create `backend/scripts/smoke_codex_provider.py`:

```python
#!/usr/bin/env python3
"""Manual smoke test for the openai_codex provider.

Usage:
    cd backend
    DATABASE_URL='sqlite+aiosqlite:///:memory:' uv run python scripts/smoke_codex_provider.py

Requires:
    - openai-codex-cli-bin installed (uv sync) OR a built submodule binary
      OR `codex` on PATH with OPENAI_CODEX_ALLOW_PATH_FALLBACK=true.
    - ~/.codex/auth.json from a normal `codex login`.

Prints each StreamEvent and exits 0 on a successful `done` event,
non-zero otherwise. Not a CI gate — keep it lightweight.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


async def main() -> int:
    from app.core.providers.openai_codex import OpenAICodexProvider

    provider = OpenAICodexProvider("gpt-5.5")
    cuid = uuid.uuid4()
    uid = uuid.uuid4()
    saw_done = False
    saw_error = False
    async for ev in provider.stream("Say hello in exactly two words.", cuid, uid):
        print("EVENT:", ev)
        if ev.get("type") == "done":
            saw_done = True
        if ev.get("type") == "error":
            saw_error = True

    if saw_error or not saw_done:
        print("SMOKE FAIL — error event surfaced or no done event")
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 7.2: Run it locally**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai/backend
DATABASE_URL='sqlite+aiosqlite:///:memory:' uv run python scripts/smoke_codex_provider.py
```

Expected: a sequence of `delta` events, optionally `thinking` events, and a terminal `done`. Then `SMOKE OK`.

If you instead see `error: Codex turn failed: …`, capture the message and bring it back into the parent bean — it's a real bug, not a config issue.

- [ ] **Step 7.3: Commit**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
git add backend/scripts/smoke_codex_provider.py
git commit -m "test(openai_codex): add manual smoke script for live end-to-end check

Not a CI gate; documented one-shot to verify the wheel-bundled codex
binary works against the local ~/.codex/auth.json after a fresh sync."
```

---

## Task 8: Documentation + Bean Closure

**Files:**
- Modify: `docs/design/codex-oauth-text-provider.md` — bump status section.
- Update via beans CLI: `pawrrtal-pu63` (this fix), `pawrrtal-t5j8` (cross-provider bleed), `pawrrtal-ujo8` (parent feature bean).

### Steps

- [ ] **Step 8.1: Update the design doc status**

In `docs/design/codex-oauth-text-provider.md`, find the top-of-file `Status:` line and replace its value with:

```
**Status:** Live for text models via `openai_codex` SDK 0.134.0 + cli-bin wheel.
Approvals deny-all (see bean pawrrtal-roi0 for the tool bridge that will
replace it). Per-workspace OAuth override not yet wired (bean pawrrtal-nf6y).
```

Add a `## Implementation Notes (2026-05-27)` section near the end pointing to:

  - `backend/app/core/providers/openai_codex/` for the runtime,
  - `backend/scripts/smoke_codex_provider.py` for the live check,
  - `backend/tests/test_openai_codex_provider.py` for the strict suite.

- [ ] **Step 8.2: Tick the parent bean todos**

```bash
beans update --json pawrrtal-pu63 \
  --body-replace-old "- [ ] Bump vendored submodule backend/vendor/codex to latest stable tag (matching cli-bin 0.134.0+)" \
  --body-replace-new "- [x] Bump vendored submodule backend/vendor/codex to latest stable tag (matching cli-bin 0.134.0+)"

beans update --json pawrrtal-pu63 \
  --body-replace-old "- [ ] Add openai-codex-cli-bin pin to backend/pyproject.toml matching the bumped SDK" \
  --body-replace-new "- [x] Add openai-codex-cli-bin pin to backend/pyproject.toml matching the bumped SDK"

beans update --json pawrrtal-pu63 \
  --body-replace-old "- [ ] Fix ReasoningSummary.auto -> ReasoningSummary.model_validate('auto') in provider.py:185" \
  --body-replace-new "- [x] Fix ReasoningSummary.auto -> ReasoningSummary.model_validate('auto') in provider.py:185"

beans update --json pawrrtal-pu63 \
  --body-replace-old "- [ ] Extend _vendor.discover_vendored_codex_bin with shutil.which('codex') fallback (dev-only guard)" \
  --body-replace-new "- [x] Extend _vendor.discover_vendored_codex_bin with shutil.which('codex') fallback (dev-only guard)"

beans update --json pawrrtal-pu63 \
  --body-replace-old "- [ ] Write failing tests first (mock _resolve_codex_bin or use launch_args_override)" \
  --body-replace-new "- [x] Write failing tests first (mocked at AsyncCodex.thread_start / AsyncTurnHandle.stream — not the binary)"

beans update --json pawrrtal-pu63 \
  --body-replace-old "- [ ] Remove file-scope pytest.mark.xfail from tests/test_openai_codex_provider.py; re-add only on image-plugin tests" \
  --body-replace-new "- [x] Remove file-scope pytest.mark.xfail from tests/test_openai_codex_provider.py; re-add only on image-plugin tests"

beans update --json pawrrtal-pu63 \
  --body-replace-old "- [ ] Verify live stream end-to-end (delta + done events)" \
  --body-replace-new "- [x] Verify live stream end-to-end (delta + done events)"
```

- [ ] **Step 8.3: Append summary to the bean and complete it**

```bash
beans update --json pawrrtal-pu63 -s completed --body-append "## Summary of Changes

- Made the openai_codex package import lazy via module-level __getattr__ so SDK runtime failures stop bleeding into other providers (fixes bean pawrrtal-t5j8).
- factory.py no longer imports OpenAICodexProvider at module scope; resolved on demand inside resolve_llm().
- provider.py installs a deny-all approval handler on the wrapped sync client before _ensure_initialized() — closes the security gap from the SDK's auto-accept default. Bean pawrrtal-roi0 will replace this with an agent-loop-aware handler.
- provider.py resolves ReasoningSummary lazily via model_validate('auto'); future SDK drift fails on the Codex turn instead of crashing backend startup.
- Bumped backend/vendor/codex submodule to rust-v0.134.0 (matches latest cli-bin).
- Added openai-codex-cli-bin==0.134.0 to backend/pyproject.toml. Wheel manifest covers macosx_11_0_arm64, manylinux_2_17_x86_64, manylinux_2_17_aarch64, win_amd64, win_arm64.
- _vendor.discover_vendored_codex_bin grew an OPENAI_CODEX_ALLOW_PATH_FALLBACK-gated shutil.which fallback for devs without the wheel.
- Removed the file-scope pytest.mark.xfail from tests/test_openai_codex_provider.py. Strict coverage for auth, discovery, event mapping, and provider contract; image-plugin tests remain xfail under IMAGE_PLUGIN_XFAIL pending bean pawrrtal-roi0.
- Added scripts/smoke_codex_provider.py for the manual end-to-end check.

Follow-up beans:
- pawrrtal-roi0 — wire the AgentTool bridge and replace deny-all approvals.
- pawrrtal-nf6y — per-workspace OPENAI_CODEX_OAUTH_TOKEN injection.
- pawrrtal-t5j8 — closed by Task 0 of this plan; see commit history."
```

- [ ] **Step 8.4: Complete or update the bleed-investigation bean**

```bash
beans update --json pawrrtal-t5j8 -s completed --body-append "## Summary of Changes

Root cause: backend/app/core/providers/openai_codex/__init__.py was running
ensure_openai_codex_available() at module import time, and
backend/app/core/providers/factory.py:30 imported OpenAICodexProvider at
the top level. Together these meant every chat turn (regardless of
provider) paid the Codex SDK bootstrap cost, and any failure (missing
codex binary, ReasoningSummary AttributeError) surfaced inside an
unrelated turn.

Fixed in Task 0 of plan docs/superpowers/plans/2026-05-27-codex-provider-fix.md:
- Lazy module-level __getattr__ in openai_codex/__init__.py.
- factory.py resolves OpenAICodexProvider on demand inside resolve_llm.
- Regression test in backend/tests/test_openai_codex_import_isolation.py."
```

- [ ] **Step 8.5: Commit docs and bean updates**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
git add docs/design/codex-oauth-text-provider.md .beans/
git commit -m "docs(openai_codex): update design doc + close fix + bleed beans

Marks the codex SDK provider live for text via 0.134.0 + cli-bin wheel.
Deny-all approval handler is the current security posture; agent-loop-
aware handler tracked in bean pawrrtal-roi0. Per-workspace OAuth
override in bean pawrrtal-nf6y."
```

---

## Final Verification (after all tasks)

- [ ] **Step 9.1: Full backend lint + typecheck + tests**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
just check-all 2>&1 | tail -30
```

Expected: clean (ruff + biome + bandit + mypy).

- [ ] **Step 9.2: Full backend pytest**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai/backend
uv run pytest 2>&1 | tail -25
```

Expected: zero failures, only `xfail`s in `test_openai_codex_provider.py` for image-plugin tests.

- [ ] **Step 9.3: Frontend type/lint (touched none of it but confirm no fallout)**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai/frontend
bun run check && bun run typecheck
```

Expected: clean.

- [ ] **Step 9.4: Live smoke**

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai/backend
DATABASE_URL='sqlite+aiosqlite:///:memory:' uv run python scripts/smoke_codex_provider.py
```

Expected: stream of events terminating in `done`, final line `SMOKE OK`.

- [ ] **Step 9.5: Real chat turn against a non-Codex provider**

Start the backend with `just dev`. Open the frontend, pick **Claude** (or Gemini, or LiteLLM/OpenAI), send a message. The turn must complete cleanly with no `openai_codex` mentions in the logs.

- [ ] **Step 9.6: Real chat turn against the Codex provider**

In the same UI, pick **GPT-5.5 (Codex SDK)**. Send a short message. Turn completes; `Conversation.codex_thread_id` is populated in the DB; a follow-up message in the same conversation reuses the thread (verify in turn_runner logs).

- [ ] **Step 9.7: Final commit + push**

If any verification step required a small adjustment, fold it into a single follow-up commit and push:

```bash
cd /Volumes/WorkDriveExternal/Projects/Work/comcom/.gstack/Prs/pawrrtal-ai
git log --oneline -10
git push origin development
```

---

## Risks, Open Questions, and Mitigations

- **Submodule tag mismatch (Step 3.1).** If the codex upstream's tag naming changed (e.g. they moved from `rust-vX.Y.Z` to `cli-vX.Y.Z`), Step 3.1 may need manual investigation. The README's `## Compatibility and versioning` section in the submodule is authoritative.
- **`gpt-5.5` model rejection (Step 3.5).** The catalog row may need to change to whatever the 0.134.0 binary actually accepts. If so, surface the change in a separate commit so the model-name decision is reviewable independently of the wiring fixes.
- **manylinux gap (Step 4.5).** Already confirmed present for 0.134.0 on 2026-05-27, but re-check at execution time. If a future release drops manylinux, this plan must fall back to the `OPENAI_CODEX_ALLOW_PATH_FALLBACK` flag as the *primary* discovery path for Linux deploys, and the cli-bin pin becomes macOS/Win-only.
- **AsyncCodex `approval_handler` kwarg in 0.134.0 (Step 3.4).** Prefer the official kwarg if it exists; private-attr injection is a fallback. Confirm at execution time.
- **`xfail` removal flushing unrelated red (Step 6.4).** Expect 5–15 dormant failures. Budget time to triage each: fix, delete, or narrow-`xfail` with a bean reference. Do not silently re-enable file-scope `xfail`.
- **Rollback story.** Tasks 1, 2, 3, 4 each land as separate commits so a platform-specific wheel failure (e.g. manylinux missing on a future bump) is bisectable. Task 3 + Task 4 commit together because they are version-coupled.

---

## Self-Review

- ✅ Spec coverage: each adversarial-review finding (BLOCKERS, HIGH, MEDIUM, NITs) maps to a step. The BLOCKER on approval handler is Task 1, BLOCKER on manylinux is Step 4.5, HIGH on lazy ReasoningSummary is Task 2, HIGH on test design uses SDK-seam mocks (Task 6.4 + Task 1.1 + Task 2.1), HIGH on live-stream gate is Task 7 + Step 9.4, HIGH on `gpt-5.5` model verification is Step 3.5 + 9.6, HIGH on PATH-fallback drift is Task 5 (gated, off by default). MEDIUM on `xfail` flush is Task 6. NIT on private `_ensure_initialized` is left in place but called out; the cross-provider bleed (`pawrrtal-t5j8`) is fixed in Task 0.
- ✅ No placeholders. Every step has the actual command, code, or expected output.
- ✅ Type consistency: `_get_default_reasoning_summary`, `_install_deny_all_approval_handler`, `OPENAI_CODEX_ALLOW_PATH_FALLBACK`, `_path_fallback_enabled`, `_shutil_which`, `_deny_all_approval_handler`, `IMAGE_PLUGIN_XFAIL` are used identically wherever they appear.
