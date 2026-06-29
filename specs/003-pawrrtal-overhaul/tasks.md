# Tasks: Pawrrtal Platform Overhaul

**Input**: Design documents from `/mnt/work/code/personal/pawrrtal/specs/003-pawrrtal-overhaul/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, `.specify/memory/constitution.md`

**Tests**: Include the smallest meaningful proof for each touched surface. New behavior gets a focused test or an explicit stronger verification gate.

**Organization**: Tasks are grouped by the 16 user stories in `spec.md`, with the new Step 0A setup/customization spine kept inside US1 because it is part of the thin-core/agent-operable story.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare the existing repo to execute the umbrella plan without creating a second feature track.

- [ ] T001 Confirm `.specify/feature.json` still points to `specs/003-pawrrtal-overhaul` in `.specify/feature.json`
- [ ] T002 [P] Record the active validation gates from `specs/003-pawrrtal-overhaul/quickstart.md` in `specs/003-pawrrtal-overhaul/tasks.md`
- [ ] T003 [P] Reconcile the current repo setup docs against the Step 0A requirement in `README.md`
- [ ] T004 [P] Reconcile agent-facing repo instructions against the Step 0A requirement in `AGENTS.md`
- [ ] T005 [P] Audit existing `paw` setup, doctor, env, and project commands in `backend/app/cli/paw/commands/doctor.py`, `backend/app/cli/paw/commands/project/cli.py`, and `backend/app/cli/paw/main.py`
- [ ] T006 [P] Audit current backend-ts test collection behavior in `backend-ts/package.json`
- [ ] T007 [P] Audit current backend-ts duplicate test trees in `backend-ts/apps/api/test/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the shared guardrails that every user story depends on.

**CRITICAL**: No implementation slice should proceed until these foundation tasks are complete.

- [ ] T008 Add the Removal Completeness Matrix shell referenced by Step 4.1 in `specs/003-pawrrtal-overhaul/plan.md`
- [ ] T009 [P] Add the Step 0A validation checklist from `quickstart.md` to `specs/003-pawrrtal-overhaul/quickstart.md`
- [ ] T010 [P] Add an explicit generated-client ownership note for future API work in `backend-ts/packages/api-core/CONVENTIONS.md`
- [ ] T011 [P] Add package-boundary notes for `@platform/*`, `@pawrrtal/kernel`, `@clients/*`, and app packages in `backend-ts/CONVENTIONS.md`
- [ ] T012 Add the first build-boundary check placeholder for SDK-to-app forbidden imports in `scripts/sentrux-check.sh`
- [ ] T013 Add a backend-ts test-gate repair plan note to `backend-ts/README.md`
- [ ] T014 Verify foundation with `UV_CACHE_DIR=/tmp/pawrrtal-uv-cache just check` from `/mnt/work/code/personal/pawrrtal`

**Checkpoint**: Foundation ready; user story implementation can now begin in priority order.

---

## Phase 3: User Story 1 - Tiny Agent SDK Core + Agent-Operable Repo (Priority: P1) MVP

**Goal**: Make Pawrrtal's core thin and make the repo teach coding agents how to bootstrap, recover, and customize it without hidden context.

**Independent Test**: From a fresh checkout, an agent follows `README.md` and `AGENTS.md`, runs the setup/doctor dry-run path, validates typed config, wires one requested capability, and confirms the SDK boundary has no app imports.

### Tests for User Story 1

- [ ] T015 [P] [US1] Add `paw setup --dry-run --json` CLI tests in `backend/tests/paw/test_command_setup.py`
- [ ] T016 [P] [US1] Add setup config schema validation tests in `backend/tests/paw/test_setup_config.py`
- [ ] T017 [P] [US1] Add SDK forbidden-import check tests in `backend-ts/apps/api/test/Architecture/sdk-boundary.test.ts`
- [ ] T018 [P] [US1] Add root instruction drift tests for setup guidance in `backend/tests/test_agents_md.py`

### Implementation for User Story 1

