# Feature Specification: Visual Verification Harness & Golden References

**Feature Branch**: `002-telegram-visual-harness`

**Created**: 2026-06-19

**Status**: Draft

**Input**: User description: "Telegram visual testing harness and golden reference library so the agent and maintainer can verify what messages actually look like on chat surfaces, not just that they work, including time-delayed flows like reminders"

## User Scenarios & Testing *(mandatory)*

> Actors: the **maintainer** (a trusted human operator) and the **coding agent** doing development/QA. This is a development & quality tool, not an end-user product surface — but the references it produces double as the acceptance criteria for every rendering feature (cage rendering, rich media, verbosity).

### User Story 1 - See the real rendered output, as the user sees it (Priority: P1)

The agent (or maintainer) runs a chat flow and gets back a faithful capture of what the chat surface **actually displayed** — the real rendered messages, not the underlying API/stream payload. This closes the gap where "it works" was claimed from the CLI/API level while the on-surface display was broken or ugly.

**Why this priority**: This is the core value and the whole reason for the feature — grounding "it works" in the real rendering. Nothing else in this spec matters without it.

**Independent Test**: Run a known prompt through a chat surface and confirm the harness returns a faithful representation of the rendered messages a user would see, distinct from the raw payload.

**Acceptance Scenarios**:

1. **Given** a chat flow is run, **When** the harness captures it, **Then** the result reflects what was actually displayed on the surface (formatting, message boundaries, tool/reasoning rows), not just the text the model emitted.
2. **Given** a flow that streams, **When** captured, **Then** the capture includes the meaningful intermediate states (partial text, reasoning appearing, a tool call and its result), because how it looks *while streaming* is part of "looks good."
3. **Given** the capture completes, **When** reviewed, **Then** the agent can point to it as evidence rather than asserting success blindly.

---

### User Story 2 - Compare against an approved "this is what it should look like" reference (Priority: P2)

There is a curated library of approved reference examples — one per kind of message, per surface — defining how each should look. A captured output can be checked against the matching reference, and any divergence is surfaced for review.

**Why this priority**: Capturing the real output (P1) tells you *what* it looks like; the reference library tells you whether that's *correct*. It's what turns the harness from a viewer into a regression gate.

**Independent Test**: Capture the output for a given message kind, compare it to that kind's approved reference, and get a clear pass-or-divergence result.

**Acceptance Scenarios**:

1. **Given** an approved reference for a message kind exists, **When** a fresh capture of that kind is compared to it, **Then** the harness reports either a match or the specific differences.
2. **Given** a divergence is found, **When** the maintainer judges it correct, **Then** they can approve it as the new reference; **When** they judge it a regression, **Then** it stands as a flagged failure.
3. **Given** a message kind has no reference yet, **When** compared, **Then** the harness reports "no reference" rather than a false pass.

---

### User Story 3 - Verify time-delayed and event-driven flows on demand (Priority: P3)

Flows that normally take real-world time to fire — reminders, scheduled messages — can be triggered on demand so their delivered rendering can be verified immediately, instead of waiting for the actual delay.

**Why this priority**: Several important flows are time-based; without on-demand triggering they're effectively unverifiable, and "looks right when it fires" is exactly what tends to silently break.

**Independent Test**: Schedule a reminder, trigger it on demand through the harness, and confirm the delivered message's rendering matches its reference — without waiting the real delay.

**Acceptance Scenarios**:

1. **Given** a scheduled/reminder flow, **When** the harness triggers it on demand, **Then** the delivered message is produced and can be captured + compared now, not after the real delay.
2. **Given** a triggered time-delayed message, **When** captured, **Then** it is verified against its own reference like any other message kind.

---

### User Story 4 - One harness, every surface (Priority: P4)

The same capture-and-compare approach extends beyond Telegram to the web app and other chat surfaces, each checked against its own surface-appropriate reference — so a rendering regression on any surface is catchable, and a message that must "read identically across channels" can be confirmed to do so.

**Why this priority**: Telegram is where the pain is today (so it comes first), but the value compounds when the same gate covers every surface and enforces cross-surface consistency.

**Independent Test**: Run the same flow on Telegram and at least one other surface and get a capture + comparison for each, against that surface's references.

**Acceptance Scenarios**:

1. **Given** a flow run on Telegram, **When** captured + compared, **Then** it is checked against Telegram references.
2. **Given** the same flow on another surface, **When** captured + compared, **Then** it is checked against that surface's references, surfacing any cross-surface inconsistency.

---

### Edge Cases

