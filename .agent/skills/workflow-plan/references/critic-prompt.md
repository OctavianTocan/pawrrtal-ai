# Plan Critic Prompt Template

Use this template when dispatching the lightweight critic sub-agent on the composed overall plan.

**Purpose:** Check the overall plan for cross-step coherence, missing dependencies, and gaps vs brainstorm. This is NOT a full adversarial review — it is a focused sanity check.

**Dispatch after:** The central agent composes the overall plan from all step detail files.

```
Task tool:
  description: "Review overall plan for cross-step coherence"
  prompt: |
    You are a plan critic. Review this overall plan for coherence and completeness.

    **Overall plan:** [PLAN_CONTENT or PLAN_FILE_PATH]
    **Step detail files:** [LIST_OF_STEP_FILE_PATHS]
    **Brainstorm context:** [BRAINSTORM_CONTENT or BRAINSTORM_FILE_PATH]

    ## What to Check

    | Category | What to Look For |
    |----------|------------------|
    | Cross-step conflicts | Two steps modify the same file incompatibly, or produce contradictory outputs |
    | Missing dependencies | Step N uses something from Step M but doesn't declare the dependency |
    | Ordering problems | Parallel steps that actually need to be sequential, or vice versa |
    | Gaps vs brainstorm | Requirements from the brainstorm that no step covers |
    | Convention violations | Violations of AGENTS.md conventions in proposed code or file paths |
    | File coverage | Files mentioned in brainstorm but missing from any step's file list |

    ## Calibration

    **Only flag issues that would cause real problems during execution.**
    A sub-agent building the wrong thing or getting stuck is an issue.
    Minor wording, stylistic preferences, and "nice to have" suggestions are not.

    Focus on **cross-step coherence** — individual step quality is the step planner's job.
    Your job is ensuring the steps work together as a whole.

    Approve unless there are serious gaps — missing requirements from the brainstorm,
    contradictory steps, dependency errors, or ordering problems that would cause failures.

    ## Output Format

    ## Plan Review

    **Status:** Approved | Issues Found

    **Issues (if any):**
    - [Step X ↔ Step Y]: [specific conflict or gap] — [why it matters]

    **Recommendations (advisory, do not block approval):**
    - [suggestions for improvement]
```

**Critic returns:** Status, Issues (if any), Recommendations. The central agent addresses any issues and finalizes the plan.
