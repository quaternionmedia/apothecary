/* The Machine: one board, close up, wherever it is mounted -- the one place for it.
 *
 * A printer's Machine is the header's link verbs and the control latch, the status
 * cards, the temperature chart, the control pad, the bed reading, the print from
 * here (a print job, naming the part it makes, and the printer's jobs as its
 * history). A devkit's Machine
 * is its port and what it is, the sketch it should run against what it was
 * heard saying, and its Flashing card: a sketch (what it should run, to start
 * with) -- an Arduino one built for a board, or a Rust one for its chip --
 * uploaded to this port, after asking, the task's output, then Identify -- the
 * Bench's form and task log (widgets/sketches.js, tasks.js), for this one port. Both have the board's one log, a printer's with
 * the one box that asks it for a report: the comms log the server keeps for the
 * port (poll traffic hidden unless asked for), or a devkit's serial output.
 *
 * A devkit's port is opened only when asked: opening its Machine shows what is
 * known of it and touches no port. Listen streams what it says (opening the
 * port may reset the board); Identify listens a few seconds for its hello and,
 * pressed, asks M115 when none was heard; Probe asks esptool what the chip is;
 * an upload is followed by Identify's listen, never by its M115.
 *
 * The board itself is boards.js's: the Machine watches it (a printer polled at
 * the interval its head says, a devkit listened to), draws what the model's
 * `apothecary:board` events say of it, and asks the model to poll, identify,
 * query, reconnect, reset and release. Everything else that draws the board
 * reads the same model, so nothing polls it a second time.
 *
 * A printer's control pad -- heaters, motion, the SD print, leveling -- shows
 * while its latch is armed. It pops out whenever the latch is armed, from here,
 * the ring or another browser: into the host's loud window (padWindow), a window
 * of its own beside the world, wherever the person is looking and whatever tab
 * is in front, since a real machine armed can heat and move. There it has an
 * E-STOP of its own, the Machine's head being in another window. Its ⇥ Put back, or
 * its window's ✕, puts it back as the last thing in the Machine's column; its
 * ⧉ Pop out pops it out again.
 *
 * mountMachine(root, { base, port, host, boards, kind, inPrinter, pin, name, say, padWindow, variantFor, sections, afterPrint, afterHello })
 * renders into `root` -- the head, what the board is and its state -- and each of
 * its sections (the Machine's entry in apothecary/systems.py: Status, Temperature,
 * Print, Bed level, Sketch, Flashing, Log) into the element `sections` gives for it,
 * a window of its own; a section given none stays in `root`. A button that is a ring
 * verb's tells `onVerb(action)` when pressed, as the ring's cell does; `onKind(kind)` is
 * told the board's kind each time it is known anew, so the host shows that kind's
 * sections. It returns the handle
 * the ring drives (carry, pairs,
 * device), the world asks to list its site's parts again when a piece is made,
 * rebuilt or dropped (print.loadChoices), to choose the piece a made piece's
 * Print names (print.choose), to slice what is chosen (print.slice), to choose a
 * kept file made from a part (print.fileOf) and to draw
 * the chosen file's path for the Machine view (print.show), and the
 * tests read (state, ctl, level, print).
 *
 * A printer's Print from here slices too (docs/slicer.md): its
 * Slice slices the part or piece chosen under makes for this printer (POST
 * /slicer/slice, the slicer's task followed in the card, with Cancel); the G-code
 * it keeps is chosen in the card's files, so ▶ Print follows Slice; then the
 * card says what the slice used, each value with where it came from, the
 * slicer's estimate, and its errors and warnings by line. A kept file a slice
 * made says what it was sliced from and for which printer. What the piece made of it
 * measures and shows is said in its part's Feedback, not here (widgets/feedback.js).
 * The window's first line says the step a person is at and what is next: what to
 * choose, Slice, ▶ Print and why it waits, the job streaming and where its end goes.
 * Its jobs are listed under it, newest first; a row of one that made a piece opens
 * that piece's drawer in Part › Feedback (`openDrawer(job)`, the host's).
 * `host` is "world": the world's page, a window of its layout, one board and
 * everything inline in one column; /firmware/monitor opens the world's page with
 * this Machine.
 * `boards` is the page's model, made here when none is given.
 * `kind` is "printer" or "devkit"; left out, it is whatever the board is. `inPrinter`
 * says the board is pinned inside a printer: a printer's board, never flashed,
 * whatever it has been identified as so far, so its Flashing card folds away and
 * Device › Flash says why. `pin` ({ site, path, how }) is where the board is pinned, or bound
 * by its sketch when `how` is "sketch". `name` is what the world calls the board's
 * Machine (the printer it is in), named on the control pad; left out, the port.
 * `padWindow` ({ open(pad, who), close(pad, putBack) }) is where the pad stands
 * popped out: the host opens a loud window holding it, and closes it when the pad
 * goes back (`putBack` when a person put it back, not when the latch disarmed);
 * the window's own ✕ is the handle's padBack(). Without it the pad stays in the
 * Machine. `say(text,
 * kind)` is the host's status bar: a refusal is said there as an error as well
 * as in the log; a print started is said there, naming where it is followed, and
 * a print that ends, how it ended (failed, and why, as an error). `variantFor(path)`
 * names the applied variant the page draws a part from, or null, so Slice slices
 * the part as drawn. `afterPrint(job)` names what comes next once a print ends, done,
 * cancelled or failed, said after how it ended, or null; `afterHello(sketch)` the same once a devkit is
 * heard saying the hello of the sketch it runs. destroy() stops watching and frees what the module put on the
 * window.
 */

import { mountBoards } from "/static/boards.js";
import { esc, heaterText, boardLabel, sketchWords, xyz, xyzHtml } from "/static/board_text.js";
import { clock, degrees, heater, mm as mmText, sentence, span, stamp, viaRing } from "/static/format.js";
import { toolPosition as toolPositionOf, fileOrigin, MOVE_COLORS } from "/static/machine_marks.js";
import { KINDS, kindOf as kindOfBoard } from "/static/machine_words.js";
import { ADHESION, LEVELLING, offsetOptions, options, own, words as firstLayerWords } from "/static/first_layer.js";
import { mountBuild } from "/static/widgets/sketches.js";
import { mountTasks } from "/static/widgets/tasks.js";
import { again } from "/static/twice.js";
import { applyCan, NEEDS_THE_LATCH, refreshDisabled, setReason, setTip, verbOfLine, withLatch } from "/static/can.js";
import { running as knobsRunning, choose as chooseKnobs } from "/static/deck_knobs.js";

const MAX_HISTORY = 300;

// What is a printer's alone carries `printer-only`, a router's `router-only`, a
// devkit's `devkit-only`; what the two G-code machines share carries `gcode` as
// well; the root's kind-* class shows one set. Written once, so each control is one.
const HEAD = `
<div class="machine-head">
    <span class="dot" id="dot"></span>
    <span id="ident" class="kv">—</span>
    <span class="grow"></span>
    <span class="cluster">
    <label class="auto printer-only gcode" title="How often the board is polled while its Machine is open; off, only when ⟳ Poll asks">poll
        <select id="interval"><option value="0">off</option><option value="1000">1 s</option><option value="2000" selected>2 s</option><option value="5000">5 s</option><option value="10000">10 s</option></select>
    </label>
    <button type="button" id="poll" class="printer-only gcode">⟳ Poll</button>
    </span>
    <span class="cluster">
    <button type="button" id="reconnect" data-can="reconnect">⇄ Reconnect</button>
    <button type="button" id="identify" data-can="identify">Identify</button>
    <button type="button" id="reset" data-can="reset" class="danger printer-only gcode" title="Reboot the board with a DTR pulse — never during a job">⏻ Reboot</button>
    <button type="button" id="release" data-can="release">Release</button>
    <button type="button" id="listen" data-can="listen" class="devkit-only" title="Open the port and stream what the board says into the log. Opening the port may reset the board">Listen</button>
    <button type="button" id="probe" data-can="probe" class="devkit-only" title="Ask esptool for the chip, its MAC and its flash size (an Espressif board; this resets it)">Probe</button>
    </span>
    <span class="cluster">
    <label class="ctl printer-only gcode" id="ctl-label">
        <input type="checkbox" id="ctl" title="Arm the control latch, or let it go"> ⚙ Control <span class="ttl" id="ctl-ttl"></span>
    </label>
    <button type="button" id="estop" data-can="estop" class="printer-only gcode">⏹ E-STOP</button>
    </span>
</div>`;

const CARDS = `
<div class="cards" id="cards">
    <div class="card printer-only gcode"><div class="k">State</div><div class="v" id="c-state">—</div><div class="s" id="c-state-s"></div><div class="s old" id="c-age" hidden></div></div>
    <div class="card wide needs" id="c-needs-card" hidden><div class="k">Needs you</div><div class="needs-list" id="c-needs"></div></div>
    <div class="card wide"><div class="k">Board · link</div><div class="kv" id="c-board">—</div></div>
    <div class="card wide missing" id="c-missing-card" hidden><div class="k">Its board, not connected</div><div id="c-missing"></div>
        <div class="missing-do" id="missing-said"></div></div>
</div>
<div data-section="status">
<div class="cards">
    <div class="card printer-only"><div class="k">Hotend</div><div class="v" id="c-hot">—</div><div class="s" id="c-hot-s"></div><div class="bar hotend"><i id="b-hot" style="width:0"></i></div></div>
    <div class="card printer-only"><div class="k">Bed</div><div class="v" id="c-bed">—</div><div class="s" id="c-bed-s"></div><div class="bar bed"><i id="b-bed" style="width:0"></i></div></div>
    <div class="card printer-only gcode"><div class="k">Position</div><div class="v" id="c-pos">—</div><div class="s" id="c-pos-s"></div></div>
    <div class="card printer-only"><div class="k">SD print</div><div class="v" id="c-sd">—</div><div class="s" id="c-sd-s"></div><div class="bar sd"><i id="b-sd" style="width:0"></i></div></div>
    <div class="card printer-only"><div class="k">Endstops · filament</div><div class="chips" id="c-stops"><span class="empty">—</span></div></div>
    <div class="card router-only"><div class="k">Spindle</div><div class="v" id="c-spindle">—</div><div class="s" id="c-spindle-s"></div></div>
    <div class="card router-only"><div class="k">Feed · overrides</div><div class="v" id="c-feed">—</div><div class="s" id="c-feed-s"></div></div>
    <div class="card router-only"><div class="k">Pins on · limits, probe, door</div><div class="chips" id="c-pins"><span class="empty">—</span></div></div>
</div>
</div>
<div data-section="sketch">
<div class="cards">
    <div class="card wide devkit-only" id="sketch-card"><div class="k">Sketch · should run, and observed</div><div class="kv" id="c-sketch">—</div></div>
</div>
</div>
<div data-section="flashing">
<div class="cards">
    <div class="card wide devkit-only" id="flash-card">
        <div class="k">Flashing</div>
        <div class="bench-ui" id="flash-form"></div>
        <div class="bench-ui" id="flash-task"></div>
    </div>
</div>
</div>
<div data-section="level">
<div class="cards">
    <div class="card wide printer-only gcode" id="level-card">
        <div class="k"><span id="level-title">Bed level</span> <span class="s" id="level-note"></span></div>
        <div class="row">
            <button type="button" id="level-probe" data-can="level.probe" class="warm" title="G28, G29, then read the mesh, the probe offset and the temperatures; saved as a record. Moves the machine: control must be armed">▤ Probe bed</button>
            <button type="button" id="level-read" data-can="level.read" class="printer-only" title="Read the stored mesh (M420 V), the probe offset and the temperatures without moving; saved as a record">Read mesh</button>
            <span class="job" id="level-job"></span>
            <span class="grow"></span>
            <button type="button" data-corner="FL" data-can="control" class="printer-only" title="Move the nozzle to the front-left corner at paper height, for a tramming check: control must be armed">◣ FL</button>
            <button type="button" data-corner="FR" data-can="control" class="printer-only" title="Move the nozzle to the front-right corner at paper height: control must be armed">◢ FR</button>
            <button type="button" data-corner="BL" data-can="control" class="printer-only" title="Move the nozzle to the back-left corner at paper height: control must be armed">◤ BL</button>
            <button type="button" data-corner="BR" data-can="control" class="printer-only" title="Move the nozzle to the back-right corner at paper height: control must be armed">◥ BR</button>
        </div>
        <div id="mesh"></div>
        <div class="stats" id="level-stats"><span class="empty">no reading yet</span></div>
        <div id="level-history"></div>
    </div>
</div>
</div>
<div data-section="print">
<div class="cards">
    <div class="card wide printer-only gcode" id="print-card">
        <div class="k"><span id="print-title"></span></div>
        <div class="s print-next" id="print-next"></div>
        <div class="row"><label for="print-part">makes</label>
            <select id="print-part"><option value="">— no part named —</option></select>
            <button type="button" id="print-slice">Slice</button>
            <span class="s" id="print-where"></span>
        </div>
        <div class="row" id="print-filament-row" hidden><label for="print-filament">filament</label>
            <select id="print-filament" title="The filament loaded on this printer: its next slices are made with it, and take its own tuning"></select>
            <span class="s" id="print-filament-said"></span>
        </div>
        <div class="row" id="print-level-row" hidden><label for="print-level">levelling</label>
            <select id="print-level" title="How the next slice levels the bed at the start of its print: as the part declares, else as this printer's profile says; a probe once the bed is hot (G29, the mesh on for that print); or homing alone">
                ${options(LEVELLING)}
            </select>
            <span class="s" id="print-level-said"></span>
        </div>
        <div class="row" id="print-adhesion-row" hidden><label for="print-adhesion">adhesion</label>
            <select id="print-adhesion" title="How the next slice's first layer holds: as the part declares, else as this printer's profile says; a brim round each piece; a raft under each; or neither">
                ${options(ADHESION)}
            </select>
        </div>
        <div class="row" id="print-offset-row" hidden><label for="print-offset">first layer</label>
            <select id="print-offset" title="This printer's first-layer offset: the nozzle lower or higher than its probe puts it, kept for the printer, and every slice made for it after is made with it (OrcaSlicer's z_offset). A one-layer square (first_layer_square) says which way: lines round and standing apart, or not holding, lower; lines thin, see-through or scraped, higher"></select>
            <span class="s" id="print-offset-said"></span>
        </div>
        <div class="row"><label for="print-pick">file</label>
            <select id="print-pick" title="The files kept on the host, newest first"><option value="">— no files kept —</option></select>
            <button type="button" id="print-delete" title="Forget the chosen file">✕</button>
            <input type="file" id="print-file" accept=".gcode,.gco,.g,.txt,text/plain">
        </div>
        <div class="row" id="print-preview-row"><label for="print-preview">preview</label>
            <input type="range" id="print-preview" min="0" max="1" step="1" value="0" title="The chosen file's path, drawn in the world on this machine: off at the left, then through each layer or pass, all of it at the right. Nothing is sent. Its ring's Preview turns it on and off">
            <span class="s" id="print-preview-said"></span>
        </div>
        <div class="row" id="print-plan-row"><label for="print-plan">plan</label>
            <button type="button" id="print-plan" title="Keep what it makes and the file chosen as this machine's plan: chosen again whenever its Machine opens, with its board connected or not. Nothing is sent">Keep as plan</button>
            <span class="s" id="print-plan-said"></span>
        </div>
        <div class="row" id="print-verbs">
            <button type="button" id="print-start" data-can="print.start" class="warm"></button>
            <button type="button" id="print-pause" data-can="print.pause">⏸ Pause</button>
            <button type="button" id="print-resume" data-can="print.resume" title="Feed lines again (control must be armed)">▶ Resume</button>
            <button type="button" id="print-cancel" data-can="print.cancel">⏏ Abort</button>
        </div>
        <div class="row" id="print-progress-row"><span id="print-progress"></span><span class="grow"></span><span class="job" id="print-job"></span></div>
        <div class="bar print" id="print-bar"><i id="b-print" style="width:0"></i></div>
        <div id="print-slice-box" class="slice-box" hidden>
            <div class="bench-ui" id="print-slice-task"></div>
            <div id="print-slice-said" class="slice-said"></div>
        </div>
        <div id="print-history"></div>
    </div>
</div>
</div>
<div data-section="temperature">
<div class="chart printer-only">
    <div class="head"><span class="title">Temperature</span><span id="chart-span">no polls yet</span>
        <span class="legend"><span class="hotend">hotend</span><span class="bed">bed</span><span style="color:var(--ink-3)">dashed = target</span></span></div>
    <div class="wrap"><svg id="chart" viewBox="0 0 600 150" preserveAspectRatio="none"></svg><div class="tip" id="tip"></div></div>
</div>
</div>`;

// The board's one log: a printer's comms log with the one box that asks it for
// a report, or a devkit's serial output.
const LOG = `
<div class="log-head">
    <span class="title">Log</span>
    <form id="qform" class="printer-only gcode" autocomplete="off">
        <input id="q" list="qcodes" aria-label="Report-only G-code to send" spellcheck="false">
        <datalist id="qcodes"></datalist>
        <button type="submit">send</button>
    </form>
    <label class="printer-only gcode"><input type="checkbox" id="show-polls"> poll traffic</label>
    <button type="button" id="clear">clear</button>
    <button type="button" id="download" title="Download the log as text" aria-label="Download the log">⤓</button>
</div>
<pre id="log"><span class="empty">pick a port to see its log</span></pre>`;

