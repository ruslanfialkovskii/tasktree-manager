"""Regression tests for the app.py review fixes (Claude status polling
robustness, delete-safety worker cancellation, the mutation/auto-refresh
race, the fingerprint-on-failure bug, Claude session prep threading, and the
push/pull-vs-mutation guard)."""

import asyncio
import json
import subprocess
import threading
from types import SimpleNamespace

from textual.worker import WorkerCancelled

from tasktree_manager.services.models import TaskSafetyReport
from tasktree_manager.services.task_manager import ArchiveIncompleteError
from tasktree_manager.widgets.create_modal import ConfirmModal, PushResultModal, SafeDeleteModal
from tasktree_manager.widgets.messages_panel import MessagesPanel
from tasktree_manager.widgets.task_list import TaskList
from tasktree_manager.widgets.worktree_list import WorktreeList


def _blocking_stub(
    started: threading.Event, release: threading.Event, done: threading.Event, result
):
    """A stand-in for a slow task_manager/git call: signals `started`,
    blocks until `release`, then signals `done` right before returning.

    `done` is required (rather than relying on app.workers.wait_for_complete)
    because Textual flips a cancelled worker's state to CANCELLED
    immediately while its underlying thread keeps running - waiting on the
    worker state alone can pass a test vacuously, before the thread ever
    reaches the code under test.
    """

    def _call(*args, **kwargs):
        started.set()
        release.wait(timeout=5)
        try:
            return result
        finally:
            done.set()

    return _call


class TestPollClaudeStatusesRobustness:
    """Fix 1: a malformed .claude_status file must be skipped, not crash
    the 5s poll interval."""

    async def test_non_object_json_status_skipped(self, app, task_manager, sample_repo):
        repo_path, branch = sample_repo
        task_manager.create_task("BAD-JSON-TASK", ["sample-repo"], branch)
        task_path = app.config.tasks_dir / "BAD-JSON-TASK"

        async with app.run_test() as pilot:
            await pilot.pause()
            (task_path / ".claude_status").write_text("[]")

            app._poll_claude_statuses()  # must not raise (AttributeError on list.get)
            await pilot.pause()

            assert app.is_running
            assert "BAD-JSON-TASK" not in app._claude_statuses

    async def test_non_utf8_status_file_skipped(self, app, task_manager, sample_repo):
        repo_path, branch = sample_repo
        task_manager.create_task("BINARY-STATUS-TASK", ["sample-repo"], branch)
        task_path = app.config.tasks_dir / "BINARY-STATUS-TASK"

        async with app.run_test() as pilot:
            await pilot.pause()
            (task_path / ".claude_status").write_bytes(b"\xff\xfe\x00\x01")

            app._poll_claude_statuses()  # must not raise (UnicodeDecodeError)
            await pilot.pause()

            assert app.is_running
            assert "BINARY-STATUS-TASK" not in app._claude_statuses

    async def test_valid_status_still_applied(self, app, task_manager, sample_repo):
        """Sanity check alongside the malformed-input cases above."""
        repo_path, branch = sample_repo
        task_manager.create_task("GOOD-STATUS-TASK", ["sample-repo"], branch)
        task_path = app.config.tasks_dir / "GOOD-STATUS-TASK"

        async with app.run_test() as pilot:
            await pilot.pause()
            (task_path / ".claude_status").write_text(json.dumps({"status": "working"}))

            app._poll_claude_statuses()
            await pilot.pause()

            assert app._claude_statuses.get("GOOD-STATUS-TASK") == "working"


