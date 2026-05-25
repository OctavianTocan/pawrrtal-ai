from app.core.plugins import (
    EnvKeySpec,
    Plugin,
)
from app.core.plugins.registry import register_plugin
from app.plugins.active_recall.recall_agent import run_active_recall

active_recall_plugin = Plugin(
    id="active_recall",
    name="Active Recall",
    description="Auto-searches long-term memory before each turn so the agent remembers without being asked.",
    env_keys=(
        EnvKeySpec(
            name="ACTIVE_RECALL_ENABLED",
            label="Active Recall Enabled",
            required=False,
        ),
        EnvKeySpec(
            name="ACTIVE_RECALL_MODEL",
            label="Active Recall Model",
            required=False,
        ),
        EnvKeySpec(
            name="ACTIVE_RECALL_SEARCH_WORKSPACE",
            label="Active Recall Search Workspace",
            required=False,
        ),
        EnvKeySpec(
            name="ACTIVE_RECALL_SYSTEM_PROMPT",
            label="Active Recall System Prompt",
            required=False,
        ),
    ),
    tool_factories=(),
    pre_turn_hooks=(run_active_recall,),
)

register_plugin(active_recall_plugin)
