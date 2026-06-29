---
name: timeout-masquerades-as-cancelled
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# GitHub Actions timeouts report as "cancelled," not "timed_out"

## Explanation

When a job hits its `timeout-minutes` limit, GitHub reports the conclusion as `cancelled` with the runner service account as the cancel actor. This looks identical to a manual cancellation. To distinguish: check if the job's elapsed time matches the timeout value exactly. If `timeout-minutes: 30` and the job ran for exactly 1800s, it timed out.

## Verify

When a job shows `conclusion: cancelled`: did the elapsed time match the timeout value?

## Patterns

Bad — assume cancellation means human intervention:

```bash
# "Someone cancelled my build" — actually it timed out
gh run view $ID --json jobs --jq '.jobs[0].conclusion'  # "cancelled"
```

Good — check elapsed time vs timeout:

```bash
STARTED=$(gh run view $ID --json jobs --jq '.jobs[0].startedAt')
ENDED=$(gh run view $ID --json jobs --jq '.jobs[0].completedAt')
# If elapsed ≈ timeout-minutes, it timed out
```
