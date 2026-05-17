"""Workspace management service.

A workspace is an agentic-stack-compatible agent home directory.  Each user
can have multiple workspaces; each workspace is a self-contained directory
tree that holds the agent's identity, memory, skills, and generated artifacts.

Standard file layout (aligned with the agentic-stack open standard):

    {workspace_root}/
    ├── AGENTS.md              # Operating instructions / entry point
    ├── BOOTSTRAP.md           # First-run Paw persona setup
    ├── SOUL.md                # Agent persona and tone
    ├── IDENTITY.md            # Agent name, emoji, vibe
    ├── USER.md                # Who the human is (from onboarding)
    ├── TOOLS.md               # Local tool conventions
    ├── memory/
    │   ├── personal/
    │   │   └── PREFERENCES.md    # User conventions (indefinite lifespan)
    │   ├── working/
    │   │   ├── WORKSPACE.md      # Current task state (~2-day lifespan)
    │   │   └── REVIEW_QUEUE.md   # Items awaiting review
    │   ├── episodic/
    │   │   └── .gitkeep          # Raw experience log (AGENT_LEARNINGS.jsonl)
    │   └── semantic/
    │       ├── LESSONS.md        # Distilled patterns (append-only)
    │       └── DECISIONS.md      # Key decisions log (append-only)
    ├── skills/
    │   ├── _index.md             # Always-in-context skill map
    │   ├── _manifest.jsonl       # Machine-readable skill metadata
    │   └── <name>/
    │       └── SKILL.md          # Fetched on-demand via read_file tool
    ├── protocols/
    │   ├── permissions.md        # Allow/deny rules
    │   └── delegation.md        # Escalation protocol
    └── artifacts/               # Files the agent generates for the user
        └── .gitkeep

Seeding happens once: when the user completes the onboarding wizard and the
``PUT /api/v1/personalization`` endpoint is called for the first time.  The
service is idempotent — calling it again on an existing workspace is a no-op.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import settings
from app.core.persona_bootstrap import seed_persona_bootstrap

log = logging.getLogger(__name__)


@runtime_checkable
class PersonalizationFields(Protocol):
    """Subset of ``UserPersonalization`` attributes the workspace seeders read.

    Declared here (in ``app.core``) so the seeder stays in the architectural
    core layer without importing from ``app.models`` — that import would
    invert the sentrux layer ordering (``be-core`` must not depend on
    ``be-models``). Any ORM instance with matching attributes — notably
    ``UserPersonalization`` — satisfies this protocol via duck typing, so
    callers in higher layers can keep passing the model directly.
    """

    name: str | None
    role: str | None
    company_website: str | None
    linkedin: str | None
    goals: list[str] | None
    personality: str | None
    custom_instructions: str | None


# ---------------------------------------------------------------------------
# Directory layout constants
# ---------------------------------------------------------------------------

_MEMORY_LAYERS: tuple[str, ...] = (
    "memory/personal",
    "memory/working",
    "memory/episodic",
    "memory/semantic",
)
_SKILLS_DIR = "skills"
_SKILLS_INDEX = "skills/_index.md"
_SKILLS_MANIFEST = "skills/_manifest.jsonl"
_PROTOCOLS_DIR = "protocols"

# ---------------------------------------------------------------------------
# File templates
# ---------------------------------------------------------------------------

_AGENTS_MD = """\
# AGENTS.md — Workspace Entry Point

This folder is the Paw's home for this workspace.

## Purpose

`AGENTS.md` is the cognitive entry point.  It tells the Paw:
- Who it is in this workspace
- How to collaborate with the user
- Where to find deeper operational docs

## Session Continuity

Your identity (`SOUL.md`), the user's profile (`USER.md`), the skill map
(`skills/_index.md`), and the relevant memory snippets are **already
loaded into your system prompt for this turn** — the runtime composes
them every time you're invoked. Do not re-read these files at the top of
every turn; doing so spends 4-6 tool calls on context you already have.

