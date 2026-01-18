---
id: mc-f84a
status: open
deps: [mc-fb38, mc-c165]
links: []
created: 2026-01-18T16:09:05Z
type: task
priority: 1
assignee: cc-vps
parent: mc-1568
tags: [phase-5, testing, cli]
---
# CLI Tests with CliRunner

Implement CLI-level tests using Typer's CliRunner.

## Test Locations
```
tests/
├── test_auth_cli.py
├── test_accounts_cli.py
├── test_transactions_cli.py
├── test_budgets_cli.py
├── test_cashflow_cli.py
└── test_categories_cli.py
```

## Testing Pattern
```python
from typer.testing import CliRunner
from unittest.mock import patch, AsyncMock

from monarch_cli.main import app

runner = CliRunner()


class TestAccountsCLI:

    def test_list_returns_json(self):
        mock_accounts = [{"id": "ACC1", "name": "Checking"}]
        
        with patch("monarch_cli.services.accounts.list_accounts") as mock:
            mock.return_value = mock_accounts
            result = runner.invoke(app, ["accounts", "list"])
        
        assert result.exit_code == 0
        assert json.loads(result.stdout) == mock_accounts

    def test_list_table_format(self):
        with patch("monarch_cli.services.accounts.list_accounts") as mock:
            mock.return_value = [{"id": "ACC1", "name": "Checking"}]
            result = runner.invoke(app, ["accounts", "list", "-f", "table"])
        
        assert result.exit_code == 0
        assert "Checking" in result.stdout

    def test_list_requires_auth(self):
        with patch("monarch_cli.services.accounts.list_accounts") as mock:
            from monarch_cli.core.exceptions import AuthenticationError
            mock.side_effect = AuthenticationError()
            
            result = runner.invoke(app, ["accounts", "list"])
        
        assert result.exit_code == 1
        assert "AUTH_REQUIRED" in result.stdout or "not authenticated" in result.stdout.lower()
```

## Tests to Implement

### test_auth_cli.py
- test_login_shows_prompts (can't fully test interactive)
- test_status_when_authenticated
- test_status_when_not_authenticated
- test_logout_success
- test_ping_when_authenticated
- test_ping_when_not_authenticated

### test_accounts_cli.py
- test_list_returns_json
- test_list_table_format
- test_list_csv_format
- test_list_requires_auth
- test_refresh_success
- test_refresh_with_account_ids

### test_transactions_cli.py
- test_list_with_defaults
- test_list_with_date_preset
- test_list_with_explicit_dates
- test_list_with_search
- test_update_success
- test_update_dry_run

### test_budgets_cli.py
- test_list_success
- test_list_empty

### test_cashflow_cli.py
- test_summary_default
- test_summary_with_preset
- test_summary_with_dates

### test_categories_cli.py
- test_list_success
- test_list_flattens_groups

## Error Handling Tests
```python
def test_network_error_handling(self):
    with patch(...) as mock:
        mock.side_effect = NetworkError("Connection failed")
        result = runner.invoke(app, ["accounts", "list"])
    
    assert result.exit_code == 1
    assert "NETWORK_ERROR" in result.stdout
```

## Mocking Guidelines
- Mock at service/client level, not deep in implementation
- Use `patch()` with full module path
- Return realistic mock data matching API structure
- Test both success and error paths

## Acceptance Criteria

- [ ] test_auth_cli.py tests auth commands
- [ ] test_accounts_cli.py tests account commands
- [ ] test_transactions_cli.py tests transaction commands
- [ ] test_budgets_cli.py tests budget commands
- [ ] test_cashflow_cli.py tests cashflow commands
- [ ] test_categories_cli.py tests category commands
- [ ] Error handling tested for each command
- [ ] All output formats tested
- [ ] Exit codes verified