- [ ] T019 [US1] Implement the `paw setup` Typer command surface in `backend/app/cli/paw/commands/setup.py`
- [ ] T020 [US1] Register the `setup` subcommand in `backend/app/cli/paw/main.py`
- [ ] T021 [P] [US1] Add typed setup config models and validation helpers in `backend/app/cli/paw/setup_config.py`
- [ ] T022 [P] [US1] Add setup config example data in `config/pawrrtal.setup.example.json`
- [ ] T023 [P] [US1] Add setup config JSON Schema in `config/pawrrtal.setup.schema.json`
- [ ] T024 [US1] Extend `paw doctor --json` with setup-resume and config-check sections in `backend/app/cli/paw/commands/doctor.py`
- [ ] T025 [US1] Add agent-readable setup/recovery instructions in `README.md`
- [ ] T026 [US1] Add coding-agent customization rules for setup/config/capabilities in `AGENTS.md`
- [ ] T027 [P] [US1] Add repo-local setup spine skill instructions in `.agents/skills/setup-spine/SKILL.md`
- [ ] T028 [P] [US1] Add capability-install skill instructions in `.agents/skills/add-capability/SKILL.md`
- [ ] T029 [US1] Create SDK package skeleton in `backend-ts/packages/kernel/package.json`
- [ ] T030 [US1] Create kernel port declarations in `backend-ts/packages/kernel/src/Ports.ts`
- [ ] T031 [US1] Create platform package skeleton in `backend-ts/packages/platform/package.json`
- [ ] T032 [US1] Wire `backend-ts/package.json` workspaces for `packages/kernel`, `packages/platform`, and `packages/clients/*`
- [ ] T033 [US1] Document the setup spine verification flow in `specs/003-pawrrtal-overhaul/quickstart.md`

**Checkpoint**: US1 is functional when `paw setup --dry-run --json`, `paw doctor --config --json`, `just check`, and the SDK-boundary test pass.

---

## Phase 4: User Story 2 - One TypeScript / Effect Codebase, One Paw CLI With Two Roles (Priority: P1)

**Goal**: Start the complete Python-to-Effect migration by proving the CLI split between kernel-only agent commands and Pawrrtal operator commands.

**Independent Test**: The Effect `paw` package can run an agent command without a Pawrrtal HTTP service and an operator command through the typed contract.

### Tests for User Story 2

- [ ] T034 [P] [US2] Add Effect CLI command tests in `backend-ts/apps/paw/test/PawCli.test.ts`
- [ ] T035 [P] [US2] Add Python-to-Effect parity tests for current verify commands in `backend/tests/paw/test_verify_all.py`
- [ ] T036 [P] [US2] Add backend-ts vitest collection regression tests in `backend-ts/apps/api/test/VitestCollection.test.ts`

### Implementation for User Story 2

- [ ] T037 [US2] Remove the false-green `--passWithNoTests` behavior from `backend-ts/package.json`
- [ ] T038 [US2] Deduplicate backend-ts test trees under `backend-ts/apps/api/test/`
- [ ] T039 [US2] Create the Effect `paw` app package in `backend-ts/apps/paw/package.json`
- [ ] T040 [US2] Implement the Effect `paw` entrypoint in `backend-ts/apps/paw/src/Main.ts`
- [ ] T041 [P] [US2] Implement kernel-only agent command placeholders in `backend-ts/apps/paw/src/AgentCommands.ts`
- [ ] T042 [P] [US2] Implement operator command placeholders using the generated client in `backend-ts/apps/paw/src/OperatorCommands.ts`
- [ ] T043 [US2] Add `apps/paw` to `backend-ts/package.json` workspaces
- [ ] T044 [US2] Document the Python `paw` to Effect `paw` transition in `backend/app/cli/paw/__init__.py`

**Checkpoint**: US2 is functional when backend-ts tests collect real assertions and the Effect `paw` package has tested agent/operator command boundaries.

---

## Phase 5: User Story 3 - Normalized Gateway for Models and CLI Harnesses (Priority: P1)

**Goal**: Define and implement one gateway contract that can drive raw models and full agent CLIs.

