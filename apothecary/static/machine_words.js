/* The words of each kind of board, said once: what the page calls a printer, a
 * router and a devkit wherever it names one -- the Machine's cards and buttons
 * (widgets/machine.js), a board's badge and row (board_text.js), and the status
 * words a person may set (the viewer). A kind's word written anywhere else is a
 * second copy that drifts; apothecary/census.py describes the controls these
 * words label.
 *
 * A G-code kind: `job` is what it runs (apothecary/jobs.py), `dialect` what its
 * board answers in, `running` the status its node takes while a job runs, `stop`
 * its emergency stop's line, `prepare` the step that makes a file to run (a
 * printer's Slice, a router's Toolpath), `byHand` the status words a person sets
 * on its node (the rest its polls set), `feedMax` and `feedDefault` the jog feed's
 * bound and default in mm/min, `files` what a job streams, `slice` whether a file
 * is sliced here, `verb` what a person does with a file, `volume` what its build
 * volume is called, `homeAxis` the title of an axis's home button, `level` its bed reading's words (a printer's bed, a router's
 * table map: the card, its probe button, the stats line, the question asked before
 * the machine moves). A devkit runs nothing from here and has the few words below.
 */
export const KINDS = {
    printer: {
        icon: "🖨", job: "print", verb: "Print", volume: "Build volume", dialect: "marlin", running: "printing", stop: "M112", can: "heat and move",
        fileTitle: "A sliced G-code file to keep on the host. It is checked (no EEPROM writes, no temperatures over the caps) and listed here; nothing is sent until Print",
        partTitle: "The part or piece this print makes, from the site the printer is pinned in: the print's job records it, and Site lists the job. The ring's Send file prints what is chosen here",
        notIdentified: "not identified as a printer",
        byHand: ["idle", "printing", "offline", "maintenance"],
        feedMax: 12000, feedDefault: 3000, files: ".gcode,.gco,.g,.txt,text/plain", slice: true,
        prepare: "Slice",
        prepareTitle: "Slice what is chosen under makes for this printer: its G-code is kept here and chosen, so ▶ Print follows. Writes files only; nothing is sent to the printer. Its ring's Slice does the same",
        identify: "M115", poll: "One poll now (M105/M114/M27/M119)", queries: "report code — M503, M119, M20, M420 V …",
        homeAxis: (a) => `Home ${a} alone (G28 ${a}): the other axes stay where they stand. Moves the machine: control must be armed`,
        start: "▶ Print", title: "Print from here",
        startTitle: "Stream the chosen file to the printer. Heats and moves: control must be armed. ⌗ Control › Print › Send file",
        pause: "Stop feeding lines; the printer finishes what it has queued",
        cancel: "Stop feeding, then heaters off, fan off, motors free",
        estop: "M112: emergency stop. Always available, latch or not. Halts the board until it is reset.",
        arm: "Arm the control latch: heaters, fan, homing, bounded jogs and SD pause/resume/abort become available in an overlay for 5 minutes of activity. Disarmed, nothing on this page can heat or move the machine.",
        level: { card: "Bed level", button: "▤ Probe bed", buttonTitle: "G28, G29, then read the mesh, the probe offset and the temperatures; saved as a record. Moves the machine: control must be armed. ⌗ Control › Level › Probe", none: "no reading yet", across: "across the bed", ask: "Home and probe the bed on {port}?\nThe nozzle will travel the whole bed." },
    },
    router: {
        icon: "🪚", job: "cut", verb: "Cut", volume: "Working area", dialect: "grbl", running: "running", stop: "RESET", can: "turn and move",
        fileTitle: "A CAM post's file to keep on the host. It is checked (no settings, no tool change, no spindle over the router's) and listed here; nothing is sent until Cut",
        partTitle: "The part this cut makes, from the site the router is pinned in: the cut's job names it, and Toolpath writes its toolpath from the cuts it declares",
        notIdentified: "not identified as a router",
        byHand: ["idle", "offline", "maintenance"],
        feedMax: 4000, feedDefault: 1000, files: ".nc,.ngc,.gcode,.tap,.txt,text/plain", slice: false,
        prepare: "Toolpath",
        prepareTitle: "Write the toolpath of what is chosen under makes for this router, from the cuts the part declares: it is kept here and chosen, so ▶ Cut follows. Writes files only; nothing is sent to the router. Its ring's Toolpath does the same",
        identify: "$I", poll: "One poll now (? and $G)", queries: "query — $$, $#, $G, $I, ?",
        homeAxis: (a) => `Home ${a} alone ($H${a}): the other axes stay where they stand. Moves the machine: control must be armed`,
        start: "▶ Cut", title: "Cut from here",
        startTitle: "Stream the chosen file to the router. Turns the spindle and moves: control must be armed. ⌗ Control › Cut › Send file",
        pause: "Feed hold: the controller stops where it is, and nothing more is fed",
        cancel: "Hold, then the soft reset: the queue empties and the spindle is off",
        estop: "Soft reset (0x18): everything halts, the queue empties, the spindle is off. Always available, latch or not. A reset in motion leaves the controller in alarm: Unlock or Home.",
        arm: "Arm the control latch: homing, unlock, bounded jogs, the spindle, work zero, a probe and the cut's hold and resume become available in an overlay for 5 minutes of activity. Disarmed, nothing on this page can turn or move the machine.",
        level: { card: "Table map", button: "▦ Probe table", buttonTitle: "Spindle off, home, then at each point of a three-by-three grid inside the working area, from the top of Z: there in machine coordinates (G53 G0), down to the plate (G38.2), up again. The touches are kept as a record, in machine coordinates, and drawn over the table. Moves the machine: control must be armed, and the probe's lead clipped to the table", none: "no map yet", across: "across the table", ask: "Home and probe the table on {port}?\nThe tool will travel the whole working area, probing down at each of nine points. The probe's lead must be clipped to the table." },
    },
    devkit: { icon: "⚡", job: null, dialect: null },
};

// The G-code kinds, the ones a job streams to.
export const GCODE_KINDS = ["printer", "router"];

// The class a badge or a row wears for a machine's state word; none for the rest.
export const STATE_CLS = { printing: "printing", running: "printing", offline: "offline", heating: "heating", alarm: "mismatch" };

// A board's kind from what the server knows of it: a G-code board's `printer.machine`
// (printer or router), else a devkit.
export function kindOf(device) {
    if (!device || !device.printer) return "devkit";
    return device.printer.machine === "router" ? "router" : "printer";
}
