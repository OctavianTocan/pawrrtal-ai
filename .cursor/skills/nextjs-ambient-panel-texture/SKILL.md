---
name: nextjs-ambient-panel-texture
description: Ports Telegram-style tileable SVG preset masks plus a procedural SVG tile generator into a Next.js App Router app as an ambient CSS-mask texture on panels (chat/main shell), with a small customization UI and idempotent install steps. Bundles 33 preset SVGs under bundled-patterns/ for direct copy to public/. Use when adding subtle panel textures, “Telegram-style” chat backgrounds, mask-based overlays, or onboarding a host repo to match the Pawrrtal whimsy feature without backend persistence.
disable-model-invocation: true
---

# Next.js ambient panel texture

Add an **optional decorative texture** (preset SVG masks and/or procedural tiles) behind a primary panel using CSS `mask-image`, plus a **small customization surface** (props-controlled React state by default—no required persistence).

## Bundled assets (default, required on install)

This skill directory includes **`bundled-patterns/pattern-1.svg` … `pattern-33.svg`** (33 tileable masks). **Copy them into the host app’s `public/` tree** so Next.js can serve them. Default public prefix: **`/ambient-texture-patterns/`** (see [reference.md](reference.md)).

Do **not** ask the user to download presets elsewhere unless they explicitly opt out of bundled assets.

**Idempotent asset install:** If the target directory already has **33** files matching `pattern-*.svg`, **skip** copying and only verify the preset URL helper matches that path.

Read [licensing.md](licensing.md) before shipping to end users.

## Idempotency gates (run before creating or editing code)

Stop and report status instead of duplicating work when:

1. **Feature folder** — `frontend/features/ambient-panel-texture/` (or the user’s chosen name from Q1) **exists** with a barrel (`index.tsx` / `index.ts`) exporting the texture hook. Then **merge or skip** creation; do not add a second feature tree.
2. **Public presets** — If `public/<presetPrefix>/` already holds 33 `pattern-*.svg` files, **do not** re-copy from `bundled-patterns/`.
3. **Library helpers** — If `generateAmbientPanelTile` / `ambient-texture-presets` (or equivalent) already exist under `frontend/lib/`, extend them instead of duplicating files.
4. **Overlay integration** — Search the chosen shell file for `maskImage` / `WebkitMaskImage` paired with the texture hook name. If present, **do not** insert a second overlay stack.

If a partial install is detected (helpers without UI or vice versa), **complete or remove** the partial work—never leave duplicate overlays.

## Phase 1 — Discovery (readonly subagents)

Launch **2–3** parallel `explore` subagents (`readonly: true`). Each agent returns a short bullet digest (paths + one-line findings).

**Agent A — layout and aliases**

- Map `frontend/` (or `src/`) structure, `@/` path alias, `app/` vs `pages/`, Tailwind entry (`globals.css` / `@theme`).
- List existing `features/` naming conventions.

**Agent B — overlay mount targets**

- Find the primary **scrollable panel** or chat root (the element that should feel “papered” with texture).
- Confirm which ancestor must be `relative` and z-index ordering for `pointer-events-none` overlays.

**Agent C — customization placement**

- Find Settings / Appearance patterns, or an existing dev route under `app/dev/`, or propose a **single** minimal route/modal for the settings card.

Synthesize digests into: **preset public path**, **primary overlay file**, **optional mirror surfaces**, **settings slot**.

## Phase 2 — User steering (one question at a time)

Use **AskQuestion** when available; otherwise ask in chat and **wait** before the next question.

Suggested order (skip questions already answered by the repo):

1. Feature folder name: default `ambient-panel-texture` or override?
2. Public URL prefix for presets: default `/ambient-texture-patterns/` or override?
3. Primary file path to mount the overlay (from Agent B).
4. Add mirrored texture on secondary shell (e.g. settings column): yes / no?
5. Where to mount **`AmbientPanelTextureSettingsCard`**: existing settings section, new `app/dev/...` page, or standalone modal?

**Forbidden:** multi-part questionnaires in a single turn.

## Phase 3 — Apply (after answers)

1. **Copy bundled SVGs** (unless gate 2 says skip):

   ```bash
   mkdir -p public/ambient-texture-patterns
   cp -n "<SKILL_DIR>/bundled-patterns/"*.svg public/ambient-texture-patterns/
   ```

   `<SKILL_DIR>` = directory containing this `SKILL.md` (repo: `.cursor/skills/nextjs-ambient-panel-texture/`; personal install: `~/.cursor/skills/nextjs-ambient-panel-texture/`).

2. Port **types, bounds, hook, tile generator, preset table, settings card** per [reference.md](reference.md). Replace imports with host design-system primitives.
3. **Default state:** implement the customization card as **controlled props** (`config` + `onConfigChange`) backed by `useState` in a parent or page. Do **not** require `localStorage` or APIs unless the user asks later.
4. Wire **`useAmbientPanelTexture()`** (or chosen name) in the primary panel; optionally mirror on secondary shell.
5. Run the host repo’s fast checks (e.g. `bun run typecheck`, `just check`).

## Verification checklist

- [ ] All **33** preset SVGs are reachable at the configured public prefix (HTTP 200 in dev).
- [ ] Overlay is `pointer-events-none`, does not block clicks, stacks under interactive content.
- [ ] Re-running the skill does **not** duplicate overlays, feature folders, or preset files.
- [ ] [licensing.md](licensing.md) is understood / linked for any redistribution of presets.

## Additional resources

- [reference.md](reference.md) — source file map, rename table, copy commands, stacking notes.
- [licensing.md](licensing.md) — Telegram-derived SVG provenance and IP warning.