**Independent Test**: Two provider styles produce the same normalized parts stream with truthful capability manifests.

### Tests for User Story 3

- [ ] T045 [P] [US3] Add gateway contract tests in `backend-ts/packages/api-core/test/GatewayContract.test.ts`
- [ ] T046 [P] [US3] Add provider manifest tests in `backend/tests/test_provider_labels.py`
- [ ] T047 [P] [US3] Add ACP adapter unit tests in `backend-ts/apps/api/test/Modules/Gateway/AcpProvider.test.ts`

### Implementation for User Story 3

- [ ] T048 [US3] Add gateway Domain types in `backend-ts/packages/api-core/src/Modules/Gateway/Domain.ts`
- [ ] T049 [US3] Add gateway HttpApi group in `backend-ts/packages/api-core/src/Modules/Gateway/Api.ts`
- [ ] T050 [US3] Add gateway RpcProtocol group in `backend-ts/packages/api-core/src/Modules/Gateway/RpcProtocol.ts`
- [ ] T051 [US3] Add gateway errors in `backend-ts/packages/api-core/src/Modules/Gateway/Errors.ts`
- [ ] T052 [US3] Export the gateway group from `backend-ts/packages/api-core/src/Api.ts`
- [ ] T053 [P] [US3] Add the `@clients/acp` package skeleton in `backend-ts/packages/clients/acp/package.json`
- [ ] T054 [P] [US3] Implement ACP client config and errors in `backend-ts/packages/clients/acp/src/Config.ts` and `backend-ts/packages/clients/acp/src/Errors.ts`
- [ ] T055 [US3] Implement host-side gateway service in `backend-ts/apps/api/src/Modules/Gateway/Service.ts`
- [ ] T056 [US3] Implement host-side gateway HTTP layer in `backend-ts/apps/api/src/Modules/Gateway/Http.ts`
- [ ] T057 [US3] Implement host-side gateway RPC layer in `backend-ts/apps/api/src/Modules/Gateway/Rpc.ts`

**Checkpoint**: US3 is functional when a model provider and an ACP agent provider both stream through the same `parts[]` contract.

---

## Phase 6: User Story 4 - Disposable Sandboxes for Agents and CLIs (Priority: P1)

**Goal**: Run agent work and CLI harnesses inside a pluggable sandbox slot with `local-confined` as the default.

**Independent Test**: A command runs inside `local-confined`, cannot write outside its confined CWD, has network disabled, and streams output.

### Tests for User Story 4

- [ ] T058 [P] [US4] Add sandbox port tests in `backend-ts/packages/kernel/test/SandboxRuntime.test.ts`
- [ ] T059 [P] [US4] Add local-confined runtime tests in `backend-ts/packages/sandbox-local-confined/test/LocalConfinedRuntime.test.ts`
- [ ] T060 [P] [US4] Add sandbox CLI smoke tests in `backend/tests/paw/test_command_setup.py`

### Implementation for User Story 4

- [ ] T061 [US4] Define the `SandboxRuntime` port in `backend-ts/packages/kernel/src/SandboxRuntime.ts`
- [ ] T062 [US4] Add sandbox domain types in `backend-ts/packages/api-core/src/Modules/Sandbox/Domain.ts`
- [ ] T063 [US4] Create the local-confined package in `backend-ts/packages/sandbox-local-confined/package.json`
- [ ] T064 [US4] Implement the local-confined runtime in `backend-ts/packages/sandbox-local-confined/src/LocalConfinedRuntime.ts`
- [ ] T065 [US4] Add sandbox runtime manifest metadata in `backend-ts/packages/sandbox-local-confined/src/Manifest.ts`
- [ ] T066 [US4] Add sandbox setup checks to `backend/app/cli/paw/commands/setup.py`

**Checkpoint**: US4 is functional when `local-confined` runs a streamed command and refuses out-of-scope filesystem/network access.

---

## Phase 7: User Story 5 - Infisical Secrets, No Plaintext (Priority: P1)

