# 20 — A part through the router

**Hermetic.** The controller here is the simulated one; nothing opens a port.

This page is run by `uv run pytest` (the quick loop) and by `apothecary test
run`, as a doctest: every value shown is the value the run computed, and a
run that computes another fails here. The examples drive the seam in this
process against the simulated controller (`grbl.SimulatedRouter`), its moves
taking no time; nothing opens a port, and the real router is section I of
[docs/bench-checklist.md](../docs/bench-checklist.md).

The subtractive loop, station by station, on one part: a design that says how
it is cut, the toolpath written from it, the cut streamed from here, the job
watched, the cut measured against the design, and the design changed and cut
again. [docs/cam.md](../docs/cam.md) is the reference for the toolpath,
[docs/cnc.md](../docs/cnc.md) for the router, and
[the plan](../docs/plans/subtractive-loop-2026-11-04.md) for what comes next.

## The design: a coupon on the router's table

The garage holds a router coupon -- a plate with a pocket and a column of
holes (`parts/router_coupon`) -- on a spoilboard on the router's table, its
stock's front-left corner at the working area's and the plate `stock_margin`
in from it:

    >>> from apothecary.example_hierarchy import CNC_ROUTER_POSITION, create_example_site
    >>> from apothecary.projects.parts import anolex_4060_evo_ultra_2 as anolex
    >>> site = create_example_site()
    >>> coupon = next(piece for piece in site.children if piece.name == "router_coupon")
    >>> coupon.part_ref
    'router_coupon'
    >>> zero = CNC_ROUTER_POSITION + anolex.WORK_ORIGIN
    >>> (coupon.position.x - zero.x, coupon.position.y - zero.y, coupon.position.z - zero.z)
    (10.0, 10.0, 5.0)

Beside its geometry the part says how it is cut: the stock it comes from, and
the operations that make it, in order -- the pocket, the holes, the outline --
each a parameter's worth of size:

    >>> from apothecary.projects.parts.router_coupon import DEFAULT as part, Params
    >>> cuts = part.cuts()
    >>> (cuts.stock.x, cuts.stock.y, cuts.stock.thickness)
    (140.0, 100.0, 10.0)
    >>> [(op.kind, op.depth) for op in cuts.operations]
    [('pocket', 4.0), ('hole', 10.5), ('hole', 10.5), ('outline', 10.5)]
    >>> (cuts.tool.label, cuts.feeds.cut, cuts.feeds.plunge, cuts.feeds.rpm)
    ('6 mm two-flute end mill', 800.0, 300.0, 12000)

## The toolpath

`apothecary.cam.toolpath.write` turns the cuts into GRBL's dialect: a header
that names what it is for, the tool lifted first whatever it stood at, the
spindle up to speed, then each operation in passes of two millimetres, each
pass announced on the line before it so the cut can say where it is.

    >>> from apothecary.cam import toolpath
    >>> written = toolpath.write(cuts, "router_coupon")
    >>> print("\n".join(written.lines[:14]))
    (apothecary toolpath: router_coupon)
    (tool: 6 mm two-flute end mill, 6 mm, 2 flutes)
    (stock: 140 x 100 x 10 mm, zero at its front-left top corner)
    (feeds: cut 800, plunge 300 mm/min, 12000 rpm; 2 mm a pass)
    G21
    G90
    G17
    G54
    G0 Z5
    M3 S12000
    G4 P2
    (op 1/4 pass 1/2: pocket 40 x 30 at 30,35 to z -2)
    G0 X33 Y38
    G1 Z-2 F300
    >>> [(op.words, op.passes) for op in written.operations]
    [('pocket 40 x 30 at 30,35, 4 deep', 2), ('hole 3 mm at 110,36.667, 10.5 deep', 6), ('hole 3 mm at 110,63.333, 10.5 deep', 6), ('outline 120 x 80 at 10,10, 10.5 deep', 6)]
    >>> (len(written.lines), written.length_mm, written.time_s)
    (129, 3533.1, 278.6)

The holes are 3 mm and the tool is 6: they cannot be cut as designed. The
toolpath bores them to the tool, and says so. That is the fact the cut hands
back to the design.

    >>> for message in written.messages:
    ...     print(message)
    hole 3 mm at 110,36.667 is smaller than the 6 mm tool: bored to the tool
    hole 3 mm at 110,63.333 is smaller than the 6 mm tool: bored to the tool

The file is checked in the router's dialect, as any file kept for a router is:
the lines it would send, and every reason it may not be sent.

    >>> from apothecary.firmware import grbl
    >>> grbl.check_gcode(toolpath.text(written))
    (105, [])

## Kept, and cut from here

