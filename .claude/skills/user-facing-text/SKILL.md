---
name: user-facing-text
description: >-
  Write and review user-facing text across Pawrrtal's surfaces (Telegram,
  Google Chat, Web). Use when adding or editing any string a user sees — tool
  or action display names, command labels, buttons, status lines, error
  messages, cards, notices — or when reviewing copy. Enforces Title Case
  "Tool Name" for tool/action names (never tool_name or "Tool name"), American
  spelling, and consistent labels across channels.
---

# User-Facing Text

How to write and review every string a Pawrrtal user reads — across **Telegram,
Google Chat, and the Web app**. The agent and the app both surface text to
users; this skill keeps it consistent, correct, and on-brand.

## When to use

- Adding or changing a tool/action display name, command label, button, status
  line, error message, card, or notice on ANY surface.
- Reviewing a diff for user-facing copy.
- Auditing the codebase for casing / spelling violations.

## The hard rule: tool/action names are "Tool Name" (Title Case)

Every user-facing tool or action **name** uses **Title Case with spaces**:

| ✅ Correct            | ❌ snake_case          | ❌ sentence case      |
| -------------------- | --------------------- | -------------------- |
| `Read File`          | `read_file`           | `Read file`          |
| `Search Chat History`| `search_chat_history` | `Search chat history`|
| `Generate Image`     | `generate_image`      | `Generate image`     |
| `Schedule Reminder`  | `schedule_reminder`   | `Schedule reminder`  |

**Title Case = capitalize the principal words; keep short function words
(`a, an, the, to, of, for, and, or, in, on, with`) lowercase UNLESS they are the
first or last word.** So: `Convert to Markdown`, `Check the Time`, `Send to User`
— not `Convert To Markdown` or `Check The Time`.

Applies on **all three surfaces** — the Web tool chip, the Telegram tool line,
and the Google Chat card. The **internal identifier stays snake_case** (it is the
function/tool name in code and in the model's tool schema); only the **display**
string is Title Case. Never show the snake_case identifier to a user.

### Where tool display names live (the strings to fix)

- `backend/app/tools/display.py` — `make_tool_display(icon, label, present, compact)`.
  The **`label`** is the user-facing name; the `present` / `compact` formatters
  produce the user-facing one-liners. Title-case the `label` and any noun-phrase
  names inside `present` / `compact`.
- Each tool factory passes its own `label=` — e.g. `app/tools/workspace_files.py`
  (`Read File` / `Write File` / `List Folder`), `app/tools/cron_tools.py`
  (`Schedule Reminder` — already correct), `app/tools/python_exec.py` (`Run Python`).
- `backend/app/tools/external_mcp.py` builds `label=f"{server}.{tool_name}"` from raw
  MCP names — render a Title Case display form (e.g. `Notion · Create Page`); do not
  leak `notion.create_page` to the user.

> At time of writing, several labels are sentence case (`Read file`, `Generate image`,
> `Search web`, `Send message`, `Report issue`, …). Bring them to Title Case when you
> touch them; use the audit below to find them all.

## Broader user-facing-text conventions

- **American spelling & grammar** everywhere a user reads (repo rule): "color",
  "behavior", "analyze", "canceled". Matches *Coding Style & Naming Conventions* in
  `AGENTS.md`.
- **Consistent labels across channels.** The same action is named identically on
  Telegram, Google Chat, and Web. Don't call it `Send Image` in one place and
  `Image Send` in another.
- **Sentence case for prose; Title Case for names/labels.** Body text, error
  messages, and notices are normal sentences ("Couldn't reach Gemini — the API key
  looks invalid."). Only *names / labels / buttons* are Title Case.
- **No internal identifiers in user text.** Never surface snake_case keys, enum
  values, model slugs, file paths, or stack-trace jargon to a user — translate to a
  human phrase.
- **Errors are actionable, not raw.** Say what happened + what to do, in plain words;
  don't paste a raw provider/JSON error as the user-facing message.
- **Voice:** concise, warm, direct. Match the existing Paw tone; emoji are fine where
  the surface already uses them (Telegram / Google Chat), used sparingly.

## Audit the codebase

List every tool/action label, then flag likely casing violations:

```bash
# All user-facing labels (review for Title Case)
rg -n 'label\s*=\s*"[^"]*"' backend/app/tools backend/app/channels --glob '*.py'

# Likely violations: a label containing an underscore (snake_case) or a
# space-then-lowercase-word (sentence case). Review each hit and IGNORE
# legitimate lowercase function words (to / the / of / for / and / or / in / on).
rg -n 'label\s*=\s*"[^"]*(_| [a-z])[^"]*"' backend/app/tools backend/app/channels --glob '*.py'
```

Fix each so the **display** string is Title Case while the underlying
tool/function identifier stays unchanged.

## Verify

Before committing user-facing text, ask:

- Is every tool/action **name** Title Case (`Tool Name`) — not `tool_name`, not
  `Tool name`?
- Did I keep short function words (`to / the / of` …) lowercase unless first or last?
- Is the label identical across Telegram, Google Chat, and Web?
- American spelling? No internal identifiers leaked to the user? Errors actionable?
