"""A saved edit is a variant in git.

Saving commits a part's SCAD as edited, and the parameters it is drawn with,
to a ref of the part's own -- ``refs/apothecary/variants/<part>/<name>`` -- in
the repository that tracks the part's SCAD (decided 2026-09-27, see
docs/plans/part-editing-in-the-browser-2026-09-27.md). It is built with git's
plumbing alone:

1. ``git hash-object -w --stdin`` writes the SCAD and the parameters as blobs;
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

The commit's tree is the tree it was based on, with the part's SCAD as edited
and, beside it, ``<stem>.variant.json``: the variant's name and its
parameters. So ``git diff HEAD <ref>`` is the edit, ``git log <ref>`` its
history, and pushing the ref shares it. Making a variant the part's source is
a merge the person does (``git merge <ref>``); nothing here writes the working
tree. Listing a part's variants reads its refs (``git for-each-ref``), each
with whether ``HEAD`` already holds it.

Every git here is told to fetch nothing: a partial clone would otherwise
fetch an object it lacks (``GIT_NO_LAZY_FETCH``), and nothing may prompt.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, NamedTuple, Optional

from pydantic import BaseModel, Field
from pydantic_core import to_jsonable_python

from .base import BasePart
from .drafts import refuse_read_only

REF_ROOT = "refs/apothecary/variants"

# A variant's name: what a person would type, and a valid ref component.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}[A-Za-z0-9_]$|^[A-Za-z0-9]$")

PARAMS_SUFFIX = ".variant.json"

GIT_TIMEOUT = 30.0


class GitError(RuntimeError):
    """A git command failed; its message is git's."""


class NotInGit(GitError):
    """The part's SCAD is not in a git repository."""


class Moved(GitError):
    """The variant's ref moved between reading it and moving it: saved meanwhile."""


class NoSuchVariant(LookupError):
    """No saved variant by that name."""


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
    scad_path: str = Field(description="The part's SCAD, from the top of its repository")
    params: Dict[str, Any] = Field(default_factory=dict)
    merged: bool = Field(description="HEAD already holds it")
    scad: Optional[str] = Field(None, description="Its SCAD, when one variant is read")


class _Where(NamedTuple):
    repo: Path
    scad: PurePosixPath  # the part's SCAD from the top of the repository

    @property
    def params(self) -> PurePosixPath:
        return self.scad.with_name(f"{self.scad.stem}{PARAMS_SUFFIX}")


def _where(part: BasePart, repo: Optional[Path] = None) -> _Where:
    repo = Path(repo).resolve() if repo is not None else repository_of(part.source_file)
    try:
        rel = part.source_file.resolve().relative_to(repo.resolve())
    except ValueError:
        raise NotInGit(f"{part.name}'s SCAD is not in the repository at {repo}") from None
    return _Where(repo, PurePosixPath(rel.as_posix()))


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
    repo: Path, tree: Optional[str], folders: List[str], files: Mapping[str, str]
) -> str:
    """``tree`` with ``files`` ({name: blob}) put in the folder ``folders`` down,
    every tree on the way written again: the new root tree's id."""
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
            old = next((e for e in entries if e.name == name), None)
            if old is not None and old.kind == "tree":
                raise GitError(f"{name} is a folder in the tree, not a file")
            # A file keeps its mode (executable or not); anything else is a plain file.
            mode = old.mode if old is not None and old.mode in ("100644", "100755") else "100644"
            entries = [e for e in entries if e.name != name] + [_Entry(mode, "blob", oid, name)]
    return _mktree(repo, entries)


# --- saving -------------------------------------------------------------------------


def _message(part: BasePart, name: str, where: _Where) -> str:
    """The commit's message: what is now true, and what it holds. No trailer."""
    return (
        f"{part.name} is saved as the variant {name}\n\n"
        f"The part's SCAD as edited in the viewer ({where.scad}), and the\n"
        f"parameters the variant is drawn with in {where.params.name} beside it.\n"
    )


def save_variant(
    part: BasePart,
    name: str,
    scad: str,
    params: Optional[Mapping[str, Any]] = None,
    repo: Optional[Path] = None,
) -> SavedVariant:
    """Commit ``scad`` as the part's SCAD and ``params`` beside it to the part's
    variant ``name``, with git's plumbing only. Its parent is the variant's last
    save, else ``HEAD``. Saving what the variant already holds makes no commit.
    ValueError for a bad name or a part whose SCAD is generated; ``Moved`` when
    the variant was saved meanwhile; ``GitError`` with git's own words else (no
    identity configured, for one)."""
    refuse_read_only(part)
    ref = ref_for(part, name)
    where = _where(part, repo)
    repo = where.repo
    old = _verify(repo, f"{ref}^{{commit}}")
    parent = old or _verify(repo, "HEAD^{commit}")
    base = _verify(repo, f"{parent}^{{tree}}") if parent else None

    record = {
        "part": part.name,
        "variant": name,
        "params": to_jsonable_python(dict(params or {})),
    }
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    scad_blob = _git(repo, "hash-object", "-w", "--stdin", input=scad).strip()
    params_blob = _git(repo, "hash-object", "-w", "--stdin", input=text).strip()
    tree = _with_files(
        repo,
        base,
        list(where.scad.parent.parts) if str(where.scad.parent) != "." else [],
        {where.scad.name: scad_blob, where.params.name: params_blob},
    )
    if old is not None and tree == base:
        return read_saved(part, name, repo=repo, with_scad=False)

    args = ["commit-tree", tree, "-F", "-"]
    if parent:
        args[2:2] = ["-p", parent]
    commit = _git(repo, *args, input=_message(part, name, where)).strip()
    try:
        # The old value: the ref must still be where it was read, or not be at all.
        _git(repo, "update-ref", "-m", f"apothecary: save {name}", ref, commit, old or "")
    except GitError:
        if _verify(repo, f"{ref}^{{commit}}") != old:
            raise Moved(f"{ref} was saved meanwhile: read it, and save again") from None
        raise
    return read_saved(part, name, repo=repo, with_scad=False)


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


def _variants(part: BasePart, where: _Where, pattern: str, with_scad: bool) -> List[SavedVariant]:
    repo = where.repo
    head = _verify(repo, "HEAD^{commit}")
    lines = _git(
        repo, "for-each-ref", "--sort=-creatordate", f"--format={_FORMAT}", pattern
    ).splitlines()
    found = []
    for line in lines:
        ref, commit, parent, author, email, date, subject = line.split("\0")
        name = ref[len(part_refs(part)) + 1 :]
        try:
            record = json.loads(_blob(repo, commit, where.params) or "{}")
        except ValueError:
            record = {}
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
                params=dict(record.get("params") or {}),
                merged=merged,
                scad=_blob(repo, commit, where.scad) if with_scad else None,
            )
        )
    return found


def list_saved(part: BasePart, repo: Optional[Path] = None) -> List[SavedVariant]:
    """The part's saved variants, newest first, from its refs."""
    where = _where(part, repo)
    return _variants(part, where, part_refs(part) + "/", with_scad=False)


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


__all__ = [
    "GitError",
    "Moved",
    "NoSuchVariant",
    "NotInGit",
    "PARAMS_SUFFIX",
    "REF_ROOT",
    "SavedVariant",
    "check_name",
    "list_saved",
    "read_saved",
    "ref_for",
    "repository_of",
    "save_variant",
]
