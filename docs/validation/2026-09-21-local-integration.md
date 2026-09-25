# Local integration run-through: the new features, by topic

*A handoff for a person at the bench with the tip of `consolidate/2026-09-19`
(`a6e9972` and after) checked out. It walks every capability the branch added
since the printer seam landed -- the guard that keeps personal data here, the
geometry brought in from elsewhere, the bench drawn as it is, the rail and
the machine popup, the camera, the printer with and without hardware, the
docs site -- as a checklist you tick as you go. Nothing here needs the
network; everything needs this machine.*

## How to walk it

Two terminals and a browser. Terminal **A** runs a server; terminal **B**
runs the commands in the boxes. Every step is a `- [ ]` line with the action,
then **→** what you should see. Tick what holds; where it does not, write
what you saw under the section in the *Results* table at the end, with the
time, the port and the command -- the convention of
[`2026-09-20-ender-bench.md`](2026-09-20-ender-bench.md), whose latch-side
checklist is the hardware half of section 6 and is not repeated here.

Two servers, on purpose:

- **Your own** (`uv run apothecary serve --reload`, port 8000): your real
  `~/.apothecary` (pins, readings, cameras), your real ports, and your own
  picture folder (the folder you start it in). Sections 2, 3, 4, 7 use it.
- **A demo one** (port 8001): temporary state, the scripted `arduino-cli`
  and the simulated printer, so nothing you do to it touches your pins or
  your board. Sections 5 and 6 use it. Section 6's hardware half uses your
  own server and the bench record's checklist.

Read the page for a topic before its section if you want the why:
[`../geometry-from-elsewhere.md`](../geometry-from-elsewhere.md),
[`../firmware.md`](../firmware.md), the one-screen plan, and the
stays-on-the-device record in `governance/qm/adr/`.

## 1. Setup

```bash
cd ~/Documents/apothecary
git status -sb                      # ## consolidate/2026-09-19...origin/consolidate/2026-09-19
git submodule status                # governance/qm at 20e00bd (the pin), or the adr/ branch if you were drafting
uv sync
uv run apothecary check             # OpenSCAD on PATH, playwright browsers, the parts count
```

- [ ] `apothecary check` → OpenSCAD found; 22 parts, none marked `•` (every
      part has a wrapper or a sidecar).
- [ ] Terminal A: `uv run apothecary serve --reload` → *Application startup
      complete*; a background `docs generate` starts (its log is
      `docs/generated/refresh.log`); STLs for parts that lack one are
      generated in the background -- expect `ender3.stl` and the five
      boards' STLs to appear under `parts/` within a minute. (A node asked
      for before its parts are built builds them first: a fresh clone
      answers `/sites/garage/nodes/printer_1/stl` on the first request.)
- [ ] Browser: `http://127.0.0.1:8000/viewer/sites/garage` → the garage, the
      workbench, three printers that look like Ender 3s (spools over the top
      bar, power supplies on the right), boards at the right end of the bench.
- [ ] `http://127.0.0.1:8000/docs` → the docs index, with a bar that says when
      the walkthroughs were last refreshed (it changes when the background
      run finishes).

## 2. Personal data stays on the device

The guard is the program's shape, not a setting: there is nothing to turn
on. Each check below is a door the record names; each should be shut.

```bash
# the process cannot reach past this machine, whichever way it is asked
uv run python -c "import apothecary, socket; socket.create_connection(('example.com', 80))"
uv run python -c "import apothecary, socket; socket.getaddrinfo('example.com', 443)"
uv run python -c "import apothecary, socket; s=socket.socket(); s.bind(('0.0.0.0', 0))"
uv run python -c "import apothecary, socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.sendto(b'x', ('127.0.0.53', 53))"
```

- [ ] Each of the four → `LeftTheMachine: ... refused to reach ...` naming
      the record. (The last is the resolver's stub on loopback: loopback is
      not this machine when a service there forwards.)
- [ ] `uv run apothecary serve --host 0.0.0.0 --port 8002` → refused before
      binding: *Apothecary listens on this machine only*.
- [ ] `uv run python -m uvicorn apothecary.api:app --host 0.0.0.0 --port 8002`
      → refused at the socket (`_socket.bind: refused`), not by the CLI.

