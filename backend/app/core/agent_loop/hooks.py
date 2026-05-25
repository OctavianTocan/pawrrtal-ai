from app.core.plugins import all_plugins
from app.core.plugins.types import PreTurnHook


def build_pre_turn_hooks() -> list[PreTurnHook]:
    """Build the pre-turn hooks from the plugin registry."""
    out: list[PreTurnHook] = []
    for plugin in all_plugins():
        out.extend(plugin.pre_turn_hooks)
    return out
