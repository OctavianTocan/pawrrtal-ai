---
name: multi-agent-git-safety
paths: [".github/**", "**/*.sh", "**/.git*"]
---

# Multi-Agent Git Safety

When multiple agents or developers work the same repository:

- No `git stash` — stashes are invisible and get forgotten
- No `git worktree` — creates state that other agents can't see
- No branch switching on a shared working copy

Each agent works on its own branch from a clean checkout state.

**Why:** Stashes and worktrees create hidden state that confuses other agents working the same repo. One agent's stash can block another agent's checkout. Branch switching leaves uncommitted debris.

**Learned from:** pawrrtal (OctavianTocan/pawrrtal) — multi-agent collaboration rules.

## Verify

"Am I using git stash, git worktree, or branch switching on a shared working copy? Should each agent use its own branch instead?"

## Patterns

Bad — shared working copy with stashes and branch switching:

```bash
# Agent A
git stash
git checkout feature-x
# Agent B (same working copy)
git checkout main
# Agent A's stash is invisible to B
# B's checkout may fail due to A's uncommitted changes
```

Good — each agent on its own branch:

```bash
# Agent A: works on branch agent-a/feature-x
# Agent B: works on branch agent-b/feature-y
# No shared state, no conflicts, no hidden stashes
```