**Goal**: Route app, CLI, CI, and sandbox secrets through self-hosted Infisical while preserving the separate workspace/user secret plane.

**Independent Test**: A repo scan finds no plaintext secrets, and every surface resolves secret references through the configured runtime path.

### Tests for User Story 5

- [ ] T067 [P] [US5] Add secret redaction tests in `backend/tests/test_secret_redaction.py`
- [ ] T068 [P] [US5] Add Infisical config validation tests in `backend/tests/paw/test_setup_config.py`
- [ ] T069 [P] [US5] Add service secret target tests in `backend/tests/paw/test_command_services.py`

### Implementation for User Story 5

- [ ] T070 [US5] Add Infisical setup config fields in `backend/app/cli/paw/setup_config.py`
- [ ] T071 [US5] Add Infisical runtime checks to `backend/app/cli/paw/commands/setup.py`
- [ ] T072 [US5] Update service secret validation in `backend/app/cli/paw/commands/services/bws.py`
- [ ] T073 [US5] Document the runtime secret plane in `README.md`
- [ ] T074 [US5] Document the workspace/user secret plane in `AGENTS.md`
- [ ] T075 [US5] Add no-plaintext secret scan instructions to `specs/003-pawrrtal-overhaul/quickstart.md`

**Checkpoint**: US5 is functional when secret checks pass without printing or committing secret values.

---

## Phase 8: User Story 6 - Shed Permission, Budget, Telemetry, and Workspace Dead Weight (Priority: P2)

**Goal**: Remove unused systems before migration while keeping logging and replacing safety with isolation.

**Independent Test**: Removed systems have no imports, runtime routes, docs, or hidden dependencies, and logging still works.

### Tests for User Story 6

- [ ] T076 [P] [US6] Add removal matrix import tests in `backend/tests/test_governance_audit.py`
- [ ] T077 [P] [US6] Add logging retention tests in `backend/tests/test_observability_agent_trace.py`
- [ ] T078 [P] [US6] Add sentrux boundary expectations for removed systems in `.sentrux/rules.toml`

### Implementation for User Story 6

- [ ] T079 [US6] Complete the Removal Completeness Matrix in `specs/003-pawrrtal-overhaul/plan.md`
- [ ] T080 [US6] Remove permission-system references from `backend/app/`
- [ ] T081 [US6] Remove budget-system references from `backend/app/`
- [ ] T082 [US6] Remove telemetry-system references from `backend/app/`
- [ ] T083 [US6] Remove legacy workspace-system references from `backend/app/`
- [ ] T084 [US6] Update docs for removed systems in `README.md`
- [ ] T085 [US6] Delete or replace obsolete deployment references in `docker-compose.yml` and `docker-compose.dev.yml`

**Checkpoint**: US6 is functional when imports, docs, and runtime behavior prove the removed systems are gone and logging remains.

---

## Phase 9: User Story 7 - Claude as a First-Class Streaming Model (Priority: P2)

**Goal**: Keep spec 001 aligned with the new gateway, parts, and removal decisions.

**Independent Test**: Claude streams text, reasoning, and tool steps through the same parts renderer as other providers.

### Tests for User Story 7

- [ ] T086 [P] [US7] Add Claude parts-stream parity tests in `backend/tests/test_agent_loop_scenarios.py`
- [ ] T087 [P] [US7] Add Claude model selection tests in `frontend/features/chat/hooks/use-chat-models.test.ts`

### Implementation for User Story 7

- [ ] T088 [US7] Reconcile `specs/001-claude-agent-sdk-streaming/spec.md` against `specs/003-pawrrtal-overhaul/contracts/message-parts.md`
- [ ] T089 [US7] Update Claude provider manifest behavior in `backend/app/providers/claude/provider.py`
- [ ] T090 [US7] Update Claude rendering assumptions in `frontend/components/ai-elements/message.tsx`
- [ ] T091 [US7] Verify Claude through `backend/app/cli/paw/verify/all_providers.py`

**Checkpoint**: US7 is functional when Claude streams through the shared message parts contract.

