"""Plugin manifest for the Notion integration.

Importing this module registers the plugin against the global
:mod:`app.core.plugins.registry`.  ``app.integrations.__init__`` is
responsible for triggering the import; nothing else should import this
file directly (importing it twice would attempt a duplicate
registration and raise).
"""

from __future__ import annotations

from app.core.plugins import (
    EnvKeySpec,
    Plugin,
    register_plugin,
)
from app.integrations.notion.tools import factories

NOTION_INTEGRATION_URL = "https://www.notion.so/profile/integrations"

notion_plugin = Plugin(
    id="notion",
    name="Notion",
    description=(
        "Read, write, search, comment, and sync workspace content with "
        "the connected Notion workspace via the official `ntn` CLI."
    ),
    env_keys=(
        EnvKeySpec(
            name="NOTION_API_KEY",
            label="Notion API Key",
            help_url=NOTION_INTEGRATION_URL,
            required=True,
        ),
    ),
    tool_factories=factories,
)

register_plugin(notion_plugin)
