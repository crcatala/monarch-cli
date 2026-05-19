"""Raw GraphQL API command for Monarch CLI."""

from __future__ import annotations

import inspect
import json
import sys
import webbrowser
from pathlib import Path
from typing import Annotated, Any

import typer
from graphql import GraphQLError, parse
from monarchmoney import MonarchMoney  # type: ignore[import-untyped]

from ..core.adapter import get_authenticated_client
from ..core.async_utils import run_api_call
from ..core.error_handler import handle_errors
from ..core.exceptions import ValidationError
from ..output import OutputFormat, output
from ..output.progress import spinner

API_DOCS_URL = "https://312-dev.github.io/monarchmoney/docs/api/overview"
MONARCHMONEYCOMMUNITY_REPO_URL = "https://github.com/bradleyseanf/monarchmoneycommunity"


def _load_query(query: str | None, query_file: Path | None) -> str:
    """Load a GraphQL query document from option text, stdin, or file."""
    if query and query_file:
        raise ValidationError("Use only one query source: --query or --query-file.")
    if query == "-":
        return sys.stdin.read()
    if query:
        return query
    if query_file:
        return query_file.read_text()
    raise ValidationError("Provide --query or --query-file.")


def _split_field(value: str, option_name: str) -> tuple[str, str]:
    """Split a key=value option."""
    key, separator, raw_value = value.partition("=")
    if not separator or not key:
        raise ValidationError(f"{option_name} values must be key=value.", field=option_name)
    return key, raw_value


def _coerce_field_value(value: str) -> Any:
    """Coerce a gh-style -F field value to JSON when possible."""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _parse_variables(
    *,
    fields: list[str] | None,
    raw_fields: list[str] | None,
    variables_json: str | None,
) -> dict[str, Any]:
    """Parse variable sources into a single GraphQL variables dictionary."""
    variables: dict[str, Any] = {}

    if variables_json:
        try:
            parsed = json.loads(variables_json)
        except json.JSONDecodeError as e:
            raise ValidationError(
                "Invalid --variables-json. Expected a JSON object.",
                field="variables-json",
                details={"original_error": str(e)},
            ) from e
        if not isinstance(parsed, dict):
            raise ValidationError("--variables-json must be a JSON object.", field="variables-json")
        variables.update(parsed)

    for raw_field in raw_fields or []:
        key, value = _split_field(raw_field, "--raw-field")
        variables[key] = value

    for field in fields or []:
        key, value = _split_field(field, "--field")
        variables[key] = _coerce_field_value(value)

    return variables


def _public_method_docs() -> list[str]:
    """Build Markdown bullets for public upstream wrapper methods."""
    method_lines: list[str] = []
    for name in sorted(dir(MonarchMoney)):
        if name.startswith("_"):
            continue
        method = getattr(MonarchMoney, name)
        if not callable(method):
            continue

        try:
            signature = str(inspect.signature(method))
        except (TypeError, ValueError):
            signature = "(...)"

        first_doc_line = ""
        if method.__doc__:
            first_doc_line = method.__doc__.strip().splitlines()[0].strip()

        description = f" - {first_doc_line}" if first_doc_line else ""
        method_lines.append(f"- `{name}{signature}`{description}")

    return method_lines


def _build_agent_docs() -> str:
    """Build compact Markdown docs suitable for agent context."""
    method_lines = "\n".join(_public_method_docs())
    return f"""# Monarch API Agent Handoff

## Sources

- Community API docs: {API_DOCS_URL}
- Python wrapper repo: {MONARCHMONEYCOMMUNITY_REPO_URL}
- Package import: `from monarchmoney import MonarchMoney`

## GraphQL Notes

- Monarch uses GraphQL behind the web app.
- Introspection is disabled for non-admin users.
- Treat community docs and wrapper methods as the practical source of truth.
- Verify mutating operations carefully against a non-critical record first.

## CLI Escape Hatch

```bash
monarch api docs
monarch api GetAccounts --query 'query GetAccounts {{ accounts {{ id displayName }} }}'
monarch api GetTransactions --query-file query.graphql -F limit=100
monarch api GetTransactions --query-file query.graphql --variables-json '{{"limit": 100}}'
```

Variables:

- `-F key=value` parses JSON scalars and objects, e.g. `limit=100`, `active=true`.
- `-f key=value` sends a raw string.
- `--variables-json '{{"key": "value"}}'` merges a JSON object.

## monarchmoneycommunity Methods

{method_lines}
"""


