"""Seeded long-conversation eval scenarios for the LCM retrieval harness.

Issue #252 requires at least six scenario *shapes* — pinpoint, broad,
multi-hop, contradiction/change, source recall, and negative recall.
Each scenario seeds enough turns to push the relevant fact *outside*
the default fresh-tail window so the eval actually measures the
retrieval/assembly layer rather than the trivial tail.

These fixtures are intentionally small and prose-flat: the harness
answerer is deterministic and only needs the target spans to be
present somewhere in the seeded turns or summaries.  We are not
training a model; we are measuring whether the right text reached
the model's input.
"""

from __future__ import annotations

from app.core.lcm.evals import LCMEvalScenario, SeedSummary

# Padding turns are reused everywhere we need to push the target fact
# beyond the fresh-tail window.  Distinct content per index keeps the
# baseline mode from accidentally surfacing the target via collision.
_PADDING_TOPICS = (
    "discussed the colour of the homepage button",
    "talked about adding a new copy edit pass to the marketing site",
    "argued about whether dark mode should default on for new accounts",
    "scoped the migration of the analytics pipeline to ClickHouse",
    "estimated effort for the i18n string scrape across the dashboard",
    "compared two competing icons for the workspace switcher",
    "noted the latency regression on the documents tab last Tuesday",
    "rehashed the SSO debate from the partnerships meeting",
    "swept the dependabot PR queue in the mobile repo",
    "tabled the question of whether to rename the Inbox screen",
)


def _padding(
    count: int, *, role_cycle: tuple[str, ...] = ("user", "assistant")
) -> list[dict[str, str]]:
    """Return ``count`` padding turns alternating roles."""
    turns: list[dict[str, str]] = []
    for i in range(count):
        role = role_cycle[i % len(role_cycle)]
        topic = _PADDING_TOPICS[i % len(_PADDING_TOPICS)]
        turns.append({"role": role, "content": f"Padding turn {i}: {topic}."})
    return turns


def _pinpoint_summary_model_scenario() -> LCMEvalScenario:
    """Pinpoint: which exact model did we pick for summaries?"""
    target_fact = (
        "We decided that summary generation will use the "
        "gemini-2.5-flash-preview-05-20 model for cost reasons."
    )
    turns: list[dict[str, str]] = [
        {"role": "user", "content": "Pick a model for the summary compaction job."},
        {"role": "assistant", "content": target_fact},
        *_padding(10),
        {"role": "user", "content": "Quick aside — should the inbox auto-archive?"},
        {"role": "assistant", "content": "Let's defer that to next week."},
    ]
    return LCMEvalScenario(
        id="pinpoint_summary_model",
        intent="pinpoint",
        question="What exact model did we decide to use for summaries?",
        seed_turns=turns,
        expected_fact_patterns=[r"gemini-2\.5-flash-preview-05-20"],
        expected_source_substrings=["gemini-2.5-flash-preview-05-20"],
        notes="Target fact is at ordinal 1; padding pushes it beyond a fresh-tail of 4.",
    )


def _broad_telegram_blockers_scenario() -> LCMEvalScenario:
    """Broad: what did we decide about Telegram demo blockers?"""
    target_fact = (
        "Demo blocker list: (a) skip the login wall for demo mode, "
        "(b) bypass the workspace-connect onboarding step, "
        "(c) suppress the API-key banner."
    )
    turns: list[dict[str, str]] = [
        {"role": "user", "content": "Let's pin down the Telegram demo blockers."},
        {"role": "assistant", "content": target_fact},
        *_padding(8),
        {"role": "user", "content": "Switching topics — got the new pricing sheet?"},
        {"role": "assistant", "content": "I'll send it over today."},
    ]
    return LCMEvalScenario(
        id="broad_telegram_demo_blockers",
        intent="broad",
        question="What did we decide about the Telegram demo blockers?",
        seed_turns=turns,
        expected_fact_patterns=[r"workspace-connect", r"login wall"],
        expected_source_substrings=["workspace-connect onboarding"],
        notes=(
            "Broad query — the target spans multiple sub-decisions in one assistant turn"
            " outside the fresh tail."
        ),
    )


