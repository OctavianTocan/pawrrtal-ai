---
name: no-direct-useeffect
paths: ["**/*.{ts,tsx}"]
---
# No Direct useEffect

Never call `useEffect` directly in components. Most useEffect usage
compensates for something React already gives you better primitives for.
Direct useEffect causes infinite loops, race conditions, stale closures,
and dependency hell. Use these replacements instead:

**1. Derive state inline** — don't useEffect to sync state from state/props.
**2. Data-fetching libraries** — useQuery/SWR, not useEffect + fetch + setState.
**3. Event handlers** — user actions belong in onClick/onSubmit, not effects.
**4. useMountEffect** — for one-time external sync (DOM, third-party widgets).
**5. key prop** — to reset a component when an ID changes, not effect + reset.

## Verify

"Are there useEffect calls that set state derived from other state or props?
Are there fetch-in-effect patterns? Are there effects that relay user actions
via state flags? Could any effect be replaced by inline computation, an event
handler, a query hook, or a key prop?"

## Patterns

Bad — effect syncs derived state (extra render + loop risk):

```tsx
const [products, setProducts] = useState([]);
const [filtered, setFiltered] = useState([]);
useEffect(() => {
  setFiltered(products.filter((p) => p.inStock));
}, [products]);
```

Good — compute inline:

```tsx
const [products, setProducts] = useState([]);
const filtered = products.filter((p) => p.inStock);
```

Bad — fetch in effect (race condition, no caching):

```tsx
useEffect(() => {
  fetchProduct(productId).then(setProduct);
}, [productId]);
```

Good — query library handles cancellation/caching/staleness:

```tsx
const { data: product } = useQuery(['product', productId], () =>
  fetchProduct(productId)
);
```

Bad — effect as action relay via state flag:

```tsx
const [liked, setLiked] = useState(false);
useEffect(() => {
  if (liked) { postLike(); setLiked(false); }
}, [liked]);
return <button onClick={() => setLiked(true)}>Like</button>;
```

Good — direct event handler:

```tsx
return <button onClick={() => postLike()}>Like</button>;
```

Bad — effect watches ID to reset:

```tsx
useEffect(() => { loadVideo(videoId); }, [videoId]);
```

Good — key forces clean remount:

```tsx
<VideoPlayer key={videoId} videoId={videoId} />
// VideoPlayer uses useMountEffect(() => loadVideo(videoId))
```

For legitimate mount-only external sync, use a named wrapper:

```tsx
function useMountEffect(effect: () => void | (() => void)) {
  useEffect(effect, []);
}
```
