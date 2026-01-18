"""Authentication commands for Monarch CLI."""

from __future__ import annotations

import getpass
from typing import Annotated

import keyring
import typer
from monarchmoney import MonarchMoney, RequireMFAException  # type: ignore[import-untyped]

from ..core.adapter import extract_token_from_client, get_authenticated_client, reset_client
from ..core.async_utils import run_async
from ..core.error_handler import handle_errors
from ..core.exceptions import APIError, AuthenticationError
from ..core.session import (
    StorageBackend,
    delete_session_token,
    get_session_path,
    get_storage_info,
    save_session_token,
)
from ..output import OutputFormat, console, output

app = typer.Typer(
    help="Authentication management",
    no_args_is_help=True,
)


def _is_keyring_available() -> bool:
    """Check if a real keyring backend is available.

    The keyring library falls back to keyring.backends.fail.Keyring when
    no working backend is found (e.g., headless Linux without Secret Service).
    We detect this by checking the module name for "fail".

    See: https://github.com/jaraco/keyring#api-interface
    """
    try:
        backend = keyring.get_keyring()
        return "fail" not in type(backend).__module__
    except Exception:
        return False


def _get_keyring_backend_name() -> str:
    """Get the name of the current keyring backend."""
    try:
        backend = keyring.get_keyring()
        return type(backend).__name__
    except Exception:
        return "unknown"


def _prompt_storage_backend() -> StorageBackend:
    """Prompt user to choose a storage backend interactively."""
    console.print()
    console.print("[bold]Choose storage backend:[/bold]")

    if _is_keyring_available():
        console.print("  1. [green]keyring[/green] (recommended) - Secure OS credential storage")
        console.print("  2. file - JSON file in config directory")
        choice = typer.prompt("Enter choice", default="1")
        if choice == "2":
            return StorageBackend.FILE
        return StorageBackend.KEYRING
    else:
        console.print("  [yellow]Keyring not available, using file storage[/yellow]")
        return StorageBackend.FILE


@app.command()
def login(
    storage: Annotated[
        str | None,
        typer.Option(
            "-s",
            "--storage",
            help="Storage backend: keyring or file (skips interactive prompt)",
        ),
    ] = None,
) -> None:
    """Log in to Monarch Money.

    Prompts for email and password interactively. If MFA is enabled on your
    account, you'll be prompted for a code from your authenticator app.

    Note: This command uses interactive prompts and styled console output
    rather than structured JSON errors, as it's designed for human use.
    For programmatic auth status checking, use 'monarch auth status'.

    Examples:
        monarch auth login              # Interactive login
        monarch auth login -s file      # Use file storage
        monarch auth login -s keyring   # Use keyring storage
    """
    console.print("[bold]Monarch Money Login[/bold]")
    console.print()

    # Get credentials
    email = typer.prompt("Email")
    password = getpass.getpass("Password: ")

    # Determine storage backend
    if storage:
        storage_lower = storage.lower()
        if storage_lower == "keyring":
            if not _is_keyring_available():
                console.print("[red]✗ Keyring not available. Use --storage=file instead.[/red]")
                raise typer.Exit(1)
            backend = StorageBackend.KEYRING
        elif storage_lower == "file":
            backend = StorageBackend.FILE
        else:
            console.print(f"[red]✗ Invalid storage backend: {storage}[/red]")
            console.print("  Valid options: keyring, file")
            raise typer.Exit(1)
    else:
        backend = _prompt_storage_backend()

    # Attempt login
    console.print()
    console.print("Authenticating...", style="dim")

    mm = MonarchMoney()
    try:
        run_async(mm.login(email, password, use_saved_session=False, save_session=False))
    except RequireMFAException:
        # MFA required - prompt for code
        console.print()
        console.print("[yellow]MFA required[/yellow]")
        mfa_code = typer.prompt("MFA Code")
        try:
            run_async(mm.multi_factor_authenticate(email, password, mfa_code))
        except Exception as e:
            console.print(f"[red]✗ MFA authentication failed: {e}[/red]")
            raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]✗ Login failed: {e}[/red]")
        raise typer.Exit(1) from None

    # Extract and save token
    token = extract_token_from_client(mm)
    if not token:
        console.print("[red]✗ Failed to obtain authentication token[/red]")
        raise typer.Exit(1)

    save_session_token(token, backend)
    reset_client()  # Clear cached client so it picks up new token

    # Show success with account count
    try:
        client = get_authenticated_client()
        accounts_data = run_async(client.get_accounts())
        accounts = accounts_data.get("accounts", [])
        account_count = len(accounts)

        console.print()
        console.print("[green]✓ Logged in successfully[/green]")
        console.print(f"  Storage: {backend.value}")
        console.print(f"  Accounts: {account_count}")
    except Exception:
        # Login succeeded but couldn't fetch accounts - still show success
        console.print()
        console.print("[green]✓ Logged in successfully[/green]")
        console.print(f"  Storage: {backend.value}")


