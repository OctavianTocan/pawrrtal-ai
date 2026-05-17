---
# pawrrtal-k4z0
title: Phase 9 — Turn streaming wrapper (history + persist + deliver + finalize)
status: todo
type: task
priority: normal
created_at: 2026-05-14T19:52:13Z
updated_at: 2026-05-14T19:52:13Z
parent: pawrrtal-l65f
blocked_by:
    - pawrrtal-w8xp
---

## Why

This is the **heart** of the rebuild. The bug commit (`859569bc fix(telegram):
persist messages to DB + real history`) exists because an earlier version of
the bot called the provider with `history=[]` every turn — the agent had no
memory. This bean is what fixes that, by mirroring the same persistence
pattern the web endpoint uses.

Read the project-overview HTML diagram "Telegram path" before writing.

## What to build

File: `backend/app/integrations/telegram/turn_stream.py`.

Public entry point: `stream_persisted_turn`. Three internal helpers:
`_persist_turn_start`, `_build_channel_message`,
`_deliver_and_persist_stream`, `_finalize_persisted_assistant_message`.

### Module constants

```
_HISTORY_WINDOW = 20    # matches the web endpoint exactly
```

### `stream_persisted_turn` — the top-level coordinator

Signature:

```
async def stream_persisted_turn(
    *,
    message: aiogram.Message,
    context: TelegramTurnContext,
    user_text: str,
    placeholder_message_id: int,
    provider: AILLM,
    agent_tools: list[AgentTool],
    workspace_system_prompt: str | None,
) -> None
```

Body:

```
history, assistant_message_id <- await _persist_turn_start(
    conversation_id=context.conversation_id,
    user_id=context.nexus_user_id,
    user_text=user_text,
)
channel_msg <- _build_channel_message(message, context, user_text, placeholder_message_id)
await _deliver_and_persist_stream(
    provider, channel_msg, context, user_text, history,
    agent_tools, workspace_system_prompt, assistant_message_id,
)
```

### `_persist_turn_start` — history fetch + dual insert

Open a session, do all three writes atomically, return the history snapshot
and the new assistant row's `id`.

```
async with async_session_maker() as session:
    recent_rows <- await get_messages_for_conversation(session, conversation_id, limit=20)
    history     <- [{"role": row.role, "content": row.content or ""}
                    for row in recent_rows
                    if row.role in {"user", "assistant"}]

    await append_user_message(session, conversation_id, user_id, content=user_text)
    assistant_row <- await append_assistant_placeholder(session, conversation_id, user_id)
    await session.commit()
    return history, assistant_row.id
```

