"""Tests for the shared mutation/preview JSON emission path (mc-hu2c).

Mutation outcomes and dry-run previews always emit JSON on stdout regardless
of TTY state; ``--quiet`` and any explicit non-JSON format are rejected with a
structured input error instead of silently swallowing or re-rendering the
result.
"""

from __future__ import annotations

import json
import sys

import pytest
import typer

from monarch_cli.core.exceptions import ErrorCode, ValidationError
from monarch_cli.core.mutation_outcomes import (
    ambiguous_item,
    build_mutation_outcome,
    succeeded_item,
)
from monarch_cli.output import (
    OutputFormat,
    emit_mutation_outcome,
    set_default_format,
    set_quiet,
)


@pytest.fixture(autouse=True)
def _reset_output_state() -> None:
    """Restore the module-level output flags around each test."""
    set_quiet(False)
    set_default_format(None)
    yield
    set_quiet(False)
    set_default_format(None)


def _succeeded() -> dict:
    return build_mutation_outcome(
        "transactions tags replace",
        [succeeded_item("transaction", "txn_1", {"tag_ids": ["t1"]})],
    )


class TestEmitMutationOutcome:
    def test_emits_json_when_stdout_is_a_tty(self, capsys, monkeypatch) -> None:
        """A TTY must not re-render the machine-readable envelope."""
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

        emit_mutation_outcome(_succeeded())

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["schema_version"] == "mutation-outcome.v1"
        assert data["operation"] == "transactions.tags.replace"

    def test_emits_json_under_default_override_json(self, capsys) -> None:
        set_default_format(OutputFormat.JSON)

        emit_mutation_outcome(_succeeded())

        captured = capsys.readouterr()
        assert json.loads(captured.out)["status"] == "succeeded"

    def test_quiet_is_rejected_with_structured_input_error(self) -> None:
        set_quiet(True)

        with pytest.raises(ValidationError) as excinfo:
            emit_mutation_outcome(_succeeded())

        assert excinfo.value.code is ErrorCode.INVALID_INPUT
        assert excinfo.value.exit_code == 2
        assert excinfo.value.details["field"] == "quiet"

    @pytest.mark.parametrize(
        "fmt",
        [OutputFormat.PLAIN, OutputFormat.TABLE, OutputFormat.CSV, OutputFormat.COMPACT],
    )
    def test_non_json_explicit_format_is_rejected(self, fmt: OutputFormat) -> None:
        set_default_format(fmt)

        with pytest.raises(ValidationError) as excinfo:
            emit_mutation_outcome(_succeeded())

        assert excinfo.value.code is ErrorCode.INVALID_INPUT
        assert excinfo.value.details["field"] == "format"

    def test_ambiguous_outcome_exits_4(self) -> None:
        outcome = build_mutation_outcome(
            "transactions tags replace",
            [ambiguous_item("transaction", "txn_1", "unknown")],
        )

        with pytest.raises(typer.Exit) as excinfo:
            emit_mutation_outcome(outcome)

        assert excinfo.value.exit_code == 4

    def test_succeeded_outcome_does_not_exit(self, capsys) -> None:
        # Must return normally (no typer.Exit) for a clean success.
        emit_mutation_outcome(_succeeded())
        assert json.loads(capsys.readouterr().out)["status"] == "succeeded"
