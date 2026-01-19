---
id: mc-da1f
status: closed
deps: []
links: []
created: 2026-01-18T19:15:00Z
type: task
priority: 1
assignee: cc-vps
parent: mc-beee
tags: [phase-3, security, auth, docs]
---
# MONARCH_TOKEN Security Documentation

Document security tradeoffs for the `MONARCH_TOKEN` environment variable in the `monarch auth setup` command.

## Background

Per CLI best practices (clig.dev), secrets via environment variables are a "documented risk" because:
- Visible in process listings (`ps aux`)
- May be logged by shells or process managers
- Can leak into child processes

The CLI currently supports `MONARCH_TOKEN` for CI/CD scenarios, but users should understand the tradeoffs.

## Location
`src/monarch_cli/commands/auth.py` - `setup()` command

## Implementation

Update the `setup()` command to include security guidance:

```python
@app.command()
def setup() -> None:
    """Show setup instructions."""
    # ... existing content ...
    
    console.print("[bold]Security Considerations:[/bold]")
    console.print()
    console.print("  [green]keyring[/green] (most secure)")
    console.print("    Token is encrypted by your OS credential manager.")
    console.print("    Best for: Local development, personal machines.")
    console.print()
    console.print("  [yellow]file[/yellow] (moderate)")
    console.print("    Token stored with 0600 permissions (owner read/write only).")
    console.print("    Best for: Single-user servers, containers with mounted secrets.")
    console.print()
    console.print("  [red]MONARCH_TOKEN env var[/red] (use with caution)")
    console.print("    ⚠️  Environment variables can be visible in:")
    console.print("       • Process listings (ps aux)")
    console.print("       • Shell history if set inline")
    console.print("       • Container orchestration logs")
    console.print()
    console.print("    Best for: CI/CD pipelines with secret injection")
    console.print("    Recommended: Use your CI's secret management:")
    console.print("       • GitHub Actions: ${{ secrets.MONARCH_TOKEN }}")
    console.print("       • GitLab CI: $MONARCH_TOKEN (masked variable)")
    console.print("       • Docker: --env-file or secrets mount")
    console.print()
    console.print("  [bold]Alternative for automation:[/bold]")
    console.print("    Consider using --token-file (reads from file) in future versions.")
    console.print()
```

## CLI Examples in Help Text

```bash
# Secure: keyring (interactive)
monarch auth login

# Moderate: file storage
monarch auth login -s file

# CI/CD: inject via secret manager
# GitHub Actions example:
#   env:
#     MONARCH_TOKEN: ${{ secrets.MONARCH_TOKEN }}
#   run: monarch accounts list
```

## Acceptance Criteria

- [ ] `monarch auth setup` shows Security Considerations section
- [ ] Documents keyring as most secure option
- [ ] Documents file storage as moderate security
- [ ] Documents MONARCH_TOKEN risks explicitly
- [ ] Provides guidance for CI/CD secret injection
- [ ] Mentions GitHub Actions, GitLab CI, Docker patterns

## Notes

**2026-01-19T01:04:52Z**

Verified complete: auth.py setup command includes full security guidance
