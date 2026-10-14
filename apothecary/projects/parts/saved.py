"""A saved edit is a variant in git.

Saving commits a part's text as edited -- its SCAD, whose values are in it --
to a ref of the part's own -- ``refs/apothecary/variants/<part>/<name>`` -- in
the repository that tracks the part's SCAD. It is built with git's plumbing
alone:

1. ``git hash-object -w --stdin`` writes the text as a blob;
2. ``git ls-tree`` reads each tree from the root down to the part's folder, and
   ``git mktree`` writes each back with its one changed entry, from the folder
   up to a new root;
3. ``git commit-tree`` makes the commit: its parent is the variant's last save,
   or ``HEAD`` for a first one;
4. ``git update-ref`` moves the ref, and refuses if it moved since it was read.

None of these reads or writes the working tree, the index or the branch that
is checked out: after a save ``git status`` and ``HEAD`` are what they were.
The commit's author and committer are the git identity of the checkout -- git's
own ``user.name`` and ``user.email``, the person who pressed Save -- and its
message carries no trailer of any kind.

The commit's tree is the tree it was based on, with the part's SCAD as
edited: its values are its assignments, so the text is the truth. ``git diff
HEAD <ref>`` is the edit, values and all, ``git log <ref>`` its history, and
pushing the ref shares it. Making a variant the part's source is a merge the
person does (``git merge <ref>``), and it applies the variant's values;
nothing here writes the working tree. Listing a part's variants reads its refs
(``git for-each-ref``), each with whether ``HEAD`` already holds it and, asked
for, what it changes: a diff of its SCAD against the part's SCAD on disk.

A *.variant.json variant* is one whose commit keeps its parameters beside its
SCAD in ``<stem>.variant.json``. Served (read, listed, compared, its history)
its SCAD has them written into it (``values_in`` says where they are in its
commit, and the merge advice that a merge of it would not apply them); saved
or restored again, it is written as text alone and that file goes.

Where a variant's values are kept is a choice with one built answer and one
stub (``KEPT_IN``): in its text; the part's own description -- its Params
model or its part.json -- remains a stub, refused, saying what it would do.

``APOTHECARY_VARIANTS_REPO`` names another repository to save into -- a clone
of the checkout, for a test's server, which must never write this checkout's
refs. The paths in its commits are still the part's, from the top of the
checkout that holds it.

**A part inside a submodule** (gridfinity's SCAD is in
``parts/gridfinity/gridfinity-rebuilt-openscad``) is saved as an **overlay**
in the superproject: ``<stem>.overlay.scad`` beside the submodule, a small
SCAD that includes the upstream file and sets the variant's values -- the
text its editor holds -- committed to the superproject's ref. The
submodule is never touched -- its repository, its tree, its refs -- and an
edit of the upstream file itself is refused (``UpstreamEdit``), saying so.

**Managing them** is git's plumbing too, and touches the working tree, the
index and ``HEAD`` no more than a save does: a rename or a duplicate moves or
copies the ref (``update-ref --stdin``, one transaction); a variant's history
is its ref's own commits, from its first save on (each commit's message
says the commit it was first saved on top of: a sentence, not a trailer); a
restore is a new commit on the ref with an earlier commit's text; a delete
moves the ref to
``refs/apothecary/trash/<part>/<name>``, where it is listed and can be restored
from, and only emptying the trash deletes it. A name taken -- a live variant's,
or a deleted one's in the trash -- is refused (``Taken``), never overwritten.

**Where the ref is, and what a merge does** (``MergeAdvice``): a save's answer
names the repository the ref lives in, the commands that make it the part's
source, and says what a merge applies: the variant's values, which are in
its text (a .variant.json variant keeps them in a file a merge does not
apply, and says so).

Every git here is told to fetch nothing: a partial clone would otherwise
fetch an object it lacks (``GIT_NO_LAZY_FETCH``), and nothing may prompt.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, NamedTuple, Optional

from pydantic import BaseModel, Field

from .base import BasePart
from .drafts import refuse_read_only

REF_ROOT = "refs/apothecary/variants"
# Where a deleted variant's ref goes: listed, restorable, gone only when emptied.
TRASH_ROOT = "refs/apothecary/trash"

# A variant's name: what a person would type, and a valid ref component.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}[A-Za-z0-9_]$|^[A-Za-z0-9]$")

PARAMS_SUFFIX = ".variant.json"
OVERLAY_SUFFIX = ".overlay.scad"

# What a saved variant is: the part's SCAD as edited, or, for a part in a
# submodule, an overlay that includes the upstream SCAD and sets its values.
KIND_SCAD = "scad"
KIND_OVERLAY = "overlay"

GIT_TIMEOUT = 30.0


class GitError(RuntimeError):
    """A git command failed; its message is git's."""


class NotInGit(GitError):
    """The part's SCAD is not in a git repository."""


class Moved(GitError):
    """The variant's ref moved between reading it and moving it: saved meanwhile."""


class NoSuchVariant(LookupError):
    """No saved variant by that name."""


