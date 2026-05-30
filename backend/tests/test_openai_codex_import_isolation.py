"""Regression: importing the provider factory must not fail when the
openai_codex package's runtime (codex binary / cli-bin wheel) is unavailable.

If this test fails, it means a cold-import problem in openai_codex/
will surface as an exception during *every* chat turn — even for chats
using Claude / Gemini / xAI / LiteLLM — which is the bug behind bean
pawrrtal-t5j8.

We force the failure mode by installing a `sys.meta_path` finder that
refuses to load `openai_codex` and its submodules. A meta_path finder
survives `sys.modules.pop(...)` and module reloads — unlike
`monkeypatch.setattr` on an inner symbol, which races with re-imports.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from typing import Any

import pytest


class _OpenAICodexBlocker:
    """meta_path finder that makes `import openai_codex` raise ImportError."""

    def find_spec(self, name: str, path: Any = None, target: Any = None) -> Any:
        if name == "openai_codex" or name.startswith("openai_codex."):
            raise ImportError(f"openai_codex blocked by isolation test ({name})")
        return None


@pytest.fixture
def _block_openai_codex() -> Iterator[None]:
    """Force `import openai_codex` to fail for the duration of the test."""
    # Evict cached modules so future imports actually hit the blocker.
    for mod in list(sys.modules):
        if mod in {
            "openai_codex",
            "app.providers.factory",
            "app.providers.openai_codex",
        } or mod.startswith(("openai_codex.", "app.providers.openai_codex.")):
            sys.modules.pop(mod, None)

    blocker = _OpenAICodexBlocker()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)
        # Clean up cached modules again so other tests in the same
        # session re-import lazily and pick up the real SDK.
        for mod in list(sys.modules):
            if mod in {
                "openai_codex",
                "app.providers.factory",
                "app.providers.openai_codex",
            } or mod.startswith(("openai_codex.", "app.providers.openai_codex.")):
                sys.modules.pop(mod, None)


@pytest.mark.usefixtures("_block_openai_codex")
def test_factory_imports_without_codex_runtime() -> None:
    """Importing the factory must succeed even when openai_codex cannot be imported."""
    factory = importlib.import_module("app.providers.factory")

    from app.providers.model_id import Host

    # All hosts are still registered…
    assert Host.agent_sdk in factory.HOST_TO_PROVIDER
    assert Host.litellm in factory.HOST_TO_PROVIDER
    assert Host.openai_codex in factory.HOST_TO_PROVIDER
    # …and the codex slot is sentinel-None (lazy resolution happens on demand).
    assert factory.HOST_TO_PROVIDER[Host.openai_codex] is None


@pytest.mark.usefixtures("_block_openai_codex")
def test_factory_codex_resolution_raises_when_runtime_unavailable() -> None:
    """When a Codex model is actually requested with no runtime, raise — never silently fall back."""
    factory = importlib.import_module("app.providers.factory")

    # Use a canonical wire string for a Codex model. The lazy resolver
    # in factory.resolve_llm should attempt the import and fail.
    with pytest.raises(ImportError):
        factory.resolve_llm("openai-codex:openai/gpt-5.5")
