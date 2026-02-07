# Specifications

This directory contains detailed technical specifications for tasktree-manager features.

## Spec Format

Each spec follows the OpenSpec format with these sections:

- **Metadata**: Status, version, owner, dates
- **Overview**: Brief description
- **Requirements**: Functional and non-functional requirements
- **User Stories**: User-focused scenarios
- **API**: Function signatures and interfaces
- **Implementation**: Technical details and algorithms
- **Testing**: Test cases and coverage
- **Migration**: Upgrade/compatibility notes
- **Future Enhancements**: Planned improvements
- **Open Questions**: Unresolved design decisions
- **Acceptance Criteria**: Definition of done
- **References**: Related docs and code

## Status Labels

- 🟦 **Draft**: Under review, not implemented
- 🟨 **In Progress**: Currently being implemented
- ✅ **Implemented**: Complete and in production
- 🟥 **Deprecated**: No longer supported
- ⏸️ **Paused**: Implementation halted

## Spec Index

| ID | Title | Status | Version |
|----|-------|--------|---------|
| [SPEC-001](./SPEC-001-task-management.md) | Task Management | ✅ Implemented | 0.1.0 |
| [SPEC-002](./SPEC-002-theme-system.md) | Theme System | ✅ Implemented | 0.1.0 |
| SPEC-003 | Git Operations | 🟦 Draft | - |
| SPEC-004 | Configuration System | 🟦 Draft | - |
| SPEC-005 | Keyboard Navigation | 🟦 Draft | - |

## Creating a New Spec

1. Copy template (create from existing spec)
2. Assign next sequential number
3. Fill in all sections
4. Submit for review
5. Update index table above
6. Link from relevant PRD/OpenSpec sections

## Spec Lifecycle

```
Draft → Review → Approved → In Progress → Implemented → Live
                     ↓
                 Rejected
```

## Review Process

1. Author creates spec PR
2. Team reviews (technical feasibility, UX, completeness)
3. Revisions made based on feedback
4. Approval = merge to main
5. Implementation tracked via spec status updates

## Best Practices

### Writing Specs

- **Be specific**: Include examples, not just descriptions
- **Be testable**: Include clear acceptance criteria
- **Be realistic**: Consider constraints and trade-offs
- **Be complete**: Cover errors, edge cases, performance
- **Be visual**: Use diagrams, tables, code snippets

### Updating Specs

- Update spec as implementation evolves
- Document deviations from original design
- Keep status current
- Link to related issues/PRs

### Referencing Specs

From code:
```python
# See SPEC-001 for task creation algorithm
def create_task(name: str, repos: list[str]) -> Task:
    ...
```

From docs:
```markdown
Task management is specified in [SPEC-001](./specs/SPEC-001-task-management.md).
```

## Questions?

- Review [OpenSpec documentation](../OPENSPEC.md)
- Ask in GitHub Discussions
- Ping @ruslan for guidance
