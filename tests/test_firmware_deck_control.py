"""The Stream Deck + as a controller for the garage's machines (firmware/deck_control.py),
against the simulated deck and the simulated server's bench: the simulated Ender and router, pinned.

Every motion goes through what bounds a person's jog -- the control latch, the port's
dialect, its bounds -- so each test sends a turn and reads the machine's own answer. No
HID device and no serial port is opened."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from apothecary import jobs
from apothecary.api import app
from apothecary.firmware import deck, deck_control, devices, gcode, grbl
from apothecary.firmware.toolchains import PortHeld, ToolchainError
from apothecary.simulated import PRINTER, ROUTER


@pytest.fixture
def bench(family_bench, monkeypatch):
    """The simulated server's bench, and one simulated deck with the layout running on it."""
    monkeypatch.setenv(deck.SIMULATED_DECK_ENV, "SIMDECK0")
    monkeypatch.delenv(deck_control.CONTROL_ENV, raising=False)
    deck.reset_decks()
    one = deck.get_decks().get("SIMDECK0")
    controller = deck_control.DeckController(one).start()
    yield controller, one, family_bench
    controller.stop()
    deck_control.stop_all()
    deck.reset_decks()


def _router(links):
    return grbl.poll_router(links.get(ROUTER)).position


def _printer(links):
    return gcode.poll_printer(links.get(PRINTER)).position


def _turn(one, knob, steps):
    one.inject("knob-turn", knob, steps)


def _press(one, key):
    one.inject("key", key, True)
    one.inject("key", key, False)


def _choose_router(one):
    _press(one, 1)


def test_the_layout_is_drawn_and_sends_nothing(bench):
    controller, one, links = bench
    assert set(one.keys) == set(range(8)) and one.strip is not None
    assert [one.keys[i]["text"] for i in (0, 1, 2)] == ["PRINTER", "ROUTER", "STEP"]
    # Two classes of stop: one per machine, and one for everything that looks different
    # and stands last on the bottom row, nearest a hand on the knobs.
    assert (one.keys[3]["text"], one.keys[3]["small"], one.keys[3]["colour"]) == (
        "DISARM",
        "nothing armed",
        "grey",
    )
    assert [one.keys[i]["text"] for i in (4, 5, 7)] == ["STOP", "STOP", "STOP ALL"]
    assert [one.keys[i]["small"] for i in (4, 5, 7)] == ["printer_1", "cnc_router", "every machine"]
    assert one.keys[7]["colour"] == deck_control.STOP_ALL_COLOUR != one.keys[4]["colour"]
    assert one.keys[4]["colour"] == one.keys[5]["colour"] == deck_control.STOP_ONE_COLOUR
    assert one.strip["text"] == "printer_1 · disarmed" and "X " in one.strip["small"]
    assert controller.sent == []


def test_a_turn_while_control_is_not_armed_moves_nothing_and_says_so(bench):
    controller, one, links = bench
    _choose_router(one)
    before = _router(links)
    _turn(one, 0, 5)
    assert _router(links) == before and controller.sent == []
    assert "disarmed" in one.strip["small"]
    assert not links.control.armed(ROUTER)  # a turn arms nothing


def test_an_armed_router_is_jogged_by_the_knobs_in_steps_of_the_chosen_size(bench):
    controller, one, links = bench
    _choose_router(one)
    links.control.arm(ROUTER)
    start = _router(links)
    _turn(one, 0, 3)
    assert controller.sent == ["$J=G91 G21 X3 F1000"]
    assert _router(links)["x"] == pytest.approx(start["x"] + 3)
    _press(one, 2)  # the step: 1 mm -> 10 mm
    assert one.keys[2]["small"] == "10 mm"
    _turn(one, 1, -2)
    assert controller.sent[-1] == "$J=G91 G21 Y-20 F1000"
    assert _router(links)["y"] == pytest.approx(start["y"] - 20)
    _press(one, 2)  # and round to 0.1 mm
    _turn(one, 2, 4)
    assert controller.sent[-1] == "$J=G91 G21 Z0.4 F1000"
    assert "· armed " in one.strip["text"] and "disarmed" not in one.strip["text"]


def test_a_jog_past_the_dialects_bound_is_refused_before_the_port(bench):
    controller, one, links = bench
    _choose_router(one)
    links.control.arm(ROUTER)
    start = _router(links)
    _press(one, 2)
    _turn(one, 0, 70)  # 700 mm, over the router's 600
    assert controller.sent == [] and _router(links) == start
    assert "refused" in one.strip["small"] and "600" in one.strip["small"]


def test_a_printer_jog_is_one_act_that_ends_absolute_and_one_out_of_bounds_sends_nothing(bench):
    """The knobs jog a printer as the page's pad does (``devices.printer_jog``): relative,
    the move and absolute as one act on the port."""
    controller, one, links = bench
    links.control.arm(PRINTER)
    start = _printer(links)
    _turn(one, 2, -1)
    assert controller.sent == ["G1 Z-1 F3000"]
    log = [e["text"] for e in links.log_for(PRINTER).since(0)["entries"] if e["kind"] == "tx"]
    assert [line for line in log if line[0] == "G"][-3:] == ["G91", "G1 Z-1 F3000", "G90"]
    assert _printer(links)["z"] == pytest.approx(start["z"] - 1)
    assert links.get(PRINTER)._t.relative is False
    controller.sent.clear()
    before = links.log_for(PRINTER).next_index
    _press(one, 2)
    _turn(one, 0, 40)  # 400 mm, over the printer's 300: bounded before the port
    assert controller.sent == [] and "beyond 300" in one.strip["small"]
    after = links.log_for(PRINTER).since(before)["entries"]
    assert not [e for e in after if e["kind"] == "tx" and e["text"] in ("G91", "G90")]
    assert links.get(PRINTER)._t.relative is False
    assert _printer(links)["x"] == start["x"]


