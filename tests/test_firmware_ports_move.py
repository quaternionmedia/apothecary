"""A port's name moves; a board's record does not move with it.

A probe's or an identification's record is kept under its port's name, and the
kernel hands ``/dev/ttyUSB0`` to whichever bridge it met first. So a record
counts only for the board the port list finds on its port
(``FirmwareState.cached_device``): any other board there is one nothing has
identified, to every reader of the record -- the dialect a line is checked in,
the stop that goes, the identity a pin stores, the MAC a flash is kept under.

No port here is real and no serial number is anybody's: each test plugs its own
boards into a port list and a scan of its own (``bench``).
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import serial.tools.list_ports
from click.testing import CliRunner
from fastapi.testclient import TestClient
from firmware_helpers import fake_cli_calls

from apothecary.api import app
from apothecary.cli import cli
from apothecary.firmware import devices, gcode, grbl, serial_monitor
from apothecary.firmware.models import BoardInfo, DeviceInfo, PrinterInfo

PORT = "/dev/ttyMOVES0"
OTHER = "/dev/ttyMOVES1"
CONTROLLER = "cnc_router.frame_system.controller"

# A printer's mainboard behind an FTDI bridge, which has a serial number, and a
# router's controller behind a CH340, which has none.
ENDER = {"vid": "0x0403", "pid": "0x6001", "serial_number": "MADEUPENDER1", "location": "1-2"}
ENDER_TWIN = {**ENDER, "serial_number": "MADEUPENDER2", "location": "1-5"}
ROUTER = {"vid": "0x1a86", "pid": "0x7523", "serial_number": None, "location": "1-3"}
ROUTER_TWIN = {**ROUTER, "location": "1-4"}


def _as_pyserial_lists_it(port, usb):
    return SimpleNamespace(
        device=port,
        vid=int(usb["vid"], 16),
        pid=int(usb["pid"], 16),
        serial_number=usb["serial_number"],
        location=usb["location"],
    )


class Bench:
    """The boards plugged in, as both finders see them: pyserial's own list, which
    the package reads, and the modules' scan in arduino-cli's spelling (``0x1A86``
    for ``0x1a86``, and no word of the socket)."""

    def __init__(self, monkeypatch):
        self.boards = {}
        self.unlisted = {}  # boards the scan finds on a port the list does not hold
        self.readings = 0
        monkeypatch.setattr(serial.tools.list_ports, "comports", self._listed)
        monkeypatch.setattr(devices, "scan_ports", self._scanned)

    def _listed(self):
        self.readings += 1
        return [_as_pyserial_lists_it(p, usb) for p, usb in self.boards.items()]

    def _scanned(self, cli=None, fresh=False):
        return [
            BoardInfo(
                port=p,
                label=p,
                vid=usb["vid"].replace("a", "A"),
                pid=usb["pid"],
                serial_number=usb["serial_number"],
                found_by="arduino",
            )
            for p, usb in sorted({**self.boards, **self.unlisted}.items())
        ]

    def plug(self, port, usb):
        self.boards[port] = usb
        devices._PORTS = None  # a hand is slower than the list's half second; a test is not

    def unplug(self, port):
        self.boards.pop(port, None)
        devices._PORTS = None


@pytest.fixture
def bench(fake_arduino_cli, monkeypatch):
    return Bench(monkeypatch)


@pytest.fixture
def garage():
    from apothecary import api as api_module

    api_module._site_store.reset("garage")
    yield api_module._site_store.get("garage")
    api_module._site_store.reset("garage")


def _links(monkeypatch, board):
    """The seam's link registry over one simulated board, its moves instant."""
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")
    links = gcode.PrinterLinks(factory=board)
    monkeypatch.setattr(gcode, "_LINKS", links)
    return links


def _answered(dialect, machine, name):
    return PrinterInfo(
        firmware_name=name,
        dialect=dialect,
        machine=machine,
        identified_at=datetime.now(timezone.utc),
    )


def _a_printer_was_identified(bench, port=PORT):
    """The record an identification leaves: the Ender's, made while it held the port."""
    bench.plug(port, ENDER)
    scanned = next(d for d in devices.detected_devices() if d.port == port)
    info = _answered("marlin", "printer", "Marlin made up")
    devices.get_state().remember_device(scanned.model_copy(update={"printer": info}))