class TestSafetyCheckCancellation:
    """Fix 2: the four delete-safety workers (group "safety_check") must not
    show a dialog for a result computed after they were cancelled."""

    async def test_check_task_safety_worker_skips_cancelled_dialog(
        self, app, task_manager, sample_repo
    ):
        repo_path, branch = sample_repo
        task = task_manager.create_task("CANCEL-TASK-SAFETY", ["sample-repo"], branch)
        started, release, done = threading.Event(), threading.Event(), threading.Event()

        async with app.run_test() as pilot:
            await pilot.pause()
            app.task_manager.check_task_safety = _blocking_stub(
                started, release, done, TaskSafetyReport()
            )
            app._check_task_safety_worker(task)
            await asyncio.get_running_loop().run_in_executor(None, started.wait, 5)

            app.workers.cancel_group(app, "safety_check")
            release.set()
            await asyncio.get_running_loop().run_in_executor(None, done.wait, 5)
            await pilot.pause()
            await pilot.pause()

            confirm_modals = [s for s in app.screen_stack if isinstance(s, ConfirmModal)]
            safe_modals = [s for s in app.screen_stack if isinstance(s, SafeDeleteModal)]
            assert not confirm_modals and not safe_modals

    async def test_check_worktree_safety_worker_skips_cancelled_dialog(
        self, app, task_manager, sample_repo
    ):
        repo_path, branch = sample_repo
        task = task_manager.create_task("CANCEL-WT-SAFETY", ["sample-repo"], branch)
        worktree = task.worktrees[0]
        started, release, done = threading.Event(), threading.Event(), threading.Event()

        async with app.run_test() as pilot:
            await pilot.pause()
            app.task_manager.check_task_safety = _blocking_stub(
                started, release, done, TaskSafetyReport()
            )
            app._check_worktree_safety_worker(task, worktree)
            await asyncio.get_running_loop().run_in_executor(None, started.wait, 5)

            app.workers.cancel_group(app, "safety_check")
            release.set()
            await asyncio.get_running_loop().run_in_executor(None, done.wait, 5)
            await pilot.pause()
            await pilot.pause()

            confirm_modals = [s for s in app.screen_stack if isinstance(s, ConfirmModal)]
            safe_modals = [s for s in app.screen_stack if isinstance(s, SafeDeleteModal)]
            assert not confirm_modals and not safe_modals

    async def test_push_branches_for_delete_worker_skips_cancelled_dialog(
        self, app, task_manager, sample_repo
    ):
        repo_path, branch = sample_repo
        task = task_manager.create_task("CANCEL-PUSH-SAFETY", ["sample-repo"], branch)
        started, release, done = threading.Event(), threading.Event(), threading.Event()

        async with app.run_test() as pilot:
            await pilot.pause()
            app.task_manager.push_all_branches = _blocking_stub(started, release, done, ([], []))
            app.task_manager.check_task_safety = lambda t: TaskSafetyReport()
            app._push_branches_for_delete_worker(task)
            await asyncio.get_running_loop().run_in_executor(None, started.wait, 5)

            app.workers.cancel_group(app, "safety_check")
            release.set()
            await asyncio.get_running_loop().run_in_executor(None, done.wait, 5)
            await pilot.pause()
            await pilot.pause()

            confirm_modals = [s for s in app.screen_stack if isinstance(s, ConfirmModal)]
            safe_modals = [s for s in app.screen_stack if isinstance(s, SafeDeleteModal)]
            push_modals = [s for s in app.screen_stack if isinstance(s, PushResultModal)]
            assert not confirm_modals and not safe_modals and not push_modals

    async def test_push_worktree_for_delete_worker_skips_cancelled_dialog(
        self, app, task_manager, sample_repo
    ):
        repo_path, branch = sample_repo
        task = task_manager.create_task("CANCEL-WT-PUSH-SAFETY", ["sample-repo"], branch)
        worktree = task.worktrees[0]
        started, release, done = threading.Event(), threading.Event(), threading.Event()

        async with app.run_test() as pilot:
            await pilot.pause()
            app.task_manager.push_all_branches = _blocking_stub(started, release, done, ([], []))
            app.task_manager.check_task_safety = lambda t: TaskSafetyReport()
            app._push_worktree_for_delete_worker(task, worktree)
            await asyncio.get_running_loop().run_in_executor(None, started.wait, 5)

            app.workers.cancel_group(app, "safety_check")
            release.set()
            await asyncio.get_running_loop().run_in_executor(None, done.wait, 5)
            await pilot.pause()
            await pilot.pause()

            confirm_modals = [s for s in app.screen_stack if isinstance(s, ConfirmModal)]
            safe_modals = [s for s in app.screen_stack if isinstance(s, SafeDeleteModal)]
            push_modals = [s for s in app.screen_stack if isinstance(s, PushResultModal)]
            assert not confirm_modals and not safe_modals and not push_modals


