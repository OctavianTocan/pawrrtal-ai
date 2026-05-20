"""Multimodal ``aiter_user_prompt`` envelope assembly for the Claude SDK.

The Claude SDK accepts either a plain string or an ``AsyncIterable[dict]``
for the ``prompt`` argument, but enforces the streaming-mode shape
whenever a permission hook (``can_use_tool``) is registered — which the
provider now always does via the bridge. Yielding one envelope keeps
every call site uniform regardless of whether tools were mounted on
this turn.

Pulled into its own module so :mod:`app.core.providers.claude.provider`
stays under the 500-line file budget.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


async def _aiter_user_prompt(
    question: str,
    images: list[dict[str, str]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Wrap a single user message as the streaming-mode input the SDK expects.

    PR 05: when ``images`` is supplied, the user message becomes a
    multimodal content list (images first, then the text question)
    matching Claude's ``messages.content`` shape:

        [{"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}},
         {"type": "text", "text": question}]
    """
    if not images:
        yield {
            "type": "user",
            "message": {"role": "user", "content": question},
        }
        return
    blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.get("media_type", "image/png"),
                "data": image["data"],
            },
        }
        for image in images
        if "data" in image
    ]
    blocks.append({"type": "text", "text": question})
    yield {
        "type": "user",
        "message": {"role": "user", "content": blocks},
    }
