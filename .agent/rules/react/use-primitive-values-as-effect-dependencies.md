---
name: use-primitive-values-as-effect-dependencies
paths: ["**/*.{ts,tsx}"]
---
# Use Primitive Values (Not Object References) as Effect Dependencies - Objects Change Identity Every Render

Don't put entire objects in useEffect dependency arrays. Objects create new
references on every render even when contents are identical, causing effects
to re-run unnecessarily. Destructure or derive the specific primitive values
you actually depend on.

## Verify

"Am I putting an object in a dependency array? Can I extract the specific
primitive value I depend on?"

## Patterns

Bad — re-runs whenever any user field changes:

```typescript
const user = useStore(s => s.user);
useEffect(() => {
  if (user?.isPremium) loadPremiumFeatures();
}, [user]);
```

Good — only re-runs when premium status changes:

```typescript
const isPremium = useStore(s => s.user?.isPremium ?? false);
useEffect(() => {
  if (isPremium) loadPremiumFeatures();
}, [isPremium]);
```
