"""A printer's heater loops through the seam (``apothecary.firmware.loops``), simulated only.

The simulated board's modelled heaters (``gcode.SimulatedHeater``) against their own plant;
the lines that read, set and save a loop's gains; the experiments, each a job that holds
the port, against the lines they send; every way an experiment ends sending the heater
off; a ceiling ending one; nothing heating without the latch; ``M500`` never sent unless
asked for by name; and ``can_now`` agreeing with the routes for the loop's verbs.

Every board here is simulated or scripted. What Marlin says to ``M303`` and how it scales
``@:`` are assumed (``gcode.py``'s notes); these tests hold this code to those assumptions,
not a board to them.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from firmware_helpers import REPLIES, ScriptedTransport

from apothecary import control_loops as cl
from apothecary import jobs
from apothecary.api import app
from apothecary.firmware import api as firmware_api
from apothecary.firmware import can, devices, gcode, loops, tasks
from apothecary.firmware.toolchains import ToolchainError
from apothecary.state_folder import private_folder

PORT = "/dev/ttyFAKE1"
OFF = ["M104 S0", "M140 S0", "M107", "M84"]  # the safe-off a cancelled print sends


class Fast:
    """Simulated seconds running ``speed`` times real time: the board's and the job's."""

    def __init__(self, speed: float):
        self.speed, self.t0 = speed, time.monotonic()

    def now(self) -> float:
        return (time.monotonic() - self.t0) * self.speed

    def sleep(self, s: float) -> None:
        time.sleep(s / self.speed)


class Recorded(gcode.SimulatedPrinter):
    """The simulated board, keeping every line it was sent."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.sent = []

    def write(self, data):
        self.sent += [ln.strip() for ln in data.decode().split("\n") if ln.strip()]
        super().write(data)


@pytest.fixture
def board(fake_arduino_cli, fresh_task_runner, monkeypatch):
    """A simulated printer whose heaters are modelled, on a clock 200 times real time,
    behind the seam's link registry; the board and the clock."""
    fast = Fast(200)
    made = {}

    def factory(port, baud):
        made["board"] = Recorded(port, baud, heaters=gcode.simulated_heaters(port), clock=fast.now)
        return made["board"]

    links = gcode.PrinterLinks(factory=factory)
    monkeypatch.setattr(gcode, "_LINKS", links)
    devices.printer_status(PORT)  # opened and identified, as a page's first poll does
    yield SimpleNamespace(links=links, fast=fast, sim=made["board"], made=made)
    for job in loops.running():
        job.cancel()
        job.thread.join(5)
    links.stop_all()


def _run(board, plan, wait=60.0):
    job = loops.start(PORT, plan, clock=board.fast.now, sleep=board.fast.sleep)
    job.thread.join(wait)
    assert job.finished is not None, f"{job.what} did not end within {wait:.0f}s"
    return job


def _after(sent, line):
    return sent[len(sent) - 1 - sent[::-1].index(line) + 1 :]


def _heats(sent):
    return [
        ln for ln in sent if ln.startswith(("M104 S", "M140 S", "M303")) and not ln.endswith(" S0")
    ]


STEP = dict(base_c=180, step_c=5, settle_s=300.0, after_s=240.0)


class Stepped:
    """Simulated seconds that pass only as the job sleeps them or a reading takes them:
    a board as slow as a test says, with no real time spent and nothing else running
    in the process able to change it."""

    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


@pytest.fixture
def slow_board(fake_arduino_cli, fresh_task_runner, monkeypatch):
    """The simulated printer of ``board`` on a ``Stepped`` clock, each ``M105`` taking
    ``slow.reading_s(t)`` simulated seconds, ``t`` the clock as it is written."""
    clock = Stepped()
    slow = SimpleNamespace(clock=clock, reading_s=lambda t: 0.0)
    made = {}

    class SlowReadings(Recorded):
        def write(self, data):
            if data.decode().strip() == "M105":
                clock.t += slow.reading_s(clock.t)
            super().write(data)

    def factory(port, baud):
        made["board"] = SlowReadings(
            port, baud, heaters=gcode.simulated_heaters(port), clock=clock.now
        )
        return made["board"]

    links = gcode.PrinterLinks(factory=factory)
    monkeypatch.setattr(gcode, "_LINKS", links)
    devices.printer_status(PORT)
    links.control.arm(PORT)
    slow.links, slow.sim = links, made["board"]
    yield slow
    for job in loops.running():
        job.cancel()
        job.thread.join(5)
    links.stop_all()


# ---- the simulated board's heaters --------------------------------------------------------


