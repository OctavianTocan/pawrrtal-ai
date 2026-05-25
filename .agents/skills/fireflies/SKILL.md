---
name: fireflies
description: Retrieve and search meeting summaries, transcripts, and action items from Fireflies.ai. Use when asked to check recent meetings, search for specific topics discussed in meetings, or get transcripts/details of a meeting.
---

# Fireflies Meeting Retrieval

Query and search meeting transcripts, summaries, and action items from the team's Fireflies.ai workspace.

## Quick start

Run the Fireflies CLI utility via Python inside the project repository to retrieve meeting data.

```bash
# List the last 5 meetings
python3 .agents/skills/fireflies/scripts/fireflies_cli.py list

# Search for meetings by a keyword in transcripts
python3 .agents/skills/fireflies/scripts/fireflies_cli.py search "react development"

# Get details of a specific meeting (overview, action items, shorthand outline)
python3 .agents/skills/fireflies/scripts/fireflies_cli.py get "MEETING_ID"

# Get the full sentence-by-sentence transcript of a specific meeting
python3 .agents/skills/fireflies/scripts/fireflies_cli.py get "MEETING_ID" --sentences
```

## Workflows

### 1. Checking recent meetings
Use this workflow when the user asks "what did we discuss in the recent meetings?" or wants to catch up on recent work.
- [ ] Run `python3 .agents/skills/fireflies/scripts/fireflies_cli.py list --limit 5` to get the list of recent meetings.
- [ ] Present the list to the user as a Markdown table.
- [ ] If the user asks for details on a specific meeting, run the `get` command for that meeting ID.

### 2. Searching for specific topics
Use this workflow when searching for historical context or decisions on a feature/topic.
- [ ] Run `python3 .agents/skills/fireflies/scripts/fireflies_cli.py search "<topic>"` to find relevant meetings.
- [ ] For the most relevant matches, run `python3 .agents/skills/fireflies/scripts/fireflies_cli.py get "<id>"` to fetch the overview and action items.
- [ ] Synthesize the findings and present them to the user.
