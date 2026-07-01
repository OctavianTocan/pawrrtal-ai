---
name: dispatch-reindex-lag
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# GitHub workflow_dispatch re-indexing lag after file update

## Explanation

After pushing a workflow file update to the default branch, GitHub's API can return stale metadata for hours. `workflow_dispatch` won't appear in API responses even though the file has it. `gh workflow run` returns 422. GitHub only re-indexes when a push event actually evaluates the workflow file. If the push only changes the workflow file itself (not files matching the `paths:` filter), the workflow never evaluates and the index stays stale.

## Verify

After updating a workflow file: did the push also touch files matching the workflow's `paths:` filter?

## Patterns

Bad — only change the workflow file:

```bash
# Only change the workflow file — paths: filter never triggers
git add .github/workflows/publish.yml
git commit -m "fix: update workflow"
git push
gh workflow run publish.yml  # 422 error
```

Good — also touch a file that matches the paths: filter:

```bash
# Also touch a file that matches the paths: filter
git add .github/workflows/publish.yml
echo "" >> react-native/CHANGELOG.md
git add react-native/CHANGELOG.md
git commit -m "fix: update workflow + trigger re-index"
git push
# Now dispatch works (or wait for the push-triggered run to complete)
```
