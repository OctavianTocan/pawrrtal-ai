---
name: dispatch-requires-default-branch-first
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# workflow_dispatch Only Works After the Workflow File Exists on the Default Branch

Category: ci
Tags: [ci, github-actions, workflow]

## Rule

Ensure workflow files with `workflow_dispatch` exist on the default branch (main) — GitHub only discovers dispatch triggers from the default branch.

## Why

If a workflow file only exists on `development` or a feature branch, `gh workflow run` returns HTTP 404 even with `--ref development`. The `--ref` flag controls which branch the workflow runs against, but the workflow file itself must exist on the default branch for GitHub to find it. Cherry-pick just the workflow file to main.

## Examples

### Bad

```bash
# Workflow only on development — 404
gh workflow run e2e.yml --ref development
# Error: workflow not found on the default branch
```

### Good

```bash
# Cherry-pick workflow file to main
git checkout main
git checkout development -- .github/workflows/e2e.yml
git commit -m "ci: add e2e workflow for dispatch discovery"
git push origin main
# Now dispatch against development code
gh workflow run e2e.yml --ref development
```

## References

- expo-brownfield-ci skill: workflow_dispatch Not Discoverable on Non-Default Branch
- rn-twinmind-brownfield-ci skill: workflow_dispatch requires file on default branch

## Verify

"Does the workflow file with `workflow_dispatch` trigger exist on the default branch (main)? Can `gh workflow run` find it without `--ref`?"

## Patterns

Bad — workflow file only on feature branch:

```bash
# Workflow exists only on development branch
gh workflow run e2e.yml --ref development
# HTTP 404: workflow not found
# The --ref flag doesn't help — GitHub looks for the file on main
```

Good — ensure file exists on default branch first:

```bash
# 1. Cherry-pick just the workflow file to main
git checkout main
git checkout development -- .github/workflows/e2e.yml
git commit -m "ci: add e2e workflow for dispatch discovery"
git push origin main

# 2. Now dispatch works against any branch
gh workflow run e2e.yml --ref development
```
