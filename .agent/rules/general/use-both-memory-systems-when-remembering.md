---
name: use-both-memory-systems-when-remembering
paths: ["**/*"]
---

# When Asked to Remember Something, Write to Both Memory Systems (Built-in + External)

When the user asks you to remember something, you MUST use BOTH memory
systems:

1. **Agent Memory skill** (`/agent-memory`) — always invoke this skill to
   persist the memory in the agent-memory system
2. **Built-in auto memory** (files in the project memory directory) — also
   save to the standard file-based memory system as usual

Using only one system is not sufficient. Both must be written to every time
the user says "remember this", "save this", "keep track of", or any
equivalent request to persist information across sessions.

## Verify

"Did I invoke /agent-memory AND write to the auto memory system? If I only
used one, I need to use the other too."

## Patterns

Bad — only one memory system used:

```text
User: "Remember that the staging API key is in 1Password"
Action: Write to CLAUDE.md only
// Agent memory system not updated → other sessions won't know
```

Good — both systems written:

```text
User: "Remember that the staging API key is in 1Password"
Action 1: Invoke /agent-memory to persist
Action 2: Write to CLAUDE.md / memory directory
// Both systems have the information → any session can retrieve it
```