class Taken(GitError):
    """A ref by that name is there already: a variant's, or a deleted one's in
    the trash. Nothing is overwritten."""


class NotBuilt(ValueError):
    """A stub was named: it says what it will do, and does not do it yet."""


class UpstreamEdit(ValueError):
    """An edit of a SCAD that lives in a submodule: never saved, the submodule
    being upstream's. Its values are saved as an overlay instead."""


@dataclass(frozen=True)
class Keeping:
    """Where a saved variant's parameters are kept, or will be."""

    id: str
    does: str
    stub: bool = False


# Where a saved variant's values are kept: in its text; the part's own
# description is a stub.
KEPT_IN = (
    Keeping(
        "text",
        "the values in the variant's SCAD: its assignments, which a merge applies",
    ),
    Keeping(
        "part-description",
        "the parameters written into the part's own description -- its Params model's "
        "defaults, or its part.json -- in the variant's commit, and the SCAD regenerated "
        "from that description when it is needed",
        stub=True,
    ),
)
KEEP_DEFAULT = "text"
# Where a .variant.json variant keeps its values.
IN_FILE = "variant-file"


def keeping(kept_in: str) -> Keeping:
    """Where parameters are to be kept; a stub is refused, saying what it will do."""
    for k in KEPT_IN:
        if k.id == kept_in:
            if k.stub:
                raise NotBuilt(
                    f"keeping a variant's parameters in {k.id!r} is a stub, not built yet "
                    f"(what it will do: {k.does})"
                )
            return k
    raise ValueError(
        f"no place {kept_in!r} to keep a variant's parameters "
        f"(there are: {', '.join(k.id for k in KEPT_IN)})"
    )


def variants_repository() -> Optional[Path]:
    """``APOTHECARY_VARIANTS_REPO``: another repository to save variants into."""
    named = os.environ.get("APOTHECARY_VARIANTS_REPO", "").strip()
    return Path(named).expanduser().resolve() if named else None


def _environment() -> Dict[str, str]:
    from apothecary.stays_local import subprocess_env

    env = subprocess_env()
    # What git is pointed at is the folder it runs in; nothing inherited moves it.
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
        env.pop(name, None)
    env.update({"GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"})
    return env


def _run(repo: Path, args: List[str], input: Optional[str] = None) -> subprocess.CompletedProcess:
    """``git <args>`` in ``repo``; text in and out as UTF-8 bytes, so what is
    hashed is exactly the text given, on every platform."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo),
            input=input.encode("utf-8") if input is not None else None,
            capture_output=True,
            env=_environment(),
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitError(f"git {args[0]}: {exc}") from None


def _git(repo: Path, *args: str, input: Optional[str] = None, ok: tuple = (0,)) -> str:
    done = _run(repo, list(args), input)
    out = done.stdout.decode("utf-8", errors="replace")
    if done.returncode not in ok:
        said = done.stderr.decode("utf-8", errors="replace").strip() or out.strip()
        raise GitError(f"git {args[0]}: {said}")
    return out


def _verify(repo: Path, rev: str) -> Optional[str]:
    """The object ``rev`` names, or None when it names nothing."""
    out = _git(repo, "rev-parse", "--verify", "--quiet", rev, ok=(0, 1, 128))
    return out.strip() or None


def repository_of(path: Path) -> Path:
    """The top of the git repository holding ``path``."""
    folder = Path(path).resolve()
    folder = folder if folder.is_dir() else folder.parent
    try:
        top = _git(folder, "rev-parse", "--show-toplevel").strip()
    except GitError:
        raise NotInGit(f"{path} is not in a git repository") from None
    return Path(top)


def _segment(text: str) -> str:
    """``text`` as one component of a ref name."""
    seg = re.sub(r"[^A-Za-z0-9_.-]", "_", text).strip(".") or "part"
    seg = seg.replace("..", "_")
    return seg[:-5] + "_lock" if seg.endswith(".lock") else seg


def check_name(name: str) -> str:
    """A variant's name, or ValueError: letters, digits, ``_ . -``, not starting
    or ending with a dot or a dash, no ``..``, at most 64 characters."""
    if not isinstance(name, str) or not NAME_PATTERN.match(name) or ".." in name:
        raise ValueError(
            f"{name!r} is not a variant name: letters, digits, _ . and -, at most 64, "
            "starting with a letter or digit and not ending with . or -"
        )
    if name.endswith(".lock"):
        raise ValueError(f"{name!r} is not a variant name: it may not end with .lock")
    return name


def part_refs(part: BasePart) -> str:
    """Where a part's saved variants are: ``refs/apothecary/variants/<part>``."""
    return f"{REF_ROOT}/{_segment(part.name)}"


def ref_for(part: BasePart, name: str) -> str:
    return f"{part_refs(part)}/{check_name(name)}"


