"""State-file corruption guards."""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path


def back_up_corrupt_file(path: Path, label: str) -> Path | None:
    """Copy a corrupt state file aside and warn without deleting the original."""
    if not path.exists():
        return None

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.corrupt.{timestamp}")
    suffix = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.corrupt.{timestamp}.{suffix}")
        suffix += 1

    shutil.copy2(path, backup_path)
    print(
        f"Warning: Backed up corrupt {label} file {path} to {backup_path}",
        file=sys.stderr,
    )
    return backup_path
