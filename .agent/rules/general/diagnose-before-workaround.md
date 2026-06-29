---
name: diagnose-before-workaround
paths: ["**/*"]
---

# Diagnose Why the Recommended Approach Failed Before Applying a Workaround

## Rule

Before applying any workaround, diagnose WHY the recommended approach failed. Workarounds that bypass the failure without understanding it create tech debt that compounds.

## Why

A workaround might fix the symptom while the root cause affects other code paths. Understanding the failure often reveals a simpler, correct fix.

## Bad

```text
"The xcodebuild command fails, so let's use the brownfield CLI instead"
→ Why did xcodebuild fail? Module visibility? Missing -fmodules flag? Prebuilt pod issue?
```

## Good

```text
"xcodebuild fails because prebuilt React Native pods compiled on Xcode 16 don't expose
internal Swift types to external consumers under Xcode 26's stricter module boundaries.
The brownfield CLI handles this by configuring the correct module flags during build."
```

## Corollary

If you can't explain why the original approach fails, you don't understand the problem well enough to trust the workaround.

## Origin

a prior iOS CI — multiple attempts at raw xcodebuild workarounds before diagnosing that prebuilt pods were the actual issue.

## Verify

"Can I explain WHY the original approach fails? If not, have I diagnosed the root cause before applying a workaround?"

## Patterns

Bad — workaround without diagnosis:

```text
"npm install fails → delete node_modules and try again"
// Why did it fail? Lockfile mismatch? Registry issue? Disk full?
// Without knowing, the same issue will recur
```

Good — diagnose first, then targeted fix:

```text
"npm install fails with ERESOLVE → check lockfile version →
 pnpm-lock.yaml was generated with pnpm 8 but CI uses pnpm 9 →
 update lockfile with pnpm import → install succeeds"
```