class MergeAdvice(BaseModel):
    """What making a saved variant the part's source takes, said truly."""

    repository: str = Field(description="Where the ref lives: '.' for this checkout, else its path")
    checkout: str = Field(description="Where the person merges: '.' for this checkout")
    commands: List[str] = Field(
        description="What to run in the checkout, in order: a fetch first where the ref "
        "lives in another repository"
    )
    applies_params: bool = Field(
        True,
        description="Whether a merge applies the variant's values: it does, they are in its "
        "text; not for a .variant.json variant, whose values are in a file a merge does "
        "not apply",
    )
    advice: str = Field(description="All of it in a sentence or two, for a status line")


class SavedVariant(BaseModel):
    """A part's variant saved in git: what a page lists, and opens."""

    part: str
    name: str
    ref: str
    commit: str
    parent: Optional[str] = None
    author: str = Field(description="Who saved it, as git names them")
    author_email: str
    date: str = Field(description="When, ISO 8601")
    subject: str
    scad_path: str = Field(
        description="The SCAD saved, from the top of the checkout: the part's own, or for "
        "a part in a submodule its overlay"
    )
    kind: str = Field(
        KIND_SCAD,
        description='"scad": the part\'s SCAD as edited; "overlay": a part in a submodule, '
        "saved as a SCAD that includes the upstream file and sets the variant's values",
    )
    upstream: Optional[str] = Field(
        None, description="An overlay's upstream SCAD, from the top of the checkout"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="What its text sets otherwise than the part's own, by the names its SCAD uses",
    )
    merged: bool = Field(description="HEAD already holds it")
    scad: Optional[str] = Field(None, description="Its SCAD, when one variant is read")
    diff: Optional[str] = Field(
        None,
        description="What it changes: a unified diff of its SCAD against the part's SCAD "
        "as it is on disk, when asked for (empty: the same)",
    )
    repository: str = Field(
        ".", description="Where its ref lives: '.' for this checkout, else that repository's path"
    )
    values_in: str = Field(
        KEEP_DEFAULT,
        description='Where its commit keeps its values: "text"; "variant-file" for one whose '
        "commit keeps them in <stem>.variant.json, and whose scad here has them written in",
    )
    deleted: bool = Field(
        False, description="It is in the trash (refs/apothecary/trash/), restorable"
    )
    merge: Optional[MergeAdvice] = Field(
        None, description="What making it the part's source takes, and what it does not do"
    )


class _Where(NamedTuple):
    repo: Path  # where git runs: the checkout's repository, or APOTHECARY_VARIANTS_REPO
    scad: PurePosixPath  # the SCAD saved, from the top of the checkout
    checkout: Path  # the checkout the part is in: a submodule's superproject
    kind: str = KIND_SCAD
    upstream: Optional[PurePosixPath] = None  # an overlay's upstream SCAD

    @property
    def params(self) -> PurePosixPath:
        stem = self.scad.name[: -len(OVERLAY_SUFFIX)] if self.overlay else self.scad.stem
        return self.scad.with_name(f"{stem}{PARAMS_SUFFIX}")

    @property
    def overlay(self) -> bool:
        return self.kind == KIND_OVERLAY


def superproject_of(top: Path) -> Optional[Path]:
    """The checkout the repository at ``top`` is a submodule of, or None."""
    try:
        out = _git(top, "rev-parse", "--show-superproject-working-tree").strip()
    except GitError:
        return None
    return Path(out).resolve() if out else None


def _where(part: BasePart, repo: Optional[Path] = None) -> _Where:
    """Where git runs for a part's variants, and the path of what is saved in
    the tree. ``repo``: the checkout holding the part, when the caller knows it.
    A part whose SCAD is in a submodule is saved in the outermost checkout, as
    an overlay beside the submodule."""
    top = Path(repo).resolve() if repo is not None else repository_of(part.source_file)
    # The repository the SCAD is in, then each it is a submodule of, outward.
    chain = [top]
    while repo is None:
        above = superproject_of(chain[-1])
        if above is None or above in chain:
            break
        chain.append(above)
    outer = chain[-1]
    try:
        rel = part.source_file.resolve().relative_to(outer.resolve())
    except ValueError:
        raise NotInGit(f"{part.name}'s SCAD is not in the repository at {outer}") from None
    scad = PurePosixPath(rel.as_posix())
    if len(chain) == 1:
        return _Where(variants_repository() or top, scad, top)
    # Beside the submodule of the outermost checkout that the SCAD is in.
    module = PurePosixPath(chain[-2].relative_to(outer).as_posix())
    overlay = module.parent / f"{part.source_file.stem}{OVERLAY_SUFFIX}"
    return _Where(variants_repository() or outer, overlay, outer, KIND_OVERLAY, scad)


def shown_repository(path: Path) -> str:
    """A repository as an answer names it: '.' for this checkout, its path from
    here for one inside it, else its own path."""
    from .skeleton import ROOT

    here = ROOT.resolve()
    path = Path(path).resolve()
    if path == here:
        return "."
    try:
        return path.relative_to(here).as_posix()
    except ValueError:
        return str(path)


