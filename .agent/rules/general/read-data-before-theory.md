---
name: read-data-before-theory
paths: ["**/*"]
---

# Read the Actual Data/Logs Before Theorizing About What Went Wrong

Category: general
Tags: [debugging, methodology]

## Rule

Read the actual error output, CI logs, and file contents before forming a theory. Don't fix what you haven't verified is broken.

## Why

Theories based on architecture knowledge ("build settings should propagate") waste cycles when the actual problem is simpler (literal `***` in source, missing JS bundle, wrong app ID). The fix for what you think is broken is often different from the fix for what is actually broken. Read first, theorize second.

## Examples

### Bad

```text
Theory: xcodegen circular reference prevents build setting expansion
Action: Remove settings from project.yml
Result: Didn't help — actual problem was PlistBuddy needed post-build
```

### Good

```text
1. Read CI log: "AUTH0_DOMAIN is empty or unexpanded in built app ()"
2. Read file bytes: confirm $AUTH0_DOMAIN is in source (not ***)
3. Read built plist: value is empty string, not $(AUTH0_DOMAIN)
4. Conclusion: expansion happened but resolved to empty
5. Fix: PlistBuddy post-build injection
```

## References

- a prior E2E project: 3 theory-driven fixes applied before reading the actual built plist contents

## Verify

"Have I read the actual error logs and file contents before forming a theory? Am I fixing what I've verified is broken?"

## Patterns

Bad — theory-driven debugging without data:

```text
"The build fails → probably a module visibility issue →
 remove module flags → still fails → add different flags →
 still fails → try 3 more theories"
// Never read the actual error message
```

Good — data-driven debugging reads first:

```text
"Read CI log: 'AUTH0_DOMAIN resolved to empty string'
 Read source: variable is present
 Read built artifact: expansion happened but value is empty
 Conclusion: env var not set in CI
 Fix: add env var to CI workflow"
```
