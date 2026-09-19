"""``monarch capabilities`` command (mc-82kf).

Emits the deterministic, versioned capabilities manifest as JSON on stdout.
The command is side-effect free: it reads only the registered command tree and
the explicit capability metadata, so it never authenticates, constructs a
client, performs a network request, prompts, or writes config/session state.
"""

from __future__ import annotations

from .. import __version__
from ..core.capabilities import render_capabilities_manifest
from ..core.error_handler import handle_errors
from ..core.operations import Effect, operation_effects


@handle_errors
@operation_effects(Effect.READ_ONLY)
def capabilities() -> None:
    """Print the versioned, machine-readable CLI capabilities manifest.

    The manifest deterministically describes every command path, argument,
    option, required input, default, output support, safety requirement, and
    published contract version for the installed CLI. It performs no
    authentication lookup, client construction, network request, prompt, or
    config/session write. See docs/capabilities.md for discovery, versioning,
    stability, and raw-output caveats.

    Examples:
        monarch capabilities
        monarch capabilities | jq '.commands[].path'
        monarch capabilities | jq '.schema_contracts[].urn'
    """
    # Generation is prompt-free: no interaction is ever requested. The lazy
    # import avoids a module-import cycle with the CLI entry point.
    from ..main import app as root_app

    print(render_capabilities_manifest(root_app, cli_version=__version__), end="")


__all__ = ["capabilities"]
