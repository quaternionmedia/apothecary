"""static/can.js greys a button the server would refuse, says why in its title, and
puts its own tip back, run under node over a few stand-in elements."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from apothecary.firmware import can, dialects

CAN_JS = Path(__file__).resolve().parents[1] / "apothecary" / "static" / "can.js"

SCRIPT = r"""
import { applyCan, refreshDisabled, setTip, setReason, askFlash, flashVerdict, forgetFlash, withLatch } from %(url)s;
const el = (verb, title) => {
  const attrs = new Map(title === undefined ? [] : [["title", title]]);
  return {
    dataset: { can: verb }, disabled: false,
    getAttribute: (k) => (attrs.has(k) ? attrs.get(k) : null),
    setAttribute: (k, v) => attrs.set(k, String(v)),
    removeAttribute: (k) => attrs.delete(k),
    set title(v) { attrs.set("title", v); }, get title() { return attrs.get("title"); },
    attrs,
  };
};
const buttons = { jog: el("jog", "Move X"), home: el("home.X", "Home X"), stop: el("estop", "Stop"), odd: el("nothing"), };
const root = { querySelectorAll: () => Object.values(buttons) };
const seen = (b) => ({ disabled: b.disabled, aria: b.attrs.get("aria-disabled") || null, title: b.attrs.get("title") || null });
const out = {};
const refused = { ok: false, kind: "armed", why: "/dev/x: control is not armed -- arm it first" };
const can = { jog: refused, home: { ok: true, why: null, kind: null }, estop: refused };
applyCan(root, can);
out.refused = Object.fromEntries(Object.entries(buttons).map(([k, b]) => [k, seen(b)]));
buttons.jog.dataset.busy = "1"; applyCan(root, { jog: { ok: true } });
out.busy_holds_it = seen(buttons.jog);
delete buttons.jog.dataset.busy; refreshDisabled(buttons.jog);
out.restored = seen(buttons.jog);
applyCan(root, can); setTip(buttons.jog, "Move X by the step");
out.tip_while_refused = seen(buttons.jog);
applyCan(root, { jog: { ok: true } });
out.tip_after = seen(buttons.jog);
out.latch = withLatch({ jog: { ok: true }, off: { ok: true }, home: { ok: false, kind: "held", why: "w" } }, false);
out.latch_of = withLatch({ jog: { ok: true } }, false, "/dev/x");
const up = el("upload", "Build it");
up.dataset.address = "932";
setReason(up, "choose a sketch first", "Build it");
out.reason = seen(up);
setReason(up, null, "Build it");
out.reason_gone = seen(up);
const asked = [];
const call = async (path) => { asked.push(path); return { can: { flash: { ok: false, kind: "kind", why: "holds a router's controller" } } }; };
out.first = await askFlash(call, "/dev/x");
out.again = await askFlash(call, "/dev/x");
out.verdict = flashVerdict("/dev/x");
forgetFlash("/dev/x");
out.forgotten = flashVerdict("/dev/x");
out.asked = asked;
const slow = [];
let answer;
const later = (path) => { slow.push(path); return new Promise((done) => { answer = done; }); };
const one = askFlash(later, "/dev/y"), two = askFlash(later, "/dev/y");
answer({ can: { flash: { ok: false, kind: "kind", why: "a printer's controller" } } });
out.together = [await one, await two];
out.together_asked = slow;
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_a_refused_button_is_greyed_with_the_reason_and_its_own_tip_comes_back():
    script = SCRIPT % {"url": json.dumps(CAN_JS.as_uri())}
    run = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    refused = out["refused"]
    why = "/dev/x: control is not armed -- arm it first"
    assert refused["jog"] == {"disabled": True, "aria": "true", "title": f"Disabled: {why}. Move X"}
    # `home.X` has no verdict of its own and takes `home`'s, which is ok.
    assert refused["home"] == {"disabled": False, "aria": None, "title": "Home X"}
    # The stop is never greyed, whatever the answer says; a verb nobody answers is left.
    assert refused["stop"] == {"disabled": False, "aria": None, "title": "Stop"}
    assert refused["odd"] == {"disabled": False, "aria": None, "title": None}
    # A send in flight holds a button the answer allows; letting go enables it.
    assert out["busy_holds_it"] == {"disabled": True, "aria": None, "title": "Move X"}
    assert out["restored"] == {"disabled": False, "aria": None, "title": "Move X"}
    # A tip said anew shows after the reason while refused, and alone once allowed.
    assert out["tip_while_refused"]["title"] == f"Disabled: {why}. Move X by the step"
    assert out["tip_after"]["title"] == "Move X by the step"
    # One helper greys a button for a reason the page knows, keeping the ring's address.
    assert out["reason"] == {
        "disabled": True,
        "aria": "true",
        "title": "Disabled: choose a sketch first. Build it \u00b7 \u2317932",
    }
    assert out["reason_gone"] == {
        "disabled": False,
        "aria": None,
        "title": "Build it \u00b7 \u2317932",
    }
    # `can.flash` of a port is asked once, kept, and asked again after it is forgotten.
    assert out["first"] is True and out["again"] is False
    assert out["verdict"]["kind"] == "kind" and out["forgotten"] is None
    assert out["asked"] == ["/firmware/printers/info?port=%2Fdev%2Fx"]
    # Two asking of one port while it is answered are both given the answer, asked once.
    assert out["together"] == [True, True]
    assert out["together_asked"] == ["/firmware/printers/info?port=%2Fdev%2Fy"]
    # A latch that lapsed refuses what only the latch allowed, and nothing else.
    assert out["latch"]["jog"]["kind"] == "armed" and out["latch"]["off"] == {"ok": True}
    assert out["latch"]["home"] == {"ok": False, "kind": "held", "why": "w"}
    # Said with the port it is told, in the server's own words (firmware/can.py not_armed).
    assert out["latch_of"]["jog"]["why"] == can.not_armed("/dev/x", False)


