"""Tests for Notion CLI display formatting."""

from __future__ import annotations

from app.plugins.notion.display import _format_ntn_display


class TestFormatter:
    def test_formatter_pages_get(self) -> None:
        payload = _format_ntn_display(
            {"args": ["pages", "get", "3673c065-308b-4153-92a5-e21c625cfe74"]}
        )
        assert payload["icon"] == "📖"
        assert "Reading Notion page 3673c065..." in payload["present"]
        assert "Read Notion page 3673c065..." in payload["compact"]

    def test_formatter_pages_create_with_markdown_title(self) -> None:
        payload = _format_ntn_display(
            {
                "args": [
                    "pages",
                    "create",
                    "--parent",
                    "database:3673c065-308b-4153-92a5-e21c625cfe74",
                    "--content",
                    "# Romanian Verbs\nSome verbs here",
                ]
            }
        )
        assert payload["icon"] == "📝"
        assert (
            'Creating Notion page "Romanian Verbs" under database 3673c065...' in payload["present"]
        )
        assert (
            'Created Notion page "Romanian Verbs" under database 3673c065...' in payload["compact"]
        )

    def test_formatter_api_uuid_truncation(self) -> None:
        payload = _format_ntn_display(
            {"args": ["api", "v1/pages/3673c065-308b-4153-92a5-e21c625cfe74"]}
        )
        assert payload["icon"] == "📖"
        assert "Reading Notion page 3673c065..." in payload["present"]

    def test_formatter_help_commands(self) -> None:
        payload = _format_ntn_display({"args": ["pages", "--help"]})
        assert payload["icon"] == "ℹ️"  # noqa: RUF001
        assert "Displaying help for Notion pages" in payload["present"]

        payload_general = _format_ntn_display({"args": ["--help"]})
        assert payload_general["icon"] == "ℹ️"  # noqa: RUF001
        assert "Displaying Notion help..." in payload_general["present"]

    def test_formatter_global_flags_filtering(self) -> None:
        payload = _format_ntn_display({"args": ["--json", "--verbose", "pages", "get", "3673c065"]})
        assert payload["icon"] == "📖"
        assert "Reading Notion page 3673c065..." in payload["present"]

    def test_formatter_piped_stdin(self) -> None:
        payload = _format_ntn_display(
            {
                "args": ["pages", "update", "3673c065"],
                "stdin": "some content",
            }
        )
        assert "Updating Notion page 3673c065 (piped stdin)" in payload["present"]
        assert "Updated Notion page 3673c065 (piped stdin)" in payload["compact"]

    def test_formatter_doctor(self) -> None:
        payload = _format_ntn_display({"args": ["doctor"]})
        assert payload["icon"] == "🩺"
        assert "Running Notion diagnostics" in payload["present"]
        assert "Ran Notion diagnostics" in payload["compact"]

    def test_formatter_pages_list(self) -> None:
        payload = _format_ntn_display({"args": ["pages", "list"]})
        assert payload["icon"] == "📖"
        assert "Listing Notion pages" in payload["present"]
        assert "Listed Notion pages" in payload["compact"]

    def test_formatter_api_ls(self) -> None:
        payload = _format_ntn_display({"args": ["api", "ls"]})
        assert payload["icon"] == "📋"
        assert "Listing Notion API endpoints" in payload["present"]
        assert "Listed Notion API endpoints" in payload["compact"]

    def test_formatter_api_database_query(self) -> None:
        payload = _format_ntn_display(
            {"args": ["api", "v1/databases/3673c065-308b-4153-92a5-e21c625cfe74/query"]}
        )
        assert payload["icon"] == "🔍"
        assert "Querying Notion database 3673c065..." in payload["present"]
        assert "Queried Notion database 3673c065..." in payload["compact"]

    def test_formatter_api_database_schema(self) -> None:
        payload = _format_ntn_display(
            {"args": ["api", "v1/databases/3673c065-308b-4153-92a5-e21c625cfe74"]}
        )
        assert payload["icon"] == "🗂️"
        assert "Reading Notion database schema 3673c065..." in payload["present"]
        assert "Read Notion database schema 3673c065..." in payload["compact"]

    def test_formatter_slugified_id_resolution(self) -> None:
        payload = _format_ntn_display(
            {"args": ["pages", "get", "My-Page-Title-3673c065308b415392a5e21c625cfe74"]}
        )
        assert payload["icon"] == "📖"
        assert 'Reading Notion page "My Page Title"' in payload["present"]
        assert 'Read Notion page "My Page Title"' in payload["compact"]

        payload_db = _format_ntn_display(
            {"args": ["databases", "query", "My-Db-Title-3673c065-308b-4153-92a5-e21c625cfe74"]}
        )
        assert payload_db["icon"] == "🔍"
        assert 'Querying Notion database "My Db Title"' in payload_db["present"]
        assert 'Queried Notion database "My Db Title"' in payload_db["compact"]

    def test_formatter_nested_help_commands(self) -> None:
        payload = _format_ntn_display({"args": ["pages", "create", "--help"]})
        assert payload["icon"] == "ℹ️"  # noqa: RUF001
        assert "Displaying help for Notion pages create" in payload["present"]
        assert "Displayed help for Notion pages create" in payload["compact"]

    def test_formatter_search_command_with_query(self) -> None:
        payload = _format_ntn_display({"args": ["search", "my query string"]})
        assert payload["icon"] == "🔍"
        assert 'Searching Notion for "my query string"' in payload["present"]
        assert 'Searched Notion for "my query string"' in payload["compact"]

        payload_long = _format_ntn_display(
            {"args": ["search", "this is a very long search query string"]}
        )
        assert 'Searching Notion for "this is a very long ..."' in payload_long["present"]

    def test_formatter_api_search_with_query(self) -> None:
        payload = _format_ntn_display(
            {"args": ["api", "v1/search", "-d", '{"query": "api query string"}']}
        )
        assert payload["icon"] == "🔍"
        assert 'Searching Notion for "api query string"' in payload["present"]
        assert 'Searched Notion for "api query string"' in payload["compact"]

    def test_formatter_api_search_rejects_http_methods(self) -> None:
        payload = _format_ntn_display({"args": ["api", "v1/search", "-X", "POST"]})
        assert payload["icon"] == "🔍"
        assert "Searching Notion" in payload["present"]
        assert 'for "POST"' not in payload["present"]

    def test_formatter_files_command(self) -> None:
        payload_list = _format_ntn_display({"args": ["files", "list"]})
        assert payload_list["icon"] == "📁"
        assert "Listing Notion file uploads" in payload_list["present"]
        assert "Listed Notion file uploads" in payload_list["compact"]

        payload_get = _format_ntn_display({"args": ["files", "get", "3673c065"]})
        assert payload_get["icon"] == "📁"
        assert "Retrieving Notion file upload 3673c065" in payload_get["present"]
        assert "Retrieved Notion file upload 3673c065" in payload_get["compact"]

        payload_create = _format_ntn_display(
            {"args": ["files", "create", "--filename", "photo.png"]}
        )
        assert payload_create["icon"] == "📤"
        assert 'Creating Notion file upload "photo.png"' in payload_create["present"]
        assert 'Created Notion file upload "photo.png"' in payload_create["compact"]

    def test_formatter_datasources_command(self) -> None:
        payload_query = _format_ntn_display({"args": ["datasources", "query", "3673c065"]})
        assert payload_query["icon"] == "🔍"
        assert "Querying Notion data source 3673c065" in payload_query["present"]
        assert "Queried Notion data source 3673c065" in payload_query["compact"]

        payload_resolve = _format_ntn_display({"args": ["datasources", "resolve", "3673c065"]})
        assert payload_resolve["icon"] == "🔍"
        assert "Resolving Notion database 3673c065 to data source IDs" in payload_resolve["present"]
        assert "Resolved Notion database 3673c065 to data source IDs" in payload_resolve["compact"]
