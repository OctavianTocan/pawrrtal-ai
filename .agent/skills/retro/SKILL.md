---
name: retro
description: Turn a bad or long Pawrrtal work session into durable project learning. Use when the user says $retro, asks to learn from a session, says too much went wrong, or asks to create/update skills or rules from recent failures.
---

# Retro

Use this when the user wants the project to learn from a messy session. The goal is not a report; the goal is to change the next agent's behavior.

## Process

1. **Extract incidents from evidence.** Use the current thread, git diff, PR state, logs, and commands. Do not rely on vibes or blame.
   - If `.agent/skills/retro/scripts/collect-codex-retro-context.py` is missing, use the current conversation as primary evidence and run `/root/.agent/skills/retro/scripts/collect-codex-retro-context.py` when available.
2. **Name each failure mode.** Phrase it as an action that should happen next time, such as "prove live Telegram with real delivery before claiming it works."
3. **Choose the durable artifact.**
   - Repeated workflow mistake: create or update a skill.
   - Repo-wide rule: update `AGENTS.md` or a `.claude/rules/**` file.
   - Product/code task: create a bean with the `beans` CLI.
   - One-off fact that should be remembered across sessions: write a Codex memory note only when the user explicitly asked to remember it.
4. **Prefer small skills over one giant policy.** A skill should trigger for a specific situation and fit in one context read.
5. **Add verification to every skill.** The skill must say what evidence proves the agent followed it.
6. **Reference project skills from `AGENTS.md`.** Future agents should discover them without guessing names.
7. **Validate metadata.** Every skill description must include clear "Use when..." triggers and stay under 1024 characters.

## Incident Patterns To Capture

| Pattern | Durable Fix |
| --- | --- |
| Long-running goal drifts into a tiny PR | Add a scope-audit skill that maps requirements to commits, runtime work, PR diff, and missing items. |
| "Works" claimed from a simulation only | Add live-ops verification requiring real browser/channel/provider proof. |
| CI runners consume the wrong disk or wrong trust model | Add runner-ops instructions covering placement, labels, actor gates, and cleanup. |
| Generic core gets provider/channel/tool details | Add extension-boundary instructions and tests at the interface. |
| Secrets or credentials could leak in logs | Add redaction and "do not print" rules to the relevant operational skill. |
| The user asks "why" after a failure | Answer from current evidence first, then make the durable fix. |

## Output

When done, report:

- Skills/rules added or changed.
- Which incident each artifact prevents.
- Validation run.
- Anything intentionally left for a follow-up bean or PR.
