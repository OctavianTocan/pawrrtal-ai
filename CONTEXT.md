# Pawrrtal Context

Pawrrtal is a workspace-centered personal agent system. This glossary captures
domain terms whose names should stay stable while the codebase is thinned into a
plugin platform.

## Language

**Kernel**:
The small mandatory Pawrrtal runtime that owns identity, workspaces, conversations, persistence, audit, turn orchestration, and the plugin host.
_Avoid_: core, app core, god layer

**Plugin**:
A manifest-backed package that contributes capabilities and adapters which can be enabled, configured, validated, reloaded, and inspected per workspace.
_Avoid_: integration, extension when the package participates in the plugin host

**Capability**:
A user-facing or Paw-facing thing a plugin contributes that can be searched, selected, invoked, or slotted.
_Avoid_: generic hook, callback bag

**Adapter**:
A runtime implementation a plugin contributes to satisfy a kernel interface, such as a provider, channel, agent runtime, migration provider, router, lifecycle task, or scheduler.
_Avoid_: capability when the contribution is infrastructure rather than a searchable or invokable user/Paw surface

**Slot**:
A named role that one or more enabled capabilities can satisfy, ordered by workspace preference rather than forced singleton ownership by default.
_Avoid_: hardcoded singleton, provider type

**Turn Context Provider**:
A capability that produces typed context before a main agent turn while the kernel owns ordering, budgeting, and prompt assembly.
_Avoid_: pre-turn hook

**Turn Observer**:
A capability that reacts to a completed turn without changing the already-running main turn.
_Avoid_: post-turn hook

**Agent Runtime Adapter**:
An adapter that runs a session-owning agent backend behind a stable Pawrrtal interface.
_Avoid_: agent harness capability, subagent implementation, provider special case

**Agent Profile**:
A named agent definition that carries instructions, allowed tools, model/runtime preferences, selection metadata, and optional memory policy.
_Avoid_: agent type when discussing persona/config, plugin-owned subagent

**Delegated Agent Job**:
A durable execution of an Agent Profile through an Agent Runtime Adapter, with lifecycle state, events, cancellation, and a returned summary.
_Avoid_: subagent plugin, plugin-implemented subagent

## Relationships

- A **Plugin** contributes one or more **Capabilities** and **Adapters**.
- A **Plugin** may contribute **Agent Profiles**, but it does not implement delegated execution.
- A **Capability** may satisfy one or more **Slots**.
- The **Kernel** loads **Plugins** and routes **Capabilities** without importing plugin-specific implementations.
- The **Kernel** calls **Adapters** through stable interfaces without exposing them as generic searchable capabilities.
- **Active Recall** is a **Turn Context Provider**, not a generic pre-turn hook.
- Memory-writing and analytics-style work are **Turn Observers**, not generic post-turn hooks.
- Codex/Pi-style delegated runtimes are **Agent Runtime Adapters**, not provider-specific branches in the agent loop.
- A **Delegated Agent Job** uses one captured **Agent Profile** and one captured **Agent Runtime Adapter** snapshot.

## Example Dialogue

> **Dev:** "Should Active Recall stay as a pre-turn hook?"
> **Domain expert:** "No. Active Recall is a **Turn Context Provider**. It can search however it wants, but the **Kernel** owns how that context is ordered and inserted."

## Flagged Ambiguities

- "hook" was used for pre-turn prompt context, post-turn memory work, startup/shutdown lifecycle, and tool-call policy. Resolved: use **Turn Context Provider**, **Turn Observer**, lifecycle task, or tool policy capability as appropriate.
- "capability" was used for both user/Paw-facing operations and infrastructure seams. Resolved: use **Capability** for searchable/selectable/invokable surfaces, and **Adapter** for infrastructure implementations.
- "agent harness" was used as a capability type. Resolved: use **Agent Runtime Adapter** for the runtime seam.
- "subagent" was used for plugin contribution, persona, and runtime execution. Resolved: plugins may contribute **Agent Profiles**; the kernel creates **Delegated Agent Jobs** through **Agent Runtime Adapters**. UI copy may still call a delegated job a subagent run when that is clearer to users.