def _a_router_was_identified(bench, port=PORT):
    bench.plug(port, ROUTER)
    scanned = next(d for d in devices.detected_devices() if d.port == port)
    info = _answered("grbl", "router", "Grbl made up")
    devices.get_state().remember_device(scanned.model_copy(update={"printer": info}))


def _sent(links, port=PORT):
    return [e["text"] for e in links.log_for(port).since(0)["entries"] if e["kind"] == "tx"]


# --- the port list -------------------------------------------------------------------


def test_the_port_list_carries_each_bridge_s_ids_and_its_socket(bench, monkeypatch):
    bench.plug(OTHER, ROUTER)
    bench.plug(PORT, ENDER)
    uart = SimpleNamespace(device="/dev/ttyS0", vid=None, pid=None, serial_number=None)
    listed = [*bench._listed(), uart]  # and a motherboard's own UART, nobody's board
    monkeypatch.setattr(serial.tools.list_ports, "comports", lambda: listed)
    found = serial_monitor.list_ports()
    assert [(b.port, b.vid, b.pid, b.serial_number, b.location) for b in found] == [
        (PORT, "0x0403", "0x6001", "MADEUPENDER1", "1-2"),
        (OTHER, "0x1a86", "0x7523", None, "1-3"),
    ]


def test_a_port_under_another_of_its_names_is_the_same_port(bench, tmp_path):
    alias = tmp_path / "printer"
    alias.symlink_to(PORT)  # as udev names a device node, or /dev/serial/by-id does
    bench.plug(PORT, ENDER)
    assert devices.board_on(str(alias)).serial_number == "MADEUPENDER1"
    state = devices.get_state()
    info = _answered("marlin", "printer", "Marlin made up")
    state.remember_device(DeviceInfo(port=str(alias), serial_number="MADEUPENDER1", printer=info))
    assert state.cached_device(str(alias)).printer.dialect == "marlin"
    bench.plug(PORT, ROUTER)
    assert state.cached_device(str(alias)) is None
    assert devices.board_on("COM7") is None  # a name that is no path is looked up as written


# --- the record itself ---------------------------------------------------------------


def test_a_record_counts_for_the_board_it_was_made_of_and_for_no_other(bench):
    state = devices.get_state()
    _a_printer_was_identified(bench)
    assert state.cached_device(PORT).serial_number == "MADEUPENDER1"
    # The printer leaves and a router takes its port's name: nothing is known of it.
    bench.plug(PORT, ROUTER)
    assert state.cached_device(PORT) is None
    # The record is not thrown away: the printer back on that port is known again.
    bench.plug(PORT, ENDER)
    assert state.cached_device(PORT).printer.dialect == "marlin"


def test_an_empty_port_keeps_the_record_of_the_board_last_on_it(bench, garage):
    _a_printer_was_identified(bench)
    devices.get_state().set_binding("garage", "printer_1", "MADEUPENDER1")
    bench.unplug(PORT)
    assert devices.get_state().cached_device(PORT).serial_number == "MADEUPENDER1"
    assert devices.dialect_of(PORT) == "marlin"
    # Which is what marks the node of an unplugged printer offline: its pin names
    # the board, and only the record says that board was the one on this port.
    printer_1 = next(s for s in garage.children if s.name == "printer_1")
    assert printer_1.status == "idle"
    said = devices.notify_status(gcode.offline_status(PORT, "the port went"))
    assert [row["path"] for row in said.synced] == ["printer_1"]
    assert printer_1.status == "offline"


def test_two_bridges_of_one_model_are_told_apart_by_serial_number(bench):
    _a_printer_was_identified(bench)
    bench.plug(PORT, ENDER_TWIN)
    assert devices.get_state().cached_device(PORT) is None
    twin = next(d for d in devices.detected_devices() if d.port == PORT)
    assert twin.serial_number == "MADEUPENDER2" and twin.printer is None