MACHINE_JS = CAN_JS.parent / "widgets" / "machine.js"


def _alternatives(pattern) -> list:
    """The lines a dialect's ``^(a|b|c)$`` matches, each one."""
    found = re.fullmatch(r"\^\((.*)\)\$", pattern.pattern)
    assert found, pattern.pattern
    return found[1].split("|")


# The verbs the server answers without the latch (firmware/can.py, line_refusal's `off`).
UNLATCHED = {"estop", "off", "interrupt", "quickstop", "card.pause"}


def _kinds(line: str) -> dict:
    """The dialects that take ``line`` (its {...} given a figure), by their machine, with
    the line as each normalises it."""
    found = {}
    for d in dialects.BY_WORD.values():
        try:
            found[d.machine] = (d, d.normalise_control(re.sub(r"\{[^}]+\}", "1", line)))
        except ValueError:
            continue
    return found


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_a_pad_line_is_greyed_as_the_server_answers_for_that_very_line():
    """can.js verbOfLine names each line a pad sends by a command the server answers, and
    the server answers that command from a line of its own (can.LINES): for every pad
    line in machine.js and every line a dialect lists, in each dialect that takes it, the
    line and the server's own go or not alike with the latch down (``always``) and while a
    job streams (``job_allows``). A dialect's stop is the one line never greyed."""
    pad = set(re.findall(r'data-cmd="([^"]+)"', MACHINE_JS.read_text(encoding="utf-8")))
    listed = {line for d in dialects.BY_WORD.values() for line in _alternatives(d.always)}
    lines = sorted(pad | listed | set(dialects.STOPS))
    script = (
        f"import {{ verbOfLine }} from {json.dumps(CAN_JS.as_uri())};\n"
        f"console.log(JSON.stringify(Object.fromEntries({json.dumps(lines)}"
        ".map((l) => [l, verbOfLine(l)]))));"
    )
    run = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr
    verbs = json.loads(run.stdout)
    problems = []
    for line, verb in verbs.items():
        if (line in dialects.STOPS) != (verb == "estop"):
            problems.append(f"{line}: {verb}, and only a dialect's stop is never greyed")
            continue
        for machine, (d, said) in _kinds(line).items():
            if verb == "estop":
                continue
            ours = can.LINES.get(verb, {}).get(machine)
            if ours is None:
                problems.append(f"{line} ({machine}): {verb}, which the server has no line for")
                continue
            ours = d.normalise_control(ours)
            if bool(d.always.match(said)) != (verb in UNLATCHED):
                problems.append(f"{line} ({machine}): {verb}, but the latch says otherwise")
            if bool(d.job_allows.match(said)) != bool(d.job_allows.match(ours)):
                problems.append(f"{line} ({machine}): {verb}, but a job treats it unlike {ours}")
    assert problems == []
    assert verbs["RESUME"] == "resume"


