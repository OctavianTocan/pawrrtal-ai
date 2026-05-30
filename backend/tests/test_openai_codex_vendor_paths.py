"""Tests for OpenAI Codex vendored SDK path discovery."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_vendored_sdk_src_path_points_at_backend_submodule() -> None:
    """Vendored SDK imports must resolve under ``backend/vendor/codex``."""
    from app.providers.openai_codex import _vendor

    backend_root = Path(__file__).resolve().parents[1]

    assert _vendor._vendored_sdk_src_path() == (
        backend_root / "vendor" / "codex" / "sdk" / "python" / "src"
    )


def test_discover_vendored_codex_bin_uses_backend_submodule(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Binary discovery must look beside the SDK under the same submodule."""
    from app.providers.openai_codex import _vendor

    sdk_src = tmp_path / "backend" / "vendor" / "codex" / "sdk" / "python" / "src"
    codex_bin = (
        tmp_path / "backend" / "vendor" / "codex" / "codex-rs" / "target" / "release" / "codex"
    )
    codex_bin.parent.mkdir(parents=True)
    codex_bin.write_text("#!/bin/sh\n")
    codex_bin.chmod(0o755)

    monkeypatch.setattr(_vendor, "_vendored_sdk_src_path", lambda: sdk_src)

    assert _vendor.discover_vendored_codex_bin() == codex_bin