class TestTheSimulatedHeaters:
    def _board(self, at):
        sim = gcode.SimulatedPrinter(
            "/dev/ttySIM",
            115200,
            heaters=gcode.simulated_heaters("/dev/ttySIM"),
            clock=lambda: at[0],
        )
        return sim, gcode.GcodeLink("/dev/ttySIM", 115200, sim)

    def test_a_heater_full_on_follows_its_plant(self):
        """Below its target by more than the PID's range the heater is full on, so the
        reading is the plant's step from ambient: ``23 + 255 K (1 - e^-(t - theta)/tau)``."""
        at = [0.0]
        sim, link = self._board(at)
        gcode.control_printer(link, "M104 S250")
        plant = sim.heaters["T"].plant
        for t in (2.0, 20.0, 60.0):
            at[0] = t
            hot = gcode.parse_m105(link.command("M105")[0])["hotends"][0]
            assert hot.power == 255
            assert hot.actual == pytest.approx(23 + plant.step(t, 255), abs=1.0)

    def test_a_heater_left_alone_holds_its_target(self):
        at = [0.0]
        sim, link = self._board(at)
        gcode.control_printer(link, "M104 S200")
        at[0] = 1500.0
        hot = gcode.parse_m105(link.command("M105")[0])["hotends"][0]
        assert hot.actual == pytest.approx(200, abs=1.0)
        assert hot.power == pytest.approx((200 - 23) / sim.heaters["T"].plant.gain, abs=15)

    def test_the_board_answers_its_gains_and_takes_new_ones(self):
        at = [0.0]
        sim, link = self._board(at)
        said = gcode.parse_gains(link.command("M503"))
        assert set(said) == {"hotend 0", "bed"}
        gcode.control_printer(link, "M301 P12.5 I0.3 D20")
        assert gcode.parse_gains(link.command("M503"))["hotend 0"]["kp"] == 12.5
        assert sim.heaters["T"].gains == (12.5, 0.3, 20.0)
        assert gcode.parse_gains_report(link.command("M301"))["kd"] == 20.0

    def test_an_autotune_says_the_classic_gains_of_its_relay(self):
        fast = Fast(400)
        sim = gcode.SimulatedPrinter(
            "/dev/ttySIM", 115200, heaters=gcode.simulated_heaters("/dev/ttySIM"), clock=fast.now
        )
        link = gcode.GcodeLink("/dev/ttySIM", 115200, sim)
        lines = link.watch("M303 E0 S200 C5", lambda line: None, silence=15, limit=600)
        said = gcode.parse_autotune(lines)
        v = said["values"]
        assert said["finished"] and said["failed"] is None and len(said["temperatures"]) > 20
        assert v["kp"] == pytest.approx(0.6 * v["ku"], abs=0.02)
        assert v["ki"] == pytest.approx(2 * v["kp"] / v["tu"], abs=0.02)
        assert v["kd"] == pytest.approx(v["kp"] * v["tu"] / 8, abs=0.02)
        # The heater is off when it ends, and the board answers again.
        assert gcode.parse_m105(link.command("M105")[0])["hotends"][0].target == 0

    def test_a_break_ends_an_autotune_and_the_waiting_lines_are_answered_after(self):
        at = [0.0]
        sim, _ = self._board(at)
        sim.write(b"M303 E0 S200 C5\n")
        sim.write(b"M105\n")  # waits behind the autotune, as a board's queue does
        assert sim._waiting == ["M105"]
        sim.write(b"M108\n")
        said = sim.read(0.1).decode().splitlines()
        assert said[0] == "echo:autotune broken by M108" and said[1] == "ok"
        assert said[2].startswith("ok T:") and said[-1] == "ok"
        assert sim.heaters["T"].target == 0 and sim.heaters["T"].autotune is None

    def test_an_unmodelled_board_keeps_its_old_ways(self, monkeypatch):
        monkeypatch.delenv("APOTHECARY_SIMULATED_HEATERS", raising=False)
        sim = gcode.SimulatedPrinter("/dev/ttySIM", 115200)
        assert sim.heaters is None
        link = gcode.GcodeLink("/dev/ttySIM", 115200, sim)
        gcode.control_printer(link, "M104 S50")
        assert abs(gcode.parse_m105(link.command("M105")[0])["hotends"][0].actual - 50) < 1
        assert "not modelled" in link.command("M303 E0 S200 C5")[0]
        monkeypatch.setenv("APOTHECARY_SIMULATED_HEATERS", "model")
        assert gcode.SimulatedPrinter("/dev/ttySIM", 115200).heaters is not None


# ---- the lines ----------------------------------------------------------------------------