def test_the_printers_fourth_knob_extrudes_within_the_bound(bench):
    controller, one, links = bench
    links.control.arm(PRINTER)
    _turn(one, 3, 2)
    assert controller.sent == ["M83", "G1 E2 F200"]
    controller.sent.clear()
    _turn(one, 3, 11)  # 11 mm, over the 10 mm bound
    assert controller.sent == ["M83"] and "extrusion beyond 10" in one.strip["small"]


def test_the_routers_fourth_knob_turns_the_spindle_only_while_it_turns_and_within_its_cap(bench):
    controller, one, links = bench
    _choose_router(one)
    links.control.arm(ROUTER)
    _turn(one, 3, 2)
    assert controller.sent == [] and "spindle off" in one.strip["small"]
    devices.printer_control(ROUTER, "M3 S12000")
    _turn(one, 3, 2)
    assert controller.sent == ["M3 S14000"]
    _turn(one, 3, 99)
    assert controller.sent[-1] == f"M3 S{grbl.SPINDLE_MAX_RPM}"
    _turn(one, 3, -99)
    assert controller.sent[-1] == "M3 S1000"  # down to one step, never to nothing
    assert _spindle_on(links)
    assert " S " in one.strip["small"]  # the fourth quantity is on the strip


def test_the_spindle_is_not_turned_from_a_reading_that_is_old(bench):
    """A cut holding the port answers a poll with its last reading: the knob turns the
    spindle from what it reads now, or not at all."""
    from datetime import timedelta

    controller, one, links = bench
    _choose_router(one)
    links.control.arm(ROUTER)
    devices.printer_control(ROUTER, "M3 S12000")
    real = controller.poll

    def old(port):
        status = real(port)
        return status.model_copy(update={"polled_at": status.polled_at - timedelta(seconds=30)})

    controller.poll = old
    _turn(one, 3, -5)
    assert controller.sent == [] and "not read just now" in one.strip["small"]
    assert grbl.poll_router(links.get(ROUTER)).spindle.target == 12000


def _both_going(links):
    """The router's spindle on and the printer's hotend heating: what each stop undoes."""
    links.control.arm(ROUTER)
    links.control.arm(PRINTER)
    devices.printer_control(ROUTER, "M3 S8000")
    devices.printer_control(PRINTER, "M104 S200")
    links.control.disarm(ROUTER)
    links.control.disarm(PRINTER)


def _spindle_on(links):
    return grbl.poll_router(links.get(ROUTER)).spindle.on


def _printer_halted(links):
    try:
        gcode.poll_printer(links.get(PRINTER))
    except Exception as exc:  # noqa: BLE001 -- a halted printer answers with its halt
        return "halted" in str(exc)
    return False


def test_a_machines_own_stop_key_stops_that_machine_alone_whatever_the_latch_says(bench):
    controller, one, links = bench
    _both_going(links)
    assert _spindle_on(links)
    _press(one, 5)  # cnc_router's
    assert controller.sent == ["stop cnc_router"]
    assert "STOP sent to cnc_router" in one.strip["small"] and "printer_1" not in one.strip["small"]
    assert not _spindle_on(links) and not _printer_halted(links)


def test_the_printers_own_stop_key_halts_the_printer_and_leaves_the_router_be(bench):
    controller, one, links = bench
    _both_going(links)
    _press(one, 4)  # printer_1's
    assert controller.sent == ["stop printer_1"]
    assert _printer_halted(links) and _spindle_on(links)


def test_a_stop_key_disarms_the_machine_it_stops_and_the_next_turn_moves_nothing(bench):
    controller, one, links = bench
    _choose_router(one)
    links.control.arm(ROUTER)
    links.control.arm(PRINTER)
    _press(one, 5)  # cnc_router's
    assert not links.control.armed(ROUTER) and links.control.armed(PRINTER)
    assert one.strip["text"] == "cnc_router · disarmed"
    before = _router(links)
    _turn(one, 0, 1)
    assert controller.sent == ["stop cnc_router"] and _router(links) == before
    assert "disarmed" in one.strip["small"]
    _press(one, 7)  # every machine's
    assert not links.control.armed(PRINTER)


def test_the_everything_key_reaches_each_machines_own_stop(bench):
    controller, one, links = bench
    _both_going(links)
    seen = []
    real = controller.send

    def spy(port, line):
        seen.append((port, line))
        return real(port, line)

    controller.send = spy
    _press(one, 7)
    # Each by its own dialect's word, and at once: neither waits for the other.
    assert sorted(seen) == [(PRINTER, "M112"), (ROUTER, "RESET")]
    assert controller.sent == ["stop printer_1", "stop cnc_router"]
    assert _printer_halted(links) and not _spindle_on(links)
    assert "STOP sent to printer_1, cnc_router" in one.strip["small"]


def test_the_everything_key_goes_on_stopping_when_one_machine_cannot_be_reached(bench):
    controller, one, links = bench
    _both_going(links)
    controller.resolve = lambda machine: ROUTER if machine.name == "cnc_router" else None
    controller.others = lambda kind=None: []
    _press(one, 7)
    assert controller.sent == ["stop cnc_router"] and not _spindle_on(links)
    assert "not printer_1 (no board pinned)" in one.strip["small"]