class TestMutationAutoRefreshRace:
    """Fix 3: _begin_mutation must cancel an in-flight periodic scan, and
    _apply_refreshed_tasks must discard a stale scan's results while a
    mutation is in flight even if cancellation didn't land in time."""

    async def test_begin_mutation_cancels_in_flight_auto_refresh(
        self, app, task_manager, sample_repo
    ):
        repo_path, branch = sample_repo
        task_manager.create_task("SCAN-RACE", ["sample-repo"], branch)
        started, release = threading.Event(), threading.Event()

        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()  # let startup's own scan finish

            def blocking_list_tasks():
                started.set()
                release.wait(timeout=5)
                return []

            app.task_manager.list_tasks = blocking_list_tasks
            app._run_periodic_refresh()
            await asyncio.get_running_loop().run_in_executor(None, started.wait, 5)

            scan_workers = [w for w in app.workers if w.group == "auto_refresh"]
            assert scan_workers and not scan_workers[0].is_cancelled

            assert app._begin_mutation("task-list")
            assert scan_workers[0].is_cancelled

            release.set()
            try:
                await app.workers.wait_for_complete()
            except WorkerCancelled:
                pass  # expected: this worker was deliberately cancelled
            await pilot.pause()

    async def test_apply_refreshed_tasks_discards_stale_scan_during_mutation(
        self, app, task_manager, sample_repo
    ):
        """Belt-and-suspenders: even a scan callback whose worker wasn't
        cancelled in time must be discarded while a mutation is running, so
        it cannot clobber the mutation's own loading state."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("MUTATION-DISCARD", ["sample-repo"], branch)
        release = threading.Event()

        def blocking_create(*args, **kwargs):
            release.wait(timeout=5)
            raise ValueError("boom")

        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()

            app.task_manager.create_task = blocking_create
            assert app._begin_mutation("task-list")
            app._create_task_worker("BUSY", ["sample-repo"], branch, verb="created")
            await pilot.pause()
            assert app._mutation_in_flight()

            task_list = app.query_one("#task-list", TaskList)
            assert task_list.loading is True  # set by _begin_mutation

            fake_worker = SimpleNamespace(is_cancelled=False)
            app._apply_refreshed_tasks([task], force_ui=True, worker=fake_worker)

            # Discarded: the mutation's own loading indicator is untouched
            assert task_list.loading is True

            release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()


class TestFingerprintOnApplyFailure:
    """Fix 4: an exception in the widget-apply block must not record the
    fingerprint, or a retry with the same (never-applied) data is skipped."""

    async def test_exception_in_apply_does_not_poison_fingerprint(
        self, app, task_manager, sample_repo, monkeypatch
    ):
        repo_path, branch = sample_repo
        task = task_manager.create_task("FP-TASK", ["sample-repo"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()

            task_list = app.query_one("#task-list", TaskList)
            calls = {"n": 0}
            original_load_tasks = task_list.load_tasks

            def flaky_load_tasks(*args, **kwargs):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("boom")
                return original_load_tasks(*args, **kwargs)

            monkeypatch.setattr(task_list, "load_tasks", flaky_load_tasks)
            app._last_tasks_fingerprint = None

            app._apply_refreshed_tasks([task], force_ui=True)
            assert calls["n"] == 1
            assert app._last_tasks_fingerprint is None  # not recorded on failure

            # A retry with the identical data must not be skipped as a no-op
            app._apply_refreshed_tasks([task], force_ui=False)
            assert calls["n"] == 2
            assert app._last_tasks_fingerprint is not None


class TestClaudeGuiCodeOpenFailure:
    """Fix 5: a non-zero `open` return code must notify+log an error, not
    report success."""

    async def test_open_returncode_nonzero_reports_error(
        self, app, task_manager, sample_repo, monkeypatch
    ):
        repo_path, branch = sample_repo
        task = task_manager.create_task("GUI-CODE-TASK", ["sample-repo"], branch)

        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if cmd and cmd[0] == "open":
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="no handler for URL")
            return real_run(cmd, *args, **kwargs)

        async with app.run_test() as pilot:
            await pilot.pause()
            monkeypatch.setattr(subprocess, "run", fake_run)

            app._open_claude_gui_code_worker(task)
            await app.workers.wait_for_complete()
            await pilot.pause()

            messages_panel = app.query_one("#messages-display", MessagesPanel)
            texts = [m.message for m in messages_panel._store.messages]
            assert any("Failed to open Claude desktop" in t for t in texts)


class TestClaudeSessionPrepOffThread:
    """Fix 6: session prep (which can shell out to git per worktree) must
    run in a worker, not block the UI thread inside the action handler."""

    async def test_resume_prep_runs_off_thread_before_opening_tab(
        self, app, task_manager, sample_repo, monkeypatch
    ):
        repo_path, branch = sample_repo
        task = task_manager.create_task("RESUME-TASK", ["sample-repo"], branch)
        app.current_task = task

        started, release = threading.Event(), threading.Event()
        opened = []

        def blocking_get_task(name):
            started.set()
            release.wait(timeout=5)
            return None

        monkeypatch.setattr(app, "_open_ghostty_tab", lambda *a, **k: opened.append(a))

        async with app.run_test() as pilot:
            await pilot.pause()
            monkeypatch.setattr(app.task_manager, "get_task", blocking_get_task)

            app.action_open_claude_resume()
            # The action must return immediately - the UI stays responsive
            # while prep blocks in the background instead of on this thread
            await pilot.pause()
            assert opened == []  # tab not opened yet: prep hasn't finished
            assert app.is_running

            await asyncio.get_running_loop().run_in_executor(None, started.wait, 5)
            release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert len(opened) == 1


class TestPushPullBusyGuard:
    """Fix 7: push_all/pull_all must refuse to start while a task mutation
    (e.g. a delete) is in flight, instead of racing it."""

    async def test_push_all_refuses_while_mutation_in_flight(self, app, task_manager, sample_repo):
        repo_path, branch = sample_repo
        task = task_manager.create_task("BUSY-PUSH", ["sample-repo"], branch)
        app.current_task = task
        release = threading.Event()

        def blocking_create(*args, **kwargs):
            release.wait(timeout=5)
            raise ValueError("boom")

        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()

            app.task_manager.create_task = blocking_create
            assert app._begin_mutation("task-list")
            app._create_task_worker("BLOCKER", ["sample-repo"], branch, verb="created")
            await pilot.pause()
            assert app._mutation_in_flight()

            worktree_list = app.query_one("#worktree-list", WorktreeList)
            worktree_list.loading = False

            app.action_push_all()

            assert not app._worker_running("push_pull")
            assert worktree_list.loading is False

            release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()

    async def test_pull_all_refuses_while_mutation_in_flight(self, app, task_manager, sample_repo):
        repo_path, branch = sample_repo
        task = task_manager.create_task("BUSY-PULL", ["sample-repo"], branch)
        app.current_task = task
        release = threading.Event()

        def blocking_create(*args, **kwargs):
            release.wait(timeout=5)
            raise ValueError("boom")

        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()

            app.task_manager.create_task = blocking_create
            assert app._begin_mutation("task-list")
            app._create_task_worker("BLOCKER", ["sample-repo"], branch, verb="created")
            await pilot.pause()
            assert app._mutation_in_flight()

            worktree_list = app.query_one("#worktree-list", WorktreeList)
            worktree_list.loading = False

            app.action_pull_all()

            assert not app._worker_running("push_pull")
            assert worktree_list.loading is False

            release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()


class TestArchivePathOnDeleteFailure:
    """Fix 8: a partial-archive path (ArchiveIncompleteError.path) must
    surface in the warning, and a successful archive path must still be
    logged even when the delete itself fails afterward."""

    async def test_finish_task_worker_logs_partial_archive_path(
        self, app, task_manager, sample_repo
    ):
        repo_path, branch = sample_repo
        task = task_manager.create_task("PARTIAL-ARCHIVE-TASK", ["sample-repo"], branch)

        partial = app.config.get_archive_dir() / "PARTIAL-ARCHIVE-TASK.partial.patch"

        def failing_archive(t):
            raise ArchiveIncompleteError(partial, [("repo-x", "diff failed")])

        async with app.run_test() as pilot:
            await pilot.pause()
            app.task_manager.archive_task = failing_archive

            app._finish_task_worker(task, False)
            await app.workers.wait_for_complete()
            await pilot.pause()

            messages_panel = app.query_one("#messages-display", MessagesPanel)
            texts = [m.message for m in messages_panel._store.messages]
            assert any(str(partial) in t for t in texts)
            # Deletion still proceeded (archive failure is non-blocking)
            assert not task.path.exists()

    async def test_finish_task_worker_error_path_logs_successful_archive(
        self, app, task_manager, sample_repo
    ):
        """finish_task raising (task changed on disk) must still report the
        archive location it already wrote, not just a bare failure."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("ARCHIVE-THEN-FAIL", ["sample-repo"], branch)
        archive_path = app.config.get_archive_dir() / "ARCHIVE-THEN-FAIL.patch"

        def failing_finish(t):
            raise ValueError("worktrees changed on disk")

        async with app.run_test() as pilot:
            await pilot.pause()
            app.task_manager.archive_task = lambda t: archive_path
            app.task_manager.finish_task = failing_finish

            app._finish_task_worker(task, False)
            await app.workers.wait_for_complete()
            await pilot.pause()

            messages_panel = app.query_one("#messages-display", MessagesPanel)
            texts = [m.message for m in messages_panel._store.messages]
            assert any("Failed to delete task" in t for t in texts)
            assert any(str(archive_path) in t for t in texts)
            # Nothing removed, matching finish_task's contract
            assert task.path.exists()
