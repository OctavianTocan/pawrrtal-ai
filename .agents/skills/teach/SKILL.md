---
name: teach
description: Teach the user a new skill or concept, within this workspace.
disable-model-invocation: true
argument-hint: "What would you like to learn about?"
---

The user has asked you to teach them something. This is a stateful request - they intend to learn the topic over multiple sessions.

## Teaching Workspace

Treat the current directory as a teaching workspace. The state of their learning is captured in this directory in several files:

- `MISSION.md`: A document capturing the _reason_ the user is interested in the topic. This should be used to ground all teaching. Use the format in [MISSION-FORMAT.md](./MISSION-FORMAT.md).
- `./reference/*.md`: Compressed pattern sheets — cheat sheets, anti-patterns, file:line tables. Index at [reference/README.md](../../reference/README.md).
- `RESOURCES.md`: Annotated index of trusted sources. Use the format in [RESOURCES-FORMAT.md](./RESOURCES-FORMAT.md).
- `./learning-records/*.md`: ADR-style insights that steer ZPD. Use [LEARNING-RECORD-FORMAT.md](./LEARNING-RECORD-FORMAT.md).
- `./lessons/*.md`: Thin skill assignments tied to the mission (Pawrrtal uses markdown + IDE, not HTML).
- `GLOSSARY.md`: Canonical terminology — adhere in every lesson.
- `NOTES.md`: User teaching preferences — read before drafting.

## Pawrrtal workflow (mandatory)

**Three-layer stack:** `RESOURCES.md` (index) → `reference/` (durable patterns) → `lessons/` (thin assignments). User codes in IDE; agent reviews (see `NOTES.md`).

### Before writing a lesson

1. Read `MISSION.md`, latest `learning-records/`, `NOTES.md`.
2. Check `reference/` for an existing pattern — **link it; do not re-explain**.
3. If the pattern is new:
   - Research: `effect-smol` (v4 API) → live `backend-ts` → `backend/vendor/effect-api-layout/` (v3 layout, translate) → Python parity.
   - Run `./scripts/setup-vendor-effect-api-layout.sh` if architecture-reference paths are missing.
   - Write `reference/<topic>.md` first.
   - Add index lines to `RESOURCES.md`.
4. Write a **thin lesson** (~100–150 lines): Goal, Concepts (capped), link to `reference/`, file:line table, What to do (no function bodies), Verify, What I won't do.
5. On correction: one learning record pointing at the reference doc — do not inflate the lesson.

### Pattern research order

| Source | Role |
|--------|------|
| `backend/vendor/effect-smol/` | v4 API source of truth |
| `backend-ts/` shipped code | Live Pawrrtal patterns |
| `backend/vendor/effect-api-layout/` | Module layout (gitignored; v3 — translate to v4) |
| Python backend | Parity behavior |

Never trust parametric knowledge. Never copy v3 imports into Pawrrtal v4 code.

### Lesson prescription level

Per `NOTES.md` and LR-0004: give goal, concepts, references (file:line), verify commands, hints. Do **not** give function bodies, scratchpad code, or full `Layer.effect` shapes. When stuck, point at a reference — never write the answer.

## Philosophy

To learn at a deep level, the user needs three things:

- **Knowledge**, captured from high-quality, high-trust resources
- **Skills**, acquired through highly-relevant interactive lessons devised by you, based on the knowledge
- **Wisdom**, which comes from interacting with other learners and practitioners

Before the `RESOURCES.md` is well-populated, your focus should be to find high-quality resources which will help the user acquire knowledge. Never trust your parametric knowledge.

## Lessons

A lesson teaches ONE THING tied to the mission. Pawrrtal lessons are markdown files: `./lessons/0001-<dash-case-name>.md`.

Each lesson should link to `reference/` docs and prior lessons. Include a Followups section reminding the user to ask the agent.

## The Mission

Every lesson should be tied into the mission. If `MISSION.md` is empty, question the user on why they want to learn this.

Update `MISSION.md` and add a learning record when the mission shifts. Confirm with the user first.

## Zone Of Proximal Development

Read `learning-records/` before choosing the next topic. Record prior knowledge when the user says they already know something.

## Acquiring Knowledge & Skills

Design lessons around a skill. Knowledge in the lesson is only what is required for that skill. Citations go to `RESOURCES.md` entries and `reference/` docs.

Feedback loop: user writes code → agent reviews in chat. Typecheck and scoped tests are the automated gate.

## Reference Documents

`reference/` holds compressed patterns reused across lessons. **Write reference before a fat lesson.** Lessons link; reference holds the rules.

Update `GLOSSARY.md` only after the user demonstrates correct use of a term.

## Acquiring Wisdom

When wisdom is needed, attempt an answer then point to communities in `RESOURCES.md`.

## `NOTES.md`

Read before every lesson draft. Record new preferences there.
