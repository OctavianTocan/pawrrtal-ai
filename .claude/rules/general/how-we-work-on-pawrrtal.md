---
name: how-we-work-on-pawrrtal
paths: ["**/*"]
---

# How We Work on Pawrrtal

Working agreement for this repo. These rules came out of a session of
visible behavioural drift — the same mistakes recurring across days
because they weren't written down. Apply them on every session.

## Rule 1 — Read first, write second

Always read the implementation you're about to change before changing
it. Open the file. Read the function. Read the parent. Trace the
upstream caller. Only then edit.

This applies to: components you're styling, hooks you're calling,
mutations you're invalidating, designs you're matching to a token, and
backends you're integrating with.

If you can't articulate the existing behaviour after reading, you're
not ready to change it.

## Rule 2 — Trace cause before fixing

For visual or behavioural bugs, trace from trigger → state → render
output before writing any fix. Answer in sequence:

1. What is the immediate cause of the visible problem?
2. Is my change targeting that cause, or a downstream symptom?

If targeting a symptom, stop and trace further upstream. The sidebar
"creep" bug looked like a CSS issue but the real cause was the
inner `translate-x` racing the parent flex-grow. The shift+click bug
looked like a state machine bug but the real cause was a navigate
firing the path-sync effect.

## Rule 3 — DESIGN.md is the source of truth

Token decisions live in `DESIGN.md`. When you change a sidebar text
size, a cursor convention, or a motion pattern in code:

1. Update `DESIGN.md` in the **same** PR.
2. Mention the section by name in the commit body.
3. Run `bun run design:lint` before commit.

Do NOT introduce literal Tailwind colors (`text-gray-*`,
`bg-blue-500`), new `--radius-*` tokens, or sidebar text below 14px.

## Rule 4 — Use established patterns, not parallel ones

Before reaching for a new tool, mechanism, or library, check what the
codebase already has:

- Modals/sheets → `AppDialog` from `components/ui` (uses
  `@octavian-tocan/react-overlay` via `ResponsiveModal`). Never raw shadcn `Dialog` /
  `Sheet` in feature code. **`AppDialogFooter`** + **`AppFormRow`** + **`AppDialogCallout`**
  for dialog chrome; **`Field`** stays for full-page forms (login, personalization).
- Empty states → **`AppEmptyState`** (`tone` sidebar/page/card/panel; **`inlineCta`**
  for single-row CTAs). Thin feature wrappers only.
- Sidebar lists → **`SidebarNavRow`** + **`SidebarSectionHeader`** instead of one-off
  hover stacks / uppercase labels.
- Badges / tags / counts → **`AppPill`** (`shape` pill vs tag; semantic **`tone`**).
- Server state → TanStack Query via `useAuthedQuery` /
  `useAuthedFetch`.
- Client UI prefs → `usePersistedState` (localStorage). Not Query.
- Feature constants → `features/<f>/constants.ts` with namespaced keys
  + `as const` + derived union types.
- Icons + SVGs → their own files under `components/brand-icons/` or
  per-feature `components/`. Never inline `<svg>` in a component file.

## Rule 5 — Cursor + cursor-pointer

Every interactive element gets `cursor-pointer` (or one of the
variants in DESIGN.md → Interactive Affordances → Cursor Rules). The
Tailwind base layer doesn't set this for you. The verify question on
every PR: "does every clickable element in this diff have
`cursor-pointer`?"

## Rule 6 — Run the toolchain after every file write

After creating or modifying any file:

1. Run the project formatter (`biome` for FE, `ruff format` for BE).
2. Run `tsc --noEmit` for TS, `mypy` for Python.
3. Fix errors before touching the next file.

Don't batch file writes and check at commit time — the pre-commit hook
will flag what you missed and the recovery is more disruptive than
catching each issue at the source.

## Rule 7 — Tests for every new feature

Every new component, hook, mutation, or backend service ships with
tests in the same commit. Targets:

- Frontend: 70%+ statements via Vitest in `frontend/test/setup.ts`
  configured environment.
- Backend: every CRUD service hit by at least one `pytest.mark.anyio`
  test using the `db_session` + `test_user` fixtures from
  `backend/tests/conftest.py`.
- E2E: Playwright spec under `frontend/e2e/` for any user-facing flow,
  using the dev-admin login fixture (no UI signup) per the
  api-setup-not-ui rule.

## Rule 8 — Commit in logical units, never batch unrelated work

One concern per commit. The commit body explains "what changed and
why." Conventional Commits format. Run the full local check (`just
check` + `bunx tsc --noEmit` + `bunx vitest run` + relevant pytest)
before pushing. Push after each logical unit lands — never let
multiple unrelated changes pile up unpushed.

## Rule 9 — Ask before destructive or scope-bending work

If you're about to: drop a column, rename a public API, switch auth
providers, force-push, delete files outside your current change, or
add a dependency that wasn't on the menu — pause and ask. Auto mode
accelerates routine work; it doesn't license unrequested architecture
shifts.

## Verify

"Did I read the implementation first? Trace cause before fixing?
Update DESIGN.md if I touched a token? Use established patterns? Add
cursor-pointer to interactive elements? Run the toolchain after every
file? Add tests in the same commit? Commit one concern at a time?"
