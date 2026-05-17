---
# pawrrtal-dzp2
title: Onboarding redesign — 4-step workspace flow gated by 'New workspace'
status: completed
type: feature
priority: high
created_at: 2026-05-04T21:23:27Z
updated_at: 2026-05-04T21:37:56Z
---

Replace the current always-on onboarding modal with a 4-step flow that only opens when the user clicks "New workspace" from the workspace selector.

## Steps (per reference screenshots)
1. Let's get to know you — name, company website, LinkedIn, role, what to accomplish (chips).
2. Let's give Goose some context about you — open ChatGPT button + paste-context textarea + skip.
3. How should Goose communicate? — personality picker (Goose / Sharp Co-worker / Honest Coach / Thorough Analyst / Relentless Executor).
4. Connect Messaging — Slack / Telegram / WhatsApp / iMessage rows with Connect buttons + Continue.

## Wiring
- Move the existing OnboardingModal to render only when invoked from "New Workspace" in WorkspaceSelector
- Reuse current background + modal shell
- Personality choice in step 3 should later become the system-prompt addition for agents — for now persist the answers (localStorage) and surface them in the Personalization section of Settings (so the same fields appear there).

## Acceptance
- Onboarding does not show on every page load.
- Triggered from workspace selector → 4-step flow → close.
- Personalization section in /settings reads/writes the same data.

Done — gated existing modal behind workspace selector by removing always-on instance from (app)/page.tsx, and replaced 3-step OnboardingModal with new 4-step OnboardingFlow (Identity → Context → Personality → Connect Messaging). Profile persists to pawrrtal:personalization localStorage and is round-tripped by the Settings → Personalization section.
