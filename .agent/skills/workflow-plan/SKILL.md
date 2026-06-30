---
name: workflow-plan
description: "Use when planning creative, ambiguous, or multi-step work: new features, components, behavior changes, refactors, or any task whose requirements need clarifying before implementation."
---

# Workflow: Plan

Phase 1 locks intent with the user. Phases 2-6 break the work into steps, dispatch one sub-agent per step, compose an overall plan, critic-review it, and save.

References: `references/writing-plans.md` (format conventions), `references/step-planner-prompt.md` (Phase 3 sub-agent prompt), `references/critic-prompt.md` (Phase 5 critic prompt).

## Process

```
┌──────────────────────────────────────────────────────────────────┐
│                     CENTRAL PLAN AGENT                           │
│                                                                  │
│  Phase 1  Brainstorm with user → .context/plans/brainstorm.md    │
│  Phase 2  Gather context, break into steps, decide ordering      │
│  Phase 3  Dispatch one step planner per step (parallel/seq)      │
│              └─▶ .context/plans/step-N-<name>.md                 │
│  Phase 4  Compose overall plan from step files                   │
│  Phase 5  Critic sub-agent → cross-step coherence                │
│  Phase 6  Address feedback, save to docs/plans/                  │
└──────────────────────────────────────────────────────────────────┘
```

**Modes.** *Warm handoff:* if `.context/plans/brainstorm.md` already exists, read it and skip Phase 1. *Cold start:* run Phase 1 to produce it. Either way, Phases 2-6 work identically.

## Phase 1: Brainstorm

The main agent talks to the user directly during the brainstorm. Do not delegate the user-intent interview; delegate only repo exploration that can run in parallel without deciding product intent.

**Hard gate.** Do not write code, scaffold projects, or invoke implementation skills until the brainstorm is approved. Every project, regardless of perceived simplicity — "simple" projects are where unexamined assumptions cause the most wasted work. The brainstorm can be short for trivial changes, but it must exist and be approved.

**Explore first.** Read the relevant codebase before asking anything. Identify existing patterns, files likely to change, related features, architectural constraints. Use Explore sub-agents for broader searches.

**Ask clarifying questions.** Interview until you reach shared understanding on scope, constraints, acceptance criteria, edge cases, and design.

- 3-5 questions per batch; batch unrelated questions together; only serialize when one answer shapes the next.
- Provide your recommended answer conversationally ("I'd lean toward X because Y — sound right?") so the user has something to react to.
- Keep probing across rounds — stop when all decisions are resolved, not at a question count.
- Scope check first: if the request is multiple independent subsystems, decompose into sub-projects, each with its own plan cycle.

**Save to `.context/plans/brainstorm.md`** (gitignored). Present the brainstorm in the active agent UI, iterate on feedback, repeat until approved. Use this template:

```markdown
# [Feature Name]

## What we're building
One paragraph — problem, what we're solving, why.

## Architectural context
Where in the stack this lives; packages and layers involved.
Include an ASCII diagram (box-drawing characters) for moderate or
complex changes. Skip or one-sentence it for trivial changes.

## Approach A: [Name]
Core idea. Optional ASCII diagram.
**Key files:** Create `path/new.ts` — purpose. Modify `path/existing.ts` — what.
**Trade-offs:** [pros/cons]

## Approach B: [Name]   (only if there is a real tradeoff)

## Recommendation
Which approach and why; or, single-approach, key design decisions.

## Out of scope
```

Present multiple approaches only when there is a genuine tradeoff. Otherwise, one approach.

**When to grill.** If the domain has dense terminology, conflicting concept names, or unresolved invariants, run `workflow-grill-with-docs` against the approved brainstorm before Phase 2 — it sharpens terminology and may capture ADRs you'd otherwise re-litigate later.

## Phase 2: Gather Context and Determine Steps

Read `.context/plans/brainstorm.md`, relevant skill files (`domain-effect`, `paw`, `domain-cli`, `extension-boundaries`, `skill-gen`, etc.), `AGENTS.md`, and the key source files the brainstorm names.

Break the work into steps. Granularity is your call — simple work → fewer larger steps, complex work → more smaller steps. Each step is one coherent unit a sub-agent can execute. Decide ordering: independent steps in parallel, dependent steps sequential so later sub-agents can read earlier step files.

## Phase 3: Dispatch Step Planner Sub-Agents

For each step, dispatch a planning sub-agent using the runtime's available subagent tool and `references/step-planner-prompt.md`. Each sub-agent writes `.context/plans/step-N-<name>.md` with exact paths, full code blocks, verification commands, commit messages, and a decomposition hint. Follow the model/tool rules in `AGENTS.md` when the runtime exposes those choices.

## Phase 4: Compose Overall Plan

Read all `step-N-*.md` files and compose the overall plan per the "Overall Plan Format" in `references/writing-plans.md`: goal, architecture (2-3 sentences), overview, packages & files affected (grouped by package, all steps), execution order with dependencies, and step summaries linking each detail file.

## Phase 5: Critic Pass

Dispatch a single critic sub-agent using `references/critic-prompt.md`. It checks cross-step coherence — conflicts, missing dependencies, ordering, gaps vs brainstorm, convention violations.

Serious issues (dependency errors, missing requirements) → re-dispatch affected step planners. Minor issues → fix directly. Cap at 3 iterations; surface remaining issues to the user.

## Phase 6: Finalize and Save

Show the user a one-line summary (step count, parallel groups, critic issues resolved) and the clean plan. On approval, save to `docs/plans/YYYY-MM-DD-<feature-name>.md`, commit `docs: add <feature-name> implementation plan`. Step detail files stay in `.context/plans/` (gitignored).

Hand off: **"Plan complete and saved. Ready for execution."**
