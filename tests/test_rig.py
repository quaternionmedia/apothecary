"""A rig photographed: a face pinned by its corners, its controls read off drawn
pictures at known values, held in carlos as the rig at those values with each
module's and lead's state, and a concert's frames followed into carlos."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from apothecary.cli.main import cli
from apothecary.rig import concert, look, panels, reading, simulated
from apothecary.vision.projection import CORNERS

ROOT_DIR = Path(__file__).resolve().parents[1]

# A made-up desktop synth, measured as a carlos catalogue entry is: two knobs, a
# fader, a switch and an encoder on its front, three sockets there and one on its back;
# a desk the camera never sees, with one socket a lead runs to; and a rig of two
# synths and the desk, with a lead between them and one to the desk.
_CATALOGUE = json.loads(Path(__file__).with_name("rig_catalogue.json").read_text(encoding="utf-8"))
SYNTH, DESK, RIG = _CATALOGUE["synth"], _CATALOGUE["desk"], _CATALOGUE["rig"]


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


def _held_off(setup, tmp_path, values, plugged, scale: float = 1.0):
    picture = simulated.draw(setup, values, plugged)
    if scale != 1.0:
        picture = picture.resize((round(picture.width * scale), round(picture.height * scale)))
    picture.save(tmp_path / "rig.png")
    return reading.held(setup, reading.read(setup, tmp_path / "rig.png"))


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
    plugged["one"]["cv_out"] = False  # the lead's near end pulled
    patch, states = _held_off(setup, tmp_path, values, plugged)

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
    # The control not read has a state of its own, for carlos to draw it so; an
    # encoder never has a position to read, so it asks nothing of a person.
    unread = states.modules["one"].controls
    assert list(unread) == ["select"] and unread["select"].level == "none"
    assert unread["select"].says[0].startswith("not read: an encoder turns without end")
    assert states.modules["two"].level == "ok"
    assert states.modules["desk"].level == "none"

    # Each socket read has a state of its own when it has something to say.
    assert {name: j.level for name, j in states.modules["one"].jacks.items()} == {
        "cv_out": "fault",
        "spare_in": "warn",
    }
    assert states.modules["two"].jacks["gate_in"].says == ["seen: a plug in it"]

    pulled, unseen = states.connections
    assert pulled.level == "fault"
    assert pulled.says == [
        "declared: nothing plugged into CV on one",
        "seen: a plug in GATE on two",
    ]
    assert unseen.level == "none"
    assert unseen.says == [
        "not seen: OUT on two is not in the picture",
        "not seen: IN 1 on desk is not in the picture",
    ]


def test_a_plug_moved_to_a_socket_no_lead_names_is_held_moved_there(setup, tmp_path):
    values, plugged = simulated.at_rest(setup)
    plugged["two"]["gate_in"] = False  # the lead's plug, out of GATE on two
    plugged["one"]["spare_in"] = True  # and in SPARE on one: an input, a 3.5mm plug
    patch, states = _held_off(setup, tmp_path, values, plugged)

    # Held where the picture has it, as a warning, and said where it was.
    assert patch["connections"][0]["target"] == {"module": "one", "jack": "spare_in"}
    assert RIG["connections"][0]["target"] == {"module": "two", "jack": "gate_in"}
    moved = states.connections[0]
    assert (moved.target, moved.level) == ({"module": "one", "jack": "spare_in"}, "warn")
    assert moved.says == [
        "moved: its plug in GATE on two is in SPARE on one now, as the picture has it",
        "seen: a plug in CV on one",
        "seen: a plug in SPARE on one",
    ]
    assert states.modules["one"].jacks["spare_in"].says == [
        "a plug in it: the lead's from GATE on two, as the picture has it"
    ]
    assert states.modules["two"].jacks["gate_in"].says == [
        "empty: its lead's plug is in SPARE on one"
    ]
    # Not a stray, then: no module warns of a plug no lead names.
    assert not any("no lead names" in line for m in states.modules.values() for line in m.says)


def test_a_rig_re_patched_a_plug_at_a_time_is_followed_a_plug_at_a_time(tmp_path):
    # Two leads into the two synths' gates, each moved in turn to a SPARE.
    rig = json.loads(json.dumps(RIG))
    rig["connections"].append(
        {
            "source": {"module": "two", "jack": "cv_out"},
            "target": {"module": "one", "jack": "gate_in"},
        }
    )
    setup = simulated.scene(rig, [SYNTH, DESK])
    values, plugged = simulated.at_rest(setup)
    plugged["two"]["gate_in"], plugged["one"]["spare_in"] = False, True
    first, _ = _held_off(setup, tmp_path, values, plugged)
    assert first["connections"][0]["target"] == {"module": "one", "jack": "spare_in"}

    plugged["one"]["gate_in"], plugged["two"]["spare_in"] = False, True
    # Against the setup alone, two plugs are out and two are in, and either
    # could be either lead's: nothing is guessed.
    alone, _ = _held_off(setup, tmp_path, values, plugged)
    assert alone["connections"] == rig["connections"]
    # Against the leads as the last frame held them, one plug moved since.
    picture = tmp_path / "rig.png"
    second, states = reading.held(setup, reading.read(setup, picture), leads=first["connections"])
    assert [c["target"] for c in second["connections"][::2]] == [
        {"module": "one", "jack": "spare_in"},
        {"module": "two", "jack": "spare_in"},
    ]
    assert [lead.level for lead in states.connections] == ["ok", "none", "warn"]
    assert first["connections"][2]["target"] == {"module": "one", "jack": "gate_in"}


def test_no_move_is_guessed_where_the_picture_could_say_two_things(setup, tmp_path):
    values, plugged = simulated.at_rest(setup)
    plugged["two"]["gate_in"] = False
    plugged["one"]["spare_in"] = True
    # A plug no lead names in an output too: SPARE and CV on two could be a new
    # lead's two ends, and GATE on two a lead's plug pulled.
    plugged["two"]["cv_out"] = True
    patch, states = _held_off(setup, tmp_path, values, plugged)
    assert patch["connections"] == RIG["connections"]
    assert states.connections[0].level == "fault"
    assert states.modules["one"].jacks["spare_in"].level == "warn"
    assert states.modules["two"].jacks["cv_out"].says == ["a plug in it that no lead names"]


def test_a_socket_too_small_in_the_picture_is_not_read(setup, tmp_path):
    values, plugged = simulated.at_rest(setup)
    patch, states = _held_off(setup, tmp_path, values, plugged, scale=0.12)
    plugs = [p for m in reading.read(setup, tmp_path / "rig.png").modules for p in m.plugs]
    assert plugs and all(p.plugged is None for p in plugs)
    assert all(p.why.startswith("too small in the picture to read") for p in plugs)
    # The lead to it is drawn on the rig's word alone, and says so.
    gate = states.modules["two"].jacks["gate_in"]
    assert gate.level == "warn" and gate.says[0].startswith("not read: too small")
    assert states.modules["one"].jacks["spare_in"].level == "none"
    assert "not read: 3 of 3 sockets on its front" in states.modules["one"].says
    lead = states.connections[0]
    assert lead.level == "none"
    assert lead.says[0].startswith("not read: CV on one, too small in the picture to read")
    assert patch["connections"] == RIG["connections"]


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
def carlos_routes():
    return {
        "/api/catalogue/devices/made-up.synth/examples": {
            "device": SYNTH["id"],
            "examples": {"simple": RIG, "complex": RIG},
        },
        "/api/catalogue/devices/made-up.synth": SYNTH,
        "/api/catalogue/devices/made-up.desk": DESK,
    }


def test_a_concert_is_followed_into_carlos_and_recorded(a_carlos, tmp_path):
    url, heard, _ = a_carlos
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
    _, cue = heard[0]
    assert cue["cue"]["number"] == "frame-0001" and cue["cue"]["fired_at"] == truth[0]["at"]
    held = cue["action"]["hold"]
    assert held["patch"]["display"]["mode"] == "irl"
    assert [d["id"] for d in held["devices"]] == ["made-up.desk", "made-up.synth"]


def test_a_frame_whose_time_does_not_read_is_taken_at_its_files_time(tmp_path):
    """A camera with no clock writes 0000:00:00 00:00:00, and a PNG's ``taken`` text
    may say anything: neither is a time, so the frame is taken at its file's time
    rather than ending the follow."""
    from PIL import Image, PngImagePlugin

    jpeg, png = tmp_path / "no-clock.jpg", tmp_path / "said.png"
    exif = Image.Exif()
    exif.get_ifd(0x8769)[concert.EXIF_TAKEN] = "0000:00:00 00:00:00"
    Image.new("RGB", (8, 8)).save(jpeg, exif=exif)
    said = PngImagePlugin.PngInfo()
    said.add_text("taken", "the second song")
    Image.new("RGB", (8, 8)).save(png, pnginfo=said)
    for path in (jpeg, png):
        with Image.open(path) as image:
            at = concert.taken(path, image)
        assert datetime.fromisoformat(at) == datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc
        )


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


UNO_RIG = ROOT_DIR / "examples" / "rigs" / "uno-power-and-usb.json"


def test_a_rig_file_takes_apothecary_s_own_devices_and_asks_for_the_rest(tmp_path):
    rig_doc, devices = reading.rig_from_file(UNO_RIG)
    assert [d["id"] for d in devices] == [
        "apothecary.host",
        "apothecary.power-supply",
        "arduino.uno-r3",
    ]
    # The Uno's two sockets are laid out on the edge they share.
    edge = panels.panel(next(d for d in devices if d["id"] == "arduino.uno-r3"), "left")
    assert [s.name for s in edge.sockets] == ["usb", "power"] and edge.controls == []

    mixed = tmp_path / "mixed.json"
    mixed.write_text(
        json.dumps({**RIG, "modules": [*RIG["modules"], {"id": "uno", "type": "arduino.uno-r3"}]})
    )
    with pytest.raises(ValueError, match="made-up.desk is not one of apothecary's devices"):
        reading.rig_from_file(mixed)
    asked = []
    _, devices = reading.rig_from_file(
        mixed,
        lambda name: asked.append(name) or {"made-up.desk": DESK, "made-up.synth": SYNTH}[name],
    )
    assert asked == ["made-up.desk", "made-up.synth"] and len(devices) == 3


def test_a_rig_of_sockets_alone_is_laid_by_its_sockets_and_read(tmp_path):
    rig_doc, devices = reading.rig_from_file(UNO_RIG)
    setup = simulated.scene(rig_doc, devices)
    assert list(setup.faces) == ["uno"] and setup.faces["uno"].side == "left"
    assert all(0 < u < 1 and 0 < v < 1 for u, v in setup.faces["uno"].corners)
    measured = {row.kind: row for row in simulated.measure(setup, count=3)}
    assert set(measured) == {"socket"} and measured["socket"].mean == 0

    patch, states = _held_off(setup, tmp_path, {}, {"uno": {"usb": False, "power": True}})
    usb, power = states.connections
    assert usb.level == "fault" and usb.says[0] == "declared: nothing plugged into USB on uno"
    assert power.level == "none"  # a plug seen in the Uno; the supply is not in the picture
    assert power.says == [
        "seen: a plug in POWER on uno",
        "not seen: DC OUT on supply is not in the picture",
    ]


def test_rig_setup_pins_a_photograph_s_faces_by_their_corners_in_pixels(tmp_path):
    rig_doc, devices = reading.rig_from_file(UNO_RIG)
    drawn = simulated.scene(rig_doc, devices)
    picture = tmp_path / "uno.png"
    simulated.draw(drawn, {}, {"uno": {"usb": True, "power": False}}).save(picture)
    width, height = simulated.PICTURE
    pixels = ",".join(f"{u * width:.2f},{v * height:.2f}" for u, v in drawn.faces["uno"].corners)
    out = tmp_path / "pinned.json"
    runner = CliRunner()

    done = runner.invoke(
        cli,
        [
            "rig",
            "setup",
            "--rig",
            str(UNO_RIG),
            "--picture",
            str(picture),
            "--face",
            f"uno=left:{pixels}",
            "--out",
            str(out),
        ],
    )
    assert done.exit_code == 0, done.output
    assert "uno, its left: USB, POWER" in done.output
    pinned = reading.Setup.load(out)
    for got, want in zip(pinned.faces["uno"].corners, drawn.faces["uno"].corners, strict=True):
        assert got == pytest.approx(want, abs=1e-4)
    done = runner.invoke(cli, ["rig", "read", str(picture), "--setup", str(out)])
    assert done.exit_code == 0 and "plugs in: usb" in done.output

    for face, said in (
        ("uno=top:0,0,1,0,1,1,0,1", "uno's top has nothing on it to read"),
        ("uno=left:1,2,3", "a face is MODULE=SIDE:x1,y1,x2,y2,x3,y3,x4,y4"),
        ("piano=front:0,0,1,0,1,1,0,1", "which the rig does not have"),
    ):
        refused = runner.invoke(
            cli,
            [
                "rig",
                "setup",
                "--rig",
                str(UNO_RIG),
                "--face",
                face,
                "--out",
                str(tmp_path / "no.json"),
            ],
        )
        assert refused.exit_code != 0 and said in refused.output, refused.output
