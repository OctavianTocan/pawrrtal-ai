---
name: one-concern-per-pr
paths: [".github/**", "**/*.sh", "**/.git*"]
---

# One Concern Per PR

Each PR addresses exactly one concern. No mixing refactors with features, no combining unrelated bug fixes, no "while I was here" changes. If a refactor is needed to implement a feature, the refactor goes in a separate PR first.

**Why:** Mixed-concern PRs make review harder, bisect harder, and revert harder. When the feature needs to be reverted, the refactor shouldn't come with it.

**Learned from:** tap (OctavianTocan/tap) — PR discipline.

## Verify

"Does this PR address exactly one concern? Are there any 'while I was here' changes that should be a separate PR?"

## Patterns

Bad — mixed concerns in one PR:

```text
PR title: "feat: add user profile + fix login bug + refactor auth module"
# Which change caused the regression?
# Can't revert the login fix without losing the profile feature
# Reviewer has to check 3 separate logical changes
```

Good — one PR per concern:

```text
PR 1: "refactor: extract auth helpers" (merge first)
PR 2: "fix: login session expiry" (depends on PR 1)
PR 3: "feat: add user profile" (independent)
// Each can be reviewed, reverted, and bisected independently
```
