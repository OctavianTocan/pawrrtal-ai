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
        if (
            mod.startswith("openai_codex")
            or mod.startswith("app.core.providers.openai_codex")
            or mod == "app.core.providers.factory"
        ):
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
