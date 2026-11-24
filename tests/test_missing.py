"""Why a machine's board is not found (apothecary/firmware/missing.py), read with no
port opened: the kernel's USB list read from a tree written here, the serial ports and
the scan given, and each check a board gets through in its order. Each test keeps its
pins in a state folder of its own.
"""

import pytest
from fastapi.testclient import TestClient
from firmware_helpers import _isolate_firmware_state

from apothecary.api import app
from apothecary.firmware import devices, missing
from apothecary.firmware.models import GRBL, BoardInfo, DeviceInfo, PrinterInfo

client = TestClient(app)

FTDI = {"vid": "0x0403", "pid": "0x6001", "serial_number": "A106ZTEU", "location": "1-1.2"}


@pytest.fixture(autouse=True)
def _a_state_folder_of_its_own(monkeypatch, tmp_path):
    _isolate_firmware_state(monkeypatch, tmp_path)


def _device(root, place, vid, pid, *, serial=None, product=None, tty=None, hub=False):
    dev = root / place
    dev.mkdir(parents=True)
    (dev / "idVendor").write_text(vid + "\n")
    (dev / "idProduct").write_text(pid + "\n")
    (dev / "bDeviceClass").write_text("09\n" if hub else "00\n")
    if serial:
        (dev / "serial").write_text(serial + "\n")
    if product:
        (dev / "product").write_text(product + "\n")
    iface = dev / f"{place}:1.0"
    iface.mkdir()
    if tty:
        # An FTDI's or a CH340's port is a folder of the interface; an ACM board's is under tty/.
        (iface / tty if tty.startswith("ttyUSB") else iface / "tty" / tty).mkdir(parents=True)
    return dev


def test_the_kernel_s_usb_list_is_read_hubs_and_interfaces_left_out(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "pyserial")
    root = tmp_path / "usb"
    _device(root, "1-1", "05e3", "0610", product="USB2.0 Hub", hub=True)
    _device(
        root, "1-1.2", "0403", "6001", serial="A106ZTEU", product="FT232R USB UART", tty="ttyUSB1"
    )
    _device(root, "1-1.3", "1a86", "7523", product="USB Serial", tty="ttyUSB0")
    _device(root, "1-4", "2341", "0043", serial="85735313", tty="ttyACM0")
    (root / "usb1").mkdir()  # a bus's root hub
    got = {d.place: d for d in missing.usb_devices(root)}
    assert sorted(got) == ["1-1.2", "1-1.3", "1-4"]
    assert got["1-1.2"].make == "usb:0403:6001" and got["1-1.2"].serial == "A106ZTEU"
    assert got["1-1.2"].ports == ["/dev/ttyUSB1"] and got["1-4"].ports == ["/dev/ttyACM0"]
    assert got["1-1.3"].serial is None
    # Where the kernel keeps no such list nothing is read; a simulated engine reads none.
    assert missing.usb_devices(tmp_path / "nowhere") is None
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "simulated")
    assert missing.usb_devices(root) == []


def test_a_socket_and_a_bridge_as_a_person_reads_them():
    assert missing.socket("1-1.2") == "USB socket 1-1.2 (a hub's socket 2)"
    assert missing.socket("1-4") == "USB socket 1-4"
    assert missing.bridge("usb:0403:6001") == "FTDI FT232R (0403:6001)"
    assert missing.bridge("usb:dead:beef") == "dead:beef"


def _states(out):
    return [(c["id"], c["state"]) for c in out["checks"]]


def test_a_board_not_on_usb_is_switched_on_and_cabled_where_it_was_last_found():
    out = missing.explain(
        "A106ZTEU", "printer", usb=[], listed={}, last_port="/dev/ttyUSB1", seen=FTDI
    )
    assert _states(out) == [("usb", "off"), ("port", "after"), ("open", "after"), ("scan", "after")]
    assert out["checks"][0]["says"] == "nothing on USB is FTDI FT232R (0403:6001) A106ZTEU"
    assert out["todo"].startswith("Switch the printer on and seat its USB cable at both ends")
    assert "last found on /dev/ttyUSB1, in USB socket 1-1.2 (a hub's socket 2)" in out["todo"]


