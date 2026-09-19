"""Capabilities manifest contract tests (mc-82kf).

These pin the ``monarch capabilities`` command and the explicit capability
metadata in :mod:`monarch_cli.core.capabilities`:

* one canonical fixture test verifies stable manifest shape, ordering, and
  byte-for-byte serialization across repeated runs;
* completeness tests fail when a registered command is missing metadata,
  metadata disagrees with the shared execution policy, schema references are
  unknown, or the generated inventory is unexpectedly empty or partial;
* the manifest is proven side-effect free (no auth lookup, client, network,
  prompt, or config/session write).

They never touch the network or real credentials.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from monarch_cli import __version__
from monarch_cli.core.capabilities import (
    CAPABILITIES_MANIFEST_VERSION,
    CAPABILITIES_TAXONOMY_VERSION,
    COMMAND_CAPABILITIES,
    CapabilitiesError,
    build_capabilities_manifest,
    render_capabilities_manifest,
    validate_capabilities,
)
from monarch_cli.core.operations import Effect, collect_command_effects
from monarch_cli.main import app
from monarch_cli.schemas import OPERATION_CONTRACTS, SCHEMA_ARTIFACTS

runner = CliRunner()

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "capabilities.manifest.json"

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def _manifest() -> dict[str, Any]:
    return build_capabilities_manifest(app, cli_version=__version__)


# ---------------------------------------------------------------------------
# Canonical fixture: stable shape, ordering, byte-for-byte serialization
# ---------------------------------------------------------------------------


class TestCanonicalFixture:
    def test_matches_checked_in_fixture_byte_for_byte(self) -> None:
        assert FIXTURE_PATH.exists(), "canonical capabilities fixture is missing"
        expected = FIXTURE_PATH.read_text(encoding="utf-8")
        actual = render_capabilities_manifest(app, cli_version=__version__)
        assert actual == expected, (
            "capabilities manifest drifted from the canonical fixture; if the "
            "change is intended, regenerate tests/fixtures/capabilities.manifest.json"
        )

    def test_repeated_runs_serialize_identically(self) -> None:
        first = render_capabilities_manifest(app, cli_version=__version__)
        second = render_capabilities_manifest(app, cli_version=__version__)
        assert first == second

    def test_command_ordering_is_deterministic(self) -> None:
        names = [command["name"] for command in _manifest()["commands"]]
        assert names == sorted(names)
        assert names == sorted(COMMAND_CAPABILITIES)

    def test_fixture_is_valid_json_and_versioned(self) -> None:
        document = json.loads(render_capabilities_manifest(app, cli_version=__version__))
        assert document["manifest_version"] == CAPABILITIES_MANIFEST_VERSION
        assert document["taxonomy_version"] == CAPABILITIES_TAXONOMY_VERSION


# ---------------------------------------------------------------------------
# Completeness: registered tree and explicit metadata must agree
# ---------------------------------------------------------------------------


class TestCompleteness:
    def test_registered_commands_all_have_metadata(self) -> None:
        # Raises CapabilitiesError on any missing metadata.
        validate_capabilities(app)
        inventory = collect_command_effects(app)
        assert set(inventory) == set(COMMAND_CAPABILITIES)

    def test_inventory_is_not_empty(self) -> None:
        empty_app = typer.Typer(name="empty")

        @empty_app.callback()
        def _callback() -> None:  # pragma: no cover - never invoked
            pass

        with pytest.raises(CapabilitiesError, match="empty"):
            validate_capabilities(empty_app)

    def test_missing_metadata_is_rejected(self) -> None:
        synthetic = typer.Typer(name="synthetic", no_args_is_help=True)

        @synthetic.callback()
        def _callback() -> None:  # pragma: no cover - never invoked
            pass

        @synthetic.command("rogue")
        def rogue() -> None:  # pragma: no cover - never invoked
            raise AssertionError("should not run")

        with pytest.raises(CapabilitiesError, match="missing capability metadata"):
            validate_capabilities(synthetic)

    def test_unregistered_metadata_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        capability = COMMAND_CAPABILITIES["accounts list"]
        monkeypatch.setitem(
            COMMAND_CAPABILITIES,
            "accounts does-not-exist",
            dataclasses.replace(capability, path="accounts does-not-exist"),
        )
        with pytest.raises(CapabilitiesError, match="unregistered"):
            validate_capabilities(app)

    def test_effect_disagreement_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        capability = COMMAND_CAPABILITIES["accounts list"]
        monkeypatch.setitem(
            COMMAND_CAPABILITIES,
            "accounts list",
            dataclasses.replace(capability, effects=frozenset({Effect.REMOTE_MUTATION})),
        )
        with pytest.raises(CapabilitiesError, match="disagrees with the shared execution policy"):
            validate_capabilities(app)

    def test_unknown_schema_reference_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        capability = COMMAND_CAPABILITIES["accounts list"]
        monkeypatch.setitem(
            COMMAND_CAPABILITIES,
            "accounts list",
            dataclasses.replace(
                capability,
                output=dataclasses.replace(
                    capability.output, schemas=("urn:monarch-cli:schema:made-up:v1",)
                ),
            ),
        )
        with pytest.raises(CapabilitiesError, match="unknown schema URN"):
            validate_capabilities(app)

    def test_ndjson_disagreement_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        capability = COMMAND_CAPABILITIES["accounts list"]
        monkeypatch.setitem(
            COMMAND_CAPABILITIES,
            "accounts list",
            dataclasses.replace(
                capability,
                output=dataclasses.replace(capability.output, ndjson=False),
            ),
        )
        with pytest.raises(CapabilitiesError, match="NDJSON declaration disagrees"):
            validate_capabilities(app)

    def test_raw_disagreement_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        capability = COMMAND_CAPABILITIES["accounts list"]
        monkeypatch.setitem(
            COMMAND_CAPABILITIES,
            "accounts list",
            dataclasses.replace(
                capability,
                output=dataclasses.replace(capability.output, raw=False),
            ),
        )
        with pytest.raises(CapabilitiesError, match="raw declaration disagrees"):
            validate_capabilities(app)

    def test_preview_disagreement_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        capability = COMMAND_CAPABILITIES["transactions update"]
        monkeypatch.setitem(
            COMMAND_CAPABILITIES,
            "transactions update",
            dataclasses.replace(capability, preview=False),
        )
        with pytest.raises(CapabilitiesError, match="--dry-run option"):
            validate_capabilities(app)


# ---------------------------------------------------------------------------
# Manifest content requirements
# ---------------------------------------------------------------------------


class TestManifestContent:
    def test_every_command_describes_path_and_effects(self) -> None:
        document = _manifest()
        registered = collect_command_effects(app)
        for command in document["commands"]:
            name = command["name"]
            assert command["path"] == name.split()
            assert command["effects"] == sorted(effect.value for effect in registered[name])

    def test_every_option_and_argument_is_described(self) -> None:
        import typer.main

        root = typer.main.get_command(app)
        for command in _manifest()["commands"]:
            node = root
            for part in command["path"]:
                node = node.commands[part]
            expected_options = {
                param.name for param in node.params if param.param_type_name == "option"
            }
            expected_arguments = {
                param.name for param in node.params if param.param_type_name == "argument"
            }
            assert {item["name"] for item in command["options"]} == expected_options
            assert {item["name"] for item in command["arguments"]} == expected_arguments

    def test_positional_arguments_are_not_represented_as_flags(self) -> None:
        for command in _manifest()["commands"]:
            for argument in command["arguments"]:
                assert argument["kind"] == "argument"
                assert argument["flags"] == [], command["name"]

    def test_required_inputs_and_defaults_are_represented(self) -> None:
        document = _manifest()
        commands = {command["name"]: command for command in document["commands"]}
        create = commands["transactions create"]
        by_name = {item["name"]: item for item in create["options"]}
        assert by_name["account_id"]["required"] is True
        assert by_name["account_id"]["default"] is None
        assert by_name["notes"]["required"] is False
        assert by_name["notes"]["default"] == ""

        listing = commands["transactions list"]
        limit = {item["name"]: item for item in listing["options"]}["limit"]
        assert limit["type"] == "integer"
        assert limit["default"] == 100

    def test_repeatable_and_enum_options_are_represented(self) -> None:
        document = _manifest()
        command = next(c for c in document["commands"] if c["name"] == "transactions list")
        by_name = {item["name"]: item for item in command["options"]}
        assert by_name["account"]["repeatable"] is True
        assert by_name["format"]["type"] == "enum"
        assert by_name["format"]["choices"] == ["plain", "json", "table", "csv", "compact"]

    def test_no_framework_internal_shapes_leak(self) -> None:
        # The manifest must be plain JSON: no Click/Typer objects anywhere.
        document = _manifest()
        serialized = json.dumps(document, sort_keys=True)
        assert "click." not in serialized
        assert "typer." not in serialized
        for command in document["commands"]:
            for item in (*command["arguments"], *command["options"]):
                assert isinstance(item["name"], str)
                assert isinstance(item["flags"], list)
                assert isinstance(item["type"], str)
                assert isinstance(item["choices"], list)
                assert isinstance(item["repeatable"], bool)

    def test_safety_classification_is_explicit_and_separate(self) -> None:
        document = _manifest()
        commands = {command["name"]: command for command in document["commands"]}
        delete = commands["transactions delete"]["safety"]
        assert delete["requires_authorization"] is True
        assert delete["requires_destructive_confirmation"] is True
        assert delete["interactive"] is False
        assert delete["supports_preview"] is True

        login = commands["auth login"]["safety"]
        assert login["requires_authorization"] is False
        assert login["requires_destructive_confirmation"] is False
        assert login["interactive"] is True

        refresh = commands["accounts refresh"]["safety"]
        assert refresh["requires_authorization"] is True
        assert refresh["requires_destructive_confirmation"] is False

    def test_preview_and_authorization_are_represented_separately(self) -> None:
        document = _manifest()
        commands = {command["name"]: command for command in document["commands"]}
        update = commands["transactions update"]["safety"]
        assert update["supports_preview"] is True
        assert update["requires_authorization"] is True

    def test_global_output_is_distinct_from_per_command_ndjson_and_raw(self) -> None:
        document = _manifest()
        assert document["output"]["formats"] == ["json", "table", "csv", "compact", "plain"]
        assert document["output"]["quiet"]["mutation_outcomes_compatible"] is False
        commands = {command["name"]: command for command in document["commands"]}
        # NDJSON and raw are per-command and only present where supported.
        assert commands["transactions list"]["output"]["ndjson"] is True
        assert commands["transactions list"]["output"]["raw"] is True
        assert commands["budgets list"]["output"]["ndjson"] is False
        assert commands["budgets list"]["output"]["raw"] is False

    def test_raw_passthrough_is_marked_unstable_and_unschematized(self) -> None:
        output = _manifest()["output"]
        assert output["raw"]["stable"] is False
        assert output["raw"]["schema_urn"] is None

    def test_schema_contracts_match_mc_cpzi_mapping_exactly(self) -> None:
        document = _manifest()
        expected = sorted(
            [
                {"contract": artifact.contract, "version": artifact.version, "urn": artifact.urn}
                for artifact in SCHEMA_ARTIFACTS.values()
            ],
            key=lambda item: (item["contract"], item["version"]),
        )
        assert document["schema_contracts"] == expected

    def test_operation_contracts_match_mc_cpzi_mapping_exactly(self) -> None:
        document = _manifest()
        expected = sorted(
            [
                {
                    "operation": contract.operation,
                    "schema_urn": SCHEMA_ARTIFACTS[(contract.schema_contract, "v1")].urn,
                    "effect_entities": list(contract.effect_entities),
                }
                for contract in OPERATION_CONTRACTS.values()
            ],
            key=lambda item: item["operation"],
        )
        assert document["operation_contracts"] == expected

    def test_taxonomy_lists_shared_effect_vocabulary(self) -> None:
        document = _manifest()
        assert document["taxonomy"]["effects"] == sorted(effect.value for effect in Effect)
        assert "remote_mutation" in document["taxonomy"]["effects"]
        assert "preview" in document["taxonomy"]["effects"]


# ---------------------------------------------------------------------------
# Side-effect-free generation
# ---------------------------------------------------------------------------


class TestSideEffectFreeGeneration:
    def test_generation_does_not_touch_config_client_network_or_prompts(self) -> None:
        def _explode(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("manifest generation must be side-effect free")

        with (
            patch("monarch_cli.core.adapter.get_authenticated_client", _explode),
            patch("monarch_cli.core.config.get_config", _explode),
            patch("monarch_cli.core.config.get_config_dir", _explode),
            patch("monarch_cli.core.session.get_storage_info", _explode),
            patch("monarch_cli.core.prompting.prompt_text", _explode),
            patch("monarch_cli.core.prompting.prompt_secret", _explode),
            patch("monarch_cli.core.prompting.confirm_action", _explode),
            patch("monarch_cli.core.async_utils.run_api_call", _explode),
        ):
            first = render_capabilities_manifest(app, cli_version=__version__)
            second = render_capabilities_manifest(app, cli_version=__version__)

        assert first == second
        assert json.loads(first)["manifest_version"] == CAPABILITIES_MANIFEST_VERSION

    def test_cli_command_emits_manifest_without_a_client(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MONARCH_CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("MONARCH_TOKEN", raising=False)

        def _no_client() -> None:
            raise AssertionError("capabilities must not construct an authenticated client")

        with patch("monarch_cli.core.adapter.get_authenticated_client", _no_client):
            result = runner.invoke(app, ["capabilities"])

        assert result.exit_code == 0, result.output
        payload = json.loads(ANSI_ESCAPE_RE.sub("", result.stdout))
        assert payload["manifest_version"] == CAPABILITIES_MANIFEST_VERSION
        assert payload["cli"]["version"] == __version__
