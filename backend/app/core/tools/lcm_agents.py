"""Aggregator for LCM-history agent tool factories.

The five LCM tool factories live in their own modules so each one is
small and individually testable. The composer in ``agent_tools.py``
imports them through this single module to keep its fan-out under
sentrux's ``no_god_files`` threshold (15) — without this aggregator,
each LCM module is a separate edge.
"""

from __future__ import annotations

from app.core.tools.lcm_describe_agent import (
    make_lcm_describe_tool,
    make_lcm_list_summaries_tool,
)
from app.core.tools.lcm_expand_query_agent import make_lcm_expand_query_tool
from app.core.tools.lcm_grep_agent import make_lcm_grep_tool
from app.core.tools.lcm_search_agent import make_lcm_search_tool

__all__ = [
    "make_lcm_describe_tool",
    "make_lcm_expand_query_tool",
    "make_lcm_grep_tool",
    "make_lcm_list_summaries_tool",
    "make_lcm_search_tool",
]