```bash
# the server answers this machine only: client, bound address, Host, sender
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/cameras                        # 200
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: evil.example" http://127.0.0.1:8000/cameras  # 403
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: $(hostname)" http://127.0.0.1:8000/cameras   # 403
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Origin: https://evil.example" -H "Sec-Fetch-Site: cross-site" -H "Content-Type: application/json" -d '{}' http://127.0.0.1:8000/photos/gather   # 403
curl -s -o /dev/null -w "%{http_code}\n" -H "Sec-Fetch-Site: cross-site" -H "Sec-Fetch-Mode: navigate" http://127.0.0.1:8000/viewer/sites/garage   # 200: a link from elsewhere still opens a page
curl -sI http://127.0.0.1:8000/viewer/sites/garage | grep -i "content-security-policy\|referrer-policy"
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/docs                      # 404: Swagger is off
```

- [ ] The codes as commented; the CSP header lists `'self'` everywhere and no
      `http:`/`https:` host; `referrer-policy: no-referrer`.
- [ ] From a LAN machine (or `curl --interface <lan-ip>` here):
      `http://<this-machine's-lan-ip>:8000/` → connection refused (nothing
      listens there).
- [ ] `cat ~/.apothecary/tools/arduino-cli.yaml` → `skip_board_detection_calls:
      true`, `enable_notification: false`, the three package indexes. Every
      arduino-cli the seam runs is given this file; your own
      `~/.arduino15/arduino-cli.yaml` is not read under apothecary.
- [ ] `HTTPS_PROXY=http://10.0.0.1:3128 uv run apothecary firmware boards` →
      the same answer as without it: the child's environment carries no proxy
      and no `ARDUINO_*` override.
- [ ] Optional, with `strace`: `strace -f -e trace=network -o /tmp/scan.log
      uv run apothecary firmware boards`, then `grep -v "AF_UNIX\|127.0.0"
      /tmp/scan.log | grep connect` → nothing but the mDNS question to
      `224.0.0.251`/`ff02::fb` (named in the record, carries nothing of yours).
- [ ] `APOTHECARY_PICTURE_ROOT=$HOME uv run apothecary serve --port 8003
      --no-refresh-docs`, then `curl -s http://127.0.0.1:8003/photos/pictures`
      → a 500 whose text says the folder *holds everything of yours, not a
      folder of pictures*. Stop it. (Same for
      `APOTHECARY_PICTURE_ROOT=~/.apothecary`.)
- [ ] `ls -ld ~/.apothecary` → `drwx------` once anything has been saved
      there on this tip (a pin, a reading: the folder is made the account's
      alone on every write); so is `captures/` under any picture root, once a
      frame is kept.
- [ ] `uv run pytest -q tests/test_stays_local.py` → 20 passed. This file is
      the review: loosening any door is an edit here and to the record.

## 3. Geometry from elsewhere, and the bench drawn as it is

On your own server, in the garage.

- [ ] Zoom the camera (scroll) onto the bench: three **Ender 3s** -- the
      2040 frame, the bed on springs, the X gantry, the **power supply on the
      right side behind the upright**, the LCD off the front-right corner,
      the **spool on the bracket over the top bar**. Their cyan build-volume
      boxes sit on the bed at 95 mm, not on the bench, and inside the frame
      (not centred on the footprint, which the PSU skews).
- [ ] At the bench's right end: an ESP32 devkit standing on its pins, the
      footpedal, an **Arduino Uno** (teal, USB-B and jack on its left), a
      **Raspberry Pi 4** (green, the USB stacks and Ethernet on its right), a
      **Teensy 4.0** (small, on its pins). Contents lists 16 structures.
- [ ] Click `printer_1` in Contents → the Selected panel shows **Name,
      Position, Status** (editable: it is a structure) and then one row,
      **Part: ender3**. The Contents list keeps its height and scroll.
