---
name: use-gh-workflow-run-not-api
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Use gh workflow run Instead of gh api for Triggering Workflow Dispatches

## Rule

Use `gh workflow run` (not `gh api`) for dispatching workflows. The `gh api` dispatches endpoint requires the ref and inputs as JSON body, while `gh workflow run` handles the serialization.

## Good

```bash
gh workflow run publish.yml --ref main -f version=0.3.1
```

## Bad

```bash
# Easy to get the JSON structure wrong
gh api repos/{owner}/{repo}/actions/workflows/{id}/dispatches \
  -f ref=main -f inputs='{"version":"0.3.1"}'
```

## Verify

```bash
# Confirm the dispatch created a run with correct inputs
gh run list -w publish.yml --limit 1 --json databaseId,event
```

## Patterns

Bad — raw API dispatch with manual JSON:

```bash
# Easy to get JSON structure wrong → silent failure, no run created
gh api repos/{owner}/{repo}/actions/workflows/{id}/dispatches \
  -f ref=main -f inputs='{"version":"0.3.1"}'
# No error, no run — spent 30 min wondering why nothing happened
```

Good — use gh workflow run:

```bash
gh workflow run publish.yml --ref main -f version=0.3.1
# Verify the run was created
gh run list -w publish.yml --limit 1 --json databaseId,event
```

## Origin

a prior project publish workflow — API dispatch syntax errors caused silent failures where no run was created.
