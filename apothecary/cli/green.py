"""What `apothecary test changed` leaves out: a unit file, or the walkthrough, unchanged
since a run in which it passed.

A unit part that exits 0, given no further pytest argument that may narrow it, keeps a
record under the checkout's ignored ``.cache/``: for each unit file it ran, and for the walkthrough, a
digest of every file a change to which reaches it, and when. What reaches a unit file is
tests/groups.py's ``reaching``, the same rules that choose what a change runs: the
shared ground, its group's sources, the helpers that import into it, and itself. The
walkthrough's pages stand on everything outside ``tests/`` and on the shared ground.

`test changed` runs what its change reaches less what has the digest the record keeps,
and says each of those apart, as not run, unchanged since green at a time, with a count
of its own. The record is not trusted at all -- everything the change reaches runs, and
the run says why -- when it does not parse, when its seal does not match what it holds,
or when the environment it was written in is not this one: Python, the lockfile, the
conftests, tests/groups.py itself, the OpenSCAD the renders use, the tools folder, or
node.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Where the record is kept, from the checkout's root: an ignored folder (.gitignore).
# APOTHECARY_GREEN_RECORD names another file: a test session's own (conftest.py), so that
# a test's `apothecary test`, its pytest a stand-in, keeps nothing for the checkout.
RECORD = Path(".cache") / "test-changed" / "green.json"
RECORD_ENV = "APOTHECARY_GREEN_RECORD"


def record_path(root: Path) -> Path:
    """The record's file for the checkout at ``root``."""
    named = os.environ.get(RECORD_ENV, "").strip()
    return Path(named) if named else root / RECORD


VERSION = 1
WALKTHROUGH = "walkthrough"

# A digest that names no file's contents: a path the listing holds and the disk does not.
MISSING = "missing"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_digest(path: Path) -> str:
    """A file's contents' digest; a folder's (a submodule) is its commit and what its
    working tree changes; ``MISSING`` for nothing there."""
    if path.is_dir():
        head = _git(path, "rev-parse", "HEAD")
        dirty = _git(path, "status", "--porcelain")
        return _sha(f"{head}\n{dirty}".encode())
    try:
        return _sha(path.read_bytes())
    except OSError:
        return MISSING


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else f"git {args[0]} failed: {done.returncode}"


def checkout_paths(root: Path) -> list[str]:
    """Every path of the checkout a change can name: what git tracks, and what it does
    not and does not ignore."""
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True
    ).stdout
    added = subprocess.run(
        ["git", "ls-files", "-z", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted({p for p in (tracked + added).split("\0") if p})


def _stat(path) -> str:
    """Where a program is, its size and when it last changed; nothing for none."""
    if not path:
        return "none"
    try:
        found = Path(path).resolve()
        st = found.stat()
    except OSError:
        return f"{path}: not there"
    return f"{found} {st.st_size} {st.st_mtime_ns}"


def _tools(folder: Path) -> str:
    """The tools folder two levels deep, each entry with when it last changed: a tool
    installed, removed or updated there changes it."""
    lines = []
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return f"{folder}: none"
    for entry in entries:
        lines.append(f"{entry.name} {entry.stat().st_mtime_ns}")
        if entry.is_dir():
            try:
                inner = sorted(entry.iterdir())
            except OSError:
                continue
            lines += [f"{entry.name}/{p.name} {p.stat().st_mtime_ns}" for p in inner]
    return _sha("\n".join(lines).encode())


def environment(root: Path) -> dict[str, str]:
    """What a record is written in, by part: a record from another is not trusted."""
    from apothecary.firmware.toolchains import tools_dir
    from apothecary.openscad_installer import current_version
    from apothecary.projects.parts.stl_renderer import get_renderer

    def read(*names: str) -> str:
        return _sha(b"".join(_file_digest(root / name).encode() for name in names))

    return {
        "Python": f"{sys.version} at {sys.executable}",
        "the lockfile": read("uv.lock", "pyproject.toml"),
        "the conftests": read("conftest.py", "tests/conftest.py"),
        "tests/groups.py": read("tests/groups.py"),
        "OpenSCAD": f"snapshot {current_version()}; {_stat(get_renderer().openscad_path)}",
        "the tools folder": _tools(tools_dir()),
        "node": _stat(shutil.which("node")),
    }


def digests(root: Path, groups) -> dict[str, str]:
    """Each unit file's digest, and the walkthrough's: of every file a change to which
    reaches it (``groups``, tests/groups.py's map, says which)."""
    paths = checkout_paths(root)
    contents = {path: _file_digest(root / path) for path in paths}
    shared, each = groups.reaching(paths)
    unit_files = sorted(
        f"tests/{p.name}" for p in (root / "tests").glob("test_*.py") if p.is_file()
    )

    def digest(names) -> str:
        return _sha("".join(f"{p}\0{contents[p]}\n" for p in sorted(names)).encode())

    found = {test: digest(shared | each.get(test, set())) for test in unit_files}
    found[WALKTHROUGH] = digest(shared | {p for p in paths if not p.startswith("tests/")})
    return found


def _seal(body: dict) -> str:
    return _sha(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())


class Record:
    """The kept record, read: each unit file's (and the walkthrough's) digest and when it
    passed, or nothing and why the record is not trusted."""

    def __init__(self, entries: dict[str, dict], distrust: str | None = None):
        self.entries = entries
        self.distrust = distrust

    def unchanged(self, name: str, digest: str) -> str | None:
        """When ``name`` passed with ``digest``, if the record says it did."""
        entry = self.entries.get(name)
        if entry is not None and entry.get("digest") == digest:
            return entry.get("at")
        return None


def read(root: Path, env: dict[str, str]) -> Record:
    """The record as the checkout keeps it, if it is to be trusted in ``env``."""
    path = record_path(root)
    if not path.exists():
        return Record({}, f"no record of a run that passed ({path} is not there)")
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
        body = {k: kept[k] for k in ("version", "environment", "entries")}
        sealed = kept["seal"]
    except (OSError, ValueError, KeyError, TypeError):
        return Record({}, f"{path} does not read as a record")
    if sealed != _seal(body):
        return Record({}, f"{path} does not hold what its seal says: it was changed by hand")
    if body["version"] != VERSION:
        return Record({}, f"{path} is of another version of this command")
    if not isinstance(body["entries"], dict) or not isinstance(body["environment"], dict):
        return Record({}, f"{path} does not read as a record")
    moved = [part for part in env if body["environment"].get(part) != env[part]]
    if moved:
        return Record({}, f"{', '.join(moved)} changed since the record was written")
    return Record(body["entries"])


def write(root: Path, env: dict[str, str], passed: dict[str, str], at: datetime | None = None):
    """Keep ``passed`` -- each unit file (or the walkthrough) a run passed, with its
    digest from before that run -- as green now, beside what the record already holds
    in this environment."""
    if not passed:
        return
    when = (at or datetime.now(timezone.utc)).astimezone().isoformat(timespec="seconds")
    kept = read(root, env)
    entries = dict(kept.entries)
    entries.update({name: {"digest": digest, "at": when} for name, digest in passed.items()})
    body = {"version": VERSION, "environment": env, "entries": entries}
    path = record_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    scratch.write_text(json.dumps({**body, "seal": _seal(body)}, indent=1, sort_keys=True))
    os.replace(scratch, path)
