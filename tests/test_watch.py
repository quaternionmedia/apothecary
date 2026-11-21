"""`apothecary watch`: a running server's output and state, one line per thing that changed.

The server is stood in for by a getter answering from a dict, the serial ports by a
function, and the output by a file a thread writes to."""

from __future__ import annotations

import threading
import time

from click.testing import CliRunner

from apothecary.cli import watch as watching
from apothecary.cli.main import cli
from apothecary.cli.watch import LogReader, StateWatch, follow

ACCESS = 'INFO:     127.0.0.1:50000 - "{method} {path} HTTP/1.1" {code} OK'


def _fed(lines):
    reader = LogReader()
    out = []
    for line in lines:
        out += reader.feed(line)
    return out + reader.idle()


def test_a_post_and_an_error_are_said_and_the_page_s_reads_are_not():
    said = _fed(
        [
            ACCESS.format(method="GET", path="/firmware/printers/status", code=200),
            ACCESS.format(method="GET", path="/sites/garage", code=200),
            ACCESS.format(method="POST", path="/menu/resolve", code=200),
            ACCESS.format(method="POST", path="/slicer/slice", code=200),
            ACCESS.format(method="POST", path="/menu/resolve", code=500),
            ACCESS.format(method="GET", path="/favicon.ico", code=404),
        ]
    )
    assert [kind for kind, _ in said] == ["http", "http"]
    assert "POST /slicer/slice" in said[0][1] and said[1][1].endswith("500 OK")


def test_a_traceback_is_one_line_naming_apothecary_s_own_frame():
    said = _fed(
        [
            "ERROR:    Exception in ASGI application",
            "Traceback (most recent call last):",
            '  File "/x/site-packages/starlette/routing.py", line 1, in app',
            '  File "/x/apothecary/menu.py", line 700, in _fit',
            "    raise RingTooFull(name)",
            "apothecary.menu.RingTooFull: Pieces",
            ACCESS.format(method="GET", path="/sites/garage", code=200),
        ]
    )
    assert said == [
        ("error", 'traceback at menu.py", line 700, in _fit: apothecary.menu.RingTooFull: Pieces')
    ]


def test_a_restart_is_said_and_known_noise_is_not():
    said = _fed(
        [
            "INFO:     Started server process [42]",
            "UserWarning: Duplicate Operation ID slicer_tuning",
            "  warnings.warn(message",
            "INFO:     Application startup complete.",
            "something the server printed",
        ]
    )
    assert said == [
        ("server", "Started server process [42]"),
        ("log", "something the server printed"),
    ]


class _Server:
    """A getter answering each path from ``answers``; a path's answer may be a function of
    the query."""

    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def __call__(self, path, **query):
        self.asked.append((path, query))
        answer = self.answers.get(path, ConnectionError("no such route here"))
        return answer(**query) if callable(answer) else answer


def _state(**changed):
    answers = {
        "/slicer/slices": [{"file_id": "a.gcode"}],
        "/cam/cuts": [],
        "/jobs": [],
        "/firmware/printers/armed": {"armed": {}},
    }
    answers.update(changed)
    return answers


def test_the_first_read_learns_and_the_next_says_what_is_new():
    server = _Server(_state())
    watch = StateWatch(server, ports=dict)
    assert watch.step() == []
    server.answers["/slicer/slices"] = [{"file_id": "a.gcode"}, {"file_id": "b.gcode"}]
    server.answers["/slicer/slices/b.gcode"] = {
        "file_id": "b.gcode",
        "made": {"name": "cube"},
        "printer": {"path": "printer_1"},
        "settings": [{"name": "z_offset", "value": ["0.1"], "origin": "turn"}],
    }
    server.answers["/jobs"] = [
        {
            "id": "j1",
            "kind": "print",
            "input": {"name": "cube"},
            "machine": {"port": "/dev/ttyUSB0"},
        },
        {"id": "t1", "kind": "print", "machine": {"port": "/dev/ttyPOLL"}},
    ]
    said = watch.step()
    assert [kind for kind, _ in said] == ["slice", "job"]
    assert "made=cube" in said[0][1] and "z_offset=0.1(turn)" in said[0][1]
    assert said[1][1] == "new print j1 cube on /dev/ttyUSB0"
    server.answers["/jobs"][0].update(
        outcome="running", progress=0.42, detail={"stage": "printing"}
    )
    assert watch.step() == [("job", "j1 outcome=running stage=printing progress=42% reason=None")]
    assert watch.step() == []


