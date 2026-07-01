#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import argparse
from datetime import datetime

def load_api_key():
    # Try environment variable first
    api_key = os.environ.get("FIREFLIES_API_KEY")
    if api_key:
        return api_key

    # List of candidate paths to check for .env
    candidates = []
    
    # 1. Check relative to script dir (multiple levels up)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(script_dir, "..", "..", "..", ".env"))
    candidates.append(os.path.join(script_dir, "..", "..", "..", "..", ".env"))
    candidates.append(os.path.join(script_dir, "..", "..", "..", "..", "..", ".env"))
    
    # 2. Check the dev-admin workspace .env explicitly
    candidates.append("/Volumes/WorkDriveExternal/Projects/Personal/pawrrtal-ai/workspaces/dev-admin/.env")
    
    # 3. Check current working directory and its parents
    curr = os.getcwd()
    while True:
        candidates.append(os.path.join(curr, ".env"))
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent

    for env_path in candidates:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("FIREFLIES_API_KEY="):
                            val = line.split("=", 1)[1].strip()
                            if val.startswith(('"', "'")) and val.endswith(('"', "'")):
                                val = val[1:-1]
                            if val:
                                return val
            except Exception:
                pass
    return None


def query_fireflies(query, variables=None):
    api_key = load_api_key()
    if not api_key:
        print("Error: FIREFLIES_API_KEY not found in environment or .env file.")
        sys.exit(1)

    req_payload = {"query": query}
    if variables:
        req_payload["variables"] = variables

    req_data = json.dumps(req_payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.fireflies.ai/graphql",
        data=req_data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as res:
            resp_data = json.loads(res.read().decode("utf-8"))
            if "errors" in resp_data:
                print("GraphQL Errors:")
                for err in resp_data["errors"]:
                    print(f"  - {err.get('message')}")
                sys.exit(1)
            return resp_data.get("data", {})
    except Exception as e:
        print(f"HTTP Request failed: {e}")
        sys.exit(1)

def format_date(timestamp_ms):
    if not timestamp_ms:
        return "Unknown Date"
    try:
        dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(timestamp_ms)

def cmd_list(args):
    query = """
    query GetTranscripts($limit: Int, $skip: Int) {
      transcripts(limit: $limit, skip: $skip) {
        id
        title
        date
        duration
        transcript_url
        host_email
      }
    }
    """
    variables = {
        "limit": args.limit,
        "skip": args.skip
    }
    data = query_fireflies(query, variables)
    transcripts = data.get("transcripts", [])
    
    if not transcripts:
        print("No meetings found.")
        return

    print(f"### Recent Meetings (Total: {len(transcripts)})\n")
    print("| Meeting ID | Title | Date & Time | Duration | Link |")
    print("|---|---|---|---|---|")
    for t in transcripts:
        date_str = format_date(t.get("date"))
        duration = t.get("duration", 0)
        # Format duration to 1 decimal place
        dur_str = f"{duration:.1f}m" if duration else "N/A"
        title = t.get("title", "Untitled Meeting").replace("|", "\\|")
        url = t.get("transcript_url", "")
        url_markdown = f"[Link]({url})" if url else "N/A"
        print(f"| `{t['id']}` | {title} | {date_str} | {dur_str} | {url_markdown} |")

def cmd_search(args):
    # Fireflies query for transcripts with keyword or title
    query = """
    query SearchTranscripts($keyword: String, $title: String, $limit: Int) {
      transcripts(keyword: $keyword, title: $title, limit: $limit) {
        id
        title
        date
        duration
        transcript_url
      }
    }
    """
    variables = {
        "limit": args.limit
    }
    if args.title_only:
        variables["title"] = args.query
    else:
        variables["keyword"] = args.query

    data = query_fireflies(query, variables)
    transcripts = data.get("transcripts", [])

    if not transcripts:
        print(f"No meetings found matching: '{args.query}'")
        return

    print(f"### Search Results for '{args.query}' (Total: {len(transcripts)})\n")
    print("| Meeting ID | Title | Date & Time | Duration | Link |")
    print("|---|---|---|---|---|")
    for t in transcripts:
        date_str = format_date(t.get("date"))
        duration = t.get("duration", 0)
        dur_str = f"{duration:.1f}m" if duration else "N/A"
        title = t.get("title", "Untitled Meeting").replace("|", "\\|")
        url = t.get("transcript_url", "")
        url_markdown = f"[Link]({url})" if url else "N/A"
        print(f"| `{t['id']}` | {title} | {date_str} | {dur_str} | {url_markdown} |")

def cmd_get(args):
    query = """
    query GetTranscriptDetail($id: String!) {
      transcript(id: $id) {
        id
        title
        date
        duration
        transcript_url
        host_email
        organizer_email
        summary {
          keywords
          overview
          action_items
          shorthand_bullet
        }
        sentences {
          speaker_name
          text
          start_time
        }
      }
    }
    """
    variables = {"id": args.id}
    data = query_fireflies(query, variables)
    t = data.get("transcript")
    
    if not t:
        print(f"Error: Meeting with ID '{args.id}' not found.")
        sys.exit(1)

    print(f"# {t.get('title', 'Untitled Meeting')}\n")
    print(f"- **ID:** `{t.get('id')}`")
    print(f"- **Date & Time:** {format_date(t.get('date'))}")
    duration = t.get("duration", 0)
    print(f"- **Duration:** {duration:.1f} minutes" if duration else "- **Duration:** N/A")
    print(f"- **Host Email:** {t.get('host_email') or 'N/A'}")
    print(f"- **Organizer Email:** {t.get('organizer_email') or 'N/A'}")
    print(f"- **Transcript URL:** {t.get('transcript_url') or 'N/A'}\n")

    summary = t.get("summary") or {}
    
    if summary.get("keywords"):
        print("## Keywords")
        print(", ".join(summary["keywords"]) + "\n")

    if summary.get("overview"):
        print("## Overview")
        print(summary["overview"].strip() + "\n")

    if summary.get("action_items"):
        print("## Action Items")
        print(summary["action_items"].strip() + "\n")

    if summary.get("shorthand_bullet"):
        print("## Shorthand Outline")
        print(summary["shorthand_bullet"].strip() + "\n")

    sentences = t.get("sentences") or []
    if args.sentences and sentences:
        print("## Transcript Sentences")
        for s in sentences:
            speaker = s.get("speaker_name") or "Unknown"
            text = s.get("text") or ""
            start = s.get("start_time", 0)
            
            # Format start time in minutes:seconds
            try:
                start_sec = float(start)
                minutes = int(start_sec // 60)
                seconds = int(start_sec % 60)
                time_str = f"[{minutes:02d}:{seconds:02d}]"
            except Exception:
                time_str = f"[{start}]"
                
            print(f"- **{speaker}** {time_str}: {text}")

def main():
    parser = argparse.ArgumentParser(
        description="Fireflies.ai CLI - Retrieve and search meeting summaries and transcripts."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list command
    p_list = subparsers.add_parser("list", help="List recent meetings")
    p_list.add_argument("--limit", type=int, default=5, help="Number of meetings to retrieve (default: 5)")
    p_list.add_argument("--skip", type=int, default=0, help="Offset number of meetings")

    # search command
    p_search = subparsers.add_parser("search", help="Search meetings by keyword or title")
    p_search.add_argument("query", type=str, help="Search term/keyword")
    p_search.add_argument("--title-only", action="store_true", help="Search only in meeting titles")
    p_search.add_argument("--limit", type=int, default=5, help="Max search results (default: 5)")

    # get command
    p_get = subparsers.add_parser("get", help="Get full details of a specific meeting")
    p_get.add_argument("id", type=str, help="Meeting ID")
    p_get.add_argument("--sentences", action="store_true", help="Include full sentence-by-sentence transcript")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "get":
        cmd_get(args)

if __name__ == "__main__":
    main()
