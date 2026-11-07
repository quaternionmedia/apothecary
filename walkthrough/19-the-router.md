# The router

**Hermetic.** The controller here is the simulated one; nothing opens a port.

The garage's second machine is a CNC router, an AnoleX 4060-Evo Ultra 2 drawn
from published dimensions ([the part](../parts/anolex_4060_evo_ultra_2/README.md)),
on a stand beside storage. Its working area is its build volume, and the
tool's (0, 0, 0) is on the table at the working area's front-left corner, so
the world's marks and a job's volume stand on the real table rather than on
the floor of its footprint.

    >>> from apothecary.example_hierarchy import create_example_site
    >>> site = create_example_site()
    >>> router = next(s for s in site.children if s.name == "cnc_router")
    >>> router.part_ref, router.build_volume.to_list(), router.build_origin.to_list()
    ('anolex_4060_evo_ultra_2', [400.0, 600.0, 80.0], [115.0, 165.0, 100.0])

It is built as printer_1 is: a `frame_system`, the control box at the back
of the base holding the controller, and a `gantry_system`, the gantry riding
the Y rails with the Z carriage on its cross beam and the trim router in the
carriage's 65 mm clamp. The gantry's pieces stand where the part draws them
with its axes at their defaults, placed from the part's own constants.

    >>> [c.name for c in router.children]
    ['frame_system', 'gantry_system']
    >>> gantry = router.children[1]
    >>> [a.name for a in gantry.additions], [c.name for c in gantry.children]
    (['left_leg', 'right_leg', 'cross_beam'], ['z_carriage_system'])
    >>> clamp = next(a for a in gantry.children[0].additions if a.name == "clamp")
    >>> spindle = clamp.children[0]
    >>> spindle.name, spindle.base.v.to_list(), spindle.base.children[0].r
    ('spindle', [315.0, 465.0, 148.0], 32.5)

Its controller runs Grbl_ESP32 and speaks GRBL's dialect of G-code, which
differs from Marlin's in the places this seam cares about: a board is
identified by `$I`, there being no `M115`; a poll is the realtime `?` and
`$G`; what may be typed at it is another short list; and the stop is a soft
reset. The port is pinned to the controller inside the control box, as
printer_1's is to its mainboard, and the router above it takes the
controller's state. The controller is drawn as the board it is assumed to be
([the board](../parts/boards/anolex_grbl_esp32/README.md): the maker
publishes no drawing of it).

    >>> box = router.children[0]
    >>> [c.name for c in box.children], box.children[0].part_ref, box.children[0].comment
    (['controller'], 'anolex_grbl_esp32', "Controller (Grbl_ESP32) -- pin the router's port here")

## The dialect

A status report, as the controller writes one, read into its fields. The
report carries the machine position or the work position and, every few
reports, the offset between them; whichever is missing is computed.

    >>> from apothecary.firmware import grbl
    >>> report = grbl.parse_status("<Run|MPos:-120.000,-250.500,-3.000|FS:800,12000|WCO:-115.000,-165.000,-3.000>")
    >>> report["machine_state"], report["mpos"], report["wpos"]
    ('Run', {'x': -120.0, 'y': -250.5, 'z': -3.0}, {'x': -5.0, 'y': -85.5, 'z': 0.0})
    >>> grbl.site_state("Run"), grbl.site_state("Hold"), grbl.site_state("Alarm")
    ('running', 'hold', 'alarm')

What may be typed at an armed router is a short list, each line bounded for
this machine -- a jog no longer than its longest axis, a feed no faster than
the maker's figure, a spindle no faster than the trim router turns. A line
the dialect knows but bounds is refused as `OutOfBounds`, a `ValueError` of
its own, and the rest is refused before it reaches the port:

    >>> grbl.normalise_control("$J=G91 G21 x10 f500")
    '$J=G91 G21 X10 F500'
    >>> grbl.normalise_control("M3 S30000")
    Traceback (most recent call last):
    ...
    apothecary.firmware.gcode.OutOfBounds: spindle above 24000 rpm: 'M3 S30000'