class TestTheLines:
    def test_the_gain_lines_are_bounded_control_lines(self):
        assert gcode.normalise_control("m301 p22.2 i1.08 d114") == "M301 P22.2 I1.08 D114"
        assert gcode.normalise_control("M304 P70 I1.5 D800") == "M304 P70 I1.5 D800"
        with pytest.raises(gcode.OutOfBounds):
            gcode.normalise_control("M301 P2000 I1 D1")
        with pytest.raises(ValueError):
            gcode.normalise_control("M301 P-1 I1 D1")
        with pytest.raises(ValueError):
            gcode.normalise_control("M301 E1 P1 I1 D1")  # hotend 0 alone
        with pytest.raises(ValueError):
            gcode.normalise_control("M301 P1.12345 I1 D1")

    def test_an_autotune_and_a_save_are_never_control_lines(self):
        for line in ("M303 E0 S200 C5", "M500", "M502"):
            with pytest.raises(ValueError):
                gcode.normalise_control(line)
        assert gcode.SAVE_SETTINGS not in gcode.QUERY_CODES

    def test_a_streamed_file_may_not_carry_an_autotune(self):
        """A file streamed line by line gives each line a line's time; an autotune runs for
        minutes with the heater relay-driven, and is an experiment's, watched as one."""
        total, problems = gcode.check_gcode("G28\nM303 E0 S200 C5\nM301 P1 I1 D1\n")
        assert total == 3 and problems == [
            "line 2: M303 runs the firmware's autotune: a heater loop's experiment, watched as one (firmware/loops.py)"
        ]

    def test_an_autotune_line_is_bounded(self):
        assert gcode.normalise_autotune("m303 e0 s200 c5") == "M303 E0 S200 C5"
        with pytest.raises(gcode.OutOfBounds):
            gcode.normalise_autotune("M303 E-1 S140 C5")  # over the bed's cap
        with pytest.raises(gcode.OutOfBounds):
            gcode.normalise_autotune("M303 E0 S200 C2")
        with pytest.raises(ValueError):
            gcode.normalise_autotune("M303 S200")

    def test_the_parsers_read_the_forms_they_name(self):
        lines = [
            "echo:; PID settings:",
            "echo:  M301 P22.20 I1.08 D114.00",
            "echo:  M304 P70.00 I1.50 D800.00",
            "ok",
        ]
        assert gcode.parse_gains(lines)["hotend 0"] == {
            "kp": 22.2,
            "ki": 1.08,
            "kd": 114.0,
            "line": lines[1].strip(),
        }
        assert gcode.parse_gains(["echo:  M301 E1 P1 I2 D3"])["hotend 1"]["kd"] == 3.0
        said = gcode.parse_autotune(
            [
                " T:200.10 /200.00 @:127",
                " Ku: 31.92 Tu: 25.27",
                " Kp: 19.15 Ki: 1.52 Kd: 60.49",
                "PID Autotune finished! Put the last Kp, Ki and Kd constants from below into Configuration.h",
                "#define DEFAULT_Kp 19.16",
                "#define DEFAULT_Ki 1.52",
                "#define DEFAULT_Kd 60.49",
            ]
        )
        assert said["values"] == {"ku": 31.92, "tu": 25.27, "kp": 19.16, "ki": 1.52, "kd": 60.49}
        assert said["finished"] and said["temperatures"][0]["hotends"][0].actual == 200.1
        assert (
            gcode.parse_autotune(["PID Autotune failed! Temperature too high"])["failed"]
            == "Temperature too high"
        )


# ---- plans ---------------------------------------------------------------------------------


class TestPlans:
    @pytest.mark.parametrize(
        "args, says",
        [
            (dict(heater="hotend", kind="step", ceiling_c=400, max_duration_s=900, **STEP), "cap"),
            (
                dict(
                    heater="bed",
                    kind="step",
                    ceiling_c=60,
                    max_duration_s=900,
                    base_c=50,
                    step_c=15,
                    settle_s=300,
                    after_s=300,
                ),
                "above the ceiling",
            ),
            (
                dict(heater="hotend", kind="step", ceiling_c=200, max_duration_s=500, **STEP),
                "longer than the longest",
            ),
            (
                dict(heater="hotend", kind="step", ceiling_c=200, max_duration_s=9000, **STEP),
                "longest time is",
            ),
            (
                dict(heater="hotend", kind="step", ceiling_c=200, max_duration_s=900, base_c=180),
                "needs",
            ),
            (
                dict(
                    heater="hotend",
                    kind="autotune",
                    ceiling_c=203,
                    max_duration_s=900,
                    target_c=200,
                    cycles=5,
                ),
                "above its target",
            ),
            (
                dict(
                    heater="hotend",
                    kind="perturbation",
                    ceiling_c=210,
                    max_duration_s=3000,
                    centre_c=200,
                    amplitude_c=2,
                    period_s=61,
                    periods=3,
                    settle_s=300,
                ),
                "even number",
            ),
            (
                dict(
                    heater="hotend",
                    kind="perturbation",
                    ceiling_c=210,
                    max_duration_s=3000,
                    centre_c=200,
                    amplitude_c=2,
                    period_s=60,
                    periods=1,
                    settle_s=300,
                ),
                "two periods",
            ),
            (
                dict(
                    heater="hotend", index=1, kind="step", ceiling_c=200, max_duration_s=900, **STEP
                ),
                "hotend 0",
            ),
            (
                dict(heater="chamber", kind="step", ceiling_c=60, max_duration_s=900, **STEP),
                "hotend's or the bed's",
            ),
        ],
        ids=[
            "over-the-cap",
            "target-over-ceiling",
            "schedule-too-long",
            "longest-over-the-seam",
            "missing-parameters",
            "autotune-headroom",
            "odd-period",
            "one-period",
            "second-hotend",
            "no-such-heater",
        ],
    )
    def test_a_plan_off_its_bounds_is_refused_before_anything_is_sent(self, args, says):
        args = {"index": 0, **args}
        with pytest.raises(ValueError, match=says):
            loops.plan(**args)

    def test_a_plan_says_its_targets_and_when(self):
        step = loops.plan("hotend", 0, "step", 200, 900, **STEP)
        assert step.changes == ((0.0, 180), (300.0, 185)) and step.end_s == 540.0
        wave = loops.plan(
            "bed",
            0,
            "perturbation",
            70,
            3000,
            centre_c=60,
            amplitude_c=2,
            period_s=120,
            periods=2,
            settle_s=600,
        )
        assert [t for _, t in wave.changes] == [60, 62, 58, 62, 58, 60]
        assert wave.target_line(62) == "M140 S62"
        tune = loops.plan("bed", 0, "autotune", 70, 3000, target_c=60, cycles=5)
        assert tune.autotune == "M303 E-1 S60 C5"


