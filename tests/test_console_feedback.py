"""Console input: the sACN parser, the live state, and the receiver on a real socket.

Packets are built by hand from the E1.31 layout, so the parser is checked against
the spec's byte positions rather than against its own output.
"""

from __future__ import annotations

import socket
import struct
import time

import pytest

from apothecary.console_feedback import (
    ACN_ID,
    DMX_HEADER,
    ConsoleState,
    OscReceiver,
    SacnReceiver,
    parse_osc,
    parse_sacn,
)
from apothecary.lighting import LightingRig, Patch


def make_sacn(universe: int, slots: bytes, options: int = 0, start_code: int = 0) -> bytes:
    header = bytearray(DMX_HEADER)
    header[0:2] = (0x0010).to_bytes(2, "big")
    header[4:16] = ACN_ID
    header[40:44] = (2).to_bytes(4, "big")
    header[112] = options
    header[113:115] = universe.to_bytes(2, "big")
    header[117] = 2
    header[123:125] = (len(slots) + 1).to_bytes(2, "big")
    header[125] = start_code
    return bytes(header) + slots


def _rig() -> LightingRig:
    return LightingRig(
        patches=[
            Patch(channel=1, fixture_type="ColorSource_SPOT_5ch", universe=1, addresses=[1, 2, 3, 4, 5]),
            Patch(channel=9, fixture_type="Virtual_Layer_Ver_1.0"),
        ],
    )


def test_parse_sacn_returns_universe_and_slots():
    slots = bytes([255, 0, 128]) + bytes(509)
    assert parse_sacn(make_sacn(3, slots)) == (3, slots)


@pytest.mark.parametrize(
    "packet",
    [
        b"not sacn at all",
        make_sacn(1, bytes(512), options=0x40),  # stream terminated
        make_sacn(1, bytes(512), start_code=0xDD),  # not DMX data
    ],
)
def test_parse_sacn_ignores_other_packets(packet):
    assert parse_sacn(packet) is None


def test_state_decodes_addressed_channels_and_takes_console_levels():
    state = ConsoleState(_rig())
    slots = bytearray(512)
    slots[0], slots[1] = 255, 128
    state.apply_universe(1, bytes(slots))
    state.set_levels({9: {"Pan": 0.25}})

    snap = state.snapshot()
    assert snap["channels"][1]["Intens"] == 1.0
    assert snap["channels"][1]["Red"] == pytest.approx(128 / 255)
    assert snap["channels"][9] == {"Pan": 0.25}
    assert snap["seq"] == 2
    assert snap["age"] is not None and snap["age"] < 5


def test_state_rejects_unknown_channel_and_out_of_range_level():
    state = ConsoleState(_rig())
    with pytest.raises(KeyError):
        state.set_levels({42: {"Intens": 0.5}})
    with pytest.raises(ValueError):
        state.set_levels({1: {"Intens": 1.5}})
    assert state.snapshot()["seq"] == 0


def test_simulated_levels_only_name_parameters_the_fixture_has():
    from apothecary.console_feedback import simulate_levels
    from apothecary.lighting import FixtureType

    rig = _rig()
    rig.types["ColorSource_SPOT_5ch"] = FixtureType(name="ColorSource_SPOT_5ch", params=["Intens", "Red", "Green", "Blue"])
    rig.types["Virtual_Layer_Ver_1.0"] = FixtureType(name="Virtual_Layer_Ver_1.0", params=["Intens", "Pan", "Tilt"])
    levels = simulate_levels(rig, t=1.0)
    assert set(levels[1]) == {"Intens", "Red", "Green", "Blue"}
    assert set(levels[9]) == {"Intens", "Pan", "Tilt"}
    assert all(0.0 <= v <= 1.0 for ch in levels.values() for v in ch.values())


def test_receiver_takes_a_packet_for_its_universe_and_ignores_another():
    state = ConsoleState(_rig())
    receiver = SacnReceiver(state, [1])
    receiver.start()
    try:
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with sender:
            for universe in (2, 1):  # the other universe first: it must not count
                sender.sendto(make_sacn(universe, bytes([255]) + bytes(4) + bytes(507)), ("127.0.0.1", 5568))
        deadline = time.monotonic() + 3
        while state.snapshot()["seq"] == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        receiver.stop()
    snap = state.snapshot()
    assert snap["seq"] == 1
    assert snap["channels"][1]["Intens"] == 1.0


def _osc_str(text: str) -> bytes:
    raw = text.encode() + b"\0"
    return raw + b"\0" * (-len(raw) % 4)


def make_osc(address: str, *args) -> bytes:
    """An OSC message from the spec's layout: padded address, type tags, big-endian args."""
    tags, body = ",", b""
    for a in args:
        if isinstance(a, bool):
            tags += "T" if a else "F"
        elif isinstance(a, int):
            tags, body = tags + "i", body + struct.pack("!i", a)
        elif isinstance(a, float):
            tags, body = tags + "f", body + struct.pack("!f", a)
        else:
            tags, body = tags + "s", body + _osc_str(a)
    return _osc_str(address) + _osc_str(tags) + body


def test_parse_osc_reads_each_argument_type():
    packet = make_osc("/eos/out/pantilt", 1, -2, 0.5, "x y", True)
    assert parse_osc(packet) == [("/eos/out/pantilt", [1, -2, 0.5, "x y", True])]
    assert parse_osc(make_osc("/eos/out/ping")) == [("/eos/out/ping", [])]
    assert parse_osc(_osc_str("/no/tags")) == [("/no/tags", [])]


def test_parse_osc_flattens_a_bundle():
    one, two = make_osc("/a", 1), make_osc("/b", "two")
    bundle = _osc_str("#bundle") + bytes(8)
    for message in (one, two):
        bundle += struct.pack("!i", len(message)) + message
    assert parse_osc(bundle) == [("/a", [1]), ("/b", ["two"])]


@pytest.mark.parametrize(
    "packet",
    [b"", b"hello", b"/unterminated", make_osc("/a", 1)[:-2], _osc_str("#bundle") + bytes(8) + struct.pack("!i", 999)],
)
def test_parse_osc_ignores_what_is_not_osc_or_is_cut_short(packet):
    assert parse_osc(packet) == []


def test_state_keeps_the_consoles_status_and_nothing_else():
    state = ConsoleState(_rig())
    state.apply_osc(parse_osc(make_osc("/eos/out/cmd", "LIVE: Chan 41")) + parse_osc(make_osc("/other", 1)))
    snap = state.snapshot()
    assert snap["status"] == {"/eos/out/cmd": ["LIVE: Chan 41"]}
    assert snap["seq"] == 1  # the console is talking; the other address was not its status


def test_status_holds_a_bounded_number_of_addresses():
    from apothecary.console_feedback import MAX_STATUS

    state = ConsoleState(_rig())
    state.apply_osc([(f"/eos/out/n{i}", [i]) for i in range(MAX_STATUS + 10)])
    assert len(state.snapshot()["status"]) == MAX_STATUS


def test_osc_receiver_takes_a_packet_on_a_real_socket():
    from apothecary.stays_local import OSC_PORT

    state = ConsoleState(_rig())
    receiver = OscReceiver(state)
    receiver.start()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(make_osc("/eos/out/active/chan", "1-2 [100]"), ("127.0.0.1", OSC_PORT))
        deadline = time.monotonic() + 3
        while state.snapshot()["seq"] == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        receiver.stop()
    assert state.snapshot()["status"] == {"/eos/out/active/chan": ["1-2 [100]"]}