def merge_advice(
    part: BasePart, where: _Where, ref: str, values_in: str = KEEP_DEFAULT, old: bool = False
) -> MergeAdvice:
    """What making the variant at ``ref`` the part's source takes, and what it
    does: where the ref lives, the commands, and that its values come with it
    (``values_in`` "text"), or, for a .variant.json variant (``old``), that
    they do not."""
    repository, checkout = shown_repository(where.repo), shown_repository(where.checkout)
    here = "this checkout" if checkout == "." else checkout
    commands = []
    if where.repo.resolve() != where.checkout.resolve():
        commands.append(f"git fetch {where.repo} {ref}:{ref}")
    commands.append(f"git merge {ref}")
    elsewhere = (
        f"The ref is in {repository}, not {here}: `{commands[0]}` there brings it, then "
        if len(commands) > 1
        else f"In {here}, "
    )
    if where.overlay:
        does = (
            f"`git merge {ref}` adds {where.scad}, which includes {where.upstream} and sets "
            f"the variant's values; the submodule and the part {part.name} are not changed, "
            "and the part is still drawn from its own SCAD with its own defaults."
        )
    elif old:
        does = (
            f"`git merge {ref}` makes the variant's SCAD the part's. Its commit keeps its "
            f"values in {where.params.name}, which a merge does not apply. Saved again, they "
            "are written into its SCAD, and a merge applies them."
        )
    else:
        does = (
            f"`git merge {ref}` makes the variant's SCAD the part's, its values with it: they "
            "are its assignments, so the part is drawn with them."
        )
    return MergeAdvice(
        repository=repository,
        checkout=checkout,
        commands=commands,
        applies_params=not old,
        advice=elsewhere + does,
    )


# --- writing a tree with mktree -----------------------------------------------------


class _Entry(NamedTuple):
    mode: str
    kind: str
    oid: str
    name: str


def _ls_tree(repo: Path, tree: Optional[str]) -> List[_Entry]:
    if tree is None:
        return []
    entries = []
    for record in _git(repo, "ls-tree", "-z", tree).split("\0"):
        if not record:
            continue
        head, name = record.split("\t", 1)
        mode, kind, oid = head.split(" ")
        entries.append(_Entry(mode, kind, oid, name))
    return entries


def _mktree(repo: Path, entries: List[_Entry]) -> str:
    text = "".join(f"{e.mode} {e.kind} {e.oid}\t{e.name}\0" for e in entries)
    return _git(repo, "mktree", "-z", input=text).strip()


def _with_files(
    repo: Path, tree: Optional[str], folders: List[str], files: Mapping[str, Optional[str]]
) -> str:
    """``tree`` with ``files`` ({name: blob, or None to remove it}) put in the
    folder ``folders`` down, every tree on the way written again: the new root
    tree's id."""
    entries = _ls_tree(repo, tree)
    if folders:
        here, below = folders[0], folders[1:]
        sub = next((e for e in entries if e.name == here), None)
        if sub is not None and sub.kind != "tree":
            raise GitError(f"{here} is a {sub.kind} in the tree, not a folder (a submodule?)")
        new = _with_files(repo, sub.oid if sub else None, below, files)
        entries = [e for e in entries if e.name != here] + [_Entry("040000", "tree", new, here)]
    else:
        for name, oid in files.items():
            if oid is None:  # removed
                entries = [e for e in entries if e.name != name]
                continue
            old = next((e for e in entries if e.name == name), None)
            if old is not None and old.kind == "tree":
                raise GitError(f"{name} is a folder in the tree, not a file")
            # A file keeps its mode (executable or not); anything else is a plain file.
            mode = old.mode if old is not None and old.mode in ("100644", "100755") else "100644"
            entries = [e for e in entries if e.name != name] + [_Entry(mode, "blob", oid, name)]
    return _mktree(repo, entries)


# --- saving -------------------------------------------------------------------------


FIRST_SAVED = "It was first saved on top of"
_FIRST_SAVED = re.compile(FIRST_SAVED + r" ([0-9a-f]{40,64})\.")


def _first_saved(base: Optional[str]) -> str:
    """The sentence that keeps where a variant's history begins: prose, not a trailer."""
    return f"\n{FIRST_SAVED} {base}.\n" if base else ""


def _message(part: BasePart, name: str, where: _Where, base: Optional[str] = None) -> str:
    """The commit's message: what is now true, what it holds, and the commit
    the variant was first saved on top of. No trailer."""
    if where.overlay:
        return (
            f"{part.name} is saved as the variant {name}\n\n"
            f"An overlay ({where.scad}) that includes the part's SCAD in its\n"
            f"submodule ({where.upstream}) and sets the variant's values. The\n"
            f"submodule is not changed.\n" + _first_saved(base)
        )
    return (
        f"{part.name} is saved as the variant {name}\n\n"
        f"The part's SCAD as edited in the viewer ({where.scad}), its values\n"
        f"in its text.\n" + _first_saved(base)
    )