`apothecary.cam.service.cut_into` writes the toolpath for a router, keeps it
where the Cut card keeps a file, and records what made it beside the file. In
the page this is the Cut card's **Toolpath**, or Toolpath on the part's ring.

    >>> from apothecary.cam import service
    >>> from apothecary.cam.models import CutFor
    >>> PORT = "/dev/ttySIM"
    >>> record = service.cut_into("router_coupon", CutFor(name="cnc_router", site="garage", port=PORT))
    >>> (record.name, record.lines, record.problems)
    ('router_coupon-cnc_router.nc', 105, [])
    >>> service.get_record(record.file_id) == record
    True

The controller, simulated, is identified, the latch armed, and the work zero
set at the stock's corner where the tool stands -- the pad's Zero. The
toolpath's coordinates count from that corner; without it the first move
would be outside the travel, and the controller would say so.

    >>> from apothecary.firmware import devices, gcode, grbl
    >>> from apothecary.firmware.models import DeviceInfo
    >>> links = gcode.PrinterLinks(factory=grbl.SimulatedRouter)
    >>> link = links.open(PORT, 115200)
    >>> link._t.time_scale = 0   # its moves take no time on this page
    >>> info = grbl.identify_router(link)
    >>> devices.get_state().remember_device(DeviceInfo(port=PORT, label="the simulated router", printer=info))
    >>> _ = links.control.arm(PORT)
    >>> devices.printer_control(PORT, "G10 L20 P1 X0 Y0 Z0", links=links).lines
    ['ok']

Then the cut: a job of the router, streamed a line at a time with the
planner's room counted, naming the operation it is in as it goes.

    >>> job = devices.start_print(PORT, record.file_id, links=links)
    >>> job.thread.join(10)
    >>> (job.stage, job.error, job.sent, job.total)
    ('done', None, 105, 105)
    >>> job.snapshot()["operation"]
    'op 4/4 pass 6/6: outline 120 x 80 at 10,10 to z -10.5'

## Watched

The job is a record of the router's, as a print's is of the printer's; the
next poll finds the controller idle again, its spindle off, the tool back over
the zero at the safe height.

    >>> (job.record.kind, job.record.machine.kind, job.record.outcome, job.record.detail["sent"])
    ('cut', 'router', 'done', 105)
    >>> status = devices.printer_status(PORT, links=links)
    >>> (status.state, status.spindle.on, status.work_position)
    ('idle', False, {'x': 0.0, 'y': 0.0, 'z': 5.0})

A cut that takes time is watched the same way, poll by poll: the Machine's
progress line names the operation beside the percentage, the badge wears
*running · cut*, and the Status card shows the tool moving in the work zero
and in machine coordinates (page 19's cards; `tests/e2e/test_router_ui.py`
drives one in a browser).

## As cut, measured against the design

The simulated controller kept every block it ran. The cutting moves at a
depth, widened by the tool's radius, are the material gone: the pocket as cut
is the pocket as designed, and each hole is the tool's width, not the
design's.

    >>> from apothecary.cam import measure
    >>> trace = link._t.trace
    >>> pocket = cuts.operations[0]
    >>> around = (pocket.x - 1, pocket.y - 1, pocket.x + pocket.w + 1, pocket.y + pocket.h + 1)
    >>> measure.size(measure.extent(trace, z=-pocket.depth, tool_diameter=cuts.tool.diameter, within=around))
    (40.0, 30.0)
    >>> hole = cuts.operations[1]
    >>> around = (hole.x - 5, hole.y - 5, hole.x + 5, hole.y + 5)
    >>> measure.size(measure.extent(trace, z=-1, tool_diameter=cuts.tool.diameter, within=around))
    (6.0, 6.0)
    >>> hole.diameter
    3.0

## The iteration

The design changes where the cut said it must: the holes become 8 mm, wider
than the tool, so they are bored in circles. The toolpath has nothing to say
this time, and the cut, run again, leaves holes of the size designed.

    >>> cuts = part.cuts(Params(hole_diameter=8).model_dump())
    >>> written = toolpath.write(cuts, "router_coupon")
    >>> (written.messages, written.operations[1].words)
    ([], 'hole 8 mm at 110,36.667, 10.5 deep')
    >>> kept = devices.save_print_file("router_coupon-8mm.nc", toolpath.text(written).encode(), machine="router")
    >>> link._t.trace.clear()
    >>> job = devices.start_print(PORT, kept.id, links=links)
    >>> job.thread.join(10)
    >>> job.stage
    'done'
    >>> hole = cuts.operations[1]
    >>> around = (hole.x - 6, hole.y - 6, hole.x + 6, hole.y + 6)
    >>> measure.size(measure.extent(link._t.trace, z=-1, tool_diameter=cuts.tool.diameter, within=around))
    (8.0, 8.0)
    >>> links.close(PORT)
    True

In the page the same change is the part's editor -- Part › Edit, the hole's
size, Apply -- then Toolpath on the variant drawn, then ▶ Cut;
`tests/e2e/test_router_ui.py` goes round it in a browser. What this page does
not show is the bench: the real controller has been identified and polled once, and a
real coupon has not been measured by hand. That is the plan's next slice.
