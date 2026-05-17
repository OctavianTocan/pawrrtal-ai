**IMPORTANT**: before you do anything else, run the `beans prime` command and heed its output.

# Repository Guidelines

- Repo: https://github.com/OctavianTocan/pawrrtal
- In chat replies, file references must be repo-root relative only (example: `frontend/components/ui/sidebar.tsx:80`); never absolute paths or `~/...`.
- Do not edit files covered by security-focused `CODEOWNERS` rules unless a listed owner explicitly asked for the change or is already reviewing it with you. Treat those paths as restricted surfaces, not drive-by cleanup.
- **Never describe a failure mode as "pre-existing" to justify leaving it broken.** If you encounter a lint warning, type error, runtime warning, console error, broken test, or regression — fix it. The user does not care who introduced it; they care whether the app works. Warnings need fixing too: they are latent errors that haven't been promoted to blocking yet (Biome rolls levels, React 19 hardened previously informational warnings into fatal hydration faults, etc.). If a fix would explode the PR scope, open a sibling PR and reference it; do not punt with genealogy. See `.claude/rules/general/no-pre-existing-excuse.md`.

## Project Structure & Architecture Boundaries

- **Frontend (`frontend/`)**: Next.js App Router, TypeScript, Tailwind CSS v4, and shadcn-style UI. Routes live in `frontend/app/`, UI components in `frontend/components/`, feature modules in `frontend/features/`.
- **Backend (`backend/`)**: Python FastAPI application. API routes in `backend/app/api/`, database models in `backend/app/models/`, CRUD operations in `backend/app/crud/`.
- **Design system (`DESIGN.md`)**: Repo-root [DESIGN.md](https://github.com/google-labs-code/design.md)-format spec describing the Craft Agents-inspired visual identity — colors, typography, spacing, shapes, elevation, and component bindings. Canonical token values live in `frontend/app/globals.css`; `DESIGN.md` mirrors them as machine-readable YAML front matter so coding agents have a persistent, structured understanding of the system. Lint with `bun run design:lint`.
- **Docs (`docs/`)**: Project documentation, migration plans, and design specs.
- **Tasks (`.beans/`)**: Markdown-based task tracking. Update the status of `.beans` files as work is completed.
- **Rule**: Always use the `beans` CLI (e.g. `beans create`, `beans update`) to manage `.beans` files. Never create or edit them manually.
- **AI Rules (`.claude/rules/`)**: Most rules are vendored from [github.com/OctavianTocan/claude-rules](https://github.com/OctavianTocan/claude-rules) into `.claude/rules/`; each file uses YAML frontmatter with `paths` globs so rules apply only for matching files. This repo also keeps project-specific rule sets under `.claude/rules/clean-code/` and `.claude/rules/github-actions/`.
- **Semantic code search first**: When an agent has access to semantic code tools (CodeGraph, Serena, language-server symbol search, or equivalent), use them before broad text search for code exploration. Start with semantic context/search for symbols, ownership, callers/callees, and impact; then use `rg` for exact literals, docs/config text, or after the semantic tool is unavailable, uninitialized, or returns insufficient results. See `.claude/rules/general/prefer-semantic-code-search.md`.
- **Stagehand + browser MCP (Cursor / Claude Code)**: Project MCP servers in `.cursor/mcp.json`, `.mcp.json`, and `config/mcporter.json`: **stagehand-docs** (`https://docs.stagehand.dev/mcp`), **context7** (`@upstash/context7-mcp`, [GitHub](https://github.com/upstash/context7)), **deepwiki** (`https://mcp.deepwiki.com/mcp`, [DeepWiki](https://mcp.deepwiki.com/)). **Documentation index** for Stagehand (discover all pages before drilling in): https://docs.stagehand.dev/llms.txt — agents should fetch this (or query **stagehand-docs** MCP) before asserting Stagehand V3 APIs. **Cursor:** `.cursor/rules/stagehand-v3-typescript.mdc` (always-on patterns + MCP workflow). **Claude Code:** `.claude/rules/stagehand/stagehand-documentation-and-mcp.md` and path-scoped `.claude/rules/stagehand/stagehand-v3-typescript-patterns.md`; see `.claude/CLAUDE.md` § Stagehand.
- **Rule**: Frontend code must only communicate with the backend via the established API endpoints (using `useAuthedFetch` or TanStack Query mutations). Do not mix frontend and backend responsibilities.
- **Rule**: UI components should follow the established Craft Agents design language (e.g., `popover-styled` classes, exact radius matching). `DESIGN.md` at the repo root is the source of truth for tokens; do not introduce literal Tailwind colors (`text-gray-*`, `bg-blue-500`, etc.) or new `--radius-*` tokens — use the existing scale or `0`.
- **Rule**: Ensure PascalCase is used for components inside `frontend/features/`.

## Build, Test, and Development Commands

We rely on `just` as our primary task runner for the repository.

- **Start all dev servers**: `just dev` (starts both frontend and backend concurrently).
- **Check (Lint/Format read-only)**: `just check` (runs Biome).
- **Lint & Auto-fix**: `just lint-fix` (runs Biome check with writes).
- **Format**: `just format` (runs Biome format).
- **Design system lint**: `bun run design:lint` (validates `DESIGN.md` against the spec; CI runs the same gate).
- **Design system diff**: `bun run design:diff -- DESIGN.md DESIGN-v2.md` (compare two design system snapshots).
- **Install All Dependencies**: `just install` (runs `bun install` for frontend and `uv sync` for backend).
- **Auto-commit**: `just commit` (auto-generates conventional commit).
- **Push**: `just push` (runs push with auth switching).
- **Terminology**:
    - "gate" means a verification command or command set that must be green for the decision you are making.
    - A local dev gate is the fast default loop, usually `bun run typecheck` and `just check` plus any scoped test you actually need.

## CI & GitHub Actions

This is a public repo wired to a self-hosted runner pool on Octavian's VPS. CI is **scoped to OctavianTocan** for safety, not by accident — every workflow you create or modify must obey the rules in `.claude/rules/github-actions/octaviantocan-only-and-self-hosted-runner.md`. The short version:

- **Actor gate is mandatory on every job.** Even on `ubuntu-latest`, never let a fork PR or another author trigger a workflow:

  ```yaml
  if: >-
    github.actor == 'OctavianTocan' &&
    (github.event_name != 'pull_request' ||
      github.event.pull_request.head.repo.full_name == github.repository)
  ```

- **Default runner is self-hosted:** `runs-on: [self-hosted, openclaw-mini, pawrrtal]`. The runner pool is `openclaw-vps-NN` registered out of `/srv/github-runners/<repo>/actions-runner/` as the `gha` system user. Use `ubuntu-latest` only when there's a real reason (macOS/Windows/GPU/untrusted external code already gated separately).
- **Documented exception:** `rebase.yml` uses `pull_request_target` and never runs PR code; it relies on `author_association` instead of the actor gate. See `.claude/rules/github-actions/safe-pull-request-target.md`.
- **Repo-level Actions settings** (must be set in the GitHub UI; the standard CI tokens don't have Actions admin scope): require approval for first-time contributor workflows, default workflow permissions = read.
- **Layout / install / removal:** `frontend/content/docs/handbook/ci/self-hosted-runner.md`. Use `scripts/install-self-hosted-runner.sh` to add another runner; the script auto-picks the next `openclaw-vps-NN` slot.

New CI surfaces (backend pytest, frontend vitest, Maestro E2E, etc.) belong on the self-hosted runner with the actor gate. If you find yourself thinking "just this once on `ubuntu-latest` without the gate," don't.

## Architectural Quality (sentrux)

Architectural drift is gated by [sentrux](https://github.com/sentrux/sentrux) v0.5.7+.

- **Rules**: `.sentrux/rules.toml` — defines layers (frontend: `app → features → ai-elements → ui-primitives → lib`; backend: `entry → api → crud → models → core`) and the cross-stack boundary (`frontend/* ⇏ backend/*`).
- **Local check**: `just sentrux` — runs `scripts/sentrux-check.sh`, which checks a temporary app-code snapshot and excludes agent/tooling roots such as `.agents/`, `.claude/`, `.cursor/`, `.factory/`, `.goose/`, and `.pi/`.
- **CI**: `.github/workflows/sentrux.yml` runs the same filtered check on every PR to `development`/`main` and posts violations as a PR comment on failure.
- **Per-session loop** (agents): if the sentrux MCP is wired into your client (Claude Code, Cursor, etc.), call `session_start` before substantive work and `session_end` after to surface architectural regressions caused by the session. Local baseline is stored at `.sentrux/baseline.json` (gitignored).
- **Why this exists**: see `frontend/content/docs/handbook/decisions/2026-05-03-adopt-sentrux-architecture-gating.md` (baseline quality 6753/10000, equality bottleneck, 2.5% test coverage gap noted).

## Coding Style & Naming Conventions

- **Frontend**: TypeScript (ESM) and React. Prefer strict typing; avoid `any`.
- **Formatting/linting**: Managed by Biome. Never add `@ts-nocheck` and do not add inline lint suppressions by default. Fix root causes first; only keep a suppression when the code is intentionally correct, the rule cannot express that safely, and the comment explains why.
- Do not disable `no-explicit-any`; prefer real types, `unknown`, or a narrow adapter/helper instead.
- Prefer explicit inheritance/composition or helper composition so TypeScript can typecheck.
- Keep files concise; extract helpers instead of "V2" copies. Aim to keep files under ~700 LOC. Split/refactor when it improves clarity or testability.
- **Written English**: Use American spelling and grammar in code, comments, docs, and UI strings (e.g. "color" not "colour", "behavior" not "behaviour", "analyze" not "analyse").
- **Preserve Documentation**: NEVER remove existing docstrings, JSDoc comments, or explanatory comments when modifying code. Only remove documentation if the code it documents is being deleted, or update it if your changes make it inaccurate. See `.claude/rules/clean-code/preserve-documentation.md` for detailed rules.
- **Icons + SVGs live in their own files**: Never inline SVG markup or icon definitions inside a component file. Every glyph, logo, status icon, or decorative SVG must live in a dedicated file (e.g. `frontend/features/nav-chats/components/ConversationIndicators.tsx` for the row-status glyphs, `frontend/features/onboarding/OnboardingBackdrop.tsx` for the backdrop). Components import + render the icon, never define it. This keeps feature files focused, lets tree-shaking work, and stops icon swaps from re-flowing unrelated code. Lucide / Tabler imports already follow the rule because they're external packages.
- **File-line budget**: 500 lines hard ceiling for any `.ts`/`.tsx`/`.py` source file. `node scripts/check-file-lines.mjs` enforces it; CI fails on overflow. Split into smaller modules rather than asking for an exemption.
- **Nesting-depth budget (Python)**: max 3 levels of compound-statement nesting per Python function (`if`/`for`/`while`/`try`/`with`/`match`). `python3 scripts/check-nesting.py` enforces it on every backend pytest CI run. Pre-existing offenders are tracked in the script's `EXEMPT_FUNCTIONS`; do not add new entries.
- **Provider-agnostic tools**: tool factories live in `backend/app/core/tools/`, providers in `backend/app/core/providers/`. Providers translate `AgentTool[]` → SDK format and never import tool modules themselves. Tool composition (which tools the agent gets this turn) lives in the chat router (`backend/app/api/chat.py`). Enforced by `scripts/check-no-tools-in-providers.py`. See `.claude/rules/architecture/no-tools-in-providers.md`.
- **Nesting-depth budget (frontend)**: max 3 levels of compound-statement nesting per TS/TSX function (`if`/`for`/`while`/`do`/`try`/`switch`). `node scripts/check-nesting.mjs` runs as part of `bun run check` and the Frontend Check CI workflow.
- **Dev-mode console must stay clean**: `node scripts/dev-console-smoke.mjs` boots the app under `next dev` (Turbopack + React 19 strict) via the `agent-browser` CLI and fails CI if `pageerror` or `console.error` fires on the cold-boot routes. The Stagehand suite hits the *production* build, which silences hydration warnings; this smoke is the gate that catches dev-only fatal warnings (e.g. React 19's `<script>` rule). Allowlist policy: narrow regex per CI-environment artefact only, with a TODO + reason; never widen the matcher.
- See `.claude/rules/clean-code/limit-nesting-depth.md` for guidance on flattening with guard clauses and helper functions.

## Commit & Pull Request Guidelines

- Use `$pr-to-branch` skill for PR creation and analysis when available.
- Create commits with clear, action-oriented messages (e.g., `feat(sidebar): add rename functionality`).
- Group related changes; avoid bundling unrelated refactors.
- PRs should be small, review-friendly slices (e.g., "Sidebar Craft Parity Round 2"). Do not bundle massive rewrites with unrelated visual tweaks.
- When landing or merging any PR, ensure the working tree is clean and CI gates pass.
- **Fix lint warnings on every PR you touch a file in, not just errors.** A Biome warning, a CI non-blocking notice, a `console.warn` — these are latent failures and they need fixing. Do not write "pre-existing" or "not from this PR" in a description to justify leaving them; the user reads that as "I noticed but chose not to fix." If the fix is structurally unrelated, open a sibling PR and reference it; do not leave a TODO hanging. See `.claude/rules/general/no-pre-existing-excuse.md`.

## Git Notes

- Agents MUST NOT create or push merge commits on `main` or `development`. If the target branch has advanced, rebase local commits onto the latest `origin/development` before pushing.
- Bulk PR close/reopen safety: if a close action would affect more than 5 PRs, first ask for explicit user confirmation with the exact PR count and target scope/query.

## Collaboration / Safety Notes

- **Multi-agent safety:** do **not** create/apply/drop `git stash` entries unless explicitly requested. Assume other agents may be working; keep unrelated WIP untouched and avoid cross-cutting state changes.
- **Multi-agent safety:** when the user says "push", you may `git pull --rebase` to integrate latest changes (never discard other agents' work). When the user says "commit", scope to your changes only.
- **Multi-agent safety:** prefer grouped `commit` / `pull --rebase` / `push` cycles for related work instead of many tiny syncs.
- **Multi-agent safety:** do **not** create/remove/modify `git worktree` checkouts unless explicitly requested.
- **Multi-agent safety:** do **not** switch branches / check out a different branch unless explicitly requested.
- **Multi-agent safety:** running multiple agents is OK as long as each agent has its own session.
- **Multi-agent safety:** when you see unrecognized files, keep going; focus on your changes and commit only those.
- Lint/format churn:
    - If staged+unstaged diffs are formatting-only, auto-resolve without asking.
    - If commit/push already requested, auto-stage and include formatting-only follow-ups in the same commit.
    - Only ask when changes are semantic (logic/data/behavior).
- **Multi-agent safety:** focus reports on your edits; avoid guard-rail disclaimers unless truly blocked; when multiple agents touch the same file, continue if safe; end with a brief “other files present” note only if relevant.
- Bug investigations: read source code of relevant dependencies and all related local code before concluding; aim for high-confidence root cause.
- Code style: add brief comments for tricky logic.
- **Look up official docs / CLI / agent skills BEFORE inventing or hacking.** When integrating a library or framework, check its official docs, CLI, and any shipped `SKILL.md` files first — not after writing 80 lines of custom code that the library already solves in one call. For TanStack libraries: `npx @tanstack/intent@latest list` and `npx @tanstack/intent@latest load <pkg>#<skill>`. For ad-hoc TanStack queries: `npx @tanstack/cli search-docs "<query>" --library router --framework react --json`. For other libraries: Context7 + DeepWiki MCPs are wired in `.mcp.json`. The full rule, including the migration mistakes that prompted it, is in `.claude/rules/general/check-official-docs-and-skills-first.md`.
- **GitHub Actions Rules (`.claude/rules/github-actions/`)**: Strict context and design patterns to follow when creating or modifying CI/CD workflows and actions.
- **Clean Code Rules (`.claude/rules/clean-code/`)**: Universal rules for function design, naming conventions, named constants, Python logging/exception narrowing, and code structure. Your generated code must adhere to these principles (KISS, DRY, single-responsibility, meaningful naming).
- **React Rules (`.claude/rules/react/`)**: Component patterns including callback prop naming (`on*` for props, `handle*` for implementations), aria-hidden consistency on decorative icons, focus management, state guards, StrictMode-safe render patterns (no mutable closures in JSX), and stable content-derived React keys.
- **Dropdown selector commit rule**: Custom selectable rows inside `@octavian-tocan/react-dropdown` menus/submenus must commit on primary pointer-down, keep click as the keyboard/fallback path, and guard duplicate pointer+click commits. App code should use `frontend/hooks/use-pointer-down-commit.ts`; vendored `@octavian-tocan/react-chat-composer` code should use its package-local equivalent. Do not rely on `onClick` alone for selector rows that close or unmount their menu.
- **TypeScript Rules (`.claude/rules/typescript/`)**: Explicit return types on every function, TSDoc on exports, JSDoc placement (directly above the declaration), parameter limits (max 3 positional, group into objects beyond that), literal union types for constrained string fields, and environment variable conventions.

## Electron Desktop Shell

The repo ships a desktop shell at `electron/` that wraps the same
Next.js frontend without any duplication. Web behavior is unchanged;
desktop is purely additive. See `electron/README.md` for the full
architecture; the rules at a glance:

- The frontend stays Electron-agnostic. Anywhere it needs a desktop
  capability it goes through `frontend/lib/desktop.ts`, which detects
  `window.pawrrtal` and falls back to web equivalents on the browser.
- Desktop-only IPC is namespaced `desktop:*` and validated on the
  main side (see `electron/src/ipc.ts`). Renderer security is locked:
  `nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`.
- Adding a new desktop feature touches three files in lockstep:
  `electron/src/preload.ts` (bridge), `electron/src/ipc.ts` (handler),
  `frontend/lib/desktop.ts` (typed wrapper + web fallback).
- Dev: `just electron-dev` against the running `just dev`.
  Prod-style: `just electron-prod`. Installer: `just electron-dist`.
- Backend is not bundled; set `BACKEND_URL` to point the desktop app
  at a remote FastAPI deployment (defaults to `http://localhost:8000`).

## How We Work On Pawrrtal

The session-derived working agreement lives in
`.claude/rules/general/how-we-work-on-ai-nexus.md`. It encodes nine rules
the team keeps re-discovering: read implementations before changing them,
trace cause before fixing, update `DESIGN.md` when tokens change in code,
reuse established patterns instead of inventing parallel ones, declare
every interactive element with `cursor-pointer`, run the toolchain after
every file write, ship tests in the same commit as new features, commit
one concern at a time, and ask before destructive or scope-bending work.
Apply on every session.

## Claude rules index

The curated reading list for the highest-signal rules in this stack lives at [`docs/curated-claude-rules.md`](docs/curated-claude-rules.md). Rule content itself lives under `.claude/rules/**` with `paths:` frontmatter, so Claude only loads each rule when it edits a matching file. Backend agent-loop testing rules (including the `ScriptedStreamFn` pattern) are scoped to `backend/**` and live at [`.claude/rules/testing/agent-loop-testing-philosophy.md`](.claude/rules/testing/agent-loop-testing-philosophy.md).

## Learned User Preferences

- When the user asks to log a technical or architectural decision, capture it in `frontend/content/docs/handbook/decisions/` (ADR-style) and tie it to task tracking (e.g. `beans`) when the flow already uses beans.
- When adapting external UI references (screenshots, other products), use AI Nexus naming and the repo theme tokens rather than copying third-party branding or palettes from the reference.
- The user may ask for extremely terse “caveman” explanations when digging into complex technical changes.
- When a UI fix establishes a reusable pattern, or when a surface fetches data as soon as it appears (for example integration connection state), use a loader or skeleton until the result is known; capture the approach in `DESIGN.md` so the design system stays the single narrative for “how we do this,” not only inline code comments.
- Prefer modal/backdrop (“scrim”) treatments that combine background blur with a subtle dark tint (for example a linear gradient around 10–15% black) instead of a flat uniform opacity overlay when aiming for depth or a glass-like feel.
- Electron desktop distribution should plan for an in-app update prompt flow so everyday users are not manually reinstalling each new build.
- For `@octavian-tocan/react-overlay`, compose overlays using the package’s header and footer surfaces (`ModalHeader`, `ModalDescription`, `ResponsiveModal` `header`/`footer`, and BottomSheet `header`/`footer`) instead of putting titles and primary actions only in the scrollable body.

## Learned Workspace Facts

- Local dev runs on plain localhost: Next.js on `http://localhost:3001`, FastAPI on `http://localhost:8000`. `dev.ts` (run via `just dev` or `bun run dev`) starts both side-by-side. No HTTPS, no proxy, no special hostnames.
- Frontend → backend cookie auth works because both run on the same host (`localhost`); cookies ignore ports, so `Set-Cookie` from `:8000` is visible to fetches from `:3001` with `credentials: 'include'`. Use `COOKIE_SAMESITE=lax` and `COOKIE_SECURE=false` in dev.
- Post-login navigation in `LoginForm` must use `window.location.replace('/')` (full-page navigation), not `router.push`. Client-side navigation keeps React in the same turn so authed queries (`NavChats`, etc.) can fire before the browser commits the `Set-Cookie` response, causing a 401 → redirect-to-login race. This is especially visible on Safari and when onboarding UI adds heavier post-login hydration.
- In staging/production the backend API lives on an `api.*` subdomain; the Next.js dev-login proxy (`/api/dev-login`) must call `cookies.set` with an explicit `domain` sourced from the `AUTH_COOKIE_DOMAIN` env var (or inferred by stripping `api.` from `NEXT_PUBLIC_API_URL`). Forwarding the upstream `Set-Cookie` verbatim omits `Domain`, making the cookie host-only for the proxy origin and invisible to API requests on the subdomain — Safari enforces this strictly where Chrome may appear to work.
- Canonical application font stack (with fallbacks): `Google Sans Flex`, `Google Sans`, `Helvetica Neue`, `sans-serif`; keep `DESIGN.md` and `frontend/app/globals.css` aligned when this changes.
- The deployed FastAPI backend for remote usage is hosted on Railway; local development still targets plain `localhost` per the ports above unless you intentionally run against that remote URL.
- Custom React hooks use consistent `use-*` naming for modules and exports (for example `use-login-mutations.ts`).
- When adding or extending GitHub Actions workflows, follow the repository pattern of running jobs on the team’s custom GitHub runner rather than assuming default hosted runners only.
- Git `pre-commit` runs via `backend/.venv/bin/python3 -m pre_commit`; keep `pre-commit` in the backend `pyproject.toml` dev dependency group and run `cd backend && uv sync --group dev` so hooks do not fail with `No module named pre_commit`.
- From `frontend/`, run scoped Vitest with `bun run test -- <file-or-pattern>` so paths are passed after `--` (avoid `bun run test --run <path>`, which does not match how Vitest is wired here).

<claude-mem-context>
# Memory Context

# [pawrrtal] recent context, 2026-05-04 9:18am GMT+2

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (17,256t read) | 85,110t work | 80% savings

### Feb 15, 2026
S7 Update Task List After Successfully Implementing Conversation Rendering (Feb 15 at 3:49 PM)
S1 Check Notion todos for project status and verify CLAUDE.md symlink setup (Feb 15 at 3:49 PM)
19 4:33p 🟣 Enhanced git commit automation with stream piping
20 4:34p 🟣 Implemented React Query with authenticated API fetching
21 " 🔄 Refactored conversation fetching to use React Query caching
### Feb 16, 2026
120 5:13p 🔵 Notion Integration Tools Available in pawrrtal Project
121 " 🔵 AppSidebar Component Structure in pawrrtal Frontend
122 5:14p 🔵 Pawrrtal Project Architecture and Task Management System
123 " 🔵 App Layout Structure Uses Sidebar Wrapper Component
124 " 🔵 Sidebar Component Architecture Using SidebarProvider Pattern
125 5:27p 🟣 Conversations Successfully Rendering in UI
S8 Fix React Query cache invalidation issue where new conversations weren't appearing in the sidebar after creation (Feb 16 at 5:33 PM)
### Feb 17, 2026
S9 Architectural design help for organizing chat interface code in frontend/app/(app)/page.tsx (Feb 17 at 4:06 PM)
320 4:07p 🔵 Frontend File Structure Discovery
321 4:08p 🔵 Complete Frontend Source File Inventory
322 " 🔵 Root Layout Configuration
323 " 🔵 App Layout Uses NewSidebar Component
324 " 🔵 Landing Page Uses Conversation Creation Hook
325 " 🔵 Providers Component Wraps React Query Client
326 4:09p 🔵 Import Dependency Graph Extracted
327 " 🔵 NewSidebar Component Architecture
328 4:10p 🔵 AppSidebar Contains Unused Navigation Data
329 " 🔵 Component Example File is Demo Showcase
330 " 🔵 ComponentExample Confirmed as Orphaned File
331 " 🔵 Example Component Wrapper Utilities
332 " 🔵 AI Elements Component Usage Verification
333 4:11p 🔵 Chat Component Uses Five AI Elements
334 " 🔵 Chat Component Implementation Details
335 " 🔵 Complete AI Elements Component Inventory
336 " 🔵 AI Elements Search Pattern Issue Detected
337 " 🔵 Chat Component Uses Mixed Import Paths
338 4:12p 🔵 Chat Component Complete Import Analysis
339 " 🔵 Message Component Complexity Analysis
340 " 🔵 Conversation Component Wrapper for Scrolling
341 " 🔵 Prompt Input Component Massive Size
342 4:13p 🔵 Loader Component Simple Spinner
343 " 🔵 Automated Search Produces False Negatives
344 4:19p 🔵 Chat Feature Relocated to Features Directory
345 4:20p 🔵 Features Directory Contains Modular Chat Implementation
346 " 🔵 Conversation Page Uses ChatContainer from Features Directory
347 " 🔵 Dashboard Page is Placeholder Demo UI
348 " 🔵 Login Page Uses LoginForm Component
349 " 🔵 Signup Page Uses SignupForm Component
350 4:21p 🔵 Page-Level Imports Reveal Active Components
351 " 🔵 Layout Files Import NewSidebar and Providers
352 " 🔵 ChatContainer is Thin Wrapper Around ChatView
353 " 🔵 Features Chat Component Entirely Commented Out
354 4:22p 🔵 ChatView is Non-Functional Placeholder
355 " 🔵 Comprehensive Unused File Analysis Complete
**356** " 🔵 **Orphaned Navigation Components Confirmed**
Grep search confirms nav-main, nav-projects, and nav-secondary navigation components are completely orphaned with zero references across the entire codebase. These components were likely created as part of sidebar scaffolding alongside nav-chats and nav-user, but were never integrated into either NewSidebar or AppSidebar. The components represent planned but unimplemented navigation features (project management, secondary navigation menus, main navigation structure) that can be safely deleted. This confirms the Python import analysis accuracy and provides additional validation for the unused file list.
~279t 🔍 808

**357** " 🔵 **NavMain Component Is Functional But Unused**
NavMain is a fully functional, well-implemented navigation component that creates collapsible menu sections with nested items. Unlike placeholder code, this component is production-ready with proper accessibility (tooltips, screen reader labels) and interaction patterns (collapsible sections, active state). The "Platform" label suggests it was intended for top-level application navigation. However, despite being complete, it's never imported or used anywhere. This represents over-engineering - building components speculatively before they're needed. The component may have been created during initial scaffolding when the sidebar architecture was being designed, but the final implementation (NewSidebar and AppSidebar) took different approaches and never used NavMain. Safe to delete as high-quality but unused scaffolding code.
~371t 🔍 1,322

### Feb 22, 2026
**1543** 8:53p ✅ **Added implementation context to Task 71 Notion page**
Added comprehensive implementation context to the Notion task page for "Fix create_conversation_service to accept pre-generated UUID" (Task ID 71). The documentation explains that the current implementation in backend/app/crud/conversation.py always auto-generates a new UUID for conversations, which works fine for the standard POST /api/v1/conversations endpoint but causes issues in the /api/chat fallback path where the frontend's pre-created UUID must be preserved. The context includes a code example showing how to add an optional conversation_id parameter that defaults to None, allowing the function to either use a provided UUID or let SQLAlchemy auto-generate one. This preserves backward compatibility while enabling the new functionality needed for Task 72. The documentation emphasizes why this is critical: without this fix, Agno would store messages under a different session ID than what the frontend expects, breaking the conversation flow.
~422t 🛠️ 913

**1544** 8:54p ✅ **Added implementation context to Task 72 Notion page**
Added comprehensive implementation context to the Notion task page for "Fix POST /api/chat to use frontend's conversation_id for new conversations" (Task ID 72). The documentation explains a critical UUID mismatch bug in the /api/chat endpoint's fallback path. Currently, when a conversation_id lookup fails, the backend creates a new conversation with an auto-generated UUID instead of using the UUID the frontend sent. This causes Agno to store messages under a different session ID than what the frontend expects, breaking the conversation link. The context includes a detailed edge case scenario showing the race condition, a code example of the fix, and a flow diagram illustrating the corrected behavior. The documentation clarifies this is the second task in a two-part fix and requires Task 71 to be completed first, as it depends on the create_conversation_service accepting an optional conversation_id parameter.
~426t 🛠️ 1,564

S15 Clarification on task scope after documenting implementation details for 5 Notion tasks (Feb 22 at 9:16 PM)
**1545** 9:17p 🔵 **Task Backlog Contains 93 Tasks Across 6 Sprints**
The Notion database query revealed the complete project scope after user questioned why only "5 pages" were mentioned. The pawrrtal project has 93 tracked tasks spanning 6 sprints. Sprint 1 (22 tasks) and Sprint 2 (16 tasks) show substantial completion with most tasks marked "Done". Sprint 3 begins with critical UUID handling fixes (tasks 71-72), sidebar features (73-75), and conversation management features. Later sprints (4-6) contain 50+ additional tasks covering technical debt, polish, testing, deployment, and accessibility improvements. The recent documentation effort targeted only 5 specific Sprint 3 tasks, representing a small fraction of the total backlog. This explains the user's confusion - the phrase "all 5 pages updated" implied completeness when it was actually a focused subset.
~397t 🔍 10,114


Access 85k tokens of past work via get_observations([IDs]) or mem-search skill.
## Agent skills

### Issue tracker

Local markdown via `beans` CLI — tasks live in `.beans/` as individual markdown files with frontmatter (`status`, `type`, `priority`, `tags`). See `frontend/content/docs/handbook/agents/issue-tracker.md`.

### Triage labels

Beans uses a flat `status` field (`todo`, `in-progress`, `completed`). No triage state machine. The five canonical triage roles are unused — issues are either tracked or done. See `frontend/content/docs/handbook/agents/triage-labels.md`.

### Domain docs

Single-context. One `CONTEXT.md` at the repo root when created. ADRs live in `frontend/content/docs/handbook/decisions/` (not `docs/adr/`). See `frontend/content/docs/handbook/agents/domain.md`.
