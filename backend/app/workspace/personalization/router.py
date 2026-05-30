"""HTTP endpoints for the home-page personalization wizard."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.models import UserPersonalization
from app.schemas import PersonalizationProfile
from app.workspace.crud import ensure_default_workspace
from app.workspace.personalization import crud

log = logging.getLogger(__name__)


def _to_profile(row: UserPersonalization | None) -> PersonalizationProfile:
    """Convert the ORM row (or absence) to the response schema.

    Returns an empty profile when the user hasn't filled in the wizard
    yet — the frontend treats this as "no defaults yet, render placeholders".
    """
    if row is None:
        return PersonalizationProfile()
    return PersonalizationProfile(
        name=row.name,
        company_website=row.company_website,
        linkedin=row.linkedin,
        role=row.role,
        goals=row.goals,
        connected_channels=row.connected_channels,
        chatgpt_context=row.chatgpt_context,
        personality=row.personality,
        custom_instructions=row.custom_instructions,
    )


def get_personalization_router() -> APIRouter:
    """Build the personalization router (mounted at /api/v1/personalization)."""
    router = APIRouter(prefix="/api/v1/personalization", tags=["personalization"])

    @router.get("", response_model=PersonalizationProfile)
    async def get_personalization(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> PersonalizationProfile:
        """Return the authenticated user's personalization profile."""
        row = await crud.get_personalization(user.id, session)
        return _to_profile(row)

    @router.put("", response_model=PersonalizationProfile)
    async def upsert_personalization(
        payload: PersonalizationProfile,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> PersonalizationProfile:
        """Create or replace the authenticated user's personalization profile.

        Also seeds the user's default workspace the first time this endpoint
        is called (idempotent — subsequent calls are a no-op for the workspace).
        """
        row = await crud.upsert_personalization(user_id=user.id, payload=payload, session=session)

        # Seed the default workspace on first personalization save.  This is
        # the natural trigger for "onboarding complete" since the wizard writes
        # the full profile before calling finish().
        try:
            await ensure_default_workspace(
                user_id=user.id,
                session=session,
                personalization=row,
            )
            await session.commit()
        except Exception:
            log.exception("Failed to ensure default workspace for user %s", user.id)
            # Non-fatal — workspace seeding must not break the personalization save.

        return _to_profile(row)

    return router