- [ ] Double-click `printer_1` → inside it: `frame_system` (the electronics
      box, with the **Creality V4.2.2** board inside) and `gantry_system` (the
      uprights, the top bar, the belt tensioner boss at the Y rail's front).
      The printer's own body is not drawn at this level -- it is the picture
      one level up, which is how the viewer treats every parent. *Zoom Out*.
- [ ] In the parts library (`/viewer/sites/parts_library`): 22 parts in a
      grid; double-click `arduino_uno` → the breadcrumb reads
      `parts_library › arduino_uno`, the Selected panel carries the part's
      section (SCAD source, readiness, no parameters -- it is described by
      its sidecar, not a wrapper). `ender3` has parameters: `z_axis`,
      `x_axis`, `y_axis`, `with_spool`, `with_lcd`.

Bring a file in:

```bash
cd ~/Documents/apothecary
printf 'v 0 0 0\nv 2 0 0\nv 2 1 0\nv 0 1 0\nv 0 0 3\nv 2 0 3\nv 2 1 3\nv 0 1 3\nf 1 2 3 4\nf 5 6 7 8\nf 1 2 6 5\nf 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\n' > /tmp/brick.obj
uv run apothecary parts import /tmp/brick.obj --name demo_brick --units in --up y \
    --title "A brick" --author "You" --license CC-BY-4.0 --url https://example.org/brick
uv run apothecary parts info demo_brick
ls parts/demo_brick/ ; cat parts/demo_brick/part.json
```

- [ ] `parts import` → `✓ demo_brick: 12 triangles, 50.8 x 76.2 x 25.4 mm`
      (2 x 1 x 3 inches, a quarter turn from Y-up), the folder listing
      (`demo_brick.mesh.stl`, `demo_brick.stl`, `demo_brick.scad`,
      `demo_brick.mesh.stl.license`, `part.json`), and a `Place it:` line
      with the footprint to paste.
- [ ] `parts info` → `category: imported`, bounds `min y -76.2`, the source
      block with your title, author, licence, URL and `obtained` today.
- [ ] Reload `/viewer/sites/parts_library` → 23 parts; `demo_brick` is a
      grid cell; double-click it → its SCAD is the one `import(...)` line.
- [ ] `uv run apothecary parts import /tmp/brick.obj --name demo_brick` →
      refused: *exists; --force replaces it*. With `--license CC-BY-NC-4.0`
      and `--force` → a yellow line: *a licence with a field-of-use
      restriction cannot be committed to this repository*; the part is still
      made, for your own use.
- [ ] `git status --short parts/demo_brick` → only `part.json`, the `.scad`
      and the `.license` file show; the two STLs are ignored (`*.stl`).
- [ ] Clean up: `rm -rf parts/demo_brick`.
- [ ] Optional, the union limit:
      `printf 'union(){ import("%s/parts/ender3/ender3.stl"); translate([1000,1000,1000]) cube(1); }\n' "$PWD" > /tmp/u.scad && openscad -o /tmp/u.stl /tmp/u.scad`
      → hundreds of facets and no `ERROR:` line. The same with
      `parts/matboard_cutter_mount/matboard_cutter_mount.stl` → a CGAL
      `ERROR:` and 6 facets: that mesh is one OpenSCAD 2021.01 drops from a
      union, which the docs page names.

## 4. One screen: the rail, the anchors, the machine in front of the world

On your own server, in the garage, with the page freshly loaded.

- [ ] Press **`** (or `~`) → the rail hides and a tab stands in for it; press
      again → back. Typing in a text box never triggers it.
- [ ] Drag the rail's inner edge → its width follows, between 220 px and half
      the page; press **⇄** in the rail's head (or drag its grip) → every
      panel moves to the other side.
- [ ] On the **Contents** panel: ▾ collapses it to its title; ⧉ floats it
      free (drag it by its title, resize from its corner); its title's ⧉
      again docks it back; ✕ closes it to a tab at the bottom right; the tab
      reopens it. Reload → the layout is remembered.
- [ ] Right-click the canvas → the ring; **Panels** → a cell per panel
      (Contents, Selected, Jobs, Layout Validation, Generated OpenSCAD, Rail,
      **Machine** (which groups the machine and its log), **Camera**); a
      digit toggles one.
- [ ] Select `printer_1`, press **m** → the node ring: Device, Control, Why
      this, Into, cardinals first, 5 backs out. (`Get shape` is a leaf's
      option; a machine with things inside it keeps its ring.)
- [ ] A **badge** floats above every pinned, connected board and follows it
      as you orbit; with nothing pinned there is none. Pin something in
      section 6 and come back: the badge appears; a click selects the node;
      clicking a printer's badge opens the **machine popup** tethered to the
      printer with a leader line; drag the popup → the tether lets go; the
      popup's jog moves the world's nozzle marker ahead of the next poll.
- [ ] `/firmware/monitor?port=<your port>` → the same module as the popup,
      as a page of its own, and `/firmware` → the toolchain page with its
      config row naming `~/.apothecary/tools/arduino-cli.yaml`.

## 5. The camera and the pictures

On the **demo server**, in a folder of pictures, so frames land somewhere you
mean:

```bash
mkdir -p /tmp/apothecary-pictures && cd /tmp/apothecary-pictures
ARDUINO_CLI=$(uv run --project ~/Documents/apothecary python -c "import sys; sys.path.insert(0, '$HOME/Documents/apothecary/tests'); from pathlib import Path; from firmware_helpers import write_fake_arduino_cli; print(write_fake_arduino_cli(Path('/tmp/fake-arduino-cli')))") \
APOTHECARY_SERIAL_ENGINE=simulated APOTHECARY_SIMULATED_PRINTER=printing \
APOTHECARY_STATE_DIR=/tmp/apothecary-demo APOTHECARY_TOOLS_DIR=/tmp/apothecary-demo/tools \
uv run --project ~/Documents/apothecary apothecary serve --port 8001 --no-refresh-docs
```

Open `http://127.0.0.1:8001/viewer/sites/garage`; ring → Panels → Camera.

- [ ] **Allow cameras** → the browser asks once; the list fills with your
      cameras by name; the chosen one shows live; the note says *is live*.
      (Chromium's fake camera works too: launch it with
      `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream`.)
- [ ] Select the workbench in Contents, **📍 Place at selected** → *placed at
      workbench in garage*; a camera badge and a frustum appear in the world;
      `curl -s http://127.0.0.1:8001/cameras?site=garage` → one camera, path
      `workbench`, with the browser's label for it -- kept in
      `/tmp/apothecary-demo/cameras.json` (0700), never anywhere else.
- [ ] Name `surroundings`, width `800`, **👁 Look** → within ~15 s the world
      opens the arrangement `surroundings`: the camera's own surroundings as
      the finder sees them (blobs as plates, discs, wedges). `ls
      /tmp/apothecary-pictures/captures/` → one PNG, and the folder is
      `drwx------`.
- [ ] Back to `garage` (site select) → the camera still stands where it was
      placed.
- [ ] The mark follows the focus: double-click `printer_1` → the badge and
      the frustum are gone (not at the top-left corner of the canvas, not
      anywhere); **Zoom Out** → both are back, above the bench, and the badge
      is not dimmed when nothing stands between you and the bench top.
      Double-click `workbench` → the badge stands above the bench and its
      tools.
- [ ] **📷 Capture** twice more with different names → the picture list grows;
      tick **all**, **Gather** → a report with *Groups*, the questions the
      machine thinks are worth your word (answered with buttons), and a
      `details` block; **Open as one** → a site `gathered_…` opens with the
      pieces of every ticked picture.
- [ ] **Unplace** → the badge leaves; `/cameras?site=garage` → `[]`.
- [ ] **add** (the file picker) → choose two pictures of your own → the
      note says *added 2 picture(s)*; they appear in the list *· added*,
      each with a ✕; `ls /tmp/apothecary-pictures/uploads/` → the two, named
      as you named them, the folder `drwx------`. Click one ✕ → gone from
      the list and from the folder; the tick-box did not toggle.
- [ ] *Cameras in the world* lists every placed camera (place one first);
      its row's **Unplace** takes it back, badge included. *Boards pinned
      to pieces* lists every pin: pin something from a piece's Device
      section (or by typed identity, `aa:bb:cc:dd:ee:ff`) → its row appears
      (⟳ if not); a pin whose site is gone -- pin a node of an arrangement,
      then forget the arrangement -- shows *site gone*; each row's
      **Unpin** takes it back, and the piece's Device section offers the
      ports again at once.
- [ ] **Purge kept** → asks once → every capture and upload is gone, the
      pictures you put in the folder by hand are still there
      (`ls /tmp/apothecary-pictures/`).
- [ ] Nothing left the machine: the only requests the page made are to
      `127.0.0.1:8001` (the browser's network panel; the CSP would have
      refused anything else).

## 6. The printer, without hardware and with it

**Without** -- on the demo server from section 5 (the simulated printer,
mid-print; two scripted ports, `/dev/ttyFAKE0` an Uno and `/dev/ttyFAKE1` a
bare board):

- [ ] Select `printer_1 › frame_system › mainboard` in the viewer; the
      Device section offers a pick list of free ports → choose
      `/dev/ttyFAKE1`, **Query** → an M115 answer from the simulator, **Pin**
      → the section shows the last poll (`printing`, temperatures, `XX %`);
      `printer_1`'s row wears the 🖨 badge and its status becomes `printing`
      *via* the board.
- [ ] The badge above `printer_1` in the world; click it → the machine popup:
      status cards, a temperature chart after a few polls, the comms log as a
      panel on the left rail.
- [ ] **⚙ Control** → the overlay, a 5:00 latch; **Bed 45 → Set** → `M140
      S45` in the log and the target on the card; **Home XY**; **Y+** by 10 →
      the nozzle marker in the world moves; **Off**.
- [ ] Bed level: **Read mesh** → a record with a heatmap (the simulator's
      tilted, bowed bed) and a relief drawn on the bed in the world at the
      printer's `build_origin`; **▤ Probe bed** → confirm → a job that holds
      the port, then a second record.
- [ ] Print from here: **Choose File** →
      `docs/validation/dry-run-square.gcode` → **▶ Print** → confirm → lines
      stream one per `ok`; **⏸ Pause**, **Resume**, **■ Cancel** → the safe-off
      lines in amber; `GET /firmware/printers/print/records` → the record
      with its outcome.
- [ ] `curl -s "http://127.0.0.1:8001/firmware/printers/where?port=/dev/ttyFAKE1"`
      → `build_volume [220,220,250]`, `build_origin [90,100,95]`,
      `base_height 95`, the board inside the printer at (80, 90, 26).
- [ ] Stop the demo server. `ls /tmp/apothecary-demo` → `firmware-state.json`,
      `cameras.json`, `leveling/`, `prints/`: everything the demo kept, in
      the folder you gave it, and nothing under your own `~/.apothecary`.

**With hardware** -- your own server, the board plugged in: the latch-side
checklist in [`2026-09-20-ender-bench.md`](2026-09-20-ender-bench.md)
(heaters, motion, the corner checks, a probe, a print from here, E-STOP,
release), unchanged, plus these two that the bench did not have:

- [ ] `apothecary firmware boards` with the board plugged in → the port and
      its `0403:6001` as before; `~/.arduino15/inventory.yaml` does **not**
      gain a new `cache:` entry with today's time: the cloud lookup is off.
- [ ] Pin it to `printer_1.frame_system.mainboard` → the bed reading's relief
      and the nozzle marker sit on the Ender 3 model's bed in the world, and
      the board view on the monitor page draws the whole machine as the
      body, the board in its box at the front left.

## 7. The docs, and the walkthrough

- [ ] `http://127.0.0.1:8000/docs/geometry-from-elsewhere.md`,
      `/docs/firmware.md`, `/docs/plans/photo-finders-local-models-2026-09-21.md`,
      `/docs/plans/pull-requests-2026-09-21.md` → rendered, links between
      pages work, every image is local (a picture from elsewhere would be
      named, not fetched).
- [ ] `/walkthrough/11-photographs-into-pieces.md` → the page says *137
      controls of the viewer's own* and shows the rail and the camera panel
      in its screenshots.
- [ ] `/walkthrough/12-the-bench-as-it-is.md` → fourteen steps: a file from
      elsewhere measured, the sidecar part, the Ender 3s, the mainboard, the
      DevKitC, the camera placed at the bench and *not* following you into a
      printer, what the browser put here taken back (added pictures, a pin,
      a purge), the guard's refusal and the server's 403 -- each with the
      output or the picture of the run that wrote it.
- [ ] `uv run apothecary docs generate` → both doc workflows regenerate under
      a temporary server on 8766; the bar on every docs page then says when.
      The two walkthrough pages (11 and 12) are rewritten by the ordinary
      test command instead (`uv run apothecary test run`), screenshots
      included.

## 8. The suites and the gates

```bash
uv run pytest walkthrough -q                 # 10 pages, as doctests
uv run apothecary test all                   # 1166 unit + 73 browser, on fenced state and pictures
uv run --with "reuse[charset-normalizer]" python -m reuse lint
git -C governance/qm log --oneline origin/project/apothecary..adr/firmware-toolchain-seam   # six records
```

- [ ] All green; `test all` never touches `~/.apothecary` or your pictures
      (its server runs on a temp state dir and a temp picture folder).
- [ ] `uv run pytest -q tests/test_geometry_from_elsewhere.py` → 8 passed
      (the mesh reader, `Import`, the sidecar importer, `parts import`, the
      garage's printers and boards, the cache key, the licence rule).

## Results

Fill this in as you go; anything refused or slow gets its time, port and
command. Outcomes that change a number in a doc go to that doc; a defect
goes to the queue page ([`../plans/queue-2026-09-20.md`](../plans/queue-2026-09-20.md))
or an issue; a door found open goes to the record's risk register.

| Section | Ticked | Notes (what, when, port, command) |
|---|---|---|
| 1. Setup | / 4 | |
| 2. Stays on the device | / 12 | |
| 3. Geometry | / 12 | |
| 4. One screen | / 7 | |
| 5. Camera | / 11 | |
| 6. Printer (simulated) | / 7 | |
| 6. Printer (hardware) | / 2 + the bench record | |
| 7. Docs | / 4 | |
| 8. Suites | / 2 | |
