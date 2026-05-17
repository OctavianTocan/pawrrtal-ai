"""Notion tool factories grouped by concern.

Eighteen tools (``notion_search``, ``notion_read``, ...) live across
the modules in this package; each module owns the factories for one
loose category so no single file exceeds the project's 500-LOC ceiling.

``factories`` exports the flat tuple the :class:`Plugin` consumes.
"""

from app.integrations.notion.tools.comments import (
    make_notion_comment_create_tool,
    make_notion_comment_list_tool,
)
from app.integrations.notion.tools.database import make_notion_query_tool
from app.integrations.notion.tools.diagnostics import (
    make_notion_doctor_tool,
    make_notion_help_tool,
    make_notion_logs_read_tool,
)
from app.integrations.notion.tools.lifecycle import (
    make_notion_delete_tool,
    make_notion_move_tool,
    make_notion_publish_tool,
)
from app.integrations.notion.tools.read import (
    make_notion_file_tree_tool,
    make_notion_read_markdown_tool,
    make_notion_read_tool,
    make_notion_search_tool,
)
from app.integrations.notion.tools.sync import make_notion_sync_tool
from app.integrations.notion.tools.write import (
    make_notion_append_tool,
    make_notion_create_tool,
    make_notion_update_markdown_tool,
    make_notion_update_page_tool,
)

# Stable tuple consumed by ``plugin.notion_plugin.tool_factories``.
# Order matches openclaw-notion's ``contracts.tools`` list so prompts
# enumerating the tool surface get a familiar ordering.
factories = (
    make_notion_search_tool,
    make_notion_read_tool,
    make_notion_append_tool,
    make_notion_create_tool,
    make_notion_read_markdown_tool,
    make_notion_update_markdown_tool,
    make_notion_update_page_tool,
    make_notion_comment_create_tool,
    make_notion_comment_list_tool,
    make_notion_query_tool,
    make_notion_delete_tool,
    make_notion_move_tool,
    make_notion_publish_tool,
    make_notion_file_tree_tool,
    make_notion_sync_tool,
    make_notion_help_tool,
    make_notion_doctor_tool,
    make_notion_logs_read_tool,
)

__all__ = ["factories"]
