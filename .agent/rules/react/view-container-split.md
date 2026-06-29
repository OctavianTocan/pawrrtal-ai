---
name: view-container-split
paths: ["**/*.{ts,tsx}"]
---
# View/Container Split

Split components into a View (pure presentation) and Container (logic/state).
Views receive ALL data and callbacks via props — no hooks except useMediaQuery.
Containers call hooks, manage state, and pass props to Views. This makes
components testable, reusable, and easy to reason about.

Name files `FooView.tsx` and `Foo.tsx` (or `FooContainer.tsx`).

## Verify

"Does this component mix hooks/state with significant JSX? Should the
presentation be extracted into a View component that receives props only?"

## Patterns

Bad — logic and presentation mixed:

```tsx
export function PromoBanner() {
  const { isMax, loading } = useSubscription();
  const [dismissed, setDismissed] = useState(false);
  const router = useGuardedRouter();

  const handleDismiss = () => { track('Dismissed'); setDismissed(true); };
  const handleClaim = () => { track('Claimed'); router.push('/pricing'); };

  if (loading || isMax || dismissed) return null;

  return (
    <div className="...">
      {/* 80 lines of JSX */}
      <button onClick={handleDismiss}>X</button>
      <button onClick={handleClaim}>Claim</button>
    </div>
  );
}
```

Good — Container owns logic, View owns presentation:

```tsx
// PromoBannerView.tsx — pure presentation, no hooks
export interface PromoBannerViewProps {
  onDismiss: () => void;
  onClaim: () => void;
}
export function PromoBannerView({ onDismiss, onClaim }: PromoBannerViewProps) {
  return (
    <div className="...">
      <button onClick={onDismiss}>X</button>
      <button onClick={onClaim}>Claim</button>
    </div>
  );
}

// PromoBanner.tsx — container with all logic
export function PromoBanner() {
  const { isMax, loading } = useSubscription();
  const [dismissed, setDismissed] = useState(false);
  const router = useGuardedRouter();

  const handleDismiss = () => { track('Dismissed'); setDismissed(true); };
  const handleClaim = () => { track('Claimed'); router.push('/pricing'); };

  if (loading || isMax || dismissed) return null;
  return <PromoBannerView onDismiss={handleDismiss} onClaim={handleClaim} />;
}
```

Skip the split for trivial components (< 20 lines, 1-2 props, no hooks).
