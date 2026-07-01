---
name: compare-working-vs-broken-before-fixing
paths: ["**/*"]
---

# Create a Structured Comparison Between Working and Broken State Before Writing Any Fix

When a build or integration fails, create a structured comparison of the working setup vs your broken setup before making any code changes.

## Rule

1. Find a setup where it works (library's CI, a colleague's machine, a previous commit)
2. Create a side-by-side comparison: OS, tool versions, config files, environment variables
3. Identify the divergence
4. Fix only the divergence

Never start changing code until you understand why it's broken. Trial-and-error fixes compound: each failed attempt leaves residue that makes the next diagnosis harder.

## Why

A 5-minute comparison eliminates hours of guessing. Two days of trial-and-error fixes for a brownfield CI issue were resolved in 30 minutes once the working CI config was compared side-by-side with the broken one.

## Verify

"Before writing any fix, have I created a structured side-by-side comparison of the working setup vs the broken setup? Do I know exactly what diverges?"

## Patterns

Bad — trial-and-error without comparison:

```text
1. Build fails with linker error
2. Try adding -lstdc++ to linker flags → still broken
3. Try changing deployment target → still broken
4. Try updating pod versions → still broken
5. Two days of speculative fixes, each leaving residue
# Never compared against the working CI config
```

Good — structured comparison first:

```text
1. Build fails with linker error
2. Find working CI config from colleague's branch
3. Diff: OS version, Xcode version, Podfile, build settings
4. Divergence found: missing CODE_SIGNING_ALLOWED=NO in CI
5. Fix only that → build passes in 30 minutes
```