# ---- experiments ---------------------------------------------------------------------------


class TestExperiments:
    def test_a_step_sets_its_targets_reads_and_ends_with_the_heater_off(self, board):
        board.links.control.arm(PORT)
        job = _run(board, loops.plan("hotend", 0, "step", 200, 900, **STEP))
        sent = board.sim.sent
        assert job.outcome == "done", job.error
        heats = _heats(sent)
        assert heats == ["M104 S180", "M104 S185"]
        assert sent[sent.index("M104 S185") + 1 :].count("M105") >= 200  # read on after the step
        assert _after(sent, "M104 S185")[-5:] == [*OFF, "M105"]  # off, then read back
        assert job.heater_off.startswith("heater off") and "M500" not in sent
        assert job.experiment.samples.actual and max(job.experiment.samples.target) == 185
        assert jobs.get(job.job.id).outcome == "done"
        assert loops.experiment(job.experiment.id)["kind"] == "step"

    def test_a_step_s_stages_and_progress_reach_a_follower_of_the_jobs(self, board):
        import asyncio

        from apothecary import surfaces

        board.links.control.arm(PORT)

        async def follow():
            following = surfaces.subscribe(["jobs"])
            try:
                job = await asyncio.to_thread(
                    _run, board, loops.plan("hotend", 0, "step", 200, 900, **STEP)
                )
                got, _ = await following.next(0.2)
                return job, got
            finally:
                following.close()

        job, told = asyncio.run(follow())
        stages = [e["body"]["detail"]["stage"] for e in told]
        assert {e["key"] for e in told} == {job.job.id}
        assert [s for n, s in enumerate(stages) if n == 0 or stages[n - 1] != s] == [
            "starting",
            "running",
            "done",
        ]
        progress = [e["body"]["progress"] for e in told]
        assert progress == sorted(progress) and 3 < len(told) <= 105
        assert told[-1]["body"]["outcome"] == "done"

    def test_a_tune_and_its_document_are_surfaces_that_ask_no_port(self, board):
        import asyncio

        from apothecary import surfaces
        from apothecary.api import app

        client = TestClient(app)
        board.links.control.arm(PORT)

        async def follow():
            following = surfaces.subscribe(["tune", "control_loop"])
            try:
                job = await asyncio.to_thread(
                    _run, board, loops.plan("hotend", 0, "step", 200, 900, **STEP)
                )
                got, _ = await following.next(0.2)
                return job, got
            finally:
                following.close()

        job, told = asyncio.run(follow())
        tuned = [e for e in told if e["surface"] == "tune"]
        assert {e["key"] for e in tuned} == {PORT} and len(tuned) >= 3
        assert tuned[0]["body"]["running"] is True and tuned[-1]["body"]["running"] is False
        assert tuned[-1]["body"]["outcome"] == "done" and tuned[-1]["body"]["stage"] == "done"
        assert [e["body"]["progress"] for e in tuned] == sorted(e["body"]["progress"] for e in tuned)
        [made] = [e for e in told if e["surface"] == "control_loop"]
        assert made["key"] == job.experiment.id and made["body"]["error"] is None
        assert made["body"]["document"]["schema"] == "control/loop/1"
        # Read now: the same, and nothing written to the board by either.
        sent = len(board.sim.sent)
        read = client.get("/surfaces/control_loop", params={"experiment": job.experiment.id})
        assert read.status_code == 200
        again = read.json()["snapshot"]["document"]
        for doc in (again, made["body"]["document"]):
            doc.pop("generated_at")  # the one figure that is the moment it was made
        assert again == made["body"]["document"]
        listed = client.get("/surfaces/control_loop", params={"port": PORT}).json()["snapshot"]
        assert [e["id"] for e in listed["experiments"]] == [job.experiment.id]
        assert client.get("/surfaces/tune").json()["snapshot"]["tuning"][0]["job_id"] == job.job.id
        gone = client.get("/surfaces/control_loop", params={"experiment": "nope"}).json()
        assert gone["snapshot"]["document"] is None and "no kept experiment" in gone["snapshot"]["error"]
        assert len(board.sim.sent) == sent

    def test_a_step_s_document_finds_the_simulated_plant(self, board):
        """The fit of a closed-loop step read once a (simulated) second finds the
        simulator's own plant within 15 % in its gain and time constant and 2 s in its dead
        time. The data comes from the model it is fitted to, so this holds the pipeline --
        the job, the record, the document -- and says nothing of a machine."""
        board.links.control.arm(PORT)
        job = _run(
            board,
            loops.plan(
                "hotend", 0, "step", 200, 1200, base_c=180, step_c=5, settle_s=600, after_s=400
            ),
        )
        doc = loops.document(job.experiment.id, rule="simc", read_board=True)
        p, true = doc.plant, board.sim.heaters["T"].plant
        assert p.gain == pytest.approx(true.gain, rel=0.15)
        assert p.time_constant == pytest.approx(true.time_constant, rel=0.15)
        assert p.dead_time == pytest.approx(true.dead_time, abs=2.0)
        assert doc.controller.on_machine.basis == "measured"
        client = TestClient(app)
        body = {"experiment_id": job.experiment.id, "rule": "simc"}
        md = client.post("/firmware/printers/loops/document?format=md", json=body)
        assert md.status_code == 200 and md.text.startswith("# Control loop: hotend 0")
        drawn = client.post("/firmware/printers/loops/curves", json=body).json()
        assert len(drawn["step"]["measured"]) == len(job.experiment.samples.t)
        assert "designed" in drawn["bode"]
        listed = client.get("/firmware/printers/loops/experiments", params={"port": PORT}).json()
        assert [e["id"] for e in listed] == [job.experiment.id] and "samples" not in listed[0]
        assert doc.get("loop.phase_margin_designed").basis == "computed"
        assert doc.get("response.overshoot").basis == "measured"
        assert doc.machine.simulated is False or doc.machine.port == PORT

    def test_an_autotune_is_watched_and_its_gains_kept(self, board):
        board.links.control.arm(PORT)
        job = _run(board, loops.plan("hotend", 0, "autotune", 230, 1800, target_c=200, cycles=4))
        sent = board.sim.sent
        assert job.outcome == "done", job.error
        assert _heats(sent) == ["M303 E0 S200 C4"]
        assert set(job.result) >= {"kp", "ki", "kd"} and job.samples["actual"]
        assert _after(sent, "M303 E0 S200 C4")[-6:] == ["M108", *OFF, "M105"]
        doc = loops.document(job.experiment.id)
        assert doc.controller.designed.rule == "firmware_autotune"
        assert doc.controller.designed.basis == "identified"

    def test_a_perturbation_gives_the_frequency_response(self, board):
        board.links.control.arm(PORT)
        plan = loops.plan(
            "hotend",
            0,
            "perturbation",
            210,
            3000,
            centre_c=200,
            amplitude_c=2,
            period_s=60,
            periods=4,
            settle_s=600,
        )
        job = _run(board, plan, wait=90)
        assert job.outcome == "done", job.error
        assert _heats(board.sim.sent)[:3] == ["M104 S200", "M104 S202", "M104 S198"]
        doc = loops.document(job.experiment.id)
        first = doc.frequency[0]
        assert first.segments == 3 and first.trust in ("good", "fair")
        g = gcode.simulated_heaters(PORT)["T"].plant.response(first.frequency)
        assert first.magnitude == pytest.approx(abs(g), rel=0.25)

    def test_readings_slower_than_the_sample_period_set_each_target_at_its_time(self, slow_board):
        """Each reading takes two sample periods: fewer samples, and the step is still
        set at 300 s, with the reading after it -- not after 300 readings, which take
        600 s and come after the step's end at 540 s."""
        slow_board.reading_s = lambda t: 2.0
        clock = slow_board.clock
        plan = loops.plan("hotend", 0, "step", 200, 900, **STEP)
        job = loops.start(PORT, plan, clock=clock.now, sleep=clock.sleep)
        job.thread.join(60)
        sent = slow_board.sim.sent
        assert job.outcome == "done", job.error
        assert _heats(sent) == ["M104 S180", "M104 S185"]
        s = job.samples
        stepped = next(t for t, target in zip(s["t"], s["target"], strict=True) if target == 185)
        assert 300 < stepped <= 306
        assert len(s["t"]) < 540 / 2
        assert _after(sent, "M104 S185")[-5:] == [*OFF, "M105"]
        assert job.heater_off.startswith("heater off")

    def test_an_end_that_comes_before_a_target_is_set_ends_it_failed_and_off(self, slow_board):
        """The reading begun at 299 s takes 250 s: the step's end has come with its step
        never set. It is no step, so it is not done: it fails saying so, the heater off."""
        clock = slow_board.clock
        start = clock.t
        slow_board.reading_s = lambda t: 250.0 if 299 <= t - start < 300 else 0.0
        plan = loops.plan("hotend", 0, "step", 200, 900, **STEP)
        job = loops.start(PORT, plan, clock=clock.now, sleep=clock.sleep)
        job.thread.join(60)
        sent = slow_board.sim.sent
        assert job.outcome == "failed"
        assert "its end came before its target of 185 degC, due at 300 s, was set" in job.error
        assert _heats(sent) == ["M104 S180"]
        assert _after(sent, "M104 S180")[-5:] == [*OFF, "M105"]
        assert job.heater_off.startswith("heater off")
        assert job.error in jobs.get(job.job.id).reason


