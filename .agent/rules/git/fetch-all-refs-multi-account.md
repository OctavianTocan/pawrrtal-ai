---
name: fetch-all-refs-multi-account
paths: [".gitconfig", ".git/config", "**/*.sh", ".github/**"]
---
# Force Full Ref Fetch with Multiple GitHub Accounts

When multiple GitHub accounts are configured (e.g., personal + work via SSH config aliases), `git fetch origin` uses the default refspec which may be narrowed by credential helpers or partial clone filters. Branches created by your other account — or branches pushed from a different machine with a different SSH identity — may not appear in `git branch -r` after a standard fetch.

This manifests as "branch not found" errors when trying to checkout or rebase onto a branch you know exists on the remote. Running `git fetch` again doesn't help because the default refspec hasn't changed.

Force a full fetch of all refs to ensure your local view of the remote is complete.

## Verify

"After fetching, can I see the remote branch I expect in `git branch -r`? If not, have I tried a full ref fetch?"

## Patterns

Bad — default fetch may skip refs:

```bash
git fetch origin
git checkout feature-xyz
# error: pathspec 'feature-xyz' did not match any file(s) known to git
```

Good — explicit full refspec fetches all branches:

```bash
git fetch origin '+refs/heads/*:refs/remotes/origin/*'
git checkout feature-xyz
# Works — branch was fetched
```

Good — set the refspec permanently for this repo:

```bash
git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
# Now `git fetch origin` always fetches everything
git fetch origin
```
