---
# pawrrtal-0v4v
title: Phase 10 — Auto-title helper (fire-once title + editForumTopic)
status: todo
type: task
priority: normal
created_at: 2026-05-14T19:52:13Z
updated_at: 2026-05-14T19:52:13Z
parent: pawrrtal-l65f
blocked_by:
    - pawrrtal-k4z0
---

## Why

A fresh Telegram conversation is created with `title="Telegram"`. That makes
the web sidebar useless for finding a specific Telegram thread among many.
Auto-title derives a short label from the first user message — once — so the
sidebar entry becomes "Refactor the payment webhook" instead of "Telegram".

Bonus: when the conversation lives in a Telegram **forum topic**, the helper
also calls `editForumTopic` to rename the thread in the user's topic list.
Now the Telegram client UI matches the web UI.

This runs as a **fire-and-forget post-turn step** in `_run_llm_turn` (bean 11),
wrapped in a try/except so a rename failure can never break the conversation.

## What to build

In `backend/app/integrations/telegram/bot.py` (the file you'll build in
bean 11), add two module-level helpers.

### `_generate_title(text: str, max_len: int = 48) -> str`

Pseudocode:

```
cleaned <- text.strip()

# Strip a leading slash-command: belt-and-suspenders for the user typing
# "/new tell me about X" as their first message. We want "tell me about X",
# not "/new".
if cleaned.startswith("/"):
    cleaned <- cleaned.split(None, 1)[1] if " " in cleaned else ""

cleaned <- cleaned.strip()
if not cleaned:
    return "Telegram"               # fallback for empty input

if len(cleaned) <= max_len:
    return cleaned
return cleaned[:max_len - 1] + "…"  # reserve one char for the ellipsis
```

**Why 48 chars**: matches the web auto-title length cap (kept in lockstep
deliberately so a conversation's display title looks the same on both
surfaces). One ellipsis char counts against the budget.

**Why `split(None, 1)`**: `split()` with no arg splits on any whitespace.
The `1` cap keeps the rest of the message intact (preserves internal
whitespace, just drops the leading command).

### `async def _maybe_set_auto_title(*, bot, conversation_id, user_text, chat_id, thread_id) -> None`

Pseudocode:

```
async with async_session_maker() as session:
    conv <- await session.get(Conversation, conversation_id)
    if conv is None or conv.title_set_by is not None:
        return                       # already titled — fire-once gate

    title <- _generate_title(user_text)
    conv.title         <- title
    conv.title_set_by  <- "auto"     # the gate is now closed forever
    await session.commit()

logger.info("TELEGRAM_AUTO_TITLE conversation_id=%s title=%r thread_id=%s",
            conversation_id, title, thread_id)

# If the conversation is in a forum topic, rename the topic too.
# Topic-only Bot API call — graceful failure for DM-only chats.
if thread_id is not None:
    try:
        await bot.edit_forum_topic(
            chat_id=chat_id,
            message_thread_id=thread_id,
            name=title,
        )
    except Exception as exc:
        logger.warning("TELEGRAM_EDIT_TOPIC_FAILED chat_id=%s thread_id=%s error=%s",
                       chat_id, thread_id, exc)
        # swallow — bot might lack admin rights, topic might be locked, etc.
```

## Why `title_set_by` is the gate, not `title != "Telegram"`

A user might **want** their conversation title to be "Telegram" (rename it
back manually). The gate is the lifecycle marker, not the content. `NULL`
means "the auto-title pass hasn't run"; `"auto"` means "ran and wrote";
`"user"` means "user has edited it, don't touch".

The user-edit path (in the web frontend) sets `title_set_by = "user"`. Both
states block the auto-title pass.

## Why `editForumTopic` failures are warnings, not errors

Common failure modes:

- Bot lacks `can_manage_topics` admin permission in the group.
- The chat isn't actually a supergroup (topics require supergroup).
- The topic was deleted between message arrival and the post-turn pass.
- Telegram's rate limit on `editForumTopic` (separate from `editMessage`).

None of these justify failing the conversation. The DB-side title persists
either way; the Telegram-side rename is gravy.

## Edge cases

- The fire-once gate is **per-conversation**. A user with 50 Telegram
  conversations gets 50 auto-titles, one each. Good.
- Don't trust `conv.title_set_by != "auto"` — explicit `is not None` check.
  Future values (`"user"`, `"workspace"`, whatever) all block.
- `bot.edit_forum_topic` requires the bot's session to be open. In the
  shutdown path the session might be closed; the `try/except` covers it.
- User message starting with `///` (multiple slashes) — `cleaned.split(None, 1)`
  yields `["///", ...]` if there's a space, else `[""]`. Trim once more
  with `cleaned.strip()` after the strip step.

## Where it's called from

`_run_llm_turn` in `bot.py` (bean 11), after `await task` completes:

```
try:
    await _maybe_set_auto_title(
        bot=message.bot,
        conversation_id=context.conversation_id,
        user_text=user_text,
        chat_id=message.chat.id,
        thread_id=context.thread_id,
    )
except Exception:
    logger.warning("TELEGRAM_AUTO_TITLE_FAILED", exc_info=True)
```

The outer try/except is paranoia — _maybe_set_auto_title already swallows
the editForumTopic error internally, but DB commit could in principle raise.
A failed title is never worth crashing the turn.

## Tests that should pass after this

No direct unit tests for auto-title (it's covered by the broader bot tests).
This bean unblocks the final integration assemble in bean 11.

## Next

Bean 11 — the bot service: `build_telegram_service`, `_run_llm_turn`,
`_resolve_provider_with_auto_clear`, the `_running_tasks` cancellation dict,
`telegram_lifespan` with the polling/webhook split + demo-mode gate, and
the final `main.py` wiring.