def test_a_stop_reaches_a_machine_that_is_pinned_somewhere_else(bench):
    """The printer pinned to another site's node, as the bench's Ender is: its board is
    the one printer this server knows, so the knobs find it; and were there no telling
    it from another, its stop key and the everything key would still reach it, by its
    kind."""
    controller, one, links = bench
    state = devices.get_state()
    from apothecary.simulated import BOARD, SITE

    assert state.clear_binding(SITE, BOARD)
    state.set_binding("apothecary", "creality_v422", devices.stable_identity(PRINTER))
    assert deck_control.pinned_port(deck_control.MACHINES[0]) == PRINTER
    assert deck_control.machine_ports("printer") == [PRINTER]
    assert set(deck_control.machine_ports()) == {PRINTER, ROUTER}
    _both_going(links)
    _press(one, 4)  # the printer's own stop
    assert controller.sent == ["stop printer_1"] and _printer_halted(links)
    # Not told from another of its kind: every board of that kind is stopped.
    controller.sent.clear()
    controller.resolve = lambda machine: None
    _press(one, 5)
    assert controller.sent == [f"stop router on {ROUTER}"] and not _spindle_on(links)
    controller.sent.clear()
    _press(one, 7)
    assert sorted(controller.sent) == [f"stop printer on {PRINTER}", f"stop router on {ROUTER}"]


def test_the_everything_key_stops_a_machine_that_is_neither_of_the_decks_two(bench):
    controller, one, links = bench
    _both_going(links)
    controller.resolve = lambda machine: PRINTER if machine.kind == "printer" else None
    controller.others = lambda kind=None: [] if kind else [PRINTER, ROUTER]
    _press(one, 7)
    assert controller.sent == ["stop printer_1", f"stop the machine on {ROUTER}"]
    assert not _spindle_on(links) and _printer_halted(links)


def test_the_everything_key_does_not_wait_for_one_machine_to_reach_the_next(bench):
    """Each stop goes on its own: a machine slow to answer its stop holds up no other's."""
    controller, one, links = bench
    _both_going(links)
    real, reached = controller.send, threading.Event()

    def printer_is_slow(port, line):
        if port == PRINTER:
            assert reached.wait(5), "the router's stop waited for the printer's"
        else:
            reached.set()
        return real(port, line)

    controller.send = printer_is_slow
    _press(one, 7)
    assert controller.sent == ["stop printer_1", "stop cnc_router"]


def test_the_everything_key_goes_on_stopping_when_one_machine_refuses_its_stop(bench):
    controller, one, links = bench
    _both_going(links)
    real = controller.send

    def printer_refuses(port, line):
        if port == PRINTER:
            raise ToolchainError("no answer")
        return real(port, line)

    controller.send = printer_refuses
    _press(one, 7)
    assert controller.sent == ["stop cnc_router"] and not _spindle_on(links)
    assert "STOP sent to cnc_router; not printer_1 (no answer)" in one.strip["small"]


def test_a_stop_that_reaches_no_machine_says_so(bench):
    controller, one, links = bench
    controller.resolve = lambda machine: None
    controller.others = lambda kind=None: []
    _press(one, 7)
    assert controller.sent == []
    assert one.strip["small"].startswith("STOP reached nothing; not printer_1 (no board pinned)")


def _silent(port):
    raise ToolchainError("no answer within 2 s")


def test_a_jog_on_a_port_another_holds_moves_nothing_and_says_who_holds_it(bench):
    controller, one, links = bench
    links.control.arm(ROUTER)
    _choose_router(one)
    start = _router(links)

    def held(port, axis, mm, feed):
        raise PortHeld(f"{port} is held by a print")

    controller.jog = held
    _turn(one, 0, 5)
    assert controller.sent == [] and _router(links) == start
    assert one.strip["small"].startswith(f"{ROUTER} is held by a print")  # not a refusal


def test_a_jog_whose_machine_does_not_answer_its_poll_moves_nothing(bench):
    controller, one, links = bench
    links.control.arm(ROUTER)
    _choose_router(one)
    start = _router(links)
    controller.poll = _silent
    _turn(one, 0, 5)
    assert controller.sent == [] and _router(links) == start
    assert "cnc_router: no answer within 2 s" in one.strip["small"]


def test_the_fourth_knob_extrudes_nothing_when_the_printer_does_not_answer(bench):
    controller, one, links = bench
    links.control.arm(PRINTER)
    controller.poll = _silent
    _turn(one, 3, 2)  # printer_1 is chosen
    assert controller.sent == []
    assert "printer_1: no answer within 2 s" in one.strip["small"]


def test_a_key_for_one_kind_never_moves_a_board_of_another(bench):
    controller, one, links = bench
    links.control.arm(ROUTER)
    start = _router(links)
    controller.resolve = lambda machine: ROUTER  # the router has taken the printer's port
    _turn(one, 0, 5)  # printer_1 is chosen
    assert controller.sent == [] and _router(links) == start
    assert f"{ROUTER} is not a printer" in one.strip["small"]


def test_a_machine_with_no_board_pinned_says_so(bench):
    controller, one, links = bench
    controller.resolve = lambda machine: None
    _turn(one, 0, 1)
    assert controller.sent == [] and "no board pinned" in one.strip["small"]


def test_the_layout_starts_and_stops_by_a_route_and_by_the_environment(bench, monkeypatch):
    controller, one, links = bench
    controller.stop()
    client = TestClient(app)
    off = client.get("/firmware/decks/SIMDECK0/control").json()
    assert off["running"] is False and set(off) == {"running", "can"}  # with the deck's answer
    started = client.post("/firmware/decks/SIMDECK0/control", json={"on": True}).json()
    assert started["running"] and started["machine"] == "printer_1" and started["sent"] == []
    assert client.get("/firmware/decks/SIMDECK0/control").json()["running"] is True
    stopped = client.post("/firmware/decks/SIMDECK0/control", json={"on": False}).json()
    assert stopped["running"] is False and set(stopped) == {"running", "can"}
    assert client.post("/firmware/decks/NOPE/control", json={"on": True}).status_code == 404
    assert deck_control.start_all() == []  # asked for by neither the environment nor a route
    monkeypatch.setenv(deck_control.CONTROL_ENV, "1")
    assert deck_control.start_all() == ["SIMDECK0"]
    deck_control.stop_all()


