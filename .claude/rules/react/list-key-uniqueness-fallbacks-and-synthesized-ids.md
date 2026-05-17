---
name: list-key-uniqueness-fallbacks-and-synthesized-ids
paths: ["**/*.{ts,tsx}", "backend/app/core/providers/**/*.py"]
---
# When You Don't Have a Stable ID, Fall Back to the Row Index — and When the Backend Mints IDs, Make Them Session-Unique

Companion to [`stable-keys.md`](./stable-keys.md), which says "use a stable
server-provided ID." This rule covers what to do when there isn't one, and
the backend-side mistake that masquerades as one. Both produced
duplicate-key warnings in pawrrtal on the same day (bean `pawrrtal-ffc2`).

## Verify

"For each `.map(...)`: if no stable ID exists, am I falling back to the
**array index** — not to content (`item.body`, `content.slice(0, 80)`)
and not to a literal string (`'saved'`, `${a}-${b}`)? And for any ID I
synthesize server-side that will be used as a React key (tool-call IDs,
event IDs): is it unique across the whole session (UUID-backed), not just
within one provider `stream()` call?"

## Patterns

Bad — content-derived fallback collapses when content repeats:

```tsx
{chatHistory.map((msg) => {
  // `timestamp` is unset on persisted history → key becomes `user:saved:Yo`.
  // Send "Yo" twice and React renders one row.
  const key = `${msg.role}:${msg.timestamp ?? 'saved'}:${msg.content.slice(0, 80)}`;
  return <Row key={key} />;
})}

{items.map((it) => (
  // Two cards with the same icon+title+body collide silently.
  // Very common in LLM-rendered output where the model repeats itself.
  <Card key={`${it.icon}-${it.title}-${it.body}`} />
))}
```

Good — index suffix makes position the discriminator. Safe **only** when
the list is append-only or render-once; if the list reorders or inserts
in the middle, add a real ID upstream instead.

```tsx
{chatHistory.map((msg, index) => (
  <Row key={`${msg.role}:${msg.timestamp ?? `saved-${index}`}`} />
))}

{items.map((it, index) => <Card key={`card-${index}`} />)}
```

Bad — backend counter scoped to one `stream()` call. Counter restarts at
0 every agent-loop iteration, so two `list_dir` calls in two turns both
serialize as `call-list_dir-0` and collide as React keys downstream:

```python
def _tool_calls_from_chunk(chunk, start_index):
    tool_call_id = f"call-{name}-{start_index + i}"  # ❌ not session-unique
```

Good — UUID suffix, no cross-call state needed. 12 hex chars = 48 bits;
collision is impossible in practice and the name prefix keeps logs
grep-friendly:

```python
def _tool_calls_from_chunk(chunk):
    tool_call_id = f"call-{name}-{uuid.uuid4().hex[:12]}"
```

## Defense in depth

If the frontend may have received colliding IDs historically (persisted
rows written before a backend synthesis bug was fixed), suffix the React
key with the row index on top of the ID
(`key={\`tool-${call.id}-${index}\`}`). Remove the defensive suffix once
the data is migrated.

## Origin

pawrrtal 2026-05-17, bean `pawrrtal-ffc2`. `ChatView.tsx`'s
content-derived fallback produced `user:saved:Yo` collisions;
`gemini_provider.py:_tool_calls_from_chunk`'s per-stream counter produced
`tool-call-list_dir-0` collisions; five more matching keys turned up in
`features/chat/artifacts/components.tsx` for LLM-rendered cards, risks,
and steps.
