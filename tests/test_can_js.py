"""static/can.js greys a button the server would refuse, says why in its title, and
puts its own tip back, run under node over a few stand-in elements."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CAN_JS = Path(__file__).resolve().parents[1] / "apothecary" / "static" / "can.js"

SCRIPT = r"""
import { applyCan, refreshDisabled, setTip, withLatch } from %(url)s;
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
    # A latch that lapsed refuses what only the latch allowed, and nothing else.
    assert out["latch"]["jog"]["kind"] == "armed" and out["latch"]["off"] == {"ok": True}
    assert out["latch"]["home"] == {"ok": False, "kind": "held", "why": "w"}
