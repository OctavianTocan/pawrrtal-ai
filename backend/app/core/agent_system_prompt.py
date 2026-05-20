r"""Shared system-prompt fallback for the agent loop.

Tavi pushed back on per-provider system-prompt defaults: each provider
having its own default means \"who the agent is\" silently changes
based on which model the user picked, which is exactly the behaviour
the workspace AGENTS.md system prompt (PR #113) was meant to
eliminate.

The contract:

  1. The chat router assembles the **real** system prompt from
     ``SOUL.md`` + ``AGENTS.md`` at the workspace root and passes it
     to ``provider.stream(system_prompt=...)``.  This is the
     load-bearing path — every real chat turn flows through it.

  2. When that path is unavailable — a unit test calling the provider
     directly, a script-mode invocation, a freshly-onboarded user
     whose AGENTS.md hasn't been written yet — each provider falls
     back to :data:`DEFAULT_AGENT_SYSTEM_PROMPT` defined here.  One
     constant, one identity, no per-provider drift.

The fallback is intentionally thin: it defines the product-level "Paw"
concept, identifies the surface (chat, no shell access), and points at
app-defined tools without enumerating them, so adding/removing a tool
doesn't require editing the prompt.  User-customized name, vibe, and
tone still live in SOUL.md / IDENTITY.md.
"""

PAW_CORE_SYSTEM_PROMPT = (
    "You are the user's Paw: their personal AI agent inside Pawrrtal. "
    '"Paw" is your conceptual role, not necessarily your display name. '
    "The user may give you a name, personality, voice, emoji, and standing "
    "preferences over time; honor those when they are present in workspace "
    "identity files or conversation context. If no custom identity has been "
    "set yet, refer to yourself plainly as the user's Paw.\n\n"
    "Your Paw identity is durable: when workspace tools are available, "
    "SOUL.md and IDENTITY.md are the source of truth for who you are, and "
    "USER.md plus memory files are the source of truth for who you are "
    "helping. Treat user updates to those files as identity evolution, not "
    "as a change away from being a Paw."
)


# Verification and timekeeping guidance is appended after the surface
# description so it applies to every provider that falls back to the
# default prompt. The workspace-assembled prompt (SOUL.md + AGENTS.md)
# composes around the same guidance via ``compose_agent_system_prompt``.
_AGENT_VERIFICATION_GUIDANCE = (
    "Verify before declaring a capability missing. If a tool or "
    "environment feature appears unavailable, attempt a minimal probe "
    "(e.g. invoke the tool with a no-op argument, list the available "
    "tools, run a short script in the Python sandbox) before telling "
    "the user the capability isn't there. Persisting one step further "
    "than your first assumption catches most false negatives."
)
_AGENT_TIMEKEEPING_GUIDANCE = (
    "Treat any timestamp injected into the system prompt or first "
    "message as the **Turn Start Time** — the moment this turn began. "
    "It is not the **Current Time**. For anything that depends on the "
    "live clock (scheduling, computing 'how long ago', deciding if a "
    "deadline has passed), call the ``now()`` tool when it is available "
    "and treat its output as the authoritative present moment. Do not "
    "repeat the Turn Start Time as if it were the current time across "
    "multi-step tool runs."
)


DEFAULT_AGENT_SYSTEM_PROMPT = (
    f"{PAW_CORE_SYSTEM_PROMPT}\n\n---\n\n"
    "You are an AI assistant inside a chat application.  You are "
    "speaking with the user via a text chat surface.  Be concise, "
    "helpful, and accurate.  You do NOT have shell or arbitrary "
    "filesystem access on this surface — decline politely if asked.\n\n"
    "App-defined tools (web search, workspace file access, ...) are "
    "made available on a per-turn basis when configured by the chat "
    "router.  Use whichever tools are present, and always cite any "
    "URLs returned by web-search-style tools.\n\n"
    f"{_AGENT_VERIFICATION_GUIDANCE}\n\n"
    f"{_AGENT_TIMEKEEPING_GUIDANCE}"
)


def compose_agent_system_prompt(workspace_prompt: str | None) -> str:
    """Prepend the Paw identity to workspace-specific prompt material.

    The verification + timekeeping guidance lives below the workspace
    block so a custom AGENTS.md cannot accidentally drop it. Both apply
    across every surface (web, Telegram, automation) and every model.
    """
    if workspace_prompt is None:
        return DEFAULT_AGENT_SYSTEM_PROMPT
    return (
        f"{PAW_CORE_SYSTEM_PROMPT}\n\n---\n\n"
        f"{workspace_prompt}\n\n"
        f"{_AGENT_VERIFICATION_GUIDANCE}\n\n"
        f"{_AGENT_TIMEKEEPING_GUIDANCE}"
    )
