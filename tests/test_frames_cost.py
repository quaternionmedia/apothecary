"""What the kept frames cost to read: the frames files are read when they change,
not once for every question asked of them."""

from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from apothecary.evidence import frames, log

T0 = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


@pytest.fixture
def reads(monkeypatch):
    """The frames files opened, by name."""
    opened = []
    real = pathlib.Path.open

    def counting(self, *args, **kwargs):
        appending = str(kwargs.get("mode", args[0] if args else "r")).startswith("a")
        if f"{os.sep}frames{os.sep}" in str(self) and not appending:
            opened.append(self.name)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", counting)
    return opened


def _frame(n, at=None):
    at = at or T0 + timedelta(minutes=n)
    record = {
        "id": f"captures/{n}.png",
        "camera": "camera_1",
        "poll": f"poll-{n}",
        "at": at.isoformat(),
        "size": 100,
        "subjects": ["garage:printer_1"],
    }
    log.append("garage", log.FRAMES, record, at)


def test_a_refresh_and_a_frame_read_the_frames_history_once_between_writes(state_dir, reads):
    for n in range(3):
        _frame(n)
    log.document("garage", at=T0 + timedelta(hours=1))  # kept, and sizes, for one refresh
    assert len(reads) == 1
    log.document("garage", at=T0 + timedelta(hours=1))
    frames.sizes("garage")
    frames.over_budget("garage", "garage:printer_1")
    assert len(reads) == 1  # nothing was written: nothing is read again
    _frame(3)
    assert [f["id"] for f in frames.kept("garage")][-1] == "captures/3.png"
    frames.over_budget("garage", "garage:printer_1")
    assert len(reads) == 2  # one write, one read
    frames.forgotten("garage", "captures/0.png", "over the budget", T0 + timedelta(minutes=9))
    assert "captures/0.png" not in [f["id"] for f in frames.kept("garage")]
    assert len(reads) == 3


def test_a_budget_write_that_fails_midway_leaves_the_previous_file_readable(state_dir, monkeypatch):
    frames.set_budget("garage", "garage:printer_1", 111)

    def failing(src, dst):
        raise OSError("the disk went away")

    with monkeypatch.context() as patched:
        patched.setattr(os, "replace", failing)
        with pytest.raises(OSError):
            frames.set_budget("garage", "garage:printer_1", 222)
    folder = log.space_dir("garage")
    assert json.loads((folder / frames.BUDGETS).read_text()) == {"garage:printer_1": 111}
    assert frames.budget("garage", "garage:printer_1") == 111
    assert [p.name for p in folder.iterdir()] == [frames.BUDGETS]
