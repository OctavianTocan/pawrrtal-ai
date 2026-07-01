---
name: run-toolchain-after-writes
paths: ["**/*.{ts,tsx,js,jsx}"]
---
# Run Toolchain Checks After Every File Write

After creating or modifying any file, run the project formatter and type
checker before moving to the next task. Do not batch multiple file changes
and check later -- check after each file. Errors compound when deferred,
and pre-commit hooks will catch what you missed.

Sequence after every file write:

1. Run the project formatter on the file (`biome format --write` or equivalent)
2. Run `tsc --noEmit` to catch type errors
3. Fix any errors before touching the next file

## Verify

"Did I run the formatter and type checker on the file I just wrote or modified?
Am I about to move to the next task with unchecked files?"

## Patterns

Bad -- write three View files, then discover type errors at commit time:

```text
write FileAView.tsx
write FileBView.tsx
write FileCView.tsx
git commit  # pre-commit hook fails with 5 errors across 3 files
```

Good -- check each file immediately after writing:

```text
write FileAView.tsx
biome format --write FileAView.tsx && tsc --noEmit  # catches Calligraph type error
fix FileAView.tsx
write FileBView.tsx
biome format --write FileBView.tsx && tsc --noEmit  # clean
```