def test_two_bridges_with_no_serial_number_are_told_apart_by_their_socket(bench):
    _a_router_was_identified(bench)
    assert devices.dialect_of(PORT) == "grbl"
    # Another CH340, in another socket, numbered first after a restart.
    bench.plug(PORT, ROUTER_TWIN)
    assert devices.dialect_of(PORT) is None
    bench.plug(PORT, ROUTER)
    assert devices.dialect_of(PORT) == "grbl"


def test_a_record_kept_before_the_port_list_was_is_compared_by_its_own_usb_identity(bench):
    """A state file written before the port list's word was kept beside a record, or
    a record of a port the list did not hold: its own vendor, product and serial
    number stand, whichever finder spelled them."""
    state = devices.get_state()
    as_arduino_cli_wrote_it = DeviceInfo(
        port=PORT,
        vid="0x1A86",
        pid="0x7523",
        printer=_answered("grbl", "router", "Grbl made up"),
    )
    state.remember_device(as_arduino_cli_wrote_it)  # nothing is plugged in: no word kept
    assert json.loads(state.path.read_text())["seen"] == {}
    bench.plug(PORT, ROUTER)  # pyserial's 0x1a86 is arduino-cli's 0x1A86
    assert state.cached_device(PORT).printer.dialect == "grbl"
    bench.plug(PORT, ENDER)
    assert state.cached_device(PORT) is None
    # And a bridge is told from another of its model by serial number.
    a_printer = DeviceInfo(
        port=OTHER,
        vid="0x0403",
        pid="0x6001",
        serial_number="MADEUPENDER1",
        printer=_answered("marlin", "printer", "Marlin made up"),
    )
    state.remember_device(a_printer)
    bench.plug(OTHER, ENDER_TWIN)
    assert state.cached_device(OTHER) is None
    bench.plug(OTHER, ENDER)
    assert state.cached_device(OTHER).printer.dialect == "marlin"


def test_a_port_the_list_does_not_hold_is_told_by_the_scan(bench):
    """A simulated port is on no port list, and pyserial lists no board on a
    motherboard's UART: there the modules' scan is the only word on what holds the
    port, and its entry takes a record only of the board it names."""
    state = devices.get_state()
    bench.unlisted[PORT] = ENDER
    scanned = next(d for d in devices.detected_devices() if d.port == PORT)
    info = _answered("marlin", "printer", "Marlin made up")
    state.remember_device(scanned.model_copy(update={"printer": info}))
    assert next(d for d in devices.detected_devices() if d.port == PORT).printer is not None
    bench.unlisted[PORT] = ENDER_TWIN
    twin = next(d for d in devices.detected_devices() if d.port == PORT)
    assert twin.serial_number == "MADEUPENDER2" and twin.printer is None
    bench.unlisted[PORT] = ROUTER
    assert next(d for d in devices.detected_devices() if d.port == PORT).printer is None
    # The record itself is kept, as an empty port's is: the list finds nothing there.
    assert state.cached_device(PORT).serial_number == "MADEUPENDER1"


def test_the_scan_merges_a_record_whichever_finder_spelled_the_ids(bench, monkeypatch):
    _a_router_was_identified(bench)
    kept = json.loads(devices.get_state().path.read_text())["devices"][PORT]
    assert kept["vid"] == "0x1A86"  # the scan's spelling, as the record was written
    # The Rust module's pyserial finds the port next, in its own spelling.
    by_pyserial = [BoardInfo(port=PORT, label=PORT, found_by="rust_esp32", **ROUTER)]
    monkeypatch.setattr(devices, "scan_ports", lambda cli=None, fresh=False: by_pyserial)
    found = next(d for d in devices.detected_devices() if d.port == PORT)
    assert found.vid == "0x1a86" and found.printer.dialect == "grbl"


# --- every reader of the record --------------------------------------------------------


def test_the_dialect_is_the_board_s_on_the_port_not_the_last_board_s(bench):
    _a_printer_was_identified(bench)
    assert devices.dialect_of(PORT) == "marlin"
    with pytest.raises(ValueError, match="not a report-only query code"):
        devices.normalise_query(PORT, "$I")
    bench.plug(PORT, ROUTER)
    assert devices.dialect_of(PORT) is None
    # A port nothing has identified takes a line either dialect has.
    assert devices.normalise_query(PORT, "$I") == "$I"
    assert devices.normalise_query(PORT, "M503") == "M503"
    assert devices.normalise_control(PORT, "$H") == "$H"
    assert "M503" in devices.query_codes(PORT)