# ---- every way out ---------------------------------------------------------------------------


def _scripted(monkeypatch, replies=None, cls=ScriptedTransport):
    ScriptedTransport.instances.clear()
    links = gcode.PrinterLinks(
        factory=lambda port, baud: cls(port, baud, replies=replies or REPLIES)
    )
    monkeypatch.setattr(gcode, "_LINKS", links)
    devices.printer_status(PORT)
    links.control.arm(PORT)
    return links, ScriptedTransport.instances[0]


HOT = {
    **REPLIES,
    "M104 S180": ["ok"],
    "M104 S185": ["ok"],
    "M104 S0": ["ok"],
    "M140 S0": ["ok"],
    "M107": ["ok"],
    "M84": ["ok"],
}


class TestEveryWayOut:
    """Each end of an experiment, and the heater off after it."""

    def _plan(self):
        return loops.plan("hotend", 0, "step", 200, 900, **STEP)

    def _start(self, speed=200):
        fast = Fast(speed)
        return loops.start(PORT, self._plan(), clock=fast.now, sleep=fast.sleep)

    def test_a_reading_over_the_ceiling_ends_it(
        self, fake_arduino_cli, fresh_task_runner, monkeypatch
    ):
        links, board = _scripted(
            monkeypatch, {**HOT, "M105": ["ok T:250.00 /180.00 B:23.00 /0.00 @:255 B@:0"]}
        )
        job = self._start()
        job.thread.join(10)
        assert job.outcome == "failed" and "over the ceiling" in job.error
        # The target read back is not 0 on this board, which answers 180 whatever it is
        # sent: the stop follows.
        assert board.sent[-6:] == [*OFF, "M105", "M112"]
        assert "the stop was sent" in job.heater_off
        links.stop_all()

    def test_a_board_that_objects_ends_it(self, fake_arduino_cli, fresh_task_runner, monkeypatch):
        links, board = _scripted(
            monkeypatch,
            {
                **HOT,
                "M104 S180": ["Error:Heating failed"],
                "M105": ["ok T:23.00 /0.00 B:23.00 /0.00 @:0 B@:0"],
            },
        )
        job = self._start()
        job.thread.join(10)
        assert job.outcome == "failed" and "Heating failed" in job.error
        assert board.sent[-5:] == [*OFF, "M105"] and job.heater_off.startswith("heater off")
        links.stop_all()

    def test_a_board_that_restarts_ends_it(self, fake_arduino_cli, fresh_task_runner, monkeypatch):
        class Restarts(ScriptedTransport):
            reads = 0

            def write(self, data):
                super().write(data)
                if data.decode().strip() == "M105":
                    Restarts.reads += 1
                    if Restarts.reads == 5:
                        self.pending += b"start\n"

        links, board = _scripted(
            monkeypatch, {**HOT, "M105": ["ok T:23.00 /0.00 B:23.00 /0.00 @:0 B@:0"]}, Restarts
        )
        job = self._start()
        job.thread.join(10)
        assert job.outcome == "failed" and "restarted" in job.error
        assert board.sent[-5:] == [*OFF, "M105"]
        links.stop_all()

    def test_a_board_that_says_no_temperature_ends_it(
        self, fake_arduino_cli, fresh_task_runner, monkeypatch
    ):
        links, board = _scripted(monkeypatch, {**HOT, "M105": ["ok"]})
        job = self._start()
        job.thread.join(10)
        assert job.outcome == "failed" and "no temperature" in job.error
        # Nor does it say its target after the off: unconfirmed, so the stop follows.
        assert board.sent[-6:] == [*OFF, "M105", "M112"] and "stop was sent" in job.heater_off
        links.stop_all()

    def test_a_lost_link_ends_it_and_says_the_heater_is_not_known_off(
        self, fake_arduino_cli, fresh_task_runner, monkeypatch
    ):
        class Unplugged(ScriptedTransport):
            gone = False

            def write(self, data):
                if Unplugged.gone:
                    raise ToolchainError("/dev/ttyFAKE1: device disconnected")
                super().write(data)
                if data.decode().strip() == "M104 S180":
                    Unplugged.gone = True

        links, board = _scripted(
            monkeypatch, {**HOT, "M105": ["ok T:23.00 /0.00 B:23.00 /0.00 @:0 B@:0"]}, Unplugged
        )
        job = self._start()
        job.thread.join(10)
        assert job.outcome == "failed" and "disconnected" in job.error
        assert job.heater_off.startswith("not confirmed") and "thermal protection" in job.heater_off
        assert any("not answered" in line for line in job.record.log)  # each off line was tried
        links.stop_all()

    def test_a_cancel_ends_it(self, board):
        board.links.control.arm(PORT)
        job = self._start(speed=20)
        time.sleep(0.5)
        job.cancel()
        job.thread.join(10)
        assert job.outcome == "cancelled" and job.heater_off.startswith("heater off")
        assert _after(board.sim.sent, "M108")[-5:] == [*OFF, "M105"]

    def test_the_server_stopping_ends_it(self, board):
        board.links.control.arm(PORT)
        job = self._start(speed=20)
        time.sleep(0.5)
        said = devices.stop_jobs(timeout=10)
        assert any("made safe" in line for line in said), said
        assert job.outcome == "cancelled" and board.sim.sent[-5:] == [*OFF, "M105"]
        assert devices.at_work() == [f"{PORT}: control is armed"]

    def test_the_stop_ends_it_and_nothing_follows_it(self, board):
        board.links.control.arm(PORT)
        job = self._start(speed=20)
        time.sleep(0.5)
        devices.printer_control(PORT, "M112")
        job.thread.join(10)
        sent = board.sim.sent
        assert job.outcome == "cancelled" and "stop" in job.heater_off
        assert "M104 S0" not in _after(sent, "M112")  # a halted board is sent nothing more
        assert board.sim.heaters["T"].target == 0  # the stop is the heater off

    def test_an_autotune_past_its_ceiling_is_broken_and_the_heater_turned_off(self, board):
        """A heater with a long dead time swings a relay wide: ``K d (1 - e^(-theta/tau))``,
        about 19 degC each way here, past a ceiling 5 degC over the target."""
        board.sim.heaters["T"] = gcode.SimulatedHeater(
            cl.FOPDT(1.0, 60.0, 10.0), 23.0, (10.0, 0.1, 20.0), seed="wide"
        )
        board.links.control.arm(PORT)
        job = _run(board, loops.plan("hotend", 0, "autotune", 205, 1800, target_c=200, cycles=5))
        sent = board.sim.sent
        assert job.outcome == "failed" and "over the ceiling" in job.error
        assert _after(sent, "M303 E0 S200 C5")[-6:] == ["M108", *OFF, "M105"]
        assert job.heater_off.startswith("heater off") and board.sim.heaters["T"].target == 0

    def test_an_autotune_that_does_not_answer_its_break_gets_the_stop_at_once(
        self, fake_arduino_cli, fresh_task_runner, monkeypatch
    ):
        """A board that says a few temperatures, then nothing, and does not parse ``M108``
        early: it may still be in its autotune, where an off line would wait behind it, so
        the stop goes at once and no off line is sent first."""

        class Stubborn(ScriptedTransport):
            def write(self, data):
                cmd = data.decode().strip()
                if cmd == "M108":
                    self.sent.append(cmd)  # heard, and nothing said
                    return
                super().write(data)

        replies = {
            **HOT,
            "M105": ["ok T:23.00 /0.00 B:23.00 /0.00 @:0 B@:0"],
            "M303 E0 S200 C5": [" T:150.00 /200.00 @:255", " T:160.00 /200.00 @:255"],
            "M112": ["Error:Printer halted. kill() called!"],
        }
        links, board = _scripted(monkeypatch, replies, Stubborn)
        fast = Fast(200)
        job = loops.start(
            PORT,
            loops.plan("hotend", 0, "autotune", 230, 1800, target_c=200, cycles=5),
            clock=fast.now,
            sleep=fast.sleep,
        )
        job.thread.join(10)
        assert job.outcome == "failed" and "nothing said" in job.error
        assert _after(board.sent, "M303 E0 S200 C5") == ["M108", "M112"]
        assert "did not answer the break" in job.heater_off
        links.stop_all()

    def test_an_experiment_past_its_longest_time_is_ended(self, board):
        board.links.control.arm(PORT)
        tune = loops.plan("hotend", 0, "autotune", 260, 60, target_c=200, cycles=5)
        job = _run(board, tune)
        assert job.outcome == "failed" and "longest time" in job.error
        assert job.heater_off.startswith("heater off")


