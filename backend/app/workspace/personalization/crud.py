"""CRUD operations for the UserPersonalization 1:1 row.

The wizard is fundamentally an upsert: the user can save a partial
profile, refresh, save more, etc. We model it as a full-replacement PUT
so the frontend doesn't have to track which fields it has touched.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio.session import AsyncSession

from app.models import UserPersonalization
from app.schemas import PersonalizationProfile


async def get_personalization(
    user_id: uuid.UUID, session: AsyncSession
) -> UserPersonalization | None:
    """Fetch the personalization row for the given user.

    Returns ``None`` when the user hasn't filled the wizard in yet.
    """
    stmt = select(UserPersonalization).where(UserPersonalization.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_personalization(
    user_id: uuid.UUID,
    payload: PersonalizationProfile,
    session: AsyncSession,
) -> UserPersonalization:
    """Insert or update the personalization row.

    Treats the payload as a full replacement: every field on the row is
    overwritten with the value from the payload (including nulls). This
    matches the frontend's behavior of POSTing the entire wizard state
    on every step transition, so partial progress round-trips correctly
    without tracking dirty fields.
    """
    existing = await get_personalization(user_id, session)
    now = datetime.now()

    if existing is None:
        row = UserPersonalization(
            user_id=user_id,
            name=payload.name,
            company_website=payload.company_website,
            linkedin=payload.linkedin,
            role=payload.role,
            goals=payload.goals,
            connected_channels=payload.connected_channels,
            chatgpt_context=payload.chatgpt_context,
            personality=payload.personality,
            custom_instructions=payload.custom_instructions,
            updated_at=now,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    existing.name = payload.name
    existing.company_website = payload.company_website
    existing.linkedin = payload.linkedin
    existing.role = payload.role
    existing.goals = payload.goals
    existing.connected_channels = payload.connected_channels
    existing.chatgpt_context = payload.chatgpt_context
    existing.personality = payload.personality
    existing.custom_instructions = payload.custom_instructions
    existing.updated_at = now
    session.add(existing)
    await session.commit()
    await session.refresh(existing)
    return existing
