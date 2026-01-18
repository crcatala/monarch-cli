# Phase 4 AI Agent Guardrails

## Quiet Mode Design

Quiet mode is for machine consumption:
- One value per line
- No headers, no formatting
- No colors, no spinners
- Just the data

```python
if quiet:
    # Skip spinner entirely
    result = fetch_data()
    for item in result:
        print(item["id"])
    return
```

## Batch Operation Safety

1. **Always support --dry-run**: Users should preview before bulk changes

2. **Report failures clearly**: Don't silently skip failures
   ```python
   {"success_count": 8, "failure_count": 2, "failures": [{"id": "TXN1", "error": "..."}]}
   ```

3. **Respect rate limits**: Use concurrency control (semaphore)
   ```python
   semaphore = asyncio.Semaphore(max_concurrency)
   ```

4. **Graceful degradation**: If one update fails, continue with others

## Stdin Reading Pattern

```python
if stdin:
    import sys
    for line in sys.stdin:
        line = line.strip()
        if line:  # Skip empty lines
            ids.append(line)
```

## Testing Batch Operations

```bash
# Create test file
echo -e "TXN001\nTXN002\nTXN003" > /tmp/ids.txt

# Dry run
monarch transactions batch-update --stdin --category CAT123 --dry-run < /tmp/ids.txt

# Actual run (careful!)
monarch transactions batch-update --stdin --category CAT123 < /tmp/ids.txt
```

## Reference

- Tickets: `.tickets/mc-804c.md`, `.tickets/mc-6397.md`