# ---- the latch, and the board's memory ---------------------------------------------------------


class TestTheLatchAndTheMemory:
    def test_nothing_heats_without_the_latch(self, board):
        with pytest.raises(gcode.ControlNotArmed):
            loops.start(PORT, loops.plan("hotend", 0, "step", 200, 900, **STEP))
        with pytest.raises(gcode.ControlNotArmed):
            loops.set_gains(PORT, "hotend", 0, 10, 0.5, 20)
        assert _heats(board.sim.sent) == [] and not any(
            ln.startswith("M301") for ln in board.sim.sent
        )

    def test_gains_set_are_read_back_and_not_saved(self, board):
        board.links.control.arm(PORT)
        said = loops.set_gains(PORT, "hotend", 0, 10.25, 0.3125, 20)
        assert said["sent"] == "M301 P10.25 I0.3125 D20" and said["matches"] and not said["saved"]
        assert board.sim.saves == 0 and "M500" not in board.sim.sent
        bed = loops.set_gains(PORT, "bed", 0, 40, 0.2, 150)
        assert bed["read_back"]["kp"] == 40 and bed["matches"]

    def test_the_board_s_memory_is_written_only_when_asked_by_name(self, board):
        with pytest.raises(ValueError, match="write_board_memory"):
            loops.save_settings(PORT)
        board.links.control.arm(PORT)
        with pytest.raises(ValueError, match="write_board_memory"):
            loops.save_settings(PORT, write_board_memory=False)
        assert "M500" not in board.sim.sent and board.sim.saves == 0
        board.links.control.disarm(PORT)
        with pytest.raises(gcode.ControlNotArmed):
            loops.save_settings(PORT, write_board_memory=True)
        board.links.control.arm(PORT)
        assert loops.save_settings(PORT, write_board_memory=True)["saved"]
        assert board.sim.sent.count("M500") == 1 and board.sim.saves == 1


