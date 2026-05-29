"""Provider-agnostic core for the ``render_artifact`` tool.

The tool lets the agent ship an "artifact" to the user — a small, self-
contained renderable surface (think Claude artifacts, ChatGPT canvas, but
**guardrailed by a server-defined component catalog** instead of letting the
model emit arbitrary HTML/JS).

Wire shape
----------

* The agent calls ``render_artifact`` with two arguments:

  - ``title``  — short label shown on the preview card and the dialog header.
  - ``spec``   — a json-render flat-spec object: ``{"root": "id",
    "elements": {"id": {"type": "<ComponentName>", "props": {...},
    "children": ["..."]}}}``.

* The tool's *return value to the LLM* is a short confirmation string,
  **not** the spec.  The full spec escapes into the SSE stream via the
  chat router (see ``backend/app/api/chat.py``), which inspects
  ``tool_call_end`` events for this tool name and emits a sibling
  ``artifact`` SSE event.

* This split exists so the LLM does not see its own (possibly large) spec
  echoed back as "tool result" on the next turn — that would inflate
  context and bias subsequent turns.

What this module does NOT do
----------------------------

* It does **not** render anything.  Rendering happens client-side via
  ``frontend/features/chat/artifacts``, which owns the catalog of safe
  components.  The server's only job is to validate the wire shape, mint
  an id, and return the LLM-facing summary.

* It does **not** persist.  v0 artifacts are stream-only — closing the
  page drops them.  Persistence will live alongside ``chat_messages``
  (see follow-up bean).

Validation policy
-----------------

The catalog (which component names exist, which props each accepts) is
the *frontend's* contract.  The server intentionally validates only the
**top-level wire shape** so the catalog can evolve in one place without
forcing a backend redeploy on every new component.  Bad shapes fail
loudly here; bad component names fail visibly in the renderer with a
fallback "unknown component" stub.
"""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

# Cap the artifact title at a length that fits comfortably in a preview card
# header without truncation and rejects accidental "title is the whole post"
# inputs from the LLM.
_MAX_TITLE_LENGTH = 200


class ArtifactValidationError(ValueError):
    """Raised when a render_artifact call has a malformed top-level shape."""


class ArtifactPayload(TypedDict):
    """Structured payload the chat router lifts out of the tool args.

    Mirrored verbatim onto the SSE ``artifact`` event consumed by the
    frontend.  Adding fields here is a wire-compat change — bump the
    schema in :mod:`app.chat.router` and the matching frontend type at the
    same time.
    """

    id: str
    title: str
    spec: dict[str, Any]


def build_artifact(*, title: str, spec: dict[str, Any]) -> ArtifactPayload:
    """Validate the wire shape and return the SSE-ready payload.

    Args:
        title: Short label.  1..200 chars after stripping; longer titles
            are rejected so the preview card stays single-line.
        spec: json-render flat-spec object.  Must contain ``root`` (str)
            and ``elements`` (dict).  Each element must declare ``type``
            (str) and ``props`` (dict); ``children`` defaults to ``[]``.

    Returns:
        An :class:`ArtifactPayload` with a freshly minted id.

    Raises:
        ArtifactValidationError: If any of the above invariants fail.
        The error message names the failing field so the LLM can self-
        correct on the next turn.
    """
    cleaned_title = (title or "").strip()
    if not cleaned_title:
        raise ArtifactValidationError("title must be a non-empty string")
    if len(cleaned_title) > _MAX_TITLE_LENGTH:
        raise ArtifactValidationError(
            f"title must be ≤{_MAX_TITLE_LENGTH} chars (got {len(cleaned_title)})"
        )

    if not isinstance(spec, dict):
        raise ArtifactValidationError("spec must be an object")

    root = spec.get("root")
    if not isinstance(root, str) or not root:
        raise ArtifactValidationError("spec.root must be a non-empty string")

    elements = spec.get("elements")
    if not isinstance(elements, dict) or not elements:
        raise ArtifactValidationError("spec.elements must be a non-empty object")

    if root not in elements:
        raise ArtifactValidationError(f"spec.root '{root}' is not present in spec.elements")

    for element_id, element in elements.items():
        if not isinstance(element, dict):
            raise ArtifactValidationError(f"spec.elements['{element_id}'] must be an object")
        if not isinstance(element.get("type"), str):
            raise ArtifactValidationError(f"spec.elements['{element_id}'].type must be a string")
        if "props" in element and not isinstance(element["props"], dict):
            raise ArtifactValidationError(f"spec.elements['{element_id}'].props must be an object")
        children = element.get("children", [])
        if not isinstance(children, list) or not all(isinstance(c, str) for c in children):
            raise ArtifactValidationError(
                f"spec.elements['{element_id}'].children must be an array of strings"
            )

    artifact_id = f"art_{uuid.uuid4().hex[:12]}"
    return ArtifactPayload(id=artifact_id, title=cleaned_title, spec=spec)


def llm_summary_for(payload: ArtifactPayload) -> str:
    """The string the LLM sees as the tool result.

    Deliberately compact and free of spec content: the agent already
    knows what it sent, and including the spec here would echo it on the
    next turn for no benefit.
    """
    return (
        f"Artifact rendered for the user. id={payload['id']} "
        f"title={payload['title']!r}. "
        "The user can now preview and expand it inline."
    )