def save_variant(
    part: BasePart,
    name: str,
    scad: Optional[str] = None,
    params: Optional[Mapping[str, Any]] = None,
    repo: Optional[Path] = None,
    kept_in: str = KEEP_DEFAULT,
) -> SavedVariant:
    """Commit ``scad`` -- the part's text, its values in it -- to the part's
    variant ``name``, with git's plumbing only. ``params``, from a caller that
    sends values on the side, are written into the text first; no file
    of parameters is written, and one the variant's last save had goes. Its
    parent is the variant's last save, else ``HEAD``; its message says the
    commit it was first saved on top of. Saving what the variant already holds
    makes no commit. ValueError for a bad name, a part whose SCAD is
    generated, or a place to keep its values that is a stub (``NotBuilt``);
    ``Moved`` when the variant was saved meanwhile; ``GitError`` with git's own
    words else (no identity configured, for one).

    A part in a submodule is saved as its overlay, the text its editor holds
    (``texts.as_edited``): its upstream SCAD as it stands is the overlay
    setting nothing, and any other text that is no overlay is an edit of the
    upstream file, ``UpstreamEdit``."""
    from .texts import as_edited, with_params

    refuse_read_only(part)
    keeping(kept_in)
    ref = ref_for(part, name)
    where = _where(part, repo)
    text = with_params(part, as_edited(part, scad), params)
    repo = where.repo
    old = _verify(repo, f"{ref}^{{commit}}")
    parent = old or _verify(repo, "HEAD^{commit}")
    first = _base_of(repo, where, old) if old else parent
    return _commit_text(
        part, name, where, ref, text, old, parent, _message(part, name, where, first)
    )


def _commit_text(
    part: BasePart,
    name: str,
    where: _Where,
    ref: str,
    text: str,
    old: Optional[str],
    parent: Optional[str],
    message: str,
) -> SavedVariant:
    """A commit on ``ref`` whose tree is ``parent``'s with ``text`` as the
    variant's SCAD (and the variant's own old parameters file gone), moved to
    from ``old``; none when the tree would not change."""
    repo = where.repo
    base = _verify(repo, f"{parent}^{{tree}}") if parent else None
    blob = _git(repo, "hash-object", "-w", "--stdin", input=text).strip()
    files: Dict[str, Optional[str]] = {where.scad.name: blob}
    if old is not None and _blob(repo, old, where.params) is not None:
        files[where.params.name] = None  # its values are in its text
    tree = _with_files(
        repo,
        base,
        list(where.scad.parent.parts) if str(where.scad.parent) != "." else [],
        files,
    )
    if old is not None and tree == base:
        return _variants(part, where, ref, with_scad=False)[0]

    args = ["commit-tree", tree, "-F", "-"]
    if parent:
        args[2:2] = ["-p", parent]
    commit = _git(repo, *args, input=message).strip()
    try:
        # The old value: the ref must still be where it was read, or not be at all.
        _git(repo, "update-ref", "-m", f"apothecary: save {name}", ref, commit, old or "")
    except GitError:
        if _verify(repo, f"{ref}^{{commit}}") != old:
            raise Moved(f"{ref} was saved meanwhile: read it, and save again") from None
        raise
    return _variants(part, where, ref, with_scad=False)[0]


# --- reading ------------------------------------------------------------------------

_FORMAT = "%00".join(
    [
        "%(refname)",
        "%(objectname)",
        "%(parent)",
        "%(authorname)",
        "%(authoremail:trim)",
        "%(authordate:iso-strict)",
        "%(subject)",
    ]
)


def _blob(repo: Path, commit: str, path: PurePosixPath) -> Optional[str]:
    out = _git(repo, "cat-file", "-p", f"{commit}:{path}", ok=(0, 128))
    return out if out else None


def _served(part: BasePart, where: _Where, commit: str) -> tuple:
    """A variant's text at ``commit`` as it is served, and where its commit keeps
    its values: (text, values_in, whether a file kept values it does not). A
    .variant.json variant has the parameters that file keeps written into its
    SCAD (an overlay's text has them already)."""
    from .texts import with_params

    text = _blob(where.repo, commit, where.scad) or ""
    kept = _blob(where.repo, commit, where.params)
    if kept is None:
        return text, KEEP_DEFAULT, False
    try:
        params = dict(json.loads(kept).get("params") or {})
    except (ValueError, AttributeError):
        params = {}
    if where.overlay or not params:
        return text, IN_FILE, False
    try:
        return with_params(part, text, params), IN_FILE, True
    except (TypeError, ValueError):
        return text, IN_FILE, True


def _shown_params(part: BasePart, text: str) -> Dict[str, Any]:
    """What a variant's text sets otherwise than the part's own."""
    from .assignments import differences
    from .texts import own_text

    try:
        return differences(text, own_text(part))
    except OSError:
        return {}


