"""Shared non-interactive prompt policy (mc-2btg).

Every interactive input request in the CLI (text prompts, password reads,
storage choices, MFA codes, destructive confirmations) must go through the
guards in this module. The policy is driven by one shared non-interactive
mode, resolved from (highest first, OR-combined):

1. The global ``--non-interactive`` CLI flag (before the command path).
2. The ``MONARCH_NON_INTERACTIVE`` environment variable (truthy: 1/true/yes).
3. The ``non_interactive`` key in ``~/.config/monarch-cli/config.toml``.

When non-interactive mode is enabled, a prompt request fails promptly with
:class:`PromptBlockedError` — a structured ``PROMPT_BLOCKED`` error with a
stable exit code (5) — *before* any read from stdin, ``/dev/tty``, password
input, or confirmation input. The error names the missing input and the
non-interactive remedy so automated callers can fix their invocation.

Separation of safety concepts (mirrors mc-k48z):

- Non-interactive mode controls whether input may be *requested*.
- It never authorizes mutations (``--allow-mutations`` is still required) and
  never satisfies destructive confirmation. A confirmation requested under
  non-interactive mode still fails; it is never auto-answered.

Interactive behavior is unchanged when non-interactive mode is not enabled.

Contributor guidance: any future prompt site must use :func:`prompt_text`,
:func:`prompt_secret`, :func:`prompt_choice`, or :func:`confirm_action`
instead of calling ``typer.prompt``/``typer.confirm``/``getpass`` directly.
Explicit, non-prompt input channels (e.g. ``transactions batch-update
--stdin``) are deliberate data redirection, not prompting, and remain
available in non-interactive mode.
"""

from __future__ import annotations

import getpass
from typing import Any, cast

import typer

from .exceptions import ErrorCode, MonarchCLIError

#: Stable exit code for a blocked prompt in non-interactive mode.
#: Exit 1 is generic failure, 2 usage/validation, 3 blocked mutation, and 4
#: ambiguity/partial outcomes; 5 is reserved for prompt policy failures.
PROMPT_BLOCKED_EXIT_CODE = 5


class PromptBlockedError(MonarchCLIError):
    """A prompt was requested while non-interactive mode is enabled.

    Raised before any input is read. ``details`` identifies the missing input
    and the non-interactive remedy so automation can recover without hanging.
    """

    def __init__(
        self,
        missing_input: str,
        remedy: str,
        operation: str | None = None,
    ) -> None:
        message = (
            f"Non-interactive mode is enabled, so the CLI cannot prompt for "
            f"{missing_input}. {remedy}"
        )
        details: dict[str, Any] = {
            "missing_input": missing_input,
            "remedy": remedy,
        }
        if operation:
            details["operation"] = operation
        super().__init__(
            message=message,
            code=ErrorCode.PROMPT_BLOCKED,
            details=details,
            exit_code=PROMPT_BLOCKED_EXIT_CODE,
        )


# --- Shared non-interactive state ------------------------------------------
#
# Deliberately process-global and set only by the root CLI callback from the
# resolved policy (flag OR config). It never persists between invocations.

_non_interactive: bool = False


def set_non_interactive(value: bool) -> None:
    """Set non-interactive mode for the current process invocation."""
    global _non_interactive  # noqa: PLW0603
    _non_interactive = bool(value)


def non_interactive() -> bool:
    """Return whether the current invocation forbids prompting."""
    return _non_interactive


def reset_non_interactive() -> None:
    """Clear non-interactive mode (used by tests and between invocations)."""
    global _non_interactive  # noqa: PLW0603
    _non_interactive = False


def resolve_non_interactive(cli_flag: bool = False) -> bool:
    """Resolve the effective non-interactive policy for one invocation.

    The CLI flag enables the policy unconditionally; otherwise the layered
    config decides (environment variable ``MONARCH_NON_INTERACTIVE`` and the
    ``non_interactive`` config-file key, already merged by :class:`Config`).
    """
    if cli_flag:
        return True
    from .config import get_config  # noqa: PLC0415  (avoid import cycle)

    return bool(get_config().non_interactive)


# --- Shared guard and prompt helpers ----------------------------------------


def require_prompt_allowed(
    *,
    missing_input: str,
    remedy: str,
    operation: str | None = None,
) -> None:
    """Fail promptly if a prompt would be requested in non-interactive mode.

    Must be called immediately before any input read (stdin, /dev/tty,
    password, MFA code, storage choice, or confirmation) so a blocked prompt
    never hangs or partially consumes input.
    """
    if non_interactive():
        raise PromptBlockedError(missing_input, remedy, operation)


def prompt_text(
    label: str,
    *,
    missing_input: str,
    remedy: str,
    default: str | None = None,
    operation: str | None = None,
) -> str:
    """Prompt for a text value through the shared non-interactive guard."""
    require_prompt_allowed(missing_input=missing_input, remedy=remedy, operation=operation)
    return cast(str, typer.prompt(label, default=default))


def prompt_secret(
    label: str,
    *,
    missing_input: str,
    remedy: str,
    operation: str | None = None,
) -> str:
    """Prompt for a secret (password) through the shared non-interactive guard.

    The guard runs before ``getpass`` touches stdin or ``/dev/tty``.
    """
    require_prompt_allowed(missing_input=missing_input, remedy=remedy, operation=operation)
    return getpass.getpass(label)


def prompt_choice(
    label: str,
    *,
    choices: list[str],
    missing_input: str,
    remedy: str,
    default: str | None = None,
    operation: str | None = None,
) -> str:
    """Prompt for a value from a fixed set through the shared guard.

    The guard runs before any input read; choice validation stays with the
    caller (unchanged interactive behavior).
    """
    require_prompt_allowed(missing_input=missing_input, remedy=remedy, operation=operation)
    # Choice validation intentionally remains with the caller to preserve the
    # interactive behavior of each command.
    _ = choices
    return cast(str, typer.prompt(label, default=default))


def confirm_action(
    message: str,
    *,
    missing_input: str,
    remedy: str,
    default: bool = False,
    operation: str | None = None,
) -> bool:
    """Request destructive/explicit confirmation through the shared guard.

    Non-interactive mode controls whether prompting is allowed; it never
    auto-answers a confirmation. With the mode enabled, confirmation is
    refused and the caller must pass the explicit non-interactive equivalent
    of the requested action (if one exists) instead.
    """
    require_prompt_allowed(missing_input=missing_input, remedy=remedy, operation=operation)
    return typer.confirm(message, default=default)


__all__ = [
    "PROMPT_BLOCKED_EXIT_CODE",
    "PromptBlockedError",
    "confirm_action",
    "non_interactive",
    "prompt_choice",
    "prompt_secret",
    "prompt_text",
    "require_prompt_allowed",
    "reset_non_interactive",
    "resolve_non_interactive",
    "set_non_interactive",
]
