---
name: review-comments-are-patterns
paths: ["**/*.{ts,tsx,js,jsx,css}"]
---
# Treat Review Comments as Patterns, Not Points

When a review comment flags an issue at a specific location, that comment
identifies a PATTERN -- not just that one line. Before fixing the flagged
instance, scan every file changed in the PR for the same pattern and fix
all occurrences in one pass.

## Verify

"Am I about to fix only the exact line the reviewer flagged? Did I search
all PR-changed files for the same pattern first?"

## How to Apply

1. Read the review comment and identify the underlying pattern
   (e.g., "missing Omit on ComponentProps" is a pattern, not just one file)
2. Run `git diff --name-only <base>..HEAD` to get all files changed in the PR
3. Search those files for the same pattern using grep/ripgrep
4. Fix every occurrence, not just the one the reviewer pointed at
5. In the commit message, note "Fixed across N files" to show pattern coverage

## Patterns

Bad -- fixes only the flagged location:

```text
Review: "LoginFormView.tsx:15 -- onSubmit conflicts with ComponentProps"
Action: fix LoginFormView.tsx only
Result: User says "fix this EVERYWHERE in the PR, not just here"
```

Good -- treats it as a pattern scan:

```text
Review: "LoginFormView.tsx:15 -- onSubmit conflicts with ComponentProps"
Action: grep all PR-changed .tsx files for `extends.*ComponentProps`
        without Omit, fix all matches
Result: all instances fixed in one pass
```
