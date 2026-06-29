---
name: guard-state-clears
paths: ["**/*.{ts,tsx}"]
---
# Guard State Clears with ID Matching

When clearing active state (conversation, session, editor), check that the
ID being cleared matches the current state. Without this guard, a stale
clear from an earlier operation can wipe a newly-set value.

## Verify

"Could a delayed clear operation wipe state that was set by a newer operation?"

## Patterns

Bad — stale clear wipes the newly-set conversation:

```typescript
function clearActiveConversation() {
  setActiveConversation(null); // Wipes whatever is current
}
```

Good — only clears if ID still matches:

```typescript
function clearActiveConversation(conversationId: string) {
  setActiveConversation(prev =>
    prev?.id === conversationId ? null : prev
  );
}
```