---

## Phase 10: User Story 8 - Clean Model Catalog and Reasoning-Effort Knob (Priority: P2)

**Goal**: Show each model once and move reasoning depth to a separate control.

**Independent Test**: The picker shows one entry per model, and the effort selector changes thinking depth without duplicate model IDs.

### Tests for User Story 8

- [ ] T092 [P] [US8] Add catalog normalization tests in `backend/tests/test_catalog.py`
- [ ] T093 [P] [US8] Add model picker tests in `frontend/features/chat/hooks/use-chat-models.test.ts`
- [ ] T094 [P] [US8] Add reasoning selector tests in `frontend/features/chat/lib/model-selection.test.ts`

### Implementation for User Story 8

- [ ] T095 [US8] Normalize backend catalog entries in `backend/app/providers/catalog.py`
- [ ] T096 [US8] Update model ID parsing rules in `backend/app/providers/model_id.py`
- [ ] T097 [US8] Update frontend model selection helpers in `frontend/features/chat/lib/model-selection.ts`
- [ ] T098 [US8] Update chat model hook output in `frontend/features/chat/hooks/use-chat-models.ts`
- [ ] T099 [US8] Update picker copy and state handling in `frontend/features/chat/ChatView.tsx`

**Checkpoint**: US8 is functional when the same model no longer appears once per effort level.

---

## Phase 11: User Story 9 - Reliable Provider Auth and Configuration (Priority: P2)

**Goal**: Make provider auth paths, especially Antigravity/Google, reliable, documented, and clear on failure.

**Independent Test**: Valid credentials succeed; missing or expired credentials return a clear failure and a safe fallback.

### Tests for User Story 9

- [ ] T100 [P] [US9] Add Antigravity auth tests in `backend/tests/test_agy_api_auth.py`
- [ ] T101 [P] [US9] Add provider credential failure tests in `backend/tests/test_provider_selection.py`

### Implementation for User Story 9

- [ ] T102 [US9] Document Google/Antigravity auth setup in `README.md`
- [ ] T103 [US9] Add provider auth config validation to `backend/app/cli/paw/commands/setup.py`
- [ ] T104 [US9] Improve Antigravity credential handling in `backend/app/providers/agy_cli/provider.py`
- [ ] T105 [US9] Improve provider auth error messages in `backend/app/providers/factory.py`
- [ ] T106 [US9] Add provider auth verification to `backend/app/cli/paw/verify/all_providers.py`

**Checkpoint**: US9 is functional when configured auth succeeds and broken auth produces a clear actionable error.

---

## Phase 12: User Story 10 - Model-Agnostic Active Recall (Priority: P2)

**Goal**: Route active recall through the provider abstraction and keep it silent unless the turn needs memory.

**Independent Test**: Active recall works with two selected providers and emits nothing on generic prompts.

### Tests for User Story 10

- [ ] T107 [P] [US10] Add active recall provider-abstraction tests in `backend/tests/test_active_recall_security.py`
- [ ] T108 [P] [US10] Add memory silence tests in `backend/tests/test_lcm_expand_query.py`

### Implementation for User Story 10

- [ ] T109 [US10] Move active recall model calls behind provider selection in `backend/app/lcm/planner.py`
- [ ] T110 [US10] Tighten recall prompt behavior in `backend/app/lcm/pack.py`
- [ ] T111 [US10] Update LCM context output handling in `backend/app/lcm/observe.py`
- [ ] T112 [US10] Add `paw verify lcm` coverage in `backend/app/cli/paw/verify/lcm.py`

**Checkpoint**: US10 is functional when recall is provider-agnostic and quiet by default.

---

## Phase 13: User Story 11 - Trust What You See Visual Verification Harness (Priority: P2)

**Goal**: Keep spec 002 as the proof gate for rendering and streaming states.

**Independent Test**: A real rendered flow is captured and compared against a human-approved golden reference.

### Tests for User Story 11

