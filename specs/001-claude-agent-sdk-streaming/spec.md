# Feature Specification: Claude Agent SDK Streaming Model

**Feature Branch**: `001-claude-agent-sdk-streaming`

**Created**: 2026-06-15

**Status**: Draft

**Input**: User description: "Reintroduce the Claude Agent SDK as a streaming model option selectable by users, rendering live incremental output like Claude Code across web and Telegram, running through the same tool-permission and safety guarantees as every other model, available alongside the existing Claude Code PTY option"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Live, Claude-Code-style streaming from a Claude model (Priority: P1)

A person chatting in the app selects a Claude model and sends a message. The answer appears **as it is produced** — text streams in incrementally, the model's reasoning is shown as it thinks, and any tool the model uses is shown the moment it runs, together with the result — rather than the user staring at a spinner until a finished block arrives. The experience matches the live, step-by-step feel of Claude Code itself.

**Why this priority**: This is the core value of the feature. Without live incremental streaming there is no observable benefit over the status quo. It is the smallest slice that is demonstrable and delivers value on its own.

**Independent Test**: Select a Claude model, send a prompt that triggers reasoning and at least one tool action, and confirm text, reasoning, and tool-call/tool-result steps appear incrementally during the turn (not only at completion), ending with a complete answer.

**Acceptance Scenarios**:

1. **Given** a Claude model is selected, **When** the user sends a message, **Then** partial answer text becomes visible while the model is still responding.
2. **Given** the model chooses to use a tool mid-answer, **When** the tool runs, **Then** the user sees the tool action and its result appear as they happen.
3. **Given** the model produces intermediate reasoning, **When** it is thinking, **Then** that reasoning is surfaced live and distinguished from the final answer.
4. **Given** the response completes, **When** the turn ends, **Then** the user sees a single coherent final answer with no duplicated or dropped content.

---

### User Story 2 - Same safety and tool-permission guarantees as every other model (Priority: P2)

A user (and the operator who trusts the system) can rely on Claude turns being governed by the **same** tool-permission checks and the **same** runaway-protection limits as every other model. A tool the user or policy disallows does not run; a turn cannot loop or run without bound.

**Why this priority**: This is the guarantee whose absence caused the previous Claude integration to be removed. It is mandatory for real use, but it layers onto the streaming slice rather than being independently demoable to an end user, so it follows P1.

**Independent Test**: Configure a disallowed tool and a low runaway bound; run a Claude turn that attempts the disallowed tool and a turn that would otherwise loop, and confirm the disallowed tool is blocked and the turn stops in a controlled way — identical to the outcome for other models.

**Acceptance Scenarios**:

1. **Given** a tool is disallowed by policy, **When** a Claude turn attempts to use it, **Then** the tool does not execute, the denial is surfaced, and the turn continues safely.
2. **Given** the standard runaway-protection bound, **When** a Claude turn would exceed it, **Then** the turn stops in a controlled way with a clear notice, the same way other models do.
3. **Given** an allowed tool, **When** a Claude turn uses it, **Then** it executes through the same permission path other models use and its result is shown.

---

### User Story 3 - Consistent experience across all chat surfaces (Priority: P3)

The same Claude streaming behavior renders correctly on every chat surface the app supports (the web app and messaging surfaces such as Telegram), each in that surface's established style — no surface is left with a broken or degraded rendering of Claude output.

**Why this priority**: Broad reach matters, but a single working surface already delivers the core value, so multi-surface parity follows the first two stories.

**Independent Test**: Send the same Claude prompt on the web app and on a messaging surface and confirm both render a coherent live trace (incremental text, reasoning, tool steps) appropriate to that surface, with no missing or malformed output.

**Acceptance Scenarios**:

1. **Given** a Claude turn on the web app, **When** it streams, **Then** the user sees the live trace in the web app's normal style.
2. **Given** the same kind of Claude turn on a messaging surface, **When** it streams, **Then** the user sees a coherent live trace in that surface's normal style.
3. **Given** any supported surface, **When** a Claude turn completes, **Then** the final rendered result is equivalent in content to the other surfaces.

---

### User Story 4 - Operator enablement alongside the existing Claude option (Priority: P4)

An operator enables the new Claude option using an existing Claude subscription. The **previously available** Claude option keeps working unchanged, and users can choose either. If the new option is not configured or its credentials are invalid, the system gracefully falls back rather than failing.

**Why this priority**: Enablement and coexistence are required to ship safely, but they are operator-facing and depend on the user-facing slices existing first.

**Independent Test**: Enable the new option with valid credentials and confirm it is selectable and works; confirm the existing Claude option still works unchanged; then remove/invalidate the credentials and confirm turns fall back gracefully with a clear notice.

**Acceptance Scenarios**:

1. **Given** valid Claude subscription credentials are configured, **When** a user opens the model picker, **Then** the new Claude option is selectable alongside the existing Claude option.
2. **Given** the new option is enabled, **When** a user uses the pre-existing Claude option, **Then** it behaves exactly as before with no regression.
3. **Given** credentials are missing or invalid, **When** a user selects the new Claude option, **Then** the turn falls back to an available model and the user is clearly informed, without the turn erroring out.