ROOT = CAN_JS.parents[2]


def _verbs_the_server_answers(monkeypatch) -> set:
    """Every command can_now answers, for a printer and for a router."""
    verbs = set()
    for kind in ("printer", "router"):
        facts = can.Facts(
            port="/dev/x",
            task=None,
            armed=True,
            link=None,
            job=None,
            printing=None,
            leveling=None,
            last=None,
            kind=kind,
            firmware=None,
        )
        monkeypatch.setattr(can, "facts_of", lambda *a, _f=facts, **k: _f)
        verbs |= set(can.can_now("/dev/x"))
    return verbs


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_every_verb_the_page_names_is_one_the_server_answers(monkeypatch):
    """A button whose data-can names no verb of can_now is never greyed (verdictOf finds
    nothing and leaves it): each verb machine.js, sketches.js, loops.js and the templates
    write, each can.js gives a pad's line, and each the latch lapsing refuses, is one the
    server answers."""
    answers = _verbs_the_server_answers(monkeypatch)
    pages = [
        MACHINE_JS,
        CAN_JS.parent / "widgets" / "sketches.js",
        CAN_JS.parent / "widgets" / "loops.js",
        *sorted((ROOT / "templates").glob("*.j2")),
    ]
    written = {v for p in pages for v in re.findall(r'data-can="([^"<>]+)"', p.read_text("utf-8"))}
    pad = sorted(set(re.findall(r'data-cmd="([^"]+)"', MACHINE_JS.read_text(encoding="utf-8"))))
    script = (
        f"import {{ verbOfLine, NEEDS_THE_LATCH }} from {json.dumps(CAN_JS.as_uri())};\n"
        f"console.log(JSON.stringify([{json.dumps(pad)}.map(verbOfLine), NEEDS_THE_LATCH]));"
    )
    run = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr
    of_lines, latched = json.loads(run.stdout)
    assert written and of_lines and latched
    for where, verbs in (
        ("data-can", written),
        ("verbOfLine", of_lines),
        ("NEEDS_THE_LATCH", latched),
    ):
        unanswered = sorted(set(verbs) - answers)
        assert not unanswered, f"{where} names {unanswered}, which can_now does not answer"


def _machine_rings():
    """Every ring a machine's acts are on: a printer's, a router's and a devkit's device
    ring, latch down and up."""
    from apothecary.menu import Context, Device, Pointing, resolve

    for device in (
        Device(port="/dev/x", printer=True, bound=True),
        Device(port="/dev/x", printer=True, armed=True),
        Device(port="/dev/x", printer=True, machine="router", bound=True),
        Device(port="/dev/x", printer=True, machine="router", armed=True),
        Device(port="/dev/x", bound=True),
        Device(port="/dev/x"),
    ):
        yield resolve(Context(pointing=Pointing.DEVICE, targets=[device.port]), device=device)


def _acts(options) -> set:
    """Every act among ``options`` and the rings under them."""
    found = set()
    for option in options:
        found |= _acts(option.children) if option.children else {option.action}
    return found


def _named(verb) -> set:
    """The commands an entry of menu.CAN_VERBS names: one, both halves of a ByJob, or none."""
    from apothecary.menu import ByJob

    halves = verb if isinstance(verb, ByJob) else (verb,)
    return {v for v in halves if v}


