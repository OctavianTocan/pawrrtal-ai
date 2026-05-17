---
# pawrrtal-bn6c
title: Phase 7 — Channel registry registration
status: todo
type: task
priority: normal
created_at: 2026-05-14T19:52:13Z
updated_at: 2026-05-14T19:52:13Z
parent: pawrrtal-l65f
blocked_by:
    - pawrrtal-0rah
---

## Why

Two consumers need this:

1. **The turn streaming wrapper** (bean 9) calls `resolve_channel("telegram")`
   to get the singleton, then calls `.deliver(stream, msg)` on it. Without
   the registration this returns `SSEChannel` (the fallback) and the deliver
   loop tries to write SSE bytes to nothing.
2. **The frontend hook + tests** assert `registered_surfaces()` includes
   `"telegram"` once the channel ships.

This bean is tiny but blocks the integration tests.

## What to build

Two file edits:

### `backend/app/channels/registry.py`

Re-add the import and the dict entry. The deletion left a comment marker
showing where:

```
from .telegram import SURFACE_TELEGRAM, TelegramChannel
...
_REGISTRY: dict[str, Channel] = {
    SURFACE_WEB:      SSEChannel(surface=SURFACE_WEB),
    SURFACE_ELECTRON: SSEChannel(surface=SURFACE_ELECTRON),
    SURFACE_TELEGRAM: TelegramChannel(),       # <-- this line
}
```

### `backend/app/channels/__init__.py`

Re-export `TelegramChannel` so `from app.channels import TelegramChannel`
works (tests use this form):

```
from .telegram import TelegramChannel
...
__all__ = [..., "TelegramChannel", ...]
```

## Contracts

- `TelegramChannel()` takes no constructor args. It's a stateless singleton —
  per-request state travels through `ChannelMessage.metadata`.
- The registry's `resolve_channel(surface: str)` falls back to the web SSE
  channel on unknown surfaces. So a bug where the surface name doesn't match
  produces a silent-ish failure (SSE bytes nobody reads) rather than a
  KeyError. Keep `SURFACE_TELEGRAM = "telegram"` consistent everywhere.

## Edge cases

- Don't make `TelegramChannel` instantiation depend on settings. The registry
  module imports at app startup; the bot may be disabled but the channel
  type still has to be constructible (it's the registration that gates
  usage, not the existence of an instance).
- Order in `_REGISTRY` doesn't matter functionally; keep web/electron/
  telegram for readability.

## Tests that should pass after this

```bash
cd backend && .venv/bin/python -m pytest \
  tests/test_telegram_channel.py::TestTelegramChannelSurface \
  tests/test_telegram_channel.py::TestTelegramRegistry \
  tests/test_channels.py::TestRegisteredSurfaces \
  -x
```

`test_telegram_channel.py::TestTelegramRegistry` has two cases:

- `test_resolve_returns_telegram_channel` — `resolve_channel("telegram")` is
  an instance of `TelegramChannel`.
- `test_registered_surface_included` — `"telegram" in registered_surfaces()`.

## Next

Bean 8 — the framework-thin handlers (`backend/app/integrations/telegram/handlers.py`).
These are the inbound dispatch logic: `/start`, `/stop`, `/new`, `/model`,
plain message. After bean 8, the rest of `test_channels_api.py` and
`TestHandlePlainMessage` / `TestHandleStopCommand` / `TestHandleModelCommand`
in `test_telegram_channel.py` will go green.
