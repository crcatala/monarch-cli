# Phase 5 Quality Guardrails

## Testing Standards

### Test File Naming
- `test_<module>.py` for unit tests
- `test_<feature>_cli.py` for CLI tests
- `tests/live/` for live API tests

### Test Coverage Goals
- Core modules: >80%
- Transformers: 100% (pure functions)
- Commands: >70% (mock external calls)

### What NOT to Test
- Don't test the monarchmoney library itself
- Don't test typer framework behavior
- Don't test Rich rendering details

## Live Tests Rules

1. **Never in CI**: Live tests require real credentials
2. **Skip by default**: Use `@pytest.mark.live` and env check
3. **No assertions on user data**: Don't assert specific account names/balances
4. **Only verify structure**: Assert fields exist, types are correct

```python
@pytest.mark.skipif(not LIVE_ENABLED, reason="Live tests disabled")
def test_accounts_have_expected_structure():
    accounts = fetch_accounts()
    assert "accounts" in accounts
    assert isinstance(accounts["accounts"], list)
```

## Documentation Standards

### README Checklist
- [ ] Badges (PyPI, CI, coverage)
- [ ] One-sentence description
- [ ] Installation for pip, uv, pipx
- [ ] Quick start with copy-paste commands
- [ ] All commands documented with examples
- [ ] Environment variables table
- [ ] Troubleshooting section

### Docstring Style
```python
def function(arg: str) -> dict:
    """One-line description.
    
    Longer description if needed.
    
    Args:
        arg: Description of argument.
        
    Returns:
        Description of return value.
        
    Examples:
        >>> function("test")
        {"result": "test"}
    """
```

## Pre-Release Checklist

Before tagging release:
1. [ ] All tests pass (`make verify`)
2. [ ] Version bumped in `__init__.py`
3. [ ] CHANGELOG updated
4. [ ] README reviewed
5. [ ] `uv build` succeeds
6. [ ] Test install works

## Reference

- Tickets: `.tickets/mc-fb38.md` through `.tickets/mc-e04c.md`
- pytest docs: https://docs.pytest.org
- Keep a Changelog: https://keepachangelog.com