# ---- can_now and the routes --------------------------------------------------------------------

STEP_BODY = {
    "port": PORT,
    "heater": "hotend",
    "kind": "step",
    "ceiling_c": 200,
    "max_duration_s": 900,
    **STEP,
}
VERBS = ["tune.start", "tune.cancel", "tune.read", "tune.set", "tune.save"]


def _ask(client, verb):
    post = client.post
    if verb == "tune.start":
        return post("/firmware/printers/loops/start", json=STEP_BODY)
    if verb == "tune.cancel":
        return post("/firmware/printers/loops/cancel", json={"port": PORT})
    if verb == "tune.read":
        return post("/firmware/printers/loops/read", json={"port": PORT})
    if verb == "tune.set":
        return post(
            "/firmware/printers/loops/set",
            json={"port": PORT, "heater": "hotend", "kp": 10, "ki": 0.5, "kd": 20},
        )
    return post("/firmware/printers/loops/save", json={"port": PORT})


def _idle(board, monkeypatch):
    board.links.control.arm(PORT)


def _down(board, monkeypatch):
    pass


def _task(board, monkeypatch):
    board.links.control.arm(PORT)
    active = SimpleNamespace(id="t1", title="upload", port=PORT, snapshot=lambda: {"id": "t1"})
    runner = SimpleNamespace(active=active)
    monkeypatch.setattr(firmware_api, "get_task_runner", lambda: runner)
    monkeypatch.setattr(tasks, "get_task_runner", lambda: runner)


