"""Recovery manifest for the gated live mutation suite (mc-584r).

A restricted-permission, git-ignored JSON journal records the intended and
observed effects of every disposable-fixture mutation attempt so an
interrupted run can be recovered manually. It is created before the first
mutation and updated around every attempted fixture effect.

Owner-approved durability rules:

- Repository-relative ``.monarch-live-mutation-recovery/`` directory (resolved
  from pytest's repository root), never ``tests/live``, ``.pytest_cache``, or a
  temporary directory.
- Directory mode ``0700``; per-run manifest mode ``0600``.
- Atomic updates: same-directory temporary file, flush + ``fsync``, then
  ``os.replace``.
- Manifests are named by the high-entropy run ID. A manifest is removed only
  after both the fixture transaction and fixture account cleanup are
  definitively known to have succeeded. Every ambiguous, incomplete,
  interrupted, or failed cleanup outcome preserves it.
- The manifest contains only the minimum operation, run marker, remote IDs,
  status, and recovery steps. It never contains credentials, financial values,
  raw payloads, household IDs, or unrelated household data.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Repository-relative recovery directory name (root-anchored in .gitignore).
RECOVERY_DIR_NAME = ".monarch-live-mutation-recovery"

#: Manifest schema identifier for machine consumers.
MANIFEST_SCHEMA = "live-mutation-recovery.v1"

_DIR_MODE = 0o700
_FILE_MODE = 0o600

#: Keys that must never be persisted in a recovery manifest. Metadata supplied
#: by callers is filtered against this set before it is written.
FORBIDDEN_KEYS = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "password",
        "authorization",
        "api_key",
        "secret",
        "cookie",
        "session",
        "balance",
        "amount",
        "raw",
        "payload",
        "household_id",
        "householdid",
        "account_number",
        "ssn",
    }
)


class RecoveryManifestError(RuntimeError):
    """The recovery manifest could not be created or updated safely."""


def generate_run_id() -> str:
    """Return a high-entropy run marker used for fixture names and manifests."""
    return secrets.token_hex(16)


def recovery_directory(repo_root: str | os.PathLike[str]) -> Path:
    """Return the repository-relative recovery directory path."""
    return Path(repo_root) / RECOVERY_DIR_NAME


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _redact_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop any forbidden key from caller metadata before it is persisted.

    Redaction is by key allowlist-adjacent filtering (forbidden-key removal).
    Nested mappings are filtered recursively.
    """
    if not metadata:
        return {}
    redacted: dict[str, Any] = {}
    for key, value in metadata.items():
        if key.lower() in FORBIDDEN_KEYS:
            continue
        if isinstance(value, Mapping):
            redacted[key] = _redact_metadata(value)
        else:
            redacted[key] = value
    return redacted


def assert_manifest_is_safe(data: Mapping[str, Any]) -> None:
    """Raise if a manifest payload contains a forbidden key anywhere.

    Args:
        data: A manifest dict (or nested value) to inspect.

    Raises:
        RecoveryManifestError: If a forbidden key is present.
    """
    if isinstance(data, Mapping):
        for key, value in data.items():
            if isinstance(key, str) and key.lower() in FORBIDDEN_KEYS:
                raise RecoveryManifestError(
                    f"Recovery manifest contains forbidden key {key!r}; refusing to persist."
                )
            assert_manifest_is_safe(value)
    elif isinstance(data, (list, tuple)):
        for item in data:
            assert_manifest_is_safe(item)


class RecoveryManifest:
    """A single per-run recovery manifest with atomic, restricted writes."""

    def __init__(self, path: Path, data: dict[str, Any]) -> None:
        self._path = path
        self._data = data

    @property
    def path(self) -> Path:
        """Absolute path of the manifest file (safe to print on failure)."""
        return self._path

    @property
    def run_id(self) -> str:
        return str(self._data["run_id"])

    @classmethod
    def create(
        cls,
        repo_root: str | os.PathLike[str],
        run_id: str | None = None,
    ) -> RecoveryManifest:
        """Create the recovery directory and this run's manifest atomically."""
        run_id = run_id or generate_run_id()
        directory = recovery_directory(repo_root)
        try:
            directory.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
            os.chmod(directory, _DIR_MODE)
        except OSError as e:  # pragma: no cover - environment dependent
            raise RecoveryManifestError(
                f"Could not create recovery directory {directory}: {e.strerror or e}"
            ) from e

        data: dict[str, Any] = {
            "schema": MANIFEST_SCHEMA,
            "run_id": run_id,
            "marker": run_id,
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
            "operations": [],
        }
        manifest = cls(directory / f"{run_id}.json", data)
        manifest._write()
        return manifest

    def record(
        self,
        *,
        operation: str,
        phase: str,
        status: str,
        remote_ids: tuple[str, ...] | list[str] = (),
        recovery_steps: tuple[str, ...] | list[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one effect record and atomically persist the manifest.

        Args:
            operation: Stable namespaced fixture operation or CLI operation.
            phase: ``intent`` (before the attempt) or ``observed`` (after).
            status: ``pending``, ``succeeded``, ``failed``, or ``ambiguous``.
            remote_ids: Known remote fixture IDs (never household or
                unrelated records).
            recovery_steps: Minimal manual recovery instructions.
            metadata: Optional non-sensitive labels; forbidden keys are
                dropped before persistence.

        Returns:
            The recorded entry.
        """
        entry: dict[str, Any] = {
            "operation": operation,
            "phase": phase,
            "status": status,
            "run_marker": self.run_id,
            "remote_ids": [str(value) for value in remote_ids],
            "recovery_steps": [str(step) for step in recovery_steps],
            "recorded_at": _utcnow(),
        }
        redacted = _redact_metadata(metadata)
        if redacted:
            entry["metadata"] = redacted

        assert_manifest_is_safe(entry)

        self._data["operations"].append(entry)
        self._data["updated_at"] = _utcnow()
        self._write()
        return entry

    def read(self) -> dict[str, Any]:
        """Return the current in-memory manifest data."""
        return self._data

    def remove(self) -> None:
        """Remove the manifest after definitively successful cleanup."""
        try:
            self._path.unlink(missing_ok=True)
        except OSError as e:  # pragma: no cover - environment dependent
            raise RecoveryManifestError(
                f"Could not remove recovery manifest {self._path}: {e.strerror or e}"
            ) from e

    def _write(self) -> None:
        """Atomically persist the manifest with mode 0600."""
        assert_manifest_is_safe(self._data)
        # Same-directory temp file so os.replace is atomic on one filesystem.
        tmp_path = self._path.with_name(self._path.name + ".tmp")
        try:
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(self._data, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                # fdopen closes the descriptor even on failure.
                raise
            os.chmod(tmp_path, _FILE_MODE)
            os.replace(tmp_path, self._path)
            self._fsync_directory()
        except OSError as e:
            raise RecoveryManifestError(
                f"Could not write recovery manifest {self._path}: {e.strerror or e}"
            ) from e

    def _fsync_directory(self) -> None:
        """Best-effort directory fsync so the rename is durable."""
        try:
            dir_fd = os.open(self._path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:  # pragma: no cover - not supported on every platform
            pass
        finally:
            os.close(dir_fd)


__all__ = [
    "RECOVERY_DIR_NAME",
    "MANIFEST_SCHEMA",
    "FORBIDDEN_KEYS",
    "RecoveryManifestError",
    "generate_run_id",
    "recovery_directory",
    "assert_manifest_is_safe",
    "RecoveryManifest",
]
