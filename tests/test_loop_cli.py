"""``apothecary loop``: identify, design, margins, documents and a simulated run, from the shell.

Each command against what the maths it calls says, on files written here from a known
plant; ``simulate`` on the simulated printer in the test's own process and state folder.
"""

from __future__ import annotations

import csv
import json
import re

import pytest
from click.testing import CliRunner

from apothecary import control_loops as cl
from apothecary.cli import cli
from apothecary.loop_document import SCHEMA

HEATER = cl.FOPDT(2.0, 60.0, 8.0)  # made up: no machine's


def _write(path, trace):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["t", "target", "actual", "power"])
        for row in zip(trace.t, trace.r, trace.y, trace.u, strict=True):
            w.writerow(row)
    return path


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    pid = cl.PID(kp=1.875, ki=0.03125, dt=1.0)
    trace = cl.closed_loop(
        HEATER, pid, lambda s: 200.0 if s < 60 else 205.0, 600, ambient=25.0, substeps=100
    )
    return _write(tmp_path_factory.mktemp("loop") / "step.csv", trace)


def run(*args):
    done = CliRunner().invoke(cli, ["loop", *map(str, args)])
    assert done.exit_code == 0, done.output
    return done.output


def test_identify_fits_the_plant_that_made_the_record(recorded):
    said = json.loads(run("identify", recorded, "--json"))
    assert (said["gain"], said["time_constant"], said["dead_time"]) == pytest.approx(
        (2.0, 60.0, 8.0), rel=1e-4
    )
    assert run("identify", recorded).startswith(
        "fit_fopdt: gain 2, time constant 60 s, dead time 8 s"
    )


def test_identify_from_a_step_asks_for_the_input_s_change(recorded):
    done = CliRunner().invoke(cli, ["loop", "identify", str(recorded), "--method", "areas"])
    assert done.exit_code != 0 and "--input-change" in done.output


def test_design_says_both_forms_the_line_unsent_and_the_margins():
    out = run(
        "design",
        "--gain",
        2,
        "--time-constant",
        30,
        "--dead-time",
        8,
        "--rule",
        "simc",
        "--kind",
        "pi",
        "--dt",
        0.01,
    )
    assert "parallel: Kp 0.9375  Ki 0.03125 /s  Kd 0 s" in out
    assert "line:     M301 P0.94 I0.0312 D0.00  (not sent)" in out
    # SIMC with tau_c = theta: the loop e^(-8 s)/(16 s), its gain margin pi, a hair less
    # for the hold of a controller sampled every hundredth of a second.
    assert re.search(r"gain margin 3\.1[34]", out)


def test_margins_of_a_pid_round_a_plant():
    out = run(
        "margins",
        "--gain",
        2,
        "--time-constant",
        30,
        "--dead-time",
        8,
        "--kp",
        0.9375,
        "--ki",
        0.03125,
        "--continuous",
    )
    assert "phase margin 61.35°" in out and "(continuous)" in out


def test_rules_name_their_sources_and_what_is_left_out():
    out = run("rules")
    assert all(name + ":" in out for name in cl.RULES)
    assert "left out:" in out and "chien_hrones_reswick" in out


def test_a_document_from_a_recorded_file_is_one_validate_reads_back(recorded, tmp_path):
    md = run("document", recorded, "--kind", "step", "--settle-s", 60)
    assert md.startswith("# Control loop: hotend 0") and "(a recorded file)" in md
    doc = json.loads(
        run("document", recorded, "--kind", "step", "--settle-s", 60, "--format", "json")
    )
    assert doc["schema"] == SCHEMA and doc["plant"]["gain"] == pytest.approx(2.0, rel=1e-4)
    path = tmp_path / "loop.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert run("validate", path).startswith(f"OK {SCHEMA} · hotend 0 · 1 experiments")
    assert run("validate", path, "--format", "md").startswith("# Control loop")
    doc["groups"][0]["figures"][0]["source"] = "nothing"
    path.write_text(json.dumps(doc), encoding="utf-8")
    bad = CliRunner().invoke(cli, ["loop", "validate", str(path)])
    assert bad.exit_code == 1 and "Invalid loop document" in bad.output


def test_the_schema_is_printed():
    assert json.loads(run("schema"))["title"] == "LoopDocument"


def test_simulate_runs_a_step_on_the_simulated_printer_and_prints_its_document(
    fake_arduino_cli, monkeypatch, tmp_path
):
    """In this process, on a state folder of the run's own: the variables it sets are
    set first here, so they are put back after."""
    for name in (
        "APOTHECARY_STATE_DIR",
        "APOTHECARY_TOOLS_DIR",
        "APOTHECARY_SERIAL_ENGINE",
        "APOTHECARY_SIMULATED_PRINTER",
        "APOTHECARY_SIMULATED_DEVKIT",
        "ARDUINO_CLI",
        "ESPTOOL",
    ):
        monkeypatch.setenv(name, "")
    done = CliRunner().invoke(
        cli,
        [
            "loop",
            "simulate",
            "step",
            "--ceiling",
            200,
            "--max-duration",
            900,
            "--base",
            180,
            "--step",
            5,
            "--settle",
            400,
            "--after",
            300,
            "--speed",
            1000,
            "--format",
            "json",
            "--keep",
            tmp_path / "run",
        ],
    )
    assert done.exit_code == 0, done.output
    doc = json.loads(done.output[done.output.index("{") :])
    assert doc["machine"]["simulated"] and doc["experiments"][0]["outcome"] == "done"
    assert doc["controller"]["on_machine"]["basis"] == "measured"
    assert (tmp_path / "run" / "state" / "loops").is_dir()


def test_simulate_refuses_a_plan_off_its_bounds(fake_arduino_cli, monkeypatch, tmp_path):
    for name in (
        "APOTHECARY_STATE_DIR",
        "APOTHECARY_TOOLS_DIR",
        "APOTHECARY_SERIAL_ENGINE",
        "APOTHECARY_SIMULATED_PRINTER",
        "APOTHECARY_SIMULATED_DEVKIT",
        "ARDUINO_CLI",
        "ESPTOOL",
    ):
        monkeypatch.setenv(name, "")
    done = CliRunner().invoke(
        cli,
        [
            "loop",
            "simulate",
            "step",
            "--ceiling",
            400,
            "--max-duration",
            900,
            "--keep",
            str(tmp_path / "r"),
        ],
    )
    assert done.exit_code != 0 and "cap" in done.output