def test_a_stopped_layout_hears_nothing(bench):
    controller, one, links = bench
    controller.stop()
    links.control.arm(PRINTER)
    _turn(one, 2, -1)
    assert controller.sent == []


# --- arming: two sequential long presses on the machine's key ---------------------------


def _held(controller, key, down, seconds):
    """A key reported pressed at ``down`` and let go ``seconds`` later."""
    controller.handle(deck.DeckEvent(1, "key", key, True, at=down))
    controller.handle(deck.DeckEvent(2, "key", key, False, at=down + seconds))
    return down + seconds


def test_the_windows_are_named():
    assert (deck_control.LONG_PRESS_S, deck_control.ARM_WINDOW_S) == (0.8, 5.0)


def test_one_long_press_alone_arms_nothing_and_says_what_the_next_will_do(bench):
    controller, one, links = bench
    _held(controller, 1, 100.0, 1.0)
    assert not links.control.armed(ROUTER)
    assert controller.machine.name == "cnc_router"
    assert "again within 5 s to arm" in one.strip["small"]


def test_two_long_presses_in_time_arm_that_machines_control_through_the_latch(bench):
    controller, one, links = bench
    ended = _held(controller, 1, 100.0, 1.0)
    _held(controller, 1, ended + 2.0, 1.0)  # 2 s after the first let go
    assert links.control.armed(ROUTER) and not links.control.armed(PRINTER)
    assert 290 <= links.control.seconds_left(ROUTER) <= deck_control.gcode.CONTROL_TTL_S
    assert "cnc_router · armed" in one.strip["text"]
    start = _router(links)
    _turn(one, 0, 2)  # and what it armed is what the knobs may now move
    assert _router(links)["x"] == pytest.approx(start["x"] + 2)


def test_a_second_long_press_begun_in_time_arms_however_long_it_is_held(bench):
    """As a hand does it: the second begun 3.3 s after the first was let go and held 3.2 s,
    so let go 6.5 s after it."""
    controller, one, links = bench
    ended = _held(controller, 1, 100.0, 2.7)
    _held(controller, 1, ended + 3.3, 3.2)
    assert links.control.armed(ROUTER)


def test_a_second_long_press_after_the_window_arms_nothing(bench):
    controller, one, links = bench
    ended = _held(controller, 1, 100.0, 1.0)
    _held(controller, 1, ended + deck_control.ARM_WINDOW_S + 0.5, 1.0)
    assert not links.control.armed(ROUTER)
    assert "again within 5 s to arm" in one.strip["small"]  # it is a first press now


def test_a_short_press_or_another_key_between_the_two_breaks_the_pair(bench):
    controller, one, links = bench
    ended = _held(controller, 1, 100.0, 1.0)
    _held(controller, 1, ended + 0.5, 0.1)  # a short press of the same key
    _held(controller, 1, ended + 1.0, 1.0)
    assert not links.control.armed(ROUTER)
    ended = _held(controller, 1, 200.0, 1.0)
    _press(one, 2)  # the step key
    _held(controller, 1, ended + 1.0, 1.0)
    assert not links.control.armed(ROUTER)
    ended = _held(controller, 1, 300.0, 1.0)
    _turn(one, 0, 1)  # a knob
    _held(controller, 1, ended + 1.0, 1.0)
    assert not links.control.armed(ROUTER)


def test_long_presses_of_two_different_keys_do_not_make_a_pair(bench):
    controller, one, links = bench
    ended = _held(controller, 0, 100.0, 1.0)
    _held(controller, 1, ended + 1.0, 1.0)
    assert not links.control.armed(ROUTER) and not links.control.armed(PRINTER)


def test_a_short_press_alone_never_arms_however_often_it_is_pressed(bench):
    controller, one, links = bench
    for n in range(6):
        _held(controller, 1, 100.0 + n, 0.2)
    assert not links.control.armed(ROUTER)


def test_arming_a_machine_with_no_board_says_so_and_arms_nothing(bench):
    controller, one, links = bench
    controller.resolve = lambda machine: None
    ended = _held(controller, 1, 100.0, 1.0)
    _held(controller, 1, ended + 1.0, 1.0)
    assert not links.control.armed(ROUTER) and "no board pinned" in one.strip["small"]


def test_the_page_chooses_what_the_knobs_move_and_their_step_as_the_keys_do(bench):
    """A machine chosen by its name or by its board's port, and a step, from the page: the
    keys and the strip redrawn as the deck's own keys would leave them, nothing armed and
    nothing sent; what the deck has not got is refused."""
    controller, one, links = bench
    controller.choose(machine="cnc_router")
    assert controller.machine.name == "cnc_router"
    assert one.keys[1]["colour"] == "green" and one.keys[0]["colour"] == "grey"
    assert one.strip["text"].startswith("cnc_router · ")
    controller.choose(port=PRINTER)  # the port printer_1's board is on
    assert controller.machine.name == "printer_1" and one.keys[0]["colour"] == "green"
    controller.set_step(10.0)
    assert controller.step_mm == 10.0 and one.keys[2]["small"] == "10 mm"
    assert controller.sent == []
    assert not links.control.armed(PRINTER) and not links.control.armed(ROUTER)
    with pytest.raises(ValueError, match="its machines are printer_1, cnc_router"):
        controller.choose(machine="lathe")
    with pytest.raises(ValueError, match="no machine of the deck's"):
        controller.choose(port="/dev/ttyNOPE")
    with pytest.raises(ValueError, match="the deck's steps are 0.1, 1, 10 mm"):
        controller.set_step(50.0)


