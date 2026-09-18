"""Pytest collection guard for the gated live mutation suite (mc-584r).

Nodes marked ``live_mutation`` are deselected unless
``MONARCH_LIVE_MUTATION_TESTS=1`` is present. The supported ``make`` targets
also select explicit marker expressions; this guard is defense in depth so a
bare ``pytest`` invocation cannot collect mutation nodes either.
"""

from __future__ import annotations

from typing import Any

from tests.live.live_mutation_gates import deselect_live_mutation_unless_opted_in


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    deselected = deselect_live_mutation_unless_opted_in(items)
    if not deselected:
        return
    config.hook.pytest_deselected(items=deselected)
    deselected_ids = {id(item) for item in deselected}
    items[:] = [item for item in items if id(item) not in deselected_ids]
