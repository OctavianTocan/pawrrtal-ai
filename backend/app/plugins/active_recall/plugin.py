from app.core.plugins import (
    Plugin,
)
from app.core.plugins.registry import register_plugin
from app.plugins.active_recall.recall_agent import run_active_recall

active_recall_plugin = Plugin(
    id="active_recall",
    name="Active Recall",
    description="Auto-searches long-term memory before each turn so the agent remembers without being asked.",
    env_keys=(),
    tool_factories=(),
    pre_turn_hooks=(run_active_recall,),
)

register_plugin(active_recall_plugin)
