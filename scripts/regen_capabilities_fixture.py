#!/usr/bin/env python3
"""Regenerate the canonical capabilities manifest fixture.

Run this only after an *intentional* capabilities manifest change (a new
command, option, effect, schema reference, and so on) and review the diff
before committing. The fixture pins manifest shape, ordering, and
byte-for-byte serialization.

The fixture deliberately stores a fixed placeholder CLI version (``0.0.0``)
so ordinary release version bumps do not invalidate it. This constant must
stay in sync with ``FIXTURE_CLI_VERSION`` in ``tests/test_capabilities.py``;
if they diverge, the canonical fixture test fails loudly.
"""

from __future__ import annotations

from pathlib import Path

from monarch_cli.core.capabilities import render_capabilities_manifest
from monarch_cli.main import app

FIXTURE_CLI_VERSION = "0.0.0"
FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "capabilities.manifest.json"
)


def main() -> None:
    rendered = render_capabilities_manifest(app, cli_version=FIXTURE_CLI_VERSION)
    FIXTURE_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {FIXTURE_PATH} (cli version {FIXTURE_CLI_VERSION!r})")


if __name__ == "__main__":
    main()