const CONTROL = `
<div id="control" class="machine-pad" hidden>
    <div class="head">🔓 <span id="ctl-who">Control</span> armed: it can <span id="ctl-can">heat and move</span> <span class="ttl" id="ctl-ttl2"></span><span class="grow"></span>
        <span class="sent" id="ctl-sent"></span>
        <span class="unknown" id="ctl-unknown" hidden>not confirmed: the server did not answer</span>
        <button type="button" id="pad-estop" data-can="estop">⏹ E-STOP</button>
        <button type="button" id="ctl-pop"></button>
        <button type="button" id="ctl-disarm" title="Let go of the control latch: nothing on this page can then heat, turn or move the machine">🔒 Disarm</button>
    </div>
    <div class="body">
        <div class="grp deck-knobs-grp" hidden>
            <div class="k">Stream Deck +</div>
            <div class="row"><span id="deck-knobs-on"></span><button type="button" id="deck-here" data-can="here" title="The deck's knobs move this machine, as its key on the deck chooses it">🎛 Knobs here</button></div>
        </div>
        <div class="grp printer-only">
            <div class="k">Heaters</div>
            <div class="row">hotend <input type="number" id="h-hot" min="0" max="300" step="5" value="200"> °C
                <button type="button" class="warm" data-cmd="M104 S{h-hot}" data-label="Set hotend" title="Heat the hotend to the temperature in the box (M104)">Set</button>
                <button type="button" data-cmd="M104 S0" data-label="Hotend off" title="Hotend heater off (M104 S0)">Off</button></div>
            <div class="row">bed <input type="number" id="h-bed" min="0" max="130" step="5" value="60"> °C
                <button type="button" class="warm" data-cmd="M140 S{h-bed}" data-label="Set bed" title="Heat the bed to the temperature in the box (M140)">Set</button>
                <button type="button" data-cmd="M140 S0" data-label="Bed off" title="Bed heater off (M140 S0)">Off</button></div>
            <div class="row">fan <input type="range" id="h-fan" min="0" max="255" step="5" value="255"> <span id="h-fan-v">255</span>
                <button type="button" data-cmd="M106 S{h-fan}" data-label="Set fan" title="Run the part-cooling fan at the speed on the slider (M106)">Set</button>
                <button type="button" data-cmd="M107" data-label="Fan off" title="Fan off (M107)">Off</button></div>
        </div>
        <div class="grp printer-only gcode">
            <div class="k">Motion</div>
            <div class="row" style="align-items:flex-start">
                <div class="jog">
                    <span></span><button type="button" data-jog="Y+" title="Jog Y+ one step (the step below)">▲</button><span></span>
                    <button type="button" data-jog="X-" title="Jog X− one step (the step below)">◀</button><button type="button" data-cmd="HOME" title="Home all (a printer's G28, a router's $H)">⌂</button><button type="button" data-jog="X+" title="Jog X+ one step (the step below)">▶</button>
                    <span></span><button type="button" data-jog="Y-" title="Jog Y− one step (the step below)">▼</button><span></span>
                </div>
                <div class="jogz"><button type="button" data-jog="Z+" title="Jog Z+ one step (the step below)">Z▲</button><button type="button" data-jog="Z-" title="Jog Z− one step (the step below)">Z▼</button></div>
            </div>
            <div class="row steps">step <button type="button" data-step="0.1" title="Each jog moves 0.1 mm">0.1</button><button type="button" data-step="1" title="Each jog moves 1 mm">1</button><button type="button" data-step="10" title="Each jog moves 10 mm" class="on">10</button><button type="button" data-step="50" title="Each jog moves 50 mm">50</button> mm
                · F <input type="number" id="h-feed" min="10" max="12000" step="100" value="3000" title="How fast to jog, in mm/min"></div>
            <div class="row"><button type="button" data-cmd="HOME-X">Home X</button><button type="button" data-cmd="HOME-Y">Home Y</button><button type="button" data-cmd="HOME-Z">Home Z</button></div>
            <div class="homing router-only" id="ctl-homing"></div>
            <div class="row printer-only"><button type="button" data-cmd="G28 X Y" title="Home X and Y alone (G28 X Y): Z stays where it stands. Moves the machine">Home XY</button><button type="button" data-cmd="M84" title="Release the stepper motors (M84): the axes turn by hand, and the printer forgets where it stands">Motors off</button><button type="button" data-cmd="M410" title="Stop the moves queued at once (M410), without halting the board">Quickstop</button></div>
            <div class="row router-only"><button type="button" data-cmd="$X" title="Unlock after an alarm ($X): the controller moves again, where it believes it is">Unlock</button><button type="button" data-cmd="G53 G0 Z0" title="The tool to the top of its travel, in machine coordinates">Top of Z</button><button type="button" data-cmd="G0 X0 Y0" title="The tool over the work zero, at its height">Go to zero</button><button type="button" data-cmd="JOG-CANCEL" title="Stop a jog in flight">Stop jog</button></div>
        </div>
        <div class="grp printer-only">
            <div class="k">SD print</div>
            <div class="row"><button type="button" data-cmd="M24" title="Carry on the print on the SD card where it was paused, or start the one chosen on the printer (M24)">▶ Resume</button><button type="button" data-cmd="M25" title="Pause the print on the SD card where it is (M25)">⏸ Pause</button><button type="button" data-cmd="M524" data-twice="abort" title="Abandon the print on the card: pressed twice">⏏ Abort</button></div>
        </div>
        <div class="grp printer-only">
            <div class="k">Leveling</div>
            <div class="row"><button type="button" data-cmd="M420 S1" title="Correct Z by the stored bed mesh (M420 S1)">Mesh on</button><button type="button" data-cmd="M420 S0" title="Stop correcting Z by the bed mesh (M420 S0)">Mesh off</button><button type="button" data-cmd="M108" title="Break out of a wait for heating, so the printer goes on (M108)">Break wait</button></div>
        </div>
        <div class="grp router-only">
            <div class="k">Spindle</div>
            <div class="row">rpm <input type="number" id="r-rpm" min="0" max="24000" step="1000" value="12000">
                <button type="button" class="warm" data-cmd="M3 S{r-rpm}" data-label="Spindle on" title="Spindle on, clockwise, at this speed (M3 S); the trim router's own dial sets what the speed means">On</button>
                <button type="button" data-cmd="M5" data-label="Spindle off" title="Spindle off (M5)">Off</button></div>
        </div>
        <div class="grp router-only">
            <div class="k">Zero and probe</div>
            <div class="row"><button type="button" data-cmd="G10 L20 P1 X0 Y0 Z0" title="The work zero (G54) is where the tool is now, in X, Y and Z">XYZ zero here</button><button type="button" data-cmd="G10 L20 P1 Z0" title="The work Z zero is where the tool is now">Z zero here</button>
                · probe down <input type="number" id="r-probe" min="1" max="80" step="1" value="25"> mm
                <button type="button" data-cmd="G38.2 Z-{r-probe} F100" title="Probe down this far at 100 mm/min until the plate is touched (G38.2); the touch is in the log, and $# says where">Probe Z</button></div>
            <div class="row plate">plate <input type="number" id="r-plate" min="0.01" max="50" step="0.01" value="19" title="The touch plate's thickness as you measured it with calipers, in mm, kept for this machine's board as it is changed: the maker's nominal is 19, and its manual's own example measures 19.08"> mm
                <button type="button" data-cmd="PROBE-PLATE Z{r-plate} D{r-probe} F100" title="The bit comes down at 100 mm/min, the probe depth at most, until it touches the plate; the touch is called Z = the plate's thickness, so Z 0 is the stock's top under it; the bit lifts 5 mm. Written to the work zero (G54), where Z zero here writes it. A probe that touches nothing sets nothing. Moves the machine: control must be armed">Probe Z to plate</button>
                <span class="s" id="r-plate-s"></span></div>
            <details class="how plate-how"><summary>How to zero Z with the touch plate</summary><ol>
                <li>Measure the plate's thickness with calipers and put it in <b>plate</b>: it is kept for this machine's board. The maker's nominal is 19 mm; a plate measures a little off it.</li>
                <li>Jog X and Y to where the work's zero is, and <b>XYZ zero here</b> or zero X and Y as the job needs.</li>
                <li>Stand the plate on the stock under the bit and clip its lead to the bit. Touch the clip to the plate by hand: <b>Pins on</b> shows <i>probe</i>. If it does not, do not probe: the bit would not stop.</li>
                <li>Jog the bit to within the probe depth above the plate, spindle off.</li>
                <li><b>Probe Z to plate</b>: the bit comes down until it touches, that point is called Z = the plate's thickness, and the bit lifts 5 mm. Z 0 is now the stock's top.</li>
                <li>Take the clip off the bit and the plate off the stock before anything turns.</li>
            </ol><div class="s">From the maker's manual, the Z probe (page 27), as parts/anolex_4060_evo_ultra_2/manual.json keeps it. The manual's sender sets the touch with G92, which a reset forgets; here it is written to the work zero.</div></details>
        </div>
        <div class="grp router-only">
            <div class="k">Cut</div>
            <div class="row"><button type="button" data-cmd="RESUME" title="Cycle start (~): a held controller moves again, and a paused cut from here streams again">▶ Resume</button><button type="button" data-cmd="HOLD" title="Feed hold (!): the controller decelerates and stops where it is; a cut from here stops feeding">⏸ Hold</button><button type="button" data-cmd="RESET" data-twice="abort" title="Abandon the cut: a hold, then the soft reset, which empties the queue and turns the spindle off; pressed twice">⏏ Abort</button></div>
        </div>
    </div>
</div>`;

// Verb -> the one G-code line its button sends. Values are read at the
// moment of choosing, from the same boxes the buttons read. A printer's, then a
// router's (GRBL's dialect: apothecary/firmware/grbl.py).
const LINES = {
    "control:hotend-on": (m) => m.fillTemplate("M104 S{h-hot}"),
    "control:hotend-off": () => "M104 S0",
    "control:bed-on": (m) => m.fillTemplate("M140 S{h-bed}"),
    "control:bed-off": () => "M140 S0",
    "control:fan-on": (m) => m.fillTemplate("M106 S{h-fan}"),
    "control:fan-off": () => "M107",
    "control:home": () => "G28",
    "control:home-x": () => "G28 X",
    "control:home-y": () => "G28 Y",
    "control:home-xy": () => "G28 X Y",
    "control:home-z": () => "G28 Z",
    "control:sd-resume": () => "M24",
    "control:sd-pause": () => "M25",
    "control:sd-abort": () => "M524",
    "control:motors-off": () => "M84",
    "control:break-wait": () => "M108",
    "control:mesh-on": () => "M420 S1",
    "control:mesh-off": () => "M420 S0",
    "control:quickstop": () => "M410",
};
const ROUTER_LINES = {
    "control:home": () => "$H",
    "control:home-x": () => "$HX",
    "control:home-y": () => "$HY",
    "control:home-z": () => "$HZ",
    "control:unlock": () => "$X",
    "control:spindle-on": (m) => m.fillTemplate("M3 S{r-rpm}"),
    "control:spindle-off": () => "M5",
    "control:zero-xyz": () => "G10 L20 P1 X0 Y0 Z0",
    "control:zero-z": () => "G10 L20 P1 Z0",
    "control:go-zero": () => "G0 X0 Y0",
    "control:top-z": () => "G53 G0 Z0",
    "control:probe-z": (m) => m.fillTemplate("G38.2 Z-{r-probe} F100"),
    "control:probe-plate": (m) => m.fillTemplate("PROBE-PLATE Z{r-plate} D{r-probe} F100"),
    "control:jog-cancel": () => "JOG-CANCEL",
    "control:job-resume": () => "RESUME",
    "control:job-hold": () => "HOLD",
    "control:job-abort": () => "RESET",
};
// What cannot be undone is pressed twice (twice.js), its button saying "Again to ..."; the
// ring asks twice on its own wedge, so what it carries here is confirmed already.
// The same three verbs, carried to the job from here when one is running: a
// printer's SD verbs, a router's cut verbs.
const HOST_VERBS = {
    "control:sd-resume": "resume", "control:sd-pause": "pause", "control:sd-abort": "cancel",
    "control:job-resume": "resume", "control:job-hold": "pause", "control:job-abort": "cancel",
};
// The buttons the machine has, each by the verb it is.
const BY_CMD = {
    "M104 S{h-hot}": "control:hotend-on", "M104 S0": "control:hotend-off",
    "M140 S{h-bed}": "control:bed-on", "M140 S0": "control:bed-off",
    "M106 S{h-fan}": "control:fan-on", "M107": "control:fan-off",
    "HOME": "control:home", "HOME-X": "control:home-x", "HOME-Y": "control:home-y", "HOME-Z": "control:home-z", "G28 X Y": "control:home-xy",
    "M24": "control:sd-resume", "M25": "control:sd-pause", "M524": "control:sd-abort", "M84": "control:motors-off",
    "M410": "control:quickstop", "M108": "control:break-wait", "M420 S1": "control:mesh-on", "M420 S0": "control:mesh-off",
    "$X": "control:unlock", "M3 S{r-rpm}": "control:spindle-on", "M5": "control:spindle-off",
    "G10 L20 P1 X0 Y0 Z0": "control:zero-xyz", "G10 L20 P1 Z0": "control:zero-z", "G0 X0 Y0": "control:go-zero", "G53 G0 Z0": "control:top-z",
    "G38.2 Z-{r-probe} F100": "control:probe-z", "PROBE-PLATE Z{r-plate} D{r-probe} F100": "control:probe-plate", "JOG-CANCEL": "control:jog-cancel", "RESUME": "control:job-resume", "HOLD": "control:job-hold", "RESET": "control:job-abort",
};
// The lines that interrupt what the board is doing: the server writes each ahead of
// the exchange in flight, so the page sends each at once, never behind another line,
// and its button is never greyed.
const INTERRUPTS = new Set(["M410", "M108", "JOG-CANCEL", "HOLD", "RESUME"]);
// Each verb's pad line, the other way round: a ring verb is held to the latch as its
// button is, by the command can.js names that line by.
const CMD_OF = Object.fromEntries(Object.entries(BY_CMD).map(([cmd, verb]) => [verb, cmd]));
// A status older than this is said to be, with its age; a board polled less often
// than that is given two of its intervals.
const OLD_MS = 5000;
// The words of each kind are machine_words.js's (KINDS): applyKind writes them into
// the markup, which carries none of its own.


