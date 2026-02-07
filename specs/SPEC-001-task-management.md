# SPEC-001: Task Management

**Status**: ✅ Implemented
**Version**: 0.1.0
**Owner**: @ruslan
**Created**: 2026-01-22
**Updated**: 2026-01-22

## Overview

Core task management functionality for creating, listing, and deleting tasks.

## Requirements

### Functional

#### FR-1: Create Task
- User can create a named task with one or more repositories
- Task name becomes the branch name for all worktrees
- Base branch is configurable per task
- Task directory is created in `TASKS_DIR`

**Input**:
- Task name (required, alphanumeric + hyphens)
- Repository list (required, 1+)
- Base branch (optional, defaults to "master")

**Output**:
- Task object with worktrees created
- Success/error notification

**Validation**:
- Task name must be unique
- Repositories must exist in `REPOS_DIR`
- Base branch must exist in repositories

#### FR-2: List Tasks
- Display all tasks in left panel
- Show dirty indicator for tasks with uncommitted changes
- Show dirty count in parentheses
- Auto-select first task on load

**Display Format**:
```
● task-name (2)  # dirty with 2 dirty worktrees
  task-name-2    # clean
```

#### FR-3: Delete Task
- User can delete selected task
- Confirmation modal shows warning if dirty
- All worktrees are removed via git
- Task directory is deleted

**Confirmation Message**:
```
Delete task 'task-name' and all its worktrees?

WARNING: 2 worktree(s) have uncommitted changes!
```

### Non-Functional

#### NFR-1: Performance
- Create task: < 5s for 5 repos
- List tasks: < 200ms for 100 tasks
- Delete task: < 3s for 5 worktrees

#### NFR-2: Safety
- Confirmation required for destructive operations
- Warning shown for dirty worktrees
- No data loss on error

## User Stories

### US-1: Create Task
```
As a developer
I want to create a task for my feature work
So that I can organize worktrees across multiple repos

Given I have repos in ~/repos
When I press 'n' and fill in task details
Then worktrees are created with the task branch name
```

### US-2: View Tasks
```
As a developer
I want to see all my tasks at a glance
So that I can quickly identify which need attention

Given I have multiple tasks
When I open tasktree-manager
Then I see all tasks with dirty indicators
```

### US-3: Delete Task
```
As a developer
I want to delete completed tasks
So that I can keep my workspace clean

Given I have a completed task
When I press 'd' and confirm
Then all worktrees are removed and the task disappears
```

## API

### TaskManager

```python
def create_task(
    name: str,
    repos: list[str],
    base_branch: str = "master"
) -> Task:
    """Create a new task with worktrees.

    Args:
        name: Unique task name (used as branch name)
        repos: List of repository names from REPOS_DIR
        base_branch: Branch to branch from

    Returns:
        Created Task object

    Raises:
        ValueError: If task exists or repos invalid
        subprocess.CalledProcessError: If git fails
    """
```

```python
def list_tasks() -> list[Task]:
    """List all tasks.

    Returns:
        List of Task objects sorted by name
    """
```

```python
def finish_task(task: Task) -> None:
    """Delete task and all worktrees.

    Args:
        task: Task to delete

    Raises:
        subprocess.CalledProcessError: If git fails
        OSError: If directory deletion fails
    """
```

## Implementation

### Create Task Flow

```
1. Validate input
   - Check task name unique
   - Check repos exist
   - Check base branch exists (future)

2. Create task directory
   mkdir -p {TASKS_DIR}/{task_name}

3. For each repo:
   cd {REPOS_DIR}/{repo}
   git worktree add {TASKS_DIR}/{task_name}/{repo} -b {task_name} {base_branch}

4. Create Task object
   - Scan worktree directories
   - Create Worktree objects
   - Return Task

5. Handle errors
   - Clean up partial worktrees on failure
   - Show error notification
```

### List Tasks Flow

```
1. Scan TASKS_DIR
   for dir in TASKS_DIR:
       if dir.is_dir():
           tasks.append(load_task(dir))

2. Load each task
   - Scan subdirectories for worktrees
   - Create Worktree objects
   - Get git status for each

3. Sort by name

4. Return list
```

### Delete Task Flow

```
1. Show confirmation modal

2. If confirmed:
   For each worktree:
       cd {repo_origin}
       git worktree remove {worktree_path}

3. Delete task directory
   rm -rf {TASKS_DIR}/{task_name}

4. Refresh task list
```

## Testing

### Unit Tests

```python
def test_create_task(task_manager, sample_repos):
    """Test creating a task with multiple repos."""
    task = task_manager.create_task("test-task", ["repo1", "repo2"])
    assert task.name == "test-task"
    assert len(task.worktrees) == 2

def test_list_tasks_empty(task_manager):
    """Test listing tasks when none exist."""
    tasks = task_manager.list_tasks()
    assert len(tasks) == 0

def test_finish_task(task_manager, sample_task):
    """Test deleting a task."""
    task_manager.finish_task(sample_task)
    assert not sample_task.path.exists()
```

### Integration Tests

```python
async def test_create_task_workflow(pilot):
    """Test full task creation workflow."""
    await pilot.press("n")
    await pilot.pause()
    # Fill in modal fields
    # Press create
    # Verify task appears in list
```

## Error Handling

| Error | Handling |
|-------|----------|
| Task exists | Show error notification, keep modal open |
| Repo doesn't exist | Show error, keep modal open |
| Git worktree fails | Clean up partial work, show error |
| Permission denied | Show error with details |
| Disk full | Show error, clean up |

## Migration

N/A (initial feature)

## Open Questions

1. ✅ Should we validate base branch exists? → Yes, in v0.2
2. ✅ What if worktree creation partially fails? → Clean up all
3. ✅ Should task names be case-sensitive? → Yes
4. ❓ Should we support spaces in task names? → TBD

## Acceptance Criteria

- [x] Can create task with valid inputs
- [x] Can list all tasks
- [x] Can delete task with confirmation
- [x] Dirty indicators show correctly
- [x] Errors are handled gracefully
- [x] Test coverage > 80%

## References

- [PRD](../PRD.md)
- [OpenSpec](../OPENSPEC.md)
- Implementation: `tasktree_manager/services/task_manager.py`
