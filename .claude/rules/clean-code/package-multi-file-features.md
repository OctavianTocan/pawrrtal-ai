---
name: Package Multi-File Features Instead of Flat Files With Redundant Prefixes
paths: ["backend/**/*.py", "frontend/**/*.{ts,tsx}"]
---

# Package Multi-File Features Instead of Flat Files With Redundant Prefixes

When a feature, provider, or subsystem grows past a single module,
collect its files into a package directory and drop the feature-name
prefix from each module — the directory already carries that
namespace. Flat `feature.py` + `_feature_events.py` + `_feature_io.py`
sibling clusters create three problems:

1. **Redundant prefix.** Every reader pays for `_feature_` in every
   import path. `foo.feature` + `foo._feature_events` + `foo._feature_io`
   reads worse than `foo.feature` + `foo.feature.events` + `foo.feature.io`.
2. **No clear external surface.** A package's `__init__.py` is the one
   place external callers import from. Flat siblings have no equivalent;
   each consumer picks whichever underscored sibling they need, and a
   rename means touching every call site.
3. **Privacy boundary blur.** The `_` prefix on a module is supposed
   to signal "package-internal." But when the package is the
   providers directory itself, half the things in it are internal
   helpers for one provider and the other half are the public
   providers — the `_` carries less weight than a real directory
   boundary would.

The trigger: as soon as a single feature owns **more than one
module**, promote it to a package. One-file features stay flat.

## Rule

When you'd otherwise create a second sibling file with the same
feature prefix:

1. Make a directory at the existing feature's location: `feature_name/`.
2. Move the existing file in as `feature_name/<role>.py`. The "role"
   names what the file *does*, not what feature it belongs to —
   `provider.py`, `client.py`, `events.py`, `fs.py`, `messages.py`,
   `stream.py`. **No feature-name prefix on the file.**
3. Create `feature_name/__init__.py` that re-exports the public
   surface (the symbols other modules import) and nothing else.
4. Within the package, cross-module imports use absolute paths
   (`from app.x.feature_name.events import ...`) so ruff's TID252
   stays happy and grep'ing for a symbol shows the canonical path.
5. External callers import only from the package: `from app.x.feature_name
   import PublicSymbol`. Never reach past `__init__.py` from outside.

## Why

The pawrrtal Gemini CLI provider hit this on review. The first draft
shipped four flat files —
`backend/app/core/providers/gemini_cli_provider.py`,
`_gemini_cli_client.py`, `_gemini_cli_acp.py`, `_gemini_cli_fs.py` —
all sitting next to unrelated providers (`claude_provider.py`,
`xai_provider.py`, `gemini_provider.py`, …). The reviewer flagged it:
the `_gemini_cli_` prefix appeared 27 times across imports and module
docstrings, and every consumer had to pick which of four sibling
modules to import from.

Moving to `gemini_cli/` (`provider.py`, `client.py`, `acp.py`,
`fs.py`, `__init__.py`) cut the redundant prefix and gave the
package a single external entry point (`from app.core.providers.gemini_cli
import GeminiCliLLM, …`). The diff was mechanical and the
public-surface footprint shrank.

## Applies to

- **Backend providers** (`backend/app/core/providers/`) — the
  canonical case. `gemini_cli/` is the first package-shaped provider;
  treat its layout as the template when the next multi-file provider
  lands. Single-file providers like `litellm_provider.py` stay flat
  until a second module is needed.
- **Frontend features** (`frontend/features/<feature>/`) already
  follow this convention by repo policy.
- **Any backend subsystem** that ends up with multiple cooperating
  modules — channels, integrations, tools, governance.

## Verify

"Am I about to create a second file with the same `<feature>_` prefix
or `_<feature>_` prefix sitting next to its first sibling? If yes:
should this be a package directory instead?"

## Patterns

Bad — flat siblings with redundant prefix:

```text
backend/app/core/providers/
  gemini_cli_provider.py
  _gemini_cli_client.py
  _gemini_cli_acp.py
  _gemini_cli_fs.py
```

```python
# Consumers can't tell which file holds the public surface.
from app.core.providers.gemini_cli_provider import GeminiCliLLM
from app.core.providers._gemini_cli_client import PawrrtalAcpClient
from app.core.providers._gemini_cli_acp import open_session
```

Good — package with role-named modules:

```text
backend/app/core/providers/gemini_cli/
  __init__.py        # re-exports public surface
  provider.py        # GeminiCliLLM, is_gemini_cli_available, …
  client.py          # PawrrtalAcpClient
  acp.py             # ACP handshake + prompt drive
  fs.py              # filesystem callbacks
```

```python
# __init__.py
from app.core.providers.gemini_cli.provider import (
    GEMINI_BINARY_NAME,
    GeminiCliLLM,
    is_gemini_cli_available,
    render_history_prefix,
)

__all__ = [
    "GEMINI_BINARY_NAME",
    "GeminiCliLLM",
    "is_gemini_cli_available",
    "render_history_prefix",
]
```

```python
# Every external consumer goes through the package surface.
from app.core.providers.gemini_cli import GeminiCliLLM, is_gemini_cli_available
```

## Exceptions

- **Truly single-module features.** Don't pre-package a feature that
  fits in one file just because it might grow. Promote when the
  second file actually needs to exist.
- **External-package mirrors.** If the file mirrors a published
  package's layout (e.g. a vendored `react-overlay/` copy), match the
  upstream structure even if it diverges from this rule.
- **Test files.** Tests under `tests/` / `__tests__/` group by
  subject under test, not by package layout. A single
  `test_<feature>.py` file is fine even when the feature is a
  package; only split the test file when it actually grows past the
  500-line budget.
