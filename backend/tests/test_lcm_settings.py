"""Settings smoke test for the LCM configuration knobs.

Part of the LCM stack — PR #1 (design doc + settings).
Confirms the five new config keys have safe off-by-default values
*at the schema level*. We instantiate a fresh ``Settings`` without the
process ``.env`` overrides so the test reflects the declared defaults,
not whatever the developer happens to have enabled locally.
"""

from __future__ import annotations


def test_lcm_settings_have_safe_defaults() -> None:
    """All LCM knobs must have sane off-by-default values."""
    from app.core.config import Settings

    # Build a fresh Settings instance with NO env overrides so the test
    # inspects the schema defaults, not the developer's local .env.
    defaults = Settings.model_construct()

    # Master switch off — no chat-router code path is altered.
    assert defaults.lcm_enabled is False
    # Numeric defaults match the upstream plugin.
    assert defaults.lcm_fresh_tail_count == 64
    assert defaults.lcm_leaf_chunk_tokens == 20000
    assert 0.0 < defaults.lcm_context_threshold <= 1.0
    # Leaf-only condensation by default.
    assert defaults.lcm_incremental_max_depth == 1
    # No summary-model override — falls back to the conversation model.
    assert defaults.lcm_summary_model == ""
