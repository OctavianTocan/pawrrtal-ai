---
name: workspace-context
description: "Use when Pawrrtal local dev, auth, deployment routing, or domain vocabulary questions come up during a task. Read memory/semantic/DOMAIN_KNOWLEDGE.md first; this skill adds task-triggered pointers to domain-effect and live-ops."
---

# Workspace context

**Read first:** `.agent/memory/semantic/DOMAIN_KNOWLEDGE.md` (ports, commands, auth, deploy, Effect summary).

**Personal taste:** `.agent/memory/personal/PREFERENCES.md`.

This skill is a **task trigger** — load it when you're about to touch dev URLs, auth flows, or deployment routing and want a fast checklist without re-deriving facts from code.

## Quick checklist

| Question | Answer lives in |
|----------|-----------------|
| What port is X on? | DOMAIN_KNOWLEDGE § Local development |
| What does "Projects" mean? | DOMAIN_KNOWLEDGE § Domain vocabulary |
| Login redirect race | DOMAIN_KNOWLEDGE § Auth |
| Cloudflared vs Tailscale | DOMAIN_KNOWLEDGE § Production routing |
| Effect package layout | DOMAIN_KNOWLEDGE § Effect TS → `domain-effect` skill |
| 003 migration rules | `specs/003-pawrrtal-overhaul/plan.md` |

## Related skills

| Skill | When |
|-------|------|
| `domain-effect` | Writing/reviewing `backend-ts/` |
| `live-ops` | Proving live deploy, Telegram, shutdown |
| `repo-operations` | Git, beans, multi-agent |
| `paw` | E2E via CLI |

Do not duplicate DOMAIN_KNOWLEDGE or PREFERENCES here — update those files when facts or taste change.
