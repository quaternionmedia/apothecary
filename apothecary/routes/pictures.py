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
- ``POST /photos/gather`` takes in up to forty of those pictures at once,
  with what a person has already said in the same five sentences the
  answers file uses, and answers with the report, the groups, the questions
  worth asking, and -- when asked to -- the whole gathering built as one
  arrangement the world can open. A file that cannot be read is set aside
  with the reason, not a refusal of the rest.
- ``GET/PUT/DELETE /cameras`` are the cameras a person placed in the world:
  a browser's camera (its id and label, which only the browser knows) at a
  node of a site, kept in the firmware state folder beside the pins, so
  every browser draws every camera where it stands.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from ..gathering.looking import PICTURE_SUFFIXES

router = APIRouter(tags=["photos"])

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
def keep_picture(
    data: bytes = Depends(_picture_body),
    name: str = Query("capture", min_length=1, max_length=120),
    kept: str = Query("capture", pattern="^(capture|upload)$"),
    site: Optional[str] = Query(None, max_length=64),
    host: Optional[str] = Query(None, max_length=400),
    camera: Optional[str] = Query(None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
):
    """Keep a picture the browser sends: a camera's frame under captures/, named by the
    moment, or (``kept=upload``) a file a person chose under uploads/, named as they
    named it. A picture by its first bytes, whatever its name says.

    With ``site`` and ``host`` (``""`` is the floor), the picture is kept and pinned
    there as a view in one request, and the answer carries the view: nothing is
    found in it yet, since Find shapes is a step of its own. A host that cannot hold a view is refused before
    anything is kept.

    The body is read on the event loop; the write of up to 16 MB runs in the threadpool."""
    suffix = _suffix_by_bytes(data)
    if suffix is None:
        raise HTTPException(
            status_code=415,
            detail="not a picture (PNG, JPEG, GIF, WebP, BMP or TIFF, judged by its first bytes)",
        )
    pinning = site is not None
    if pinning != (host is not None):
        raise HTTPException(
            status_code=422, detail="to pin a picture as it is kept, give both site and host"
        )
    if pinning:
        from .views import check_host

        check_host(site, host)
    root = _root()
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem).strip("_")[:60]
    if kept == "upload":
        path = _unused(_private(root / UPLOADS), stem or "picture", suffix)
    else:
        at = datetime.now(timezone.utc)
        stamp = f"{at:%Y%m%dT%H%M%S}.{at.microsecond // 1000:03d}"
        path = _private(root / CAPTURES) / f"{stamp}-{stem or 'capture'}{suffix}"
    path.write_bytes(data)
    entry = _entry(path, root)
    from ..vision.views import store

    store().kept_again(entry["path"])
    if pinning:
        from .views import _answer, pin_picture

        try:
            entry["view"] = _answer(site, pin_picture(site, host, entry["path"], camera=camera))
        except HTTPException as refused:
            # Kept, and not pinned: the picture is the person's either way.
            entry["view"], entry["not_pinned"] = None, refused.detail
    return entry


# The sizes a picture is served at, along its longer edge: a Kept card, a mat, a large mat.
PICTURE_SIZES = (256, 512, 1024, 2048)
# No picture enters the browser's disk cache: reuse is in the page's memory only.
NO_STORE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


@router.get("/photos/pictures/file")
def picture_file(
    path: str = Query(..., min_length=1, max_length=400),
    px: Optional[int] = Query(None, ge=1, le=100_000),
):
    """One picture from the folder, by the relative path the listing gave.

    With ``px``, no larger than the smallest of ``PICTURE_SIZES`` that holds it
    along its longer edge (the largest when none does), turned upright as the
    finder sees it: the pixels a mat or a card draws. A JPEG is decoded at a
    reduced size first, so a large photograph costs little. Never cached."""
    import mimetypes

    from fastapi.responses import FileResponse, Response

    from ..api import PICTURE_TYPES, _picture_within_root

    root = _root()
    asked = Path(path)
    settled = _picture_within_root(asked if asked.is_absolute() else root / asked)
    guessed, _ = mimetypes.guess_type(settled.name)
    kind = guessed if guessed in PICTURE_TYPES else None
    if kind is None or not _is_a_picture(settled):
        # A file that is not a picture is not served, whatever folder it is in.
        raise HTTPException(status_code=415, detail=f"{settled.name} is not a picture")
    if px is None:
        return FileResponse(settled, media_type=kind, headers=NO_STORE)
    edge = next((size for size in PICTURE_SIZES if size >= px), PICTURE_SIZES[-1])
    body, kind = _smaller(settled, edge)
    return Response(content=body, media_type=kind, headers=NO_STORE)


