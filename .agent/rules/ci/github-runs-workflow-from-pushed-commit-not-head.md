---
name: github-runs-workflow-from-pushed-commit-not-head
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# GitHub Evaluates the Workflow File From the Pushed Commit, Not HEAD - Fixes Don't Apply to Their Own Trigger

## Explanation

When a merge commit pushes to main, GitHub evaluates the workflow file from the commit being pushed, not the resulting HEAD. If PR #67 updates the workflow file, the merge commit triggers the OLD version of the workflow (from before #67 merged). The updated workflow only takes effect on the NEXT push to main. This means a PR that fixes a workflow doesn't benefit from its own fix on the merge trigger.

## Verify

After merging a workflow fix: will the merge-triggered run use the old or new version of the workflow?

## Patterns

Bad — expect the fix to apply to its own trigger:

```text
Merge PR that fixes workflow paths → expect the merge-triggered run to use the new paths
# Actually runs the OLD workflow from the pre-merge commit
```

Good — expect old workflow on merge, dispatch manually:

```text
Merge PR that fixes workflow → merge-triggered run uses OLD workflow (expected)
Dispatch manually to run the NEW workflow version
# Or push another change to trigger a run with the fixed workflow
```