@app.command()
@handle_errors
def status(
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON (for scripts and AI agents)",
        ),
    ] = False,
) -> None:
    """Show current authentication status.

    Examples:
        monarch auth status              # Human-readable output
        monarch auth status --json       # JSON output for scripts
    """
    storage_info = get_storage_info()
    is_authenticated = storage_info["active_backend"] is not None

    if json_output:
        result = {
            "authenticated": is_authenticated,
            "storage_backend": storage_info["active_backend"],
            "message": (
                "Authenticated and ready"
                if is_authenticated
                else "Not authenticated. Run 'monarch auth login' to authenticate."
            ),
        }
        output(result, OutputFormat.JSON)
    else:
        # Human-readable output
        if is_authenticated:
            console.print("[green]✓ Authenticated[/green]")
            backend = storage_info["active_backend"]
            if backend == "file":
                console.print(f"  Backend: {backend} ({get_session_path()})")
            elif backend == "env":
                console.print(f"  Backend: {backend} (MONARCH_TOKEN)")
            else:
                console.print(f"  Backend: {backend}")
        else:
            console.print("[yellow]✗ Not authenticated[/yellow]")
            console.print()
            console.print("Run [cyan]monarch auth login[/cyan] to authenticate.")


@app.command()
@handle_errors
def logout(
    storage: Annotated[
        str | None,
        typer.Option(
            "-s",
            "--storage",
            help="Clear specific backend only: keyring, file, or file-compat",
        ),
    ] = None,
) -> None:
    """Log out and clear stored credentials.

    By default, clears tokens from all storage backends.
    Use --storage to clear a specific backend only.

    Examples:
        monarch auth logout              # Clear all tokens
        monarch auth logout -s keyring   # Clear keyring only
        monarch auth logout -s file      # Clear file only
    """
    if storage:
        storage_lower = storage.lower()
        try:
            backend = StorageBackend(storage_lower)
        except ValueError:
            console.print(f"[red]✗ Invalid storage backend: {storage}[/red]")
            console.print("  Valid options: keyring, file, file-compat")
            raise typer.Exit(1) from None

        delete_session_token(backend)
        console.print(f"[green]✓ Cleared {backend.value} storage[/green]")
    else:
        delete_session_token(None)  # Clear all
        console.print("[green]✓ Logged out from all storage backends[/green]")

    reset_client()


@app.command()
@handle_errors
def doctor() -> None:
    """Diagnose authentication setup.

    Checks keyring availability, shows status of all token storage
    locations, and tests API connectivity if authenticated.

    Examples:
        monarch auth doctor
    """
    console.print("[bold]Monarch CLI Auth Diagnostics[/bold]")
    console.print()

    # Keyring check
    console.print("[bold]Keyring:[/bold]")
    keyring_available = _is_keyring_available()
    keyring_backend = _get_keyring_backend_name()
    if keyring_available:
        console.print(f"  [green]✓ Available[/green] (backend: {keyring_backend})")
    else:
        console.print(f"  [yellow]✗ Not available[/yellow] (backend: {keyring_backend})")
    console.print()

    # Storage status
    console.print("[bold]Token Storage:[/bold]")
    storage_info = get_storage_info()

    if storage_info["has_env_token"]:
        console.print("  [green]✓ MONARCH_TOKEN[/green] env var set")
    else:
        console.print("  [dim]✗ MONARCH_TOKEN[/dim] env var not set")

    if storage_info["has_keyring_token"]:
        console.print("  [green]✓ Keyring[/green] token stored")
    else:
        console.print("  [dim]✗ Keyring[/dim] no token")

    if storage_info["has_file_token"]:
        console.print(f"  [green]✓ File[/green] token at {get_session_path()}")
    else:
        console.print(f"  [dim]✗ File[/dim] no token at {get_session_path()}")

    if storage_info["has_compat_token"]:
        console.print("  [green]✓ Compat[/green] legacy mm_session.pickle found")
    else:
        console.print("  [dim]✗ Compat[/dim] no legacy session")

    console.print()
    console.print("[bold]Active Backend:[/bold]")
    if storage_info["active_backend"]:
        console.print(f"  [green]{storage_info['active_backend']}[/green]")
    else:
        console.print("  [yellow]None - not authenticated[/yellow]")

    # API test if authenticated
    console.print()
    console.print("[bold]API Connectivity:[/bold]")
    if storage_info["active_backend"]:
        try:
            client = get_authenticated_client()
            accounts_data = run_async(client.get_accounts())
            accounts = accounts_data.get("accounts", [])
            console.print(f"  [green]✓ Connected[/green] ({len(accounts)} accounts)")
        except AuthenticationError:
            console.print("  [yellow]✗ Not authenticated[/yellow]")
        except Exception as e:
            console.print(f"  [red]✗ API error: {e}[/red]")
    else:
        console.print("  [dim]Skipped - not authenticated[/dim]")


