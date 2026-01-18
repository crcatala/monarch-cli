---
id: mc-ff18
status: open
deps: [mc-3f7c, mc-8d99]
links: []
created: 2026-01-18T16:05:58Z
type: task
priority: 0
assignee: cc-vps
parent: mc-beee
tags: [phase-3, commands, budgets]
---
# Budget Commands

Implement budget CLI command: list.

## Location
`src/monarch_cli/commands/budgets.py`

## Command

### `monarch budgets list`
Get budget status with spent/remaining amounts.

```python
@app.command("list")
@handle_errors
def list_budgets(
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format", "-f")
):
    """Get budget status with spent/remaining amounts."""
    with spinner("Fetching budgets..."):
        client = get_authenticated_client()
        budgets = run_async(client.get_budgets())

    # Simple inline transformation (no separate transformer needed)
    result = []
    for budget in budgets.get("budgetData", {}).get("budgetItems", []):
        result.append({
            "id": budget.get("id"),
            "category": budget.get("category", {}).get("name"),
            "budgeted": budget.get("budgetAmount"),
            "spent": abs(budget.get("spentAmount", 0)),  # Abs for readability
            "remaining": budget.get("remainingAmount"),
        })

    output(result, format)
```

## Output Schema
| Field | Type | Description |
|-------|------|-------------|
| id | string | Budget item ID |
| category | string | Category name |
| budgeted | float | Budget amount |
| spent | float | Amount spent (positive) |
| remaining | float | Remaining budget |

## Why Inline Transformation?
Budget transformation is simple enough to not need a separate transformer file. The transform logic is:
1. Extract budgetItems from response
2. Flatten nested category name
3. Make spent amount positive for readability

## CLI Examples
```bash
monarch budgets list                     # JSON output
monarch budgets list -f table            # Table output
monarch budgets list | jq '[.[] | select(.remaining < 0)]'  # Over budget

# Calculate total budget status
monarch budgets list | jq '{
    total_budgeted: map(.budgeted) | add,
    total_spent: map(.spent) | add,
    total_remaining: map(.remaining) | add
}'
```

## Note on Budget Period
The get_budgets() API returns the current month's budget by default. Period selection can be added in v1.1 if needed.

## Acceptance Criteria

- [ ] `budgets list` returns budget items
- [ ] Output includes id, category, budgeted, spent, remaining
- [ ] Spent amount is positive (absolute value)
- [ ] All output formats work
- [ ] Spinner shown during fetch
- [ ] Help text includes examples
- [ ] Live test: real budget data returned

