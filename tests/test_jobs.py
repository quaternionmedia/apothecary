"""Jobs: one operation a machine performs on a part, kept in the state folder.

The model over machine kinds, the registry of what each kind of machine offers,
the store, and the print records kept before jobs carried over as print jobs.
"""

import json
import stat
from datetime import datetime, timedelta, timezone

import pytest

from apothecary import jobs


@pytest.fixture(autouse=True)
def _a_state_folder_of_its_own(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(jobs, "_LIVE", {})
    monkeypatch.setattr(jobs, "LISTENERS", [])
    monkeypatch.setattr(jobs, "_OPERATIONS", dict(jobs._OPERATIONS))
    yield tmp_path / "state"


AT = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)


def _job(kind="print", port="/dev/ttyUSB0", at=AT, **over) -> jobs.Job:
    machine = {"print": "printer", "mill": "mill"}.get(kind, kind)
    fields = dict(
        id=jobs.new_id(at, port),
        kind=kind,
        machine=jobs.JobMachine(kind=machine, port=port),
        input=jobs.JobInput(name="bracket.gcode", size=120, sha256="ab" * 32),
        started_at=at,
    )
    fields.update(over)
    return jobs.Job(**fields)


def _ended(job: jobs.Job, outcome="done", reason=None) -> jobs.Job:
    return job.model_copy(
        update={
            "outcome": outcome,
            "reason": reason,
            "finished_at": job.started_at + timedelta(minutes=5),
            "progress": 1.0 if outcome == "done" else 0.5,
        }
    )


def _run(job: jobs.Job, outcome="done", reason=None) -> jobs.Job:
    """A job begun and ended, as a machine's own thread does it."""
    jobs.begin(job, live=lambda: job)
    return jobs.end(_ended(job, outcome, reason))


def test_a_printer_offers_print():
    (only,) = jobs.operations("printer")
    assert (only.kind, only.machine, only.label) == ("print", "printer", "Print")
    assert ".gcode" in only.inputs
    assert jobs.operation("print") is only
    assert jobs.operations("mill") == []


def test_a_second_kind_registers_and_lists_beside_print():
    """The abstraction: a mill registers its operation as a printer does, its jobs are
    kept and listed the same way, and a kind is one machine's."""
    mill = jobs.register(jobs.Operation(kind="mill", machine="mill", label="Mill", inputs=(".nc",)))
    assert jobs.operations("mill") == [mill]
    assert [op.kind for op in jobs.operations()] == ["print", "mill"]
    assert jobs.machine_kinds() == ["printer", "mill"]
    assert jobs.register(jobs.Operation(kind="mill", machine="mill", label="Mill", inputs=(".nc",)))
    with pytest.raises(ValueError, match="already"):
        jobs.register(jobs.Operation(kind="mill", machine="laser", label="Cut"))

    cut = _run(_job("mill", port="/dev/ttyACM0", input=jobs.JobInput(name="pocket.nc")))
    printed = _run(_job("print", at=AT + timedelta(hours=1)))
    assert [j.id for j in jobs.list_jobs(kind="mill")] == [cut.id]
    assert [j.id for j in jobs.list_jobs(kind="print")] == [printed.id]
    assert [j.id for j in jobs.list_jobs()] == [printed.id, cut.id]
    assert jobs.get(cut.id).machine.kind == "mill"


def test_a_job_no_machine_offers_is_refused():
    with pytest.raises(ValueError, match="no machine offers 'weld'"):
        jobs.begin(_job("weld"), live=lambda: None)
    assert jobs.list_jobs() == []


def test_a_running_job_reads_live_and_is_written_when_it_begins_and_ends(
    _a_state_folder_of_its_own,
):
    job = _job()
    now = {"job": job}
    jobs.begin(job, live=lambda: now["job"])
    on_disk = json.loads((_a_state_folder_of_its_own / "jobs" / f"{job.id}.json").read_text())
    assert on_disk["outcome"] == "running" and on_disk["progress"] == 0.0
    now["job"] = job.model_copy(update={"progress": 0.5, "detail": {"sent": 6, "total": 12}})
    # Progress is read from the machine's own thread, not written line by line.
    assert jobs.get(job.id).progress == 0.5
    assert jobs.list_jobs()[0].detail == {"sent": 6, "total": 12}
    on_disk = json.loads((_a_state_folder_of_its_own / "jobs" / f"{job.id}.json").read_text())
    assert on_disk["progress"] == 0.0
    jobs.end(_ended(job, "cancelled", "cancelled from the card"))
    got = jobs.get(job.id)
    assert (got.outcome, got.reason, got.running) == ("cancelled", "cancelled from the card", False)
    assert got.finished_at is not None
    with pytest.raises(ValueError, match="ends done, cancelled or failed"):
        jobs.end(job)


def test_a_job_left_running_when_the_server_stopped_reads_as_failed(_a_state_folder_of_its_own):
    job = _job()
    folder = _a_state_folder_of_its_own / "jobs"
    folder.mkdir(parents=True)
    (folder / f"{job.id}.json").write_text(job.model_dump_json())
    got = jobs.get(job.id)
    assert got.outcome == "failed" and "server stopped" in got.reason
    assert json.loads((folder / f"{job.id}.json").read_text())["outcome"] == "running"


def test_the_list_puts_running_jobs_first_then_the_newest():
    old = _run(_job(at=AT))
    newer = _run(_job(at=AT + timedelta(hours=2), port="/dev/ttyUSB1"))
    running = _job(at=AT + timedelta(hours=1), port="/dev/ttyUSB2")
    jobs.begin(running, live=lambda: running)
    assert [j.id for j in jobs.list_jobs()] == [running.id, newer.id, old.id]


