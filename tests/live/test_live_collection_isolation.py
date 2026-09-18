"""Collection-disjointness proof for the supported live-test node sets (mc-584r).

These tests prove, without any API call or subprocess, that the three
supported pytest node sets never overlap:

- normal suite: ``-m "not live"`` (``make test``),
- read-only live suite: ``-m "live and not live_mutation"`` (``make test-live``),
- gated mutation suite: ``-m live_mutation`` (``make test-live-mutation``).

They evaluate the exact marker expressions used by the Makefile targets
against representative node keyword sets, and statically verify the real
suite modules' ``pytestmark`` declarations so a future edit cannot silently
leak mutation nodes into a normal or read-only collection.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

import pytest

from tests.live import live_cli, test_live_api, test_live_mutation_api

TESTS_LIVE_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_LIVE_DIR.parents[1]

NORMAL_EXPRESSION = "not live"
READ_ONLY_EXPRESSION = "live and not live_mutation"
MUTATION_EXPRESSION = "live_mutation"


class _Node:
    """Minimal stand-in for a collected pytest item."""

    def __init__(self, nodeid: str, keywords: set[str]) -> None:
        self.nodeid = nodeid
        self.keywords = keywords

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"_Node({self.nodeid!r}, {sorted(self.keywords)})"


def _marker_names(pytestmark: list[Any]) -> set[str]:
    return {mark.name for mark in pytestmark}


def _eval(node: ast.expr, keywords: set[str]) -> bool:
    """Evaluate the supported marker-expression grammar (and/or/not/names)."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return all(_eval(value, keywords) for value in node.values)
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(_eval(value, keywords) for value in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval(node.operand, keywords)
    if isinstance(node, ast.Name):
        return node.id in keywords
    raise AssertionError(f"Unsupported marker expression element: {ast.dump(node)}")


def _select(expression: str, items: list[_Node]) -> list[_Node]:
    """Apply a Makefile-style ``-m`` expression to the representative nodes."""
    tree = ast.parse(expression, mode="eval")
    return [item for item in items if _eval(tree.body, item.keywords)]


def _representative_nodes() -> list[_Node]:
    """Node shapes covering every keyword combination the suites can produce."""
    return [
        _Node("tests/test_unit.py", set()),
        _Node("tests/live/test_live_api.py::test_ping", {"live"}),
        _Node(
            "tests/live/test_live_mutation_api.py::test_transaction_notes_round_trip",
            {"live", "live_mutation"},
        ),
    ]


# --- Supported target expressions are mutually exclusive --------------------


def test_normal_suite_excludes_every_live_node() -> None:
    selected = _select(NORMAL_EXPRESSION, _representative_nodes())
    assert [item.nodeid for item in selected] == ["tests/test_unit.py"]


def test_read_only_live_suite_excludes_mutation_nodes() -> None:
    selected = _select(READ_ONLY_EXPRESSION, _representative_nodes())
    assert [item.nodeid for item in selected] == ["tests/live/test_live_api.py::test_ping"]
    assert all("live_mutation" not in item.keywords for item in selected)


def test_live_mutation_suite_selects_only_mutation_nodes() -> None:
    selected = _select(MUTATION_EXPRESSION, _representative_nodes())
    assert len(selected) == 1
    assert selected[0].keywords == {"live", "live_mutation"}


def test_supported_node_sets_are_pairwise_disjoint() -> None:
    items = _representative_nodes()
    normal = {item.nodeid for item in _select(NORMAL_EXPRESSION, items)}
    read_only = {item.nodeid for item in _select(READ_ONLY_EXPRESSION, items)}
    mutation = {item.nodeid for item in _select(MUTATION_EXPRESSION, items)}
    assert not normal & read_only
    assert not normal & mutation
    assert not read_only & mutation
    assert normal | read_only | mutation == {item.nodeid for item in items}


# --- The real suite modules carry the right markers -------------------------


def test_read_only_live_modules_carry_live_but_never_live_mutation() -> None:
    markers = _marker_names(test_live_api.pytestmark)
    assert "live" in markers
    assert "live_mutation" not in markers


def test_mutation_module_carries_both_live_and_live_mutation() -> None:
    markers = _marker_names(test_live_mutation_api.pytestmark)
    assert {"live", "live_mutation"} <= markers


def test_shared_runner_module_defines_mutation_opt_in_independently() -> None:
    # The read-only opt-in alone must never enable mutation collection or
    # execution: the gates read the dedicated variable, not MONARCH_LIVE_TESTS.
    from tests.live import live_mutation_gates

    assert (os.environ.get("MONARCH_LIVE_TESTS") == "1") == live_cli.LIVE_ENABLED
    assert live_mutation_gates.MUTATION_OPT_IN_ENV == "MONARCH_LIVE_MUTATION_TESTS"
    assert live_mutation_gates.HOUSEHOLD_ID_ENV == "MONARCH_LIVE_MUTATION_HOUSEHOLD_ID"


def test_read_only_opt_in_alone_enables_neither_gate(monkeypatch: Any) -> None:
    # MONARCH_LIVE_TESTS=1 by itself must enable neither mutation collection
    # nor mutation execution: both gates read the dedicated opt-in only.
    monkeypatch.setenv("MONARCH_LIVE_TESTS", "1")
    monkeypatch.delenv("MONARCH_LIVE_MUTATION_TESTS", raising=False)
    from tests.live import live_mutation_gates

    assert not live_mutation_gates.mutation_opt_in_enabled()
    with pytest.raises(live_mutation_gates.LiveMutationPrerequisiteError):
        live_mutation_gates.enforce_runtime_prerequisites()


# --- The supported targets and guard are wired as documented ----------------


def test_makefile_targets_use_the_disjoint_expressions() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert 'pytest -m "not live"' in makefile
    assert '-m "live and not live_mutation"' in makefile
    assert "-m live_mutation" in makefile


def test_live_conftest_installs_collection_guard() -> None:
    conftest = (TESTS_LIVE_DIR / "conftest.py").read_text(encoding="utf-8")
    assert "pytest_collection_modifyitems" in conftest
    assert "deselect_live_mutation_unless_opted_in" in conftest