def test_every_act_on_a_machines_ring_names_a_command_the_server_answers_or_none(monkeypatch):
    """The ring greys an act from the command menu.CAN_VERBS names for it. Every act a
    machine's ring carries has an entry -- a command, or None where nothing the server
    answers stands in its way -- so a new act is not left out of the answer by being
    left out of the table, and each command named is one can_now answers."""
    from apothecary.menu import CAN_VERBS

    answers = _verbs_the_server_answers(monkeypatch)
    acts = set().union(*(_acts(ring.options) for ring in _machine_rings()))
    assert {"control:jog:Y+", "control:job-hold", "device:listen", "print:start"} <= acts
    missing = sorted(acts - set(CAN_VERBS))
    assert not missing, f"no entry in menu.CAN_VERBS for {missing}: name its command, or None"
    stale = sorted(set(CAN_VERBS) - acts)
    assert not stale, f"menu.CAN_VERBS names acts no machine's ring carries: {stale}"
    named = set().union(*(_named(v) for v in CAN_VERBS.values()))
    assert not sorted(named - answers), f"menu.CAN_VERBS names {sorted(named - answers)}"


def _block(text: str, start: str, end: str) -> str:
    at = text.index(start)
    return text[at : text.index(end, at)]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_rings_acts_are_greyed_by_the_commands_the_machines_buttons_are():
    """menu.CAN_VERBS and the Machine name each act by one command: a pad's line by the
    verb verbOfLine names it (BY_CMD, the line's act), a job's verb by the job's command
    (HOST_VERBS), and each button the ring's addresses are written on (pairs()) by its
    data-can -- a button with none, an act with none."""
    from apothecary.menu import CAN_VERBS, ByJob

    text = MACHINE_JS.read_text(encoding="utf-8")
    by_cmd = dict(re.findall(r'"([^"]+)": "(control:[a-z-]+)"', _block(text, "const BY_CMD", "};")))
    host = dict(
        re.findall(r'"(control:[a-z-]+)": "([a-z]+)"', _block(text, "const HOST_VERBS", "};"))
    )
    tags = {}
    for tag in re.findall(r"<button\b[^>]*>", text):
        named = re.search(r'\bid="([^"]+)"', tag)
        if named:
            said = re.search(r'\bdata-can="([^"]+)"', tag)
            tags[named[1]] = said[1] if said else None
    paired = re.findall(
        r'out\.push\(\[\$\("([^"]+)"\), "([a-z:-]+)"\]\)',
        _block(text, "function pairs()", "\n    }"),
    )
    assert len(by_cmd) > 20 and len(host) == 6 and len(paired) > 15, (by_cmd, host, paired)
    script = (
        f"import {{ verbOfLine }} from {json.dumps(CAN_JS.as_uri())};\n"
        f"console.log(JSON.stringify(Object.fromEntries({json.dumps(sorted(by_cmd))}"
        ".map((l) => [l, verbOfLine(l)]))));"
    )
    run = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert run.returncode == 0, run.stderr
    of_line = json.loads(run.stdout)

    def line_half(action):
        ours = CAN_VERBS[action]
        return ours.line if isinstance(ours, ByJob) else ours

    def button_half(action):
        ours = CAN_VERBS[action]
        return ours.job if isinstance(ours, ByJob) else ours

    problems = [
        f"{cmd} ({action}): the pad greys it as {of_line[cmd]}, the ring as {line_half(action)}"
        for cmd, action in by_cmd.items()
        if of_line[cmd] != line_half(action)
    ]
    problems += [
        f"{action}: the job's {word} is print.{word}, the ring's {button_half(action)}"
        for action, word in host.items()
        if button_half(action) != f"print.{word}"
    ]
    problems += [
        f"#{button} ({action}): its data-can is {tags.get(button)}, the ring's {button_half(action)}"
        for button, action in paired
        if tags.get(button) != button_half(action)
    ]
    problems += [
        f"control:jog:{axis}: a jog button's data-can is jog"
        for axis in ("X+", "Y-")
        if CAN_VERBS[f"control:jog:{axis}"] != "jog"
    ]
    assert problems == []