def test_a_board_is_named_once_by_what_is_known_of_it():
    # Its bridge and serial number; a pin by make, the bridge alone, never its make twice;
    # a serial number never seen on USB, that alone; a port typed by hand, as typed.
    assert missing.explain("A106ZTEU", "printer", usb=[], listed={}, seen=FTDI)["board"] == (
        "FTDI FT232R (0403:6001) A106ZTEU"
    )
    out = missing.explain("usb:1a86:7523", "router", usb=[], listed={})
    assert out["board"] == "CH340 (1a86:7523)"
    assert out["checks"][0]["says"] == "nothing on USB is CH340 (1a86:7523)"
    out = missing.explain("A106ZTEU", "printer", usb=[], listed={})
    assert out["checks"][0]["says"] == "nothing on USB is A106ZTEU"
    assert (
        missing.explain("/dev/ttyUSB3", "printer", usb=None, listed={})["board"] == "/dev/ttyUSB3"
    )


def test_another_board_of_its_make_is_named_to_pin_in_its_place():
    other = missing.UsbDevice("1-3", "usb:0403:6001", serial="B2XYZ", ports=["/dev/ttyUSB2"])
    out = missing.explain("A106ZTEU", "printer", usb=[other], listed={}, seen=FTDI)
    assert _states(out)[0] == ("usb", "off")
    assert (
        "FTDI FT232R (0403:6001) B2XYZ is on /dev/ttyUSB2: if that is this printer's board now, pin it here"
        in out["todo"]
    )


def test_a_board_on_usb_with_no_serial_port_has_no_driver():
    ch340 = missing.UsbDevice("1-1.3", "usb:1a86:7523")
    out = missing.explain("usb:1a86:7523", "router", usb=[ch340], listed={})
    assert _states(out) == [("usb", "ok"), ("port", "off"), ("open", "after"), ("scan", "after")]
    assert out["checks"][0]["says"] == "CH340 (1a86:7523) is in USB socket 1-1.3 (a hub's socket 3)"
    assert out["todo"].startswith("Unplug it and plug it in again.") and "brltty" in out["todo"]
    ftdi = missing.UsbDevice("1-1.2", "usb:0403:6001", serial="A106ZTEU")
    assert "brltty" not in missing.explain("A106ZTEU", "printer", usb=[ftdi], listed={})["todo"]


def test_a_port_this_user_cannot_open_names_its_group():
    ftdi = missing.UsbDevice("1-1.2", "usb:0403:6001", serial="A106ZTEU", ports=["/dev/ttyUSB1"])
    out = missing.explain("A106ZTEU", "printer", usb=[ftdi], listed={}, can_open=lambda port: False)
    assert _states(out) == [("usb", "ok"), ("port", "ok"), ("open", "off"), ("scan", "after")]
    assert "dialout" in out["todo"]


def test_a_board_on_an_open_port_the_scan_does_not_name_is_looked_for_again():
    ftdi = missing.UsbDevice("1-1.2", "usb:0403:6001", serial="A106ZTEU", ports=["/dev/ttyUSB1"])
    out = missing.explain("A106ZTEU", "printer", usb=[ftdi], listed={}, can_open=lambda port: True)
    assert _states(out) == [("usb", "ok"), ("port", "ok"), ("open", "ok"), ("scan", "off")]
    assert out["todo"].startswith("It is scanned for afresh by itself")
    # One that last answered as another kind of machine is the other's.
    router = DeviceInfo(
        port="/dev/ttyUSB1", **FTDI, printer=PrinterInfo(firmware_name="Grbl 1.3a", dialect=GRBL)
    )
    out = missing.explain(
        "A106ZTEU", "printer", usb=[ftdi], listed={}, last=router, can_open=lambda port: True
    )
    assert (
        out["checks"][3]["says"]
        == "its board last answered as a router, and this machine is a printer"
    )


