"""
Error handler decorator for consistent CLI error handling.

Provides a decorator that catches exceptions and outputs structured errors
for AI agent consumption. Uses typer.Exit() for testability with CliRunner.
"""

import functools
import sys
import traceback
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import typer

from ..output import is_debug, output_error
from .exceptions import MonarchCLIError

P = ParamSpec("P")
R = TypeVar("R")


def handle_errors(func: Callable[P, R]) -> Callable[P, R]:  # noqa: UP047
    """Decorator that catches exceptions and outputs consistent errors.

    Handles three types of exceptions:
    1. KeyboardInterrupt: Prints "Interrupted." and exits with code 130
    2. MonarchCLIError: Outputs structured error and exits with error's exit_code
    3. Other exceptions: Wraps in MonarchCLIError and exits with code 1

    Uses typer.Exit() instead of sys.exit() for better testability with CliRunner.

    Args:
        func: The CLI command function to wrap.

    Returns:
        Wrapped function with error handling.

    Example:
        @app.command()
        @handle_errors
        def my_command():
            ...
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            raise typer.Exit(130) from None
        except MonarchCLIError as e:
            output_error(e)
            raise typer.Exit(e.exit_code) from None
        except Exception as e:
            if is_debug():
                traceback.print_exc()
            output_error(MonarchCLIError(f"Unexpected error: {e}"))
            raise typer.Exit(1) from None

    return wrapper


__all__ = ["handle_errors"]
