---
name: cancel-queued-ci-runs-before-push
paths: ["**/*"]
---

# Cancel Queued CI Runs Before Pushing to Avoid Wasted Runner Time

Category: git
Tags: [ci, github-actions, self-hosted, runner]

## Rule

Cancel stale queued CI runs before pushing new commits to the same branch on a single self-hosted runner. Queued runs block the runner even after newer code is pushed.

## Why

With a single Mac Mini runner, GitHub Actions queues runs sequentially. Old queued runs from stale commits or other branches block your new run for 20-45 minutes each. Concurrency groups only cancel within the same group — runs from different workflows or branches queue independently. Use `gh run cancel` to clear the queue.

## Examples

### Good

```bash
# Before triggering a new E2E run:
gh run list -L 10 --json databaseId,status | \
  jq '.[] | select(.status == "queued") | .databaseId' | \
  xargs -I{} gh run cancel {}
gh workflow run "E2E Maestro" --ref main
```

## References

- a prior E2E project: E2E run queued for 40+ min behind 5 stale runs from another branch

## Verify

"Before pushing, are there queued CI runs? Have I cancelled stale runs before triggering new ones?"

## Patterns

Bad — stale runs block the runner:

```bash
# 5 stale queued runs from feature-x branch
gh workflow run "E2E Maestro" --ref main
# New run queues behind all 5 stale runs
# Waits 40+ minutes before starting
```

Good — cancel stale runs first:

```bash
# Clear the queue
gh run list -L 10 --json databaseId,status | \
  jq '.[] | select(.status == "queued") | .databaseId' | \
  xargs -I{} gh run cancel {}
# Now trigger — runs immediately
gh workflow run "E2E Maestro" --ref main
```