def test_what_is_known_of_a_port_is_known_of_the_board_on_it(bench):
    _a_printer_was_identified(bench)
    assert devices.machine_kind(devices.known_device(PORT)) == "printer"
    bench.plug(PORT, ROUTER)
    known = devices.known_device(PORT)
    # The scan's entry, as for a port nothing has talked to yet.
    assert known.port == PORT and known.printer is None and known.serial_number is None
    assert devices.machine_kind(known) is None


def test_a_port_is_pinned_as_the_board_on_it(bench):
    _a_printer_was_identified(bench)
    assert devices.stable_identity(PORT) == "MADEUPENDER1"
    bench.plug(PORT, ROUTER)
    # A CH340 has no serial number: the router is pinned by its port, not as the printer.
    assert devices.stable_identity(PORT) == PORT
    assert devices.stable_identity("MADEUPENDER1") == "MADEUPENDER1"


def test_a_flash_is_not_kept_under_the_mac_of_the_board_that_left(bench):
    bench.plug(PORT, ENDER)
    state = devices.get_state()
    scanned = next(d for d in devices.detected_devices() if d.port == PORT)
    state.remember_device(scanned.model_copy(update={"mac": "aa:bb:cc:00:00:01"}))
    assert (
        devices.make_flash_record(PORT, None, "esp32:esp32:esp32").identity == "aa:bb:cc:00:00:01"
    )
    bench.plug(PORT, ROUTER)
    record = devices.make_flash_record(PORT, None, "esp32:esp32:esp32")
    assert record.mac is None and record.identity == PORT


def test_asking_what_is_known_starts_no_process_and_reads_the_list_once(bench, fake_arduino_cli):
    _a_printer_was_identified(bench)
    devices._PORTS = None
    before = bench.readings
    for _ in range(5):  # one poll's questions
        assert devices.dialect_of(PORT) == "marlin"
        assert devices.known_device(PORT).printer is not None
        assert devices.stable_identity(PORT) == "MADEUPENDER1"
    assert bench.readings == before + 1
    assert fake_cli_calls(fake_arduino_cli) == []  # no arduino-cli ran: the scan is the bench's


def test_the_list_is_read_again_once_its_half_second_is_over(bench, monkeypatch):
    _a_printer_was_identified(bench)
    now = [1000.0]
    monkeypatch.setattr(devices.time, "monotonic", lambda: now[0])
    devices._PORTS = None
    assert devices.dialect_of(PORT) == "marlin"
    bench.boards[PORT] = ROUTER  # swapped behind the reading's back
    assert devices.dialect_of(PORT) == "marlin"
    now[0] += devices.PORTS_TTL
    assert devices.dialect_of(PORT) is None


# --- the stop that goes ----------------------------------------------------------------


def test_a_router_on_a_printer_s_old_port_is_stopped_as_a_router(bench, monkeypatch):
    links = _links(monkeypatch, grbl.SimulatedRouter)
    _a_printer_was_identified(bench)
    bench.plug(PORT, ROUTER)
    links.control.arm(PORT)
    assert devices.printer_control(PORT, "M3 S8000").command == "M3 S8000"
    # Its first use asked it what it is, and it answered as a router.
    assert devices.dialect_of(PORT) == "grbl" and devices.emergency_stop_for(PORT) == "RESET"
    assert devices.printer_status(PORT).spindle.on
    links.control.disarm(PORT)
    # A printer's stop is refused, said, and not sent: GRBL would answer it error:20
    # and go on cutting.
    with pytest.raises(ValueError, match="not an allowed GRBL control"):
        devices.printer_control(PORT, "M112")
    assert "M112" not in _sent(links)
    said = devices.printer_control(PORT, "RESET").lines
    assert any(ln.startswith("Grbl") for ln in said)
    assert not devices.printer_status(PORT).spindle.on
    links.stop_all()


