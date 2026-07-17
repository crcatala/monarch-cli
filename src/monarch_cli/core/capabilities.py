"""Machine-readable CLI capabilities manifest."""

from __future__ import annotations

from typing import Any

import click

from .config import get_config_file_path
from .exit_codes import EXIT_CODES
from .session import get_session_path

CONTRACT_VERSION = "1"

ENV_VARS: tuple[dict[str, str], ...] = (
    {"name": "MONARCH_TOKEN", "description": "Session token for authentication."},
    {"name": "MONARCH_CONFIG_DIR", "description": "Directory for config and session files."},
    {"name": "MONARCH_SESSION_PATH", "description": "Path to the JSON session file."},
    {"name": "MONARCH_FORMAT", "description": "Default output format."},
    {"name": "MONARCH_VERBOSE", "description": "Enable operational progress messages."},
    {"name": "MONARCH_DEBUG", "description": "Enable stack traces on unexpected errors."},
    {"name": "MONARCH_QUIET", "description": "Output only IDs, one per line."},
    {"name": "MONARCH_TIMEOUT", "description": "API request timeout in seconds."},
    {"name": "MONARCH_MAX_RETRIES", "description": "Max API retry attempts."},
    {"name": "MONARCH_NON_INTERACTIVE", "description": "Fail instead of prompting."},
    {"name": "MONARCH_NO_COLOR", "description": "Disable colored output."},
    {"name": "NO_COLOR", "description": "Standard color disable flag."},
    {"name": "CI", "description": "Enables non-interactive mode when truthy."},
)

MUTATING_WORDS = {
    "attach",
    "create",
    "delete",
    "login",
    "logout",
    "refresh",
    "remove",
    "reset",
    "set",
    "update",
    "upload",
    "upsert",
}


def _sort_key(value: str) -> tuple[int, ...]:
    return tuple(ord(char) for char in value)


def _option_to_dict(option: click.Option) -> dict[str, Any]:
    flags = [*option.opts, *option.secondary_opts]
    return {
        "flags": sorted(flags, key=_sort_key),
        "help": option.help or "",
        "required": option.required,
        "default": None if option.default is None else str(option.default),
        "multiple": option.multiple,
    }


def _argument_to_dict(argument: click.Argument) -> dict[str, Any]:
    return {
        "name": argument.name or "",
        "required": argument.required,
        "nargs": argument.nargs,
    }


def _command_to_dict(name: str, command: click.Command) -> dict[str, Any]:
    flags = [
        _option_to_dict(param)
        for param in command.params
        if isinstance(param, click.Option) and not param.hidden
    ]
    arguments = [
        _argument_to_dict(param) for param in command.params if isinstance(param, click.Argument)
    ]
    words = set(name.split())
    return {
        "name": name,
        "description": command.short_help or command.help or "",
        "flags": sorted(
            flags,
            key=lambda item: _sort_key(item["flags"][0] if item["flags"] else ""),
        ),
        "arguments": arguments,
        "json_output": any("--json" in option["flags"] for option in flags),
        "mutates": bool(words & MUTATING_WORDS),
    }


def _walk_commands(group: click.Group, prefix: str = "") -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for command_name in sorted(group.commands, key=_sort_key):
        command = group.commands[command_name]
        full_name = f"{prefix} {command_name}".strip()
        commands.append(_command_to_dict(full_name, command))
        if isinstance(command, click.Group):
            commands.extend(_walk_commands(command, full_name))
    return commands


def build_capabilities(root_command: click.Command, cli_version: str) -> dict[str, Any]:
    """Build the deterministic agent contract for the current Typer app."""
    global_flags = [
        _option_to_dict(param)
        for param in root_command.params
        if isinstance(param, click.Option) and not param.hidden
    ]
    commands = _walk_commands(root_command) if isinstance(root_command, click.Group) else []
    return {
        "contract_version": CONTRACT_VERSION,
        "cli_version": cli_version,
        "commands": sorted(commands, key=lambda item: _sort_key(item["name"])),
        "global_flags": sorted(
            global_flags, key=lambda item: _sort_key(item["flags"][0] if item["flags"] else "")
        ),
        "exit_codes": EXIT_CODES,
        "env_vars": sorted(ENV_VARS, key=lambda item: _sort_key(item["name"])),
        "config_files": [
            {"path": "config.toml", "scope": "user", "resolved_path": str(get_config_file_path())},
            {"path": "session.json", "scope": "user", "resolved_path": str(get_session_path())},
        ],
    }
