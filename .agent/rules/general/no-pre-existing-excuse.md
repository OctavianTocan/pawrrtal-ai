---
description: Fix issues you encounter — never punt on them by labelling them "pre-existing".
paths: ["**/*"]
---

# Rule: Never Say "Pre-Existing" — Fix It

## Rule

The phrase **"pre-existing"** (or "not introduced by this PR", "from
an earlier change", "was already broken before") is **banned from PR
descriptions, review replies, commit messages, and chat output**.

If you encounter a problem — lint warning, type error, runtime
warning, console error, broken test, regression, console noise — you
**fix it**. You do not justify leaving it broken by tracing its
genealogy. The user does not care who introduced the problem. The
user cares whether the app works.

This rule applies whether the problem is:

- An error or a warning. Both need fixing.
- In code you wrote, code someone else wrote, or vendored code.
- In the file you're touching, or two files away.
- "In scope" or "out of scope" of the PR you opened.

If a fix would balloon a PR's scope unreasonably, the right move is
to **open a separate PR for the fix and reference it** — not to
defer with "pre-existing." Either fix it in this PR or fix it in
the next one. Do not leave it broken and explain it away.

## Why this matters

A real customer cannot tell whether a console error was introduced
in commit `abcdef` from May 7th or in the PR that just shipped. The
app is broken either way. Tracing genealogy is a rationalisation;
the user reads it as "I noticed but chose not to fix."

Specifically: warnings are not optional. A Biome warning, a CI
non-blocking notice, a `console.warn` — these are all latent
failures that haven't been promoted to blocking yet. They will be
promoted (Biome rolls levels, React 19 hardened previously
informational warnings into hydration faults, etc.). Treat warnings
the same as errors.

## What to do instead

- **Fix it in the current PR** when the fix is small enough that the
  PR scope still reads cleanly.
- **Fix it in a sibling PR** when the fix is structurally unrelated.
  Open the PR before you finish the original; don't leave a TODO
  hanging.
- **Never describe a failure mode as "pre-existing" to justify
  leaving it.** If you must describe its history, do so in the
  commit message of the *fix* PR, not as an excuse.

## Examples

### Wrong

> The bun-check failure is from PR #132's leftover `id="theme-detection"` literal — pre-existing, not from this PR.

> Two warnings (pre-existing tech debt: `KnowledgeContainer` + `whimsy/index`); they don't fail CI.

> The Stagehand failure on #126 is pre-existing — not from this session, leaving it untouched unless you say otherwise.

### Right

> The bun-check failure is from a static `id="theme-detection"` literal in `app/layout.tsx`. Fixed in this PR (or: filed as PR #135 since the fix touches a different concern).

> Biome flagged two functions over the line budget — `KnowledgeContainer` and `WhimsySettingsCard`. Split each into smaller pieces in this PR.

> Stagehand is failing on #126; running it down now / opened a follow-up PR / asking for context if I genuinely can't reproduce.

## Enforcement

This is an instruction-level rule, not a script-enforced gate. The
operator will call out any "pre-existing" usage they see. Treat the
callout as a hard stop and fix the underlying issue immediately.

## See also

- `AGENTS.md` (top-of-file rules — surfaces this same expectation
  to every agent on every session start).