def test_the_knobs_are_read_and_chosen_by_route_while_they_run(bench):
    controller, one, links = bench
    controller.stop()
    client = TestClient(app)
    assert client.get("/firmware/decks/control").json() == {"controls": []}
    refused = client.put("/firmware/decks/SIMDECK0/control", json={"machine": "cnc_router"})
    assert refused.status_code == 409 and "not started" in refused.json()["detail"]
    client.post("/firmware/decks/SIMDECK0/control", json={"on": True})
    [knobs] = client.get("/firmware/decks/control").json()["controls"]
    assert knobs["deck"] == "SIMDECK0" and knobs["machines"] == ["printer_1", "cnc_router"]
    assert knobs["steps_mm"] == [0.1, 1.0, 10.0] and knobs["machine"] == "printer_1"
    chosen = client.put(
        "/firmware/decks/SIMDECK0/control", json={"port": ROUTER, "step_mm": 0.1}
    ).json()
    assert (chosen["machine"], chosen["port"], chosen["step_mm"]) == ("cnc_router", ROUTER, 0.1)
    assert client.get("/firmware/decks/control").json()["controls"][0]["machine"] == "cnc_router"
    bad = client.put("/firmware/decks/SIMDECK0/control", json={"step_mm": 50})
    assert bad.status_code == 422 and "0.1, 1, 10 mm" in bad.json()["detail"]
    deck_control.stop_all()


# --- nothing a hand does waits behind anything else -----------------------------------


@pytest.fixture
def slow(bench, monkeypatch):
    """A layout whose machine answers only when let: ``poll`` waits on ``gate``, and what
    was sent is kept in order. The port is a router's by the stand-ins' word alone."""
    controller, one, _ = bench
    controller.stop()
    gate, polling, sent = threading.Event(), threading.Event(), []

    def poll(port):
        polling.set()
        assert gate.wait(10), "the test never let the machine answer"
        return None

    monkeypatch.setattr(deck_control.devices, "known_device", lambda port: None)
    monkeypatch.setattr(deck_control.devices, "machine_kind", lambda device: "router")
    monkeypatch.setattr(deck_control.devices, "emergency_stop_for", lambda port: "RESET")
    mine = deck_control.DeckController(
        one,
        resolve=lambda machine: "/dev/slow",
        send=lambda port, line: sent.append(line),
        poll=poll,
        armed=lambda port: 0.0,  # disarmed to the tick, so it asks the machine nothing
        jog=lambda port, axis, mm, feed: sent.append(f"$J=G91 G21 {axis}{mm:g} F{feed}"),
        others=lambda kind=None: [],
    )
    mine.machine = deck_control.MACHINES[1]
    mine.start()
    yield mine, gate, polling, sent
    gate.set()
    mine.stop()


def _event(kind, index, value, seq=1):
    return deck.DeckEvent(seq, kind, index, value)


def test_the_reader_is_not_held_by_a_machine_that_is_slow_to_answer(slow):
    controller, gate, polling, sent = slow
    began = time.monotonic()
    controller.hear(_event("knob-turn", 0, 1))
    assert polling.wait(5)  # the layout's own thread is asking the machine, and waiting
    controller.hear(_event("key", 2, True))
    controller.hear(_event("knob-turn", 1, 1))
    assert time.monotonic() - began < 2 and sent == []
    gate.set()
    assert controller.settle(10)
    assert sent == ["$J=G91 G21 X1 F1000", "$J=G91 G21 Y10 F1000"]  # in order, STEP between


def test_turns_of_one_knob_that_wait_together_go_as_one_jog_of_their_sum(slow):
    controller, gate, polling, sent = slow
    controller.hear(_event("knob-turn", 2, 1))
    assert polling.wait(5)
    for steps in (1, 2, -1, 1):
        controller.hear(_event("knob-turn", 0, steps))
    controller.hear(_event("knob-turn", 1, 1))
    controller.hear(_event("knob-turn", 1, -1))  # there and back: nothing to send
    gate.set()
    assert controller.settle(10)
    assert sent == ["$J=G91 G21 Z1 F1000", "$J=G91 G21 X3 F1000"]


def test_a_stop_key_is_sent_at_once_and_nothing_turned_before_it_is_sent_after_it(slow):
    controller, gate, polling, sent = slow
    controller.hear(_event("knob-turn", 0, 5))
    assert polling.wait(5)  # that jog is taken up, the machine not yet answering
    controller.hear(_event("knob-turn", 1, 5))  # and this one waits behind it
    controller.hear(_event("key", 5, True))  # the router's own stop
    assert sent == ["RESET"]  # gone already, the machine still not answering the jog
    gate.set()
    assert controller.settle(10)
    assert sent == ["RESET"], sent  # neither the jog taken up nor the one waiting
    controller.hear(_event("knob-turn", 0, 1))  # a turn after the stop is a turn again
    assert controller.settle(10)
    assert sent == ["RESET", "$J=G91 G21 X1 F1000"]


def test_the_everything_key_is_sent_at_once_too(slow):
    controller, gate, polling, sent = slow
    controller.hear(_event("knob-turn", 0, 5))
    assert polling.wait(5)
    controller.hear(_event("key", 7, True))
    assert sent == ["RESET", "RESET"]  # each machine's own, the jog still unanswered


def test_a_key_or_a_knob_reads_the_newest_scan_and_starts_none(bench, monkeypatch):
    asked = []
    real = deck_control.devices.detected_devices

    def detected(*args, **kwargs):
        asked.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(deck_control.devices, "detected_devices", detected)
    assert deck_control.pinned_port(deck_control.MACHINES[1]) == ROUTER
    assert asked and all(kwargs.get("any_age") is True for kwargs in asked), asked


