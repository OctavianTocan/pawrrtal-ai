---
name: reuse-established-patterns
paths: ["**/*"]
---

# Reuse Established Codebase Patterns — Never Implement Parallel Mechanisms for the Same Behavior

When the codebase already has a mechanism for a behavior, new code paths
that need the same behavior must use the existing mechanism — not implement
their own version. Rolling a parallel approach causes race conditions,
inconsistencies, and bugs that the original pattern was designed to prevent.

## Verify

"Is there already an established pattern in the codebase for this behavior?
Am I about to write a second way to do the same thing? Could I use the
existing mechanism instead?"

## Patterns

Bad — new code path invents its own redirect mechanism:

```ts
// native-login: custom redirect after auth
await signInWithCustomToken(auth, token);
router.push(redirectPath); // races with auth state
```

Good — reuses the established redirect mechanism:

```ts
// native-login: uses same pattern as OAuth flows
sessionStorage.setItem('authRedirectPath', redirectPath);
await signInWithCustomToken(auth, token);
// AuthContext's onIdTokenChanged handles redirect after auth settles
```

Before implementing any cross-cutting behavior (auth redirects, error
handling, analytics, caching), search for how existing code handles the
same concern and follow that pattern.
