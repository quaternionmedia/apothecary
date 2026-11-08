"""The Stream Deck + as a controller for the garage's machines (firmware/deck_control.py),
against the simulated deck and the demo's bench: the simulated Ender and router, pinned.

Every motion goes through what bounds a person's jog -- the control latch, the port's
dialect, its bounds -- so each test sends a turn and reads the machine's own answer. No
HID device and no serial port is opened."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.demo import PRINTER, ROUTER
from apothecary.firmware import deck, deck_control, devices, gcode, grbl
from apothecary.firmware.toolchains import PortHeld, ToolchainError


@pytest.fixture
def bench(family_bench, monkeypatch):
    """The demo's bench, and one simulated deck with the layout running on it."""
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


def test_a_printer_jog_returns_to_absolute_positioning_even_when_the_move_is_refused(bench):
    controller, one, links = bench
    links.control.arm(PRINTER)
    start = _printer(links)
    _turn(one, 2, -1)
    assert controller.sent == ["G91", "G1 Z-1 F3000", "G90"]
    assert _printer(links)["z"] == pytest.approx(start["z"] - 1)
    controller.sent.clear()
    _press(one, 2)
    _turn(one, 0, 40)  # 400 mm, over the printer's 300: G91 went, the move did not
    assert controller.sent == ["G91", "G90"]
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
    assert controller.sent[-1] == "M3 S0"
    assert " S " in one.strip["small"]  # the fourth quantity is on the strip


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
    assert seen == [(PRINTER, "M112"), (ROUTER, "RESET")]  # each by its own dialect's word
    assert controller.sent == ["stop printer_1", "stop cnc_router"]
    assert _printer_halted(links) and not _spindle_on(links)
    assert "STOP sent to printer_1, cnc_router" in one.strip["small"]


def test_the_everything_key_goes_on_stopping_when_one_machine_cannot_be_reached(bench):
    controller, one, links = bench
    _both_going(links)
    controller.resolve = lambda machine: ROUTER if machine.name == "cnc_router" else None
    _press(one, 7)
    assert controller.sent == ["stop cnc_router"] and not _spindle_on(links)
    assert "not printer_1 (no board pinned)" in one.strip["small"]


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

    def held(port, line):
        raise PortHeld(f"{port} is held by a print")

    controller.send = held
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
    assert client.get("/firmware/decks/SIMDECK0/control").json() == {"running": False}
    started = client.post("/firmware/decks/SIMDECK0/control", json={"on": True}).json()
    assert started["running"] and started["machine"] == "printer_1" and started["sent"] == []
    assert client.get("/firmware/decks/SIMDECK0/control").json()["running"] is True
    assert client.post("/firmware/decks/SIMDECK0/control", json={"on": False}).json() == {
        "running": False
    }
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
