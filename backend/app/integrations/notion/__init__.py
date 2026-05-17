"""Notion integration for Pawrrtal.

Importing this package registers the Notion :class:`Plugin` against
:mod:`app.core.plugins.registry`, exposing the eighteen ``notion_*``
tools to any agent whose workspace has a ``NOTION_API_KEY`` configured.

Execution is delegated to the official Notion CLI (``ntn``):
:mod:`app.integrations.notion.ntn_client` shells out per call with the
workspace's token injected via ``NOTION_API_TOKEN`` and an isolated
``HOME`` so any state ``ntn`` writes can't leak between workspaces.
Each invocation is logged to :class:`app.models.NotionOperationLog`
so ``notion_logs_read`` can surface history without scraping uvicorn
output.

Design rationale lives in
``frontend/content/docs/handbook/decisions/2026-05-15-plugin-system-and-notion-integration.mdx``.
"""

from app.integrations.notion.plugin import notion_plugin

__all__ = ["notion_plugin"]
