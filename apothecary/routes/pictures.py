"""The photo workflow from the browser: the pictures on this machine, a
picture a camera just took, many pictures gathered, and where cameras stand.

`POST /photos` in `api.py` already looks at one picture on disk and builds
an arrangement from it; `apothecary photo gather` does the rest from the
command line. These routes give the world's page the same, and no more:

- ``GET /photos/pictures`` lists the pictures in the one folder pictures are
  read from (`APOTHECARY_PICTURE_ROOT`, see `_picture_root` in api.py) and
  its ``captures/`` sub-folder, where the routes below keep what a camera
  took. Nothing outside that folder is ever listed or read.
- ``POST /photos/pictures?name=…`` keeps a picture the browser sends -- a
  frame from a camera, or a file a person chose -- under ``captures/``,
  after checking it is a PNG or a JPEG by its first bytes and not by its
  name. It stays on this machine; nothing is sent anywhere.
- ``POST /photos/gather`` takes in several of those pictures at once, with
  what a person has already said in the same five sentences the answers
  file uses, and answers with the report, the groups, the questions worth
  asking, and -- when asked to -- the whole gathering built as one
  arrangement the world can open.
- ``GET/PUT/DELETE /cameras`` are the cameras a person placed in the world:
  a browser's camera (its id and label, which only the browser knows) at a
  node of a site, kept in the firmware state folder beside the pins, so
  every browser draws every camera where it stands.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["photos"])

PICTURE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
CAPTURES = "captures"
CAPTURE_MAX = 16 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


def _root() -> Path:
    from ..api import _picture_root

    return _picture_root()


def _entry(path: Path, root: Path) -> dict:
    stat = path.stat()
    return {
        "name": path.name,
        "path": path.relative_to(root).as_posix(),
        "size": stat.st_size,
        "taken_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "captured": path.parent.name == CAPTURES and path.parent.parent == root,
    }


@router.get("/photos/pictures")
def list_pictures() -> List[dict]:
    """The pictures in the one folder, newest first: the folder's own and its captures."""
    root = _root()
    found: List[Path] = []
    for folder in (root, root / CAPTURES):
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.is_file() and path.suffix.lower() in PICTURE_SUFFIXES:
                found.append(path)
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [_entry(p, root) for p in found]


@router.post("/photos/pictures", status_code=201)
async def keep_picture(
    request: Request, name: str = Query("capture", min_length=1, max_length=120)
):
    """Keep a picture the browser sends under captures/; a PNG or a JPEG by its bytes."""
    data = await request.body()
    if not data:
        raise HTTPException(status_code=422, detail="an empty picture")
    if len(data) > CAPTURE_MAX:
        raise HTTPException(
            status_code=413, detail=f"larger than {CAPTURE_MAX // (1024 * 1024)} MB"
        )
    if data.startswith(PNG_MAGIC):
        suffix = ".png"
    elif data.startswith(JPEG_MAGIC):
        suffix = ".jpg"
    else:
        raise HTTPException(
            status_code=415, detail="not a PNG or a JPEG (judged by its first bytes)"
        )
    root = _root()
    folder = root / CAPTURES
    folder.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(folder, 0o700)  # a camera's frames are the person's alone
    except OSError:
        pass
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem).strip("_") or "capture"
    at = datetime.now(timezone.utc)
    path = folder / f"{at:%Y%m%dT%H%M%S}.{at.microsecond // 1000:03d}-{stem[:60]}{suffix}"
    path.write_bytes(data)
    return _entry(path, root)


@router.get("/photos/pictures/file")
def picture_file(path: str = Query(..., min_length=1, max_length=400)):
    """One picture from the folder, by the relative path the listing gave -- for a thumbnail."""
    import mimetypes

    from fastapi.responses import FileResponse

    from ..api import PICTURE_TYPES, _picture_within_root

    root = _root()
    asked = Path(path)
    settled = _picture_within_root(asked if asked.is_absolute() else root / asked)
    guessed, _ = mimetypes.guess_type(settled.name)
    kind = guessed if guessed in PICTURE_TYPES else None
    if kind is None or not _is_a_picture(settled):
        # A file that is not a picture is not served, whatever folder it is in.
        raise HTTPException(status_code=415, detail=f"{settled.name} is not a picture")
    return FileResponse(settled, media_type=kind)


def _is_a_picture(path: Path) -> bool:
    """Judged by its first bytes, not its name."""
    try:
        with path.open("rb") as f:
            head = f.read(16)
    except OSError:
        return False
    return (
        head.startswith(PNG_MAGIC)
        or head.startswith(JPEG_MAGIC)
        or head.startswith((b"GIF87a", b"GIF89a", b"BM", b"II*\x00", b"MM\x00*"))
        or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    )


@router.delete("/photos/pictures/{name}")
def forget_picture(name: str):
    """Forget a capture (only captures: the folder's own pictures are a person's)."""
    root = _root()
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=404, detail="no such capture")
    path = root / CAPTURES / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no such capture")
    path.unlink()
    return {"forgotten": name}