# --- disarming: one press of its own key ------------------------------------------------


def test_the_disarm_key_lets_go_of_every_machines_control_and_is_lit_while_any_is_armed(bench):
    controller, one, links = bench
    links.control.arm(PRINTER)
    ended = _held(controller, 1, 100.0, 1.0)
    _held(controller, 1, ended + 1.0, 1.0)  # the router's, armed from the deck
    assert links.control.armed(ROUTER) and links.control.armed(PRINTER)
    assert (one.keys[3]["colour"], one.keys[3]["small"]) == ("blue", "every machine")
    _press(one, 3)
    assert not links.control.armed(ROUTER) and not links.control.armed(PRINTER)
    assert (one.keys[3]["colour"], one.keys[3]["small"]) == ("grey", "nothing armed")
    assert (
        "disarmed" in one.strip["text"] and "printer_1, cnc_router disarmed" in one.strip["small"]
    )
    before = _router(links)
    _turn(one, 0, 1)  # and a turn moves nothing again
    assert _router(links) == before and controller.sent == []


def test_the_disarm_key_with_nothing_armed_says_so_and_sends_nothing(bench):
    controller, one, links = bench
    _press(one, 3)
    assert "nothing was armed" in one.strip["small"] and controller.sent == []


def test_the_disarm_key_is_acted_on_at_once_and_what_was_turned_before_it_is_not_sent(slow):
    controller, gate, polling, sent = slow
    let_go = []
    controller.disarm = let_go.append
    controller.armed = lambda port: 0.0 if let_go else 300.0
    controller.hear(_event("knob-turn", 0, 5))
    assert polling.wait(5)  # a jog taken up, the machine not yet answering
    controller.hear(_event("knob-turn", 1, 5))
    controller.hear(_event("key", 3, True))
    assert let_go == ["/dev/slow", "/dev/slow"]  # each machine's port, here the same one
    gate.set()
    assert controller.settle(10)
    assert sent == []


# --- a deck lost from USB while the layout runs ------------------------------------------


def test_a_lost_deck_is_found_again_by_the_layout_and_goes_on_being_heard(bench):
    controller, one, links = bench
    first = one.link
    first.lost = True  # the deck gone from USB
    deadline = time.monotonic() + 5
    while one.link is first and time.monotonic() < deadline:
        time.sleep(0.05)
    assert one.link is not first and one.alive() and one.mended == 1
    assert [what for what, _, _ in one.link.sent].count("key") == 8  # drawn again, every key
    assert controller.state()["deck_alive"] and controller.state()["deck_mended"] == 1
    links.control.arm(ROUTER)
    _choose_router(one)
    before = _router(links)
    _turn(one, 0, 1)  # the layout still listens, and a knob still jogs
    assert _router(links)["x"] == pytest.approx(before["x"] + 1)


# --- a router in alarm: the deck's own way out ------------------------------------------


def test_the_unlock_key_is_there_while_the_router_is_in_alarm_and_unlocks_it(bench):
    controller, one, links = bench
    _choose_router(one)
    assert (one.keys[6]["text"], one.keys[6]["small"]) == ("STOP JOG", "cnc_router")
    sim = links.get(ROUTER)._t
    sim.state, sim.alarm = "Alarm", 1  # a limit switch touched
    devices.printer_status(ROUTER)
    links.control.arm(ROUTER)
    _turn(one, 0, 1)  # locked out, and the strip says what to press
    assert "in alarm: UNLOCK it" in one.strip["small"] and controller.sent == []
    assert (one.keys[6]["text"], one.keys[6]["colour"]) == ("UNLOCK", "amber")
    _press(one, 6)
    assert controller.sent == ["$X"] and devices.printer_status(ROUTER).state == "idle"
    assert one.keys[6]["text"] == "STOP JOG"
    before = _router(links)
    _turn(one, 0, 1)
    assert _router(links)["x"] == pytest.approx(before["x"] + 1)


def test_a_stopped_layout_leaves_no_thread_to_touch_the_bench(bench):
    """Stopped is stopped: a tick part way through a scan, or an event being acted on,
    has ended when stop returns, so nothing of the layout's scans the ports or polls a
    machine after whoever stopped it has moved on."""
    controller, one, links = bench
    _turn(one, 0, 1)
    controller.stop()
    assert not controller._ticker.is_alive() and not controller._worker.is_alive()


def test_the_unlock_key_lights_from_the_newest_poll_after_a_stop_lets_the_router_go(bench):
    """A stop lets the router's control go, and the layout asks nothing while it is let
    go: after a stop mid-move the router is in alarm, and the next poll by anyone -- its
    Machine, a program -- is newer than the layout's own, and is what UNLOCK reads."""
    controller, one, links = bench
    _choose_router(one)
    links.control.arm(ROUTER)
    _turn(one, 0, 1)  # armed, the layout polls the router as it jogs
    assert controller.last is not None and controller.last.state != "alarm", controller.said
    _press(one, 5)  # the router's own stop: its control let go
    assert not links.control.armed(ROUTER)
    sim = links.get(ROUTER)._t
    sim.state, sim.alarm = "Alarm", 3  # as a reset mid-move leaves it
    assert devices.printer_status(ROUTER).state == "alarm"  # its Machine's poll
    controller.draw()  # the layout's next tick
    assert (one.keys[6]["text"], one.keys[6]["colour"]) == ("UNLOCK", "amber")


