# Step Planner Prompt Template

Use this template when dispatching a planning sub-agent to write the detail file for one step. Follow the active runtime's subagent types and `AGENTS.md` model rules.

**Dispatch:** one sub-agent per step. Independent steps in parallel; dependent steps sequentially so later sub-agents can read earlier step files.

**Sub-agent receives:**
- Brainstorm context (`.context/plans/brainstorm.md`)
- Step description, goal, dependencies
- Relevant source files and skill files for this step
- The format reference from `references/writing-plans.md`

**Sub-agent produces:** `.context/plans/step-N-<name>.md` with exact paths, full code blocks, verification commands, commit messages, and a decomposition hint.

```
Task tool:
  description: "Write detailed implementation plan for step N"
  prompt: |
    You are writing a detailed implementation plan for one step of a larger project.

    **Step:** [STEP_NUMBER] — [STEP_NAME]
    **Goal:** [STEP_GOAL]
    **Dependencies:** [DEPENDS_ON or "none"]

    **Brainstorm context:**
    [BRAINSTORM_CONTENT]

    **Relevant source files:**
    [LIST_OF_FILES_TO_READ]

    **Relevant skills to read:**
    [LIST_OF_SKILL_NAMES — e.g., domain-effect, paw, domain-cli, extension-boundaries]

    **Writing format reference:**
    [CONTENT_OF_WRITING_PLANS_MD]

    Write a detailed step plan following the "Step Detail File Format" from the
    writing reference. Save it to `.context/plans/step-[N]-[name].md`.

    Requirements:
    - Every file path must be exact and verified by reading the codebase
    - Complete code in all implementation sections, not descriptions of code
    - Include verification commands with expected output
    - Include commit messages
    - Include a decomposition hint for the executor sub-agent
    - Read the relevant domain skills listed above before writing the plan
    - Follow all AGENTS.md conventions
```

**Parallelization:**
- Independent step planners run in parallel.
- Dependent step planners run sequentially; pass earlier step file paths in `[BRAINSTORM_CONTENT]` or as additional context.
- The critic sub-agent runs only after every step planner completes.