def test_jobs_list_by_site_and_by_machine_and_a_moved_port_keeps_its_history():
    """A machine is the board's own identity when both the job and the asker know it,
    else its port: the same printer under another port number lists its jobs, and
    another board on its old port does not; a job recorded with no identity (a
    print record from before jobs) is its port's."""
    here = _run(
        _job(
            port="/dev/ttyUSB1",
            site="garage",
            machine=jobs.JobMachine(
                kind="printer",
                port="/dev/ttyUSB1",
                identity="A106ZTEU",
                path="printer_1.frame_system.mainboard",
            ),
        )
    )
    anonymous = _run(_job(port="/dev/ttyUSB0", at=AT + timedelta(hours=1)))
    assert [j.id for j in jobs.list_jobs(site="garage")] == [here.id]
    assert jobs.list_jobs(site="parts_library") == []
    assert [j.id for j in jobs.list_jobs(machine="/dev/ttyUSB0", identity="A106ZTEU")] == [
        anonymous.id,
        here.id,
    ]
    assert [j.id for j in jobs.list_jobs(machine="/dev/ttyUSB1", identity="OTHERBOARD")] == []
    assert [j.id for j in jobs.list_jobs(machine="/dev/ttyUSB0")] == [anonymous.id]
    assert [j.id for j in jobs.list_jobs(machine="/dev/ttyUSB1")] == [here.id]


def test_a_job_id_that_is_not_one_finds_nothing():
    _run(_job())
    for bad in ("../firmware-state", "a/b", "", ".hidden", "x" * 200):
        assert jobs.get(bad) is None, bad


def test_the_store_is_the_accounts_alone(_a_state_folder_of_its_own):
    _run(_job())
    mode = stat.S_IMODE((_a_state_folder_of_its_own / "jobs").stat().st_mode)
    assert mode == 0o700


def test_listeners_hear_a_job_begin_and_end():
    heard = []
    jobs.LISTENERS.append(lambda job: heard.append((job.id, job.outcome)))
    job = _run(_job())
    assert heard == [(job.id, "running"), (job.id, "done")]


def _old_record(folder, rid, port, name, file_id, at, outcome, sent, total, error=None):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{rid}.json").write_text(
        json.dumps(
            {
                "id": rid,
                "port": port,
                "file_id": file_id,
                "name": name,
                "at": at.isoformat(),
                "finished": (at + timedelta(minutes=30)).isoformat(),
                "outcome": outcome,
                "sent": sent,
                "total": total,
                "error": error,
                "firmware": "Marlin TH3D UFW 2.94a",
                "lines": ["> G1 X5", "ok"],
            }
        )
    )


def test_the_print_records_kept_before_jobs_are_carried_over_as_print_jobs(
    _a_state_folder_of_its_own,
):
    """Every print record under prints/records becomes a print job with the record's id:
    its port, file, times, outcome, error, lines sent and the firmware's tail. The
    records stay where they were, and reading again carries nothing twice."""
    records = _a_state_folder_of_its_own / "prints" / "records"
    prints = _a_state_folder_of_its_own / "prints"
    _old_record(
        records, "20260920T132512.468-dev_ttyUSB0", "/dev/ttyUSB0", "cube.gcode",
        "20260920T130000.000-cube", AT - timedelta(days=13), "done", 12, 12,
    )  # fmt: skip
    _old_record(
        records, "20260921T090000.000-dev_ttyUSB0", "/dev/ttyUSB0", "bracket.gcode",
        "20260921T085900.000-bracket", AT - timedelta(days=12), "failed", 3, 40,
        error="Error:Printer halted",
    )  # fmt: skip
    (prints / "20260920T130000.000-cube.json").write_text(
        json.dumps(
            {
                "id": "20260920T130000.000-cube",
                "name": "cube.gcode",
                "size": 345,
                "lines": 12,
                "uploaded_at": (AT - timedelta(days=13)).isoformat(),
                "problems": [],
            }
        )
    )
    (records / "garbage.json").write_text("{ not json")

    listed = jobs.list_jobs(machine="/dev/ttyUSB0")
    assert [j.id for j in listed] == [
        "20260921T090000.000-dev_ttyUSB0",
        "20260920T132512.468-dev_ttyUSB0",
    ]
    failed, done = listed
    assert (failed.kind, failed.machine.kind, failed.machine.port) == (
        "print",
        "printer",
        "/dev/ttyUSB0",
    )
    assert (failed.outcome, failed.reason) == ("failed", "Error:Printer halted")
    assert failed.input.name == "bracket.gcode"
    assert failed.input.file_id == "20260921T085900.000-bracket"
    assert failed.progress == pytest.approx(3 / 40)
    assert failed.detail == {"sent": 3, "total": 40, "firmware": "Marlin TH3D UFW 2.94a"}
    assert failed.finished_at - failed.started_at == timedelta(minutes=30)
    assert (failed.site, failed.part, failed.input.sha256) == (None, None, None)
    assert (done.outcome, done.reason, done.progress, done.input.size) == ("done", None, 1.0, 345)
    assert jobs.get(done.id).log == ["> G1 X5", "ok"]
    # The records stay; the jobs are written beside them, once.
    assert len(list(records.glob("*.json"))) == 3
    assert len(list((_a_state_folder_of_its_own / "jobs").glob("*.json"))) == 2
    assert [j.id for j in jobs.list_jobs()] == [j.id for j in listed]
    assert len(list((_a_state_folder_of_its_own / "jobs").glob("*.json"))) == 2
