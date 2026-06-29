---
name: stable-keys
paths: ["**/*.{ts,tsx}"]
---
# Stable Server-Provided IDs as React Keys

Use stable server-provided IDs as React keys, never content-derived values.
Using `key={text.slice(0,20)}` or similar during streaming causes full
remounts on every update, losing cursor position, scroll state, and selection.

## Verify

"Am I using content-derived keys that change during streaming or editing?
Should I use a stable ID instead?"

## Patterns

Bad — key changes on every streaming token, causing full remount:

```tsx
{messages.map(msg => (
  <Message key={msg.content.slice(0, 20)} message={msg} />
))}
```

Good — stable ID survives content changes:

```tsx
{messages.map(msg => (
  <Message key={msg.id} message={msg} />
))}
```
