"""Pictures of a rig at values known beforehand, through a pinhole camera.

The rig's devices lie face up on a table, side by side, each showing the side
the rig names for it when that side has controls; a camera above the front of
the table looks down at them, tilted toward the far side, as
``vision/projection.py``'s pinhole has it. Each face is drawn flat from its
catalogue layout -- knobs with a pointer, faders with a cap, switches with a
lever, sockets as a nut round a hole or a plug in a cable's colour -- and laid
into the picture through its four corners.

Drawn pictures prove the plumbing, not the eyes: the same drawing rules
(``panels``' sizes) draw them and read them. They are what ``apothecary rig
check`` measures the reader on, and what ``rig simulate`` draws a concert
with: songs that each move a few controls, and between them a plug pushed
where no lead names one and a lead's plug pulled.
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from ..vision import projection
from . import look, panels
from .panels import Panel
from .reading import FaceInPicture, Setup, read

PICTURE = (1600, 1000)
# A camera 640 mm above the table, short of its front edge, tilted toward the far side.
EYE = (0.0, -330.0, 640.0)
TURN, TILT, FOV = 0.0, 24.0, 62.0
GAP_MM = 30.0  # between two devices on the table
ROW_MM = 650.0  # a row of devices this wide is seen from EYE; a narrower one from nearer
PX_PER_MM = 4  # each face is drawn at this before it is laid into the picture
START = datetime(2026, 10, 29, 20, 0, tzinfo=timezone.utc)

TABLE = (128, 120, 110)
PANEL = (52, 54, 58)
KNOB = (22, 22, 24)
POINTER = (235, 235, 230)
SLOT = (12, 12, 12)
CAP = (205, 205, 200)
NUT = (175, 175, 170)
HOLE = (8, 8, 8)
CABLES = ((200, 60, 50), (60, 120, 200), (230, 190, 60), (90, 170, 90))

Values = Dict[str, Dict[str, float]]
Plugged = Dict[str, Dict[str, bool]]


def _panel_of(setup: Setup, module: Dict[str, Any]) -> Optional[Panel]:
    return panels.panel(setup.entry(module["type"]), module.get("view", "front"))


def scene(rig: Dict[str, Any], devices: List[Dict[str, Any]]) -> Setup:
    """The rig laid on the table, and where each face lies in the camera's picture.

    The devices laid are those whose side the rig shows has controls on it; in a
    rig with none, those whose side has sockets -- a board and the leads into
    it. The camera is as far above as the row needs, wide or tall, so it fills
    the picture as a synth rig's does."""
    setup = Setup(rig=rig, devices=devices)
    shown = [(m, p) for m in rig.get("modules", []) if (p := _panel_of(setup, m)) is not None]
    laid = [(m, p) for m, p in shown if p.controls] or [(m, p) for m, p in shown if p.sockets]
    width = sum(panel.width_mm for _, panel in laid) + GAP_MM * max(0, len(laid) - 1)
    tallest = max((panel.height_mm for _, panel in laid), default=0.0)
    away = max(width, 1.5 * tallest * PICTURE[0] / PICTURE[1], 60.0) / ROW_MM
    eye = (EYE[0] * away, EYE[1] * away, EYE[2] * away)
    onto_picture = panels.invert(projection.pinhole(eye, TURN, TILT, FOV, PICTURE[1] / PICTURE[0]))
    left = -width / 2
    for module, panel in laid:
        cx, cy = left + panel.width_mm / 2, 40.0 * away
        corners = []
        for fx, fy in projection.CORNERS:
            x = cx + (fx - 0.5) * panel.width_mm
            y = cy + (0.5 - fy) * panel.height_mm
            corners.append(panels.apply(onto_picture, x, y))
        setup.faces[module["id"]] = FaceInPicture(side=panel.side, corners=corners)
        left += panel.width_mm + GAP_MM
    return setup


def _fraction(control: panels.Control, value: float) -> float:
    span = control.maximum - control.minimum
    return min(1.0, max(0.0, (value - control.minimum) / span)) if span else 0.0


