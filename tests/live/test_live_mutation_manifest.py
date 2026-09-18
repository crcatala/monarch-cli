"""Unit tests for the live mutation recovery manifest (mc-584r).

Non-live: no API calls. They prove the restricted-permission, atomic manifest
behavior and the redaction guarantees that must hold before the first
disposable-fixture mutation.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from tests.live import live_mutation_manifest as manifest_mod
from tests.live.live_mutation_manifest import (
    RECOVERY_DIR_NAME,
    RecoveryManifest,
    RecoveryManifestError,
    assert_manifest_is_safe,
    generate_run_id,
    recovery_directory,
)


def test_recovery_directory_is_repository_relative(tmp_path: Path) -> None:
    directory = recovery_directory(tmp_path)
    assert directory == tmp_path / RECOVERY_DIR_NAME
    assert directory.name == ".monarch-live-mutation-recovery"


def test_generate_run_id_is_high_entropy_unique() -> None:
    ids = {generate_run_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(len(value) == 32 for value in ids)


def test_create_restricts_permissions(tmp_path: Path) -> None:
    manifest = RecoveryManifest.create(tmp_path, "run-abc")
    directory = recovery_directory(tmp_path)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(manifest.path.stat().st_mode) == 0o600
    assert manifest.path == directory / "run-abc.json"


def test_record_appends_and_persists_atomically(tmp_path: Path) -> None:
    manifest = RecoveryManifest.create(tmp_path, "run-abc")
    manifest.record(
        operation="live-fixture account create",
        phase="intent",
        status="pending",
        remote_ids=[],
        recovery_steps=["lookup by marker"],
    )
    manifest.record(
        operation="live-fixture account create",
        phase="observed",
        status="succeeded",
        remote_ids=["acct-1"],
        recovery_steps=["delete acct-1"],
    )

    on_disk = json.loads(manifest.path.read_text())
    assert on_disk["schema"] == manifest_mod.MANIFEST_SCHEMA
    assert on_disk["run_id"] == "run-abc"
    assert [entry["phase"] for entry in on_disk["operations"]] == ["intent", "observed"]
    assert on_disk["operations"][1]["remote_ids"] == ["acct-1"]
    # No temp file is left behind.
    assert list(manifest.path.parent.glob("*.tmp")) == []
    # File mode stays restricted after repeated writes.
    assert stat.S_IMODE(manifest.path.stat().st_mode) == 0o600


def test_record_drops_forbidden_metadata_keys(tmp_path: Path) -> None:
    manifest = RecoveryManifest.create(tmp_path, "run-abc")
    entry = manifest.record(
        operation="live-fixture account create",
        phase="intent",
        status="pending",
        metadata={
            "token": "super-secret",
            "amount": 12345.67,
            "household_id": "hh-secret",
            "safe_label": "fixture",
            "nested": {"password": "pw", "keep": "ok"},
        },
    )
    assert "token" not in entry.get("metadata", {})
    assert "amount" not in entry.get("metadata", {})
    assert "household_id" not in entry.get("metadata", {})
    assert entry["metadata"]["safe_label"] == "fixture"
    assert entry["metadata"]["nested"] == {"keep": "ok"}

    on_disk = json.loads(manifest.path.read_text())
    serialized = json.dumps(on_disk)
    assert "super-secret" not in serialized
    assert "hh-secret" not in serialized
    assert "pw" not in serialized


def test_record_redacts_forbidden_keys_nested_in_sequences(tmp_path: Path) -> None:
    manifest = RecoveryManifest.create(tmp_path, "run-abc")
    entry = manifest.record(
        operation="live-fixture account create",
        phase="intent",
        status="pending",
        metadata={
            "steps": [
                {"token": "secret-in-list", "keep": "ok"},
                [{"password": "pw-in-list"}],
                "plain",
            ],
        },
    )
    assert entry["metadata"]["steps"] == [{"keep": "ok"}, [{}], "plain"]
    serialized = json.dumps(json.loads(manifest.path.read_text()))
    assert "secret-in-list" not in serialized
    assert "pw-in-list" not in serialized


def test_record_rejects_payload_without_forbidden_keys(tmp_path: Path) -> None:
    manifest = RecoveryManifest.create(tmp_path, "run-abc")
    # The public record() path only accepts safe fields, so a forbidden key can
    # only arrive through internal corruption; the guard must still trip.
    manifest._data["operations"].append({"balance": 1000})  # type: ignore[index]
    with pytest.raises(RecoveryManifestError):
        manifest._write()


def test_assert_manifest_is_safe_detects_nested_forbidden_keys() -> None:
    assert_manifest_is_safe({"safe": [{"nested": {"ok": 1}}]})
    with pytest.raises(RecoveryManifestError):
        assert_manifest_is_safe({"outer": [{"inner": {"access_token": "x"}}]})


def test_remove_deletes_manifest(tmp_path: Path) -> None:
    manifest = RecoveryManifest.create(tmp_path, "run-abc")
    assert manifest.path.exists()
    manifest.remove()
    assert not manifest.path.exists()


def test_manifest_excludes_unrelated_directory_scope(tmp_path: Path) -> None:
    # The directory is created exactly under the given root, never in caches.
    RecoveryManifest.create(tmp_path, "run-abc")
    assert (tmp_path / RECOVERY_DIR_NAME).is_dir()
    for name in (".pytest_cache", "tests"):
        assert not (tmp_path / name / RECOVERY_DIR_NAME).exists()


def test_dir_mode_repaired_when_preexisting(tmp_path: Path) -> None:
    directory = recovery_directory(tmp_path)
    directory.mkdir(mode=0o755)
    os.chmod(directory, 0o755)
    RecoveryManifest.create(tmp_path, "run-abc")
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