export function mountMachine(root, { base = "", port = "", host = "world", boards = null, kind = null, inPrinter = false, pin = null, name = null, machineAt = null, say = null, padWindow = null, variantFor = null, sections = {}, onVerb = null, onKind = null, afterPrint = null, afterHello = null, onFound = null, openDrawer = null } = {}) {
    const BASE = base;
    const model = boards || mountBoards({ base });
    root.classList.add("machine", `host-${host}`);
    root.classList.toggle("in-printer", !!inPrinter);
    root.innerHTML = HEAD + `<div class="machine-main"><section class="left">${CARDS}</section><div data-section="log"><section class="right">${LOG}</section></div></div>` + CONTROL;
    // The control pad is the Machine's wherever it stands: popped out, it is the page's child.
    const pad = root.querySelector("#control");
    // Each section's block moves to its window (the Machine's entry in
    // apothecary/systems.py), which takes the Machine's classes so the kind's own
    // controls show there as here; a section without a window stays in the Machine.
    const windows = [];
    for (const block of [...root.querySelectorAll("[data-section]")]) {
        const win = sections[block.dataset.section];
        if (!win) continue;
        win.classList.add("machine", `host-${host}`, "machine-section");
        win.classList.toggle("in-printer", !!inPrinter);
        win.replaceChildren(...block.childNodes);
        block.remove();
        windows.push(win);
    }
    const everywhere = [root, pad, ...windows];
    const $ = (id) => (id === "control" ? pad
        : everywhere.map((el) => el.querySelector(`#${CSS.escape(id)}`)).find(Boolean) ?? null);
    const who = {};  // this Machine, as the model's watcher of its board
    const b = () => model.board(state.port);
    // What the Machine keeps of its own: the port, its kind, the chart's history.
    // The board's status, link, poll timer and log are the model's, read through.
    const state = {
        port, kind: null, history: [], codesLoaded: false, listening: false,
        get status() { return state.port ? b().status : null; },
        get info() { return state.port ? b().info : null; },
        get timer() { return state.port ? b().timer : null; },
        get polling() { return state.port ? !!b().polling : false; },  // a poll asked and not yet answered
        get entries() { return state.port ? b().log : []; },
    };
    // Planning: the Machine of a machine not connected (machineAt, its site
    // and node, with no port). What makes it, its slice or toolpath, the files and the
    // path drawn ask the board nothing; ▶ and every control are its board's.
    const planning = () => !state.port && !!machineAt;
    const onWindow = [];  // [event, handler] pairs the module put on the window, taken off by destroy()
    const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));

    // --- api ---------------------------------------------------------------------------
    const api = (path, opts) => model.api(path, opts);
    const post = (path, body) => model.post(path, body);

    // --- refusals: in the log, and in the host's status bar as errors ------------------------
    // A step that ends here is told in the status bar too, naming the step after it:
    // a print started names where it is followed. A ring verb carried here hands
    // what it told back to the ring (carry's `said`), which says it after its label.
    let refusals = 0, lastRefusal = null, told = 0, lastTold = null, refusalLetGo = null, errorShown = false;
    function logLine(kind, text) { if (state.port) model.note(state.port, text, { kind }); }
    function refuse(text) {
        refusals++; lastRefusal = text; errorShown = true;
        logLine("sys", text);
        if (say) say(sentence(text), "error");  // the log keeps the line as it was said
    }
    // The red the server keeps for the last refused line (`refused` on a poll) stays through
    // unrelated acts until a line goes; this page lets go of it as soon as an act of this
    // machine succeeds, and shows only a refusal newer than the one it let go of.
    function forgetRefusal(said = null) {
        const st = state.status;
        if (st && st.refused) { refusalLetGo = st.refused.at || st.refused.command; renderNeeds(st); }
        const sent = $("ctl-sent"); if (sent) sent.classList.remove("bad");
        // A red line this machine's own refusal left in the status bar goes with it.
        if (errorShown && said) tell(said);
    }
    function tell(text) {
        told++; lastTold = text; errorShown = false;
        if (say) say(text, "success");
    }

    // --- the board: which, and what kind -------------------------------------------------
    function kindOf() {
        if (kind) return kind;
        const d = state.port ? b().device : null;
        if (!d || !d.printer) return d ? "devkit" : "printer";
        return kindOfBoard(d);
    }
    // A G-code machine: a printer or a router, polled over its held link.
    const isGcode = () => state.kind === "printer" || state.kind === "router";
    const LINES_OF = () => (state.kind === "router" ? ROUTER_LINES : LINES);
    const words = () => KINDS[state.kind] || KINDS.printer;
    const jobKind = () => words().job;
    // The kind's controls shown, the board watched as that kind; answers whether it changed.
    function applyKind() {
        const k = kindOf(), changed = k !== state.kind;
        state.kind = k;
        for (const el of [root, pad, ...windows]) {
            el.classList.toggle("kind-printer", k === "printer");
            el.classList.toggle("kind-router", k === "router");
            el.classList.toggle("kind-devkit", k === "devkit");
        }
        if (changed && onKind) onKind(k);
        const w = words();
        $("identify").textContent = isGcode() ? w.identify : "Identify";
        setTip($("identify"), isGcode() ? `Ask ${w.identify} again (no reset)` : "Listen a few seconds for the sketch's hello banner; none heard, ask M115 whether it is a G-code printer (no reset)");
        setTip($("reconnect"), isGcode() ? "Release and reopen the serial link (no reset); the remedy for a wedged port" : "Close the serial stream and open it again, while listening");
        setTip($("release"), isGcode() ? "Drop the held link so another program can open the port" : "Stop listening, so another program (an upload) can open the port");
        if (isGcode()) {
            $("poll").title = w.poll; $("q").placeholder = w.queries; setTip($("estop"), w.estop); setTip($("pad-estop"), w.estop); $("ctl-label").title = w.arm;
            $("ctl-can").textContent = w.can;
            $("print-title").textContent = w.title;
            $("print-start").textContent = w.start; setTip($("print-start"), w.startTitle);
            $("print-pause").textContent = `⏸ ${w.pauseWord}`;
            setTip($("print-pause"), w.pause); setTip($("print-cancel"), w.cancel);
            $("ctl").title = w.arm;
            $("print-slice").textContent = w.prepare;
            const feed = $("h-feed");  // the jog feed's bound is the machine's
            feed.max = String(w.feedMax);
            if (changed || Number(feed.value) > w.feedMax) feed.value = String(w.feedDefault);
            $("print-file").accept = w.files; $("print-file").title = w.fileTitle;
            $("print-part").title = w.partTitle;
            for (const b of pad.querySelectorAll('button[data-cmd^="HOME-"]')) setTip(b, w.homeAxis(b.dataset.cmd.slice(-1)));
            $("level-title").textContent = w.level.card; $("level-probe").textContent = w.level.button; setTip($("level-probe"), w.level.buttonTitle);
        }
        if (changed) state.codesLoaded = false;
        if (changed && state.port) {
            watchNow();
            if (k === "printer") { loadCodes(); loadLevel(); loadPrintJobs(); loadChoicesAndFiles(); loadSlicer(); watchPrint(); }
            else if (k === "router") { loadCodes(); loadWhere(); loadLevel(); loadPrintJobs(); loadChoicesAndFiles(); watchPrint(); }
            else if (!inPrinter) mountFlashing();
        } else if (changed && planning()) {
            loadChoicesAndFiles();
            if (k === "printer") loadSlicer();
        }
        return changed;
    }
    // The router's working volume, from its frame (GET /firmware/printers/where): its
    // controller's travel once it has said it, else the site's figure.
    async function loadWhere() {
        if (!state.port) return;
        try {
            const w = await api(`/firmware/printers/where?port=${encodeURIComponent(state.port)}`);
            if (w && w.printer && w.printer.frame) { level.volume = w.printer.frame.volume; level.frame = w.printer.frame; }
        } catch (e) { /* not known yet: nothing is sized by it */ }
    }
    // A jog's position carries no dialect of its own: the kind's is used.
    const toolPosition = (st) => toolPositionOf({ ...(st || {}), dialect: words().dialect });
    // The one choice of how often to poll: off is 0, polled only when asked.
    const interval = () => Number($("interval").value) || 2000;
    const isLive = () => (state.kind === "devkit" ? state.listening : Number($("interval").value) > 0);
    function watchNow() {
        if (state.port) model.watch(state.port, who, { kind: state.kind, interval: interval(), live: isLive() });
    }
    // How often to poll, off among the choices (a devkit: listening or not):
    // the model's poller for this board, scheduled afresh from now.
    function schedule() {
        if (state.port) model.setWatch(state.port, who, { interval: interval(), live: isLive() });
    }

    async function loadCodes() {
        if (state.codesLoaded) return;
        try {
            const codes = await api(`/firmware/printers/queries?port=${encodeURIComponent(state.port)}`);
            $("qcodes").innerHTML = codes.map((q) => `<option value="${esc(q.command)}">${esc(q.reports)}</option>`).join("");
            state.codesLoaded = true;
        } catch (e) { /* suggestions are optional */ }
    }

    // --- status ------------------------------------------------------------------------
    const pinRow = () => `${pin.how === "sketch" ? "bound by its sketch to" : "pinned at"} <b>${esc(pin.site)} › ${esc(pin.path)}</b>`;
    // How old the status the cards are drawn from is, said once it is old: a poll
    // that failed leaves the last one drawn, and so does polling switched off.
    // Counted each second while a G-code board's Machine is open.
    function renderAge() {
        const st = isGcode() ? state.status : null;
        const age = st && st.polled_at ? Date.now() - new Date(st.polled_at).getTime() : 0;
        const old = age > Math.max(OLD_MS, isLive() ? 2 * interval() : 0);
        $("c-age").hidden = !old;
        $("c-age").textContent = old ? `status ${age < 60000 ? `${Math.round(age / 1000)} s` : span(age / 1000)} old` : "";
        for (const el of [root, ...windows]) el.classList.toggle("status-old", old);
    }
    const ageTimer = setInterval(renderAge, 1000);
    function renderStatus() {
        renderAge();
        if (state.kind === "devkit") { renderDevkit(); return; }
        if (state.kind === "router") { renderRouter(); return; }
        const bd = state.port ? b() : null;
        const st = bd && bd.status, d = bd && bd.device;
        const pr = d && d.printer;
        $("ident").innerHTML = identLine(bd, d, pr);
        renderNeeds(st);
        if (!st) { $("c-state").textContent = "—"; $("c-state-s").textContent = ""; renderBoard(); return; }
        const offline = st.state === "offline";
        $("dot").className = "dot " + (offline ? "bad" : "on");
        $("c-state").innerHTML = offline ? '<span class="bad">offline</span>' : (st.job && st.job.stage === "paused" ? '<span class="warn">paused</span>' : st.state === "printing" ? '<span class="ok">printing</span>' : (st.heating ? '<span class="warn">heating</span>' : "idle"));
        $("c-state-s").textContent = st.job ? (st.job.kind === words().job ? `${st.job.kind} from here: ${st.job.stage} ${(st.job.progress * 100).toFixed(0)}%` : `${st.job.kind}: ${st.job.stage}`) : (offline ? (st.raw[0] || "") : `polled ${clock(st.polled_at)}`);
        const hot = st.hotends[0];
        $("c-hot").textContent = heaterText(hot); $("c-hot-s").textContent = hot && hot.power != null ? `power ${hot.power}/127` : "";
        $("b-hot").style.width = hot && hot.target > 0 ? Math.min(100, hot.actual / hot.target * 100).toFixed(0) + "%" : "0";
        $("c-bed").textContent = heaterText(st.bed); $("c-bed-s").textContent = st.bed && st.bed.power != null ? `power ${st.bed.power}/127` : "";
        $("b-bed").style.width = st.bed && st.bed.target > 0 ? Math.min(100, st.bed.actual / st.bed.target * 100).toFixed(0) + "%" : "0";
        const p = st.position;
        $("c-pos").innerHTML = p ? xyzHtml(p) : "—";
        $("c-pos-s").textContent = p ? `E ${p.e.toFixed(1)}` : "";
        if (st.sd_printing) {
            const pct = st.sd_progress != null ? (st.sd_progress * 100).toFixed(1) + "%" : "…";
            $("c-sd").textContent = pct; $("b-sd").style.width = st.sd_progress != null ? (st.sd_progress * 100).toFixed(1) + "%" : "0";
            $("c-sd-s").textContent = st.print_time_s != null ? `elapsed ${span(st.print_time_s)}` : "";
        } else { $("c-sd").textContent = st.job ? "none" : "not printing"; $("c-sd-s").textContent = st.job ? `the ${st.job.kind} streams from here` : ""; $("b-sd").style.width = "0"; }
        const chips = Object.entries(st.endstops).map(([k, v]) => `<span class="chip ${v === "TRIGGERED" ? "hit" : ""}">${esc(k)} ${v === "TRIGGERED" ? "▮" : "▯"}</span>`);
        if (st.filament_present != null) chips.push(`<span class="chip ${st.filament_present ? "hit" : "bad"}">filament ${st.filament_present ? "present" : "OUT"}</span>`);
        $("c-stops").innerHTML = chips.join("") || '<span class="empty">—</span>';
        renderBoard();
    }

    // The head's line: what the board said it is, or how far from known it is.
    function identLine(bd, d, pr) {
        if (pr) return `<b>${esc(pr.firmware_name)}</b>${pr.machine_type ? " · " + esc(pr.machine_type) : ""}`;
        if (d) return `${esc(d.port)} — ${words().notIdentified}`;
        return state.port ? (bd.info ? "not detected" : "connecting…") : "—";
    }

    // What the machine's state asks of a person, read from the poll and not from the log:
    // what must be done before it moves again (a router in alarm), and the last control
    // line the port refused or its board objected to, until one goes.
    function renderNeeds(st) {
        const rows = [];
        const unlock = st && st.dialect === "grbl" && st.state === "alarm"
            ? ' <button type="button" class="needs-unlock" title="Unlock ($X): the controller moves again, where it believes it is. Moves nothing. Control must be armed">Unlock</button>' : "";
        // Unlock stands on the alarm's own line: a router not yet placed for a cut is not unlocked into one.
        for (const t of (st && st.todo) || []) rows.push(`<div class="need warn">${esc(t)}${/^In alarm/.test(t) ? unlock : ""}</div>`);
        const r = st && st.refused;
        if (r && (r.at || r.command) !== refusalLetGo) {
            const at = r.at ? clock(r.at) : "";
            // The button's label, as the person pressed it; the line is in its tip.
            const label = actLabels.get(String(r.command).toUpperCase()) || labelOfLine(r.command) || "A control line";
            rows.push(`<div class="need bad"><b title="${esc(r.command)}">${esc(label)}</b> did not go${at ? ` · ${esc(at)}` : ""}<div class="why">${esc(r.said)}</div></div>`);
        }
        $("c-needs").innerHTML = rows.join("");
        $("c-needs-card").hidden = !rows.length;
    }

    // The touch plate's thickness: kept by the server for this machine's board, the
    // maker's nominal until one has been measured.
    let plateFor = null;
    async function loadPlate() {
        if (!state.port || state.kind !== "router" || plateFor === state.port) return;
        try {
            const p = await api(`/firmware/printers/plate?port=${encodeURIComponent(state.port)}`);
            plateFor = state.port;
            $("r-plate").value = p.thickness_mm;
            $("r-plate-s").textContent = p.measured ? "as measured" : `the maker's nominal ${p.nominal_mm} mm: measure yours`;
        } catch (e) { /* asked again at the next poll */ }
    }
    async function keepPlate() {
        try {
            const p = await api("/firmware/printers/plate", { method: "PUT", body: JSON.stringify({ port: state.port, thickness_mm: Number($("r-plate").value) }) });
            $("r-plate").value = p.thickness_mm; $("r-plate-s").textContent = "as measured";
        } catch (e) { refuse(`plate: ${e.message}`); }
    }

    $("r-plate").addEventListener("change", () => keepPlate());
    $("c-needs").addEventListener("click", (ev) => {
        if (ev.target.closest(".needs-unlock")) sendControl("$X");
    });

    // Each axis's home, beside the buttons that ask for it: which way it will seek, and
    // the two things the port must have shown first. A home not proved is refused by the
    // server, and its button is greyed with that reason (renderCan); here is what to do.
    function renderHoming(st) {
        const box = $("ctl-homing"), pad = $("control");
        const homing = (st && st.homing) || [];
        const mark = (ok) => (ok ? '<span class="ok">✓</span>' : '<span class="bad">✗</span>');
        box.innerHTML = homing.map((h) => {
            const far = h.search != null ? `up to ${h.search.toFixed(0)} mm` : "";
            const fast = h.seek != null ? `at ${h.seek.toFixed(0)} mm/min` : "";
            const need = [];
            if (!h.jogged) need.push(`jog ${h.axis} 1 mm toward ${h.way}${h.axis} and watch which way it goes`);
            if (!h.switch_seen) need.push(`press ${h.axis}'s limit switch by hand for two seconds and let go`);
            return `<div class="home-axis${h.ready ? "" : " unproved"}" data-axis="${esc(h.axis)}" title="A home of ${esc(h.axis)} seeks ${esc(h.way)}${esc(h.axis)} ${fast} ${far} until its switch closes: it is sent once the switch has been seen on and off, and the axis jogged that way">`
                + `<b>${esc(h.axis)}</b> seeks ${esc(h.way)}${esc(h.axis)} · switch ${mark(h.switch_seen)} · way ${mark(h.jogged)}`
                + (need.length ? `<div class="why">first: ${esc(need.join("; then "))}</div>` : "") + `</div>`;
        }).join("");
    }

    // A router: its controller's state and word, the tool in the work zero and in machine
    // coordinates, the spindle, the feed and the overrides, the input pins on.
    function renderRouter() {
        const bd = state.port ? b() : null;
        const st = bd && bd.status, d = bd && bd.device, pr = d && d.printer;
        $("ident").innerHTML = identLine(bd, d, pr);
        renderNeeds(st); renderHoming(st); loadPlate();
        if (!st) { $("c-state").textContent = "—"; $("c-state-s").textContent = ""; renderBoard(); return; }
        const offline = st.state === "offline";
        $("dot").className = "dot " + (offline ? "bad" : "on");
        const word = { offline: '<span class="bad">offline</span>', alarm: '<span class="bad">alarm</span>', hold: '<span class="warn">hold</span>', running: '<span class="ok">running</span>' }[st.state] || esc(st.state);
        $("c-state").innerHTML = word;
        const controller = `${st.machine_state || ""}${st.alarm != null ? ` · alarm ${st.alarm}${st.alarm_text ? `: ${st.alarm_text}` : ""}` : ""}`;
        $("c-state-s").textContent = st.job ? `${st.job.kind} from here: ${st.job.stage} ${(st.job.progress * 100).toFixed(0)}% · ${controller}` : (offline ? (st.raw[0] || "") : `${controller} · polled ${clock(st.polled_at)}`);
        const p = st.position, wp = st.work_position;
        $("c-pos").innerHTML = wp ? xyzHtml(wp) : (p ? xyzHtml(p) : "—");
        $("c-pos-s").innerHTML = p && wp ? `work zero · machine ${xyzHtml(p)}` : (p ? "machine coordinates" : "");
        const sp = st.spindle;
        $("c-spindle").textContent = sp ? (sp.on ? `${sp.rpm.toFixed(0)} rpm` : "off") : "—";
        $("c-spindle-s").textContent = sp && sp.target ? `S${sp.target.toFixed(0)} programmed` : "";
        $("c-feed").textContent = st.feed != null ? `F${st.feed.toFixed(0)}` : "—";
        $("c-feed-s").textContent = st.overrides ? `feed ${st.overrides.feed}% · rapid ${st.overrides.rapid}% · spindle ${st.overrides.spindle}%` : "";
        const names = { X: "X limit", Y: "Y limit", Z: "Z limit", P: "probe", D: "door", H: "hold", R: "reset", S: "start" };
        const chips = (st.pins || []).map((k) => `<span class="chip hit">${esc(names[k] || k)} ▮</span>`);
        $("c-pins").innerHTML = chips.join("") || '<span class="chip">none</span>';
        renderBoard();
    }

    function renderBoard() {
        if (state.kind === "devkit") { renderDevkit(); return; }
        const info = state.info; if (!info) { $("c-board").innerHTML = pin ? pinRow() : "—"; return; }
        const d = info.device ? info.device.device : null, pr = d && d.printer, link = info.link;
        const rows = [];
        if (d) rows.push(`<b>${esc(d.port)}</b> vid:pid ${esc(d.vid || "?")}:${esc(d.pid || "?")}${d.serial_number ? " · S/N " + esc(d.serial_number) : ""}`);
        if (pr) {
            rows.push(`firmware <b>${esc(pr.firmware_name)}</b>${pr.machine_type ? " · machine " + esc(pr.machine_type) : ""}${pr.machine === "router" ? ` · build ${esc(pr.protocol_version || "?")}` : ` · protocol ${esc(pr.protocol_version || "?")} · extruders ${pr.extruder_count}`}`);
            if (pr.uuid) rows.push(`uuid ${esc(pr.uuid)}`);
            const caps = Object.entries(pr.capabilities || {}).filter(([, v]) => v).map(([k]) => k);
            if (caps.length) rows.push(`caps ${esc(caps.join(", "))}`);
            if (pr.boot_lines && pr.boot_lines.length) rows.push(`boot ${esc(pr.boot_lines.slice(0, 3).join(" | "))}`);
        }
        if (pin) rows.push(pinRow());
        rows.push(link
            ? `link <b class="ok">held</b> @ ${link.baud} baud via ${esc(link.engine)} since ${clock(link.opened_at)} · engine ${esc(info.engine)}`
            : `link <b>not held</b> · engine ${esc(info.engine)} — the next poll opens it`);
        if (info.active_task) rows.push(`<span class="warn">task ${esc(info.active_task.title)} holds the toolchain — polls wait</span>`);
        $("c-board").innerHTML = rows.join("<br>");
    }

    // A devkit: the board, where it is pinned, whether it is listened to; what it
    // should run against what it was heard saying, and what drifted since.
    function renderDevkit() {
        if (state.kind !== "devkit" || !state.port) return;
        const bd = b(), d = bd.device;
        $("ident").innerHTML = d ? `<b>${esc(boardLabel(d))}</b>` : "not detected";
        $("dot").className = "dot " + (bd.live ? "on" : "");
        const rows = [];
        if (d) {
            rows.push(`<b>${esc(d.port)}</b> vid:pid ${esc(d.vid || "?")}:${esc(d.pid || "?")}${d.board_name ? " · " + esc(d.board_name) : ""}${d.serial_number ? " · S/N " + esc(d.serial_number) : ""}${d.found_by ? " · found by " + esc(d.found_by) : ""}`);
            if (d.chip) rows.push(`chip <b>${esc(d.chip)}</b> rev ${esc(d.revision || "?")} · MAC ${esc(d.mac || "?")} · flash ${esc(d.flash_size || "?")}`);
        } else rows.push(`<b>${esc(state.port)}</b> — not detected`);
        if (pin) rows.push(pinRow());
        rows.push(bd.live ? `serial <b class="ok">listening</b> @ 115200` : (state.listening ? "serial <b>not listening</b> — opening it" : "serial <b>not listening</b> — the port is closed; Listen opens it (that may reset the board)"));
        $("listen").dataset.busy = state.listening ? "1" : ""; refreshDisabled($("listen"));
        $("listen").textContent = state.listening ? "Listening" : "Listen";
        $("c-board").innerHTML = rows.join("<br>");
        const w = sketchWords(bd.expected, bd.observed);
        const lines = [];
        if (w.rec) lines.push(`should run <b>${esc(w.should)}</b> · ${esc(builtFor(w.rec))} · flashed <span class="when">${esc(stamp(w.rec.flashed_at))}</span>${w.rec.build_sha256 ? " · build " + esc(w.rec.build_sha256.slice(0, 10)) : ""}`);
        else lines.push('<span class="warn">nothing flashed from apothecary</span>');
        for (const t of w.drift) lines.push(`<span class="warn">! ${esc(t)}</span>`);
        lines.push(w.observed
            ? `observed <b class="${w.verdict === "match" ? "ok" : (w.verdict === "mismatch" ? "bad" : "")}">${esc(w.observed)}</b>${w.verdict === "match" ? " ✓ matches" : (w.verdict === "mismatch" ? " ✗ differs" : "")}`
            : '<span class="empty">observed: no hello heard yet — Identify listens for it</span>');
        $("c-sketch").innerHTML = lines.join("<br>");
    }
    // What a flash record says it was built for: an Arduino sketch's board, another
    // module's sketch its chip (the toolchain is in the sketch's id), raw images esptool.
    function builtFor(rec) {
        if (rec.fqbn) return rec.fqbn;
        if (rec.sketch) return rec.target || "its chip";
        return "esptool";
    }
    function renderAll() { renderStatus(); renderChart(); renderLog(); }

    // --- chart: temperatures over the last N polls, one °C axis ------------------------
    function renderChart() {
        const svg = $("chart"), H = state.history;
        $("chart-span").textContent = `last ${H.length} poll${H.length === 1 ? "" : "s"}`;
        if (H.length < 2) { svg.innerHTML = ""; return; }
        const W = 600, HT = 150, padL = 34, padR = 44, padT = 8, padB = 18;
        const vals = H.flatMap((h) => [h.hot, h.hotT, h.bed, h.bedT]).filter((v) => v != null);
        let lo = Math.min(...vals), hi = Math.max(...vals);
        if (hi - lo < 10) { hi = lo + 10; }
        lo = Math.floor(lo / 5) * 5; hi = Math.ceil(hi / 5) * 5;
        const x = (i) => padL + (i / (H.length - 1)) * (W - padL - padR);
        const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (HT - padT - padB);
        const path = (key) => H.map((h, i) => h[key] == null ? null : `${i && H[i - 1][key] != null ? "L" : "M"}${x(i).toFixed(1)},${y(h[key]).toFixed(1)}`).filter(Boolean).join(" ");
        const ticks = [lo, (lo + hi) / 2, hi];
        const grid = ticks.map((t) => `<line x1="${padL}" x2="${W - padR}" y1="${y(t).toFixed(1)}" y2="${y(t).toFixed(1)}" stroke="#2a302a" stroke-width="1"/><text x="${padL - 6}" y="${(y(t) + 3).toFixed(1)}" font-size="9" fill="#66746a" text-anchor="end">${t.toFixed(0)}°</text>`).join("");
        const last = H[H.length - 1];
        const endLabel = (v, cls) => v == null ? "" : `<text x="${W - padR + 6}" y="${(y(v) + 3).toFixed(1)}" font-size="9" fill="${cls === "hotend" ? "#e8b04a" : "#6fb3e8"}">${v.toFixed(0)}°</text>`;
        svg.innerHTML = grid
            + `<path d="${path("hotT")}" fill="none" stroke="#e8b04a" stroke-width="1" stroke-dasharray="3 3" opacity="0.7"/>`
            + `<path d="${path("bedT")}" fill="none" stroke="#6fb3e8" stroke-width="1" stroke-dasharray="3 3" opacity="0.7"/>`
            + `<path d="${path("hot")}" fill="none" stroke="#e8b04a" stroke-width="2" stroke-linejoin="round"/>`
            + `<path d="${path("bed")}" fill="none" stroke="#6fb3e8" stroke-width="2" stroke-linejoin="round"/>`
            + endLabel(last.hot, "hotend") + endLabel(last.bed, "bed")
            + `<line id="xh" x1="0" x2="0" y1="${padT}" y2="${HT - padB}" stroke="#66746a" stroke-width="1" style="display:none"/>`;
        svg.onmousemove = (ev) => {
            const rect = svg.getBoundingClientRect();
            const fx = (ev.clientX - rect.left) / rect.width * W;
            const i = Math.max(0, Math.min(H.length - 1, Math.round((fx - padL) / (W - padL - padR) * (H.length - 1))));
            const h = H[i], xh = $("xh");
            xh.setAttribute("x1", x(i)); xh.setAttribute("x2", x(i)); xh.style.display = "";
            const tip = $("tip");
            tip.style.display = "block";
            tip.innerHTML = `${clock(h.t)}<br>hotend ${heater(h.hot, h.hotT)}<br>bed ${heater(h.bed, h.bedT)}`;
            const px = (x(i) / W) * rect.width;
            tip.style.left = Math.min(rect.width - 150, px + 10) + "px"; tip.style.top = "8px";
        };
        svg.onmouseleave = () => { $("tip").style.display = "none"; const xh = $("xh"); if (xh) xh.style.display = "none"; };
    }

    // --- log: the board's, the model's ------------------------------------------------------
    // Routine polls are tagged origin "poll" on the server; a person's queries and
    // M115s are not, so hiding poll traffic keeps them. Each entry drawn is one
    // element of the log, so new entries are appended and the ones the model
    // dropped off the front go with their elements; the whole log is redrawn only
    // when the poll-traffic box changes, it is cleared, or the board changes. It follows
    // its end while it is scrolled to it; scrolled up, it stays where the reader is.
    const LOG_EMPTY = '<span class="empty">nothing logged yet — poll or send a query</span>';
    function logRow(e) {
        e.drawn = $("show-polls").checked || !((e.kind === "tx" || e.kind === "rx") && e.origin === "poll");
        if (!e.drawn) return "";
        const d = new Date(e.t);
        const t = isNaN(d) ? e.t.slice(11, 23) : clock(d) + "." + String(d.getMilliseconds()).padStart(3, "0");
        const cls = e.kind + (e.origin === "control" || e.origin === "print" || e.origin === "cut" ? " control" : "") + (/^\s*(ok\s+)?T:\s*-?\d/.test(e.text) ? " temp" : "")
            + (/^(Error:|!!|error:\d|ALARM:)/.test(e.text) ? " err" : "") + (/apothecary\s+\S+:\s*hello/.test(e.text) ? " banner" : (e.text.startsWith("[apothecary:") ? " marker" : ""));
        // A line the dialect has words for (a GRBL error or alarm number) wears them.
        const note = e.note ? ` <span class="note">— ${esc(e.note)}</span>` : "";
        return `<span><span class="t">${t}</span> <span class="${cls}">${e.kind === "tx" ? "&gt; " : ""}${esc(e.text)}</span>${note}\n</span>`;
    }
    function drawLog(draw) {
        const log = $("log");
        const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
        draw(log);
        if (!log.firstElementChild) log.innerHTML = LOG_EMPTY;
        if (atBottom) log.scrollTop = log.scrollHeight;
    }
    function renderLog() {
        drawLog((log) => { log.innerHTML = state.entries.map(logRow).join(""); });
    }
    function appendLog(entries, dropped) {
        drawLog((log) => {
            if (log.querySelector(":scope > .empty")) log.innerHTML = "";
            for (const e of dropped || []) if (e.drawn) log.firstElementChild?.remove();
            log.insertAdjacentHTML("beforeend", entries.map(logRow).join(""));
        });
    }

    // --- what the model says of the board -----------------------------------------------------
    function pushHistory(st) {
        if (st.state === "offline") return;
        const hot = st.hotends[0];
        state.history.push({ t: st.polled_at, hot: hot ? hot.actual : null, hotT: hot ? hot.target : null, bed: st.bed ? st.bed.actual : null, bedT: st.bed ? st.bed.target : null });
        if (state.history.length > MAX_HISTORY) state.history.shift();
    }
    function onBoard(ev) {
        const d = ev.detail;
        if (!root.isConnected) return;
        if (d.what === "scan") {
            if (state.port) { applyKind(); renderStatus(); }
            return;
        }
        if (!state.port || d.port !== state.port) return;
        switch (d.what) {
            case "status":
                if (!isGcode()) break;
                if (state.kind === "printer") { pushHistory(d.status); renderChart(); }
                renderStatus();
                if (d.status.position) emit("apothecary:position", { position: toolPosition(d.status), source: "poll", port: state.port });
                tellPreview();  // a work zero set since moves a router's path with it
                followJob(d.status);
                if (d.status.control && latchFresh(d.asked)) applyControlState(d.status.control);
                takeCan(d.status.can);
                break;
            case "info":
                if (d.info && latchFresh(d.asked)) applyControlState(d.info.control);
                // The newest poll's answer when the board has one (the model may hold a poll
                // made before this Machine opened), else the info's.
                takeCan((state.status && state.status.can) || (d.info && d.info.can));
                applyKind(); renderStatus();
                break;
            case "error":
                if (!isGcode()) break;
                $("dot").className = "dot bad"; $("c-state").innerHTML = '<span class="bad">error</span>'; $("c-state-s").textContent = d.error;
                // A poll refused while a task holds the port carries no answer; the info does.
                api(`/firmware/printers/info?port=${encodeURIComponent(state.port)}`).then((i) => takeCan(i.can)).catch(() => {});
                break;
            case "log":
                if (d.cleared) renderLog(); else appendLog(d.entries, d.dropped);
                break;
            case "device":
                applyKind(); renderStatus();
                break;
            case "control":
                // The latch as the model follows it (GET /firmware/printers/armed), whoever
                // armed it or let it go: the deck, another browser. The model's own
                // count of a second carries no `asked` and changes nothing here.
                if (d.asked && latchFresh(d.asked)) {
                    const until = d.board ? d.board.armedUntil : 0;
                    applyControlState({ armed: !!until, seconds_left: until ? Math.max(0, (until - Date.now()) / 1000) : 0 });
                }
                break;
            case "observed": case "live":
                renderDevkit();
                break;
        }
    }
    window.addEventListener("apothecary:board", onBoard);
    onWindow.push(["apothecary:board", onBoard]);

    // Planned, with a board pinned at the machine that no port holds: why it is not
    // found, read with no port opened (GET /sites/{site}/machines/{path}/missing), each
    // check a board gets through on its way in its order, and the first that is off
    // said as what to do. Asked again every few seconds while it shows; a board come up
    // on its port and not yet in the scan is scanned for once, and a board found opens
    // its own Machine (onFound).
    const MISSING_MS = 4000;
    const miss = { timer: null, asked: 0, scannedFor: null };
    const MARK = { ok: "✓", off: "✗", unread: "?", after: "·" };
    async function loadMissing({ again = false } = {}) {
        clearTimeout(miss.timer); miss.timer = null;
        if (!planning()) { $("c-missing-card").hidden = true; return; }
        const at = machineAt, asked = ++miss.asked;
        if (again) { $("missing-said").textContent = "scanning the ports…"; try { await model.rescan(); } catch (e) { /* the route says what is there */ } }
        let d = null;
        try { d = await api(`/sites/${encodeURIComponent(at.site)}/machines/${encodeURIComponent(at.path)}/missing`); } catch (e) { d = null; }
        if (asked !== miss.asked || !planning()) return;
        if (d && d.connected.length && !d.expected.length) {
            $("c-missing-card").hidden = true;
            const found = d.connected[0];
            if (say) say(`${at.path}'s board is found on ${found.port}: its Machine opens with it`, "success");
            // The page's own scan names it too before its Machine is opened on it.
            if (!again) { try { await model.rescan(); } catch (e) { /* onFound waits for it */ } }
            if (asked === miss.asked && planning() && onFound) onFound(at.path, found.port);
            return;
        }
        renderMissing(d, again);
        // On its port, open to this user, and not in the scan: scanned for once.
        const ready = d && d.expected.find((e) => e.checks.every((c) => c.id === "scan" || c.state === "ok"));
        if (ready && !again && miss.scannedFor !== ready.identity) { miss.scannedFor = ready.identity; return loadMissing({ again: true }); }
        miss.timer = setTimeout(loadMissing, document.hidden ? 4 * MISSING_MS : MISSING_MS);
    }
    function renderMissing(d, looked) {
        const card = $("c-missing-card");
        if (!d || !d.expected.length) { card.hidden = true; return; }
        card.hidden = false;
        const boards = d.expected.map((e) => {
            const checks = e.checks.map((c) => `<li class="check ${esc(c.state)}"><span class="mark">${MARK[c.state] || "·"}</span> ${esc(c.label)}${c.says ? ` — ${esc(c.says)}` : ""}</li>`).join("");
            return `<div class="expected"><b>${esc(e.board)}</b>, pinned at ${esc(e.pinned_at)}.${e.last_said ? ` ${esc(e.last_said)}` : ""}</div>`
                + `<ul class="checks">${checks}</ul>`
                + (e.todo ? `<div class="todo">${esc(e.todo)}</div>` : "");
        }).join("");
        const plugged = (d.plugged || []).map((p) => `<b>${esc(p.port)}</b> ${esc(p.bridge)}${p.serial ? " " + esc(p.serial) : ""}${p.for ? ` — ${esc(p.for)}'s` : " — pinned nowhere"}`);
        $("c-missing").innerHTML = boards
            + `<div class="plugged">Plugged in now: ${plugged.length ? plugged.join(" · ") : "no serial port"}${d.usb_read ? "" : " (USB is not read here)"}</div>`;
        $("missing-said").textContent = `${looked ? "scanned afresh" : "checked"} at ${clock(new Date())}; checked again every few seconds`;
    }

    async function selectPort(port) {
        clearTimeout(miss.timer); miss.timer = null; miss.asked++;
        $("c-missing-card").hidden = true;
        if (state.port && state.port !== port) model.unwatch(state.port, who);
        if (flash && flash.port !== port) { flash.build.destroy(); flash.tasks.destroy(); flash = null; }
        state.port = port; state.kind = null; state.history = []; state.listening = false;
        applyControlState(null);
        for (const el of [root, ...windows]) el.classList.toggle("planning", planning());
        if (!port) {
            applyKind(); renderAll(); loadLevel(); loadPrintJobs();
            if (!planning()) { loadChoices(); loadPrintFiles(); }
            if (planning()) { $("ident").textContent = `${machineAt.path}: not connected — its plan is made here, and ${words().start} is its board's once it is`; loadMissing(); }
            return;
        }
        // Watched at once as what it is known to be, so a verb carried the moment
        // the Machine opens finds it so; what the server says of it follows. A poll the
        // model holds already answers for its buttons and its ring from the first.
        applyKind();
        renderAll();
        if (state.status && state.status.can) takeCan(state.status.can);
        $("ident").textContent = "connecting…";
        try { await model.loadInfo(port); } catch (e) { refuse(e.message); }
        if (state.port !== port) return;  // another port was chosen meanwhile
        model.pullLog(port);
        applyKind();
        renderStatus();
    }

    // --- header controls ------------------------------------------------------------------
    // Each says what refused it, in the log and in the host's status bar.
    $("interval").addEventListener("change", schedule);
    $("poll").onclick = () => (state.port ? model.poll(state.port).catch((e) => refuse(`poll: ${e.message}`)) : Promise.resolve());
    $("reconnect").onclick = async () => {
        if (!state.port) return;
        if (state.kind === "devkit") {
            if (!state.listening) { refuse("Reconnect: not listening -- Listen opens the port (it may reset the board)"); return; }
            model.restream(state.port); model.note(state.port, "listening again"); return;
        }
        try { await model.reconnect(state.port); } catch (e) { refuse("reconnect failed: " + e.message); }
    };
    // A devkit's live serial stream, asked for: the port opened, which may reset the board.
    function listen() {
        if (!state.port) return;
        if (state.kind !== "devkit") { refuse(`Listen: a ${state.kind} is polled over its held link, never streamed -- opening its port would reset it`); return; }
        if (state.listening) { logLine("sys", "already listening"); return; }
        model.note(state.port, `Listen: opening ${state.port} -- this may reset the board`);
        state.listening = true; schedule(); renderDevkit();
    }
    $("listen").onclick = () => listen();
    async function probe() {
        if (!state.port) return;
        if (state.kind !== "devkit") { refuse(`Probe: a ${state.kind} is polled over its held link; esptool would take its port and reset it`); return; }
        try { await model.probe(state.port); } catch (e) { refuse(`probe: ${e.message}`); }
    }
    $("probe").onclick = () => probe();
    // Asking the board what it is: a printer, M115; a devkit, its hello -- and, no
    // hello heard and Identify pressed, M115, since a board pinned before it was
    // asked may be a printer (it answers, and its Machine becomes a printer's).
    // After an upload only the hello is listened for: M115 is a person's to ask.
    async function identify({ pressed = true } = {}) {
        if (!state.port) return;
        try {
            if (state.kind === "devkit") {
                const heard = await model.listen(state.port);
                if (heard.running_sketch) {
                    const next = afterHello ? afterHello(heard.running_sketch) : null;
                    tell(`heard ${heard.running_sketch} say hello${next ? `; ${next}` : ""}`);
                    return;
                }
                if (!pressed) { logLine("sys", "no hello heard -- Identify asks M115 too, when pressed"); return; }
                // Listening no more first: its stream, reconnecting, would take the port the
                // question is asked on (the server refuses it meanwhile, 409).
                if (state.listening) { state.listening = false; schedule(); renderDevkit(); logLine("sys", "listening stopped to ask M115"); }
                try { await model.identify(state.port); }
                catch (e) { refuse(`no hello heard in ${heard.seconds} s, and ${e.message}`); }
                return;
            }
            await model.identify(state.port);
        } catch (e) { refuse(`${state.kind === "devkit" ? "listen" : words().identify}: ${e.message}`); }
    }
    $("identify").onclick = () => identify();
    // Reboot (a DTR pulse): not undoable -- a running print is lost -- so its button is
    // pressed twice; the ring's Reboot asked twice already.
    async function reboot(button = null) {
        if (!state.port) return;
        if (state.kind === "devkit") { refuse("a devkit is reset by flashing it, or by Probe (Link › Probe)"); return; }
        if (!again(button, "reboot")) { tell(`press again to reboot the board on ${state.port}: a running ${jobKind()} would be lost`); return; }
        try { await model.reset(state.port); state.history = []; renderChart(); }
        catch (e) { refuse("reboot failed: " + e.message); }
    }
    $("reset").onclick = () => reboot($("reset"));
    $("release").onclick = async () => {
        if (!state.port) return;
        if (state.kind === "devkit") { state.listening = false; schedule(); model.note(state.port, "stopped listening — Listen opens the port again"); renderDevkit(); return; }
        $("interval").value = "0"; schedule();
        try { const r = await model.release(state.port); logLine("sys", r.released ? "link released — polling off" : "no link was held"); applyControlState(null); }
        catch (e) { refuse("release failed: " + e.message); }
    };
    $("qform").addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const command = $("q").value.trim(); if (!command || !state.port) return;
        $("q").disabled = true;
        try { await model.query(state.port, command); $("q").value = ""; }
        catch (e) { refuse("query refused: " + e.message); }
        $("q").disabled = false; $("q").focus();
    });
    $("show-polls").addEventListener("change", renderLog);
    $("clear").onclick = () => { if (state.port) model.clearLog(state.port); };
    $("download").onclick = () => {
        const text = state.entries.map((e) => `${e.t} ${e.kind.padEnd(4)} ${e.text}`).join("\n");
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
        a.download = `apothecary-${(state.port || "board").replace(/[^A-Za-z0-9]+/g, "_")}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.log`;
        a.click(); URL.revokeObjectURL(a.href);
    };

    // --- control latch + pad ---------------------------------------------------------------
    // An answer carries the latch as it was when it was asked for. `askedAt` is the
    // model's number for the latest arm or disarm, `pending` the ones in flight: an
    // answer asked before the latest, or while one is in flight, is stale.
    // `out` is whether the pad stands popped out, in the host's window: it is, each
    // time the latch is armed. `unknown` is an arm or disarm that failed with the
    // server then silent on the latch: what is drawn is the last it said, marked so.
    const ctl = { armed: false, until: 0, step: 10, timer: null, askedAt: 0, pending: 0, out: true, unknown: false };
    // The deck's knobs, the server's layout (deck_knobs.js), followed while the pad is shown:
    // the machine they move and their step; Knobs here points them at this machine, greyed
    // as the deck's answer for this port says (`can.here`, firmware/can.py).
    const knob = { now: null, timer: null };
    async function followKnobs() {
        let all = [];
        try { all = await knobsRunning(BASE, state.port); } catch (e) { all = []; }
        const k = all.find((c) => c.running) || null;
        knob.now = k;
        renderCan();
        const grp = $("control").querySelector(".deck-knobs-grp");
        grp.hidden = !k;
        if (!k) return;
        const here = !!state.port && k.port === state.port;
        $("deck-knobs-on").textContent = `knobs on ${here ? "this machine" : k.machine} · step ${k.step_mm} mm`;
        $("deck-here").hidden = here;
    }
    async function knobsHere() {
        if (!knob.now || !state.port) return;
        try {
            const s = await chooseKnobs(BASE, knob.now.deck, { port: state.port });
            tell(`the deck's knobs move ${s.machine}, step ${s.step_mm} mm`);
        } catch (e) { refuse(`knobs: ${e.message}`); }
        await followKnobs();
    }
    const latchFresh = (asked) => asked > ctl.askedAt && ctl.pending === 0;
    function renderControl() {
        const left = Math.max(0, Math.round((ctl.until - Date.now()) / 1000));
        if (ctl.armed && left <= 0) { ctl.armed = false; }
        $("ctl").checked = ctl.armed;
        $("ctl-label").classList.toggle("armed", ctl.armed);
        $("ctl-label").classList.toggle("unknown", ctl.unknown);
        $("ctl-unknown").hidden = !ctl.unknown;
        $("control").hidden = !ctl.armed;
        const ttl = ctl.armed ? span(left) : "";
        $("ctl-ttl").textContent = ttl + (ctl.unknown ? " ?" : ""); $("ctl-ttl2").textContent = ttl;
        placePad();
        renderCan();
        clearInterval(ctl.timer); ctl.timer = null;
        if (ctl.armed) ctl.timer = setInterval(renderControl, 1000);
        if (ctl.armed && !knob.timer) { followKnobs(); knob.timer = setInterval(followKnobs, 2000); }
        else if (!ctl.armed && knob.timer) { clearInterval(knob.timer); knob.timer = null; }
    }
    function applyControlState(c) {
        const was = ctl.armed;
        ctl.armed = !!(c && c.armed);
        ctl.until = Date.now() + (c ? c.seconds_left * 1000 : 0);
        ctl.unknown = false;
        if (ctl.armed && !was) ctl.out = true;
        renderControl();
    }
    // Popped out, the pad is the host's window's; put back, or disarmed, it is the
    // Machine's last child again. `padIsOut` is where it stands now, so the host is
    // asked once per move.
    let padIsOut = false;
    function placePad(putBack = false) {
        const out = !!(ctl.armed && ctl.out && padWindow);
        const who = name || state.port || "Control";
        $("ctl-who").textContent = who;
        const pop = $("ctl-pop");
        pop.hidden = !padWindow;
        pop.textContent = ctl.out ? "⇥ Put back" : "⧉ Pop out";
        pop.title = ctl.out ? "Put the control pad back in the Machine, as its window's ✕ does (Panels › Machine › Control pad)" : "The control pad in a loud window of its own beside the world (Panels › Machine › Control pad)";
        if (out === padIsOut) return;
        padIsOut = out;
        pad.classList.toggle("out", out);
        if (out) padWindow.open(pad, who);
        else { padWindow.close(pad, putBack); root.appendChild(pad); }
    }
    async function arm(on) {
        if (!state.port) { $("ctl").checked = false; return; }
        ctl.askedAt = model.tick(); ctl.pending++;
        const port = state.port;
        try { applyControlState(await post("/firmware/printers/control", { port, armed: on })); forgetRefusal(); pollNow(); }
        catch (e) {
            // Refused or unanswered, the latch is what the server says it is, never
            // what was asked for: a Disarm that failed leaves the machine armed. Asked
            // again; with no answer, it stays as last drawn and says it is not confirmed.
            refuse("control: " + e.message);
            let c = null;
            try { c = await api(`/firmware/printers/control?port=${encodeURIComponent(port)}`); } catch (e2) { c = null; }
            if (state.port === port) {
                if (c) applyControlState(c);
                else { ctl.unknown = true; renderControl(); }
            }
        }
        finally { ctl.pending--; }
        await model.pullLog(port);
    }
    function fillTemplate(cmd) {
        return cmd.replace(/\{([a-z-]+)\}/g, (_, id) => $(id).value);
    }
    // --- what the server would refuse now: greyed, with the reason (can.js) ---------------
    // The server's answer (`can` on a status and on an info, firmware/can.py) names each
    // command's verdict; each button names its command in data-can. The pad's buttons
    // carry the line they send, so they are tagged here, once, from it (can.js verbOfLine,
    // which holds which lines the server takes with the latch down). What only this page
    // knows -- a file that is for the other kind, a send from here under way -- is said in
    // the same shape, over the server's answer; the latch is counted down here, since it
    // lapses with no event.
    for (const btn of pad.querySelectorAll("button[data-jog], button[data-cmd]")) {
        btn.dataset.can = btn.dataset.jog ? "jog" : verbOfLine(btn.dataset.cmd);
    }
    const canNow = { server: null, start: null, asking: null };
    // The chosen file asked of the server (GET /firmware/printers/can-start): asked when
    // the choice, the files or the server's own answer for a start changes, never on a timer.
    function askStart() {
        const id = $("print-pick").value, port = state.port;
        if (!id || !port || !isGcode()) { canNow.start = null; return; }
        const key = `${port}|${id}|${JSON.stringify(canNow.server && canNow.server["print.start"])}`;
        if (canNow.asking === key) return;
        canNow.asking = key;
        api(`/firmware/printers/can-start?port=${encodeURIComponent(port)}&file_id=${encodeURIComponent(id)}`)
            .then((v) => { if (canNow.asking === key) { canNow.start = { file: id, verdict: v }; renderCan(); } })
            .catch(() => { if (canNow.asking === key) canNow.asking = null; });
    }
    function localCan() {
        const out = { ...withLatch(canNow.server, ctl.armed, state.port) };
        const job = prt.job, running = !!(job && job.running);
        const chosen = prt.files.find((f) => f.id === $("print-pick").value);
        if (!state.port) {
            out["print.start"] = { ok: false, kind: "offline", why: machineAt ? `${machineAt.path} is not connected: its plan is made here, and ${words().start} is its board's once it is` : "no board is chosen" };
        } else if (running) {
            out["print.start"] = { ok: false, kind: "held", why: `a ${job.kind || "job"} from here is under way` };
        } else if (chosen && ofAnother(chosen, $("print-part").value)) {
            const part = $("print-part").value;
            out["print.start"] = { ok: false, kind: "file", why: `${chosen.name} was made of ${madeFrom(chosen.id)[0]}, and makes names ${part}: ${words().prepare || "Slice"} makes one of ${part}, or makes names ${madeFrom(chosen.id)[0]}` };
        } else if (chosen && canNow.start && canNow.start.file === chosen.id) {
            // Whether this file would be started now is the server's to say (can-start).
            out["print.start"] = canNow.start.verdict;
        } else if (chosen && canNow.asking) {
            out["print.start"] = { ok: false, kind: "file", why: "the server is being asked whether this file can be sent" };
        }
        if (running) {
            // A job from here is this page's own news, fresher than the poll the server's
            // answer was read from: a Pause or a Cancel is not greyed as if nothing ran
            // between ▶ and the next poll.
            for (const verb of ["print.pause", "print.cancel"]) {
                if (out[verb] && !out[verb].ok && out[verb].kind === "idle") out[verb] = { ok: true, why: null, kind: null };
            }
        }
        if (running && job.stage !== words().running && job.stage !== "finishing") {
            out["print.pause"] = { ok: false, kind: "idle", why: `the print is ${job.stage}, not running` };
        }
        // The deck's knobs pointed here: the deck's answer, not the port's.
        if (knob.now && knob.now.can && knob.now.can.here) out.here = knob.now.can.here;
        return out;
    }
    function renderCan() {
        askStart();
        const c = localCan();
        for (const el of everywhere) applyCan(el, c);
        // The Print window's first line reads the same answer: said again with it.
        const next = $("print-next");
        if (next) next.textContent = nextSaid();
    }
    function takeCan(c) {
        if (!c) return;
        canNow.server = c;
        renderCan();
    }

    // Every control send that moves, heats or sets goes through one chain, one line
    // answered before the next is sent, and the pad is disabled while it runs. What
    // stops or interrupts -- the stop, and INTERRUPTS -- is sent at once, outside the
    // chain, and its button is never disabled: a home in flight takes a minute.
    let ctlChain = Promise.resolve();
    const neverBusy = (btn) => btn.id === "pad-estop" || INTERRUPTS.has(btn.dataset.cmd);
    function setBusy(on) {
        for (const btn of $("control").querySelectorAll("button")) {
            btn.dataset.busy = on && !neverBusy(btn) ? "1" : "";
            refreshDisabled(btn);
        }
    }
    // One control request, said in the pad as `said`: whether it was taken.
    // What a person pressed, by its label, for the refusals that name it: the lines it sent
    // map to it, so a refused G90 is a corner move's, as the person knows it.
    const actLabels = new Map();
    let acting = null;
    async function sendOne(path, body, said) {
        const sent = $("ctl-sent"), what = acting || said;
        if (acting && body.command) actLabels.set(body.command.trim().toUpperCase(), acting);
        sent.textContent = "> " + said; sent.classList.remove("bad");
        try {
            const asked = model.tick();
            const r = await post(path, { port: state.port, ...body });
            if (latchFresh(asked)) applyControlState(r.control);
        } catch (e) {
            sent.textContent = `${what}: ${e.message}`; sent.classList.add("bad");
            refuse(`${what}: ${e.message}`);
            if (/not armed/.test(e.message)) applyControlState(null);
            return false;
        }
        forgetRefusal(`${what} sent`);
        return true;
    }
    const labelOf = (btn) => btn.dataset.label || btn.textContent.replace(/^[^\p{L}\p{N}]+/u, "").trim();
    // The label of the pad's button that sends `command`, or null where none does.
    function labelOfLine(command) {
        const want = String(command || "").trim().toUpperCase();
        for (const btn of pad.querySelectorAll("button[data-cmd]")) {
            const make = btn.dataset.cmd.startsWith("HOME") ? LINES_OF()[BY_CMD[btn.dataset.cmd]] : null;
            const line = make ? make(handle) : fillTemplate(btn.dataset.cmd);
            if (String(line).trim().toUpperCase() === want) return labelOf(btn);
        }
        return null;
    }
    async function sendLines(lines) {
        for (const command of lines) {
            if (!(await sendOne("/firmware/printers/command", { command }, command))) return false;
        }
        return true;
    }
    const pollNow = () => (state.port ? model.poll(state.port).catch(() => null) : Promise.resolve(null));
    // Straight through, never queued behind another line.
    async function sendNow(command, label = null) {
        if (!state.port) return;
        acting = label;
        try { await sendLines([command]); } finally { acting = null; }
        await pollNow(); await model.pullLog(state.port);
    }
    function sendControl(command, confirmText, label = null) {
        if (!state.port) return Promise.resolve();
        if (confirmText && !confirm(confirmText)) return Promise.resolve();
        if (INTERRUPTS.has(command)) return sendNow(command, label);
        return enqueue([command], undefined, label);
    }
    // `send` is what the turn sends: the lines, or a jog's one request; `label` what the
    // person pressed, which a refusal names in place of the line.
    function enqueue(lines, send = () => sendLines(lines), label = null) {
        ctlChain = ctlChain.then(async () => {
            setBusy(true);
            acting = label;
            try { await send(); await pollNow(); }  // the effect shows in the cards right away
            finally { acting = null; setBusy(false); }
            await model.pullLog(state.port);
        }).catch(() => setBusy(false));
        return ctlChain;
    }
    function jog(axis, sign) {
        const d = (sign === "-" ? -ctl.step : ctl.step).toFixed(1).replace(/\.0$/, "");
        // The tool's marker moves ahead of the poll that confirms it.
        const st = state.status;
        const p = st && st.position ? { ...st.position } : { x: 0, y: 0, z: 0 };
        p[axis.toLowerCase()] = (p[axis.toLowerCase()] || 0) + Number(d);
        const k = axis.toLowerCase();
        const ahead = st && st.tool_position ? { ...st.tool_position, [k]: (st.tool_position[k] || 0) + Number(d) } : null;
        emit("apothecary:position", { position: toolPosition({ ...(st || {}), position: p, tool_position: ahead }), source: "jog", port: state.port });
        const f = Number($("h-feed").value) || words().feedDefault;
        // One request for either kind (POST /firmware/printers/jog): the server sends a
        // router GRBL's one jog line, and a printer its relative move with absolute
        // positioning put back whatever became of it, so no line of a jog is the page's
        // to lose. In the chain, as every move is: one jog answered before the next.
        return enqueue([], () => sendOne("/firmware/printers/jog", { axis, mm: Number(d), feed: f }, `jog ${axis}${d} F${f}`), `Jog ${axis}${sign}`);
    }
    $("ctl").addEventListener("change", () => arm($("ctl").checked));
    $("ctl-disarm").onclick = () => arm(false);
    // In its own window, or back in the Machine: the pad's ⧉ Pop out and ⇥ Put back,
    // and the ring's Panels › Machine › Control pad. What it did, or why it could not.
    function togglePad() {
        const who = name || state.port;
        if (!ctl.armed) return { refused: `${who}'s control is not armed: ⚙ Control in its Machine arms it, and its pad pops out` };
        if (!padWindow) return { refused: `${who}'s control pad has no window to pop out into here` };
        ctl.out = !ctl.out;
        placePad(true);
        if (!ctl.out) pad.scrollIntoView({ block: "nearest" });
        return { said: ctl.out ? `${who}'s control pad is in a loud window of its own beside the world` : `${who}'s control pad put back in its Machine` };
    }
    // Its window's ✕: the pad back in the Machine, as ⇥ Put back does.
    function padBack() {
        if (!padIsOut) return;
        padIsOut = false;
        ctl.out = false;
        pad.classList.remove("out");
        root.appendChild(pad);
        placePad();
    }
    $("ctl-pop").onclick = () => togglePad();
    // The emergency stop never asks: a printer's heaters and motors off, a router reset, at once.
    // The Machine's button and the pad's own, which shows while the pad stands popped
    // out, in a window the Machine's head may not be beside.
    const estop = () => sendNow(words().stop);
    $("estop").onclick = estop;
    $("pad-estop").onclick = estop;
    $("h-fan").addEventListener("input", () => { $("h-fan-v").textContent = $("h-fan").value; });
    $("control").addEventListener("click", (ev) => {
        const btn = ev.target.closest("button"); if (!btn) return;
        if (btn.id === "deck-here") {
            knobsHere();
        } else if (btn.dataset.step) {
            ctl.step = Number(btn.dataset.step);
            for (const s of $("control").querySelectorAll(".steps button")) s.classList.toggle("on", s === btn);
        } else if (btn.dataset.jog) {
            jog(btn.dataset.jog[0], btn.dataset.jog[1]);
        } else if (btn.dataset.cmd) {
            if (btn.dataset.twice && !again(btn, btn.dataset.twice)) { tell(`press again to ${btn.dataset.twice}: it cannot be undone`); return; }
            // A job's verb while one streams from here goes to the job, which holds or
            // resets the controller itself and stops or starts feeding with it.
            const verb = HOST_VERBS[BY_CMD[btn.dataset.cmd]];
            if (verb && prt.job && prt.job.running) { printVerb(verb); return; }
            // One home button per axis, and for all, for both G-code machines: each dialect's line.
            sendControl(btn.dataset.cmd.startsWith("HOME") ? LINES_OF()[BY_CMD[btn.dataset.cmd]](handle) : fillTemplate(btn.dataset.cmd), undefined, labelOf(btn));
        }
    });

    // --- bed level: probe or read, show the mesh, keep the records -----------------------
    // A printer's bed, probed or read as stored; a router's table, mapped by its probe
    // at a grid of points: one card, one route, the kind's words (KINDS[kind].level).
    // `volume` is the machine's working volume from its frame, null until the world or
    // GET /firmware/printers/where has said it: no corner is guessed from another's.
    // `frame` is the whole of that record (api.machine_frame), which says too which way
    // a router's axes home: where its file's zero stands (fileOrigin).
    const level = { records: [], shown: null, timer: null, volume: null, frame: null };
    const onWhere = (ev) => {
        const frame = ev.detail && ev.detail.printer && ev.detail.printer.frame;
        if (frame && (!ev.detail.port || ev.detail.port === state.port)) { level.volume = frame.volume; level.frame = frame; }
    };
    window.addEventListener("apothecary:where", onWhere);
    onWindow.push(["apothecary:where", onWhere]);
    // Null while the printer's volume is not known (its board pinned nowhere): refused.
    const NO_CORNERS = "a corner move needs the printer's volume, which its frame says once its board is pinned in a site";
    function cornerLines(which) {
        if (!level.volume) return null;
        // Paper height at the four corners, inset from the edges; lifted first so a
        // nozzle never drags. Absolute moves; the allowlist bounds them.
        const [vx, vy] = level.volume, inset = 30, z = 0.2, f = 3000;
        const x = which[1] === "L" ? inset : Math.round(vx - inset);
        const y = which[0] === "F" ? inset : Math.round(vy - inset);
        return ["G90", `G1 Z5 F${f}`, `G1 X${x} Y${y} F${f}`, `G1 Z${z} F${Math.min(f, 600)}`];
    }
    function heat(v, lo, hi) {
        // Blue below the mean, amber above: the same two hues as the chart, so a
        // low corner reads as "bed" and a high one as "hotend" without a key.
        const t = hi > lo ? (v - lo) / (hi - lo) : 0.5;
        const a = [0x6f, 0xb3, 0xe8], c2 = [0xe8, 0xb0, 0x4a];
        return `rgb(${a.map((c, i) => Math.round(c + (c2[i] - c) * t)).join(",")})`;
    }
    // The probe and the corners move the machine: greyed while control is down, saying so,
    // as every button that needs the latch is (renderCan); Read mesh moves nothing.
    function renderLevel() {
        const rec = level.shown, w = words().level;
        if (!w) return;  // a devkit has no bed or table to map, and no words for one
        const meshEl = $("mesh"), statsEl = $("level-stats");
        if (!rec || !rec.mesh || !rec.mesh.length) {
            meshEl.innerHTML = ""; meshEl.style.gridTemplateColumns = "";
            statsEl.innerHTML = `<span class="empty">${esc(w.none)}</span>`;
        } else {
            const st = rec.stats || {};
            const rows = rec.mesh, cols = rows[0].length;
            meshEl.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
            // Drawn as the bed lies: the last row printed is the back of the bed, so it goes on top.
            meshEl.innerHTML = [...rows].reverse().map((row) => row.map((v) => `<div class="cell" style="background:${heat(v, st.min, st.max)}" title="${v.toFixed(3)} mm">${v.toFixed(2)}</div>`).join("")).join("");
            const c = st.corners || {};
            // A router's map says where its points lie (record.area) and reads in machine
            // coordinates; a printer's mesh is its firmware's, with the leveling state, and
            // where its probe said the points lie when it said (G29 V3).
            const a = rec.area, table = rec.method === "G38.2";
            statsEl.innerHTML = `${esc(rec.method)} · ${stamp(rec.at)} · range <b>${(st.range ?? 0).toFixed(3)}</b> mm · tilt X <b>${(st.tilt_x ?? 0).toFixed(3)}</b> Y <b>${(st.tilt_y ?? 0).toFixed(3)}</b> mm ${esc(w.across)}<br>`
                + `corners vs mean: FL <b>${(c.front_left ?? 0).toFixed(3)}</b> FR <b>${(c.front_right ?? 0).toFixed(3)}</b> BL <b>${(c.back_left ?? 0).toFixed(3)}</b> BR <b>${(c.back_right ?? 0).toFixed(3)}</b>`
                + (table && a ? ` · Z in machine coordinates · X ${a.min.x}–${a.max.x}, Y ${a.min.y}–${a.max.y} mm from the front-left corner` : ` · leveling ${rec.leveling_on == null ? "?" : (rec.leveling_on ? "on" : "off")}`)
                + (!table && a ? ` · probed X ${a.min.x}–${a.max.x}, Y ${a.min.y}–${a.max.y} mm, where the probe said` : "")
                + (rec.probe_offset ? ` · probe offset X${rec.probe_offset.x} Y${rec.probe_offset.y} Z${rec.probe_offset.z}` : "")
                + (rec.bed_c != null ? ` · bed ${degrees(rec.bed_c)}` : "") + (rec.hotend_c != null ? ` hotend ${degrees(rec.hotend_c)}` : "")
                + (rec.note ? `<br>note: ${esc(rec.note)}` : "");
        }
        emit("apothecary:mesh", rec || null);  // the board view and the world draw it over the bed
        $("level-history").innerHTML = level.records.length
            ? level.records.map((r) => `<div><span class="pick ${level.shown && r.id === level.shown.id ? "on" : ""}" data-id="${esc(r.id)}">${stamp(r.at)} · ${esc(r.method)} · range ${(r.stats && r.stats.range != null ? r.stats.range : 0).toFixed(3)} mm</span><a href="${BASE}/firmware/printers/leveling/${encodeURIComponent(r.id)}" download="${esc(r.id)}.json" title="The record as JSON, with every line the firmware said">⤓ log</a></div>`).join("")
            : "";
    }
    async function loadLevel() {
        if (!state.port || !isGcode()) { level.records = []; level.shown = null; renderLevel(); return; }
        try {
            level.records = await api(`/firmware/printers/leveling?port=${encodeURIComponent(state.port)}`);
            if (!level.shown || !level.records.some((r) => r.id === level.shown.id)) level.shown = level.records[0] || null;
        } catch (e) { level.records = []; }
        renderLevel();
    }
    // The stage a reading is at and, while a table map probes, the points done of its total.
    const levelStage = (job) => `${job.stage}${job.points ? ` ${job.points.done}/${job.points.total}` : ""}…`;
    async function watchLevelJob() {
        clearTimeout(level.timer);
        try {
            const job = await api(`/firmware/printers/level?port=${encodeURIComponent(state.port)}`);
            $("level-job").textContent = job.running ? levelStage(job) : (job.error ? `failed: ${job.error}` : "");
            if (job.running) { level.timer = setTimeout(watchLevelJob, 1000); return; }
            level.timer = null;
            if (job.record_id) {
                await loadLevel(); level.shown = level.records.find((r) => r.id === job.record_id) || level.shown; renderLevel();
                // A reading kept: the windows of the bed (Runs, Differences) take it.
                window.dispatchEvent(new CustomEvent("apothecary:leveled", { detail: { port: state.port, records: job.record_ids || [job.record_id] } }));
            }
            await pollNow();
        } catch (e) { $("level-job").textContent = e.message; }
    }
    // `hot`: probe hot -- the bed heated to hot.heat °C and held hot.soak s first, probed
    // twice, a reading each, and turned off after. { said } or { refused }.
    async function startLevel(probe, hot = null) {
        const no = (text) => { refuse(text); return { refused: text }; };
        if (!state.port) return { refused: "no port" };
        if (probe && !ctl.armed) return no("probing moves the machine: arm control first");
        const ask = hot
            ? `Heat ${state.port}'s bed to ${hot.heat} °C, hold it ${hot.soak} s, then home and probe it twice? It is turned off after.`
            : words().level.ask.replace("{port}", state.port);
        if (probe && !confirm(ask)) return { refused: "not asked to" };
        const body = hot ? { port: state.port, probe, heat_c: hot.heat, soak_s: hot.soak, times: 2 } : { port: state.port, probe };
        try {
            const job = await post("/firmware/printers/level", body);
            $("level-job").textContent = levelStage(job);
            level.timer = setTimeout(watchLevelJob, 800);
            forgetRefusal();
            return { said: hot ? `${state.port}'s bed heating to ${hot.heat} °C, held ${hot.soak} s, then probed twice: Runs lists each reading as it is kept, and the bed is turned off after` : `${state.port}: ${levelStage(job)}` };
        } catch (e) { $("level-job").textContent = e.message; return no(`${words().level.card}: ` + e.message); }
    }
    // The bed temperature of the filament the Print window holds (the loaded one, else the
    // profile's), or null where none is known.
    function bedTemperature() {
        const a = fil.answer;
        if (!a || !a.choices) return null;
        const name = $("print-filament").value || (a.loaded ? a.loaded.loaded.filament : a.profile);
        const found = a.choices.find((c) => c.name === name);
        const t = found ? Number(found.bed_temperature) : NaN;
        return Number.isFinite(t) && t > 0 ? t : null;
    }
    $("level-probe").onclick = () => startLevel(true);
    $("level-read").onclick = () => startLevel(false);
    $("level-history").addEventListener("click", (ev) => {
        const pick = ev.target.closest(".pick"); if (!pick) return;
        level.shown = level.records.find((r) => r.id === pick.dataset.id) || level.shown; renderLevel();
    });
    $("level-card").addEventListener("click", (ev) => {
        const btn = ev.target.closest("button[data-corner]"); if (!btn) return;
        if (!ctl.armed) { refuse("a corner move needs control armed"); return; }
        const lines = cornerLines(btn.dataset.corner);
        if (!lines) { refuse(NO_CORNERS); return; }
        enqueue(lines, undefined, `${labelOf(btn)} corner`);
    });
    // A reading or a print that holds the port, as a poll reports it, is followed.
    function followJob(st) {
        const job = st.job;
        if (job && job.kind === "leveling") { $("level-job").textContent = levelStage(job); if (!level.timer) level.timer = setTimeout(watchLevelJob, 1000); }
        if (job && (job.kind === "print" || job.kind === "cut")) { prt.job = job; renderPrint(); if (!prt.timer) prt.timer = setTimeout(watchPrint, 1000); }
    }

    // --- print from here: a kept file streamed over the link, as a print job ----------
    // `jobs` is the printer's print jobs, running first then newest (GET /jobs): the
    // history. `choices` is what a job here can name (GET /jobs/choices): the parts
    // and pieces of the site the printer is pinned in.
    // `wanted` is a part asked for from outside (print.choose), chosen once listed.
    const prt = { files: [], jobs: [], job: null, timer: null, choices: null, wanted: null, slices: {}, picked: null, ownFor: null, offset: null, offsetDrawn: null };
    // Slicing: the slicer's status (whether one is installed), and the task that
    // slices what makes names, followed by tasks.js at the slicer's own routes.
    // `shown` is the kept file whose slice the card says, the one chosen in its files.
    const slc = { status: null, tasks: null, running: false, shown: null };
    // The chosen file's slice, said under makes: what it was sliced from, for which
    // printer, what it used and the estimate. Said again only when another file is
    // chosen, and never over a slice that runs or one that has just failed.
    // --- the chosen file's path, drawn in the world (docs/toolpath-preview.md) --------
    // One slider: off at the left, then through each group of moves, all of them at the
    // right. Nothing is asked of the server until it is moved off the left.
    // `unplaced`: the card last said the path is not drawn for want of its zero.
    const pv = { file: null, data: null, turn: 0, told: null, unplaced: false };
    const previewOn = () => Number($("print-preview").value) > 0;
    // A router's file with no zero to stand at (fileOrigin): why its path is not drawn.
    const ZERO_UNKNOWN = "where its work zero stands is not known until the controller has said which way each axis homes (its settings, $$) and its work offset";
    // Where the file's zero stands in the volume; null for a router's until it is known.
    const previewOrigin = () => {
        if (!planning() || state.kind !== "router" || !pv.data) return fileOrigin(state.port ? b().status : null, level.frame, { router: state.kind === "router" });
        // Planned, with no board to say where its work zero is: the stock as if laid on
        // the table at the working area's front-left corner, its deepest pass on the table.
        const lows = Object.values(pv.data.bounds || {}).map((box) => box.min[2]);
        return { x: 0, y: 0, z: Math.max(0, -Math.min(0, ...lows)) };
    };
    const inMetres = (v) => (v >= 1000 ? `${(v / 1000).toFixed(1)} m` : mmText(v));
    const signed = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;
    function previewUpto() {
        const groups = pv.data ? pv.data.groups : [], at = Number($("print-preview").value);
        if (!at || !groups.length) return 0;
        const group = groups[Math.min(at, groups.length) - 1];
        return group.first + group.count;
    }
    function tellPreview() {
        const origin = previewOrigin(), on = previewOn() && !!pv.data && origin !== null;
        // A poll that places the zero, or no longer does: the card says so first.
        if (previewOn() && pv.data && (origin === null) !== pv.unplaced) { renderPreview(); return; }
        const told = `${on ? pv.file : ""}|${on ? previewUpto() : 0}|${JSON.stringify(origin)}`;
        if (told === pv.told) return;
        pv.told = told;
        emit("apothecary:toolpath", { port: state.port, path: machineAt ? machineAt.path : null, preview: on ? pv.data : null, upto: previewUpto(), origin });
    }
    function renderPreview() {
        const said = $("print-preview-said"), d = pv.data;
        pv.unplaced = previewOn() && !!d && previewOrigin() === null;
        if (!previewOn() || !d) {
            said.textContent = previewOn() ? "reading the file…" : "off";
        } else if (!d.groups.length) {
            said.textContent = "this file moves nothing";
        } else if (pv.unplaced) {
            said.textContent = `not drawn: ${ZERO_UNKNOWN}`;
        } else {
            const at = Number($("print-preview").value), n = d.groups.length, group = d.groups[at - 1];
            const where = at >= n ? "all of it" : group.label;
            const zero = planning() && state.kind === "router" ? " · drawn on the working area's front-left corner, its deepest pass on the table: its zero is set at the machine" : "";
            // Each kind's length in the colour its moves are drawn in: the path's key.
            said.textContent = `${where} · the file: `;
            for (const k of d.kinds.filter((k) => d.length_mm[k])) {
                const key = document.createElement("span");
                key.className = "move-key";
                key.dataset.kind = k;
                key.style.color = `#${MOVE_COLORS[k].toString(16).padStart(6, "0")}`;
                key.textContent = `${k} ${inMetres(d.length_mm[k])}`;
                said.append(key, ", ");
            }
            said.append(`${span(d.time_s)} at its feeds${d.within_mm ? ` · drawn to within ${d.within_mm} mm` : ""}${zero}`);
        }
        tellPreview();
    }
    async function loadPreview() {
        const id = $("print-pick").value || null, turn = ++pv.turn, slider = $("print-preview");
        pv.file = id;
        pv.data = null;
        renderPreview();
        if (!id || !(state.port || planning()) || !isGcode()) { slider.value = "0"; slider.max = "1"; renderPreview(); return; }
        let data;
        try { data = await api(`/firmware/printers/prints/${encodeURIComponent(id)}/preview?machine=${encodeURIComponent(state.kind)}`); }
        catch (e) { if (turn === pv.turn) { slider.value = "0"; refuse(`preview: ${e.message}`); renderPreview(); } return; }
        if (turn !== pv.turn) return;
        pv.data = data;
        slider.max = String(Math.max(1, data.groups.length));
        slider.value = slider.max;
        renderPreview();
    }
    // The chosen file changed: a preview that is on follows it, one that is off forgets it.
    function followChosenFile() {
        const id = $("print-pick").value || null;
        if (id === pv.file) return;
        if (previewOn()) { loadPreview(); return; }
        pv.file = id;
        pv.data = null;
        $("print-preview").max = "1";
        renderPreview();
    }
    function togglePreview() {
        const slider = $("print-preview");
        slider.value = previewOn() ? "0" : slider.max;
        if (previewOn() && !pv.data) loadPreview(); else renderPreview();
    }
    // The Machine view's: the chosen file's path drawn where it is not drawn already,
    // all of it -- a slider a person left part way stays there. What it found, for the
    // host to say: the card's name and what a group is called, the file, what its
    // slice or toolpath was made from (`of`: a piece's path and a part's name), and
    // whether its path is drawn and how far (`where`), why not (`refused`), or with
    // no file of this machine's kept why there is none (`none`) and how one comes to
    // be (`how`). Null on a devkit, which has no file.
    async function showPreview() {
        if (!(state.port || planning()) || !isGcode()) return null;
        const w = words(), found = { card: w.verb, word: w.slice ? "layer" : "pass", file: null, of: [], drawn: false, where: null, refused: null, none: null, how: null };
        await loadPrintFiles();
        const id = $("print-pick").value || null;
        const name = id ? (prt.files.find((f) => f.id === id) || { name: id }).name : null;
        // Another kind of machine's file is drawn only where a person asked for it.
        if (!id || (madeForAnother(id) && !previewOn())) {
            // Nothing chosen with files kept: each is the other kind of machine's.
            const other = w.slice ? "router" : "printer", n = prt.files.length;
            found.none = id ? `the file chosen, ${name}, was made for a ${other}, and none is kept for this ${state.kind} yet`
                : n ? `${n === 1 ? `the file kept, ${prt.files[0].name}, was` : "the files kept were"} made for a ${other}, and none is kept for this ${state.kind} yet`
                : "no file is kept yet";
            found.how = "choose a part under makes, or Choose File";
            return found;
        }
        found.file = name;
        found.of = madeFrom(id);
        // A router's file stands at its work zero: its working area and a poll are
        // waited for, so the path is drawn where it will stay.
        if (w.dialect === "grbl" && state.port) {
            await loadWhere();
            if (!b().status) await model.poll(state.port).catch(() => {});
        }
        const before = refusals, slider = $("print-preview");
        if (!previewOn()) slider.value = slider.max;
        if (!pv.data || pv.file !== id) await loadPreview(); else renderPreview();
        const d = pv.data, at = Number(slider.value);
        const placed = previewOrigin() !== null;
        found.drawn = previewOn() && !!d && d.groups.length > 0 && placed;
        if (found.drawn) { found.word = d.word; found.where = at >= d.groups.length ? "all of it" : d.groups[at - 1].label; }
        else found.refused = refusals > before ? lastRefusal : !d ? "its path could not be read" : !d.groups.length ? "this file moves nothing" : ZERO_UNKNOWN;
        return found;
    }
    // --- the filament loaded ---------------------------------------------------------------
    // The filament on the printer's spool holder, chosen among those its slicer profile can
    // load (slicer/filaments.py): its next slices are made with it and take its own tuning.
    // shown: the printer whose filaments the row holds; loading: the one asked, or the one
    // whose ask failed until it is asked again; drawn: the options the drop-down holds.
    const fil = { shown: null, answer: null, loading: null, failing: null, fails: 0, drawn: null };
    function printerAt() {
        if (machineAt && machineAt.site && machineAt.path) return { site: machineAt.site, printer: machineAt.path };
        const c = prt.choices;
        return c && c.site ? { site: c.site, printer: printerName() } : null;
    }
    function renderFilament(force) {
        const row = $("print-filament-row");
        // A Machine gone has no row: an answer or a wait that lands after it draws nothing
        // and asks nothing again.
        if (!row) return;
        const at = state.kind === "printer" ? printerAt() : null;
        const key = at ? `${at.site}:${at.printer}` : null;
        if (key !== fil.shown) {
            fil.shown = null; fil.answer = null;
            if (key && fil.loading !== key) askFilaments(key, at);
        }
        const a = fil.answer;
        row.hidden = !(a && a.chooses);
        if (row.hidden) return;
        const sel = $("print-filament"), now = a.loaded ? a.loaded.loaded.filament : a.profile;
        // Drawn again only when what it offers or holds changed, and never while a person
        // has it: a print renders this once a second, and would reset it under them.
        if (force || document.activeElement !== sel) {
            const options = a.choices.map((c) => `<option value="${esc(c.name)}">${esc(c.name)}${c.nozzle_temperature ? ` · ${esc(c.nozzle_temperature)} °C` : ""}</option>`).join("");
            if (fil.drawn !== options) { sel.innerHTML = options; fil.drawn = options; }
            if (sel.value !== now) sel.value = now;
        }
        $("print-filament-said").textContent = a.loaded
            ? `loaded ${a.loaded.loaded.at.slice(0, 16).replace("T", " ")} UTC${a.loaded.loaded.note ? ` (${a.loaded.loaded.note})` : ""}`
            : "the profile's own: choose what is loaded";
    }
    // A printer's filaments are asked once; an ask that failed (no slicer installed, a
    // printer with no profile, the server away) leaves no row and is asked again, each
    // wait twice the last, up to a minute.
    function askFilaments(key, at) {
        if (fil.failing !== key) fil.fails = 0;
        fil.loading = key;
        api(`/slicer/filaments?site=${encodeURIComponent(at.site)}&printer=${encodeURIComponent(at.printer)}`)
            .then((a) => {
                if (fil.loading !== key) return;
                fil.loading = fil.failing = null; fil.fails = 0;
                fil.shown = key; fil.answer = a;
                renderFilament();
            })
            .catch(() => {
                if (fil.loading !== key) return;
                fil.failing = key;
                const wait = Math.min(60000, 2000 * 2 ** fil.fails++);
                setTimeout(() => { if (fil.loading === key) { fil.loading = null; renderFilament(); } }, wait);
            });
    }
    async function loadFilament() {
        const at = printerAt();
        if (!at) { refuse("filament: this printer stands in no site"); return false; }
        const filament = $("print-filament").value;
        let kept;
        try { kept = await post("/slicer/filaments/loaded", { ...at, filament }); }
        catch (e) { refuse(`filament: ${e.message}`); renderFilament(true); return false; }
        fil.answer = { ...fil.answer, loaded: kept };
        renderFilament();
        tell(`${filament} loaded on ${at.printer}: its next slices are made with it, and take its own tuning`);
        return true;
    }
    $("print-filament").onchange = () => loadFilament();
    $("print-filament").addEventListener("blur", () => renderFilament());


    // What a kept file's slice or toolpath was made from: the piece's path in its
    // site and the part's name, or nothing for a file no slice or toolpath made.
    function madeFrom(id) {
        const r = id && prt.slices[id];
        if (!r) return [];
        return r.toolpath ? [r.part] : [...new Set([r.made.path, r.made.name].filter(Boolean))];
    }
    // The newest file kept for this kind of machine that was made from `path`, chosen
    // in the card: its name, or null where none is kept.
    async function chooseFileOf(path) {
        await loadPrintFiles();
        const kept = prt.files.find((f) => fits(f) && madeFrom(f.id).includes(path));
        if (!kept) return null;
        await loadPrintFiles(kept.id);
        return kept.name;
    }
    function showChosenSlice() {
        const id = $("print-pick").value || null;
        if (slc.running || id === slc.shown) return;
        slc.shown = id;
        const r = id && prt.slices[id];
        if (r && r.toolpath) { $("print-slice-box").hidden = false; $("print-slice-task").hidden = true; $("print-slice-said").innerHTML = toolpathSaid(r); return; }
        $("print-slice-task").hidden = true;
        $("print-slice-said").innerHTML = r ? sliceSaid(r) : "";
        $("print-slice-box").hidden = !r;
    }
    // The card draws the step a person is at, in the loop's order, and each control
    // after it once what it needs holds: makes and Choose File are the two ways in; a
    // part chosen has its Slice or Toolpath; a file kept has the files, a file chosen
    // its ✕, the preview, Keep as plan and ▶; a job running from here has Pause and
    // Cancel, and Resume while it is paused; a job that ran has its progress. A control
    // that is there and cannot go yet is disabled, and its tooltip says why.
    function renderPrint() {
        const job = prt.job, running = !!(job && job.running);
        const paused = running && job.stage === "paused";
        const picked = $("print-pick").value, part = $("print-part").value;
        const chosen = prt.files.find((f) => f.id === picked);
        $("print-pick").hidden = !prt.files.length;
        $("print-delete").hidden = !picked;
        setReason($("print-delete"), running && job.file_id === picked ? `the ${job.kind || "job"} from here is sending it` : null, "Forget the chosen file");
        $("print-preview-row").hidden = !picked;
        $("print-start").hidden = !picked;
        setTip($("print-start"), words().startTitle);
        $("print-pause").hidden = !running || paused;
        renderCan();
        $("print-resume").hidden = !paused;
        $("print-cancel").hidden = !running;
        $("print-verbs").hidden = !picked && !running;
        const slicerOk = !words().slice || !!(slc.status && slc.status.ok);
        $("print-slice").hidden = !part;
        // A printer's slice levels as chosen here, for that slice (compose.levelled).
        $("print-level-row").hidden = !words().slice || !part;
        $("print-adhesion-row").hidden = !words().slice || !part;
        // The printer's first-layer offset, where its profile's start names it.
        $("print-offset-row").hidden = !words().slice || !part || !(prt.offset && prt.offset.named);
        if (words().slice) sayTheOwn(part);
        setReason($("print-slice"), slc.running ? "a slice is running; its log is in this window, with its Cancel" : null, slicerOk
            ? words().prepareTitle
            : `No slicer: ${(slc.status && slc.status.why) || "asking"}. Panels › Tools › Bench › Install › OrcaSlicer installs it`);
        const went = !!(job && (running || job.stage));
        $("print-progress-row").hidden = !went;
        $("print-bar").hidden = !went;
        if (went) {
            const pct = (job.progress * 100).toFixed(1);
            $("print-progress").textContent = `${job.name} · ${job.stage} · ${job.sent}/${job.total} lines (${pct}%) · ${span(job.elapsed_s)}` + (job.operation && running ? ` · ${job.operation}` : "") + (job.current && running ? ` · ${job.current}` : "") + (job.error ? ` · ${job.error}` : "");
            $("b-print").style.width = pct + "%";
        } else {
            $("print-progress").textContent = ""; $("b-print").style.width = "0";
        }
        $("print-job").textContent = running ? `${job.stage}…` : "";
        $("print-history").innerHTML = prt.jobs.map(jobRow).join("");
        showChosenSlice();
        followChosenFile();
        renderPlan();
        renderFilament();
    }
    // The step a person is at, in the window's first line: what is next, and where.
    function nextSaid() {
        const w = words(), job = prt.job, running = !!(job && job.running);
        const part = $("print-part").value, file = prt.files.find((f) => f.id === $("print-pick").value);
        if (!isGcode() || (!state.port && !planning())) return "";
        if (running) return job.stage === "paused"
            ? `The ${w.job} is paused: ▶ Resume feeds it again, ⏏ Abort ends it.`
            : `The ${w.job} streams from here; its end opens its piece's drawer in Part › Feedback.`;
        if (slc.running) return `Slicing ${part}: its G-code is chosen here when it ends, for ${w.start}.`;
        if (file) {
            const v = localCan()["print.start"];
            if (v && !v.ok && v.kind === "armed") return `${w.start} waits for control: ⚙ Control in the Machine's head arms it.`;
            if (v && !v.ok) return `${w.start} waits: ${v.why}.`;
            return `${w.start} ${w.job}s ${file.name}${part ? `, making ${part}` : ""}, asking first.`;
        }
        if (part) return `${w.prepare} makes ${part}'s file for this ${state.kind}.`;
        return `Choose what it makes under makes, then ${w.prepare}; or choose a file kept.`;
    }
    // One job of the history: when it started and finished, its kind, the file it ran
    // and the part it makes, how it ended (and why), and how far it got. A job that made
    // a piece opens its drawer, pressed.
    function jobRow(j) {
        const d = j.detail || {};
        const when = `${stamp(j.started_at)} – ${j.finished_at ? clock(j.finished_at) : "…"}`;
        const part = j.part ? ` → ${esc(j.part.path)}` : "";
        const lines = d.total != null ? ` · ${d.sent}/${d.total} lines` : "";
        const why = j.reason ? ` (${esc(j.reason)})` : "";
        const opens = j.part && openDrawer ? ` role="button" tabindex="0" title="Open the drawer of ${esc(j.part.path)}, the piece it made, in Part › Feedback"` : "";
        return `<div class="job-row" data-job="${esc(j.id)}"${opens}><span class="${esc(j.outcome)}">${when} · ${esc(j.kind)} · ${esc(j.input.name)}${part} · ${esc(j.outcome)}${lines}${why}</span><a href="${BASE}/jobs/${encodeURIComponent(j.id)}" download="${esc(j.id)}.json" title="The job as JSON, with the tail of what the firmware said">⤓ log</a></div>`;
    }
    // A job's row pressed, or Enter on it: its piece's drawer in Part › Feedback.
    function onJobRow(ev) {
        if ((ev.type === "keydown" && ev.key !== "Enter") || ev.target.closest("a")) return;
        const row = ev.target.closest('.job-row[role="button"]');
        const job = row && prt.jobs.find((j) => j.id === row.dataset.job);
        if (job && openDrawer) openDrawer(job);
    }
    $("print-history").addEventListener("click", onJobRow);
    $("print-history").addEventListener("keydown", onJobRow);
    // A kept file a slice made says what it was sliced from, and for which printer.
    // What a kept file came from: a slice's piece and printer, or a toolpath's part and router.
    const slicedFrom = (f) => {
        const r = prt.slices[f.id];
        if (!r) return "";
        if (r.toolpath) return ` · toolpath of ${esc(r.part)} for ${esc(r.router.name)}`;
        return ` · sliced from ${esc(r.made.name)} for ${esc(r.printer.name)}`;
    };
    async function loadPrintFiles(pick) {
        try { prt.files = await api("/firmware/printers/prints"); } catch (e) { prt.files = []; }
        try { prt.slices = Object.fromEntries((await api("/slicer/slices")).map((r) => [r.file_id, r])); } catch (e) { prt.slices = {}; }
        try { for (const r of await api("/cam/cuts")) prt.slices[r.file_id] = { ...r, toolpath: true }; } catch (e) { /* no toolpaths kept */ }
        const sel = $("print-pick"), had = pick || sel.value;
        // The files kept are every machine's. What was chosen stays chosen, but the
        // other kind of machine's file gives way to the newest of this kind; with
        // nothing chosen that one is. Where every file kept is the other kind's,
        // none is chosen until a person chooses one here: one left chosen from
        // another machine's Machine does not stay.
        const own = prt.files.find(fits);
        const none = prt.files.length && !own ? `<option value="">— none kept for ${state.kind ? `a ${state.kind}` : "this machine"} —</option>` : "";
        sel.innerHTML = prt.files.length
            ? none + prt.files.map((f) => `<option value="${esc(f.id)}" ${f.problems.length || !fits(f) ? 'class="bad"' : ""}>${esc(f.name)} · ${f.lines} lines${slicedFrom(f)}${f.uploaded_at ? ` · kept ${stamp(f.uploaded_at)}` : ""}${fits(f) ? "" : ` · kept for a ${esc(f.machine)}`}${f.problems.length ? " · refused: " + esc(f.problems[0]) : ""}</option>`).join("")
            : '<option value="">— no files kept —</option>';
        const stays = had && prt.files.some((f) => f.id === had) && !(own && madeForAnother(had))
            && (!madeForAnother(had) || prt.picked === had);
        sel.value = stays ? had : own ? own.id : "";
        fileOfThePart();
        renderPrint();
    }
    // A file made of another part than the one under makes (madeFrom); a file kept by
    // Choose File says nothing of what it makes.
    const ofAnother = (f, part) => { const of = madeFrom(f && f.id); return !!(part && of.length && !of.includes(part)); };
    // The file chosen follows the part under makes: one made of another part gives way
    // to the newest of this machine's kind made of this one, or to none, which says
    // Slice (or Toolpath) makes one. A file chosen by a person stays, and ▶ says why not.
    function fileOfThePart() {
        const sel = $("print-pick"), part = $("print-part").value;
        const chosen = prt.files.find((f) => f.id === sel.value);
        if (!part || !chosen || !ofAnother(chosen, part) || prt.picked === chosen.id) return;
        const mine = prt.files.find((f) => fits(f) && madeFrom(f.id).includes(part));
        if (mine) { sel.value = mine.id; return; }
        let none = sel.querySelector('option[value=""]');
        if (!none) { none = document.createElement("option"); none.value = ""; sel.prepend(none); }
        none.textContent = `— none of ${part} kept: ${words().prepare || "Slice"} makes one —`;
        sel.value = "";
    }
    // A kept file says the kind of machine it was kept for (Choose File keeps it for
    // the Machine's kind, a slice for a printer, a toolpath for a router), and is sent
    // to that kind alone: a printer's on a router homes it and waits out its
    // millisecond dwells as seconds.
    const fits = (f) => !!f && f.machine === state.kind;
    function madeForAnother(id) {
        const f = prt.files.find((x) => x.id === id);
        return !!f && !fits(f);
    }
    async function loadPrintJobs() {
        if (!state.port || !isGcode()) { prt.jobs = []; renderPrint(); return; }
        try { prt.jobs = await api(`/jobs?kind=${jobKind()}&machine=${encodeURIComponent(state.port)}`); } catch (e) { prt.jobs = []; }
        renderPrint();
    }
    // The parts a print here can name, when the printer is pinned in a site: the
    // site's pieces, then every part of the apothecary that stands nowhere in it, by
    // its name, each group under its own heading.
    // Asked again by the world whenever its site changes in place (a piece made,
    // rebuilt or dropped), so a Machine left open lists the piece made meanwhile;
    // what was chosen stays chosen while it is still there.
    async function loadChoices() {
        const sel = $("print-part"), port = state.port;
        let c = null;
        if (port && isGcode()) { try { c = await api(`/jobs/choices?machine=${encodeURIComponent(port)}`); } catch (e) { c = null; } }
        else if (planning()) {
            // The machine's node answers in the same shape, with where it stands.
            try { c = await api(machinePath()); } catch (e) { c = null; }
            if (c && c.where && c.where.frame) { level.volume = c.where.frame.volume; level.frame = c.where.frame; }
        }
        if (port !== state.port) return;  // another port was chosen meanwhile
        prt.choices = c;
        const parts = (c && c.site && c.parts) || [];
        // What is chosen now, read once the list is back: a choice made (or asked
        // for) while an earlier list was on its way is not undone by its arrival.
        const had = prt.wanted || sel.value;
        if (prt.wanted && parts.some((p) => p.path === prt.wanted)) prt.wanted = null;
        const options = (list) => list.map((p) => `<option value="${esc(p.path)}">${esc(p.path)}${p.name !== p.path ? " · " + esc(p.name) : ""}</option>`).join("");
        const group = (label, list) => (list.length ? `<optgroup label="${esc(label)}">${options(list)}</optgroup>` : "");
        sel.innerHTML = c && c.site
            ? '<option value="">— no part named —</option>'
                + group(`in ${c.site}`, parts.filter((p) => !p.registered))
                + group("every part of the apothecary", parts.filter((p) => p.registered))
            : '<option value="">— pinned in no site —</option>';
        sel.disabled = !(c && c.site);
        if (had && parts.some((p) => p.path === had)) sel.value = had;
        $("print-where").textContent = c && c.site ? `in ${c.site}` : "";
    }
    // A made piece's Print, from its ring: the site's parts listed again and that
    // piece chosen under makes, the card in view. True when it is among them.
    async function choosePart(path) {
        prt.wanted = path;
        await loadChoices();
        prt.wanted = null;
        prt.picked = null;
        fileOfThePart();
        renderPrint();
        $("print-card").scrollIntoView({ block: "nearest" });
        return $("print-part").value === path;
    }
    // --- the machine's plan ------------------------------------------------------------
    // What it makes and the file that makes it, kept for the machine's node
    // (apothecary/machine_plans.py), from its Machine opened with its board or without.
    // Chosen once when the Machine opens -- a plan for another kind of machine than the
    // board is, never -- unless a person chose another meanwhile.
    const pl = { plan: null, applied: false };
    const machinePath = () => `/sites/${encodeURIComponent(machineAt.site)}/machines/${encodeURIComponent(machineAt.path)}`;
    async function loadChoicesAndFiles() {
        await Promise.all([loadChoices(), loadPrintFiles()]);
        await loadPlan();
    }
    async function loadPlan() {
        if (!machineAt) { renderPlan(); return; }
        let r = null;
        try { r = await api(machinePath()); } catch (e) { r = null; }
        pl.plan = (r && r.plan) || null;
        if (pl.plan && !pl.applied && pl.plan.kind === state.kind) {
            pl.applied = true;
            if (pl.plan.part && !$("print-part").value) await choosePart(pl.plan.part);
            if (pl.plan.file_id && prt.files.some((f) => f.id === pl.plan.file_id)) { $("print-pick").value = pl.plan.file_id; renderPrint(); }
        }
        renderPlan();
    }
    // Keep as plan is there once there is something chosen to keep, and a kept plan is
    // said; a Machine that stands for no machine's node has no plan, and no row.
    function renderPlan() {
        const said = $("print-plan-said"), button = $("print-plan");
        const p = machineAt ? pl.plan : null;
        button.hidden = !machineAt || (!$("print-part").value && !$("print-pick").value);
        const file = p && p.file_id ? (prt.files.find((f) => f.id === p.file_id) || { name: p.file_id }).name : null;
        said.textContent = p ? `Kept ${stamp(p.planned_at)}: ${p.part || "no part named"}, ${file || "no file"}` : "";
        $("print-plan-row").hidden = button.hidden && !p;
    }
    async function keepPlan() {
        if (!machineAt) { refuse("plan: this Machine stands for no machine's node"); return false; }
        const part = $("print-part").value || null, fileId = $("print-pick").value || null;
        const file = prt.files.find((f) => f.id === fileId);
        try { pl.plan = await api(`${machinePath()}/plan`, { method: "PUT", body: JSON.stringify({ part, file_id: fileId }) }); }
        catch (e) { refuse(`plan: ${e.message}`); return false; }
        renderPlan();
        tell(`${machineAt.path}'s plan kept: ${part || "no part named"}, ${file ? file.name : "no file"}; its Machine chooses them whenever it opens` + (state.port ? "" : `, and ${words().start} is its board's once it is connected`));
        return true;
    }
    $("print-plan").onclick = keepPlan;

    // --- slicing what makes names, for this printer ---------------------------------
    // Whether a slicer is installed: asked once a printer is shown, and again before
    // a slice, so one installed meanwhile from the Bench is found.
    async function loadSlicer() {
        let s = null;
        try { s = await api("/slicer/status"); } catch (e) { s = null; }
        const chosen = s && (s.slicers || []).find((m) => m.id === s.chosen);
        slc.status = {
            ok: !!(chosen && chosen.tool && chosen.tool.ok && !(chosen.problems || []).length),
            label: chosen ? chosen.label : "the slicer",
            why: chosen ? (chosen.problems || [])[0] || "" : "the slicer cannot be asked",
        };
        renderPrint();
        return slc.status;
    }
    function sliceTasks() {
        if (!slc.tasks) slc.tasks = mountTasks($("print-slice-task"), { base: BASE, history: false, say: (text, kind) => (kind === "error" ? refuse(text) : logLine("sys", text)) });
        return slc.tasks;
    }
    // Slice: what makes names, sliced for this printer by the slicer's task, its log
    // in the card with Cancel. `variant`, when given, is the variant to slice (null for
    // the part as saved) in place of the one the page draws. True when it started.
    async function startSlice(variant = undefined) {
        if (!words().slice) return startToolpath(variant);
        const part = $("print-part").value;
        if (!state.port && !planning()) { refuse("slice: no printer chosen"); return false; }
        if (!part) { refuse("slice: choose what it makes under makes first"); return false; }
        if (slc.running) { refuse("slice: one is running; its log is in its Print window"); return false; }
        const status = await loadSlicer();
        if (!status.ok) { refuse(`slice: no slicer here (${status.why}); Panels › Tools › Bench › Install › OrcaSlicer installs it`); return false; }
        slc.running = true; renderPrint();
        // A part the page draws from a variant it applied is sliced as drawn: that
        // variant's STL, which the slice's record names (variantFor, the page's).
        if (variant === undefined) variant = variantFor ? variantFor(part) : null;
        let task;
        const at = state.port ? { port: state.port } : { site: machineAt.site, printer: machineAt.path };
        const levelling = $("print-level").value || null;
        const adhesion = $("print-adhesion").value || null;
        const body = { ...at, part, ...(variant ? { variant } : {}), ...(levelling ? { levelling } : {}), ...(adhesion ? { adhesion } : {}) };
        try { task = await post("/slicer/slice", body); }
        catch (e) { slc.running = false; renderPrint(); refuse(`slice: ${e.message}`); return false; }
        $("print-slice-box").hidden = false;
        $("print-slice-task").hidden = false;
        $("print-slice-said").innerHTML = "";
        const ending = sliceTasks().start(async () => task, "/slicer/tasks");
        const levelled = [levelling ? $("print-level") : null, adhesion ? $("print-adhesion") : null]
            .filter(Boolean).map((el) => `, ${el.selectedOptions[0].textContent.split(":")[0]}`).join("");
        tell(`slicing ${part}${variant ? ", the variant drawn," : ""} for ${printerName()}${levelled}: its log is in its Print window, and its G-code is chosen there when it ends`);
        $("print-card").scrollIntoView({ block: "nearest" });
        ending.then(sliced);
        return true;
    }
    // The rows' first choice said as what it comes to for the part under makes on this
    // printer: the part's own where it declares one, else the printer's (GET
    // /slicer/first-layer), asked once each time the part or the printer changes.
    async function sayTheOwn(part) {
        const at = state.port ? { port: state.port } : machineAt ? { site: machineAt.site, printer: machineAt.path } : null;
        const key = part && at ? JSON.stringify([part, at]) : null;
        if (key === prt.ownFor) return;
        prt.ownFor = key;
        prt.offset = null;  // another printer's, until this one's is asked
        let resolved = null;
        if (key) {
            try { resolved = await api(`/slicer/first-layer?${new URLSearchParams({ part, ...at })}`); } catch (e) { resolved = null; }
        }
        if (prt.ownFor !== key) return;  // another part or printer since
        for (const [id, row, choices] of [["print-level", "levelling", LEVELLING], ["print-adhesion", "adhesion", ADHESION]]) {
            $(id).options[0].textContent = own(row, resolved) || firstLayerWords(choices[0]);
        }
        prt.offset = (resolved && resolved.offset) || null;
        renderOffset(true);
        renderPrint();
    }
    // The first-layer offset: how far the printer's nozzle stands on the first layer from
    // where its probe puts it, kept for the printer (slicer/first_layer_offset.py) and
    // taken by every slice made for it after. GET /slicer/first-layer says it with the
    // rows' first choices; choosing one keeps it.
    function renderOffset(force) {
        const o = prt.offset, sel = $("print-offset");
        // A Machine gone has no row: an answer that lands after it draws nothing.
        if (!o || !o.named || !sel) return;
        // Drawn again only when what it offers changed, and never while a person has it.
        if (force || document.activeElement !== sel) {
            const html = offsetOptions(o.choices, o.value);
            if (prt.offsetDrawn !== html) { sel.innerHTML = html; prt.offsetDrawn = html; }
            sel.value = String(o.value);
        }
        $("print-offset-said").textContent = o.kept
            ? `kept ${o.kept.at.slice(0, 16).replace("T", " ")} UTC${o.kept.note ? ` (${o.kept.note})` : ""}`
            : "none kept yet";
    }
    async function keepOffset() {
        const at = printerAt();
        if (!at) { refuse("first layer: this printer stands in no site"); renderOffset(true); return false; }
        const offset = Number($("print-offset").value);
        let kept;
        try { kept = await post("/slicer/first-layer/offset", { ...at, offset }); }
        catch (e) { refuse(`first layer: ${e.message}`); renderOffset(true); return false; }
        prt.offset = kept;
        renderOffset(true);
        tell(`${at.printer}'s first layer: the nozzle ${kept.words}; its next slices are made with it`);
        return true;
    }
    // The ring's First layer: the next of the row's offsets, kept.
    function stepOffset() {
        const el = $("print-offset");
        if (!prt.offset || !prt.offset.named || !el.options.length) {
            refuse("first layer: choose what this printer makes under makes first; a printer whose profile keeps no first-layer offset has none");
            return false;
        }
        el.selectedIndex = (el.selectedIndex + 1) % el.options.length;
        return keepOffset();
    }
    $("print-offset").onchange = () => keepOffset();
    $("print-offset").addEventListener("blur", () => renderOffset());
    // Toolpath: what makes names, its cuts written for this router (POST /cam/cut),
    // the file kept and chosen, what it holds said under makes. True when it was kept.
    async function startToolpath(variant = undefined) {
        const part = $("print-part").value;
        if (!state.port && !planning()) { refuse("toolpath: no router chosen"); return false; }
        if (!part) { refuse("toolpath: choose what it makes under makes first"); return false; }
        if (variant === undefined) variant = variantFor ? variantFor(part) : null;
        const site = prt.choices && prt.choices.site, at = prt.choices && prt.choices.machine && prt.choices.machine.path;
        let r;
        try { r = await post("/cam/cut", { port: state.port || undefined, part, site: site || undefined, router: at || undefined, variant: variant || undefined }); }
        catch (e) { refuse(`toolpath: ${e.message}`); return false; }
        await loadPrintFiles(r.file_id);
        $("print-slice-box").hidden = false;
        $("print-slice-task").hidden = true;
        $("print-slice-said").innerHTML = toolpathSaid(r);
        const cut = r.operations.filter((o) => o.cut).length;
        // A toolpath that names what to measure says so: the piece it cuts is measured in
        // its part's cabinet, which opens on it at the cut's end.
        const named = (r.features || []).map((f) => f.name);
        const measure = named.length ? `, then measure its ${named.length > 1 ? `${named.slice(0, -1).join(", ")} and ${named[named.length - 1]}` : named[0]} across, under measured in Part › Feedback` : "";
        tell(`${r.name} kept and chosen: the toolpath of ${r.part}${r.variant ? `, the variant drawn (${r.variant.slice(0, 8)})` : ""} for ${r.router.name}, ${cut} of ${r.operations.length} operations, ${r.lines} lines, ${span(r.time_s)} at the feeds written${r.messages.length ? `; ${r.messages.length} said` : ""}; ▶ Cut cuts it${measure}`);
        $("print-card").scrollIntoView({ block: "nearest" });
        emit("apothecary:sliced", { port: state.port, file_id: r.file_id });
        return true;
    }
    // What a toolpath holds: its tool, stock and feeds, each operation with its
    // passes, and what it left out or changed, and why.
    function toolpathSaid(r) {
        const head = `<div class="slice-head">${esc(r.part)}${r.variant ? ` (the variant ${esc(r.variant.slice(0, 8))})` : ""} toolpath for ${esc(r.router.name)} · ${esc(String(r.lines))} lines · ${esc(span(r.time_s))} · ${esc(mmText(r.length_mm))} cut</div>`;
        const rows = [
            ["tool", `${r.tool.label}`], ["stock", `${r.stock.x} x ${r.stock.y} x ${r.stock.thickness} mm, zero at its front-left top corner`],
            ["feeds", `cut ${r.feeds.cut}, plunge ${r.feeds.plunge} mm/min, ${r.feeds.rpm} rpm`],
            ...r.operations.map((o) => [`op ${o.index}`, `${o.words}${o.cut ? ` · ${o.passes} pass${o.passes === 1 ? "" : "es"}` : " · not cut"}`]),
            // What a person measures of the piece, as designed: Part › Feedback's measured.
            ...((r.features || []).length ? [["measure", r.features.map((f) => f.words).join("; ")]] : []),
        ].map(([k, v]) => `<div class="declared"><span>${esc(k)}</span> <span>${esc(v)}</span> <span class="meta">part</span></div>`).join("")
            // The router's allowance every offset took, and the measurement it came from.
            + (r.allowance ? `<div title="${esc(r.allowance.source)}"><span>tool_allowance</span> <span>${esc(signed(r.allowance.value))}</span> <span class="meta">${esc(r.allowance.origin)}</span></div>` : "");
        const said = r.messages.map((m) => `<div class="warn">${esc(m)}</div>`).join("");
        return head + `<div class="slice-settings">${rows}</div>` + said;
    }
    // The printer, as its site names it: the node above the board its port is pinned to.
    function printerName() {
        const path = prt.choices && prt.choices.machine && prt.choices.machine.path;
        const parts = (path || "").split(".");
        return parts[0] || state.port;
    }
    // A slice ended: its file chosen and what it used said; or why it did not.
    async function sliced(task) {
        slc.running = false;
        const answer = task && task.slice;
        if (task && task.status === "succeeded" && answer && answer.ok) {
            const r = answer.record;
            await loadPrintFiles(r.file_id);
            $("print-slice-task").hidden = true;
            $("print-slice-said").innerHTML = sliceSaid(r);
            tell(`${r.name} kept and chosen: sliced from ${r.made.name}${r.made.variant ? `, the variant drawn (${r.made.variant.slice(0, 8)})` : ""} for ${r.printer.name}${estimateWords(r.estimate) ? `, ${estimateWords(r.estimate)}` : ""}; ▶ Print prints it`);
            emit("apothecary:sliced", { port: state.port, file_id: r.file_id });
        } else if (task && task.status === "cancelled") {
            $("print-slice-said").innerHTML = '<div class="meta">The slice was cancelled; nothing was kept.</div>';
            tell("slice cancelled: nothing was kept");
        } else if (task) {
            const why = (answer && answer.error) || `the slice ${task.status}`;
            $("print-slice-said").innerHTML = `<div class="bad">${esc(why)}</div>` + messagesSaid((answer && answer.messages) || []);
            refuse(`slice: ${why}`);
        }
        renderPrint();
    }
    function estimateWords(e) {
        if (!e) return "";
        return [e.time, e.filament_g != null ? `${e.filament_g} g of filament` : null, e.layers != null ? `${e.layers} layers` : null].filter(Boolean).join(", ");
    }
    // What a slice used, each value with where it came from -- the part's own in
    // bold -- the slicer's estimate, and its errors and warnings by line.
    function sliceSaid(r) {
        const est = estimateWords(r.estimate);
        const head = `<div class="slice-head">${esc(r.made.name)}${r.made.variant ? ` (the variant ${esc(r.made.variant.slice(0, 8))})` : ""} sliced for ${esc(r.printer.name)} by ${esc(r.slicer_label || r.slicer)} ${esc(r.slicer_version || "")}${est ? ` · ${esc(est)}` : ""}</div>`;
        const value = (v) => esc(Array.isArray(v) ? v.join(", ") : v == null ? "–" : String(v));
        const rows = r.settings.map((s) => `<div class="${s.origin === "declared" ? "declared" : ""}" title="${esc(s.source + (s.note ? " — " + s.note : ""))}"><span>${esc(s.name)}</span> <span>${value(s.value)}</span> <span class="meta">${esc(s.origin)}</span></div>`).join("");
        return head + `<div class="slice-settings">${rows}</div>` + messagesSaid(r.messages || []);
    }
    function messagesSaid(messages) {
        return messages.map((m) => `<div class="${m.level === "error" ? "bad" : "warn"}">${m.line ? `line ${m.line}: ` : ""}${esc(m.text)}</div>`).join("");
    }
    // The ring's Slice on a piece or a part, and the page's Make: chosen under makes,
    // then sliced -- as `variant` where one is given (startSlice).
    // The Print cell's Levelling and Adhesion: the next of that row's choices, told.
    function stepRow(id, what) {
        const el = $(id);
        el.selectedIndex = (el.selectedIndex + 1) % el.options.length;
        renderPrint();
        tell(`${what} of the next slices: ${el.selectedOptions[0].textContent}`);
    }
    // `levelling` and `adhesion`, when given, are chosen in the Print window's rows for this
    // slice and the ones after it ("" the part's own: what it declares, else the profile's).
    async function slicePart(path, variant = undefined, { levelling = undefined, adhesion = undefined } = {}) {
        if (!(await choosePart(path))) return { refused: `${path} is not among the parts this printer's Print window can make` };
        if (levelling !== undefined) $("print-level").value = levelling || "";
        if (adhesion !== undefined) $("print-adhesion").value = adhesion || "";
        const before = refusals;
        const started = await startSlice(variant);
        if (!started) return { refused: refusals > before ? lastRefusal : `${path} could not be sliced` };
        return { said: lastTold };
    }

    // How a print that ran here ended, in the host's status bar: done or cancelled
    // as said, failed as an error with its reason.
    function toldEnded(job) {
        const what = `${job.name} on ${state.port}${job.part ? `, making ${job.part}` : ""}`;
        // Done or not, the page is told: a piece's drawer opens in Part › Feedback, and a
        // print that stopped says there where, and what to try.
        const next = afterPrint ? afterPrint(job) : null;
        if (job.stage === "failed") { if (say) say(`${what}, failed: ${job.error || "no reason was given"}${next ? `; ${next}` : ""}`, "error"); return; }
        tell(`${what}, ended: ${job.stage}, ${job.sent}/${job.total} lines${next ? `; ${next}` : ""}`);
    }
    // A print followed until it ends; its end is told (the printer's jobs, the site's,
    // and a poll for the state it left), a print that was not running is only drawn.
    async function watchPrint() {
        clearTimeout(prt.timer); prt.timer = null;
        if (!state.port || !isGcode()) return;
        try {
            const was = !!(prt.job && prt.job.running);
            prt.job = await api(`/firmware/printers/print?port=${encodeURIComponent(state.port)}`);
            renderPrint();
            if (prt.job.running) { prt.timer = setTimeout(watchPrint, 1000); return; }
            if (!was) return;
            toldEnded(prt.job);
            await loadPrintJobs();
            emit("apothecary:jobs-changed", { port: state.port, job_id: prt.job.job_id });
            await pollNow();
        } catch (e) { $("print-job").textContent = e.message; }
    }
    async function keepPrintFile(file) {
        if (!file) return;
        try {
            // Kept for this Machine's kind of machine: checked in its terms, sent to it alone.
            if (!isGcode()) throw new Error("a file is kept for a printer or a router, and this board drives neither");
            const r = await fetch(`${BASE}/firmware/printers/prints?name=${encodeURIComponent(file.name)}&machine=${encodeURIComponent(state.kind)}`, { method: "POST", body: file, headers: { "Content-Type": "text/plain" } });
            const body = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(body.detail || r.statusText);
            logLine("sys", `kept ${body.name}: ${body.lines} lines, for a ${body.machine}` + (body.problems.length ? ` -- refused: ${body.problems.join("; ")}` : ""));
            await loadPrintFiles(body.id);
        } catch (e) { refuse("keep file: " + e.message); }
        $("print-file").value = "";
    }
    async function startPrint() {
        const fileId = $("print-pick").value;
        const w = words();
        if (!state.port || !fileId) { refuse(`${w.job}: pick a port and a file first`); return; }
        if (!ctl.armed) { refuse(`a ${w.job} ${w.can.replace(" and ", "s and ")}s the machine: arm control first`); return; }
        const f = prt.files.find((x) => x.id === fileId);
        const part = $("print-part").value || null;
        if (!confirm(`${w.verb} ${f ? f.name : fileId} on ${state.port}${part ? `, making ${part}` : ""}?\n${f ? f.lines + " lines" : ""} will stream from here; the ${state.kind} will ${w.can}.`)) return;
        try {
            prt.job = await post("/firmware/printers/print", { port: state.port, file_id: fileId, part });
            tell(`started ${f ? f.name : fileId} on ${state.port}${part ? `, making ${part}` : ""}: its ${w.verb} window follows it to its end, and Site's Jobs lists it`);
            renderPrint();
            prt.timer = setTimeout(watchPrint, 800);
            forgetRefusal();
            await loadPrintJobs();
            emit("apothecary:jobs-changed", { port: state.port, job_id: prt.job.job_id });
        } catch (e) { refuse(`${w.job}: ` + e.message); $("print-job").textContent = e.message; }
    }
    // Cancel cannot be undone: its button is pressed twice; the ring's asked twice already.
    async function printVerb(verb, button = null) {
        if (!state.port) return;
        const w = words();
        const said = { pause: w.pauseWord, resume: "Resume", cancel: "Abort" }[verb] || verb;
        if (verb === "cancel" && !again(button, "abort")) { tell(`press again to abort the ${w.job} from here: ${w.job === "cut" ? "the controller is held and reset, the spindle off" : "heaters and fan go off, motors free"}`); return; }
        try { prt.job = await post(`/firmware/printers/print/${verb}`, { port: state.port }); renderPrint(); if (!prt.timer) prt.timer = setTimeout(watchPrint, 500); }
        catch (e) { refuse(`${said} the ${w.job}: ` + e.message); return; }
        forgetRefusal(`${said}: the ${w.job} from here is ${{ pause: "paused", resume: "going on", cancel: "aborted" }[verb]}`);
    }
    $("print-file").addEventListener("change", (ev) => keepPrintFile(ev.target.files[0]));
    $("print-pick").addEventListener("change", () => { renderPrint(); prt.picked = $("print-pick").value; });
    $("print-preview").addEventListener("input", () => {
        if (previewOn() && !pv.data) loadPreview(); else renderPreview();
    });
    $("print-delete").onclick = async () => {
        const id = $("print-pick").value; if (!id) return;
        try { await api(`/firmware/printers/prints/${encodeURIComponent(id)}`, { method: "DELETE" }); await loadPrintFiles(); }
        catch (e) { refuse("forget file: " + e.message); }
    };
    $("print-start").onclick = startPrint;
    $("print-slice").onclick = () => startSlice();
    $("print-part").onchange = () => { prt.picked = null; fileOfThePart(); renderPrint(); };
    $("print-pause").onclick = () => printVerb("pause");
    $("print-resume").onclick = () => printVerb("resume");
    $("print-cancel").onclick = () => printVerb("cancel", $("print-cancel"));

    // --- flashing a devkit: the Bench's form and task log, for this port --------------
    // Mounted the first time the board is shown as a devkit. The sketch it starts
    // from is the one it should run: the last one flashed to it from here, else the
    // one its node is bound to it by. An upload that succeeds is followed by what the
    // board should run, read again, and Identify's listen for its hello.
    let flash = null;
    const flashSay = (text, kind) => (kind === "error" ? refuse(text) : logLine("sys", text));
    function mountFlashing() {
        if (flash || !state.port) return;
        const port = state.port;
        const tasks = mountTasks($("flash-task"), { base: BASE, history: false, say: flashSay });
        const build = mountBuild($("flash-form"), {
            base: BASE, tasks, port, say: flashSay,
            // By its id: the Rust esp32_blink when that is what was flashed here.
            suggest: () => {
                const e = b().expected;
                return (e && e.record && (e.record.sketch_id || e.record.sketch)) || (pin && pin.sketch) || null;
            },
            onEnd: (task, what) => flashed(port, task, what),
        });
        flash = { port, build, tasks };
        build.load();
    }
    async function flashed(port, task, what) {
        if (state.port !== port) return;
        logLine("sys", `${what.kind === "upload" ? "upload" : "compile"} of ${what.label || `${what.sketch} (${what.fqbn})`}: ${task.status}`);
        if (what.kind !== "upload" || task.status !== "succeeded") return;
        await model.loadInfo(port).catch(() => {});
        renderDevkit();
        await identify({ pressed: false });
    }
    // Device › Flash: the card in view, its sketch under the cursor.
    function showFlashing() {
        if (!state.port) return;
        if (state.kind !== "devkit" || inPrinter) { refuse(`Flash: a ${isGcode() ? state.kind : "printer"} keeps its own firmware; Apothecary polls it and never flashes it`); return; }
        mountFlashing();
        $("flash-card").scrollIntoView({ block: "nearest" });
        const pick = $("flash-form").querySelector(".sketch-select");
        if (pick) pick.focus({ preventScroll: true });
    }

    // --- the ring's side: what this board knows, and carrying a chosen verb ------------
    // `can` is what the server would refuse of the port now, with what this page knows
    // over it: the answer the buttons are greyed from, which greys the ring's acts too
    // (menu.py CAN_VERBS).
    function device() {
        const d = state.port ? b().device : null;
        return { port: state.port, printer: !!(d && d.printer), machine: d && d.printer ? d.printer.machine || "printer" : null, armed: ctl.armed, bound: !!(pin && pin.how === "manual"), can: state.port ? localCan() : null };
    }
    // A verb of this board's: false when it is not one (the host's: open, pin, unpin);
    // else { refused, said }: the refusal it met, and what it told, or null.
    async function carry(intent) {
        const before = refusals, toldBefore = told;
        const done = await carryOut(intent);
        if (!done) return false;
        return {
            refused: refusals > before ? lastRefusal : null,
            said: told > toldBefore ? lastTold : null,
        };
    }
    async function carryOut(intent) {
        const action = intent.action;
        const jogM = /^control:jog:([XYZ])([+-])$/.exec(action);
        const printerVerb = /^(control|level|print):/.test(action);
        if (printerVerb && !isGcode()) { refuse(`${viaRing(intent.label, intent.address)}: a devkit has no G-code to be driven with`); return true; }
        if (/^level:/.test(action) && state.kind === "router") { refuse(`${viaRing(intent.label, intent.address)}: a router has no bed to level`); return true; }
        if (jogM) {
            if (!ctl.armed) { refuse(`${viaRing(intent.label, intent.address)}: control is not armed`); return true; }
            jog(jogM[1], jogM[2]); return true;
        }
        if (action === "control:estop") { await estop(); return true; }
        if (action === "control:arm") { await arm(true); return true; }
        if (action === "control:disarm") { await arm(false); return true; }
        const corner = /^control:corner:([FB][LR])$/.exec(action);
        if (corner) {
            if (!ctl.armed) { refuse(`${viaRing(intent.label, intent.address)}: a corner move needs control armed`); return true; }
            const lines = cornerLines(corner[1]);
            if (!lines) { refuse(`${viaRing(intent.label, intent.address)}: ${NO_CORNERS}`); return true; }
            enqueue(lines, undefined, `${intent.label} corner`);
            return true;
        }
        if (action === "level:probe") { await startLevel(true); return true; }
        if (action === "level:read") { await startLevel(false); return true; }
        if (action === "print:start") { await startPrint(); return true; }
        if (action === "print:preview") { togglePreview(); return true; }
        if (action === "print:plan") return keepPlan();
        if (action === "print:level") { stepRow("print-level", "levelling"); return true; }
        if (action === "print:adhesion") { stepRow("print-adhesion", "adhesion"); return true; }
        if (action === "print:offset") return stepOffset();
        if (prt.job && prt.job.running && action in HOST_VERBS) { await printVerb(HOST_VERBS[action]); return true; }
        const lines = LINES_OF();
        if (action in lines) {
            // What the server takes with the latch down -- an off, an interrupt -- goes
            // disarmed, as its button would and its cell on the ring is not greyed.
            if (!ctl.armed && NEEDS_THE_LATCH.includes(verbOfLine(CMD_OF[action] || ""))) { refuse(`${viaRing(intent.label, intent.address)}: control is not armed`); return true; }
            await sendControl(lines[action](handle), undefined, intent.label);
            return true;
        }
        // A devkit is not polled: Poll reads again what it should run and what it is.
        if (action === "device:poll") {
            if (state.kind === "devkit") { await model.loadInfo(state.port).catch((e) => refuse(`poll: ${e.message}`)); renderDevkit(); return true; }
            await $("poll").onclick(); return true;
        }
        if (action === "device:query") { await identify(); return true; }
        if (action === "device:listen") { listen(); return true; }
        if (action === "device:probe") { await probe(); return true; }
        if (action === "device:flash") { showFlashing(); return true; }
        if (action === "device:rescan") { await model.rescan(); logLine("sys", "ports rescanned"); return true; }
        // The link verbs are the header buttons; their handlers already confirm what needs confirming.
        if (action === "device:reconnect") { await $("reconnect").onclick(); return true; }
        if (action === "device:reset") { await reboot(); return true; }
        if (action === "device:release") { await $("release").onclick(); return true; }
        return false;  // not this board's: the host decides (open, pin, unpin)
    }
    // The buttons this machine has, each by the verb it is -- for the ring's addresses.
    function pairs() {
        const out = [];
        for (const btn of $("control").querySelectorAll("button[data-cmd]")) out.push([btn, BY_CMD[btn.dataset.cmd] || null]);
        for (const btn of $("control").querySelectorAll("button[data-jog]")) out.push([btn, `control:jog:${btn.dataset.jog}`]);
        out.push([$("ctl"), ctl.armed ? "control:disarm" : "control:arm"]);
        out.push([$("ctl-label"), ctl.armed ? "control:disarm" : "control:arm"]);
        out.push([$("ctl-disarm"), "control:disarm"]);
        out.push([$("estop"), "control:estop"]);
        out.push([$("pad-estop"), "control:estop"]);
        out.push([$("poll"), "device:poll"]);
        out.push([$("identify"), "device:query"]);
        out.push([$("reconnect"), "device:reconnect"]);
        out.push([$("reset"), "device:reset"]);
        out.push([$("release"), "device:release"]);
        out.push([$("listen"), "device:listen"]);
        out.push([$("probe"), "device:probe"]);
        out.push([$("level-probe"), "level:probe"]);
        out.push([$("level-read"), "level:read"]);
        for (const btn of $("level-card").querySelectorAll("button[data-corner]")) out.push([btn, `control:corner:${btn.dataset.corner}`]);
        out.push([$("print-start"), "print:start"]);
        out.push([$("print-preview"), "print:preview"]);
        out.push([$("print-plan"), "print:plan"]);
        out.push([$("print-level"), "print:level"]);
        out.push([$("print-adhesion"), "print:adhesion"]);
        out.push([$("print-offset"), "print:offset"]);
        out.push([$("print-pause"), "control:sd-pause"]);
        out.push([$("print-resume"), "control:sd-resume"]);
        out.push([$("print-cancel"), "control:sd-abort"]);
        return out;
    }

    // A button pressed is its ring verb pressed: the host told, so it opens the sections
    // that verb acts on as the ring's cell does (Poll opens Status, Listen the Log).
    if (onVerb) {
        for (const [btn, action] of pairs()) {
            if (btn && action && !/^control:(arm|disarm)$/.test(action)) btn.addEventListener("click", () => onVerb(action));
        }
    }

    const handle = {
        root, host, $, boards: model,
        state, ctl, arm, jog, estop, enqueue, sendControl, fillTemplate, pollOnce: pollNow, logLine, refuse, schedule, selectPort,
        identify, listen, probe, showFlashing,
        flashing: () => flash,
        kind: () => state.kind,
        device, carry, pairs, pad: togglePad, padBack,
        level: { start: startLevel, hot: (heat, soak) => startLevel(true, { heat, soak }), corner: (which) => { const lines = cornerLines(which); return lines ? enqueue(lines) : refuse(NO_CORNERS); }, lines: cornerLines, records: () => level.records, shown: () => level.shown, load: loadLevel },
        print: { start: startPrint, verb: printVerb, keep: keepPrintFile, job: () => prt.job, files: () => prt.files, jobs: () => prt.jobs, choices: () => prt.choices, load: loadPrintFiles, loadJobs: loadPrintJobs, loadChoices, choose: choosePart, slice: slicePart, bedTemperature, fileOf: chooseFileOf, slices: () => prt.slices, slicing: () => slc.running, show: showPreview },
        plan: { keep: keepPlan, load: loadPlan, shown: () => pl.plan, planning },
        destroy() {
            if (state.port || machineAt) emit("apothecary:toolpath", { port: state.port, path: machineAt ? machineAt.path : null, preview: null, upto: 0, origin: null });
            if (state.port) model.unwatch(state.port, who);
            clearTimeout(level.timer); clearTimeout(prt.timer); clearInterval(ctl.timer); clearInterval(knob.timer); clearInterval(ageTimer);
            clearTimeout(miss.timer); miss.asked++;
            if (flash) { flash.build.destroy(); flash.tasks.destroy(); flash = null; }
            if (slc.tasks) { slc.tasks.destroy(); slc.tasks = null; }
            for (const [event, fn] of onWindow) window.removeEventListener(event, fn);
            if (!boards) model.destroy();
            if (padIsOut) { padIsOut = false; padWindow.close(pad, false); }
            pad.remove();
            for (const el of [root, ...windows]) {
                el.replaceChildren();
                el.classList.remove("machine", `host-${host}`, "machine-section", "kind-printer", "kind-router", "kind-devkit", "in-printer", "planning", "status-old");
            }
        },
    };

    renderLevel(); renderPrint();
    selectPort(state.port);
    return handle;
}
