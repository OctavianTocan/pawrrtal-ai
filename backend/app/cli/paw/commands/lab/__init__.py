"""Experimental ``paw lab`` command group."""

from __future__ import annotations

# <skill-gen>
# ---
# name: paw
# description: Pawrrtal Agent CLI. Use when you need to test the backend end-to-end as a real user -- auth, workspaces, chat with SSE streaming, conversation CRUD, provider verification. Prefer this over importing `app.*` modules in ad-hoc Python scripts; `paw` exercises the same HTTP surface the React frontend uses, so any bug visible in the UI is visible to `paw`.
# ---
#
# ## Benchmarks and dogfood flows
#
# ```bash
# just paw lab bench model --model google-ai:google/gemini-3.5-flash --prompt "hello" --runs 3 --json
# just paw lab bench providers --runs 1 --json
# just paw lab telegram chat --model google-ai:google/gemini-3.5-flash --turns /tmp/telegram-turns.txt --new --verbose 2 --json
# just paw lab telegram media --model google-ai:google/gemini-3.5-flash --text "describe and transcribe" --image /tmp/sample.jpg --voice-note /tmp/sample.ogg --voice-duration 4 --new --json
# just paw lab runs ls --json
# just paw lab runs review RUN_ID --question "What should feel cleaner before we ship this?"
# just paw lab flows show backend-cli-coverage
# just paw lab flows show telegram-polish-loop
# ```
#
# Lab commands write profile-scoped JSON run logs under
# `<PAW_CONFIG_DIR>/<profile>/lab/runs/`. Use `backend-cli-coverage` to inspect
# which backend route families have a first-class Paw command, verify suite,
# lab flow, or explicit `paw api` fallback. Use `telegram-polish-loop` before
# generalizing Telegram feedback into `taste`, `DESIGN.md`, or another flow.
# </skill-gen>

__all__ = ["app"]


def __getattr__(name: str) -> object:
    """Load the Typer app lazily so flow helpers do not import bench providers."""
    if name == "app":
        from .cli import app  # noqa: PLC0415

        return app
    raise AttributeError(name)