def _diff(part: BasePart, where: _Where, scad: Optional[str]) -> str:
    """A variant's SCAD against the part's as it is on disk, as ``git diff`` shows
    one; an overlay against the file at its path, which is none until merged."""
    on_disk = where.checkout / where.scad if where.overlay else part.source_file
    try:
        own = on_disk.read_text(encoding="utf-8")
    except OSError:
        own = ""
    return "".join(
        difflib.unified_diff(
            own.splitlines(keepends=True),
            (scad or "").splitlines(keepends=True),
            fromfile=f"a/{where.scad}",
            tofile=f"b/{where.scad}",
        )
    )


def _variants(
    part: BasePart,
    where: _Where,
    pattern: str,
    with_scad: bool,
    with_diff: bool = False,
    root: str = REF_ROOT,
) -> List[SavedVariant]:
    repo = where.repo
    head = _verify(repo, "HEAD^{commit}")
    lines = _git(
        repo, "for-each-ref", "--sort=-creatordate", f"--format={_FORMAT}", pattern
    ).splitlines()
    prefix = f"{root}/{_segment(part.name)}/"
    found = []
    for line in lines:
        ref, commit, parent, author, email, date, subject = line.split("\0")
        if not ref.startswith(prefix):
            continue
        name = ref[len(prefix) :]
        scad, values_in, old = _served(part, where, commit)
        merged = (
            head is not None
            and _run(repo, ["merge-base", "--is-ancestor", commit, head]).returncode == 0
        )
        found.append(
            SavedVariant(
                part=part.name,
                name=name,
                ref=ref,
                commit=commit,
                parent=parent.split(" ")[0] or None,
                author=author,
                author_email=email,
                date=date,
                subject=subject,
                scad_path=str(where.scad),
                kind=where.kind,
                upstream=str(where.upstream) if where.upstream else None,
                params=_shown_params(part, scad),
                merged=merged,
                scad=scad if with_scad else None,
                diff=_diff(part, where, scad) if with_diff else None,
                repository=shown_repository(where.repo),
                values_in=values_in,
                merge=merge_advice(part, where, ref, values_in, old) if root == REF_ROOT else None,
                deleted=root == TRASH_ROOT,
            )
        )
    return found


def list_saved(
    part: BasePart, repo: Optional[Path] = None, with_diff: bool = False
) -> List[SavedVariant]:
    """The part's saved variants, newest first, from its refs; with what each
    changes, when ``with_diff``."""
    where = _where(part, repo)
    return _variants(part, where, part_refs(part) + "/", with_scad=False, with_diff=with_diff)


def saved_names(part: BasePart) -> List[str]:
    """The names of a part's saved variants, newest first: what a ring offers to
    choose from. None outside git."""
    try:
        where = _where(part)
        out = _git(
            where.repo,
            "for-each-ref",
            "--sort=-creatordate",
            "--format=%(refname)",
            part_refs(part) + "/",
        )
    except GitError:
        return []
    prefix = part_refs(part) + "/"
    return [line[len(prefix) :] for line in out.splitlines() if line.startswith(prefix)]


def read_saved(
    part: BasePart, name: str, repo: Optional[Path] = None, with_scad: bool = True
) -> SavedVariant:
    """One saved variant, with its SCAD; ``NoSuchVariant`` when there is none."""
    where = _where(part, repo)
    ref = ref_for(part, name)
    found = [v for v in _variants(part, where, ref, with_scad) if v.ref == ref]
    if not found:
        raise NoSuchVariant(f"{part.name} has no saved variant {name!r}")
    return found[0]


# --- managing them: rename, duplicate, history, restore, the trash --------------------


def trash_refs(part: BasePart) -> str:
    """Where a part's deleted variants are: ``refs/apothecary/trash/<part>``."""
    return f"{TRASH_ROOT}/{_segment(part.name)}"


def trash_ref_for(part: BasePart, name: str) -> str:
    return f"{trash_refs(part)}/{check_name(name)}"


def _base_of(repo: Path, where: _Where, commit: Optional[str]) -> Optional[str]:
    """The commit a variant was first saved on: as the message of ``commit``
    says it, or, for a .variant.json variant, as that file keeps it."""
    if not commit:
        return None
    said = _FIRST_SAVED.search(_git(repo, "log", "-1", "--format=%B", commit))
    if said:
        return said.group(1)
    try:
        base = json.loads(_blob(repo, commit, where.params) or "{}").get("base")
    except ValueError:
        return None
    return base if isinstance(base, str) and re.match(r"^[0-9a-f]{40,64}$", base) else None


def _transaction(repo: Path, lines: List[str], taken: str) -> None:
    """``lines`` as one ``update-ref --stdin`` transaction: all of it, or none.
    A ref that is there already where one is created is ``Taken`` (``taken``
    says what); one that moved meanwhile is ``Moved``."""
    done = _run(repo, ["update-ref", "--stdin"], "\n".join(lines) + "\n")
    if done.returncode == 0:
        return
    said = done.stderr.decode("utf-8", errors="replace").strip()
    if "exists" in said:
        raise Taken(taken)
    if "unable to resolve" in said or "but expected" in said or "is at" in said:
        raise Moved(f"it was changed meanwhile: read it again ({said})")
    raise GitError(f"git update-ref: {said}")