---

### Edge Cases

- **Credentials missing/expired/invalid**: the turn falls back to an available model with a clear, user-visible notice; it never silently fails or crashes the conversation.
- **Underlying Claude capability unavailable in the running environment**: the system reports a clear, understandable message and does not crash the conversation or disturb other models.
- **Disallowed tool requested mid-turn**: the tool is blocked, the denial is surfaced, and the turn continues safely.
- **Runaway / overly long agentic turn**: bounded by the same protection as other models, producing a controlled stop.
- **Switching between the new and existing Claude options within one conversation**: prior context is handled gracefully without corrupting the thread.
- **Client disconnects mid-stream**: in-flight work is cleaned up; no orphaned activity or duplicate accounting.
- **Very fast / very long output**: rendering on each surface stays responsive and readable for the whole stream.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to select a Claude model as the responder for a conversation.
- **FR-002**: The system MUST stream Claude responses incrementally — partial answer text becomes visible while the model is still responding, not only upon completion.
- **FR-003**: The system MUST surface, as they occur during a Claude turn, the model's intermediate reasoning and each tool action together with its result.
- **FR-004**: Claude turns MUST be subject to the same tool-permission decisions as every other model; a tool disallowed by the user or policy MUST NOT execute.
- **FR-005**: Claude turns MUST be subject to the same runaway-protection bounds as every other model and MUST produce a controlled stop with a clear notice when a bound is reached.
- **FR-006**: The system MUST render Claude's live output coherently on every supported chat surface, each in that surface's established style.
- **FR-007**: The system MUST preserve conversation context across multiple turns with a Claude model (multi-turn continuity), consistent with other models.
- **FR-008**: Operators MUST be able to enable Claude access using an existing Claude subscription.
- **FR-009**: The newly added Claude option MUST coexist with the pre-existing Claude option; both remain selectable and the pre-existing option MUST continue to function unchanged.
- **FR-010**: When Claude access is not configured or its credentials are invalid/expired, the system MUST fall back to an available model and clearly inform the user, without failing the turn.
- **FR-011**: When the underlying Claude capability is unavailable in the running environment, the system MUST report a clear, user-understandable error and MUST NOT crash the conversation or affect other models.
- **FR-012**: Token and cost accounting for Claude turns MUST be recorded consistently with other models.
- **FR-013**: A user or operator MUST be able to verify a Claude turn end-to-end (send a message, receive a streamed answer) through the app's standard verification path.

### Key Entities *(include if feature involves data)*

- **Claude model option**: a selectable model the user can choose as responder, presented alongside other models (including the pre-existing Claude option).
- **Conversation**: the multi-turn thread; carries the continuity context for the chosen model across turns.
- **Response stream**: the ordered sequence of incremental outputs a turn emits — partial text, reasoning, tool action, tool result, completion, and usage — consumed identically by every surface.
- **Operator Claude connection**: the configured subscription-based access that enables the new Claude option for the deployment.
- **Usage record**: the per-turn token/cost accounting captured for a Claude turn.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can select a Claude model and receive a streamed response in which the first visible output appears within ~2 seconds under normal conditions.
- **SC-002**: 100% of Claude tool actions resolve to the same permission outcome as the equivalent action on other models — there are zero instances of an ungated tool executing.
- **SC-003**: Zero Claude turns run without bound — every Claude turn either completes or stops under the same runaway-protection limit applied to other models.
- **SC-004**: The same Claude prompt produces a coherent live trace on every supported surface (the web app and at least one messaging surface) in a single demonstration, with equivalent final content.
- **SC-005**: Enabling the new Claude option introduces zero regressions to the pre-existing Claude option and to other models — existing flows continue to pass their checks.
- **SC-006**: When credentials are missing or invalid, 100% of affected turns fall back gracefully with a user-visible notice rather than erroring out.
- **SC-007**: Token and cost are recorded for 100% of completed Claude turns.

## Assumptions

- The person selecting models is an authenticated app user; the person enabling Claude access is the deployment operator.
- "Stream like Claude Code" means surfacing incremental answer text, the model's reasoning, and the live tool-call/tool-result trace — consistent with how the app already renders streaming for its other models.
- All currently supported chat surfaces are in scope; each renders in its existing style and this feature introduces no new surface-specific UI.
- Claude turns expose **the app's existing tool set** (not Claude's separate built-in tools), so the safety and permission story stays identical to other models.
- The set of selectable Claude models follows the current Claude model lineup; the exact list is finalized during planning.
- Multi-turn continuity for Claude mirrors the continuity behavior already provided for other models.
- Access uses the operator's existing Claude subscription, consistent with the prior Claude integration; per-request metered API-key billing is not the default path.
- The pre-existing Claude option remains the canonical fallback target when the new option is unavailable.

## Dependencies

- Integrates with (does not duplicate) the app's existing mechanisms for model selection, incremental streaming, multi-turn continuity, tool-permission checking, runaway-protection bounding, unavailable-model fallback, and usage accounting.
- Requires valid Claude subscription credentials configured by the operator.
- Depends on the running environment being able to host the capability that drives Claude; confirming this for each deployment target (notably the hosted backend) is a planning-phase research dependency.
