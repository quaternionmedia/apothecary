"""The photo workflow from the browser: the pictures on this machine, a
picture a camera just took, many pictures gathered, and where cameras stand.

`POST /photos` in `api.py` already looks at one picture on disk and builds
an arrangement from it; `apothecary photo gather` does the rest from the
command line. These routes give the world's page the same, and no more:

- ``GET /photos/pictures`` lists the pictures in the one folder pictures are
  read from (`APOTHECARY_PICTURE_ROOT`, see `_picture_root` in api.py) and
  its two sub-folders the browser fills: ``captures/``, where a camera's
  frames are kept, and ``uploads/``, where the pictures a person added from
  the browser are kept. Nothing outside that folder is ever listed or read.
- ``POST /photos/pictures?name=…`` keeps a picture the browser sends, after
  checking it is a picture by its first bytes and not by its name: a frame
  from a camera under ``captures/`` (named by the moment), or, with
  ``kept=upload``, a file a person chose under ``uploads/`` (named as the
  person named it). It stays on this machine; nothing is sent anywhere.
- ``DELETE /photos/pictures/{path}`` forgets one kept picture and
  ``DELETE /photos/pictures`` forgets every kept picture: what the browser
  put under ``captures/`` and ``uploads/``, and only that. The folder's own
  pictures -- the ones a person named -- are never deleted from a page.
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
from pydantic import BaseModel, Field, field_validator

router = APIRouter(tags=["photos"])

PICTURE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
CAPTURES = "captures"
UPLOADS = "uploads"
# The folders the browser fills, and the only ones a page may empty.
KEPT = {"capture": CAPTURES, "upload": UPLOADS}
CAPTURE_MAX = 16 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


def _root() -> Path:
    from ..api import _picture_root

    return _picture_root()


def _kept_as(path: Path, root: Path) -> Optional[str]:
    """``"capture"`` or ``"upload"`` for a picture the browser put here, else None."""
    if path.parent.parent != root:
        return None
    return next((kind for kind, folder in KEPT.items() if path.parent.name == folder), None)


def _entry(path: Path, root: Path) -> dict:
    stat = path.stat()
    kept = _kept_as(path, root)
    return {
        "name": path.name,
        "path": path.relative_to(root).as_posix(),
        "size": stat.st_size,
        "taken_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "captured": kept == "capture",
        "kept": kept,
    }


def _pictures_in(folder: Path) -> List[Path]:
    """The picture files directly in a folder: regular files, never a link elsewhere --
    and nothing at all from a folder that is itself a link elsewhere."""
    if folder.is_symlink() or not folder.is_dir():
        return []
    return [
        path
        for path in folder.iterdir()
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in PICTURE_SUFFIXES
    ]


@router.get("/photos/pictures")
def list_pictures() -> List[dict]:
    """The pictures in the one folder, newest first: its own, its captures, its uploads."""
    root = _root()
    found: List[Path] = []
    for folder in (root, root / CAPTURES, root / UPLOADS):
        found.extend(_pictures_in(folder))
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [_entry(p, root) for p in found]


def _suffix_by_bytes(data: bytes) -> Optional[str]:
    """The suffix a picture's first bytes say it should have; None for anything else."""
    head = data[:16]
    if head.startswith(PNG_MAGIC):
        return ".png"
    if head.startswith(JPEG_MAGIC):
        return ".jpg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head.startswith(b"BM"):
        return ".bmp"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return ".tif"
    return None


def _private(folder: Path) -> Path:
    """The folder, made, and the person's alone: what the browser sends is theirs.

    A folder that is a link elsewhere is not written into: what the browser
    keeps here is forgotten from here, and that must never reach past it."""
    if folder.is_symlink():
        raise HTTPException(
            status_code=409, detail=f"{folder.name}/ is a link elsewhere; nothing is kept there"
        )
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{folder.name} is a file in the picture folder, not a folder; "
                "nothing is kept there"
            ),
        ) from None
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    return folder


def _unused(folder: Path, stem: str, suffix: str) -> Path:
    """``stem.suffix`` in the folder, or ``stem-2.suffix``, ``stem-3.suffix``… if taken."""
    path = folder / f"{stem}{suffix}"
    n = 2
    while path.exists():
        path = folder / f"{stem}-{n}{suffix}"
        n += 1
    return path