def _tip(repo: Path, ref: str, name: str, part: BasePart) -> str:
    tip = _verify(repo, f"{ref}^{{commit}}")
    if tip is None:
        raise NoSuchVariant(f"{part.name} has no saved variant {name!r}")
    return tip


def rename_variant(part: BasePart, name: str, to: str, repo: Optional[Path] = None) -> SavedVariant:
    """The variant ``name`` called ``to``: its ref moved, its commits as they
    are (the name inside its record is the one it was saved under). ``Taken``
    when a variant is called ``to`` already."""
    where = _where(part, repo)
    old, new = ref_for(part, name), ref_for(part, to)
    tip = _tip(where.repo, old, name, part)
    _transaction(
        where.repo,
        [f"create {new} {tip}", f"delete {old} {tip}"],
        f"{part.name} has a variant {to!r} already: choose another name",
    )
    return read_saved(part, to, repo, with_scad=False)


def duplicate_variant(
    part: BasePart, name: str, to: str, repo: Optional[Path] = None
) -> SavedVariant:
    """A second variant ``to`` where ``name`` is: a ref of its own on the same
    commit, which then goes its own way. ``Taken`` when ``to`` is a variant."""
    where = _where(part, repo)
    tip = _tip(where.repo, ref_for(part, name), name, part)
    _transaction(
        where.repo,
        [f"create {ref_for(part, to)} {tip}"],
        f"{part.name} has a variant {to!r} already: choose another name",
    )
    return read_saved(part, to, repo, with_scad=False)


class VariantCommit(BaseModel):
    """One save of a variant, as its history lists it."""

    commit: str
    parent: Optional[str] = None
    author: str
    author_email: str
    date: str = Field(description="When, ISO 8601")
    subject: str
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="What its text set otherwise than the part's own, by the names its SCAD uses",
    )
    current: bool = Field(description="The variant is this commit now")


_LOG_FORMAT = "%x00".join(["%H", "%P", "%an", "%ae", "%aI", "%s"])


def _own_commits(repo: Path, where: _Where, part: BasePart, tip: str) -> List[str]:
    """The variant's own commits, newest first: from ``tip`` back along first
    parents to the commit it was first saved on, not included. A variant whose
    tip names no such commit (``_base_of``) is followed while its commits are
    saves of the part's variants (their subjects say so)."""
    base = _base_of(repo, where, tip)
    if base and _verify(repo, f"{base}^{{commit}}"):
        out = _git(repo, "rev-list", "--first-parent", tip, f"^{base}")
        return [line for line in out.splitlines() if line]
    found, current = [], tip
    while current:
        subject = _git(repo, "log", "-1", "--format=%s", current).strip()
        if not subject.startswith(f"{part.name} is saved as the variant ") and not (
            subject.startswith(f"{part.name}'s variant ")
        ):
            break
        found.append(current)
        current = _verify(repo, f"{current}^1^{{commit}}")
    return found


def variant_history(
    part: BasePart, name: str, repo: Optional[Path] = None, deleted: bool = False
) -> List[VariantCommit]:
    """The commits of the variant ``name`` (in the trash, with ``deleted``),
    newest first, each with the parameters it was saved with."""
    where = _where(part, repo)
    ref = trash_ref_for(part, name) if deleted else ref_for(part, name)
    tip = _tip(where.repo, ref, name, part)
    history = []
    for commit in _own_commits(where.repo, where, part, tip):
        line = _git(where.repo, "log", "-1", f"--format={_LOG_FORMAT}", commit).rstrip("\n")
        sha, parents, author, email, date, subject = line.split("\0")
        text, _, _ = _served(part, where, sha)
        history.append(
            VariantCommit(
                commit=sha,
                parent=parents.split(" ")[0] or None,
                author=author,
                author_email=email,
                date=date,
                subject=subject,
                params=_shown_params(part, text),
                current=sha == tip,
            )
        )
    return history


def restore_variant(
    part: BasePart, name: str, commit: str, repo: Optional[Path] = None
) -> SavedVariant:
    """The variant ``name`` as it was at ``commit``, one of its own: a new commit
    on its ref with that commit's text (its values in it: a .variant.json
    variant's are written in), so its history keeps what it was in between. Restoring
    what it holds makes no commit. ``NoSuchVariant`` for a commit that is not
    one of its own."""
    where = _where(part, repo)
    ref = ref_for(part, name)
    tip = _tip(where.repo, ref, name, part)
    own = _own_commits(where.repo, where, part, tip)
    chosen = next(
        (c for c in own if c == commit or (len(commit) >= 7 and c.startswith(commit))), None
    )
    if chosen is None:
        raise NoSuchVariant(
            f"{commit!r} is not one of the commits of {part.name}'s variant {name!r}"
        )
    text, _, _ = _served(part, where, chosen)
    current, _, _ = _served(part, where, tip)
    if text == current and _blob(where.repo, tip, where.params) is None:
        return read_saved(part, name, repo, with_scad=False)
    when = _git(where.repo, "log", "-1", "--format=%aI", chosen).strip()
    message = (
        f"{part.name}'s variant {name} is restored to {chosen[:12]}\n\n"
        f"Its SCAD, its values in it, as it was saved in {chosen[:12]} ({when}).\n"
        + _first_saved(_base_of(where.repo, where, tip))
    )
    return _commit_text(part, name, where, ref, text, tip, tip, message)