def test_the_stop_of_a_router_nothing_has_asked_yet_goes_too(bench, monkeypatch):
    links = _links(monkeypatch, grbl.SimulatedRouter)
    _a_printer_was_identified(bench)
    bench.plug(PORT, ROUTER)
    said = devices.printer_control(PORT, "RESET").lines  # no latch, and nothing asked first
    assert any(ln.startswith("Grbl") for ln in said)
    assert "M112" not in _sent(links)
    links.stop_all()


def test_a_printer_s_stop_is_never_sent_to_a_router_nothing_has_asked_yet(bench, monkeypatch):
    links = _links(monkeypatch, grbl.SimulatedRouter)
    _a_printer_was_identified(bench)
    bench.plug(PORT, ROUTER)
    # It is asked what it is first, answers as a router, and the line is refused.
    with pytest.raises(ValueError, match="not an allowed GRBL control"):
        devices.printer_control(PORT, "M112")
    assert "$I" in _sent(links) and "M112" not in _sent(links)
    links.stop_all()


def test_a_router_on_a_printer_s_old_port_is_never_homed_as_a_printer(bench, monkeypatch):
    """The family's machine member homes with the line of the port's dialect
    (``dialect_for(port).home``, ``apothecary/family/members.py``). A printer's ``G28``
    is, to GRBL, a rapid to a stored position: it does not reach a router."""
    links = _links(monkeypatch, grbl.SimulatedRouter)
    _a_printer_was_identified(bench)
    bench.plug(PORT, ROUTER)
    links.control.arm(PORT)
    line = devices.dialect_for(PORT).home
    assert line == "G28"  # nothing has identified the board: Marlin's, as for any such port
    with pytest.raises(ValueError, match="not an allowed GRBL control"):
        devices.printer_control(PORT, line)
    assert "G28" not in _sent(links)
    # It was asked what it is on the way, so the next home is its own.
    assert devices.dialect_for(PORT).home == "$H"
    assert devices.printer_control(PORT, "$H").lines == ["ok"]
    links.stop_all()


def test_a_printer_on_a_router_s_old_port_is_stopped_as_a_printer(bench, monkeypatch):
    links = _links(monkeypatch, gcode.SimulatedPrinter)
    _a_router_was_identified(bench)
    assert devices.emergency_stop_for(PORT) == "RESET"
    bench.plug(PORT, ENDER)
    assert devices.printer_control(PORT, "M112").command == "M112"
    assert "M112" in _sent(links)
    assert devices.dialect_of(PORT) == "marlin" and devices.emergency_stop_for(PORT) == "M112"
    # And a router's stop is refused on it, not sent.
    with pytest.raises(ValueError, match="not an allowed control code"):
        devices.printer_control(PORT, "RESET")
    links.stop_all()


# --- the command line and the page's pin -----------------------------------------------


def test_the_command_line_asks_a_router_its_own_query_on_a_printer_s_old_port(bench, monkeypatch):
    links = _links(monkeypatch, grbl.SimulatedRouter)
    _a_printer_was_identified(bench)
    bench.plug(PORT, ROUTER)
    result = CliRunner().invoke(
        cli, ["firmware", "printer", PORT, "--query", "$I", "--query", "$$"]
    )
    assert result.exit_code == 0, result.output
    assert "> $I" in result.output and "> $$" in result.output
    assert "[VER:" in result.output
    assert "$I" in _sent(links)
    links.stop_all()


def test_pin_stores_the_board_on_the_port_and_says_what_it_stored(bench, garage):
    _a_printer_was_identified(bench)
    bench.plug(PORT, ROUTER)
    c = TestClient(app)
    row = c.put(f"/sites/garage/nodes/{CONTROLLER}/device", json={"identity": PORT}).json()
    # The router, by its port: not the printer whose record that port's name still holds.
    assert row["identity"] == PORT
    assert row["device"]["port"] == PORT and row["device"]["printer"] is None
    assert row["note"] is None
    pins = [b for b in devices.get_state().bindings("garage") if b.path == CONTROLLER]
    assert [b.identity for b in pins] == [PORT]
    # The printer plugged in again elsewhere is not what the router's node holds.
    bench.plug(OTHER, ENDER)
    rows = c.get("/sites/garage/devices").json()["bindings"]
    assert next(r for r in rows if r["path"] == CONTROLLER)["device"]["port"] == PORT
    # A board with a serial number is stored as it, and the row says so.
    row = c.put("/sites/garage/nodes/printer_1/device", json={"identity": OTHER}).json()
    assert row["identity"] == "MADEUPENDER1" and row["device"]["port"] == OTHER
    c.delete(f"/sites/garage/nodes/{CONTROLLER}/device")
    c.delete("/sites/garage/nodes/printer_1/device")


