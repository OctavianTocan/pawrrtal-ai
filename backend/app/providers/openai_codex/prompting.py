"""Prompt selection helpers for native Codex turns."""

from __future__ import annotations

import re

_WORKSPACE_REQUEST_HINTS = frozenset(
    {
        "backend",
        "bug",
        "cli",
        "code",
        "commit",
        "database",
        "db",
        "debug",
        "deploy",
        "error",
        "file",
        "fix",
        "frontend",
        "implement",
        "log",
        "logs",
        "pr",
        "repo",
        "server",
        "service",
        "sqlite",
        "telegram",
        "test",
        "workspace",
    }
)

_LIGHTWEIGHT_PROMPT_MAX_CHARS = 180

CODEX_DEVELOPER_INSTRUCTIONS = """
You are running inside Pawrrtal as a chat assistant.

Default behavior:
- For greetings, simple questions, status checks, and casual Telegram-style
  messages, answer directly without inspecting files or running commands.
- Use the workspace only when the user explicitly asks for code, files,
  debugging, implementation, tests, repo state, or other local project work.
- Keep short conversational replies short.
""".strip()

CODEX_LIGHT_SYSTEM_PROMPT = """
You are Pawrrtal's Codex-backed chat assistant. Reply directly and briefly.
Do not inspect files, run commands, or discuss internal execution unless the
user explicitly asks for project, code, debugging, or workspace work.
""".strip()


def should_use_lightweight_codex_prompt(question: str) -> bool:
    """Return True when a Codex turn should avoid full workspace context."""
    normalized = " ".join(question.lower().split())
    if not normalized:
        return True
    if len(normalized) > _LIGHTWEIGHT_PROMPT_MAX_CHARS:
        return False
    words = set(re.findall(r"[a-z0-9_+-]+", normalized))
    return not bool(words & _WORKSPACE_REQUEST_HINTS)
