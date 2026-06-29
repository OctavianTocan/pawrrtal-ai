---
name: cancelled-runs-cannot-be-rerun
paths: [".github/workflows/**"]
---

# Cancelled GitHub Actions Runs Cannot Be Re-Run - Trigger a New Dispatch Instead

## Rule

A cancelled GitHub Actions workflow run cannot be re-run. You must trigger a new dispatch. When working with publish workflows, always verify the run ID you're monitoring matches the one with correct inputs.

## Why

The GitHub UI and API don't allow re-running cancelled runs. If you cancel the wrong run (e.g., the dispatch with correct version instead of the push-triggered one), you lose that configuration and must dispatch again.

## Verify

```bash
# Check run inputs before cancelling
gh run view <run-id> --json event,displayTitle
# If event is 'push', it has no dispatch inputs
# If event is 'workflow_dispatch', it has your version
```

## Patterns

Bad — cancel without checking which run has the inputs:

```bash
# Two runs started: push + dispatch
gh run list -w publish.yml
# Cancel the first one without checking
gh run cancel <first-run-id>
# Oops — that was the dispatch with version=0.3.1
# Can't re-run a cancelled run → must dispatch again
```

Good — verify before cancelling:

```bash
# Two runs started: push + dispatch
gh run view <run-id-1> --json event
# event: "push" → no inputs, safe to cancel
gh run view <run-id-2> --json event
# event: "workflow_dispatch" → has version, keep this one
gh run cancel <run-id-1>
```

## Origin

a prior release workflow — two runs started simultaneously (push + dispatch). Wrong one was cancelled (the dispatch with version=0.3.1), requiring a third dispatch.
