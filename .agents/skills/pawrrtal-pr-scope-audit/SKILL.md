---
name: pawrrtal-pr-scope-audit
description: Audit whether Pawrrtal work is actually in the intended PR and matches the user's full requested scope. Use when continuing long goals, answering "is everything in this PR?", before saying a PR is ready, after operational VPS work, or whenever implementation, CI, reviews, live deploy, and runtime checks are mixed together.
---

# Pawrrtal PR Scope Audit

Use this before claiming that a long Pawrrtal task is complete or that a PR contains the work.

## Rule

Separate **repo changes**, **live operations**, **CI/review state**, and **unimplemented scope**. Do not compress them into "done."

## Checklist

1. **Identify the authoritative branch and PR.**

   ```bash
   git status --short --branch
   git rev-parse --show-toplevel
   git rev-parse --abbrev-ref HEAD
   gh pr view <number> --json number,title,headRefName,baseRefName,url,reviewDecision,statusCheckRollup
   ```

2. **Measure the PR honestly.**

   ```bash
   BASE_REF="$(gh pr view <number> --json baseRefName --jq .baseRefName)"
   git fetch origin "$BASE_REF"
   git rev-list --count "origin/${BASE_REF}..HEAD"
   git log --oneline "origin/${BASE_REF}..HEAD"
   git diff --stat "origin/${BASE_REF}...HEAD"
   ```

3. **Map work to the user's requirements.** Make a table with:

   | Requirement | Evidence in PR | Runtime/ops evidence | Status |
   | --- | --- | --- | --- |

   Status must be one of: `proven`, `partial`, `ops-only`, `missing`, `blocked`.

4. **Call out work that is not in the PR.** VPS configuration, service restarts, live smoke tests, runner setup, Cloudflare settings, and manual GitHub settings are not PR code unless committed as docs/scripts/workflows.
5. **Do not let a small passing subset redefine the goal.** If the user asked for provider/channel/core plugin architecture, a live deploy PR is not that architecture work.
6. **Check review threads and CI from GitHub, not memory.**

   ```bash
   gh pr checks <number>
   gh api graphql -f query='...' # review thread query when resolving comments
   ```

7. **Before pushing, stage only your files.** The Pawrrtal worktree is shared; never use `git add -A` for a mixed tree.

## Answer Shape

Lead with the truth:

- "Yes, the PR contains X, Y, Z."
- "No, it does not contain A, B, C."
- "These items were operational work outside the PR."
- "These checks are still pending/failing."

Do not soften missing scope with "pre-existing" or "mostly." If it is not proved, it is not done.
