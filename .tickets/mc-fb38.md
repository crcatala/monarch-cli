---
id: mc-fb38
status: open
deps: [mc-6397]
links: []
created: 2026-01-18T16:08:46Z
type: task
priority: 1
assignee: cc-vps
parent: mc-1568
tags: [phase-5, testing, unit]
---
# Unit Tests Structure & Core Tests

Set up unit test structure and implement core module tests.

## Test Locations
```
tests/
├── __init__.py
├── conftest.py           # Shared fixtures
├── test_async_utils.py
├── test_exceptions.py
├── test_dates.py
├── test_config.py
├── test_session.py
├── test_output.py
└── transformers/
    ├── __init__.py
    ├── test_accounts.py
    └── test_transactions.py
```

## Core Module Tests

### test_async_utils.py
```python
def test_run_async_returns_result():
    async def coro():
        return 42
    assert run_async(coro()) == 42

def test_run_async_propagates_exception():
    async def coro():
        raise ValueError("test")
    with pytest.raises(ValueError):
        run_async(coro())
```

### test_exceptions.py
```python
def test_error_to_dict():
    error = AuthenticationError()
    d = error.to_dict()
    assert d["code"] == "AUTH_REQUIRED"
    assert d["error"] is True

def test_error_codes_are_unique():
    # Verify no duplicate error codes
    codes = [e.value for e in ErrorCode]
    assert len(codes) == len(set(codes))
```

### test_dates.py
```python
@pytest.mark.freeze_time("2024-06-15")  # Optional: freeze time for deterministic tests
def test_this_month_preset():
    start, end = resolve_preset(DatePreset.THIS_MONTH)
    assert start == date(2024, 6, 1)
    assert end == date(2024, 6, 15)

def test_all_presets_return_valid_dates():
    for preset in DatePreset:
        start, end = resolve_preset(preset)
        if preset != DatePreset.ALL:
            assert start is not None or end is not None
```

### test_config.py
```python
def test_config_defaults():
    config = Config()
    assert config.format == OutputFormat.JSON
    assert config.timeout_seconds == 30

def test_config_from_env(monkeypatch):
    monkeypatch.setenv("MONARCH_FORMAT", "table")
    config = Config.load()
    assert config.format == OutputFormat.TABLE

def test_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    config = Config.load()
    assert config.color is False
```

### test_output.py
```python
def test_output_json(capsys):
    output([{"id": "1"}], OutputFormat.JSON)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == [{"id": "1"}]

def test_output_compact(capsys):
    output([{"id": "1"}], OutputFormat.COMPACT)
    captured = capsys.readouterr()
    assert "\n" not in captured.out.strip()
```

## Shared Fixtures (conftest.py)
```python
@pytest.fixture
def mock_monarch_client():
    client = AsyncMock()
    client.get_accounts.return_value = {"accounts": []}
    return client

@pytest.fixture
def sample_accounts():
    return {"accounts": [{...}]}
```

## Acceptance Criteria

- [ ] Test directory structure created
- [ ] conftest.py with shared fixtures
- [ ] test_async_utils.py with basic tests
- [ ] test_exceptions.py tests error serialization
- [ ] test_dates.py tests all presets
- [ ] test_config.py tests env loading
- [ ] test_output.py tests formatters
- [ ] All tests pass with `uv run pytest tests/`

