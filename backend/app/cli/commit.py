"""Auto-generate conventional commit messages from staged changes using Gemini directly.

Usage:
    just commit
    uv run --project backend python -m app.cli.commit
"""

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from backend/app/cli/)
_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env")

# Verify the API key is available after loading .env
if not os.environ.get("GOOGLE_API_KEY"):
    print("GOOGLE_API_KEY not found in environment or .env file.", file=sys.stderr)
    sys.exit(1)

from app.providers import resolve_llm  # noqa: E402

COMMIT_AGENT_MODEL = os.environ.get("COMMIT_AGENT_MODEL", "google-ai:google/gemini-3.1-flash-lite")

COMMIT_PROMPT = """\
You are a commit message generator. Given the staged git diff below, produce a single \
conventional commit message. Follow these rules exactly:

1. **Type**: One of feat, fix, chore, refactor, docs, test, perf, build, ci, revert
2. **Scope**: Infer from file paths — use `frontend` for frontend/, `backend` for backend/, \
or omit scope if changes span both or are project-root files
3. **Subject**: Imperative mood, lowercase, no period, max 72 chars
4. **Body** (optional): If the diff has multiple logical changes, add a blank line after the \
subject then bullet points with specifics

Output ONLY the raw commit message text. Do NOT wrap it in markdown code blocks or quotes. \
Do NOT add any preamble, postamble, or other text.

---
STAGED DIFF STAT:
{stat}

STAGED DIFF:
{diff}
"""


def get_staged_diff() -> tuple[str, str]:
    """Return (diff_stat, full_diff) for staged changes."""
    stat = subprocess.run(
        ["git", "diff", "--cached", "--stat"],
        capture_output=True,
        text=True,
        cwd=_project_root,
        check=False,
    )
    diff = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True,
        text=True,
        cwd=_project_root,
        check=False,
    )
    return stat.stdout.strip(), diff.stdout.strip()


async def generate_message(stat: str, diff: str) -> str:
    """Send the diff to the model via provider.stream and return the commit message."""
    model_id = COMMIT_AGENT_MODEL
    provider = resolve_llm(model_id)
    prompt = COMMIT_PROMPT.format(stat=stat, diff=diff)

    pieces: list[str] = []

    # Use a dummy UUID for conversation and user, as we are in a CLI context.
    dummy_conv_id = uuid.uuid4()
    dummy_user_id = uuid.uuid4()

    async for event in provider.stream(
        question=prompt,
        conversation_id=dummy_conv_id,
        user_id=dummy_user_id,
        reasoning_effort="minimal",
    ):
        if event.get("type") == "delta":
            content = event.get("content", "")
            if content:
                pieces.append(content)

    text = "".join(pieces).strip()
    if not text:
        raise RuntimeError("LLM returned an empty response.")

    # Remove markdown code block wrappers (e.g., ``` or ```git)
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Strip surrounding quotes if the model wrapped the message in them
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        text = text[1:-1].strip()

    # Remove common explanatory prefixes
    for prefix in ["commit message:", "conventional commit message:", "suggested commit message:"]:
        if text.lower().startswith(prefix):
            text = text[len(prefix) :].strip()

    return text


def commit(message: str, no_verify: bool = False) -> bool:
    """Run git commit with the given message. Returns True on success."""
    cmd = ["git", "commit"]
    if no_verify:
        cmd.append("--no-verify")
    cmd.extend(["-m", message])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=_project_root,
        check=False,
    )
    if result.returncode == 0:
        print(result.stdout.strip())
        return True
    print(f"Commit failed:\n{result.stderr.strip()}", file=sys.stderr)
    return False


def main() -> None:
    """CLI entry point — generate and apply an AI-authored commit message for staged changes."""
    stat, diff = get_staged_diff()

    if not diff:
        print("Nothing staged. Stage some changes first (git add).")
        sys.exit(0)

    no_verify = "--no-verify" in sys.argv

    print("Generating commit message...")
    try:
        message = asyncio.run(generate_message(stat, diff))
    except Exception as e:
        print(f"Failed to generate message: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{message}\n")
    if commit(message, no_verify=no_verify):
        print("Committed!")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
