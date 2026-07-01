---
name: check-job-status-not-run-status
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Check Individual Job Status, Not Overall Run Status

Category: ci
Tags: [ci, github-actions, debugging]

## Rule

Check individual job status via API when diagnosing "hung" CI runs — run-level status can show `in_progress` for hours after all jobs completed.

## Why

GitHub Actions' run-level state machine can desync from job-level state. All jobs may have completed (success, failure, or cancelled) but the run itself stays `in_progress`. This looks like a hung build and blocks the runner for other workflows. The only reliable signal is checking each job's `started_at` and `completed_at` timestamps.

## Examples

### Bad

```bash
# Run shows in_progress — assume build is hung, wait hours
gh run view $ID --json status  # "in_progress" (misleading)
```

### Good

```bash
# Check actual job status — reveals all jobs completed
gh api repos/OWNER/REPO/actions/runs/$ID/jobs \
  --jq '.jobs[] | {name, status, conclusion, started: .started_at, completed: .completed_at}'
# If all jobs show "completed" but run is "in_progress" → phantom hang
# Safe to cancel the zombie run
```

## Verify

"When a run shows `in_progress` for an unexpectedly long time, did you check individual job statuses via the jobs API before concluding it's stuck?"

## Patterns

Bad — relying on run-level status alone:

```bash
# This can show "in_progress" even when all jobs are done
gh run view $RUN_ID --json status
if [ "$(gh run view $RUN_ID --json status --jq '.status')" = "in_progress" ]; then
  echo "Still running..."  # May be lying — check jobs instead
fi
```

Good — always check job-level detail:

```bash
# Check each job's actual state
gh api repos/OWNER/REPO/actions/runs/$RUN_ID/jobs \
  --jq '.jobs[] | "\(.name): \(.status) \(.conclusion // "n/a")"'

# Detect phantom hang: all jobs completed but run still in_progress
COMPLETED=$(gh api repos/OWNER/REPO/actions/runs/$RUN_ID/jobs \
  --jq '[.jobs[] | select(.status == "completed")] | length')
TOTAL=$(gh api repos/OWNER/REPO/actions/runs/$RUN_ID/jobs \
  --jq '.jobs | length')
if [ "$COMPLETED" -eq "$TOTAL" ]; then
  echo "All jobs done — run status is stale. Safe to cancel."
  gh run cancel $RUN_ID
fi
```

## References

- debug-ci-build-hangs skill: Phantom hang pattern
- Real incident: publish run showed in_progress for 2+ hours with all jobs completed
