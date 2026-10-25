"""Every part's STL built before the browser tests take their first picture, by the
OpenSCAD their servers run, and which OpenSCAD that is.

    python tests/e2e/parts_built.py      # run with the servers' environment

A server builds a missing STL in the background when it starts, and the viewer draws
a part's box until its STL lands: a picture taken before then shows the box, and one
taken after the mesh. And an STL is kept while it is newer than its SCAD, whichever
OpenSCAD wrote it -- a person's snapshot, or the servers' -- so the same picture could
be drawn from either. So the browser tests build every STL first, here, with the
OpenSCAD their servers would use, and build again any STL this did not record writing
with it (``.cache/stl-writers.json``, beside the checkout's other caches). What it
prints, a JSON object, is the OpenSCAD and the parts drawn from anything else (an STL
it cannot build here but found, or none at all); what a page records is ``described``.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / ".cache" / "stl-writers.json"


@contextmanager
def _alone(lock: Path):
    """One builder at a time across processes (each -n worker is a session of its own)."""
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("w") as handle:
        try:
            import fcntl
        except ImportError:  # Windows: one session at a time is the person's to keep
            yield
            return
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _stamp(path: Path) -> list:
    stat = path.stat()
    return [stat.st_mtime_ns, stat.st_size]


def build() -> dict:
    """Build what is missing or written by another OpenSCAD; what the pages record."""
    from apothecary.api import _registered_part
    from apothecary.projects.parts.stl_renderer import build_stl, get_renderer, part_renderer
    from apothecary.projects.registry import scan_projects

    default = get_renderer()
    openscad = default.get_version() if default.is_available else None
    found = {
        "openscad": openscad,
        "path": str(default.openscad_path) if openscad else None,
        "elsewhere": [],
        "boxes": [],
    }
    if openscad is None:
        found["boxes"] = ["every part"]
        return found
    with _alone(RECORD.with_suffix(".lock")):
        try:
            writers = json.loads(RECORD.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            writers = {}
        for item in scan_projects(ROOT):
            if item.kind != "part":
                continue
            part = _registered_part(item)
            stl = part.get_stl_output_path()
            key = stl.relative_to(ROOT).as_posix() if stl.is_relative_to(ROOT) else str(stl)
            renderer = part_renderer(part)
            version = renderer.get_version() if renderer.is_available else None
            known = stl.exists() and writers.get(key) == [*_stamp(stl), version]
            result = build_stl(part, force=stl.exists() and not known, timeout=300)
            if result.success and stl.exists():
                writers[key] = [*_stamp(stl), version]
                if version != openscad:
                    found["elsewhere"].append(f"{part.name} ({version})")
            elif stl.exists():
                found["elsewhere"].append(f"{part.name} (an STL built before this run)")
            else:
                found["boxes"].append(part.name)
        RECORD.write_text(json.dumps(writers, indent=1, sort_keys=True), encoding="utf-8")
    return found


def described(found: dict) -> str:
    """What a page says of the STLs its pictures were drawn from: only what is the same
    wherever the same OpenSCAD runs. Which parts it cannot build, and whether an STL of
    one was already there, differ from one clone to the next, and a page that said so
    would differ with them."""
    if found.get("openscad") is None:
        return "Its pictures were taken with no OpenSCAD: every part is drawn as its box."
    return (
        "Its pictures were taken once every part's STL that "
        f"{found['openscad']}, the OpenSCAD its server runs, can build was built by it; a "
        "part it cannot build is drawn from an STL already there, or as its box."
    )


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    print(json.dumps(build()))