def _smaller(path: Path, edge: int):
    """The picture at most ``edge`` along its longer edge, upright: (bytes, media type)."""
    import io

    from PIL import Image, ImageOps

    with Image.open(path) as opened:
        jpeg = opened.format == "JPEG"
        if jpeg:
            opened.draft("RGB", (edge, edge))
        upright = ImageOps.exif_transpose(opened)
        upright.thumbnail((edge, edge))
        out = io.BytesIO()
        if jpeg:
            upright.convert("RGB").save(out, format="JPEG", quality=85)
            return out.getvalue(), "image/jpeg"
        if upright.mode not in ("RGB", "RGBA", "L", "LA"):
            upright = upright.convert("RGBA")
        upright.save(out, format="PNG")
        return out.getvalue(), "image/png"


def _is_a_picture(path: Path) -> bool:
    """Judged by its first bytes, not its name."""
    try:
        with path.open("rb") as f:
            return _suffix_by_bytes(f.read(16)) is not None
    except OSError:
        return False


def _kept_picture(root: Path, given: str) -> Path:
    """The kept picture ``given`` names -- ``captures/x.png``, ``uploads/y.jpg``, or a
    bare name under captures/ -- or 404. Only a regular file directly in one of the
    two folders the browser fills; the folder's own pictures are a person's."""
    parts = given.replace("\\", "/").split("/")
    if len(parts) == 1:
        parts = [CAPTURES, parts[0]]
    if len(parts) != 2 or parts[0] not in KEPT.values() or not parts[1] or parts[1].startswith("."):
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
    from ..vision.views import store

    root = _root()
    folders = [KEPT[kept]] if kept != "all" else list(KEPT.values())
    forgotten: List[str] = []
    unpinned: List[str] = []
    for folder in folders:
        for path in _pictures_in(root / folder):
            try:
                path.unlink()
            except FileNotFoundError:
                continue  # gone since it was listed: another purge, or the person
            forgotten.append(f"{folder}/{path.name}")
            unpinned.extend(store().forget_picture(forgotten[-1]))
    return {"forgotten": forgotten, "left": len(_pictures_in(root)), "unpinned": unpinned}


@router.delete("/photos/pictures/{path:path}")
def forget_picture(path: str):
    """Forget one kept picture (``captures/…`` or ``uploads/…``; a bare name is a capture).

    Only what the browser put here: the folder's own pictures are a person's.
    Its views are unpinned, every site's; pieces made from it stay, marked forgotten."""
    from ..vision.views import store

    root = _root()
    kept = _kept_picture(root, path)
    kept.unlink()
    forgotten = kept.relative_to(root).as_posix()
    return {"forgotten": forgotten, "unpinned": store().forget_picture(forgotten)}


# Every pair is compared, so the work grows as the square: forty pictures is 780 pairs.
GATHER_MOST = 40


class GatherRequest(BaseModel):
    pictures: List[str] = Field(..., min_length=2)
    finder: str = "plain"
    answers: str = ""  # the five sentences, as the answers file has them
    most: int = Field(8, ge=1, le=40)
    build: bool = False  # also build the whole gathering as one arrangement
    name: str = "gathering"

    @field_validator("name")
    @classmethod
    def _a_name(cls, value: str) -> str:
        """The rule POST /photos names an arrangement by: one rule, whichever route builds it."""
        from ..api import RESERVED_NAMES, SAFE_NAME

        if not SAFE_NAME.match(value):
            raise ValueError("a name is letters, digits, - and _, up to 64, starting alphanumeric")
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
    from ..gathering.looking import look_at_each, set_aside_unopened
    from ..gathering.questions import worth_asking
    from ..vision import build as build_arrangement
    from ..vision import get as get_finder
    from ..vision.shelf import shelf

    if len(body.pictures) > GATHER_MOST:
        raise HTTPException(
            status_code=422,
            detail=f"{len(body.pictures)} pictures at once is too many: every pair is "
            f"compared, so {GATHER_MOST} is the most. Gather them in smaller piles.",
        )
    root = _root()
    paths = []
    for rel in body.pictures:
        asked = Path(rel)
        paths.append(_picture_within_root(asked if asked.is_absolute() else root / asked))
    try:
        finder = get_finder(body.finder)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"no finder named {body.finder!r}") from None
    looked = look_at_each(finder, paths)
    clash = looked.clash()
    if clash:
        name, found = clash
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
    strangers = unknown_names(said, looked.names())
    if strangers:
        raise HTTPException(
            status_code=422,
            detail=f"you named picture(s) that are not here: {', '.join(strangers)}",
        )
    try:
        result = gather(looked.pictures, paths=looked.paths, answers=said)
    except PeopleDisagree as trouble:
        raise HTTPException(status_code=422, detail=str(trouble)) from None
    result = set_aside_unopened(result, looked, said)

    # Ranked once: the report, the questions and the count held back all read it.
    ranked = worth_asking(result, most=len(result.kinships) or 1)
    asked = ranked[: body.most]
    answer: dict = {
        "report": as_text(result, questions=ranked),
        "clusters": [c.model_dump() for c in result.clusters],
        "readings": [
            {k: (str(v) if isinstance(v, Path) else v) for k, v in r.model_dump().items()}
            for r in result.readings
        ],
        "set_aside": result.set_aside,
        "overruled": result.overruled,
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
        "withheld": len(ranked) - len(asked),
        "site": None,
    }
    if body.build:
        by_name = {p.name: (p, path) for p, path in zip(looked.pictures, looked.paths, strict=True)}
        built = {
            r.picture: build_arrangement(by_name[r.picture][0], picture_path=by_name[r.picture][1])
            for r in result.readings
            if r.readable and r.picture in by_name
        }
        if not built:
            raise HTTPException(
                status_code=422, detail="nothing could be read from any of these pictures"
            )
        stock = shelf()
        if body.name in _site_store.names() and body.name not in stock:
            # The same rule as POST /photos: a gathering never covers over a
            # site that did not come from pictures (the garage, the library).
            raise HTTPException(
                status_code=409,
                detail=f"{body.name!r} is already the name of an arrangement that did not "
                "come from a picture. Choose another name rather than covering it over.",
            )
        together = whole_gathering(result, built, name=body.name)
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
    path: str = Field(..., max_length=400)  # a host; "" is the site's floor
    mm_across: Optional[float] = Field(None, gt=0, allow_inf_nan=False)


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