def draw_face(panel: Panel, values: Dict[str, float], plugged: Dict[str, bool]):
    """One face, flat, at ``PX_PER_MM``."""
    from PIL import Image, ImageDraw

    size = (round(panel.width_mm * PX_PER_MM), round(panel.height_mm * PX_PER_MM))
    image = Image.new("RGB", size, PANEL)
    pen = ImageDraw.Draw(image)

    def at(x: float, y: float) -> Tuple[float, float]:
        return x * size[0], y * size[1]

    def box(cx: float, cy: float, w_mm: float, h_mm: float, fill) -> None:
        w, h = w_mm * PX_PER_MM / 2, h_mm * PX_PER_MM / 2
        pen.rectangle((cx - w, cy - h, cx + w, cy + h), fill=fill)

    for control in panel.controls:
        cx, cy = at(control.x, control.y)
        value = values.get(control.name, control.default)
        if control.kind in ("knob", "encoder"):
            r = panels.KNOB_MM * control.size / 2 * PX_PER_MM
            pen.ellipse((cx - r, cy - r, cx + r, cy + r), fill=KNOB)
            if control.kind == "knob":
                angle = math.radians(-panels.SWEEP + _fraction(control, value) * 2 * panels.SWEEP)
                tip = (cx + 0.9 * r * math.sin(angle), cy - 0.9 * r * math.cos(angle))
                pen.line(((cx, cy), tip), fill=POINTER, width=max(2, round(1.6 * PX_PER_MM)))
        elif control.kind in ("fader", "drawbar"):
            vertical = control.orient == "vertical"
            travel = control.length * (size[1] if vertical else size[0])
            if vertical:
                pen.rectangle(
                    (cx - PX_PER_MM, cy - travel / 2, cx + PX_PER_MM, cy + travel / 2), fill=SLOT
                )
                y = cy - travel / 2 + (1 - _fraction(control, value)) * travel
                box(cx, y, panels.CAP_MM[0] * control.size, panels.CAP_MM[1] * control.size, CAP)
            else:
                pen.rectangle(
                    (cx - travel / 2, cy - PX_PER_MM, cx + travel / 2, cy + PX_PER_MM), fill=SLOT
                )
                x = cx - travel / 2 + _fraction(control, value) * travel
                box(x, cy, panels.CAP_MM[1] * control.size, panels.CAP_MM[0] * control.size, CAP)
        elif control.kind == "switch":
            wide, tall = (mm * control.size for mm in panels.SWITCH_MM)
            box(cx, cy, wide, tall, KNOB)
            up = _fraction(control, value) >= 0.5
            box(cx, cy + (-1 if up else 1) * tall / 4 * PX_PER_MM, wide * 0.7, tall * 0.4, CAP)
    for number, socket in enumerate(panel.sockets):
        cx, cy = at(socket.x, socket.y)
        r = panels.SOCKET_MM * socket.size / 2 * PX_PER_MM
        pen.ellipse((cx - r, cy - r, cx + r, cy + r), fill=NUT)
        if plugged.get(socket.name):
            plug = 0.95 * r
            colour = CABLES[number % len(CABLES)]
            pen.ellipse((cx - plug, cy - plug, cx + plug, cy + plug), fill=colour)
        else:
            hole = 0.4 * r
            pen.ellipse((cx - hole, cy - hole, cx + hole, cy + hole), fill=HOLE)
    return image


