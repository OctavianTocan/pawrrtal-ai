"""ID generation for paw.

Wraps ``uuid.uuid4`` in a single named helper so tests can monkey-patch
the generator at one seam (``app.cli.paw.ids.new_conversation_id``)
instead of patching ``uuid.uuid4`` globally.
"""

from __future__ import annotations

import uuid


def new_conversation_id() -> str:
    """Return a fresh v4 UUID as a string.

    The backend's ``POST /api/v1/conversations/{id}`` accepts a client-
    generated UUID as the primary key (see ``ConversationCreate.id``);
    paw mirrors the frontend's UUID-first flow so chat sends can include
    ``conversation_id`` in the very first ``POST /api/v1/chat/`` body.
    """
    return str(uuid.uuid4())