- [ ] T113 [P] [US11] Add visual harness smoke tests in `backend/tests/test_paw_verify_telegram.py`
- [ ] T114 [P] [US11] Add web rendering smoke tests in `scripts/dev-console-smoke.mjs`

### Implementation for User Story 11

- [ ] T115 [US11] Reconcile `specs/002-telegram-visual-harness/spec.md` with `specs/003-pawrrtal-overhaul/contracts/message-parts.md`
- [ ] T116 [US11] Add harness invocation to `backend/app/cli/paw/verify/telegram.py`
- [ ] T117 [US11] Document visual proof requirements in `specs/003-pawrrtal-overhaul/quickstart.md`

**Checkpoint**: US11 is functional when rendered proof is available before claiming surface behavior works.

---

## Phase 14: User Story 12 - Rich Chat Surface and Verbosity Toggles (Priority: P3)

**Goal**: Render rich media and provide per-category visibility controls across Telegram and other chat surfaces.

**Independent Test**: Tool calls, thinking, active recall, and rich media can be shown or hidden independently.

### Tests for User Story 12

- [ ] T118 [P] [US12] Add Telegram verbosity toggle tests in `backend/tests/test_verbose_filter.py`
- [ ] T119 [P] [US12] Add rich-media rendering tests in `backend/tests/test_telegram_html.py`
- [ ] T120 [P] [US12] Add AI elements rendering tests in `frontend/components/ai-elements/message.test.tsx`

### Implementation for User Story 12

- [ ] T121 [US12] Implement per-category verbosity state in `backend/app/channels/telegram/`
- [ ] T122 [US12] Update Telegram inline controls in `backend/app/channels/telegram/`
- [ ] T123 [US12] Update rich media message rendering in `backend/app/channels/telegram/`
- [ ] T124 [US12] Update shared AI message rendering in `frontend/components/ai-elements/message.tsx`
- [ ] T125 [US12] Update design-system guidance for reusable visibility states in `DESIGN.md`

**Checkpoint**: US12 is functional when each visibility category toggles independently and rich media renders on supported surfaces.

---

## Phase 15: User Story 13 - BYO Telegram Bot and Headless Onboarding (Priority: P3)

**Goal**: Let a user bring a Telegram bot token and complete account/channel setup through API or CLI only.

**Independent Test**: A user is provisioned and chats through their own bot without opening the web app.

### Tests for User Story 13

- [ ] T126 [P] [US13] Add BYO bot API tests in `backend/tests/test_channels_api.py`
- [ ] T127 [P] [US13] Add headless CLI onboarding tests in `backend/tests/paw/test_command_backend_surface.py`

### Implementation for User Story 13

- [ ] T128 [US13] Add BYO Telegram bot schema to `backend/app/channels/router.py`
- [ ] T129 [US13] Add bot-token secret handling to `backend/app/channels/telegram/`
- [ ] T130 [US13] Add CLI channel linking flow to `backend/app/cli/paw/commands/channels.py`
- [ ] T131 [US13] Add headless onboarding docs to `README.md`
- [ ] T132 [US13] Add BYO bot verification to `backend/app/cli/paw/verify/telegram.py`

**Checkpoint**: US13 is functional when a custom bot can be linked and used entirely from the CLI/API.

---

## Phase 16: User Story 14 - Pluggable Agent Capabilities (Priority: P3)

**Goal**: Support transcription, OpenClaw plugins, and Mirage browsing as plugin capabilities layered outside the core.

**Independent Test**: Each capability installs and runs through the plugin surface without kernel edits.

### Tests for User Story 14

- [ ] T133 [P] [US14] Add transcription plugin tests in `backend/tests/test_xai_stt.py`
- [ ] T134 [P] [US14] Add OpenClaw plugin compatibility tests in `backend/tests/test_plugin_tools.py`
- [ ] T135 [P] [US14] Add browsing capability tests in `backend/tests/test_exa_search_agent.py`

### Implementation for User Story 14

