"""CRUD operations for the UserAppearance 1:1 row.

Mirrors the personalization module: full-replacement upsert keyed on
``user_id``. Frontend POSTs the entire settings payload on every change
so the server doesn't need to track dirty fields. Empty / partial
payloads are valid — the application layer overlays defaults on top of
whatever the user has saved.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio.session import AsyncSession

from app.models import UserAppearance
from app.schemas import AppearanceSettings


async def get_appearance(user_id: uuid.UUID, session: AsyncSession) -> UserAppearance | None:
    """Fetch the appearance row for the given user.

    Returns ``None`` when the user has never customized their appearance —
    callers (the API layer) treat this as "use the Mistral defaults".
    """
    stmt = select(UserAppearance).where(UserAppearance.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_appearance(
    user_id: uuid.UUID,
    payload: AppearanceSettings,
    session: AsyncSession,
) -> UserAppearance:
    """Insert or update the appearance row for the given user.

    Treats the payload as a full replacement: every JSON column on the
    row is overwritten with the corresponding sub-model dumped to a
    plain dict. ``mode="json"`` keeps `Literal` / nested-model fields
    serializable directly to the database column.
    """
    existing = await get_appearance(user_id, session)
    now = datetime.now()

    light = payload.light.model_dump(mode="json")
    dark = payload.dark.model_dump(mode="json")
    fonts = payload.fonts.model_dump(mode="json")
    options = payload.options.model_dump(mode="json")

    if existing is None:
        row = UserAppearance(
            user_id=user_id,
            light=light,
            dark=dark,
            fonts=fonts,
            options=options,
            updated_at=now,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    existing.light = light
    existing.dark = dark
    existing.fonts = fonts
    existing.options = options
    existing.updated_at = now
    session.add(existing)
    await session.commit()
    await session.refresh(existing)
    return existing


async def reset_appearance(user_id: uuid.UUID, session: AsyncSession) -> None:
    """Delete the appearance row so the user falls back to defaults.

    Used by the "Reset to defaults" button in the Appearance panel.
    Idempotent — no-ops cleanly when there's no row.
    """
    existing = await get_appearance(user_id, session)
    if existing is None:
        return
    await session.delete(existing)
    await session.commit()
