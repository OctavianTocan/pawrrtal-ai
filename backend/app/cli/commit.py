"""Auto-generate conventional commit messages from staged changes using Gemini directly.

Usage:
    just commit
    uv run --project backend python -m app.cli.commit
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load .env from project root (two levels up from backend/app/cli/)
_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env")

# Verify the API key is available after loading .env
if not os.environ.get("GOOGLE_API_KEY"):
    print("GOOGLE_API_KEY not found in environment or .env file.", file=sys.stderr)
    sys.exit(1)

COMMIT_AGENT_MODEL = os.environ.get("COMMIT_AGENT_MODEL", "gemini-3.1-flash-lite")

COMMIT_PROMPT = """\
You are a commit message generator. Given the staged git diff below, produce a single \
conventional commit message. Follow these rules exactly:

1. **Type**: One of feat, fix, refactor, test, chore, docs, style, ci
2. **Scope**: Infer from file paths — use `frontend` for frontend/, `backend` for backend/, \
or omit scope if changes span both or are project-root files
3. **Subject**: Imperative mood, lowercase, no period, max 72 chars
4. **Body** (optional): If the diff has multiple logical changes, add a blank line after the \
subject then bullet points with specifics

Output ONLY the commit message. No explanation, no markdown fences, no extra text.

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
    """Send the diff to Gemini and return the commit message."""
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    prompt = COMMIT_PROMPT.format(stat=stat, diff=diff)
    # See ``app/core/gemini_utils.py`` — same reason for the explicit
    # ``ContentUnion`` annotation here.
    contents: list[types.ContentUnion] = [
        types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    ]
    response = await client.aio.models.generate_content(
        model=COMMIT_AGENT_MODEL,
        contents=contents,
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty response.")
    return text


def commit(message: str) -> bool:
    """Run git commit with the given message. Returns True on success."""
    result = subprocess.run(
        ["git", "commit", "-m", message],
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

    print("Generating commit message...")
    try:
        message = asyncio.run(generate_message(stat, diff))
    except Exception as e:
        print(f"Failed to generate message: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{message}\n")
    if commit(message):
        print("Committed!")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
