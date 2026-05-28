"""Vendored / installed openai_codex Python SDK import shim.

This module makes `import openai_codex` (and its symbols: Codex, AsyncCodex,
AppServerConfig, TextInput, ReasoningEffort, etc.) work reliably from inside
Pawrrtal whether:

- The user has the published wheels installed (`openai-codex` + the
  platform-specific `openai-codex-cli-bin` that bundles the Rust binary), or
- We are developing against the git submodule at backend/vendor/codex.

Design:
- Prefer an already-importable `openai_codex` package (published wheels win).
- Fall back to inserting the vendored source tree into sys.path exactly once.
- Never mutate sys.path on every import.
- Provide a small helper to retrieve the effective module for version checks
  and introspection.

The vendored path (relative to this file) is:
    backend/vendor/codex/sdk/python/src

This file is intentionally small and has no heavy dependencies.
"""

from __future__ import annotations

import importlib
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Sentinel so we only attempt the fallback once per process.
_VENDOR_IMPORT_ATTEMPTED: bool = False
_OPENAI_CODEX_MODULE: Any | None = None


def _vendored_sdk_src_path() -> Path:
    """Return the absolute path to the vendored SDK source tree.

    Layout assumption (from the git submodule):
        backend/
            vendor/
                codex/
                    sdk/
                        python/
                            src/
                                openai_codex/
    """
    # This file lives at:
    #   backend/app/core/providers/openai_codex/_vendor.py
    # We need to walk up to the backend/ directory (5 levels).
    here = Path(__file__).resolve()
    # parents[0] = openai_codex/, [1] = providers/, [2] = core/, [3] = app/, [4] = backend/
    backend_dir = here.parents[4]
    vendored = backend_dir / "vendor" / "codex" / "sdk" / "python" / "src"
    return vendored


def _shutil_which(name: str) -> str | None:
    """Indirection seam so tests can monkeypatch the PATH lookup."""
    return shutil.which(name)


def _path_fallback_enabled() -> bool:
    """Read the OPENAI_CODEX_ALLOW_PATH_FALLBACK env var directly.

    _vendor.py is a bootstrap path with no app-config dependency, so we
    can't import app.core.config.settings here. Acceptable truthy values:
    '1', 'true', 'yes', 'on' (case-insensitive). Default False.
    """
    raw = os.environ.get("OPENAI_CODEX_ALLOW_PATH_FALLBACK", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


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
        backend_dir = _vendored_sdk_src_path().parents[3]  # go up from sdk/python/src
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
    except Exception as exc:
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


def _try_normal_import() -> Any | None:
    """Attempt a normal import of the installed openai_codex package."""
    try:
        mod = importlib.import_module("openai_codex")
        logger.debug(
            "openai_codex: using installed package (version=%s, path=%s)",
            getattr(mod, "__version__", "unknown"),
            getattr(mod, "__file__", "unknown"),
        )
        return mod
    except ImportError as exc:
        logger.debug("openai_codex: normal import failed: %s", exc)
        return None


def _try_vendored_fallback() -> Any | None:
    """Insert the vendored source path (if it exists) and import."""
    vendored_src = _vendored_sdk_src_path()
    if not vendored_src.exists():
        logger.warning(
            "openai_codex: vendored SDK source not found at %s (submodule may be missing or not initialized)",
            vendored_src,
        )
        return None

    vendored_str = str(vendored_src)
    if vendored_str not in sys.path:
        # Insert at the front so our vendored copy wins over any stale installed copy.
        sys.path.insert(0, vendored_str)
        logger.info("openai_codex: inserted vendored SDK path: %s", vendored_str)
    else:
        logger.debug("openai_codex: vendored path already on sys.path")

    try:
        # Force re-import in case a previous failed import cached a stub.
        if "openai_codex" in sys.modules:
            del sys.modules["openai_codex"]

        mod = importlib.import_module("openai_codex")
        logger.info(
            "openai_codex: using vendored SDK from submodule (version=%s, path=%s)",
            getattr(mod, "__version__", "unknown"),
            getattr(mod, "__file__", "unknown"),
        )
        return mod
    except Exception:
        logger.exception("openai_codex: failed to import from vendored path")
        return None


def ensure_openai_codex_available() -> None:
    """Ensure the openai_codex package is importable.

    Call this early (e.g. at provider package import time or in the app lifespan)
    before any code tries to `from openai_codex import ...`.

    This function is idempotent.
    """
    # Module-level cache: repeat callers (lifespan + first provider
    # instantiation) must not re-run the sys.path mutation in
    # `_attempt_vendored_import`.
    global _VENDOR_IMPORT_ATTEMPTED, _OPENAI_CODEX_MODULE  # noqa: PLW0603

    if _OPENAI_CODEX_MODULE is not None:
        return

    if _VENDOR_IMPORT_ATTEMPTED:
        if _OPENAI_CODEX_MODULE is None:
            raise RuntimeError(
                "openai_codex Python SDK is not available. "
                "Install the published 'openai-codex' + 'openai-codex-cli-bin' wheels, "
                "or ensure the backend/vendor/codex submodule is initialized."
            )
        return

    _VENDOR_IMPORT_ATTEMPTED = True

    # 1. Prefer a properly installed package (production path).
    mod = _try_normal_import()
    if mod is not None:
        _OPENAI_CODEX_MODULE = mod
        return

    # 2. Development path: fall back to the git submodule vendored source.
    mod = _try_vendored_fallback()
    if mod is not None:
        _OPENAI_CODEX_MODULE = mod
        return

    # If we reach here, nothing worked.
    raise RuntimeError(
        "openai_codex Python SDK could not be imported. "
        "Either install the official wheels (openai-codex + platform openai-codex-cli-bin), "
        "or run `git submodule update --init --recursive` for the vendored copy at backend/vendor/codex."
    )


def get_openai_codex_module() -> Any:
    """Return the imported openai_codex module after ensure_openai_codex_available() has run.

    Raises RuntimeError if the SDK is not available.
    """
    ensure_openai_codex_available()
    assert _OPENAI_CODEX_MODULE is not None
    return _OPENAI_CODEX_MODULE


# Convenience re-exports for callers who do "from . import _vendor".
# After ensure_... these names will be present on the module.
# We intentionally do NOT import the symbols at module load time;
# callers should call ensure_openai_codex_available() first (or import the
# public symbols from the Pawrrtal openai_codex package, which will do it).
__all__ = [
    "ensure_openai_codex_available",
    "get_openai_codex_module",
]