- A captured output **diverges** from its approved reference → the divergence is made visible and stands as a failure until a human approves a new reference; the agent cannot truthfully report success while it diverges.
- A message kind has **no reference yet** → reported as "uncovered," never a silent pass.
- **Streaming/intermediate** states differ from the final message → both the in-flight states and the final state are capturable, since both must look right.
- A **time-delayed** flow can't be waited out → triggerable on demand.
- The **same message renders differently per surface** → each surface has its own reference; cross-surface inconsistencies are surfaced rather than hidden.
- A flow would touch **real user accounts/chats** → the harness runs against a dedicated test surface and never disturbs real users.
- **Very long or rapid** output → the capture remains faithful and readable for the whole flow.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let the agent or maintainer capture the actual rendered output of an agent turn on a chat surface — what an end user would see — distinct from the underlying stream/API payload.
- **FR-002**: A capture MUST be able to include the meaningful intermediate states of a streamed turn (partial text, reasoning, a tool call appearing, its result), not only the final message.
- **FR-003**: The system MUST maintain a curated library of approved "golden" reference examples defining how each kind of message should look on each supported surface (at minimum: streamed answer, reasoning, tool-call trace, tool result, reminder/scheduled message, error, rich-media message, and verbosity on/off states).
- **FR-004**: The system MUST let a capture be compared against the matching reference and present the differences in a reviewable form.
- **FR-005**: A human MUST be able to approve or update a golden reference; references are human-curated truth, never auto-accepted as correct.
- **FR-006**: The system MUST let time-delayed or event-driven flows (reminders, scheduled messages) be triggered on demand so their delivered rendering can be verified without waiting real-world time.
- **FR-007**: The verification approach MUST extend across all supported chat surfaces — Telegram first, others using their own surface-appropriate references — so a regression on any surface is catchable.
- **FR-008**: When a capture diverges from its approved reference, the system MUST make the divergence visible to the agent and maintainer, so success cannot be truthfully claimed while the rendering is broken.
- **FR-009**: The harness MUST be runnable on demand — by the agent during development and by the maintainer — against a real running instance, **without disturbing real user accounts or chats** (it uses a dedicated test surface).
- **FR-010**: A capture and its comparison MUST be reproducible for the same input, so a pass is meaningful and a regression is attributable.
- **FR-011**: The harness MUST observe and verify rendering only; it MUST NOT change how turns are produced or rendered (it is a gate, not a renderer).

### Key Entities *(include if feature involves data)*

- **Rendered capture**: a faithful representation of what a surface displayed for a turn, including relevant intermediate (streaming) states.
- **Golden reference**: a human-approved example of how a given message kind should look on a given surface; the source of truth for "looks right."
- **Message kind**: the category of output under verification (streamed answer, reasoning, tool-call trace, tool result, reminder, error, rich media, verbosity state, …).
- **Comparison result**: the outcome of checking a capture against its reference — match, divergence (with the differences), or uncovered (no reference).
- **On-demand trigger**: a way to fire a time-delayed/scheduled flow immediately for verification.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any supported message kind, the agent or maintainer can produce a faithful capture of its real rendered output in under ~2 minutes, without touching real user chats.
- **SC-002**: 100% of the defined message kinds have at least one approved reference per supported surface.
- **SC-003**: A rendering regression in any covered message kind is flagged by a comparison run before it reaches a real user.
- **SC-004**: A time-delayed flow (e.g., a reminder) can be verified on demand in minutes, regardless of its real configured delay.
- **SC-005**: Every "this Telegram flow works" claim is backed by a capture + comparison artifact for the primary message kinds involved — zero unverified "it works" claims.
- **SC-006**: The same flow can be captured and compared on Telegram and at least one other surface from the single harness.

## Assumptions

- A **test surface already exists** (a dedicated bot + test chat the maintainer set up); provisioning and authenticating that surface is **out of scope** for this feature.
- "Looks good" is defined by **human-approved references**, not an automated aesthetic judgment — the harness surfaces differences; a human decides what is correct.
- **Telegram is the first surface** (where the rendering pain is today); the approach is designed to extend to web, other chat surfaces, and eventually mobile.
- Audience is a **handful of trusted users**; the harness is a development/QA tool. Its references are **reused as the acceptance criteria** for rendering features (cage rendering, rich media, verbosity toggles), so this feature does not preclude broader use later.
- **Rich-media and verbosity-state** message kinds are *verified* here, but *building* those rendering features lives in their own specs.

## Dependencies

- Relies on the maintainer's existing test-surface setup (a dedicated bot + chat) to drive a real surface safely.
- Observes the streaming/rendered output the app already produces; this feature does not modify rendering.
- The golden reference library becomes shared acceptance criteria that other rendering features are checked against.