def _write_agent_docs(output_path: Path) -> None:
    """Write agent-friendly docs to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_build_agent_docs())


def _is_docs_request(
    *,
    operation: str,
    query: str | None,
    query_file: Path | None,
    fields: list[str] | None,
    raw_fields: list[str] | None,
    variables_json: str | None,
) -> bool:
    """Check whether the api command should open documentation."""
    return (
        operation == "docs"
        and query is None
        and query_file is None
        and not fields
        and not raw_fields
        and variables_json is None
    )


@handle_errors
def api_cmd(
    operation: Annotated[
        str,
        typer.Argument(help="GraphQL operation name to execute."),
    ],
    query: Annotated[
        str | None,
        typer.Option(
            "--query",
            help="GraphQL query document. Use '-' to read from stdin.",
        ),
    ] = None,
    query_file: Annotated[
        Path | None,
        typer.Option(
            "--query-file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Read GraphQL query document from a file.",
        ),
    ] = None,
    fields: Annotated[
        list[str] | None,
        typer.Option(
            "-F",
            "--field",
            help="Add a GraphQL variable as key=value, parsing JSON scalars and objects.",
        ),
    ] = None,
    raw_fields: Annotated[
        list[str] | None,
        typer.Option(
            "-f",
            "--raw-field",
            help="Add a string GraphQL variable as key=value.",
        ),
    ] = None,
    variables_json: Annotated[
        str | None,
        typer.Option(
            "--variables-json",
            help="JSON object of GraphQL variables.",
        ),
    ] = None,
    docs_output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="For 'docs': write an agent-friendly Markdown file instead of opening a browser.",
        ),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option(
            "--format",
            help="Output format (plain, json, table, csv, compact).",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON (shortcut for --format json).",
        ),
    ] = False,
) -> None:
    """Call Monarch Money's raw GraphQL API.

    Examples:
        monarch api docs
        monarch api docs --output monarch-api-docs.md
        monarch api GetAccounts --query 'query GetAccounts { accounts { id } }'
        monarch api GetTransactions --query-file query.graphql -F limit=100
        monarch api GetTransactions --query-file query.graphql --variables-json '{"limit": 100}'
    """
    output_format = OutputFormat.JSON if json_output else format

    if _is_docs_request(
        operation=operation,
        query=query,
        query_file=query_file,
        fields=fields,
        raw_fields=raw_fields,
        variables_json=variables_json,
    ):
        opened = False
        if docs_output is not None:
            _write_agent_docs(docs_output)
        else:
            opened = webbrowser.open(API_DOCS_URL)

        result: dict[str, Any] = {"opened": opened, "url": API_DOCS_URL}
        if docs_output is not None:
            result["output"] = str(docs_output)
        output(result, output_format)
        return

    if docs_output is not None:
        raise ValidationError("--output is only supported with 'monarch api docs'.", field="output")

    query_text = _load_query(query, query_file)
    variables = _parse_variables(
        fields=fields,
        raw_fields=raw_fields,
        variables_json=variables_json,
    )

    try:
        graphql_query = parse(query_text)
    except GraphQLError as e:
        raise ValidationError(
            "Invalid GraphQL query.",
            field="query",
            details={"original_error": str(e)},
        ) from e

    with spinner("Calling Monarch API..."):
        client = get_authenticated_client()
        data = run_api_call(lambda: client.gql_call(operation, graphql_query, variables))

    output(data, output_format)
