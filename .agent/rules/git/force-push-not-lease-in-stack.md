---
name: force-push-not-lease-in-stack
paths: [".github/**", "**/*.sh"]
---
# Use --force Not --force-with-lease When Rebasing Stacked PRs

When working with stacked PRs (branch A → B → C), each rebase of A rewrites history that B was based on. After rebasing A and force-pushing, your local tracking ref for B's upstream is stale. Running `git push --force-with-lease` on B will reject silently because the remote ref doesn't match what your local thinks it should be.

`--force-with-lease` is a safety net for solo branches — it prevents overwriting someone else's push. But in a stacked workflow where you control all branches, it becomes a blocker. The rejection message ("stale info") gives no clue about which ref is stale or why, leading to wasted debugging time.

Use `--force` for branches in your own stack. Reserve `--force-with-lease` for shared branches where others might push.

## Verify

"Am I force-pushing a branch that's part of a rebase stack I control? If so, --force is correct."

## Patterns

Bad — `--force-with-lease` rejects after rebasing a stack:

```bash
git checkout feature-b
git rebase feature-a
git push --force-with-lease origin feature-b
# error: failed to push some refs
# hint: stale info; remote ref has changed since last fetch
```

Good — `--force` for branches you own in a stack:

```bash
git checkout feature-b
git rebase feature-a
git push --force origin feature-b
```

Good — `--force-with-lease` is still correct for solo branches:

```bash
git checkout my-solo-feature
git rebase main
git push --force-with-lease origin my-solo-feature
```
