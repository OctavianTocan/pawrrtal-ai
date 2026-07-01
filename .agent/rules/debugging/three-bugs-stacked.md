---
name: three-bugs-stacked
paths: ["**/*"]
---

# When a fix doesn't work, check for stacked bugs

## Explanation

A single observed failure can mask multiple independent bugs. When a publish workflow showed "0 jobs," three separate issues were stacked: (1) the workflow paths referenced a directory that didn't exist on the target branch, (2) the YAML had a heredoc that broke parsing, and (3) the transitive deps injection appended outside the Gradle dependencies block. Fixing only one bug still left the build broken, creating the illusion that the fix was wrong.

## Verify

When a fix doesn't resolve the issue: are there other independent bugs producing the same symptom?

## Patterns

### Pattern (bad)

```text
Fix A → still broken → revert A → try B → still broken → revert B
# A and B were both real fixes, but C also exists
```

### Pattern (good)

```text
Fix A → still broken → keep A → investigate further
Fix B → still broken → keep A+B → investigate further  
Fix C → working
# All three were needed
```
