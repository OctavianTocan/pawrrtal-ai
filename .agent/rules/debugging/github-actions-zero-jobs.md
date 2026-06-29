---
name: github-actions-zero-jobs
paths: [".github/workflows/**"]
---

# GitHub Actions "0 jobs" means YAML parse failure, not runner issue

## Explanation

When a GitHub Actions run shows `status: completed, conclusion: failure` with zero jobs spawned, the YAML itself has a parse error. GitHub doesn't surface YAML parse errors in the UI — it silently fails the run. Don't investigate runners, concurrency groups, or path filters. Download and validate the YAML file first.

## Verify

When a workflow run shows 0 jobs: have you validated the YAML file for syntax errors?

## Patterns

### Pattern (bad)

```bash
# Investigating the wrong things
gh run view $RUN_ID --json jobs  # shows empty jobs
# "Must be a runner issue" — wrong
# "Must be a path filter issue" — wrong
```

### Pattern (good)

```bash
# Check the YAML first
gh api repos/$REPO/contents/.github/workflows/publish.yml --jq .content | base64 -d | python3 -c "import yaml,sys; yaml.safe_load(sys.stdin)"
# If it throws: YAML parse error. Fix the file.
```
