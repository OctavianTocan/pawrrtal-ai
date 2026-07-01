---
name: file-references-repo-relative
paths: ["**/*"]
---

# File References: Repo-Root Relative

File references in code review, chat, and documentation must be repo-root relative, never absolute paths.

Good: `src/components/ui/sidebar.tsx:80`
Bad: `/Users/john/workspace/the vendored app/src/components/ui/sidebar.tsx:80`

**Why:** Absolute paths are machine-specific, can't be clicked by other developers, and leak system information. Repo-relative paths work for everyone, in any IDE, on any machine.

**Learned from:** Code review workflow convention.

## Verify

"Are file paths in my message repo-root relative? Do any contain /Users/, /home/, or C:\?"

## Patterns

Bad — absolute paths, only works on your machine:

```text
"The bug is in /Users/john/workspace/project/src/api/auth.ts:42"
// Other developers can't click this
// Leaks username and directory structure
```

Good — repo-relative, works for everyone:

```text
"The bug is in src/api/auth.ts:42"
// Clickable in any IDE
// Works for all developers regardless of checkout location
```
