"""Non-interactive prompt guards."""

from __future__ import annotations

from .config import get_config
from .exceptions import ErrorCode, MonarchCLIError
from .exit_codes import EXIT_INPUT_NEEDED


class InputNeededError(MonarchCLIError):
    """Raised when a command would prompt in non-interactive mode."""

    def __init__(self, prompt: str, fix: str) -> None:
        super().__init__(
            message=f"Cannot prompt for {prompt} in non-interactive mode.",
            code=ErrorCode.INPUT_NEEDED,
            details={"prompt": prompt, "fix": fix},
            exit_code=EXIT_INPUT_NEEDED,
        )


def require_interactive(prompt: str, *, fix: str) -> None:
    """Fail fast when a prompt would block a headless session."""
    if get_config().non_interactive:
        raise InputNeededError(prompt, fix)