def test_where_usb_is_not_read_the_serial_ports_say_it():
    listed = {
        "/dev/ttyUSB1": BoardInfo(
            port="/dev/ttyUSB1", vid="0x0403", pid="0x6001", serial_number="A106ZTEU"
        )
    }
    out = missing.explain(
        "A106ZTEU", "printer", usb=None, listed=listed, can_open=lambda port: True
    )
    assert _states(out) == [("usb", "ok"), ("port", "ok"), ("open", "ok"), ("scan", "off")]
    out = missing.explain("A106ZTEU", "printer", usb=None, listed={})
    assert _states(out)[0] == ("usb", "unread")


def test_every_serial_port_plugged_in_says_whose_it_is():
    usb = [
        missing.UsbDevice("1-1.3", "usb:1a86:7523", product="USB Serial", ports=["/dev/ttyUSB0"])
    ]
    listed = {
        "/dev/ttyACM0": BoardInfo(
            port="/dev/ttyACM0", vid="0x2341", pid="0x0043", serial_number="857"
        )
    }
    rows = missing.plugged(usb, listed, {"/dev/ttyUSB0": "cnc_router.frame_system.controller"})
    assert [(r["port"], r["bridge"], r["for"]) for r in rows] == [
        ("/dev/ttyACM0", "Arduino Uno (2341:0043)", None),
        ("/dev/ttyUSB0", "CH340 (1a86:7523)", "cnc_router.frame_system.controller"),
    ]


def test_where_a_board_was_last_found_is_read_from_its_record_and_the_port_list():
    state = devices.get_state()
    assert state.last_found("A106ZTEU") == (None, None, None)
    data = state._load()
    data["devices"]["/dev/ttyUSB1"] = DeviceInfo(
        port="/dev/ttyUSB1", **{k: v for k, v in FTDI.items() if k != "location"}
    ).model_dump(mode="json")
    data["seen"]["/dev/ttyUSB1"] = FTDI
    state._save(data)
    port, device, seen = state.last_found("a106zteu")
    assert (
        port == "/dev/ttyUSB1"
        and device.serial_number == "A106ZTEU"
        and seen["location"] == "1-1.2"
    )


def test_the_route_says_why_a_pinned_printer_s_board_is_not_found(monkeypatch):
    devices.get_state().set_binding(
        "garage", "printer_1.frame_system.mainboard", "A106ZTEU", "printer"
    )
    found: list = []
    asked: list = []
    monkeypatch.setattr(devices, "detected_devices", lambda **kw: asked.append(kw) or found)
    monkeypatch.setattr(devices, "ports_now", lambda: {})
    monkeypatch.setattr(missing, "usb_devices", lambda: [])
    d = client.get("/sites/garage/machines/printer_1/missing").json()
    assert d["connected"] == [] and d["usb_read"] is True and d["plugged"] == []
    [board] = d["expected"]
    assert board["pinned_at"] == "printer_1.frame_system.mainboard" and board["how"] == "manual"
    assert _states(board)[0] == ("usb", "off")
    assert board["todo"].startswith("Switch the printer on")
    # Found: no board is expected, and the one connected is said with its port.
    found.append(
        DeviceInfo(port="/dev/ttyUSB1", vid="0x0403", pid="0x6001", serial_number="A106ZTEU")
    )
    d = client.get("/sites/garage/machines/printer_1/missing").json()
    assert d["expected"] == []
    assert d["connected"] == [{"path": "printer_1.frame_system.mainboard", "port": "/dev/ttyUSB1"}]
    # Asked every few seconds, it reads the newest scan and starts none.
    assert asked == [{"any_age": True}] * 2
    # A node that is no machine is refused as the plan's routes refuse it.
    assert client.get("/sites/garage/machines/workbench/missing").status_code == 400
