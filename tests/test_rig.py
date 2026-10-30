"""A rig photographed: a face pinned by its corners, its controls read off drawn
pictures at known values, held in carlos as the rig at those values with each
module's and lead's state, and a concert's frames followed into carlos."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from apothecary.cli.main import cli
from apothecary.rig import concert, look, panels, reading, simulated
from apothecary.vision.projection import CORNERS

# A made-up desktop synth, measured as a carlos catalogue entry is: two knobs, a
# fader, a switch and an encoder on its front, three sockets there and one on its back.
SYNTH = {
    "id": "made-up.synth",
    "maker": "Made Up",
    "model": "Synth",
    "category": "semi-modular",
    "summary": "A synth for the tests.",
    "fidelity": "sketch",
    "jacks": [
        {
            "name": "gate_in",
            "label": "GATE",
            "type": "input",
            "signal": "gate",
            "connector": "3.5mm",
        },
        {"name": "cv_out", "label": "CV", "type": "output", "signal": "cv", "connector": "3.5mm"},
        {
            "name": "spare_in",
            "label": "SPARE",
            "type": "input",
            "signal": "cv",
            "connector": "3.5mm",
        },
        {
            "name": "audio_out",
            "label": "OUT",
            "type": "output",
            "signal": "audio",
            "connector": "1/4in",
            "side": "back",
        },
    ],
    "parameters": [
        {"name": "cutoff", "label": "CUTOFF", "min": 0, "max": 127, "default": 64},
        {"name": "decay", "label": "DECAY", "min": 0, "max": 10, "default": 2},
        {"name": "level", "label": "LEVEL", "min": 0, "max": 127, "default": 100},
        {"name": "range", "label": "RANGE", "min": 0, "max": 1, "default": 0},
        {"name": "select", "label": "SELECT", "min": 0, "max": 127, "default": 0},
    ],
    "layout": {
        "box": {"width": 200, "height": 100, "depth": 80},
        "controls": {
            "cutoff": {"x": 0.15, "y": 0.3, "side": "front", "size": 1.2},
            "decay": {"x": 0.35, "y": 0.3, "side": "front"},
            "level": {"x": 0.15, "y": 0.75, "side": "front", "kind": "fader", "length": 0.3},
            "range": {"x": 0.35, "y": 0.75, "side": "front", "kind": "switch"},
            "select": {"x": 0.55, "y": 0.3, "side": "front", "kind": "encoder"},
        },
        "jacks": {
            "gate_in": {"x": 0.75, "y": 0.3, "side": "front"},
            "cv_out": {"x": 0.9, "y": 0.3, "side": "front"},
            "spare_in": {"x": 0.75, "y": 0.7, "side": "front"},
            "audio_out": {"x": 0.5, "y": 0.5, "side": "back"},
        },
    },
}
# A desk the camera never sees, with one socket a lead runs to.
DESK = {
    "id": "made-up.desk",
    "maker": "Made Up",
    "model": "Desk",
    "category": "mixer",
    "summary": "A desk for the tests.",
    "fidelity": "sketch",
    "jacks": [
        {
            "name": "in_1",
            "label": "IN 1",
            "type": "input",
            "signal": "audio",
            "connector": "1/4in",
            "side": "back",
        }
    ],
    "parameters": [],
    "layout": {
        "box": {"width": 300, "height": 90, "depth": 400},
        "jacks": {"in_1": {"x": 0.5, "y": 0.5, "side": "back"}},
    },
}
RIG = {
    "format": "carlos.patch",
    "version": 3,
    "name": "two synths and a desk",
    "modules": [
        {"id": "one", "type": "made-up.synth", "view": "front", "parameters": {"cutoff": 30}},
        {"id": "two", "type": "made-up.synth", "view": "front", "parameters": {}},
        {"id": "desk", "type": "made-up.desk", "view": "back", "parameters": {}},
    ],
    "connections": [
        {
            "source": {"module": "one", "jack": "cv_out"},
            "target": {"module": "two", "jack": "gate_in"},
        },
        {
            "source": {"module": "two", "jack": "audio_out"},
            "target": {"module": "desk", "jack": "in_1"},
        },
    ],
    "groups": [],
}


@pytest.fixture
def setup():
    return simulated.scene(json.loads(json.dumps(RIG)), [SYNTH, DESK])


def test_four_corners_make_the_one_mapping_and_it_goes_back():
    corners = [(0.2, 0.3), (0.7, 0.25), (0.75, 0.6), (0.15, 0.65)]
    onto = panels.face_onto(corners)
    for (x, y), (u, v) in zip(CORNERS, corners, strict=True):
        assert panels.apply(onto, x, y) == pytest.approx((u, v))
    back = panels.invert(onto)
    assert panels.apply(back, *panels.apply(onto, 0.3, 0.8)) == pytest.approx((0.3, 0.8))
    with pytest.raises(ValueError):
        panels.face_onto([(0.1, 0.1), (0.2, 0.2), (0.3, 0.3), (0.1, 0.5)])


def test_a_panel_is_one_face_of_an_entry_with_each_control_s_range():
    front = panels.panel(SYNTH, "front")
    assert (front.width_mm, front.height_mm) == (200, 100)
    assert [c.name for c in front.controls] == ["cutoff", "decay", "level", "range", "select"]
    assert {c.name: c.kind for c in front.controls}["level"] == "fader"
    assert [s.name for s in front.sockets] == ["gate_in", "cv_out", "spare_in"]
    back = panels.panel(SYNTH, "back")
    assert back.controls == [] and [s.name for s in back.sockets] == ["audio_out"]
    assert panels.panel({**SYNTH, "layout": {}}, "front") is None


def test_the_scene_pins_each_face_the_camera_sees(setup):
    assert sorted(setup.faces) == ["one", "two"]
    one, two = setup.faces["one"].corners, setup.faces["two"].corners
    # Side by side, the second to the right of the first, both inside the picture.
    assert one[1][0] < two[0][0]
    assert all(0 < u < 1 and 0 < v < 1 for u, v in one + two)


def test_a_drawn_picture_reads_back_at_the_values_it_was_drawn_at(setup, tmp_path):
    values = {
        "one": {"cutoff": 100, "decay": 1.5, "level": 20, "range": 1, "select": 50},
        "two": {"cutoff": 5, "decay": 9, "level": 127, "range": 0, "select": 0},
    }
    plugged = {
        "one": {"gate_in": False, "cv_out": True, "spare_in": False},
        "two": {"gate_in": True, "cv_out": False, "spare_in": True},
    }
    picture = tmp_path / "rig.png"
    simulated.draw(setup, values, plugged).save(picture)
    found = reading.read(setup, picture)
    by_module = {m.module: m for m in found.modules}
    for module in ("one", "two"):
        seen = {s.name: s for s in by_module[module].seen}
        for name in ("cutoff", "level"):
            assert seen[name].value == pytest.approx(values[module][name], abs=127 * 0.03)
        assert seen["decay"].value == pytest.approx(values[module]["decay"], abs=10 * 0.03)
        assert seen["range"].value == values[module]["range"]
        assert seen["select"].value is None and "without end" in seen["select"].why
        assert {p.name: p.plugged for p in by_module[module].plugs} == plugged[module]
    assert by_module["desk"].why.startswith("not in the picture")


def test_a_knob_with_no_pointer_to_see_is_not_read():
    from PIL import Image

    grey = look.Grey.of(Image.new("L", (400, 200), 90))
    seen, plugs = look.read_face(grey, panels.panel(SYNTH, "front"), CORNERS)
    assert {s.name: s.why for s in seen}["cutoff"] == "no pointer to see"
    assert {s.name: s.why for s in seen}["level"] == "no cap to see along its travel"
    assert all(p.plugged for p in plugs)  # no hole anywhere: read as plugged


def test_held_is_the_rig_at_the_values_read_with_each_module_s_and_lead_s_state(setup, tmp_path):
    values, plugged = simulated.at_rest(setup)
    values["one"]["cutoff"] = 90
    plugged["one"]["spare_in"] = True  # a plug no lead names
    plugged["two"]["gate_in"] = False  # the lead's far end pulled
    picture = tmp_path / "rig.png"
    simulated.draw(setup, values, plugged).save(picture)
    patch, states = reading.held(setup, reading.read(setup, picture))

    assert patch["display"]["mode"] == "irl"
    one = next(m for m in patch["modules"] if m["id"] == "one")
    assert one["parameters"]["cutoff"] == pytest.approx(90, abs=4)
    assert set(one["parameters"]) == {"cutoff", "decay", "level", "range"}  # not the encoder
    assert RIG["modules"][0]["parameters"] == {"cutoff": 30}  # the setup's rig is not changed

    assert states.modules["one"].level == "warn"
    assert "a plug in SPARE that no lead names" in states.modules["one"].says
    assert states.modules["one"].says[0] == "read: 4 of 5 controls on its front"
    assert any(
        line.startswith("not read: select, an encoder") for line in states.modules["one"].says
    )
    assert states.modules["two"].level == "ok"
    assert states.modules["desk"].level == "none"

    pulled, unseen = states.connections
    assert pulled.level == "fault"
    assert pulled.says == [
        "declared: nothing plugged into GATE on two",
        "seen: a plug in CV on one",
    ]
    assert unseen.level == "none"
    assert unseen.says == [
        "not seen: OUT on two is not in the picture",
        "not seen: IN 1 on desk is not in the picture",
    ]


def test_a_setup_refuses_what_it_cannot_show(setup):
    document = json.loads(setup.model_dump_json())
    with pytest.raises(ValidationError, match="no entry for it"):
        reading.Setup.model_validate({**document, "devices": [SYNTH]})
    with pytest.raises(ValidationError, match="which the rig does not have"):
        reading.Setup.model_validate({**document, "faces": {"three": document["faces"]["one"]}})
    with pytest.raises(ValidationError, match="four corners"):
        reading.Setup.model_validate(
            {**document, "faces": {"one": {"side": "front", "corners": [[0, 0], [1, 0], [1, 1]]}}}
        )
    with pytest.raises(ValidationError, match="not an apothecary.rig-setup"):
        reading.Setup.model_validate({**document, "version": 2})


def test_the_reader_is_measured_on_drawn_pictures(setup):
    measured = {row.kind: row for row in simulated.measure(setup, count=2)}
    assert set(measured) == {"knob", "fader", "switch", "encoder", "socket"}
    assert measured["encoder"].read == 0
    for kind in ("knob", "fader"):
        assert measured[kind].read == measured[kind].looked and measured[kind].worst < 0.05
    assert measured["switch"].mean == 0 and measured["socket"].mean == 0


@pytest.fixture
def a_carlos():
    """A stand-in for carlos on loopback: its catalogue routes, and what it was sent."""
    heard = []
    routes = {
        "/api/catalogue/devices/made-up.synth/examples": {
            "device": SYNTH["id"],
            "examples": {"simple": RIG, "complex": RIG},
        },
        "/api/catalogue/devices/made-up.synth": SYNTH,
        "/api/catalogue/devices/made-up.desk": DESK,
    }

    class Carlos(BaseHTTPRequestHandler):
        def _answer(self, status, body):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def do_GET(self):
            found = routes.get(self.path)
            self._answer(200 if found else 404, found or {"detail": "Not Found"})

        def do_POST(self):
            heard.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self._answer(200, {"ok": True})

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Carlos)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", heard
    server.shutdown()
    server.server_close()


def test_a_concert_is_followed_into_carlos_and_recorded(a_carlos, tmp_path):
    url, heard = a_carlos
    rig_doc, devices = reading.rig_from_carlos(url, "made-up.synth.complex")
    assert rig_doc["name"] == RIG["name"] and [d["id"] for d in devices] == [
        "made-up.desk",
        "made-up.synth",
    ]
    setup = simulated.scene(rig_doc, devices)
    folder = tmp_path / "concert"
    assert simulated.write_concert(setup, folder, songs=3, frames=2, every=10) == 6
    truth = [json.loads(line) for line in (folder / "truth.jsonl").read_text().splitlines()]
    assert truth[2]["happened"] and truth[2]["at"] == "2026-10-29T20:00:20+00:00"

    following = concert.Concert(folder, url=url, say=lambda line: None)
    assert following.follow() == 6
    record = [json.loads(line) for line in (folder / concert.RECORD).read_text().splitlines()]
    assert [line["picture"] for line in record] == [f"frame-000{n}.png" for n in range(1, 7)]
    assert record[0]["at"] == truth[0]["at"]
    assert record[4]["plugged"]["two"]["gate_in"] is False  # the third song pulled it
    assert "select" in record[0]["unread"]["one"]

    # The second frame of the first song holds where the first left off, so
    # carlos is sent one fewer than there are frames whenever two are the same.
    sent = [line["held"] for line in record]
    assert sent[0] is True and len(heard) == sent.count(True)
    cue = heard[0]
    assert cue["cue"]["number"] == "frame-0001" and cue["cue"]["fired_at"] == truth[0]["at"]
    held = cue["action"]["hold"]
    assert held["patch"]["display"]["mode"] == "irl"
    assert [d["id"] for d in held["devices"]] == ["made-up.desk", "made-up.synth"]


def test_the_rig_commands_simulate_read_follow_and_check_from_a_catalogue_folder(tmp_path):
    catalogue = tmp_path / "catalogue"
    (catalogue / "devices").mkdir(parents=True)
    (catalogue / "examples").mkdir()
    for entry in (SYNTH, DESK):
        (catalogue / "devices" / f"{entry['id']}.json").write_text(json.dumps(entry))
    (catalogue / "examples" / "made-up.synth.complex.json").write_text(json.dumps(RIG))
    rig_from = ["--catalogue", str(catalogue), "--example", "made-up.synth.complex"]
    runner = CliRunner()

    out = tmp_path / "concert"
    done = runner.invoke(
        cli, ["rig", "simulate", *rig_from, "--out", str(out), "--songs", "1", "--frames", "2"]
    )
    assert done.exit_code == 0, done.output
    assert (
        "2 frames of 'two synths and a desk'" in done.output
        and "faces in the picture: one, two" in done.output
    )

    done = runner.invoke(
        cli, ["rig", "read", str(out / "frame-0001.png"), "--setup", str(out / "setup.json")]
    )
    assert done.exit_code == 0, done.output
    assert "one (made-up.synth), its front:" in done.output
    assert "not read: an encoder turns without end" in done.output
    assert "desk (made-up.desk): not in the picture" in done.output

    (out / "frame-0003.png").write_bytes(b"half a frame")  # still being written
    done = runner.invoke(cli, ["rig", "follow", str(out)])
    assert done.exit_code == 0, done.output
    assert "frame-0003.png: not read" in done.output
    assert "2 frames read" in done.output and (out / concert.RECORD).exists()

    done = runner.invoke(cli, ["rig", "check", *rig_from, "--count", "1"])
    assert done.exit_code == 0, done.output
    assert "knob" in done.output and "prove the plumbing, not the eyes" in done.output

    refused = runner.invoke(cli, ["rig", "check", "--carlos", "http://192.168.1.4:4186"])
    assert refused.exit_code != 0 and "this machine only" in refused.output
