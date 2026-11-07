"""The state folder: where what is kept about this machine lives, and how a record
reaches it.

What Apothecary keeps about a person's machine -- flash records, pins, bed
readings, kept files, jobs, cameras, evidence, the family's table -- is kept
under one folder, ``~/.apothecary`` (``APOTHECARY_STATE_DIR`` names another):
machine state, not repository state, so it is never committed, and the
person's own, so each folder in it is readable by this account alone. This
module is the one place that knows where the folder is and how a record is
written there whole; every package that keeps a record imports it, and none
reaches into another package for it.
"""

# An install point of the guard (apothecary/stays_local.py), before any code of
# this module runs: what is under the state folder is the person's.
from .stays_local import install_guard as _install_guard

_install_guard()

import os  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402


def state_dir() -> Path:
    """The state folder: ``APOTHECARY_STATE_DIR``, else ``~/.apothecary``."""
    override = os.environ.get("APOTHECARY_STATE_DIR", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".apothecary"


def private_folder(folder: Path) -> Path:
    """Make ``folder`` (and what is above it, up to the state folder) readable by
    this account alone: serial numbers, camera labels and readings are the
    person's, whatever the umask says about the rest of their files."""
    folder.mkdir(parents=True, exist_ok=True)
    root = state_dir()
    for here in [folder, *folder.parents]:
        try:
            os.chmod(here, 0o700)
        except OSError:
            pass
        if here == root or root not in here.parents:
            break
    return folder


def write_whole(path: Path, text: str) -> Path:
    """``text`` at ``path``, whole or not at all: written beside it under a hidden
    name in a folder made the person's, then moved into place, so a reader never
    meets half a record and a write that stops midway leaves the file that was
    there."""
    private_folder(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