def delete_variant(part: BasePart, name: str, repo: Optional[Path] = None) -> SavedVariant:
    """The variant ``name`` moved to the trash, ``refs/apothecary/trash/<part>/<name>``:
    its commits kept, listed with ``list_trash``, restorable. ``Taken`` while a
    deleted variant of that name is in the trash already (restore it, or empty
    the trash, first): the trash keeps each one until it is emptied."""
    where = _where(part, repo)
    live, trash = ref_for(part, name), trash_ref_for(part, name)
    tip = _tip(where.repo, live, name, part)
    _transaction(
        where.repo,
        [f"create {trash} {tip}", f"delete {live} {tip}"],
        f"a deleted variant {name!r} of {part.name} is in the trash already: restore it, "
        "or empty the trash, first",
    )
    return _read_trash(part, name, repo)


def _read_trash(part: BasePart, name: str, repo: Optional[Path] = None) -> SavedVariant:
    where = _where(part, repo)
    ref = trash_ref_for(part, name)
    found = [
        v for v in _variants(part, where, ref, with_scad=False, root=TRASH_ROOT) if v.ref == ref
    ]
    if not found:
        raise NoSuchVariant(f"{part.name} has no deleted variant {name!r} in the trash")
    return found[0]


def list_trash(part: BasePart, repo: Optional[Path] = None) -> List[SavedVariant]:
    """The part's deleted variants, newest save first: the trash."""
    where = _where(part, repo)
    return _variants(part, where, trash_refs(part) + "/", with_scad=False, root=TRASH_ROOT)


def restore_from_trash(
    part: BasePart, name: str, to: Optional[str] = None, repo: Optional[Path] = None
) -> SavedVariant:
    """The deleted variant ``name`` back among the part's variants, as ``to`` or
    its own name; ``Taken`` while a variant is called that."""
    where = _where(part, repo)
    trash = trash_ref_for(part, name)
    tip = _verify(where.repo, f"{trash}^{{commit}}")
    if tip is None:
        raise NoSuchVariant(f"{part.name} has no deleted variant {name!r} in the trash")
    back = to or name
    _transaction(
        where.repo,
        [f"create {ref_for(part, back)} {tip}", f"delete {trash} {tip}"],
        f"{part.name} has a variant {back!r}: restore the deleted one under another name",
    )
    return read_saved(part, back, repo, with_scad=False)


def empty_trash(
    part: BasePart, name: Optional[str] = None, repo: Optional[Path] = None
) -> List[str]:
    """The trash emptied -- every deleted variant of the part, or ``name``'s --
    its refs deleted: the names emptied. What only they kept, git collects in
    its own time."""
    where = _where(part, repo)
    if name is not None:
        refs = [trash_ref_for(part, name)]
        if _verify(where.repo, f"{refs[0]}^{{commit}}") is None:
            raise NoSuchVariant(f"{part.name} has no deleted variant {name!r} in the trash")
    else:
        out = _git(where.repo, "for-each-ref", "--format=%(refname)", trash_refs(part) + "/")
        refs = [line for line in out.splitlines() if line]
    if not refs:
        return []
    tips = [_verify(where.repo, f"{ref}^{{commit}}") for ref in refs]
    _transaction(
        where.repo,
        [f"delete {ref} {tip}" for ref, tip in zip(refs, tips, strict=True)],
        "the trash changed meanwhile",
    )
    prefix = trash_refs(part) + "/"
    return [ref[len(prefix) :] for ref in refs]


__all__ = [
    "GitError",
    "KEEP_DEFAULT",
    "KEPT_IN",
    "KIND_OVERLAY",
    "IN_FILE",
    "KIND_SCAD",
    "Keeping",
    "MergeAdvice",
    "Moved",
    "NoSuchVariant",
    "NotBuilt",
    "NotInGit",
    "OVERLAY_SUFFIX",
    "PARAMS_SUFFIX",
    "REF_ROOT",
    "SavedVariant",
    "TRASH_ROOT",
    "Taken",
    "UpstreamEdit",
    "VariantCommit",
    "check_name",
    "keeping",
    "delete_variant",
    "duplicate_variant",
    "empty_trash",
    "list_saved",
    "list_trash",
    "merge_advice",
    "read_saved",
    "rename_variant",
    "restore_from_trash",
    "restore_variant",
    "ref_for",
    "repository_of",
    "save_variant",
    "saved_names",
    "shown_repository",
    "superproject_of",
    "trash_ref_for",
    "trash_refs",
    "variant_history",
    "variants_repository",
]
