"""Bash directory-boundary parser for the ``can_use_tool`` gate.

Ported from claude-code-telegram (``src/claude/monitor.py:61-142``)
and kept as a pure function module so it can be exercised by unit
tests without touching the agent loop or the Claude SDK.

What it does
------------
Given a bash command string, the working directory it would execute
in, and the workspace-root sandbox, decide whether the command stays
inside the sandbox or breaks out (``rm /etc/passwd``,
``cp foo ../../private``, ``find / -delete``, …).

Approach
--------
1. ``shlex.split`` the command.  If the command can't be parsed
   (mismatched quotes, etc.) we let it through — the operating
   system / Claude SDK sandbox is the real backstop.  The boundary
   check is best-effort static analysis on the way in.
2. Split the token stream by the bash command separators
   (``&&``, ``||``, ``;``, ``|``, ``&``) so each "real" command in a
   pipeline / chain is validated independently — a denied command
   inside a chain blocks the whole chain.
3. Classify each sub-command's base name:
   * ``_READ_ONLY_COMMANDS`` (``ls``, ``cat``, ``echo``, …) always pass.
   * ``find`` passes unless an action like ``-delete``/``-exec`` is
     present — those make it FS-modifying.
   * ``_FS_MODIFYING_COMMANDS`` (``rm``, ``cp``, ``mv``, ``cd``, …)
     trigger a per-argument boundary check.
4. For each non-flag argument of a FS-modifying command, resolve the
   path relative to the working directory and confirm it stays inside
   the approved workspace root.  ``-delete`` / ``-exec`` arguments
   to ``find`` get the same treatment.

Why pure / synchronous
----------------------
The agent loop calls this from a permission hook that runs on the
hot path before every tool execution.  A subprocess call or async
I/O would balloon the per-turn budget.  Pure ``shlex`` + ``pathlib``
walks finish in microseconds even on long commands.

Limitations (documented, not bugs)
----------------------------------
* We don't expand ``$VARS`` — a command that uses environment
  expansion to bypass the check escapes the static analyzer, but
  the OS-level sandbox (PR 05's ``ClaudeAgentOptions.sandbox``) and
  the workspace's filesystem permissions still apply.
* Bash builtins / pipelines that move state through stdout (e.g.
  ``echo /etc/passwd > target``) bypass per-argument checks; the
  redirection ``>`` is treated as a separator, so the right-hand
  side becomes its own pseudo-command and its argument IS checked.
"""

from __future__ import annotations

import shlex
from pathlib import Path

# Commands that modify the filesystem or change shell context.
# Any non-flag argument is path-validated.
_FS_MODIFYING_COMMANDS: frozenset[str] = frozenset(
    {
        "mkdir",
        "touch",
        "cp",
        "mv",
        "rm",
        "rmdir",
        "ln",
        "install",
        "tee",
        "cd",
    }
)

# Commands that only read or print — never path-checked.
_READ_ONLY_COMMANDS: frozenset[str] = frozenset(
    {
        "cat",
        "ls",
        "head",
        "tail",
        "less",
        "more",
        "which",
        "whoami",
        "pwd",
        "echo",
        "printf",
        "env",
        "printenv",
        "date",
        "wc",
        "sort",
        "uniq",
        "diff",
        "file",
        "stat",
        "du",
        "df",
        "tree",
        "realpath",
        "dirname",
        "basename",
    }
)

# Actions / expressions that make ``find`` FS-modifying.
_FIND_MUTATING_ACTIONS: frozenset[str] = frozenset(
    {"-delete", "-exec", "-execdir", "-ok", "-okdir"}
)

# Shell command separators we split on.
_COMMAND_SEPARATORS: frozenset[str] = frozenset({"&&", "||", ";", "|", "&"})


def check_bash_directory_boundary(
    command: str,
    working_directory: Path,
    approved_directory: Path,
) -> tuple[bool, str | None]:
    """Return ``(allowed, reason_if_denied)`` for ``command``.

    Args:
        command: The exact bash command string the agent wants to run.
        working_directory: Directory the command would execute in.
        approved_directory: Workspace root the command must stay in.

    Returns:
        Tuple of ``(True, None)`` when every FS-modifying argument
        resolves inside ``approved_directory``; otherwise
        ``(False, reason)`` with a human-readable reason suitable for
        surfacing to the agent as a tool-error message.

        When the command can't be parsed (mismatched quotes,
        ``shlex`` raises ``ValueError``) the function returns
        ``(True, None)`` — the OS / SDK sandbox is the backstop.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return True, None

    if not tokens:
        return True, None

    command_chains = _split_command_chains(tokens)
    resolved_approved = approved_directory.resolve()

    for chain in command_chains:
        if not chain:
            continue
        denied_reason = _check_single_chain(chain, working_directory, resolved_approved)
        if denied_reason is not None:
            return False, denied_reason

    return True, None


def _split_command_chains(tokens: list[str]) -> list[list[str]]:
    """Split a flat token list on bash separators into per-command lists."""
    chains: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in _COMMAND_SEPARATORS:
            if current:
                chains.append(current)
            current = []
            continue
        current.append(token)
    if current:
        chains.append(current)
    return chains


def _check_single_chain(
    chain: list[str],
    working_directory: Path,
    resolved_approved: Path,
) -> str | None:
    """Return a denial reason for ``chain`` or ``None`` to allow it."""
    base_command = Path(chain[0]).name

    if base_command in _READ_ONLY_COMMANDS:
        return None

    if base_command == "find":
        if not any(token in _FIND_MUTATING_ACTIONS for token in chain[1:]):
            return None
    elif base_command not in _FS_MODIFYING_COMMANDS:
        return None

    for token in chain[1:]:
        if token.startswith("-"):
            continue
        denial = _check_path_token(token, base_command, working_directory, resolved_approved)
        if denial is not None:
            return denial
    return None


def _check_path_token(
    token: str,
    base_command: str,
    working_directory: Path,
    resolved_approved: Path,
) -> str | None:
    """Resolve a single argument and verify it stays inside the workspace."""
    try:
        if token.startswith("/"):
            resolved = Path(token).resolve()
        else:
            resolved = (working_directory / token).resolve()
    except (ValueError, OSError):
        # If we can't resolve the path, defer to the OS-level sandbox.
        return None

    if _is_within_directory(resolved, resolved_approved):
        return None
    return (
        f"Directory boundary violation: '{base_command}' targets "
        f"'{token}' which is outside the workspace root "
        f"'{resolved_approved}'."
    )


def _is_within_directory(path: Path, directory: Path) -> bool:
    """``True`` when ``path`` is the same as ``directory`` or under it."""
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True