- [ ] T136 [US14] Add transcription plugin manifest in `backend/app/plugins/builtin/transcription/plugin.json`
- [ ] T137 [US14] Add OpenClaw plugin adapter manifest in `backend/app/plugins/builtin/openclaw/plugin.json`
- [ ] T138 [US14] Add Mirage browsing manifest in `backend/app/plugins/builtin/mirage/plugin.json`
- [ ] T139 [US14] Add plugin capability docs to `.agents/skills/add-capability/SKILL.md`
- [ ] T140 [US14] Add plugin verification flow to `backend/app/cli/paw/commands/plugins.py`

**Checkpoint**: US14 is functional when all three capabilities can be installed, inspected, and exercised as plugins.

---

## Phase 17: User Story 15 - Pawrrtal Mobile Client (Priority: P3)

**Goal**: Add an Expo client that consumes the same typed contract and renders the same parts stream.

**Independent Test**: The mobile app sends a message and streams/render parts consistently with web.

### Tests for User Story 15

- [ ] T141 [P] [US15] Add mobile contract-client tests in `apps/mobile/test/api-client.test.ts`
- [ ] T142 [P] [US15] Add mobile message rendering tests in `apps/mobile/test/message-parts.test.tsx`

### Implementation for User Story 15

- [ ] T143 [US15] Create the Expo app package in `apps/mobile/package.json`
- [ ] T144 [US15] Create the mobile app entrypoint in `apps/mobile/App.tsx`
- [ ] T145 [US15] Wire the generated API client in `apps/mobile/src/api/client.ts`
- [ ] T146 [US15] Implement parts rendering in `apps/mobile/src/features/chat/MessageParts.tsx`
- [ ] T147 [US15] Document mobile tailnet setup in `README.md`

**Checkpoint**: US15 is functional when mobile consumes the same contract and renders the same stream shape.

---

## Phase 18: User Story 16 - Version Identity and Guaranteed Provider Runtimes (Priority: P4)

**Goal**: Make dev/prod version identity obvious and preflight provider runtimes before serving traffic.

**Independent Test**: `/status` distinguishes dev from prod and provider runtime preflight catches missing binaries before request time.

### Tests for User Story 16

- [ ] T148 [P] [US16] Add status version tests in `backend/tests/test_health_api.py`
- [ ] T149 [P] [US16] Add runtime preflight tests in `backend/tests/paw/test_command_project.py`

### Implementation for User Story 16

- [ ] T150 [US16] Add version identity fields to `backend/app/main.py`
- [ ] T151 [US16] Add Effect status version fields to `backend-ts/apps/api/src/Modules/System/Http.ts`
- [ ] T152 [US16] Add runtime preflight checks to `backend/app/cli/paw/commands/project/preflight.py`
- [ ] T153 [US16] Add provider runtime checks to `backend/app/providers/factory.py`
- [ ] T154 [US16] Document version/runtime preflight in `README.md`

**Checkpoint**: US16 is functional when version identity and runtime readiness are visible before traffic.

---

## Phase 19: Polish & Cross-Cutting Concerns

**Purpose**: Final gates and cleanup that apply across the desired completed story set.

- [ ] T155 [P] Run and record `UV_CACHE_DIR=/tmp/pawrrtal-uv-cache just check` results in `specs/003-pawrrtal-overhaul/quickstart.md`
- [ ] T156 [P] Run and record `just sentrux` results in `specs/003-pawrrtal-overhaul/quickstart.md`
- [ ] T157 [P] Update `docs/curated-claude-rules.md` if new setup/config rules should be agent-discoverable
- [ ] T158 [P] Update `DESIGN.md` if any implemented UI or loading-state rule changed
- [ ] T159 Reconcile completed removals with `specs/003-pawrrtal-overhaul/removal-completeness-note.md`
- [ ] T160 Re-run `node scripts/check-file-lines.mjs` from `/mnt/work/code/personal/pawrrtal`
- [ ] T161 Re-run `node scripts/check-nesting.mjs` from `/mnt/work/code/personal/pawrrtal`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1 and blocks every user story.
- **US1 through US5 (P1)**: Start after Phase 2; recommended order is US1 → US2 → US3 → US4 → US5 because the setup spine, test gate, gateway, sandbox, and secrets form the foundation.
- **US6 through US11 (P2)**: Start after the relevant P1 foundation exists; US6 should complete before thin-core extraction and large provider work.
- **US12 through US15 (P3)**: Start after message parts, gateway, secrets, and visual verification are usable.
- **US16 (P4)**: Can start after Phase 2, but should be completed before production rollout.
- **Polish**: Depends on all desired story phases being complete.

