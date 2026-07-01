---
name: explicit-return-types-everywhere
paths: ["**/*.ts", "**/*.tsx"]
---

# Every Function Must Declare an Explicit Return Type and Accept Max Three Positional Parameters

Every function must have an explicit return type annotation. Maximum 3 positional parameters — if you need more, use an options object.

**Why:** Explicit return types turn runtime type mismatches into compile errors. They document intent at the signature level. When the return type changes, callers get compiler errors instead of silent runtime failures. Max 3 params prevents unclear call sites and enables easier refactoring to options objects.

**Learned from:** pawrrtal (OctavianTocan/pawrrtal) — AGENTS.md convention.

## Verify

- Run TypeScript compiler with `noImplicitReturns` and `noImplicitAny` enabled
- Verify all functions have explicit return type annotations (not just `void` or `any`)
- Check that adding a 4th positional parameter produces a lint error
- Verify refactoring a positional param to options object is straightforward

## Patterns

- **Options object pattern:** Replace 4+ params with a single options object: `configure({ host, port, timeout, retries })`
- **Typed options interface:** Define an interface for the options object to maintain type safety
- **Destructure in signature:** `function process({ input, output, options }: ProcessConfig)`
