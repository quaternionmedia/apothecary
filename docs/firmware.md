# Firmware: programming boards from Apothecary

Parts are not only geometry. A footpedal has an Arduino in it; an RC snowplow
has an ESP32. `apothecary firmware` and the `/firmware` page let you install the
toolchain, keep sketches next to the parts they belong to, compile and upload
them, and see what each connected board is running.

Apothecary owns only the control plane. Building and flashing are done by two
external tools, invoked as subprocesses and never linked:

| Engine | Used for | Installed by |
|---|---|---|
| [arduino-cli](https://arduino.github.io/arduino-cli/) | boards, cores, libraries, compile, upload, serial monitor | `apothecary firmware install` (checksum-verified download into `~/.apothecary/tools/`) |
| [esptool](https://github.com/espressif/esptool) | chip identification and raw binary flashing of Espressif chips | detected: on `PATH`, bundled with the `esp32:esp32` core, or as a Python module |

## Setup

```bash
apothecary firmware install --avr --esp32      # arduino-cli + the AVR and ESP32 cores
apothecary firmware validate                   # exit 1 if arduino-cli is unusable
apothecary firmware cores --install rp2040:rp2040   # more cores; index URLs are added for you
apothecary firmware libraries --install FastLED --install "Control Surface@2.1.2"
```

Environment:

| Variable | Meaning | Default |
|---|---|---|
| `APOTHECARY_TOOLS_DIR` | where Apothecary installs toolchains | `~/.apothecary/tools` |
| `APOTHECARY_STATE_DIR` | where flash records and cached probes live | `~/.apothecary` |
| `ARDUINO_CLI` | explicit path to an arduino-cli binary (checked first) | — |

The tools dir is under `$HOME` on purpose rather than an XDG data dir: sandboxed
editors (the VS Code snap, for one) point `XDG_DATA_HOME` at a per-revision tree
that disappears on the next editor update.

On Linux the serial port must be writable by your user — usually
`sudo usermod -aG dialout $USER` and a new login.

## Sketches live with their parts

A sketch is a folder holding a `.ino` of the same name — arduino-cli's own
layout rule — anywhere under `parts/`, including nested category folders:

```
parts/footpedal/footpedal.ino
parts/esp32_blink/esp32_blink.ino
parts/rc/snowplow/controller/controller.ino
```

An optional `firmware.json` beside the `.ino` supplies defaults so nobody
retypes them per build:

```json
{
  "fqbn": "esp32:esp32:esp32",
  "cores": ["esp32:esp32"],
  "libraries": ["FastLED", "Control Surface@2.1.2"],
  "note": "Classic ESP32 devkits; use esp32:esp32:esp32s3 for an S3."
}
```

| Field | Purpose |
|---|---|
| `fqbn` | default board (`vendor:arch:board[:option=value,…]`); `--fqbn` or the GUI overrides it |
| `cores` | cores the sketch needs (informational; install with `firmware install --core`) |
| `libraries` | libraries to install, `Name` or `Name@Version` |
| `note` | shown in the GUI's build panel |

Build output goes to `build/firmware/<sketch>/` (git-ignored), never into `parts/`.

## Build and upload

```bash
apothecary firmware sketches                 # what was found
apothecary firmware compile esp32_blink      # FQBN from firmware.json
apothecary firmware upload esp32_blink       # compile, then upload the fresh build
apothecary firmware upload footpedal --fqbn arduino:avr:nano:cpu=atmega328old -p /dev/ttyUSB1
apothecary firmware flash-bin /dev/ttyUSB0 0x0:build/firmware/esp32_blink/esp32_blink.ino.merged.bin --chip esp32
```

`upload` always compiles first and flashes that build, never a stale binary.
The port is auto-detected only when exactly one board is connected; with
several it refuses to guess.

## Knowing what a board is running

`apothecary firmware devices` (and the Devices panel on `/firmware`) describe
each connected board from four independent sources:

| View | Source | What it tells you |
|---|---|---|
| Detected | `arduino-cli board list` | serial port, USB bridge VID:PID, any board arduino-cli matched |
| Probed | `esptool flash_id` | chip model and revision, MAC, flash size, crystal — cached per port; **resets the board** |
| Expected | Apothecary's own flash record | the sketch last uploaded to that MAC (or port), with its FQBN, time, and the SHA-256 of both the binary and the sources — plus drift flags: *source edited since*, *newer build never uploaded*, *sketch gone* |
| Observed | `arduino-cli monitor` | the sketch that announces itself over serial |

```bash
apothecary firmware probe /dev/ttyUSB0             # identify the chip
apothecary firmware listen /dev/ttyUSB0 --reset    # a few seconds of serial; names the running sketch
```

### The announce protocol

A sketch that wants to be identified prints, at boot **and every few seconds**:

```
apothecary <sketch-name>: hello
```

Periodically, not just at boot: the monitor takes longer to attach than a boot
banner lasts. `parts/esp32_blink/esp32_blink.ino` is the reference
implementation (it also prints a `chip: …` line the GUI shows next to the
probe result). When the observed name matches the expected record the GUI
marks the device green; a mismatch is red.

### Live serial

`GET /firmware/devices/stream?port=/dev/ttyUSB0&baud=115200` is a server-sent
events stream of the board's serial output. It backs the **Live** button on
each device card and the **⌨ Serial log** toggle in the fractal viewer, which
floats a terminal over the 3D view and remembers its state across reloads.

Starting any task (compile, upload, install, flash) stops every monitor first
— the port is needed — and the page reconnects when the task ends.

Some USB-UART bridges occasionally replay bytes they already delivered (seen
on a CP2102). Serial bytes are paced through a token bucket refilled at the
baud rate: a burst the wire could not have carried, or a verbatim repeat
arriving faster than the wire could resend it, is dropped; three in a row
reopen the port and print `[apothecary: serial replay detected -- reopening
port]` in the log. Genuine output is never throttled.

## HTTP API

All routes are under `/firmware`. Long-running actions return `202` with a
task; poll `GET /firmware/tasks/{id}?since=N` for new log lines. One task runs
at a time — a second request gets `409`.

| Route | Purpose |
|---|---|
| `GET /status` | toolchain state, cores, suggested cores, active task |
| `GET /sketches`, `/boards`, `/boards/all`, `/cores` | catalogue |
| `POST /install`, `/cores/install`, `/libraries/install` | toolchain tasks |
| `POST /sketches/{name}/compile`, `/upload` | build tasks (`{"fqbn": …, "port": …}`) |
| `POST /esptool/flash` | raw flash task; image paths must be inside the repository |
| `GET /devices` | detected + probed + expected, per port |
| `POST /devices/probe`, `/devices/listen` | identify the chip; capture serial (`reset: true` probes first) |
| `GET /devices/stream` | server-sent events of serial output |
| `GET /tasks`, `/tasks/{id}`, `POST /tasks/{id}/cancel` | task log and control |

Inputs that become command-line arguments are validated by shape (FQBN,
serial port path, core id, chip name) and never pass through a shell; sketch
names resolve only to discovered sketches. The server binds to localhost by
default and these routes run binaries and open serial ports on the host, so
keep it that way.

## Testing

The seam's tests run against a scripted fake `arduino-cli`
(`tests/conftest.py`), so CI needs no toolchain, network, or serial port:

```bash
uv run pytest tests/test_firmware_seam.py tests/test_firmware_api.py tests/test_firmware_devices.py
```

The decision record for all of this is *Firmware toolchain seam* in
`governance/qm/adr/`.
