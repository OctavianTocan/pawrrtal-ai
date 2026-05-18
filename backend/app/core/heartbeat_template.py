"""Workspace template for ``HEARTBEAT.md``.

Lives in its own module so ``app.core.workspace`` stays under the
project's 500-line file budget. The string is part of the workspace
seeder's contract — every new workspace gets this content as its
initial ``HEARTBEAT.md`` (idempotent: existing files are preserved).

Exported as a public name (no leading underscore) per the python-module-privacy
rule, since ``app.core.workspace`` is the cross-module consumer.
"""

from __future__ import annotations

HEARTBEAT_MD = """\
---
# Heartbeat checks for this workspace.
#
# Each entry is a periodic background turn that the scheduler fires
# on its cron expression. The agent runs the `prompt` and the result
# lands in your "🫀 Heartbeat" conversation (auto-created on first
# sync) plus, when you've linked Telegram, your Telegram chat.
#
# Sync changes to this file with: POST /api/v1/heartbeat/sync.
checks:
  - name: pulse
    cron: "0 9 * * *"
    prompt: |
      Daily heartbeat: summarise anything from the last 24 hours
      that needs my attention.
---

# Heartbeat

Edit the YAML front matter above to change cadences or add checks.
The body of this file is free-form context the agent reads alongside
the prompt — useful for project-specific instructions ("when checking
email, ignore anything from <vendor>", etc.).
"""