A file a CAM post wrote is checked once before its first line, in the router's
dialect: what every dialect refuses and what GRBL's own rules do, so a controller
setting, a tool change, a code GRBL does not take or a spindle over the cap keep
it from being sent.

    >>> grbl.check_gcode("G21 G90\n$110=5000\nM3 S12000\nG1 X-50 F800\nM5\n")
    (5, ["line 2: $110=5000 is a controller setting, not a job's to send"])

## The simulated controller

The pretend controller behind the transport slot answers as Grbl_ESP32 does.
Its machine coordinates run negative from the home corner at the back right
and the top of Z, as a Grbl machine homed to its maximum switches has them,
so the tool stands in the working area at `mpos + travel`: here the middle
of the table, where the part draws it.

    >>> from apothecary.firmware import gcode
    >>> links = gcode.PrinterLinks(factory=grbl.SimulatedRouter)
    >>> link = links.open("/dev/ttySIM", 115200)
    >>> link._t.time_scale = 0   # its moves take no time on this page
    >>> info = grbl.identify_router(link)
    >>> info.firmware_name, info.machine, info.dialect
    ('Grbl 1.3a', 'router', 'grbl')
    >>> status = grbl.poll_router(link)
    >>> status.state, status.machine_state, status.position
    ('idle', 'Idle', {'x': -200.0, 'y': -300.0, 'z': -40.0})

The spindle on at a speed and a jog, each one allowlisted line; the next
poll says what they did.

    >>> grbl.control_router(link, "M3 S12000"), grbl.control_router(link, "$J=G91 G21 X10 F500")
    (['ok'], ['ok'])
    >>> status = grbl.poll_router(link)
    >>> status.spindle.on, status.spindle.rpm, status.position["x"]
    (True, 12000.0, -190.0)

The stop is the soft reset, written ahead of whatever the link is doing:
everything halts, the queue empties, the spindle is off, and the controller
says its banner.

    >>> grbl.control_router(link, "RESET")[-1]
    "Grbl 1.3a ['$' for help]"
    >>> grbl.poll_router(link).spindle.on
    False

## The table map

The router's bed reading is its own kind. A printer keeps a mesh its firmware
probed and prints it on request; a GRBL controller keeps none, so the
router's table is mapped from here: Z probed with the touch plate at each
point of a grid over the working area, from the top of Z, in machine
coordinates so a person's work zero is neither used nor moved. The working
area is the controller's own word, its maximum travel. The simulated
controller answers a probe with a flat plate 20 mm under the tool, so its map
is flat, every touch 23 mm down from the top of the travel; the record says
where the grid lies from the working area's front-left corner.

    >>> from apothecary.firmware.models import TableGrid
    >>> reading = grbl.probe_table(link, grid=TableGrid(rows=2, cols=3, inset=50))
    >>> reading.method, reading.mesh
    ('G38.2', [[-23.0, -23.0, -23.0], [-23.0, -23.0, -23.0]])
    >>> reading.stats["range"], reading.area
    (0.0, {'min': {'x': 50.0, 'y': 50.0}, 'max': {'x': 350.0, 'y': 550.0}})

Each point was a rapid there in machine coordinates, the probe down as far as
the travel allows, and the lift back to the top, every line one the pad could
send and bounded the same way; the controller's own word on the last touch
(`$#`) is kept with the lines, after the touch itself.

    >>> [ln for ln in reading.lines if ln.startswith("[PRB:")][-2:]
    ['[PRB:-50.000,-50.000,-23.000:1]', '[PRB:-50.000,-50.000,-23.000:1]']
    >>> links.close("/dev/ttySIM")
    True

Kept as a bed reading of the router's, a map is listed for its board, laid
over its table in the world where its points were probed, and shown in its
Machine's Table map card, which takes the next one
([docs/firmware.md](../docs/firmware.md#bed-leveling)).

[docs/cnc.md](../docs/cnc.md) says what of the router is built and what is
not: the page's window for it, the demo's pin and the bench's confirmation
are the next pages of this one.
