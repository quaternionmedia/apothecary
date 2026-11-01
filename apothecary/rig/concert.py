"""A concert's frames followed in order, each held in carlos, the record kept beside them.

A concert is a folder of frames, in time order by name, with the setup that
says what they show (``setup.json``, unless another is named). Whatever wrote
the frames -- the viewer's camera, a phone's time-lapse, ffmpeg -- the
follower only reads the folder. Each frame is read through the setup and held
in carlos as the rig it shows, unless it holds the same as the frame before it.
The leads are carried from frame to frame: a plug moved in one is where it went
in the next, so a rig re-patched between songs, a plug at a time, is followed.
One line of the record, ``readings.jsonl`` beside the frames, says what each
frame was read as; the record is written afresh each time a folder is
followed.

``pace`` holds each frame for that many seconds, so a concert already played
is played again into carlos as it went; ``watch`` keeps looking for new frames
every ``every`` seconds after the last, so a concert being played is followed
as it is.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..wiring import carlos
from . import look
from .reading import Reading, Setup, held, read

SETUP = "setup.json"
RECORD = "readings.jsonl"
SUFFIXES = (".png", ".jpg", ".jpeg")
EXIF_TAKEN = 36867  # DateTimeOriginal


def frames(folder: Path) -> List[Path]:
    """The folder's pictures, in order by name."""
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES)


def taken(path: Path, image) -> str:
    """When a frame was taken: a PNG's ``taken`` text, a JPEG's EXIF time, else its file's."""
    said = image.info.get("taken")
    if said:
        return str(said)
    exif = image.getexif().get_ifd(0x8769).get(EXIF_TAKEN)
    if exif:
        return datetime.strptime(str(exif), "%Y:%m:%d %H:%M:%S").isoformat()
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def read_frame(setup: Setup, path: Path) -> Reading:
    from PIL import Image, ImageOps

    with Image.open(path) as opened:
        at = taken(path, opened)
        grey = look.Grey.of(ImageOps.exif_transpose(opened))
    return read(setup, path, grey=grey, at=at)


def hold_cue(setup: Setup, reading: Reading, patch: Dict[str, Any], states) -> Dict[str, Any]:
    """The cue that has carlos hold the rig as this frame shows it: its patch and
    states, as ``held`` gives them."""
    return carlos.hold_cue(
        number=Path(reading.picture).stem,
        name=f"apothecary: {setup.rig.get('name', 'the rig')}, {reading.picture}",
        patch=patch,
        devices=setup.devices,
        states=states.model_dump(mode="json"),
        fired_at=datetime.fromisoformat(reading.at) if reading.at else None,
    )


def record_line(
    reading: Reading,
    sent: Optional[bool],
    error: Optional[str],
    leads: Optional[List[Dict[str, Any]]] = None,
) -> str:
    unread = {
        m.module: {s.name: s.why for s in m.seen if s.value is None}
        for m in reading.modules
        if m.seen
    }
    return json.dumps(
        {
            "picture": reading.picture,
            "at": reading.at,
            "values": reading.values(),
            "plugged": reading.plugged(),
            "unread": {module: names for module, names in unread.items() if names},
            "leads": leads,
            "held": sent,
            "error": error,
        }
    )


class Concert:
    """One folder of frames, followed."""

    def __init__(
        self,
        folder: Path,
        setup: Optional[Path] = None,
        url: Optional[str] = None,
        say: Callable[[str], None] = print,
    ):
        self.folder = Path(folder)
        self.setup = Setup.load(setup or self.folder / SETUP)
        self.url = carlos.loopback_url(url) if url else None
        self.say = say
        self.seen: set = set()
        self.last_held: Optional[str] = None
        # The leads as the last frame held them: the setup's, until a frame moves one.
        self.leads: List[Dict[str, Any]] = list(self.setup.rig.get("connections", []))
        self.stopped = threading.Event()

    def take(self, path: Path) -> Reading:
        """One frame read, held in carlos when it changed, and recorded."""
        reading = read_frame(self.setup, path)
        patch, states = held(self.setup, reading, self.leads)
        self.leads = patch["connections"]
        sent: Optional[bool] = None
        error = None
        if self.url:
            body = hold_cue(self.setup, reading, patch, states)
            action = json.dumps(body["action"], sort_keys=True)
            sent = False
            if action != self.last_held:
                try:
                    carlos.send(body, self.url)
                    self.last_held, sent = action, True
                except carlos.CarlosError as exc:
                    error = str(exc)
        with (self.folder / RECORD).open("a", encoding="utf-8") as record:
            record.write(record_line(reading, sent, error, self.leads) + "\n")
        self.seen.add(path.name)
        unread = sum(1 for m in reading.modules for s in m.seen if s.value is None)
        read_count = sum(1 for m in reading.modules for s in m.seen if s.value is not None)
        plugs = sum(1 for m in reading.modules for p in m.plugs if p.plugged)
        what = f"{path.name}: {read_count} controls read, {unread} not, {plugs} plugs seen"
        self.say(what + (" -- held in carlos" if sent else f" -- {error}" if error else ""))
        return reading

    def follow(self, pace: float = 0.0, watch: bool = False, every: float = 2.0) -> int:
        """Every frame in order, then (``watch``) each new one as it comes; how many."""
        (self.folder / RECORD).write_text("", encoding="utf-8")
        taken_count = 0
        while not self.stopped.is_set():
            fresh = [p for p in frames(self.folder) if p.name not in self.seen]
            for path in fresh:
                try:
                    self.take(path)
                except OSError as exc:
                    # A frame still being written, or not a picture. Watching,
                    # it is looked at again next time; otherwise it is passed.
                    self.say(f"{path.name}: not read ({exc})")
                    if not watch:
                        self.seen.add(path.name)
                    continue
                taken_count += 1
                if pace and self.stopped.wait(pace):
                    break
            if not watch:
                break
            self.stopped.wait(every)
        return taken_count
