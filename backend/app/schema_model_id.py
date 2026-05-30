"""Model-id validators shared by API schemas."""

from __future__ import annotations

import logging
from typing import Annotated

from pydantic import AfterValidator

from app.infrastructure.config import settings
from app.providers.catalog import default_model
from app.providers.model_id import InvalidModelId, parse_model_id

logger = logging.getLogger(__name__)


def _canonicalise_model_id(raw: str | None) -> str | None:
    """Rewrite any accepted input shape to canonical form."""
    if raw is None:
        return None
    try:
        return parse_model_id(raw).id
    except InvalidModelId as exc:
        raise ValueError(str(exc)) from exc


def _canonicalise_model_id_for_read(raw: str | None) -> str | None:
    """Output validator for ``ConversationRead.model_id``."""
    if raw is None:
        return None
    try:
        return parse_model_id(raw).id
    except InvalidModelId as exc:
        if settings.strict_conversation_read_validation:
            raise ValueError(str(exc)) from exc
        logger.warning(
            "CONVERSATION_READ_FALLBACK bad_model_id=%r error=%s",
            raw,
            exc,
        )
        return default_model().id


CanonicalModelId = Annotated[str | None, AfterValidator(_canonicalise_model_id)]
CanonicalModelIdForRead = Annotated[str | None, AfterValidator(_canonicalise_model_id_for_read)]
