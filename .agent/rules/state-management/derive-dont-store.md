---
name: derive-dont-store
paths: ["**/*.{ts,tsx}"]
---
# Derive State Instead of Storing Computed Values

Compute derived values inline from existing data rather than storing them in
separate state variables. Stored computed values can fall out of sync with
their source, creating impossible states. A function like
`getPendingState(msg, isLoading, isLastMsg)` is always correct; a stored
`isPending` boolean can drift.

## Verify

"Is this state variable computed from other state? Should I derive it inline
instead of storing it?"

## Patterns

Bad — stored boolean can be out of sync:

```typescript
const [messages, setMessages] = useState([]);
const [hasPending, setHasPending] = useState(false);
// If setMessages fires without updating hasPending, they disagree
```

Good — derived inline, always correct:

```typescript
const [messages, setMessages] = useState([]);
const hasPending = messages.some(m => m.status === 'pending');
```
