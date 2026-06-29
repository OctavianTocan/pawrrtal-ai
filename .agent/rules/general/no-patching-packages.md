---
name: no-patching-packages
paths: ["**/*"]
---

# Never Patch node_modules Directly — Fork or Work Around Instead

Never use `patch-package` or `pnpm patch` to modify node_modules. If a dependency has a bug:

1. Reproduce with a minimal test case
2. File an issue upstream
3. Fork and fix if urgent, publish a scoped package
4. Work around in application code if possible

Use CI logs to prove or disprove debugging theories before assuming a dependency is broken.

**Why:** Patches rot. They break on version bumps. They hide real bugs from upstream. They make CI non-reproducible when the patch doesn't apply cleanly. Every patch is technical debt with interest.

**Learned from:** a prior mobile project development — hard-won lesson from multiple patch-package incidents.

## Verify

"Am I about to use patch-package or pnpm patch? Can I work around this in application code or file an upstream issue?"

## Patterns

Bad — patch rots on next version bump:

```bash
# Apply a patch to fix a dependency bug
pnpm patch some-library
# Edit files in node_modules
# Works today, breaks when some-library@2.1.0 is released
```

Good — work around in application code:

```typescript
// some-library exports brokenFunction
// Work around with a wrapper:
export function workingFunction(input: Input): Output {
  const result = brokenFunction(input);
  // Fix the known issue in application code
  return fixResult(result);
}
```
