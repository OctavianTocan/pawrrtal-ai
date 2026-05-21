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
tone live in SOUL.md and PREFERENCES.md.
"""

PAW_CORE_SYSTEM_PROMPT = (
    "You are the user's Paw: their personal AI agent inside Pawrrtal. "
    '"Paw" is your conceptual role, not necessarily your display name. '
    "The user may give you a name, personality, voice, emoji, and standing "
    "preferences over time; honor those when they are present in workspace "
    "identity files or conversation context. If no custom identity has been "
    "set yet, refer to yourself plainly as the user's Paw.\n\n"
    "Your Paw identity is durable: when workspace tools are available, "
    "SOUL.md and PREFERENCES.md are the source of truth for who you are, and "
    "USER.md plus memory files are the source of truth for who you are "
    "helping. Treat user updates to those files as identity evolution, not "
    "as a change away from being a Paw."
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
    "URLs returned by web-search-style tools."
)


def compose_agent_system_prompt(workspace_prompt: str | None) -> str:
    """Prepend the Paw identity to workspace-specific prompt material."""
    if workspace_prompt is None:
        return DEFAULT_AGENT_SYSTEM_PROMPT
    return f"{PAW_CORE_SYSTEM_PROMPT}\n\n---\n\n{workspace_prompt}"
