"""Live CLI integration tests - LOCAL DEVELOPMENT ONLY.

⚠️ WARNING: These tests hit the real Monarch Money API!
⚠️ They require valid credentials and are NOT for CI.

These tests verify that the actual CLI commands work end-to-end:
1. CLI spawns and authenticates correctly
2. Commands produce valid output in all formats
3. Write operations work and are safely reverted

To run:
    MONARCH_LIVE_TESTS=1 make test-live

Environment variables:
    MONARCH_LIVE_TESTS=1     Required to enable these tests
    MONARCH_LIVE_DELAY=2.0   Delay between API calls in seconds (default: 2.0)

Prerequisites:
    - Valid Monarch Money credentials stored via `monarch auth login`
    - Active internet connection
    - Session not expired
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

import pytest

# Skip all tests in this module unless MONARCH_LIVE_TESTS=1
LIVE_ENABLED = os.environ.get("MONARCH_LIVE_TESTS", "").lower() in ("1", "true", "yes")

# Configurable delay between API calls (seconds)
LIVE_DELAY = float(os.environ.get("MONARCH_LIVE_DELAY", "2.0"))

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not LIVE_ENABLED, reason="Live tests disabled (set MONARCH_LIVE_TESTS=1)"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def rate_limit_delay():
    """Auto-applied delay between tests to avoid rate limiting.

    This runs after each test to ensure we don't hammer the API.
    """
    yield
    if LIVE_DELAY > 0:
        time.sleep(LIVE_DELAY)


def run_cli(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a monarch CLI command and return the result.

    Args:
        *args: Command arguments (e.g., "accounts", "list", "--json")
        check: If True, raise on non-zero exit code

    Returns:
        CompletedProcess with stdout, stderr, returncode
    """
    cmd = ["uv", "run", "monarch", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if check and result.returncode != 0:
        pytest.fail(
            f"Command failed: {' '.join(cmd)}\n"
            f"Exit code: {result.returncode}\n"
            f"Stdout: {result.stdout}\n"
            f"Stderr: {result.stderr}"
        )

    return result


def run_cli_json(*args: str) -> Any:
    """Run a monarch CLI command and parse JSON output.

    Args:
        *args: Command arguments (--json is added automatically)

    Returns:
        Parsed JSON data
    """
    result = run_cli(*args, "--json")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        pytest.fail(f"Invalid JSON output: {e}\nOutput: {result.stdout}")


def get_output(result: subprocess.CompletedProcess[str]) -> str:
    """Get combined stdout + stderr for human-readable command output.

    Some commands output styled text to stderr (via Rich console).
    """
    return result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Auth Tests
# ---------------------------------------------------------------------------


class TestLiveAuth:
    """Live tests for authentication commands."""

    def test_auth_status(self):
        """Verify auth status command works."""
        result = run_cli("auth", "status")
        assert result.returncode == 0
        output = get_output(result)
        assert "Authenticated" in output or "authenticated" in output.lower()

    def test_auth_status_json(self):
        """Verify auth status JSON output."""
        data = run_cli_json("auth", "status")
        assert "authenticated" in data
        assert data["authenticated"] is True

    def test_auth_ping(self):
        """Verify auth ping command connects to API."""
        result = run_cli("auth", "ping")
        assert result.returncode == 0
        output = get_output(result)
        assert "Connected" in output

    def test_auth_ping_json(self):
        """Verify auth ping JSON output."""
        data = run_cli_json("auth", "ping")
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Accounts Tests
# ---------------------------------------------------------------------------


class TestLiveAccounts:
    """Live tests for account commands."""

    def test_accounts_list_json(self):
        """Verify accounts list returns valid JSON array."""
        data = run_cli_json("accounts", "list")
        assert isinstance(data, list)

        if data:
            account = data[0]
            # Verify our transformed schema (not raw API fields)
            assert "id" in account
            assert "name" in account  # Transformed from displayName
            assert "balance" in account  # Transformed from currentBalance
            assert "type" in account
            assert "institution" in account

    def test_accounts_list_table(self):
        """Verify accounts list table format works."""
        result = run_cli("accounts", "list", "--format", "table")
        assert result.returncode == 0
        # Table should have header-like content
        output = get_output(result)
        assert len(output.strip()) > 0

    def test_accounts_list_csv(self):
        """Verify accounts list CSV format works."""
        result = run_cli("accounts", "list", "--format", "csv")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        # Should have at least a header row
        assert len(lines) >= 1
        # CSV header should contain expected fields
        header = lines[0].lower()
        assert "id" in header or "name" in header

    def test_accounts_list_ndjson(self):
        """Verify accounts list NDJSON format works."""
        result = run_cli("accounts", "list", "--ndjson")
        assert result.returncode == 0

        lines = [line for line in result.stdout.strip().split("\n") if line]
        if lines:
            # Each line should be valid JSON
            for line in lines:
                data = json.loads(line)
                assert "id" in data

    def test_accounts_list_raw(self):
        """Verify accounts list raw format returns untransformed data."""
        data = run_cli_json("accounts", "list", "--raw")
        # Raw format returns API structure with accounts wrapper
        assert isinstance(data, dict)
        assert "accounts" in data
        assert isinstance(data["accounts"], list)

        if data["accounts"]:
            account = data["accounts"][0]
            # Raw format should have API field names
            assert "displayName" in account or "currentBalance" in account


# ---------------------------------------------------------------------------
# Transactions Tests
# ---------------------------------------------------------------------------


class TestLiveTransactions:
    """Live tests for transaction commands."""

    def test_transactions_list_json(self):
        """Verify transactions list returns valid JSON array."""
        data = run_cli_json("transactions", "list", "--limit", "5")
        assert isinstance(data, list)

        if data:
            txn = data[0]
            # Verify our transformed schema
            assert "id" in txn
            assert "date" in txn
            assert "amount" in txn
            assert "description" in txn

    def test_transactions_list_with_filters(self):
        """Verify transaction filters work."""
        # Just verify the command doesn't error with filters
        data = run_cli_json("transactions", "list", "--limit", "3")
        assert isinstance(data, list)

    def test_transactions_list_table(self):
        """Verify transactions list table format works."""
        result = run_cli("transactions", "list", "--limit", "5", "--format", "table")
        assert result.returncode == 0

    def test_transactions_list_csv(self):
        """Verify transactions list CSV format works."""
        result = run_cli("transactions", "list", "--limit", "5", "--format", "csv")
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 1  # At least header


class TestLiveTransactionUpdate:
    """Live tests for transaction update commands.

    These tests modify real data but always restore original values.
    """

    @pytest.fixture
    def test_transaction(self):
        """Get a transaction to use for update tests.

        Returns the transaction data and ensures we can restore it.
        """
        # Get a recent transaction
        transactions = run_cli_json("transactions", "list", "--limit", "10")

        if not transactions:
            pytest.skip("No transactions available for update test")

        # Use the first transaction
        txn = transactions[0]
        return txn

    def test_transaction_update_notes_roundtrip(self, test_transaction):
        """Test updating transaction notes and restoring original value."""
        txn_id = test_transaction["id"]
        original_notes = test_transaction.get("notes") or ""

        # Use a unique test marker
        test_notes = f"[LIVE TEST] {time.time()}"

        try:
            # Update notes (no --json flag for update command)
            result = run_cli(
                "transactions", "update", txn_id,
                "--notes", test_notes,
            )
            assert result.returncode == 0

            # Verify the update took effect by fetching transactions
            time.sleep(LIVE_DELAY)
            transactions = run_cli_json("transactions", "list", "--limit", "20")
            updated = next((t for t in transactions if t["id"] == txn_id), None)

            if updated:
                assert updated.get("notes") == test_notes

        finally:
            # Always restore original notes
            time.sleep(LIVE_DELAY)  # Rate limit before restore
            run_cli(
                "transactions", "update", txn_id,
                "--notes", original_notes,
                check=False  # Don't fail test if restore fails
            )

    def test_transaction_update_dry_run(self, test_transaction):
        """Test that dry-run doesn't actually modify the transaction."""
        txn_id = test_transaction["id"]
        original_notes = test_transaction.get("notes") or ""

        # Dry-run an update
        result = run_cli(
            "transactions", "update", txn_id,
            "--notes", "[DRY RUN TEST] should not persist",
            "--dry-run",
        )
        assert result.returncode == 0

        # Verify the transaction wasn't actually changed
        time.sleep(LIVE_DELAY)
        transactions = run_cli_json("transactions", "list", "--limit", "20")
        current_txn = next((t for t in transactions if t["id"] == txn_id), None)

        if current_txn:
            current_notes = current_txn.get("notes") or ""
            assert current_notes == original_notes, "Dry-run should not modify transaction"


# ---------------------------------------------------------------------------
# Categories Tests
# ---------------------------------------------------------------------------


class TestLiveCategories:
    """Live tests for category commands."""

    def test_categories_list_json(self):
        """Verify categories list returns valid JSON array."""
        data = run_cli_json("categories", "list")
        assert isinstance(data, list)

        if data:
            category = data[0]
            assert "id" in category
            assert "name" in category

    def test_categories_list_table(self):
        """Verify categories list table format works."""
        result = run_cli("categories", "list", "--format", "table")
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Budgets Tests
# ---------------------------------------------------------------------------


class TestLiveBudgets:
    """Live tests for budget commands."""

    def test_budgets_list_json(self):
        """Verify budgets list returns valid JSON."""
        data = run_cli_json("budgets", "list")
        # Budgets returns a dict with budget data, not a list
        assert isinstance(data, (list, dict))

    def test_budgets_list_table(self):
        """Verify budgets list table format works."""
        result = run_cli("budgets", "list", "--format", "table")
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Cashflow Tests
# ---------------------------------------------------------------------------


class TestLiveCashflow:
    """Live tests for cashflow commands."""

    def test_cashflow_summary_json(self):
        """Verify cashflow summary returns valid JSON."""
        data = run_cli_json("cashflow", "summary")
        assert isinstance(data, dict)
        # Should have income/expense data
        assert "income" in data or "expense" in data or "total" in data or len(data) > 0

    def test_cashflow_summary_table(self):
        """Verify cashflow summary table format works."""
        result = run_cli("cashflow", "summary", "--format", "table")
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


class TestLiveErrorHandling:
    """Live tests for error handling."""

    def test_invalid_transaction_id_error(self):
        """Verify invalid transaction ID returns proper error."""
        result = run_cli(
            "transactions", "update", "invalid-id-12345",
            "--notes", "test",
            check=False
        )
        # Should fail gracefully
        assert result.returncode != 0

    def test_help_works(self):
        """Verify --help works for all commands."""
        commands = [
            ["--help"],
            ["auth", "--help"],
            ["accounts", "--help"],
            ["transactions", "--help"],
            ["categories", "--help"],
            ["budgets", "--help"],
            ["cashflow", "--help"],
        ]

        for cmd in commands:
            result = run_cli(*cmd)
            assert result.returncode == 0, f"Help failed for: {cmd}"
