"""
Progress indicators for monarch-cli.

Provides spinner context manager for long-running operations.
Outputs to stderr to preserve stdout for data (supports piping).
"""

import sys
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn


def is_interactive() -> bool:
    """Check if stderr is a TTY (interactive terminal).

    We check stderr because progress indicators go to stderr,
    allowing stdout to remain clean for data piping.

    Returns:
        True if stderr is connected to a terminal, False if piped/redirected.
    """
    return sys.stderr.isatty()


@contextmanager
def spinner(message: str) -> Iterator[None]:
    """Show a spinner during a long-running operation.

    In interactive mode (TTY), displays a Rich spinner with elapsed time.
    In non-interactive mode (piped), just prints the message to stderr.

    Args:
        message: Status message to display next to the spinner.

    Usage:
        with spinner("Fetching accounts..."):
            accounts = run_async(client.get_accounts())
    """
    if not is_interactive():
        # Non-TTY: just print the message and continue
        print(message, file=sys.stderr)
        yield
        return

    # Interactive: show Rich spinner with elapsed time
    # Use stderr console so stdout stays clean for data
    stderr_console = Console(stderr=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=stderr_console,
        transient=True,  # Spinner disappears after completion
    ) as progress:
        progress.add_task(message, total=None)  # Indeterminate task
        yield


__all__ = [
    "is_interactive",
    "spinner",
]
