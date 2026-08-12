"""Tests for raw API command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from graphql.language import DocumentNode
from typer.testing import CliRunner

from monarch_cli.main import app

runner = CliRunner()


class TestApiCommand:
    """Tests for 'monarch api'."""

    def test_docs_opens_api_documentation(self) -> None:
        """Docs command opens the community API documentation URL."""
        with patch("monarch_cli.commands.api.webbrowser.open", return_value=True) as mock_open:
            result = runner.invoke(app, ["api", "docs", "--json"])

        assert result.exit_code == 0
        mock_open.assert_called_once_with(
            "https://312-dev.github.io/monarchmoney/docs/api/overview"
        )
        assert json.loads(result.stdout) == {
            "opened": True,
            "url": "https://312-dev.github.io/monarchmoney/docs/api/overview",
        }

    def test_docs_writes_agent_friendly_file(self, tmp_path: Path) -> None:
        """Docs command can write a local agent-friendly handoff file."""
        output_path = tmp_path / "monarch-api-docs.md"

        with patch("monarch_cli.commands.api.webbrowser.open") as mock_open:
            result = runner.invoke(
                app,
                ["api", "docs", "--output", str(output_path), "--json"],
            )

        assert result.exit_code == 0
        mock_open.assert_not_called()
        result_data = json.loads(result.stdout)
        assert result_data == {
            "opened": False,
            "url": "https://312-dev.github.io/monarchmoney/docs/api/overview",
            "output": str(output_path),
        }

        docs = output_path.read_text()
        assert "# Monarch API Agent Handoff" in docs
        assert "Introspection is disabled for non-admin users." in docs
        assert "## CLI Escape Hatch" in docs
        assert "## monarchmoneycommunity Methods" in docs
        assert "get_accounts" in docs

    def test_executes_graphql_query_with_variables(self) -> None:
        """API command executes a GraphQL operation with parsed variables."""
        calls: dict[str, Any] = {}
        mock_client = MagicMock()

        async def gql_call(
            operation: str,
            graphql_query: DocumentNode,
            variables: dict[str, Any],
        ) -> dict[str, Any]:
            calls["operation"] = operation
            calls["graphql_query"] = graphql_query
            calls["variables"] = variables
            return {"accounts": [{"id": "acc_123"}]}

        mock_client.gql_call = gql_call

        with (
            patch("monarch_cli.commands.api.get_authenticated_client", return_value=mock_client),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app,
                [
                    "api",
                    "GetAccounts",
                    "--query",
                    "query GetAccounts($limit: Int!, $includeHidden: Boolean!) { accounts { id } }",
                    "-F",
                    "limit=10",
                    "-F",
                    "includeHidden=true",
                    "-f",
                    "search=coffee",
                ],
            )

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"accounts": [{"id": "acc_123"}]}
        assert calls["operation"] == "GetAccounts"
        assert isinstance(calls["graphql_query"], DocumentNode)
        assert calls["variables"] == {
            "limit": 10,
            "includeHidden": True,
            "search": "coffee",
        }

    def test_reads_query_from_file(self, tmp_path: Path) -> None:
        """API command can read GraphQL query text from a file."""
        query_file = tmp_path / "query.graphql"
        query_file.write_text("query GetAccounts { accounts { id } }")
        mock_client = MagicMock()
        mock_client.gql_call.return_value = {"ok": True}

        async def gql_call(
            operation: str,
            _graphql_query: DocumentNode,
            variables: dict[str, Any],
        ) -> dict[str, Any]:
            return {"operation": operation, "variables": variables}

        mock_client.gql_call = gql_call

        with (
            patch("monarch_cli.commands.api.get_authenticated_client", return_value=mock_client),
            patch("monarch_cli.output.progress.is_interactive", return_value=False),
        ):
            result = runner.invoke(
                app,
                [
                    "api",
                    "GetAccounts",
                    "--query-file",
                    str(query_file),
                    "--variables-json",
                    '{"x": 1}',
                ],
            )

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"operation": "GetAccounts", "variables": {"x": 1}}

    def test_requires_query_source(self) -> None:
        """API command errors when no query source is provided."""
        result = runner.invoke(app, ["api", "GetAccounts"])

        assert result.exit_code == 2
        error = json.loads(result.stderr)
        assert error["code"] == "INVALID_INPUT"
        assert "Provide --query or --query-file" in error["message"]

    def test_rejects_invalid_field(self) -> None:
        """API command rejects field values that are not key=value."""
        result = runner.invoke(
            app,
            [
                "api",
                "GetAccounts",
                "--query",
                "query GetAccounts { accounts { id } }",
                "-F",
                "limit",
            ],
        )

        assert result.exit_code == 2
        error = json.loads(result.stderr)
        assert error["code"] == "INVALID_INPUT"
        assert "key=value" in error["message"]