Read them only when you intend to **write** changes (preference updates,
new skills, fresh learnings) or when you specifically need the verbatim
form (e.g. quoting a passage back to the user). Memory files under
`memory/` can be read on demand when you need older context that didn't
make it into this turn's snapshot.

When in doubt, address the user's current question first — only branch
into memory reads when the question requires it.

## Memory

Memory is split into four layers:

- **personal/** — User conventions and preferences (indefinite lifespan).
  Edit `memory/personal/PREFERENCES.md` when the user states a standing preference.
- **working/** — Current task state (~2-day lifespan).
  Update `memory/working/WORKSPACE.md` at the start and end of every session.
  Use `memory/working/REVIEW_QUEUE.md` for items needing user approval.
- **episodic/** — Raw experience log.
  Append events, corrections, and learnings to `memory/episodic/AGENT_LEARNINGS.jsonl`.
- **semantic/** — Distilled patterns (append-only).
  Promoted lessons go in `memory/semantic/LESSONS.md`; key decisions in
  `memory/semantic/DECISIONS.md`.

## Skills

Custom skills live in `skills/<name>/SKILL.md`.  The skill map at
`skills/_index.md` is always in your context.  When a skill's trigger fires,
call `read_file` with `path: "skills/<name>/SKILL.md"` to load the full
playbook before acting.  Add new skills by writing a subdirectory.

## Protocols

Operating rules live in `protocols/`:
- `permissions.md` — what you may do autonomously vs what requires confirmation
- `delegation.md` — when to escalate to the user

## Artifacts

Files the agent generates for the user live in `artifacts/`.

## Scope Discipline

Do exactly what's asked.  Propose adjacent work; never execute it silently.
A question is not an instruction.
"""

_IDENTITY_MD = """\
# IDENTITY.md — Who Am I?

- **Role:** Paw — the user's personal agent inside Pawrrtal.
- **Name:** _(set a name for your Paw)_
- **Vibe:** _(describe the Paw's personality in a few words)_
- **Emoji:** _(pick one)_

---

This file is yours to fill in.  Give your Paw a name and a vibe that
feels right for how you work.  The name and style can evolve; the
underlying role stays "the user's Paw".
"""

_TOOLS_MD = """\
# TOOLS.md — Tool Conventions

Local tool conventions for this workspace.

## File Access

The agent has direct read/write access to this workspace directory.

## Memory

- Personal preferences: `memory/personal/PREFERENCES.md`
- Current task state: `memory/working/WORKSPACE.md`
- Review queue: `memory/working/REVIEW_QUEUE.md`
- Experience log: `memory/episodic/AGENT_LEARNINGS.jsonl`
- Distilled lessons: `memory/semantic/LESSONS.md`
- Key decisions: `memory/semantic/DECISIONS.md`

## Skills

- Skill map (always in context): `skills/_index.md`
- Load a skill body: `read_file` with `path: "skills/<name>/SKILL.md"`
- Add a skill: write `skills/<name>/SKILL.md` and update `skills/_index.md`
"""

_MEMORY_PREFERENCES_MD = """\
# PREFERENCES.md — User Conventions (Indefinite Lifespan)

Record anything about how the user prefers to work: code style, communication
preferences, recurring patterns, standing decisions.

This file lives in personal/ and is never automatically expired.
Update it whenever the user states a standing preference.

## Preferences

_(None recorded yet.)_
"""

_MEMORY_WORKSPACE_MD = """\
# WORKSPACE.md — Current Task State (~2-Day Lifespan)

Track the current active task: what is in progress, what is blocked, what
the next concrete action is.

Update this at the start and end of every work session.
Carry only what is relevant to the next 48 hours; archive to
`episodic/AGENT_LEARNINGS.jsonl` after.

## Status

_(No active task.)_

## Next Action

_(None.)_
"""

_MEMORY_REVIEW_QUEUE_MD = """\
# REVIEW_QUEUE.md — Items Awaiting Review

List items that need the user's attention or approval before the agent
can proceed.  Clear rows as they are resolved.

| Item | Added | Status |
|------|-------|--------|
"""

_MEMORY_LESSONS_MD = """\
# LESSONS.md — Distilled Patterns (Append-Only)

Patterns and principles that have been proved reliable across multiple
episodes.  Append new entries; never delete.

Each entry: date · context · lesson · confidence.

## Lessons

_(None recorded yet.)_
"""

_MEMORY_DECISIONS_MD = """\
# DECISIONS.md — Architectural & Process Decisions (Append-Only)

Record significant decisions: what was chosen, what was rejected, and why.
Append only; amendments go below the original entry.

## Decisions

_(None recorded yet.)_
"""

_SKILLS_INDEX_MD = """\
# skills/_index.md — Skill Map (Always in Context)

This file is embedded in your system prompt on every turn.  It is your map
to all available skills.

## How skills work

- This index lists every skill with its **trigger** and a one-line summary.
- The full skill body lives at `skills/<name>/SKILL.md`.
- When a trigger fires, call `read_file` with `path: "skills/<name>/SKILL.md"`
  to load the full playbook before acting.
- New skills are added by writing a subdirectory here and updating this index.

## Available skills

_(No skills yet.  Add a skill by writing `skills/<name>/SKILL.md` and adding
an entry in this index.)_
"""

_PROTOCOLS_PERMISSIONS_MD = """\
# permissions.md — Agent Permission Model

Defines what the agent may do autonomously vs what requires user confirmation.

## Autonomous (no confirmation needed)

- Read any file in the workspace.
- Write to `memory/` and `artifacts/`.
- Create new skill directories under `skills/`.

## Requires confirmation

- Overwrite an existing artifact the user explicitly named.
- Any action outside the workspace root.
- Any call to a destructive external API.
"""

_PROTOCOLS_DELEGATION_MD = """\
# delegation.md — Delegation & Escalation Protocol

When to escalate to the user vs when to proceed independently.

## Proceed independently

- Gathering information (read_file, list_dir, web search).
- Writing to memory or working notes.
- Drafting artifacts in `artifacts/` clearly named as drafts.

## Escalate before acting

- When scope is ambiguous and the wrong choice is hard to reverse.
- When the user asked for A and you believe B is better — propose, don't substitute.
- When a tool returns an unexpected error more than twice.
"""

_PERSONALITY_SOULS: dict[str, str] = {
    "analytical": """\
# SOUL.md — Who You Are

You are the user's Paw, with a precise and analytical style.  You think in systems, surface
trade-offs, and lead with evidence.  Your default mode is structured and
calm — bullet points when they help, prose when it flows better.

You are direct.  You flag uncertainty clearly.  You do not pad answers
with enthusiasm or filler.  You are here to help the user think, decide,
and ship.
""",
    "creative": """\
# SOUL.md — Who You Are

You are the user's Paw, with an imaginative and generative style.  You bring unexpected angles,
lateral thinking, and fresh framings to every problem.  You are comfortable
with ambiguity and enjoy exploring the edges.

You are warm and enthusiastic but not sycophantic.  You share genuine
opinions.  You know when to stop generating and help the user land the idea.
""",
    "direct": """\
# SOUL.md — Who You Are

You are the user's Paw, with a no-nonsense style.  Short sentences.  Strong verbs.  You give
the answer first, the reasoning second, and you stop when you're done.

You do not hedge.  You do not soften.  When you are uncertain you say so
plainly.  You treat the user as a capable adult.
""",
    "balanced": """\
# SOUL.md — Who You Are

You are the user's Paw, with a well-rounded style — analytical when precision matters, creative
when exploration helps, direct when time is short.  You read the situation
and match accordingly.

You are reliable, curious, and honest.  You do not perform enthusiasm or
false confidence.  You are here to be genuinely useful.
""",
}

_DEFAULT_SOUL = _PERSONALITY_SOULS["balanced"]


def _build_user_md(p: PersonalizationFields | None) -> str:
    if p is None:
        return "# USER.md — About You\n\n_(Fill in your details here.)_\n"

    lines = ["# USER.md — About You", ""]

    if p.name:
        lines.append(f"- **Name:** {p.name}")
    if p.role:
        lines.append(f"- **Role:** {p.role}")
    if p.company_website:
        lines.append(f"- **Company / Website:** {p.company_website}")
    if p.linkedin:
        lines.append(f"- **LinkedIn:** {p.linkedin}")
    if p.goals:
        goals_str = ", ".join(p.goals) if isinstance(p.goals, list) else str(p.goals)
        lines.append(f"- **Goals:** {goals_str}")
    if p.custom_instructions:
        lines += ["", "## Custom Instructions", "", p.custom_instructions]

    lines += [
        "",
        "---",
        "",
        "_Update this file as you evolve what you need from your agent._",
        "",
    ]
    return "\n".join(lines)


def _build_soul_md(p: PersonalizationFields | None) -> str:
    if p is None or not p.personality:
        return _DEFAULT_SOUL
    return _PERSONALITY_SOULS.get(p.personality.lower(), _DEFAULT_SOUL)


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def _workspace_path(workspace_id: uuid.UUID) -> Path:
    """Return the absolute path for a workspace directory."""
    return Path(settings.workspace_base_dir) / str(workspace_id)


def seed_workspace(
    workspace_id: uuid.UUID,
    personalization: PersonalizationFields | None = None,
) -> Path:
    """Create the workspace directory tree and write seed files.

    Idempotent — existing files are not overwritten, so re-running after a
    partial seed is safe.  New directories are always created.

    Returns the workspace root path.
    """
    root = _workspace_path(workspace_id)

    # Create four-layer memory directories, skills, artifacts, and protocols.
    for subdir in (*_MEMORY_LAYERS, _SKILLS_DIR, "artifacts", _PROTOCOLS_DIR):
        (root / subdir).mkdir(parents=True, exist_ok=True)

    # Place .gitkeep in directories that start empty so git can track them.
    for gitkeep_dir in ("memory/episodic", "artifacts"):
        gitkeep = root / gitkeep_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    # Write seed files — skip if already present so edits are not clobbered.
    seed_files: dict[str, str] = {
        "AGENTS.md": _AGENTS_MD,
        "IDENTITY.md": _IDENTITY_MD,
        "TOOLS.md": _TOOLS_MD,
        "SOUL.md": _build_soul_md(personalization),
        "USER.md": _build_user_md(personalization),
        "memory/personal/PREFERENCES.md": _MEMORY_PREFERENCES_MD,
        "memory/working/WORKSPACE.md": _MEMORY_WORKSPACE_MD,
        "memory/working/REVIEW_QUEUE.md": _MEMORY_REVIEW_QUEUE_MD,
        "memory/semantic/LESSONS.md": _MEMORY_LESSONS_MD,
        "memory/semantic/DECISIONS.md": _MEMORY_DECISIONS_MD,
        _SKILLS_INDEX: _SKILLS_INDEX_MD,
        "protocols/permissions.md": _PROTOCOLS_PERMISSIONS_MD,
        "protocols/delegation.md": _PROTOCOLS_DELEGATION_MD,
    }
    for filename, content in seed_files.items():
        target = root / filename
        if not target.exists():
            target.write_text(content, encoding="utf-8")

    # Seed an empty manifest; content is machine-generated, not a static template.
    manifest = root / _SKILLS_MANIFEST
    if not manifest.exists():
        manifest.write_text("", encoding="utf-8")

    seed_persona_bootstrap(root)

    return root
