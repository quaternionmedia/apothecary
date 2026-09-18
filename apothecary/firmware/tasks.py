"""Run one engine invocation at a time in the background and keep its log.

Compiles and uploads take seconds to minutes and the GUI wants to show the
output as it arrives, so each command runs on a thread, appending lines to a
``FirmwareTask`` the API serves incrementally (``?since=N``). One task at a
time: two uploads racing for the same serial port is never what anyone
wanted, and serialising everything is simpler to reason about than a
per-port lock.
"""

from __future__ import annotations

import subprocess
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from .models import FirmwareTask, TaskStatus

MAX_TASKS = 50


def stream(
    argv: List[str],
    log: Callable[[str], None],
    env: Optional[dict] = None,
    cwd: Optional[str] = None,
) -> int:
    """Run ``argv`` to completion, feeding each output line to ``log``; return its exit code.

    The synchronous building block both the CLI (log = click.echo) and the
    background runner (log = task.lines.append) use, so the two never drift.
    """
    log("$ " + " ".join(argv))
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=cwd,
            bufsize=1,
        )
    except OSError as exc:
        log(f"ERROR: {exc}")
        return 127
    assert proc.stdout is not None
    for line in proc.stdout:
        log(line.rstrip("\n"))
    return proc.wait()


class TaskBusy(RuntimeError):
    """Another firmware task is still running."""


class TaskRunner:
    def __init__(self):
        self._tasks: Dict[str, FirmwareTask] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()
        self._active: Optional[str] = None
        self._procs: Dict[str, subprocess.Popen] = {}
        self._cancel_requested: set = set()

    # -- read side ---------------------------------------------------------------

    def get(self, task_id: str) -> Optional[FirmwareTask]:
        return self._tasks.get(task_id)

    def list(self) -> List[FirmwareTask]:
        return [self._tasks[t] for t in reversed(self._order)]

    @property
    def active(self) -> Optional[FirmwareTask]:
        return self._tasks.get(self._active) if self._active else None

    # -- write side --------------------------------------------------------------

    def run(
        self,
        kind: str,
        title: str,
        steps: List[List[str]],
        env: Optional[dict] = None,
        cwd: Optional[str] = None,
        on_done: Optional[Callable[[FirmwareTask], None]] = None,
    ) -> FirmwareTask:
        """Start ``steps`` (argv lists) in sequence; stop at the first failure."""
        if not steps:
            raise ValueError("no steps to run")
        with self._lock:
            if self._active and self._tasks[self._active].status == TaskStatus.running:
                raise TaskBusy(
                    f"task {self._active} ({self._tasks[self._active].title}) is still running"
                )
            task = FirmwareTask(
                id=uuid.uuid4().hex[:12],
                kind=kind,
                title=title,
                command=steps[0],
                started=datetime.now(timezone.utc),
            )
            self._tasks[task.id] = task
            self._order.append(task.id)
            self._active = task.id
            self._evict()
        thread = threading.Thread(
            target=self._execute,
            args=(task, steps, env, cwd, on_done),
            daemon=True,
            name=f"firmware-{task.id}",
        )
        thread.start()
        return task

    def run_callable(
        self, kind: str, title: str, fn: Callable[[Callable[[str], None]], None], on_done=None
    ) -> FirmwareTask:
        """Like ``run`` but for Python work (the installer) that logs via a callback."""
        with self._lock:
            if self._active and self._tasks[self._active].status == TaskStatus.running:
                raise TaskBusy(
                    f"task {self._active} ({self._tasks[self._active].title}) is still running"
                )
            task = FirmwareTask(
                id=uuid.uuid4().hex[:12],
                kind=kind,
                title=title,
                command=[],
                started=datetime.now(timezone.utc),
            )
            self._tasks[task.id] = task
            self._order.append(task.id)
            self._active = task.id
            self._evict()

        def target():
            try:
                fn(task.lines.append)
            except Exception as exc:  # noqa: BLE001 - surfaced to the log, not swallowed
                task.lines.append(f"ERROR: {exc}")
                self._finish(task, TaskStatus.failed, 1)
            else:
                self._finish(task, TaskStatus.succeeded, 0)
            if on_done:
                on_done(task)

        threading.Thread(target=target, daemon=True, name=f"firmware-{task.id}").start()
        return task

    def cancel(self, task_id: str) -> bool:
        """Stop a running task: kill its current process, skip any remaining steps."""
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.running:
            return False
        with self._lock:
            self._cancel_requested.add(task_id)
            proc = self._procs.get(task_id)
        if proc:
            proc.terminate()
        task.lines.append("Cancelled.")
        self._finish(task, TaskStatus.cancelled, None)
        return True

    # -- internals ---------------------------------------------------------------

    def _execute(self, task: FirmwareTask, steps, env, cwd, on_done) -> None:
        status, code = TaskStatus.succeeded, 0
        for argv in steps:
            task.command = argv
            task.lines.append("$ " + " ".join(argv))
            with self._lock:
                if task.id in self._cancel_requested:
                    return
                try:
                    proc = subprocess.Popen(
                        argv,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        env=env,
                        cwd=cwd,
                        bufsize=1,
                    )
                except OSError as exc:
                    task.lines.append(f"ERROR: {exc}")
                    status, code = TaskStatus.failed, 127
                    break
                self._procs[task.id] = proc
            assert proc.stdout is not None
            for line in proc.stdout:
                task.lines.append(line.rstrip("\n"))
            proc.wait()
            with self._lock:
                self._procs.pop(task.id, None)
                if task.id in self._cancel_requested:
                    self._cancel_requested.discard(task.id)
                    return
            if proc.returncode != 0:
                task.lines.append(f"exit {proc.returncode}")
                status, code = TaskStatus.failed, proc.returncode
                break
        self._finish(task, status, code)
        if on_done:
            on_done(task)

    def _finish(self, task: FirmwareTask, status: TaskStatus, code: Optional[int]) -> None:
        with self._lock:
            task.status = status
            task.returncode = code
            task.finished = datetime.now(timezone.utc)
            if self._active == task.id:
                self._active = None

    def _evict(self) -> None:
        while len(self._order) > MAX_TASKS:
            old = self._order.pop(0)
            if old != self._active:
                self._tasks.pop(old, None)


_RUNNER: Optional[TaskRunner] = None


def get_task_runner() -> TaskRunner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = TaskRunner()
    return _RUNNER