def test_a_server_gone_is_said_once_and_its_return_once():
    server = _Server(_state())
    watch = StateWatch(server, ports=dict)
    watch.step()
    up = server.answers["/slicer/slices"]
    server.answers["/slicer/slices"] = ConnectionError("refused")
    assert [kind for kind, _ in watch.step()] == ["server"]
    assert watch.step() == []
    server.answers["/slicer/slices"] = up
    assert watch.step() == [("server", "answering again")]


def test_a_tuning_turn_and_what_it_applied_are_said():
    doc = {"applies_to": {"filament": "PLA"}, "turns": [], "settings": {}}
    server = _Server(_state(**{"/slicer/tuning": lambda **q: {"documents": [{"document": doc}]}}))
    watch = StateWatch(server, site="garage", printer="printer_1", ports=dict)
    watch.step()
    assert ("/slicer/tuning", {"site": "garage", "printer": "printer_1"}) in server.asked
    doc["turns"] = [{"id": "turn-1", "readings": [1, 2, 3]}]
    doc["settings"] = {"z_offset": {"value": 0.1, "source": "turn-1"}}
    said = watch.step()
    assert [kind for kind, _ in said] == ["turn", "turn", "applied"]
    assert said[0][1].startswith("turn-1 on ") and said[0][1].endswith(": 3 readings")


def test_a_board_s_log_is_read_from_its_end_and_its_errors_said():
    pages = {None: {"entries": [{"text": "old"}], "next": 1}, 1: {"entries": [], "next": 1}}

    def log(port, since=None):
        return pages[since]

    server = _Server(_state(**{"/firmware/printers/log": log}))
    watch = StateWatch(server, ports=lambda: {"/dev/ttyUSB0": "usb-FTDI"})
    first = watch.step()
    assert first and first[0][0] == "board" and "old" not in str(first)
    pages[1] = {
        "entries": [
            {"text": "ok T:200 /210 B:55 /60", "origin": "poll"},
            {"text": "echo:Unknown command: M999", "origin": "poll"},
            {"text": "G28", "origin": "hand"},
            {"text": "ok", "origin": "hand"},
        ],
        "next": 2,
    }
    pages[2] = {"entries": [], "next": 2}
    said = watch.step()
    assert ("serial", "/dev/ttyUSB0 None/poll: echo:Unknown command: M999") in said
    assert ("serial", "/dev/ttyUSB0 None/hand: G28") in said
    assert ("board", "/dev/ttyUSB0 {'targets': 'None -> (210.0, 60.0)'}") in said
    assert not any("ok" == text.rsplit(": ", 1)[-1] for _, text in said)


def test_the_output_is_followed_from_its_end(tmp_path):
    log = tmp_path / "served.log"
    log.write_text(ACCESS.format(method="POST", path="/before", code=200) + "\n")
    said = []
    stop = threading.Event()
    thread = threading.Thread(
        target=follow, args=(log, lambda k, t: said.append((k, t)), stop, 0.02)
    )
    thread.start()
    try:
        time.sleep(0.2)
        with log.open("a") as f:
            f.write(ACCESS.format(method="POST", path="/after", code=200) + "\n")
        deadline = time.monotonic() + 5
        while not said and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        stop.set()
        thread.join(timeout=2)
    assert len(said) == 1 and "/after" in said[0][1]


def test_the_command_reads_the_state_and_writes_each_line_to_the_file_too(tmp_path, monkeypatch):
    server = _Server(_state())
    calls = iter([[{"file_id": "a.gcode"}], [{"file_id": "a.gcode"}, {"file_id": "c.gcode"}]])
    server.answers["/slicer/slices"] = lambda: next(calls)
    server.answers["/slicer/slices/c.gcode"] = {"file_id": "c.gcode"}
    monkeypatch.setattr(watching, "http_getter", lambda base: server)
    monkeypatch.setattr(watching, "serial_ports", dict)
    events = tmp_path / "events.log"
    done = CliRunner().invoke(
        cli, ["watch", "--port", "6999", "--rounds", "2", "--every", "0", "--events", str(events)]
    )
    assert done.exit_code == 0, done.output
    kept = events.read_text().splitlines()
    assert [line.split(None, 2)[1] for line in kept] == ["watch", "slice"]
    assert "watching http://127.0.0.1:6999" in done.output and "c.gcode" in done.output


def test_site_and_printer_go_together():
    done = CliRunner().invoke(cli, ["watch", "--site", "garage", "--rounds", "1"])
    assert done.exit_code != 0 and "go together" in done.output
