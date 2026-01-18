# Project Guidelines

## Task Management with `tk`

This project uses the `tk` CLI (ticket system) for task management. Tickets are stored as markdown files with YAML frontmatter in `.tickets/`.

### Common Workflow

```bash
# View available tickets
tk ls                    # List all tickets
tk ready                 # Show tickets ready to work on (deps resolved)
tk blocked               # Show tickets blocked by dependencies

# Working on a ticket
tk show <id>             # View ticket details (supports partial ID match)
tk start <id>            # Mark as in_progress when you begin work
tk add-note <id> "note"  # Add progress notes as you work
tk close <id>            # Mark complete when done

# Creating tickets
tk create "Title" -d "Description" -t feature   # Types: bug|feature|task|epic|chore
tk create "Title" --acceptance "Criteria here"  # With acceptance criteria
tk create "Subtask" --parent <parent-id>        # Create child ticket

# Dependencies
tk dep <id> <dep-id>     # Mark <id> as depending on <dep-id>
tk dep tree <id>         # View dependency tree
tk undep <id> <dep-id>   # Remove dependency
```

### Best Practices for Agents

1. **Before starting work**: Run `tk ready` to find unblocked tickets, or `tk show <id>` if given a specific ticket
2. **When starting**: Use `tk start <id>` to mark the ticket in progress
3. **During work**: Add notes with `tk add-note <id> "progress update"` for significant milestones
4. **On completion**: Use `tk close <id>` after verifying acceptance criteria are met
5. **Commit messages**: Reference ticket IDs in commits (e.g., `nw-5c46: implement feature`)

### Ticket File Format

Tickets are in `.tickets/<id>.md` with YAML frontmatter containing metadata (status, type, priority, dependencies) followed by markdown content (description, design notes, acceptance criteria, notes).

## Autonomous Coding with Ralph Loops

This project uses Ralph, an autonomous task loop runner CLI. Define tasks in a `prd.yaml`, then `ralph run <loop>` executes them sequentially via AI agents until complete. See `ralph guide` or
 `ralph --help`.

Ralph integrates with `tk` - set `issue_tracker: tk` in prd.yaml to auto-close tickets when tasks complete.
