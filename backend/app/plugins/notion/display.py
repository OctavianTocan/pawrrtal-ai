"""User-facing display formatting for the Notion tool.

Defines dynamically formatted present-tense and past-tense (compact) labels
for UI channels (Web interface, Telegram) without retaining any in-memory
caching/state.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.agent_loop.display import ToolDisplayPayload

UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}\b"
)

UUID_HEX_LENGTH = 32
MIN_ARGS_FOR_SUBCMD = 2
ID_DISPLAY_LENGTH = 8
TEXT_TRUNCATE_LENGTH = 20


def _make_present_label(base: str) -> str:
    """Ensure the present-tense label ends with exactly three dots, avoiding double ellipsis."""
    return f"{base.rstrip('.')[:100]}..."


def _format_id(entity_id: str) -> str:
    """Format a page, database, or data source ID."""
    entity_id = entity_id.strip("'\"")
    prefix = ""
    for p in ("database:", "page:", "data-source:"):
        if entity_id.startswith(p):
            prefix = p
            entity_id = entity_id[len(p) :]
            break

    hex_pattern = r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{32})"
    match = re.search(r"^(.+)-" + hex_pattern + r"$", entity_id)
    if match:
        slug = match.group(1)
        res = f'"{slug.replace("-", " ").strip()}"'
        return f"{prefix.rstrip(':')} {res}" if prefix else res

    clean_id = entity_id.replace("-", "")
    if len(clean_id) == UUID_HEX_LENGTH:
        res = f"{clean_id[:ID_DISPLAY_LENGTH]}..."
        return f"{prefix.rstrip(':')} {res}" if prefix else res

    return f"{prefix.rstrip(':')} {entity_id}" if prefix else entity_id


def _extract_id_from_path(path: str, keyword: str) -> str:
    """Extract page/database ID from raw path after the given keyword."""
    parts = [p for p in path.split("/") if p]
    try:
        idx = parts.index(keyword)
        if idx + 1 < len(parts):
            return parts[idx + 1]
    except ValueError:
        pass
    return ""


def _extract_inline_query(cmd_args: list[str]) -> str:
    """Helper to extract inline query options from arguments."""
    for arg in cmd_args:
        if arg.startswith("query=="):
            return arg.split("==", 1)[1].strip("'\"")
        if arg.startswith("query="):
            return arg.split("=", 1)[1].strip("'\"")
        if arg.startswith("query:="):
            val = arg.split(":=", 1)[1].strip("'\"")
            try:
                return str(json.loads(val))
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                return val
    return ""


def _extract_search_query(cmd_args: list[str]) -> str:
    """Extract search query from CLI arguments or API payload."""
    result = _search_query_from_subcmd(cmd_args)
    if result:
        return result
    result = _search_query_from_data_flag(cmd_args)
    if result:
        return result
    return _extract_inline_query(cmd_args)


def _search_query_from_subcmd(cmd_args: list[str]) -> str:
    """Try extracting the query from positional args after 'search'."""
    try:
        subcmd = next((a for a in cmd_args if not a.startswith("-")), None)
        if subcmd != "search":
            return ""
        idx = cmd_args.index("search")
        query_args = [a for a in cmd_args[idx + 1 :] if not a.startswith("-")]
        return query_args[0] if query_args else ""
    except ValueError:
        return ""


def _search_query_from_data_flag(cmd_args: list[str]) -> str:
    """Try extracting the query from a -d/--data JSON payload."""
    for flag in ("-d", "--data"):
        if flag not in cmd_args:
            continue
        try:
            idx = cmd_args.index(flag)
            if idx + 1 >= len(cmd_args):
                continue
            data = json.loads(cmd_args[idx + 1])
            if isinstance(data, dict) and "query" in data:
                return str(data["query"])
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass
    return ""


def _format_api_path(path: str) -> str:
    """Format and truncate UUIDs in raw API paths."""
    match = UUID_PATTERN.search(path)
    if match:
        uuid_str = match.group(0)
        formatted = _format_id(uuid_str)
        return path.replace(uuid_str, formatted)
    return path


def _parse_pages_create(cmd_args: list[str]) -> ToolDisplayPayload:
    parent = ""
    try:
        if "--parent" in cmd_args:
            idx = cmd_args.index("--parent")
            if idx + 1 < len(cmd_args):
                parent = _format_id(cmd_args[idx + 1])
    except (ValueError, IndexError):
        pass

    content = ""
    try:
        if "--content" in cmd_args:
            idx = cmd_args.index("--content")
            if idx + 1 < len(cmd_args):
                content = cmd_args[idx + 1]
    except (ValueError, IndexError):
        pass

    title = ""
    if content:
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                break

    display_title = (
        f'"{title[:TEXT_TRUNCATE_LENGTH]}..."'
        if len(title) > TEXT_TRUNCATE_LENGTH
        else (f'"{title}"' if title else "")
    )
    suffix = f" {display_title}" if display_title else ""
    if parent:
        suffix = f"{suffix} under {parent}"

    return ToolDisplayPayload(
        present=_make_present_label(f"Creating Notion page{suffix}"),
        compact=f"Created Notion page{suffix}",
        icon="📝",
    )


def _parse_pages_update_append(subcmd: str, page_id: str) -> ToolDisplayPayload:
    suffix = f" {_format_id(page_id)}" if page_id else ""
    verb_pres = "Updating" if subcmd == "update" else "Appending to"
    verb_comp = "Updated" if subcmd == "update" else "Appended"
    return ToolDisplayPayload(
        present=_make_present_label(f"{verb_pres} Notion page{suffix}"),
        compact=f"{verb_comp} Notion page{suffix}",
        icon="✏️" if subcmd == "update" else "📝",
    )


def _parse_pages_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    if len(cmd_args) < MIN_ARGS_FOR_SUBCMD or cmd_args[0] != "pages":
        return None

    subcmd = cmd_args[1]
    if subcmd in ("get", "trash"):
        page_id = cmd_args[MIN_ARGS_FOR_SUBCMD] if len(cmd_args) > MIN_ARGS_FOR_SUBCMD else ""
        suffix = f" {_format_id(page_id)}" if page_id else ""
        verb_pres = "Reading" if subcmd == "get" else "Trashing"
        verb_comp = "Read" if subcmd == "get" else "Trashed"
        return ToolDisplayPayload(
            present=_make_present_label(f"{verb_pres} Notion page{suffix}"),
            compact=f"{verb_comp} Notion page{suffix}",
            icon="📖" if subcmd == "get" else "🗑️",
        )
    if subcmd == "list":
        return ToolDisplayPayload(
            present="Listing Notion pages...", compact="Listed Notion pages", icon="📖"
        )
    if subcmd == "create":
        return _parse_pages_create(cmd_args)
    if subcmd in ("update", "append"):
        page_id = cmd_args[MIN_ARGS_FOR_SUBCMD] if len(cmd_args) > MIN_ARGS_FOR_SUBCMD else ""
        return _parse_pages_update_append(subcmd, page_id)
    return None


def _parse_databases_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    if len(cmd_args) < MIN_ARGS_FOR_SUBCMD or cmd_args[0] != "databases":
        return None

    subcmd = cmd_args[1]
    if subcmd == "query":
        db_id = cmd_args[MIN_ARGS_FOR_SUBCMD] if len(cmd_args) > MIN_ARGS_FOR_SUBCMD else ""
        suffix = f" {_format_id(db_id)}" if db_id else ""
        return ToolDisplayPayload(
            present=_make_present_label(f"Querying Notion database{suffix}"),
            compact=f"Queried Notion database{suffix}",
            icon="🔍",
        )
    if subcmd == "list":
        return ToolDisplayPayload(
            present="Listing Notion databases...", compact="Listed Notion databases", icon="🔍"
        )
    return None


def _parse_files_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    if len(cmd_args) < MIN_ARGS_FOR_SUBCMD or cmd_args[0] != "files":
        return None

    subcmd = cmd_args[1]
    if subcmd == "list":
        return ToolDisplayPayload(
            present="Listing Notion file uploads...",
            compact="Listed Notion file uploads",
            icon="📁",
        )
    if subcmd == "get":
        upload_id = cmd_args[MIN_ARGS_FOR_SUBCMD] if len(cmd_args) > MIN_ARGS_FOR_SUBCMD else ""
        suffix = f" {_format_id(upload_id)}" if upload_id else ""
        return ToolDisplayPayload(
            present=_make_present_label(f"Retrieving Notion file upload{suffix}"),
            compact=f"Retrieved Notion file upload{suffix}",
            icon="📁",
        )
    if subcmd == "create":
        filename = _extract_file_create_name(cmd_args)
        suffix = f' "{filename}"' if filename else ""
        return ToolDisplayPayload(
            present=_make_present_label(f"Creating Notion file upload{suffix}"),
            compact=f"Created Notion file upload{suffix}",
            icon="📤",
        )
    return None


def _extract_file_create_name(cmd_args: list[str]) -> str:
    """Extract filename or URL from a files-create command."""
    for flag in ("--filename", "--external-url"):
        name = _flag_value(cmd_args, flag)
        if not name:
            continue
        name = name.strip("'\"")
        if flag == "--external-url" and len(name) > TEXT_TRUNCATE_LENGTH:
            return f"{name[:TEXT_TRUNCATE_LENGTH]}..."
        return name
    return ""


def _flag_value(cmd_args: list[str], flag: str) -> str | None:
    """Return the value following *flag* in *cmd_args*, or ``None``."""
    try:
        idx = cmd_args.index(flag)
        if idx + 1 < len(cmd_args):
            return cmd_args[idx + 1]
    except (ValueError, IndexError):
        pass
    return None


def _parse_datasources_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    if len(cmd_args) < MIN_ARGS_FOR_SUBCMD or cmd_args[0] != "datasources":
        return None

    subcmd = cmd_args[1]
    if subcmd == "query":
        ds_id = cmd_args[MIN_ARGS_FOR_SUBCMD] if len(cmd_args) > MIN_ARGS_FOR_SUBCMD else ""
        suffix = f" {_format_id(ds_id)}" if ds_id else ""
        return ToolDisplayPayload(
            present=_make_present_label(f"Querying Notion data source{suffix}"),
            compact=f"Queried Notion data source{suffix}",
            icon="🔍",
        )
    if subcmd == "resolve":
        db_id = cmd_args[MIN_ARGS_FOR_SUBCMD] if len(cmd_args) > MIN_ARGS_FOR_SUBCMD else ""
        suffix = f" {_format_id(db_id)}" if db_id else ""
        return ToolDisplayPayload(
            present=_make_present_label(f"Resolving Notion database{suffix} to data source IDs"),
            compact=f"Resolved Notion database{suffix} to data source IDs",
            icon="🔍",
        )
    return None


def _parse_api_databases(cmd_args: list[str], path: str) -> ToolDisplayPayload:
    is_query = "query" in path.lower() or any("query" in arg.lower() for arg in cmd_args)
    db_id = _extract_id_from_path(path, "databases")
    suffix = f" {_format_id(db_id)}" if db_id else ""

    if is_query:
        return ToolDisplayPayload(
            present=_make_present_label(f"Querying Notion database{suffix}"),
            compact=f"Queried Notion database{suffix}",
            icon="🔍",
        )
    return ToolDisplayPayload(
        present=_make_present_label(f"Reading Notion database schema{suffix}"),
        compact=f"Read Notion database schema{suffix}",
        icon="🗂️",
    )


def _parse_api_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    if len(cmd_args) < MIN_ARGS_FOR_SUBCMD or cmd_args[0] != "api":
        return None

    if cmd_args[1] == "ls":
        return ToolDisplayPayload(
            present="Listing Notion API endpoints...",
            compact="Listed Notion API endpoints",
            icon="📋",
        )

    path = cmd_args[1].split("?")[0]
    display_path = _format_api_path(path)

    if "search" in path:
        query = _extract_search_query(cmd_args)
        display_query = (
            f' for "{query[:TEXT_TRUNCATE_LENGTH]}..."'
            if len(query) > TEXT_TRUNCATE_LENGTH
            else (f' for "{query}"' if query else "")
        )
        return ToolDisplayPayload(
            present=_make_present_label(f"Searching Notion{display_query}"),
            compact=f"Searched Notion{display_query}",
            icon="🔍",
        )
    if "databases" in path:
        return _parse_api_databases(cmd_args, path)

    if "pages" in path:
        is_write = any(val in "".join(cmd_args).lower() for val in ["post", "patch", "delete"])
        page_id = _extract_id_from_path(path, "pages")
        suffix = f" {_format_id(page_id)}" if page_id else f" ({display_path})"
        return ToolDisplayPayload(
            present=_make_present_label(
                f"{'Updating' if is_write else 'Reading'} Notion page{suffix}"
            ),
            compact=f"{'Updated' if is_write else 'Read'} Notion page{suffix}",
            icon="📝" if is_write else "📖",
        )
    return ToolDisplayPayload(
        present=_make_present_label(f"Calling Notion API ({display_path})"),
        compact=f"Called Notion API ({display_path})",
        icon="📓",
    )


def _parse_help_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    if not any(h in cmd_args for h in ("--help", "-h")):
        return None

    flags = {"--help", "-h", "--json", "--verbose", "-v", "--no-color"}
    subcommands = [a for a in cmd_args if a not in flags and not a.startswith("-")]
    if subcommands:
        target = " ".join(subcommands)
        return ToolDisplayPayload(
            present=f"Displaying help for Notion {target}...",
            compact=f"Displayed help for Notion {target}",
            icon="ℹ️",  # noqa: RUF001
        )
    return ToolDisplayPayload(
        present="Displaying Notion help...",
        compact="Displayed Notion help",
        icon="ℹ️",  # noqa: RUF001
    )


def _parse_doctor_command(cmd_args: list[str]) -> ToolDisplayPayload | None:
    if not cmd_args or cmd_args[0] != "doctor":
        return None
    return ToolDisplayPayload(
        present="Running Notion diagnostics...", compact="Ran Notion diagnostics", icon="🩺"
    )


def _format_ntn_display(arguments: dict[str, Any]) -> ToolDisplayPayload:
    raw_args = arguments.get("args")
    fallback = ToolDisplayPayload(
        present="Running Notion command...", compact="Notion command", icon="📓"
    )

    cmd_args = []
    if isinstance(raw_args, str):
        cmd_args = [raw_args.strip()]
    elif isinstance(raw_args, list):
        cmd_args = [str(a).strip() for a in raw_args]

    if not cmd_args:
        return fallback

    global_flags = {"--json", "--verbose", "-v", "--no-color"}
    filtered_args = [a for a in cmd_args if a not in global_flags]

    if not filtered_args:
        help_payload = _parse_help_command(cmd_args)
        return help_payload if help_payload else fallback

    payload = (
        _parse_help_command(cmd_args)
        or _parse_pages_command(filtered_args)
        or _parse_databases_command(filtered_args)
        or _parse_files_command(filtered_args)
        or _parse_datasources_command(filtered_args)
        or _parse_api_command(filtered_args)
        or _parse_doctor_command(filtered_args)
    )

    if not payload and "search" in filtered_args:
        query = _extract_search_query(cmd_args)
        display_query = (
            f' for "{query[:TEXT_TRUNCATE_LENGTH]}..."'
            if len(query) > TEXT_TRUNCATE_LENGTH
            else (f' for "{query}"' if query else "")
        )
        payload = ToolDisplayPayload(
            present=_make_present_label(f"Searching Notion{display_query}"),
            compact=f"Searched Notion{display_query}",
            icon="🔍",
        )

    if payload is None:
        joined = " ".join(cmd_args)
        display_cmd = (
            f" '{joined[:TEXT_TRUNCATE_LENGTH]}...'"
            if len(joined) > TEXT_TRUNCATE_LENGTH
            else f" '{joined}'"
        )
        payload = ToolDisplayPayload(
            present=_make_present_label(f"Running Notion command{display_cmd}"),
            compact=f"Ran Notion command{display_cmd}",
            icon="📓",
        )

    if bool(arguments.get("stdin")) and not payload["present"].endswith(" (piped stdin)..."):
        pres = payload["present"]
        if pres.endswith("..."):
            pres = pres[:-3]
        payload["present"] = _make_present_label(f"{pres} (piped stdin)")
        payload["compact"] = f"{payload['compact']} (piped stdin)"

    return payload
