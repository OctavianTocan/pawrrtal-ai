# Workspace (live task state)

> Replace this template on your first real task. The dream cycle auto-archives
> this file after 2 days of inactivity — don't keep long-lived notes here.

## Current task
Specified agent contexts and sandbox runtime as `specs/008-agent-context-sandbox-runtime/`, then strengthened `specs/006-claude-agent-conversation-engine/` into an agent-provider conversation abstraction with Claude as the first proving provider.

## Open files
- `specs/006-claude-agent-conversation-engine/spec.md`
- `specs/008-agent-context-sandbox-runtime/spec.md`

## Active hypotheses
- Pawrrtal should stay scoped as a production-quality private gateway for trusted users now, with public hostile multi-tenancy deferred.
- `006` should prove the abstraction with Claude plus at least one second compatible provider or deterministic provider proof, so future SDK/CLI/hosted/local providers fit the same conversation shape.
- Agent Vault is relevant as an agent-facing credential brokerage pattern for `008`; self-hosted Infisical remains the source of truth.

## Checkpoints
- [x] Read local AGENTS/memory/permissions and SpecKit specify skill.
- [x] Researched Nanoclaw context/container model from prior source evidence and checked Infisical Agent Vault docs.
- [x] Created `008` spec and requirements checklist.
- [x] Updated `006` so the provider abstraction is P1 and requires a second provider proof.
- [x] Updated `.specify/feature.json` back to `specs/006-claude-agent-conversation-engine` for the latest requested spec target.

## Next step
Run `/speckit-plan` for `006` if the next step is the provider conversation abstraction; run `/speckit-plan` for `008` if the next step is contexts/sandbox/secrets.
