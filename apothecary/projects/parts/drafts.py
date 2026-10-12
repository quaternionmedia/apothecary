"""Drafts: a part's SCAD as edited in the page and not saved.

A draft is text. To check it or render it, it is written to a file of its own
beside the part's SCAD, so that ``include <../board_common.scad>`` resolves
from it as it does from the part: ``.<stem>.<random>.draft.scad``, hidden,
ignored by git (.gitignore), never taken for a part by the registry, removed
when the one OpenSCAD run is done, and never written over the part's own file.
Beside a part in a submodule (gridfinity's), where the checkout's .gitignore
does not reach, the submodule's own ``info/exclude`` ignores it
(``ignored_in_its_submodule``): local to this clone, never a tracked file.

- **The check** evaluates the draft and renders nothing
  (``customizer.check_scad``): OpenSCAD's errors and warnings by line and,
  where the OpenSCAD lists them, the parameters the draft declares. A check
  of the same text with the same includes and OpenSCAD is remembered.
- **The render** is a variant like any other (``variants.make_variant`` with
  ``draft``), filed under a key computed from the draft's text, and the cache
  keeps the text beside the mesh, so a tab reloaded on that variant can show
  what it drew.

A message about the draft names the part's SCAD: its lines are the lines of
the edit. A part whose geometry is Python (the snowplow) has no SCAD of its
own to edit: ``/parts/{name}/scad`` shows the SCAD its geometry generates,
read-only, and a draft of it is refused (``ReadOnly``). Saving a draft is
apothecary/projects/parts/saved.py.
"""

from __future__ import annotations

import contextvars
import hashlib
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Tuple

from .base import BasePart
from .customizer import (
    Check,
    Compiled,
    check_scad,
    compile_scad,
    part_compile,
    remembered_check,
    remembered_compile,
)
from .stl_renderer import Cancellation, OpenSCADRenderer, part_renderer
from .variants import same_text

# Characters in a draft: far more than any part's SCAD, far less than a mistake.
DRAFT_LIMIT = 1_000_000

DRAFT_SUFFIX = ".draft.scad"
# How a submodule's info/exclude names every draft beside its files.
DRAFT_PATTERN = f".*{DRAFT_SUFFIX}"


class ReadOnly(ValueError):
    """The part's SCAD is not its source: its geometry is Python."""


def editable(part: BasePart) -> bool:
    """Whether the part's SCAD is what it is built from, and so can be edited."""
    return part.geometry({}) is None


def refuse_read_only(part: BasePart) -> None:
    """``ReadOnly`` for a part whose geometry is Python, saying where to edit it."""
    if not editable(part):
        raise ReadOnly(
            f"{part.name}'s geometry is Python ({type(part).__module__}): its SCAD is generated "
            "from its parameters and shown read-only. Its parameters are what to edit."
        )


def draft_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def draft_name(part: BasePart) -> str:
    """A new draft file's name, beside the part's SCAD."""
    return f".{part.source_file.stem}.{uuid.uuid4().hex[:12]}{DRAFT_SUFFIX}"


_EXCLUDED: set = set()
_EXCLUDED_GUARD = threading.Lock()


def ignored_in_its_submodule(folder: Path) -> Optional[Path]:
    """Drafts beside a file in ``folder`` ignored by the submodule it is in, if
    it is in one: ``DRAFT_PATTERN`` added once to that submodule's own
    ``info/exclude`` (in its git directory: not a tracked file, nothing to
    commit). The exclude file written, or None (not a submodule, not in git, or
    already done). Asked once per folder."""
    from .saved import GitError, _git, repository_of, superproject_of

    key = str(Path(folder).resolve())
    with _EXCLUDED_GUARD:
        if key in _EXCLUDED:
            return None
        _EXCLUDED.add(key)
    try:
        top = repository_of(Path(folder))
        if superproject_of(top) is None:
            return None
        named = _git(top, "rev-parse", "--git-path", "info/exclude").strip()
        exclude = Path(named) if Path(named).is_absolute() else top / named
        have = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        if DRAFT_PATTERN in have.splitlines():
            return None
        exclude.parent.mkdir(parents=True, exist_ok=True)
        lead = "" if not have or have.endswith("\n") else "\n"
        with open(exclude, "a", encoding="utf-8") as out:
            out.write(
                f"{lead}# apothecary: a draft written beside a part for one OpenSCAD run\n"
                f"{DRAFT_PATTERN}\n"
            )
        return exclude
    except (GitError, OSError):
        return None


