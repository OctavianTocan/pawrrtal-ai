import uuid

from app.core.agent_loop.types import AgentTool
from app.core.config import settings
from app.core.lcm import _collect_stream
from app.core.plugins.types import PreTurnHookContext
from app.core.providers.factory import resolve_llm
from app.core.tools.lcm_grep_agent import make_lcm_grep_tool
from app.core.tools.lcm_search_agent import make_lcm_search_tool

SYSTEM_PROMPT = """
You search long-term conversation memory. Return EITHER a single short summary (<=600 chars) of context relevant to the user message OR the literal string NONE. No preamble.
"""


async def run_active_recall(ctx: PreTurnHookContext) -> str | None:
    """Search LCM for context relevant to the user's question before the main agent turn."""
    try:
        if settings.lcm_enabled is False:
            return None

        # We're using a very fast, very cheap Google AI model to do the heavy lifting of the search.
        provider = resolve_llm("google_ai:google/gemini-3.1-flash-lite-preview")

        # TODO: This needs to be passed through the ctx, so that we can support searching for the user's memory. (Without LCM).
        search_prompt = f"Search the conversation history using your LCM tools for context relevant to the user's question: {ctx.question}"

        # The set of tools, restricted to LCM only.
        lcm_tools: list[AgentTool] = []
        lcm_tools.append(make_lcm_grep_tool(conversation_id=ctx.conversation_id))
        lcm_tools.append(make_lcm_search_tool(conversation_id=ctx.conversation_id))

        try:
            stream = provider.stream(
                question=search_prompt,
                conversation_id=uuid.uuid4(),  # isolated; not a real turn TODO: This should be easier to do. (Making a subagent that doesn't use real turns).
                user_id=ctx.user_id,
                history=None,
                tools=lcm_tools,
                system_prompt=SYSTEM_PROMPT,
            )

            answer = await _collect_stream(stream)
            if answer:
                return answer
            return "lcm_expand_query: the model returned an empty response."
        except Exception as exc:
            return f"lcm_expand_query: expansion call failed — {exc}"
    except Exception as e:
        return f"Error running active recall: {e}"