def test_the_unlock_key_needs_control_armed_as_any_line_but_a_stop_does(bench):
    controller, one, links = bench
    _choose_router(one)
    sim = links.get(ROUTER)._t
    sim.state, sim.alarm = "Alarm", 1
    devices.printer_status(ROUTER)
    _press(one, 6)
    assert controller.sent == [] and devices.printer_status(ROUTER).state == "alarm"


# --- a turn is for the moment it was made in; a move under way has its own stop ----------


def test_a_turn_that_waited_on_a_busy_machine_is_dropped_and_said(slow):
    """Turned while the machine homes or probes, a knob's turn is not a jog when it is
    done: it is dropped, with the turns summed onto it, and the strip says so."""
    controller, gate, polling, sent = slow
    controller.hear(deck.DeckEvent(1, "knob-turn", 0, 1))
    assert polling.wait(5)  # the machine is busy answering something else
    long_ago = time.time() - 60
    controller.hear(deck.DeckEvent(2, "knob-turn", 1, 5, at=long_ago))
    controller.hear(deck.DeckEvent(3, "knob-turn", 1, 5))  # summed onto the old one
    gate.set()
    assert controller.settle(10)
    assert sent == ["$J=G91 G21 X1 F1000"]
    assert controller.said[0].startswith("turn dropped: cnc_router was busy for")
    controller.hear(_event("knob-turn", 1, 1))  # a turn made now is a turn again
    assert controller.settle(10)
    assert sent[-1] == "$J=G91 G21 Y1 F1000"


def test_a_turn_taken_up_before_a_long_wait_is_dropped_when_the_wait_ends(slow, monkeypatch):
    controller, gate, polling, sent = slow
    monkeypatch.setattr(deck_control, "TURN_MAX_AGE_S", 0.2)
    controller.hear(_event("knob-turn", 0, 5))
    assert polling.wait(5)
    time.sleep(0.4)  # the machine's answer took longer than a turn stays meant
    gate.set()
    assert controller.settle(10)
    assert sent == [] and controller.said[0].startswith("turn dropped")


def test_key_six_stops_the_move_under_way_at_once_and_needs_no_latch(bench):
    controller, one, links = bench
    assert (one.keys[6]["text"], one.keys[6]["small"]) == ("QUICKSTOP", "printer_1")
    _press(one, 6)
    assert controller.sent == ["M410"] and not links.control.armed(PRINTER)
    assert "QUICKSTOP sent to printer_1" in one.strip["small"]
    _choose_router(one)
    assert one.keys[6]["text"] == "STOP JOG"
    _press(one, 6)
    assert controller.sent[-1] == "JOG-CANCEL" and not links.control.armed(ROUTER)
    sent = [e["text"] for e in links.log_for(ROUTER).since(0)["entries"] if e["kind"] == "tx"]
    assert sent[-1] == "JOG-CANCEL"


def test_a_stop_of_the_move_is_sent_ahead_of_turns_that_wait_and_they_are_not_sent(slow):
    controller, gate, polling, sent = slow
    controller.hear(_event("knob-turn", 0, 5))
    assert polling.wait(5)
    controller.hear(_event("knob-turn", 1, 5))
    controller.hear(_event("key", 6, True))
    assert sent == ["JOG-CANCEL"]
    gate.set()
    assert controller.settle(10)
    assert sent == ["JOG-CANCEL"], sent


# --- the strip's screens: Progress and Status, and the swipe between them ----------------------


def _swipe(one, direction):
    """A finger drawn along the strip, as the deck reports a drag: left is forward."""
    start, end = (700, 100) if direction > 0 else (100, 700)
    one.inject("touch", 0, {"kind": "drag", "x": start, "y": 50, "x_out": end, "y_out": 50})


def _tap(one):
    one.inject("touch", 0, {"kind": "short", "x": 400, "y": 50})


def _job(job_id="j1", outcome="running", progress=0.42, stage="printing", kind="print"):
    began = datetime.now(timezone.utc) - timedelta(seconds=754)
    return jobs.Job(
        id=job_id,
        kind=kind,
        machine=jobs.JobMachine(kind="printer", port=PRINTER),
        input=jobs.JobInput(name="benchy.gcode"),
        started_at=began,
        finished_at=None if outcome == "running" else began + timedelta(seconds=800),
        outcome=outcome,
        progress=progress,
        detail={"stage": stage},
    )


def _on(controller, port, job):
    """The host's job on ``port`` is ``job``, as the print's own thread would say."""
    controller.job = lambda asked: job if asked == port else None


def _wire(links):
    return len(links.log_for(PRINTER).since(0)["entries"]), len(
        links.log_for(ROUTER).since(0)["entries"]
    )


def test_a_swipe_along_the_strip_walks_the_screens_and_stops_at_each_end(bench):
    controller, one, links = bench
    assert controller.state()["screen"] == "knobs"
    before = one.strip["text"]
    _swipe(one, -1)  # nothing before the knobs
    assert controller.state()["screen"] == "knobs" and one.strip["text"] == before
    _swipe(one, +1)
    assert controller.state()["screen"] == "progress"
    assert one.strip["text"] == "printer_1 · no job"
    _swipe(one, +1)
    assert controller.state()["screen"] == "status" and one.strip["text"].startswith("printer_1 ·")
    status_text = one.strip["small"]
    _swipe(one, +1)  # nothing after the last
    assert controller.state()["screen"] == "status" and one.strip["small"] == status_text
    _swipe(one, -1)
    _swipe(one, -1)
    assert controller.state()["screen"] == "knobs" and one.strip["text"] == before
    assert controller.state()["screens"] == ["knobs", "progress", "status"]