@contextmanager
def written_beside(part: BasePart, text: str) -> Iterator[Path]:
    """``text`` in a file of its own beside the part's SCAD, for as long as the
    block runs; removed after, whatever happened. Never the part's own file.
    Beside a part in a submodule, the submodule ignores it."""
    refuse_read_only(part)
    ignored_in_its_submodule(part.source_file.parent)
    path = part.source_file.with_name(draft_name(part))
    # "x": a new file or nothing, so no run ever writes over another's.
    with open(path, "x", encoding="utf-8", newline="") as handle:
        handle.write(text)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def check_draft(
    part: BasePart,
    text: str,
    renderer: Optional[OpenSCADRenderer] = None,
    cancel: Optional[Cancellation] = None,
) -> Check:
    """``text`` as the part's SCAD, evaluated and not rendered: what OpenSCAD
    said of it by line (naming the part's SCAD), and the parameters it
    declares where the OpenSCAD lists them."""
    refuse_read_only(part)
    renderer = renderer or part_renderer(part)

    def run() -> Check:
        with written_beside(part, text) as path:
            return check_scad(path, renderer, cancel, shown_as=part.source_file)

    return remembered_check(part.source_file, text, renderer, run)


def compile_draft(
    part: BasePart,
    text: str,
    definitions: Optional[Mapping[str, Any]] = None,
    renderer: Optional[OpenSCADRenderer] = None,
    cancel: Optional[Cancellation] = None,
) -> Compiled:
    """``text`` as the part's SCAD, evaluated with ``definitions`` as ``-D`` and
    exported as CSG (``customizer.compile_scad``): what OpenSCAD said of it
    with the staged values, and the digest of what it compiled. A text the
    same as the part's SCAD is compiled from the part's own file."""
    refuse_read_only(part)
    renderer = renderer or part_renderer(part)
    defs = dict(definitions or {})
    if same_text(part.source_file, text):
        return part_compile(part, defs, renderer, cancel)

    def run() -> Compiled:
        with written_beside(part, text) as path:
            return compile_scad(path, renderer, defs, cancel, shown_as=part.source_file)

    return remembered_compile(part.source_file, text, defs, renderer, run)


def check_and_compile(
    part: BasePart,
    text: str,
    definitions: Optional[Mapping[str, Any]] = None,
    renderer: Optional[OpenSCADRenderer] = None,
    cancel: Optional[Cancellation] = None,
) -> Tuple[Check, Compiled]:
    """The check of ``text`` (its parameters and what OpenSCAD says of the text
    alone) and its compile with ``definitions``, the two OpenSCAD runs at once:
    the parameter export leaves out what ``-D`` sets, so it cannot be the
    run that has the staged values."""
    renderer = renderer or part_renderer(part)
    found: Dict[str, Compiled] = {}

    def compiling() -> None:
        found["compiled"] = compile_draft(part, text, definitions, renderer, cancel)

    # In the request's context, so the queue shows the run as the request's.
    context = contextvars.copy_context()
    worker = threading.Thread(
        target=context.run, args=(compiling,), name=f"compile {part.name}", daemon=True
    )
    worker.start()
    try:
        check = check_draft(part, text, renderer, cancel)
    finally:
        worker.join()
    return check, found.get("compiled") or Compiled(ok=False, error_message="not compiled")


__all__ = [
    "DRAFT_LIMIT",
    "DRAFT_PATTERN",
    "DRAFT_SUFFIX",
    "ReadOnly",
    "check_and_compile",
    "check_draft",
    "compile_draft",
    "draft_digest",
    "editable",
    "ignored_in_its_submodule",
    "refuse_read_only",
    "written_beside",
]
