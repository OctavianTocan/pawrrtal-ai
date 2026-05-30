"""Provider-agnostic Exa web-search tool.

Single async core (:func:`exa_search`) that hits Exa's search API
(`POST https://api.exa.ai/search`) and returns a compact list of
``ExaSearchHit`` rows. The Claude Agent SDK and agent-loop wrappers both
delegate here; the network call lives in exactly one place.

Design notes
------------
* Auth is ``x-api-key: <EXA_API_KEY>`` per Exa's docs.
* Defaults are tuned for chat agents: ``type="auto"`` (Exa's recommended
  balanced mode), ``num_results=5`` (keeps token usage low), and
  ``contents.highlights=True`` (~10x fewer tokens than full text per
  Exa's "Best Practices for Agents" guide).
* Errors are caught and returned as a structured dict instead of raising
  so tool callers (LLMs) can surface a readable message rather than
  crashing the turn.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

import httpx

from app.infrastructure.config import settings

logger = logging.getLogger(__name__)


# Exa REST endpoint and the recommended defaults for agent workflows
# (see https://exa.ai/docs/reference/search-api-guide-for-coding-agents.md).
EXA_API_URL = "https://api.exa.ai/search"
DEFAULT_NUM_RESULTS = 5
MAX_NUM_RESULTS = 10
DEFAULT_TYPE = "auto"
DEFAULT_TIMEOUT_SECONDS = 20.0
# Lowest 4xx status — used to detect both client and server errors in
# one branch instead of sprinkling magic numbers through the response
# handler.
HTTP_ERROR_STATUS_THRESHOLD = 400


class ExaSearchHit(TypedDict, total=False):
    """A single Exa search result, normalised for downstream consumers."""

    title: str
    url: str
    published_date: str | None
    author: str | None
    highlights: list[str]
    text: str
    summary: str


class ExaSearchResult(TypedDict):
    """Return shape of :func:`exa_search`. ``error`` is set on failure."""

    query: str
    results: list[ExaSearchHit]
    error: str | None


def _normalise_hit(raw: dict[str, Any]) -> ExaSearchHit:
    """Project Exa's response row down to the fields chat surfaces actually use.

    Exa returns ``image``, ``favicon``, ``id``, ``score``, etc. that the
    model does not need to reason about — keeping only the fields the
    assistant might cite reduces context cost without losing information.
    """
    hit: ExaSearchHit = {
        "title": str(raw.get("title", "") or ""),
        "url": str(raw.get("url", "") or ""),
        "published_date": raw.get("publishedDate"),
        "author": raw.get("author"),
        "highlights": list(raw.get("highlights") or []),
    }
    text = raw.get("text")
    if isinstance(text, str) and text:
        hit["text"] = text
    summary = raw.get("summary")
    if isinstance(summary, str) and summary:
        hit["summary"] = summary
    return hit


async def exa_search(
    query: str,
    *,
    num_results: int = DEFAULT_NUM_RESULTS,
    include_full_text: bool = False,
    api_key: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> ExaSearchResult:
    """Run a web search through Exa and return normalised hits.

    Args:
        query: Natural-language search query. Long, semantically rich
            descriptions work best — Exa is built around neural search.
        num_results: How many hits to return. Clamped to ``MAX_NUM_RESULTS``
            so a noisy LLM can't blow the token budget.
        include_full_text: When ``True``, include the full ``text`` body
            for each hit alongside ``highlights``. Default is ``False`` so
            the model stays in highlights-only mode (Exa's recommended
            agent setup).
        api_key: Override for ``settings.exa_api_key``. Tests pass a stub.
        timeout_seconds: HTTP timeout for the API call.

    Returns:
        ``ExaSearchResult`` with the original query, normalised hits, and
        a populated ``error`` string when the request failed (network
        error, missing key, non-2xx response, etc.). On success ``error``
        is ``None``.
    """
    key = api_key if api_key is not None else settings.exa_api_key
    if not key:
        return {
            "query": query,
            "results": [],
            "error": (
                "Exa API key is not configured on the server. "
                "Set EXA_API_KEY in the backend env to enable web search."
            ),
        }

    capped = max(1, min(num_results, MAX_NUM_RESULTS))
    contents: dict[str, Any] = {"highlights": True}
    if include_full_text:
        contents["text"] = True

    payload: dict[str, Any] = {
        "query": query,
        "type": DEFAULT_TYPE,
        "numResults": capped,
        "contents": contents,
    }
    headers = {"x-api-key": key, "content-type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(EXA_API_URL, json=payload, headers=headers)
    except httpx.HTTPError as error:
        logger.warning("Exa search transport error: %s", error)
        return {
            "query": query,
            "results": [],
            "error": f"Web search transport error: {error}",
        }

    if response.status_code >= HTTP_ERROR_STATUS_THRESHOLD:
        # Try to surface Exa's own error message; fall back to status text.
        body_message = ""
        try:
            body_message = str(response.json().get("error") or "")
        except ValueError:
            body_message = response.text
        logger.warning("Exa search HTTP %s: %s", response.status_code, body_message or "(no body)")
        return {
            "query": query,
            "results": [],
            "error": (
                f"Web search returned HTTP {response.status_code}"
                + (f": {body_message}" if body_message else "")
            ),
        }

    try:
        body = response.json()
    except ValueError as error:
        logger.warning("Exa search JSON decode error: %s", error)
        return {
            "query": query,
            "results": [],
            "error": "Web search returned a malformed response.",
        }

    raw_results = body.get("results")
    if not isinstance(raw_results, list):
        return {"query": query, "results": [], "error": None}

    return {
        "query": query,
        "results": [_normalise_hit(row) for row in raw_results if isinstance(row, dict)],
        "error": None,
    }


def format_results_as_markdown(result: ExaSearchResult) -> str:
    """Render an :func:`exa_search` result as a Markdown summary.

    Used by both wrappers as the "human readable" tool output the LLM
    will see — every line is grounded in a result with a clickable URL
    so the assistant can cite directly. Errors render as a single
    italic line so the model can apologise gracefully.
    """
    if result["error"]:
        return f"_Web search failed: {result['error']}_"

    hits = result["results"]
    if not hits:
        return f'No web results found for "{result["query"]}".'

    lines: list[str] = [f'Web search results for **"{result["query"]}"**:', ""]
    for index, hit in enumerate(hits, start=1):
        title = hit.get("title") or hit.get("url") or "(untitled)"
        url = hit.get("url") or ""
        lines.append(f"{index}. [{title}]({url})")
        published = hit.get("published_date")
        author = hit.get("author")
        meta_bits = [bit for bit in [author, published] if bit]
        if meta_bits:
            lines.append(f"   _{' · '.join(meta_bits)}_")
        lines.extend(f"   > {snippet.strip()}" for snippet in hit.get("highlights") or [])
        if "summary" in hit:
            lines.append(f"   {hit['summary']}")
        lines.append("")
    return "\n".join(lines).rstrip()