These CRUD functions already exist in `backend/app/crud/chat_message.py`.
They:
- Insert a `chat_messages` row with `role="user"` / `role="assistant"`
- Assign monotonic `ordinal` (don't worry about it; CRUD handles it)
- The assistant placeholder has `assistant_status="streaming"`, empty content
- Both inserts trigger `_touch_conversation` which bumps `Conversation.updated_at`
  — this is what makes a Telegram message bubble the conversation to the top
  of the web sidebar

Filter to `{"user", "assistant"}` because there can be `system` or `tool`
rows for some flows; the provider history only takes user/assistant.

### `_build_channel_message` — pack the metadata

```
return {
    "user_id":         context.nexus_user_id,
    "conversation_id": context.conversation_id,
    "text":            user_text,
    "surface":         SURFACE_TELEGRAM,
    "model_id":        context.model_id,
    "metadata": {
        "bot":        message.bot,                # aiogram Bot instance
        "chat_id":    message.chat.id,
        "message_id": placeholder_message_id,     # the "⏳" placeholder
    },
}
```

`ChannelMessage` is a `TypedDict` so this is a plain dict literal. The
metadata is what `TelegramChannel.deliver` reads in bean 5.

### `_deliver_and_persist_stream` — the orchestrator

This is the one with the `finally` block. It must always finalize the
assistant row no matter what (cancellation, exception, normal completion).

```
channel    <- resolve_channel(SURFACE_TELEGRAM)        # TelegramChannel singleton
aggregator <- ChatTurnAggregator()                      # accumulates content/tools/timeline
final_status <- "complete"

async def _guarded_stream():
    """Wraps provider.stream so exceptions become error events.

    Why an async generator wrapper? Two reasons:
    1. The channel.deliver loop is an async-for. If the provider raises mid-stream
       the deliver loop never sees it. Wrapping converts the exception into a
       terminal "error" stream event that both the aggregator AND the channel
       see naturally.
    2. The aggregator needs to apply every event before the channel sees it.
       The wrapper is the single place to fork into both consumers.
    """
    try:
        async for event in provider.stream(
            user_text,
            context.conversation_id,
            context.nexus_user_id,
            history=history,
            tools=agent_tools or None,
            system_prompt=workspace_system_prompt,
        ):
            aggregator.apply(event)        # mirror to the persistence shadow
            yield event                     # pass through to the channel
    except Exception as exc:
        logger.exception("TELEGRAM_STREAM_ERR conversation_id=%s", context.conversation_id)
        err_event <- {"type": "error", "content": str(exc)}
        aggregator.apply(err_event)
        yield err_event
        # Do NOT re-raise — the channel needs to see the error event and
        # finish cleanly. The "failed" status lands via the aggregator.

try:
    async for _ in channel.deliver(_guarded_stream(), channel_msg):
        pass                # TelegramChannel yields nothing, deliver is side-effect
except asyncio.CancelledError:
    final_status <- "failed"
    raise                   # propagate so the caller's task knows we cancelled
finally:
    await _finalize_persisted_assistant_message(
        conversation_id=context.conversation_id,
        message_id=assistant_message_id,
        aggregator=aggregator,
        status=final_status,
    )
```

**Critical `finally` invariant**: the assistant placeholder row is in the DB
as `assistant_status="streaming"` from step 1. If you don't finalize, it stays
streaming forever and the web UI shows it as in-progress. Always finalize.

**Why `tools=agent_tools or None`**: providers expect either a non-empty
list or `None`. Empty list breaks some SDK shapes. `[] or None` → `None`.

### `_finalize_persisted_assistant_message`

```
final_status <- "failed" if aggregator.error_text else status
snapshot     <- aggregator.to_persisted_shape(status=final_status)

try:
    async with async_session_maker() as session:
        await finalize_assistant_message(session, message_id=message_id, **snapshot)
        await session.commit()
except Exception:
    logger.exception("TELEGRAM_PERSIST_ERR conversation_id=%s message_id=%s",
                     conversation_id, message_id)
    # swallow — the assistant row stays "streaming" but the user already
    # got their response via Telegram. Better than crashing the bot.
```

The aggregator promotes status to `"failed"` if it captured any error event,
even if the caller passed `"complete"` — this catches the `_guarded_stream`
error path that doesn't raise.

`finalize_assistant_message` is in `backend/app/crud/chat_message.py`. The
snapshot from `aggregator.to_persisted_shape` is the kwargs dict it expects
(content, thinking, tool_calls, timeline, thinking_duration_seconds,
assistant_status).

## Why a separate session per phase

`_persist_turn_start` opens a session, commits, exits the context manager —
the rows are durable before streaming starts. `_finalize_persisted_assistant_message`
opens a **new** session for the finalization. Two short transactions instead
of one long-held session that survives the whole stream.

Reason: the LLM stream can take 30+ seconds. A session held that long blocks
pool slots and may time out at the DB. Short transactions = healthy pool.

## Edge cases

- `CancelledError` must propagate. The `bot.py` caller (bean 11) catches it
  and logs `TELEGRAM_STREAM_CANCELLED`. Swallowing it would leak the
  cancelled task into the `_running_tasks` dict forever.
- The aggregator state is in memory — if the process dies mid-stream, the
  row stays `"streaming"`. There's no recovery path. This is acceptable for
  the current single-worker deployment; a future Redis-backed checkpoint
  would change this.
- Empty `agent_tools=[]` happens when the user hasn't completed onboarding
  (no workspace). The turn still works without tools.
- `workspace_system_prompt` may be `None` — pass through to provider.
  Providers handle `system_prompt=None` as "use whatever default".
- `history` rows with `content=None` (rare — a tool-only assistant turn)
  are coerced to `""` with `row.content or ""`.

## Tests that should pass after this

No new tests specifically target the streaming wrapper (it's covered
end-to-end by the bot-level tests after bean 11). But this bean unlocks
bean 11's integration.

## Next

Bean 10 — the auto-title helper. Fires after the stream finishes; gated by
`title_set_by IS NULL`; also renames the Telegram forum topic when applicable.
