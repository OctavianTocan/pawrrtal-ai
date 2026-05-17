---
# pawrrtal-unt9
title: Step 2 — Telegram plain text → real LLM reply (blocking, no streaming)
status: todo
type: feature
priority: high
created_at: 2026-05-17T18:15:57Z
updated_at: 2026-05-17T18:15:57Z
blocked_by:
    - pawrrtal-ddkb
---

## Where we are after Step 1

The bot can identify the user. `/start <code>` creates a binding. But
plain text messages still hit the echo handler at
`backend/app/integrations/telegram/bot.py:38` and reply with
`"Hello, world\! You said: <text>"`. The agent loop is never invoked.
No conversations are created. Nothing is persisted.

## What "done" looks like

1. With Step 1 already shipped (I'm bound), I send "what's the capital
   of France" to the bot.
2. Bot acknowledges quickly (e.g. starts typing indicator or replies
   within a few seconds).
3. ~5–15 seconds later the bot sends one Telegram message with the real
   LLM answer.
4. I open the web app and there's a "Telegram" conversation in the
   sidebar containing both my message and the assistant reply.
5. I send a follow-up. The bot answers with conversation context
   (knows what we were talking about).
6. Sending a plain message while NOT bound replies with an onboarding
   nudge pointing to the connect flow.

NO streaming yet. Each turn is ONE Telegram message produced after the
LLM finishes. The point of this step is to prove the wiring — bind ⇒
user resolution ⇒ conversation ⇒ agent ⇒ persistence ⇒ reply — without
fighting flood-control or edit debounce on top of it.

## Concrete changes

### 1. `backend/app/crud/channel.py` — two new helpers

**`get_user_id_for_external(provider, external_user_id, session) -> uuid.UUID | None`**

Hit on EVERY inbound Telegram message. Keep it a single indexed lookup,
not a row fetch:

```python
async def get_user_id_for_external(
    provider: str, external_user_id: str, session: AsyncSession
) -> uuid.UUID | None:
    result = await session.execute(
        select(ChannelBinding.user_id).where(
            ChannelBinding.provider == provider,
            ChannelBinding.external_user_id == external_user_id,
        )
    )
    return result.scalar_one_or_none()
```

**`get_or_create_telegram_conversation(user_id, session) -> Conversation`**

Simplest possible version — DM mode only, no forum topics, no
`origin_channel` column (it doesn't exist on this branch and we don't
need it):

```python
async def get_or_create_telegram_conversation(
    user_id: uuid.UUID, session: AsyncSession
) -> Conversation:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .where(Conversation.title.like("Telegram%"))
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    now = _utcnow()
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user_id,
        title="Telegram",
        created_at=now,
        updated_at=now,
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv
```

The `title.like("Telegram%")` pattern is the legacy DM finder — once
auto-title runs (a future step) the title will be overwritten with the
first-message summary, so we can't query by exact match. Prefix-match
keeps working for both. For now every Telegram conversation will just
be titled `"Telegram"`.

### 2. `backend/app/integrations/telegram/bot.py` — real plain-text handler

Replace the echo handler at line 38-41. New shape:

```python
@router.message(F.text)
async def handle_text(message: Message) -> None:
    if message.from_user is None:
        return  # anonymous channel posts — ignore

    async with async_session_maker() as session:
        user_id = await get_user_id_for_external(
            provider="telegram",
            external_user_id=str(message.from_user.id),
            session=session,
        )
        if user_id is None:
            await message.answer(_NOT_BOUND_MESSAGE)
            return

        conv = await get_or_create_telegram_conversation(user_id, session)

        # Show "typing…" while the LLM runs. One shot is enough for now —
        # Step 3 will add the refresh loop.
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

        reply_text = await _run_one_turn_blocking(
            user_id=user_id,
            conversation_id=conv.id,
            user_text=message.text or "",
            session=session,
        )

    await message.answer(reply_text)
```

`_run_one_turn_blocking` is a NEW module-level helper. It needs to:

- Persist the user message (use whatever helper `backend/app/api/chat.py`
  already uses — find that function, reuse it, do NOT roll a parallel
  insert).
- Build the same provider call the web chat endpoint builds. Read
  `backend/app/api/chat.py` top-to-bottom before writing this. Find:
  - How it loads conversation history.
  - How it resolves the provider (model_id → AILLM).
  - How it constructs the agent loop input.
- Iterate the streaming response into a single string accumulator.
  When the stream ends, return the accumulator.
- Persist the assistant message.

The shape is roughly:

```python
async def _run_one_turn_blocking(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_text: str,
    session: AsyncSession,
) -> str:
    # 1. Append user message to DB
    await append_user_message(conversation_id, user_text, session)
    # 2. Load history
    history = await load_history(conversation_id, session)
    # 3. Resolve provider (use conversation.model_id or catalog default)
    provider = resolve_llm(...)
    # 4. Run agent loop, collect deltas
    accumulated = ""
    async for event in provider.stream(history, ...):
        if event["type"] == "delta":
            accumulated += event["content"]
    # 5. Persist assistant message
    await append_assistant_message(conversation_id, accumulated, session)
    return accumulated or "[empty response]"
```

The actual function/import names live in `app.api.chat` and
`app.core.providers` — read those before writing. Don't invent helpers
that already exist.

### 3. `backend/app/integrations/telegram/bot.py` — module copy

Add the not-bound nudge string near the top:

```python
_NOT_BOUND_MESSAGE = (
    "Hey 👋 I don't recognize this Telegram account yet.\n\n"
    "To connect it, log in on the web app, generate a code from "
    "Settings → Channels, and send it to me as /start <code>."
)
```

## Footguns

- **Don't roll a new conversation-creation path.** `backend/app/crud/conversation.py`
  (or wherever) already has a function for the web flow. If you duplicate
  it, the column defaults will drift the moment someone adds a column.
  Read first, reuse second.
- **Don't try to use `resolve_channel("telegram")` yet.** That goes
  through `TelegramChannel.deliver()` which is still a noop. You'll get
  an empty reply. Step 3 wires the channel adapter; for Step 2 you call
  the provider directly and collect the string.
- **Conversation `model_id` may be NULL** for a brand-new Telegram
  conversation. Falls through to the catalog default — make sure the
  resolver handles that, same way the web chat endpoint does.
- **Long responses**: Telegram messages cap at 4096 chars. If the
  accumulated reply is over that, truncate with `…`. Splitting into
  multiple messages is a Step 3+ concern — for Step 2, truncate and
  move on.
- **Errors mid-turn**: if the provider throws, reply with a generic
  "something went wrong" string and log the real exception. Don't leak
  the stack trace to the user.
- **`message.from_user` can be None** for anonymous channel posts.
  Reject silently — we don't process those.

## Out of scope

- Progressive editing of one message (Step 3).
- `TelegramChannel.deliver()` — leave it as the noop stub. Use the
  provider directly.
- `/new` to start a fresh conversation (just reuse the most recent one
  for now).
- `/model` to switch model (Step 4+).
- `/stop` task cancellation (Step 4+).
- Forum topic routing (much later).
- Auto-title (much later).
- Per-conversation typing indicator refresh loop.

## How to test it

1. Step 1 must be shipped first (the binding must exist).
2. Send a plain message to the bot. Within ~10s, expect a real LLM
   reply.
3. Open the web app, find a conversation titled "Telegram" with both
   messages.
4. Send a follow-up referring to the previous message ("and what about
   Germany?"). Reply should use the prior turn as context.
5. From a Telegram account that has NOT bound, send a message. Expect
   the onboarding nudge.
6. Send a message that triggers a long response (e.g. "write a 5000
   word essay"). Expect a single truncated message ending in `…`, not
   an exception.