def _multi_hop_onboarding_regression_scenario() -> LCMEvalScenario:
    """Multi-hop: which earlier decision caused the later regression?"""
    summary_prose = (
        "Earlier in the discussion the team agreed to remove the workspace-connect"
        " step from the onboarding flow so the Telegram demo would skip straight"
        " into the chat surface."
    )
    turns: list[dict[str, str]] = [
        {"role": "user", "content": "Quick recap on onboarding decisions."},
        {"role": "assistant", "content": "Earlier we agreed to drop the workspace-connect step."},
        {"role": "user", "content": "Cool, anything else?"},
        {"role": "assistant", "content": "Padding-style note about copy edits."},
        *_padding(6),
        {
            "role": "user",
            "content": "Bug: new accounts have no default workspace after onboarding.",
        },
        {
            "role": "assistant",
            "content": ("Right — that follows from dropping the workspace-connect step earlier."),
        },
    ]
    summary = SeedSummary(
        content=summary_prose,
        replaces_turn_indexes=[0, 1, 2, 3],
    )
    return LCMEvalScenario(
        id="multi_hop_onboarding_regression",
        intent="multi_hop",
        question="Which earlier decision caused the missing-default-workspace bug?",
        seed_turns=turns,
        seed_summaries=[summary],
        expected_fact_patterns=[r"workspace-connect", r"onboarding"],
        expected_source_substrings=["workspace-connect step"],
        notes=(
            "The cause sits in a summary node and the symptom sits in a recent raw turn;"
            " mode under test must surface both."
        ),
    )


def _contradiction_inbox_archive_scenario() -> LCMEvalScenario:
    """Contradiction/change: what did we change our mind about?"""
    summary_prose = "Original position: inbox auto-archives messages older than seven days."
    turns: list[dict[str, str]] = [
        {"role": "user", "content": "Inbox archiving cadence?"},
        {"role": "assistant", "content": "Auto-archive everything older than seven days."},
        {"role": "user", "content": "Sticking with that?"},
        {"role": "assistant", "content": "Yes, agreed for now."},
        *_padding(6),
        {"role": "user", "content": "Rethinking: enterprise users hate auto-archive."},
        {
            "role": "assistant",
            "content": (
                "Updated plan: disable auto-archive by default; users opt-in per workspace."
            ),
        },
    ]
    summary = SeedSummary(
        content=summary_prose,
        replaces_turn_indexes=[0, 1, 2, 3],
    )
    return LCMEvalScenario(
        id="contradiction_inbox_archive",
        intent="contradiction",
        question="What did we change our mind about regarding inbox archiving?",
        seed_turns=turns,
        seed_summaries=[summary],
        expected_fact_patterns=[
            r"auto-archive",
            r"disable auto-archive by default",
        ],
        expected_source_substrings=["auto-archive"],
        notes=(
            "Original stance lives in a summary; revised stance lives in the fresh tail."
            " Mode under test must surface both for a complete contradiction trace."
        ),
    )


def _source_recall_pricing_scenario() -> LCMEvalScenario:
    """Source recall: where did this claim come from?"""
    cited_fact = (
        "Pricing tier breakpoint set at 25 active workspaces per team. "
        "Source: workspaces-pricing-2026-Q2.md, section 'Tier ceilings'."
    )
    turns: list[dict[str, str]] = [
        {"role": "user", "content": "Did we cite a doc for the 25-workspace breakpoint?"},
        {"role": "assistant", "content": cited_fact},
        *_padding(8),
    ]
    return LCMEvalScenario(
        id="source_recall_pricing_breakpoint",
        intent="source",
        question="Where did the 25-workspace pricing breakpoint claim come from?",
        seed_turns=turns,
        expected_fact_patterns=[r"workspaces-pricing-2026-Q2\.md"],
        expected_source_substrings=["workspaces-pricing-2026-Q2.md"],
        notes="Citation lives in the assistant turn outside the fresh tail.",
    )


def _negative_recall_dns_scenario() -> LCMEvalScenario:
    """Negative recall: a topic we never discussed."""
    turns: list[dict[str, str]] = [
        *_padding(10),
        {"role": "user", "content": "Catch up complete; anything else for this week?"},
        {"role": "assistant", "content": "Nothing else from my side."},
    ]
    return LCMEvalScenario(
        id="negative_recall_dns_migration",
        intent="negative",
        question="What did we decide about migrating our DNS provider?",
        seed_turns=turns,
        expected_fact_patterns=[r"DNS provider"],  # absence-of-match is the pass.
        expected_source_substrings=[],
        expects_unanswerable=True,
        notes="No turn discusses DNS — the agent must refuse rather than invent.",
    )


def all_scenarios() -> list[LCMEvalScenario]:
    """Return every required scenario in stable order."""
    return [
        _pinpoint_summary_model_scenario(),
        _broad_telegram_blockers_scenario(),
        _multi_hop_onboarding_regression_scenario(),
        _contradiction_inbox_archive_scenario(),
        _source_recall_pricing_scenario(),
        _negative_recall_dns_scenario(),
    ]
