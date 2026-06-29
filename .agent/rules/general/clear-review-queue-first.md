---
name: clear-review-queue-first
paths: ["**/*"]
---

# Clear Pending Review Queue Before Starting New Work

Before starting new work, clear any pending review queue. Open PRs waiting for review take priority over new features.

**Why:** Stale PRs block other contributors, accumulate merge conflicts, and lose context. A reviewed-and-merged PR is worth more than three new draft PRs. Review queue is a liability that grows with time.

**Learned from:** agentic-stack development workflow.

## Verify

"Are there open PRs waiting for my review? Am I starting new work while reviews are pending?"

## Patterns

Bad — new features before clearing review queue:

```text
1. See 4 PRs awaiting review
2. Start implementing new feature instead
3. PRs go stale, accumulate conflicts, lose reviewer interest
// Each day of delay increases merge cost
```

Good — review queue cleared first:

```text
1. See 4 PRs awaiting review
2. Review and approve/merge all 4
3. Then start new feature
// Fresh context, no conflicts, team unblocked
```
