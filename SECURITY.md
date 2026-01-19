# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public issue.

Instead, please email crcatala@gmail.com with:

- Description of the vulnerability
- Steps to reproduce
- Potential impact

We will respond within 48 hours and work with you to address the issue.

## Security Considerations

### Credential Storage

Monarch CLI stores session tokens (not passwords) using:

1. **System keyring** (preferred) - OS-level secure storage
2. **File storage** - `~/.config/monarch-cli/session.json` with 600 permissions

### What We Don't Store

- Passwords are never stored after authentication
- No financial data is cached locally
- Session tokens are the only persisted credential

### Environment Variables

The `MONARCH_TOKEN` environment variable can be used for automation.
**Caution:** Do not expose this in logs, scripts committed to repos, or CI outputs.