def test_a_tap_or_a_short_drag_changes_no_screen_and_a_swipe_sends_nothing_to_a_machine(bench):
    controller, one, links = bench
    links.control.arm(ROUTER)  # armed, so a stray send would be accepted
    controller.send = controller.poll = controller.jog = lambda *a: pytest.fail(
        "a machine was asked"
    )
    wire = _wire(links)
    _tap(one)
    one.inject("touch", 0, {"kind": "long", "x": 400, "y": 50})
    one.inject("touch", 0, {"kind": "drag", "x": 400, "y": 50, "x_out": 500, "y_out": 50})
    assert controller.state()["screen"] == "knobs"
    for direction in (+1, +1, -1, -1, +1):
        _swipe(one, direction)
    assert controller.sent == [] and _wire(links) == wire
    assert links.control.armed(ROUTER)  # a touch arms and disarms nothing


def test_progress_shows_the_job_its_part_its_stage_how_far_and_how_long(bench):
    controller, one, links = bench
    _on(controller, PRINTER, _job(progress=0.42))
    _swipe(one, +1)
    assert one.strip["text"] == "benchy.gcode · 42%"
    assert one.strip["small"].startswith("printer_1 · printing · elapsed 12:")
    assert one.strip["bar"] == 0.42 and one.strip["colour"] == "blue"
    assert "left" not in one.strip["small"] and "remaining" not in one.strip["small"]


def test_status_shows_the_machines_state_and_what_it_reads(bench):
    controller, one, links = bench
    devices.printer_status(PRINTER)  # a poll anyone made: the deck shows the newest
    _swipe(one, +1)
    _swipe(one, +1)
    assert one.strip["text"] == "printer_1 · idle"
    assert one.strip["small"].startswith("hotend ") and " · bed " in one.strip["small"]
    assert one.strip["small"].endswith("3/3")


def test_a_print_beginning_brings_progress_forward_once_and_never_fights_a_swipe(bench):
    controller, one, links = bench
    assert controller.state()["screen"] == "knobs"
    running = _job("j1")
    _on(controller, PRINTER, running)
    for listener in list(jobs.LISTENERS):  # the machine's thread tells the jobs it began
        listener(running)
    assert controller.settle()
    assert controller.state()["screen"] == "progress"
    _swipe(one, -1)  # a person goes back to the knobs
    controller.draw()
    controller.draw()
    assert controller.state()["screen"] == "knobs"  # not brought forward again
    _swipe(one, +1)
    _swipe(one, +1)
    controller.draw()
    assert controller.state()["screen"] == "status"  # nor pulled off the screen they chose
    _swipe(one, -1)
    _swipe(one, -1)
    _on(controller, PRINTER, _job("j2"))  # the next print is another job
    controller.draw()
    assert controller.state()["screen"] == "progress"


def test_a_job_on_the_machine_not_chosen_brings_nothing_forward(bench):
    controller, one, links = bench
    controller.job = lambda port: _job("cut1", kind="cut") if port == ROUTER else None
    controller.draw()
    assert controller.state()["screen"] == "knobs"  # printer_1 is chosen
    _choose_router(one)  # the cut began before it was chosen: noted, not a new one
    controller.draw()
    assert controller.state()["screen"] == "knobs"


def test_a_job_that_ended_stays_on_progress_until_a_touch_of_it(bench):
    controller, one, links = bench
    _on(controller, PRINTER, _job("j1"))
    controller.draw()
    assert controller.state()["screen"] == "progress"
    for outcome, word in (("done", "done"), ("cancelled", "cancelled"), ("failed", "failed")):
        _on(
            controller,
            PRINTER,
            _job("j1", outcome=outcome, progress=1.0 if word == "done" else 0.6),
        )
        controller.draw()
        assert f"· {word} after 13:20" in one.strip["small"], one.strip["small"]
        controller.draw()  # and it stays, tick after tick
        assert f"· {word} after" in one.strip["small"]
    _tap(one)  # a touch of that screen clears it
    assert one.strip["text"] == "printer_1 · no job"
    assert controller.state()["screen"] == "progress"  # and moves nothing else
    _on(controller, PRINTER, _job("j3"))  # a job after it is shown again
    controller.draw()
    assert one.strip["text"] == "benchy.gcode · 42%"


def test_a_job_ended_is_not_cleared_by_a_touch_on_another_screen(bench):
    controller, one, links = bench
    _on(controller, PRINTER, _job("j1", outcome="done", progress=1.0))
    _tap(one)  # on the knobs: the result has not been seen
    _swipe(one, +1)
    assert "done after" in one.strip["small"]


def test_the_knobs_of_a_machine_a_job_holds_say_so_in_the_servers_words_and_move_nothing(bench):
    controller, one, links = bench
    _on(controller, PRINTER, _job("j1"))
    controller.draw()
    controller.screens.show("knobs")
    controller.draw()
    with pytest.raises(PortHeld) as refusal:  # the words the server refuses a jog with
        devices._job_allows({"kind": "print", "port": PRINTER, "stage": "printing"}, "G91")
    assert one.strip["text"] == "printer_1 · held"
    assert one.strip["small"].startswith(str(refusal.value))
    assert "jogs refused" in one.strip["small"] and one.strip["colour"] == "amber"
    controller.job = lambda port: None  # the job ended: the knobs are live again
    controller.draw()
    assert one.strip["text"].startswith("printer_1 · ") and "held" not in one.strip["text"]
    assert "X " in one.strip["small"]


def test_a_cut_that_holds_the_router_still_lets_the_spindle_knob_say_it_turns(bench):
    controller, one, links = bench
    _choose_router(one)
    controller.job = (
        lambda port: _job("c1", kind="cut", stage="running") if port == ROUTER else None
    )
    controller.draw()
    controller.screens.show("knobs")
    controller.draw()
    assert "a cut holds the port (running)" in one.strip["small"]
    assert "knob 4 still turns the spindle" in one.strip["small"]