def _tuning(board, monkeypatch):
    board.links.control.arm(PORT)
    slow = Fast(1)  # real time: it is still running when the route is asked
    loops.start(
        PORT, loops.plan("hotend", 0, "step", 200, 900, **STEP), clock=slow.now, sleep=slow.sleep
    )
    time.sleep(0.2)


CONDITIONS = {
    "armed-and-idle": _idle,
    "latch-down": _down,
    "a-task-holds-the-port": _task,
    "an-experiment-runs": _tuning,
}


@pytest.mark.parametrize("condition", list(CONDITIONS))
@pytest.mark.parametrize("verb", VERBS)
def test_can_now_agrees_with_the_route(board, monkeypatch, condition, verb):
    CONDITIONS[condition](board, monkeypatch)
    verdict = can.can_now(PORT)[verb]
    answer = _ask(TestClient(app), verb)
    said = f"{condition}/{verb}: can said {verdict}, route said {answer.status_code} {answer.text[:200]}"
    if verdict["ok"]:
        assert answer.status_code < 400, said
    else:
        assert answer.status_code >= 400 and verdict["why"] and verdict["kind"], said


def test_a_print_cannot_start_while_an_experiment_holds_the_port(board, monkeypatch):
    _tuning(board, monkeypatch)
    kept = devices.save_print_file("a.gcode", b"G28\n", machine="printer")
    assert can.can_now(PORT)["print.start"]["kind"] == "held"
    with pytest.raises(Exception, match="holds the port"):
        devices.start_print(PORT, kept.id)
    assert can.can_now(PORT)["level.read"]["ok"] is False


def test_the_loop_routes_publish_the_schema_and_read_a_document_back():
    client = TestClient(app)
    schema = client.get("/firmware/loops/schema").json()
    assert schema["properties"]["schema"]["const"] == "control/loop/1"
    assert client.post("/firmware/loops/validate", json={"schema": "nope"}).status_code == 422


def test_the_relay_in_the_simulator_sits_near_the_plant_s_ultimate_point():
    """The simulator's autotune reads its plant through the describing function, which
    reads a FOPDT's ultimate gain low (tests/test_control_loops.py); its Ku is under the
    plant's true one and its Tu within a fifth of the true period, the difference the
    relation's, the five-second hold's and the bias's moving."""
    fast = Fast(400)
    sim = gcode.SimulatedPrinter(
        "/dev/ttySIM", 115200, heaters=gcode.simulated_heaters("/dev/ttySIM"), clock=fast.now
    )
    link = gcode.GcodeLink("/dev/ttySIM", 115200, sim)
    v = gcode.parse_autotune(
        link.watch("M303 E0 S200 C6", lambda line: None, silence=15, limit=900)
    )["values"]
    true = cl.ultimate_of(sim.heaters["T"].plant)
    assert v["ku"] < true.gain
    assert v["tu"] == pytest.approx(true.period, rel=0.2)


def test_an_orphaned_experiment_is_ended_and_its_machine_made_safe(
    fake_arduino_cli, fresh_task_runner, monkeypatch
):
    """An experiment kept as running that nothing runs (the server died under it): when
    its port is next opened the heaters are turned off, as an orphaned print's are."""
    started = jobs.Job(
        id="20260101T000000000Z-dev_ttyFAKE1",
        kind=loops.TUNE.kind,
        machine=jobs.JobMachine(kind="printer", port=PORT),
        input=jobs.JobInput(name="a step of hotend 0"),
        started_at=datetime.now(timezone.utc),
    )
    # Kept as running by a server that is gone: its file, and no thread holding it.
    folder = private_folder(jobs.jobs_dir())
    (folder / f"{started.id}.json").write_text(started.model_dump_json(), encoding="utf-8")
    links, board = _scripted(monkeypatch, HOT)
    assert board.sent[-4:] == OFF
    assert jobs.get(started.id).outcome == "failed"
    links.stop_all()


def test_two_starts_at_once_are_one_experiment(board):
    board.links.control.arm(PORT)
    slow = Fast(1)
    plan = loops.plan("hotend", 0, "step", 200, 900, **STEP)
    results = []

    def go():
        try:
            results.append(loops.start(PORT, plan, clock=slow.now, sleep=slow.sleep))
        except Exception as exc:  # noqa: BLE001 -- the refusal is what is counted
            results.append(exc)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert sum(isinstance(r, loops.LoopJob) for r in results) == 1