class GatherRequest(BaseModel):
    pictures: List[str] = Field(..., min_length=2, max_length=200)
    finder: str = "plain"
    answers: str = ""  # the five sentences, as the answers file has them
    most: int = Field(8, ge=1, le=40)
    build: bool = False  # also build the whole gathering as one arrangement
    name: str = Field("gathering", pattern=r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")


@router.post("/photos/gather")
def gather_pictures(body: GatherRequest):
    """Which of these pictures are of the same thing, what to ask, and the arrangement."""
    from ..api import _picture_within_root, _site_store
    from ..gathering import as_text, gather, whole_gathering
    from ..gathering.judgement import (
        CannotRead,
        PeopleDisagree,
        read_answers,
        unknown_names,
    )
    from ..gathering.picture_map import as_html
    from ..gathering.questions import how_many_worth_asking, worth_asking
    from ..vision import build as build_arrangement
    from ..vision import get as get_finder
    from ..vision.shelf import shelf

    root = _root()
    paths = []
    for rel in body.pictures:
        asked = Path(rel)
        paths.append(_picture_within_root(asked if asked.is_absolute() else root / asked))
    try:
        finder = get_finder(body.finder)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"no finder named {body.finder!r}") from None
    pictures = []
    for path in paths:
        try:
            pictures.append(finder.look(path))
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail=f"{path.name} could not be read: {exc}"
            ) from None
    names_seen: Dict[str, List[Path]] = {}
    for path, picture in zip(paths, pictures, strict=True):
        names_seen.setdefault(picture.name, []).append(path)
    clashing = {n: f for n, f in names_seen.items() if len(f) > 1}
    if clashing:
        name, found = next(iter(sorted(clashing.items())))
        where = ", ".join(f.name for f in found)
        raise HTTPException(
            status_code=409, detail=f"two pictures are called {name!r} ({where}); rename one"
        )
    said = []
    if body.answers.strip():
        try:
            said = read_answers(body.answers, where="the answers")
        except (CannotRead, PeopleDisagree) as trouble:
            raise HTTPException(status_code=422, detail=str(trouble)) from None
    strangers = unknown_names(said, [p.name for p in pictures])
    if strangers:
        raise HTTPException(
            status_code=422,
            detail=f"you named picture(s) that are not here: {', '.join(strangers)}",
        )
    try:
        result = gather(pictures, paths=paths, answers=said)
    except PeopleDisagree as trouble:
        raise HTTPException(status_code=422, detail=str(trouble)) from None

    asked = worth_asking(result, most=body.most)
    answer: dict = {
        "report": as_text(result),
        "map_html": as_html(result),
        "clusters": [c.model_dump() for c in result.clusters],
        "readings": [
            {k: (str(v) if isinstance(v, Path) else v) for k, v in r.model_dump().items()}
            for r in result.readings
        ],
        "set_aside": result.set_aside,
        "ignored": result.ignored,
        "overruled": result.overruled,
        "resolved_share": result.resolved_share(),
        "questions": [
            {
                "left": q.left,
                "right": q.right,
                "settles": q.settles,
                "sentence": q.sentence(),
                "worth": q.worth(),
                "because": q.because,
                "against": q.against,
                "answers": [line[2:] for line in q.answer_lines()],
            }
            for q in asked
        ],
        "withheld": max(0, how_many_worth_asking(result) - len(asked)),
        "site": None,
    }
    if body.build:
        by_name = {p.name: (p, path) for p, path in zip(pictures, paths, strict=True)}
        built = {
            r.picture: build_arrangement(by_name[r.picture][0], picture_path=by_name[r.picture][1])
            for r in result.readings
            if r.readable and r.picture in by_name
        }
        if not built:
            raise HTTPException(
                status_code=422, detail="nothing could be read from any of these pictures"
            )
        together = whole_gathering(result, built, name=body.name)
        stock = shelf()
        stock.put(together)
        _site_store.add(
            together.site.name, stock.factory(together.site.name), stock.checker(together.site.name)
        )
        answer["site"] = together.site.name
    return answer


# --- cameras placed in the world -------------------------------------------------------


class CameraPlacement(BaseModel):
    label: str = Field("camera", max_length=120)
    site: str = Field(..., pattern=r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")
    path: str = Field(..., max_length=400)


CAMERA_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _cameras_file() -> Path:
    from ..firmware.devices import state_dir

    return state_dir() / "cameras.json"


def _load_cameras() -> Dict[str, dict]:
    try:
        data = json.loads(_cameras_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cameras(cameras: Dict[str, dict]) -> None:
    from ..firmware.devices import private_folder

    path = _cameras_file()
    private_folder(path.parent)
    path.write_text(json.dumps(cameras, indent=2), encoding="utf-8")


@router.get("/cameras")
def list_cameras(site: Optional[str] = None) -> List[dict]:
    cams = _load_cameras()
    return [c for c in cams.values() if site is None or c.get("site") == site]


@router.put("/cameras/{camera_id}")
def place_camera(camera_id: str, body: CameraPlacement):
    """Place a browser's camera at a node: the world draws it there from now on."""
    from ..api import _find_node_by_path, _get_site_or_404

    if not CAMERA_ID.match(camera_id):
        raise HTTPException(status_code=422, detail="not a camera id")
    site = _get_site_or_404(body.site)
    if _find_node_by_path(site, body.path) is None:
        raise HTTPException(
            status_code=404, detail=f"Node '{body.path}' not found in site '{body.site}'"
        )
    cams = _load_cameras()
    cams[camera_id] = {
        "id": camera_id,
        "label": body.label,
        "site": body.site,
        "path": body.path,
        "placed_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_cameras(cams)
    return cams[camera_id]


@router.delete("/cameras/{camera_id}")
def unplace_camera(camera_id: str):
    cams = _load_cameras()
    if camera_id not in cams:
        raise HTTPException(status_code=404, detail="no such camera")
    del cams[camera_id]
    _save_cameras(cams)
    return {"unplaced": camera_id}