def draw(setup: Setup, values: Values, plugged: Plugged, seed: int = 0):
    """The camera's picture of the rig at these values, these sockets plugged."""
    from PIL import Image, ImageChops, ImageFilter

    picture = Image.new("RGB", PICTURE, TABLE)
    scale_in = ((1 / PICTURE[0], 0.0, 0.0), (0.0, 1 / PICTURE[1], 0.0), (0.0, 0.0, 1.0))
    for module in setup.rig.get("modules", []):
        face = setup.faces.get(module["id"])
        if face is None:
            continue
        panel = panels.panel(setup.entry(module["type"]), face.side)
        if panel is None:
            continue
        flat = draw_face(panel, values.get(module["id"], {}), plugged.get(module["id"], {}))
        scale_out = ((flat.width, 0.0, 0.0), (0.0, flat.height, 0.0), (0.0, 0.0, 1.0))
        back = panels.invert(panels.face_onto([tuple(c) for c in face.corners]))
        m = panels.compose(scale_out, panels.compose(back, scale_in))
        coefficients = tuple(m[r][c] / m[2][2] for r in range(3) for c in range(3))[:8]
        laid = flat.transform(
            PICTURE, Image.Transform.PERSPECTIVE, coefficients, Image.Resampling.BICUBIC
        )
        mask = Image.new("L", flat.size, 255).transform(
            PICTURE, Image.Transform.PERSPECTIVE, coefficients, Image.Resampling.BILINEAR
        )
        picture.paste(laid, mask=mask)
    picture = picture.filter(ImageFilter.GaussianBlur(0.7))
    # Grain of eight grey levels either way, the same for the same seed.
    grain = Image.frombytes("L", PICTURE, random.Random(seed).randbytes(PICTURE[0] * PICTURE[1]))
    grain = grain.point([120 + value // 16 for value in range(256)]).convert("RGB")
    return ImageChops.add(picture, grain, scale=1.0, offset=-128)


# --- a concert -----------------------------------------------------------------------------


def _laid(setup: Setup):
    for module in setup.rig.get("modules", []):
        face = setup.faces.get(module["id"])
        if face is not None:
            panel = panels.panel(setup.entry(module["type"]), face.side)
            if panel is not None:
                yield module, panel


def at_rest(setup: Setup) -> Tuple[Values, Plugged]:
    """The rig as its document has it: each control at its value there, else its
    default, and a plug in every socket a lead names."""
    named = {
        (end["module"], end["jack"])
        for connection in setup.rig.get("connections", [])
        for end in (connection["source"], connection["target"])
    }
    values: Values = {}
    plugged: Plugged = {}
    for module, panel in _laid(setup):
        own = module.get("parameters", {})
        values[module["id"]] = {c.name: float(own.get(c.name, c.default)) for c in panel.controls}
        plugged[module["id"]] = {s.name: (module["id"], s.name) in named for s in panel.sockets}
    return values, plugged


def _moving(setup: Setup) -> List[Tuple[str, panels.Control]]:
    return [
        (module["id"], control)
        for module, panel in _laid(setup)
        for control in panel.controls
        if control.kind != "encoder"
    ]


def concert(setup: Setup, songs: int = 4, frames: int = 6, seed: int = 1):
    """Each frame of a concert, as (values, plugged, what changed at its song's start).

    Each song moves a few controls to new places over its first half and holds
    them; the second song starts with a plug pushed into a socket no lead names,
    the third with it out again and a lead's plug pulled, and the fourth with it
    pushed back."""
    rng = random.Random(seed)
    values, plugged = at_rest(setup)
    moving = _moving(setup)
    named_ends = [
        (end["module"], end["jack"])
        for connection in setup.rig.get("connections", [])
        for end in (connection["target"], connection["source"])
        if end["jack"] in plugged.get(end["module"], {})
    ]
    stray = sorted(
        (module, name)
        for module, sockets in plugged.items()
        for name, on in sockets.items()
        if not on
    )
    stray_plug = rng.choice(stray) if stray else None
    pulled = named_ends[0] if named_ends else None
    for song in range(songs):
        happened = []
        if song == 1 and stray_plug:
            plugged[stray_plug[0]][stray_plug[1]] = True
            happened.append(f"a plug pushed into {stray_plug[1]} on {stray_plug[0]}")
        if song == 2:
            if stray_plug:
                plugged[stray_plug[0]][stray_plug[1]] = False
                happened.append(f"the plug in {stray_plug[1]} on {stray_plug[0]} taken out")
            if pulled:
                plugged[pulled[0]][pulled[1]] = False
                happened.append(f"the lead's plug in {pulled[1]} on {pulled[0]} pulled")
        if song == 3 and pulled:
            plugged[pulled[0]][pulled[1]] = True
            happened.append(f"the lead's plug in {pulled[1]} on {pulled[0]} pushed back")
        start = {module: dict(controls) for module, controls in values.items()}
        targets = {}
        for module, control in rng.sample(moving, min(4, len(moving))):
            if control.kind == "switch":
                target = (
                    control.maximum
                    if start[module][control.name] < control.maximum
                    else control.minimum
                )
            else:
                target = round(rng.uniform(control.minimum, control.maximum))
            targets[(module, control.name)] = target
        rise = max(1, frames // 2)
        for frame in range(frames):
            share = min(1.0, (frame + 1) / rise)
            for (module, name), target in targets.items():
                begun = start[module][name]
                values[module][name] = round(begun + (target - begun) * share, 1)
            yield (
                {m: dict(c) for m, c in values.items()},
                {m: dict(s) for m, s in plugged.items()},
                happened if frame == 0 else [],
            )


def write_concert(
    setup: Setup, folder: Path, songs: int = 4, frames: int = 6, every: float = 5.0, seed: int = 1
) -> int:
    """The concert's frames, its setup and the truth of each frame, into ``folder``;
    how many frames."""
    from PIL.PngImagePlugin import PngInfo

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "setup.json").write_text(setup.model_dump_json(indent=2), encoding="utf-8")
    lines = []
    count = 0
    for count, (values, plugged, happened) in enumerate(
        concert(setup, songs, frames, seed), start=1
    ):
        name = f"frame-{count:04d}.png"
        taken = (START + timedelta(seconds=every * (count - 1))).isoformat()
        info = PngInfo()
        info.add_text("taken", taken)
        draw(setup, values, plugged, seed=seed * 10_000 + count).save(folder / name, pnginfo=info)
        lines.append(
            json.dumps(
                {
                    "picture": name,
                    "at": taken,
                    "values": values,
                    "plugged": plugged,
                    "happened": happened,
                }
            )
        )
    (folder / "truth.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


# --- how well the reader does ------------------------------------------------------------


class Measured(NamedTuple):
    kind: str
    looked: int  # controls, or sockets, looked at
    read: int
    mean: float  # how far off a reading was, on average: a share of the range, or of sockets
    worst: float


def measure(setup: Setup, count: int = 8, seed: int = 1) -> List[Measured]:
    """The reader on ``count`` pictures of the rig, every control at a value and
    every socket plugged or not, drawn at random; for each kind of control, and
    for sockets, how many were read and how far off."""
    rng = random.Random(seed)
    controls = {(module["id"], c.name): c for module, panel in _laid(setup) for c in panel.controls}
    found: Dict[str, List[float]] = {}
    looked: Dict[str, int] = {}
    for n in range(count):
        values, plugged = at_rest(setup)
        for module, control in _moving(setup):
            values[module][control.name] = (
                rng.choice((control.minimum, control.maximum))
                if control.kind == "switch"
                else rng.uniform(control.minimum, control.maximum)
            )
        for sockets in plugged.values():
            for name in sockets:
                sockets[name] = rng.random() < 0.5
        grey = look.Grey.of(draw(setup, values, plugged, seed=seed * 1000 + n))
        for module in read(setup, Path(f"drawn-{n + 1}.png"), grey=grey).modules:
            for seen in module.seen:
                looked[seen.kind] = looked.get(seen.kind, 0) + 1
                if seen.value is not None:
                    control = controls[(module.module, seen.name)]
                    span = (control.maximum - control.minimum) or 1.0
                    truth = values[module.module][seen.name]
                    found.setdefault(seen.kind, []).append(abs(seen.value - truth) / span)
            for plug in module.plugs:
                looked["socket"] = looked.get("socket", 0) + 1
                if plug.plugged is not None:
                    wrong = plug.plugged != plugged[module.module][plug.name]
                    found.setdefault("socket", []).append(1.0 if wrong else 0.0)
    return [
        Measured(
            kind,
            looked[kind],
            len(found.get(kind, [])),
            sum(found.get(kind, [])) / len(found[kind]) if found.get(kind) else 0.0,
            max(found.get(kind, [0.0])),
        )
        for kind in sorted(looked)
    ]
