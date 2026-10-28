#!/usr/bin/env python3
"""release-standard: scripts/build_info.py r1 (do not edit; see RELEASING.md)

Usage: python3 scripts/build_info.py src/<package>/_build_info.json

Stamps the commit, commit date and dirty state into the package. Run it right before
building the wheel and sdist, from the commit that is (or will be) tagged.
"""

import json
import subprocess
import sys
from pathlib import Path


def git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


if len(sys.argv) != 2:
    sys.exit(__doc__)

info: dict = {}
commit = git("rev-parse", "HEAD")
if commit:
    info = {
        "commit": commit,
        "date": git("show", "-s", "--format=%cs", "HEAD"),
        # Ignored files (the stamp itself, build output) do not count.
        "dirty": git("status", "--porcelain") != "",
    }
out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(info, indent=2) + "\n")
