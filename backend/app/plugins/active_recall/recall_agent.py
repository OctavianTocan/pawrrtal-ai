from app.core.plugins.types import PreTurnHookContext

SYSTEM_PROMPT = """
You search long-term conversation memory. Return EITHER a single short summary (<=600 chars) of context relevant to the user message OR the literal string NONE. No preamble.
"""


async def run_active_recall(ctx: PreTurnHookContext) -> str | None:
    """Search LCM for context relevant to the user's question before the main agent turn."""
    try:
        # ----
        # Build a tool list with only the LCM tools.
        # What we're trying to do here is to spawn an agent. It's kind of a sub-agent of sorts, which will go and look in the memory using the LCM tools to try and find information that might be relevant for this turn. This has to use a very fast model. And the only tools that it really needs are related to LCM.
        # ----
        return "Tried"
    except Exception as e:
        return f"Error running active recall: {e}"