def test_a_router_s_poll_does_not_drive_the_node_of_the_printer_that_left(bench, garage):
    _a_printer_was_identified(bench)
    devices.get_state().set_binding("garage", "printer_1", "MADEUPENDER1")
    printer_1 = next(s for s in garage.children if s.name == "printer_1")
    bench.plug(PORT, ROUTER)
    polled = gcode.PrinterStatus(port=PORT, polled_at=datetime.now(timezone.utc), state="alarm")
    assert devices.notify_status(polled).synced == []
    assert printer_1.status == "idle"
    # The printer on that port is the one its pin names.
    bench.plug(PORT, ENDER)
    polled = gcode.PrinterStatus(port=PORT, polled_at=datetime.now(timezone.utc), state="printing")
    assert [row["path"] for row in devices.notify_status(polled).synced] == ["printer_1"]
    assert printer_1.status == "printing"


def test_no_view_of_the_port_says_the_printer_is_still_on_it(bench, garage):
    """Every answer that reads a port without talking to it, asked while a router
    holds the port a printer's record is kept under: none names the printer."""
    _a_printer_was_identified(bench)
    bench.plug(PORT, ROUTER)
    c = TestClient(app)
    answers = {
        url: c.get(url, params=params, follow_redirects=False)
        for url, params in [
            ("/firmware/devices", {}),
            ("/firmware/printers/info", {"port": PORT}),
            ("/firmware/printers/queries", {"port": PORT}),
            ("/firmware/pins", {}),
            ("/firmware/monitor", {"port": PORT}),
            ("/sites/garage/devices", {}),
            ("/jobs", {"machine": PORT}),
            ("/jobs/choices", {"machine": PORT}),
        ]
    }
    for url, answer in answers.items():
        assert answer.status_code in (200, 307), (url, answer.text)
        assert "MADEUPENDER1" not in answer.text, url
        assert "Marlin made up" not in answer.text, url
    assert answers["/jobs/choices"].json()["machine"] == {
        "kind": None,
        "port": PORT,
        "identity": PORT,
        "path": None,
    }
    assert answers["/firmware/printers/info"].json()["device"]["device"]["printer"] is None


# --- the simulated boards --------------------------------------------------------------


def test_a_simulated_devkit_two_finders_name_differently_keeps_its_probe(
    fake_arduino_cli, monkeypatch
):
    """The scripted arduino-cli and the simulated port list give one devkit two serial
    numbers. Its record counts all the same: the list is compared with its own earlier
    word, never with the scan's."""
    from apothecary.firmware import toolchains
    from apothecary.firmware.toolchains import Esptool

    monkeypatch.setenv("FAKE_DEVKIT", "1")
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "simulated")
    monkeypatch.setenv("APOTHECARY_SIMULATED_DEVKIT", "/dev/ttyFAKE2")
    monkeypatch.setattr(toolchains, "_ESPTOOL", Esptool(argv_prefix=[str(fake_arduino_cli)]))
    listed = devices.board_on("/dev/ttyFAKE2")
    scanned = next(d for d in devices.detected_devices() if d.port == "/dev/ttyFAKE2")
    assert (listed.serial_number, scanned.serial_number) == ("SIMDEVKIT0", "FAKEDEVKIT2")
    probed = devices.probe_device("/dev/ttyFAKE2")
    assert probed.mac == "aa:bb:cc:dd:ee:ff"
    assert devices.get_state().cached_device("/dev/ttyFAKE2").mac == "aa:bb:cc:dd:ee:ff"
    again = next(d for d in devices.detected_devices() if d.port == "/dev/ttyFAKE2")
    assert again.mac == "aa:bb:cc:dd:ee:ff"
    # The simulated printer's port is on no list: its record counts as it always did.
    assert devices.board_on("/dev/ttyFAKE1") is None