# PUT and DELETE run in the threadpool: each read-modify-write holds this, and a
# write lands whole, so no placement is lost and a reader never sees half a file.
_CAMERAS_LOCK = threading.Lock()


def _save_cameras(cameras: Dict[str, dict]) -> None:
    from ..firmware.devices import private_folder

    path = _cameras_file()
    private_folder(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".cameras.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(json.dumps(cameras, indent=2))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@router.get("/cameras")
def list_cameras(site: Optional[str] = None) -> List[dict]:
    cams = _load_cameras()
    return [c for c in cams.values() if site is None or c.get("site") == site]


def camera_rows(site: Optional[str]) -> List[dict]:
    """The cameras pinned in one site (every site's with None), each saying whether its
    host is still there: a row whose host is gone is still taken back from its list."""
    from ..api import _site_store

    names = set(_site_store.names())
    rows = []
    for cam in list_cameras(site):
        where, host = cam.get("site"), cam.get("path", "")
        found = False
        if where in names:
            try:
                built = _site_store.get(where)
            except KeyError:
                built = None
            found = built is not None and (
                host == "" or any(c.name == host for c in built.children)
            )
        rows.append({**cam, "host_found": found})
    return rows


def set_camera_width(camera_id: str, mm_across: float) -> bool:
    """Keep the width last typed for a camera's picture: the next view from it starts there."""
    with _CAMERAS_LOCK:
        cams = _load_cameras()
        if camera_id not in cams:
            return False
        cams[camera_id]["mm_across"] = mm_across
        _save_cameras(cams)
    return True


@router.put("/cameras/{camera_id}")
def place_camera(camera_id: str, body: CameraPlacement):
    """Pin a browser's camera at a host, or at the floor (``path: ""``): the world draws
    it there from now on. A host holds one camera, so this replaces any other there;
    pinning a camera elsewhere moves it. A host is a root structure with a footprint
    that is not a made piece; anywhere else is refused with its reason."""
    from .views import check_host

    if not CAMERA_ID.match(camera_id):
        raise HTTPException(status_code=422, detail="not a camera id")
    check_host(body.site, body.path)
    placed = {
        "id": camera_id,
        "label": body.label,
        "site": body.site,
        "path": body.path,
        "placed_at": datetime.now(timezone.utc).isoformat(),
        "mm_across": body.mm_across,
    }
    with _CAMERAS_LOCK:
        cams = _load_cameras()
        if placed["mm_across"] is None and camera_id in cams:
            placed["mm_across"] = cams[camera_id].get("mm_across")
        replaced = sorted(
            other
            for other, cam in cams.items()
            if other != camera_id and cam.get("site") == body.site and cam.get("path") == body.path
        )
        for other in replaced:
            del cams[other]
        cams[camera_id] = placed
        _save_cameras(cams)
    return {**placed, "replaced": replaced}


@router.delete("/cameras/{camera_id}")
def unplace_camera(camera_id: str):
    with _CAMERAS_LOCK:
        cams = _load_cameras()
        if camera_id not in cams:
            raise HTTPException(status_code=404, detail="no such camera")
        del cams[camera_id]
        _save_cameras(cams)
    return {"unplaced": camera_id}