async def _picture_body(request: Request) -> bytes:
    """The picture the request carries, read no further than the limit: a body
    that says it is too large is refused before a byte of it is read, and one
    that grows past the limit is refused as it streams."""
    too_large = HTTPException(
        status_code=413, detail=f"larger than {CAPTURE_MAX // (1024 * 1024)} MB"
    )
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > CAPTURE_MAX:
        raise too_large
    chunks: List[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > CAPTURE_MAX:
            raise too_large
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=422, detail="an empty picture")
    return data


@router.post("/photos/pictures", status_code=201)
async def keep_picture(
    request: Request,
    name: str = Query("capture", min_length=1, max_length=120),
    kept: str = Query("capture", pattern="^(capture|upload)$"),
):
    """Keep a picture the browser sends: a camera's frame under captures/, named by the
    moment, or (``kept=upload``) a file a person chose under uploads/, named as they
    named it. A picture by its first bytes, whatever its name says."""
    data = await _picture_body(request)
    suffix = _suffix_by_bytes(data)
    if suffix is None:
        raise HTTPException(
            status_code=415,
            detail="not a picture (PNG, JPEG, GIF, WebP, BMP or TIFF, judged by its first bytes)",
        )
    root = _root()
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem).strip("_")[:60]
    if kept == "upload":
        path = _unused(_private(root / UPLOADS), stem or "picture", suffix)
    else:
        at = datetime.now(timezone.utc)
        stamp = f"{at:%Y%m%dT%H%M%S}.{at.microsecond // 1000:03d}"
        path = _private(root / CAPTURES) / f"{stamp}-{stem or 'capture'}{suffix}"
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


def _kept_picture(root: Path, given: str) -> Path:
    """The kept picture ``given`` names -- ``captures/x.png``, ``uploads/y.jpg``, or a
    bare name under captures/ -- or 404. Only a regular file directly in one of the
    two folders the browser fills; the folder's own pictures are a person's."""
    parts = given.replace("\\", "/").split("/")
    if len(parts) == 1:
        parts = [CAPTURES, parts[0]]
    if (
        len(parts) != 2
        or parts[0] not in KEPT.values()
        or not parts[1]
        or parts[1].startswith(".")
        or parts[1] in ("..",)
    ):
        raise HTTPException(status_code=404, detail="no such kept picture")
    path = root / parts[0] / parts[1]
    if (
        path.parent.is_symlink()
        or path.is_symlink()
        or not path.is_file()
        or path.suffix.lower() not in PICTURE_SUFFIXES
    ):
        raise HTTPException(status_code=404, detail="no such kept picture")
    return path


@router.delete("/photos/pictures")
def forget_kept_pictures(kept: str = Query("all", pattern="^(all|capture|upload)$")):
    """Forget every picture the browser put here -- the captures, the uploads, or both.

    Never the folder's own pictures: those a person named, and only a person
    removes. A link inside the folders is left alone too; only regular files
    directly in them go."""
    root = _root()
    folders = [KEPT[kept]] if kept != "all" else list(KEPT.values())
    forgotten: List[str] = []
    for folder in folders:
        for path in _pictures_in(root / folder):
            try:
                path.unlink()
            except FileNotFoundError:
                continue  # gone since it was listed: another purge, or the person
            forgotten.append(f"{folder}/{path.name}")
    return {"forgotten": forgotten, "left": len(_pictures_in(root))}


@router.delete("/photos/pictures/{path:path}")
def forget_picture(path: str):
    """Forget one kept picture (``captures/…`` or ``uploads/…``; a bare name is a capture).

    Only what the browser put here: the folder's own pictures are a person's."""
    root = _root()
    kept = _kept_picture(root, path)
    kept.unlink()
    return {"forgotten": kept.relative_to(root).as_posix()}


class GatherRequest(BaseModel):
    pictures: List[str] = Field(..., min_length=2, max_length=200)
    finder: str = "plain"
    answers: str = ""  # the five sentences, as the answers file has them
    most: int = Field(8, ge=1, le=40)
    build: bool = False  # also build the whole gathering as one arrangement
    name: str = Field("gathering", pattern=r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")

    @field_validator("name")
    @classmethod
    def _not_a_route(cls, value: str) -> str:
        from ..api import RESERVED_NAMES

        if value in RESERVED_NAMES:
            raise ValueError(f"{value!r} is the address of a route under /photos/")
        return value


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