### User Story Dependencies

- **US1**: Depends only on Phase 2; MVP scope.
- **US2**: Depends on US1 setup guidance and Phase 2 backend-ts test audit.
- **US3**: Depends on US1 package skeleton and US2 test gate repair.
- **US4**: Depends on US1 kernel ports and US3 gateway stream shape.
- **US5**: Depends on US1 setup config surface.
- **US6**: Depends on US4 sandbox posture and US5 secret posture.
- **US7**: Depends on US3 gateway and US6 removal simplification.
- **US8**: Depends on US3 provider manifest shape.
- **US9**: Depends on US5 secret posture and US3 provider taxonomy.
- **US10**: Depends on US3 provider abstraction.
- **US11**: Depends on message parts from US3; verifies later rendering stories.
- **US12**: Depends on US11 harness and US3 message parts.
- **US13**: Depends on US5 secrets and US11 channel proof.
- **US14**: Depends on US1 plugin/capability surface and US5 secrets.
- **US15**: Depends on US3 generated client/RPC contract.
- **US16**: Depends on Phase 2 and benefits every production-bound story.

### Parallel Opportunities

- T003, T004, T005, T006, and T007 can run in parallel after T001.
- T010, T011, T012, and T013 can run in parallel after T008.
- Test tasks inside each story can run in parallel before implementation.
- US8, US9, US10, and US11 can proceed in parallel once US3 is complete.
- US12, US13, US14, and US15 can proceed in parallel after their listed dependencies are satisfied.

---

## Parallel Example: User Story 1

```bash
# Launch setup-spine tests together:
Task: "T015 Add paw setup --dry-run --json CLI tests in backend/tests/paw/test_command_setup.py"
Task: "T016 Add setup config schema validation tests in backend/tests/paw/test_setup_config.py"
Task: "T017 Add SDK forbidden-import check tests in backend-ts/apps/api/test/Architecture/sdk-boundary.test.ts"
Task: "T018 Add root instruction drift tests for setup guidance in backend/tests/test_agents_md.py"

# Launch independent implementation work after test expectations are clear:
Task: "T021 Add typed setup config models and validation helpers in backend/app/cli/paw/setup_config.py"
Task: "T022 Add setup config example data in config/pawrrtal.setup.example.json"
Task: "T023 Add setup config JSON Schema in config/pawrrtal.setup.schema.json"
Task: "T027 Add repo-local setup spine skill instructions in .agents/skills/setup-spine/SKILL.md"
Task: "T028 Add capability-install skill instructions in .agents/skills/add-capability/SKILL.md"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1 and Phase 2.
2. Complete US1 tasks T015-T033.
3. Verify `paw setup --dry-run --json`, `paw doctor --config --json`, `just check`, and the SDK forbidden-import test.
4. Stop and review before moving to US2; US1 is the explicit Step 0A outcome from the plan.

### Incremental Delivery

1. Ship US1 as the setup/customization spine.
2. Ship US2 as the backend-ts test-gate and CLI-boundary repair.
3. Ship US3-US5 as the shared runtime foundation.
4. Ship US6 before large extraction or provider work.
5. Ship the remaining stories in dependency order, using the visual harness and `paw verify` for user-visible claims.

### Verification Gates

- `UV_CACHE_DIR=/tmp/pawrrtal-uv-cache just check`
- `just sentrux`
- `cd backend-ts && bun run --filter '@pawrrtal/*' typecheck`
- `paw setup --dry-run --json`
- `paw doctor --config --json`
- `paw verify chat-roundtrip --json`
- Story-specific tests named in each phase
