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


MACHINE_JS = CAN_JS.parent / "widgets" / "machine.js"


def _alternatives(pattern) -> list:
    """The lines a dialect's ``^(a|b|c)$`` matches, each one."""
    found = re.fullmatch(r"\^\((.*)\)\$", pattern.pattern)
    assert found, pattern.pattern
    return found[1].split("|")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_a_pad_line_is_greyed_for_the_latch_exactly_when_the_server_wants_the_latch():
    """can.js verbOfLine names each line a pad sends by the server's command; a line the
    server takes with the latch down (a dialect's stop, or its ``always``) is a stop
    (never greyed) or an off, and every other line needs the latch, as the route says.
    The lines: every pad button's in machine.js, and each the server lists."""
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
    for line, verb in verbs.items():
        free = line in dialects.STOPS or any(
            d.always.match(line) for d in dialects.BY_WORD.values()
        )
        assert (verb in ("estop", "off")) == free, (
            f"{line}: the page says {verb}, the server {'takes it unarmed' if free else 'wants the latch'}"
        )
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
    nothing and leaves it): each verb machine.js, sketches.js and the templates write, each
    can.js gives a pad's line, and each the latch lapsing refuses, is one the server
    answers."""
    answers = _verbs_the_server_answers(monkeypatch)
    pages = [
        MACHINE_JS,
        CAN_JS.parent / "widgets" / "sketches.js",
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