@app.command()
@handle_errors
def ping(
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON (for scripts and AI agents)",
        ),
    ] = False,
) -> None:
    """Test API connectivity.

    Makes a simple API call to verify authentication is working.
    Requires being logged in first.

    Examples:
        monarch auth ping                # Human-readable output
        monarch auth ping --json         # JSON output for scripts
    """
    client = get_authenticated_client()

    try:
        accounts_data = run_async(client.get_accounts())
        accounts = accounts_data.get("accounts", [])
        account_count = len(accounts)

        if json_output:
            result = {
                "status": "ok",
                "message": f"Connected successfully. {account_count} accounts available.",
            }
            output(result, OutputFormat.JSON)
        else:
            # Human-readable output
            console.print("[green]✓ Connected[/green]")
            console.print(f"  Accounts: {account_count}")
    except Exception as e:
        raise APIError(f"API request failed: {e}") from e


@app.command()
def setup() -> None:
    """Show setup instructions.

    Displays detailed instructions for setting up authentication,
    including storage options, security considerations, and troubleshooting tips.

    Examples:
        monarch auth setup
    """
    console.print("[bold]Monarch CLI Setup Instructions[/bold]")
    console.print()

    console.print("[bold]Quick Start:[/bold]")
    console.print("  1. Run: [cyan]monarch auth login[/cyan]")
    console.print("  2. Enter your Monarch Money email and password")
    console.print("  3. If prompted, enter your MFA code")
    console.print("  4. Choose a storage backend")
    console.print()

    console.print("[bold]Storage Options:[/bold]")
    console.print()
    console.print("  [green]keyring[/green] (recommended)")
    console.print("    Uses your OS secure credential storage (macOS Keychain,")
    console.print("    Windows Credential Manager, Linux Secret Service)")
    console.print()
    console.print("  [yellow]file[/yellow]")
    console.print(f"    Stores token in: {get_session_path()}")
    console.print("    File has 0600 permissions (owner read/write only)")
    console.print()
    console.print("  [dim]MONARCH_TOKEN[/dim] (environment variable)")
    console.print("    Set this env var to skip storage entirely")
    console.print("    Useful for CI/CD or containerized environments")
    console.print()

    console.print("[bold]Security Considerations:[/bold]")
    console.print()
    console.print("  [green]🔒 Keyring (Most Secure)[/green]")
    console.print("    • Token encrypted by OS-level security (Keychain, DPAPI, libsecret)")
    console.print("    • Protected by your user account/login password")
    console.print("    • Not accessible to other users or processes without privileges")
    console.print("    • Best for: Personal workstations, developer machines")
    console.print()
    console.print("  [yellow]📁 File Storage (Moderate Security)[/yellow]")
    console.print("    • Token stored in plaintext JSON file")
    console.print("    • Protected by filesystem permissions (0600)")
    console.print("    • Accessible to root/admin and your user account")
    console.print("    • Best for: Headless servers, VMs where keyring unavailable")
    console.print()
    console.print("  [red]⚠️  MONARCH_TOKEN Environment Variable (Use with Caution)[/red]")
    console.print("    Environment variables have inherent security risks:")
    console.print("    • Visible in process listings (ps aux, /proc/*/environ)")
    console.print("    • May be logged by shells, process managers, or monitoring tools")
    console.print("    • Inherited by child processes (risk of leaking to subprocesses)")
    console.print("    • Can appear in crash dumps or debug logs")
    console.print()
    console.print("    [bold]Only use MONARCH_TOKEN when:[/bold]")
    console.print("    • Running in CI/CD with proper secret injection")
    console.print("    • Running in containers with secrets management")
    console.print("    • You understand and accept the risks")
    console.print()

    console.print("[bold]CI/CD Secret Injection (Recommended):[/bold]")
    console.print()
    console.print("  [cyan]GitHub Actions:[/cyan]")
    console.print("    1. Add MONARCH_TOKEN to repository secrets")
    console.print("    2. Reference in workflow:")
    console.print("       env:")
    console.print("         MONARCH_TOKEN: ${{ secrets.MONARCH_TOKEN }}")
    console.print()
    console.print("  [cyan]GitLab CI:[/cyan]")
    console.print("    1. Add MONARCH_TOKEN as CI/CD variable (masked, protected)")
    console.print("    2. Variable is automatically available in jobs")
    console.print()
    console.print("  [cyan]Docker / Containers:[/cyan]")
    console.print("    Avoid baking tokens into images. Instead:")
    console.print("    • Pass at runtime: docker run -e MONARCH_TOKEN=... image")
    console.print("    • Use secrets managers (Docker Secrets, Vault, AWS SSM)")
    console.print("    • Mount secrets as files: docker run -v /secrets:/secrets image")
    console.print()

    console.print("[bold]Troubleshooting:[/bold]")
    console.print("  • Run [cyan]monarch auth doctor[/cyan] to diagnose issues")
    console.print("  • Run [cyan]monarch auth status[/cyan] to check auth state")
    console.print("  • Run [cyan]monarch auth logout[/cyan] to start fresh")
    console.print()

    console.print("[bold]More Help:[/bold]")
    console.print("  • GitHub: https://github.com/monarch-money/monarch-cli")
    console.print("  • Monarch: https://www.monarchmoney.com")
