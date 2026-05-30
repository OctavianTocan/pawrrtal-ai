"""HTTP endpoints for the per-user Appearance settings panel."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.auth.users import get_allowed_user
from app.infrastructure.database.legacy import User, get_async_session
from app.models import UserAppearance
from app.schemas import (
    AppearanceFonts,
    AppearanceOptions,
    AppearanceSettings,
    ThemeColors,
)
from app.workspace.appearance import crud


def _to_settings(row: UserAppearance | None) -> AppearanceSettings:
    """Convert the ORM row (or absence) to the response schema.

    When the row is missing or any sub-blob is ``None``, returns empty
    sub-models so the frontend's overlay logic ("user value or default")
    has a stable shape to merge against.
    """
    if row is None:
        return AppearanceSettings()
    return AppearanceSettings(
        light=ThemeColors(**(row.light or {})),
        dark=ThemeColors(**(row.dark or {})),
        fonts=AppearanceFonts(**(row.fonts or {})),
        options=AppearanceOptions(**(row.options or {})),
    )


def get_appearance_router() -> APIRouter:
    """Build the appearance router (mounted at ``/api/v1/appearance``)."""
    router = APIRouter(prefix="/api/v1/appearance", tags=["appearance"])

    @router.get("", response_model=AppearanceSettings)
    async def get_appearance(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> AppearanceSettings:
        """Return the authenticated user's appearance settings.

        Returns an empty settings object (all sub-models with their own
        empty defaults) when the user has never customized appearance.
        The frontend layers these on top of the Mistral defaults from
        ``frontend/features/appearance/defaults.ts``.
        """
        row = await crud.get_appearance(user.id, session)
        return _to_settings(row)

    @router.put("", response_model=AppearanceSettings)
    async def upsert_appearance(
        payload: AppearanceSettings,
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> AppearanceSettings:
        """Create or replace the authenticated user's appearance settings."""
        row = await crud.upsert_appearance(user_id=user.id, payload=payload, session=session)
        return _to_settings(row)

    @router.delete("", status_code=status.HTTP_204_NO_CONTENT)
    async def reset_appearance(
        user: User = Depends(get_allowed_user),
        session: AsyncSession = Depends(get_async_session),
    ) -> None:
        """Reset the user's appearance back to the Mistral defaults.

        Idempotent — deletes the persisted row so subsequent GETs return
        an empty settings object that the frontend resolves to defaults.
        """
        await crud.reset_appearance(user.id, session)

    return router
