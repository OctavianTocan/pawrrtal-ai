---
name: pawrrtal-taste
description: Apply Pawrrtal-specific taste rules for clean modern UX, CLI output, Telegram rendering, and agent/tool presentation. Use when changing UI copy, visual polish, CLI labels, Telegram flow output, tool names, folder/file listings, thinking/tool rendering, or when generalizing user feedback into repo conventions.
---

# Pawrrtal Taste

## Purpose

Use this skill to make Pawrrtal feel cleaner, simpler, and more deliberate. It applies to the web UI, Telegram rendering, CLI human output, agent tool labels, flow definitions, and any code that turns backend state into something a user reads.

## Taste Rules

- Prefer calm density over dumps. Show the useful slice first, then counts and ways to drill in.
- Keep labels specific and title-cased: `List Folder: backend/app`, `Read File: README.md`, `Search Code: Telegram media`.
- Avoid vague labels like `List folder`, raw tool names, raw schema keys, or long argument blobs in user-facing output.
- Put the object after the action. `List Folder: src` is clearer than `Folder list` or `list_directory`.
- Do not show a long folder/file list unless the user asked for exhaustiveness. Group by kind, cap visible rows, and say how many are hidden.
- Show thinking in Pawrrtal. Do not suppress it; make it readable, compact, and visually distinct from final answers and tool output.
- Prefer native Pawrrtal words over provider or SDK words. Users should see Pawrrtal concepts first, internals only when useful.
- Human CLI output should be compact and aligned; JSON should carry the full evidence.
- Avoid ornamental UI and one-note palettes. Use the repo design tokens and the quiet Craft Agents tone already encoded in `DESIGN.md`.

## Tool Output Shape

When rendering agent tool use in UI or Telegram, aim for:

```text
List Folder: backend/app/cli/paw
12 items shown, 31 hidden
```

Use short summaries for noisy outputs:

```text
Search Code: "telegram media"
8 matches across 5 files
```

Then show only the rows that help the next decision. If full detail matters, provide a drill-in command, expansion state, or saved run log reference.

## Telegram Polish Loop

Use Telegram as the feel test for conversational UX:

1. Name the candidate: what changed, which surface it affects, and what taste question needs feedback.
2. Run text chat through `paw lab telegram chat` with a short turn file that stresses the changed behavior.
3. When media could affect the feel, run `paw lab telegram media` with a JPEG and/or voice note; use `paw lab telegram providers` when provider parity matters.
4. Send the user a compact review packet: prompt, model, Telegram-visible transcript, timing, media summary, run path, and the exact taste question.
5. Treat feedback as a candidate rule until the user accepts it or it repeats across runs.
6. Adjust the implementation, rerun the same flow, then generalize the accepted lesson into this skill, `DESIGN.md`, tests, or a `paw lab flows` checklist.

Do not treat a green backend test as proof of polish. For Telegram-facing behavior, proof means a live or simulated Telegram flow with readable output.

## CLI Flow Awareness

When adding CLI support for a backend feature:

- Add the opinionated command when the flow is important to operate or test repeatedly.
- Keep `paw api request/openapi/ls` as the escape hatch, not the main UX for important flows.
- Add or update `paw lab flows` definitions when the feature needs manual judgment or longer model interaction.
- Keep human output brief; use `--json` for complete payloads and run logs.
