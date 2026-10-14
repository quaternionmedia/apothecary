"""Records named for the moment they were made, and never one over another.

A bed reading, a kept G-code file, a job and a camera's frame are each a file
named for the moment it was made, to the millisecond (``stamp``:
``20261004T120000.123``), then what made it: ``20261004T120000.123-dev_ttyUSB0``.
Two made in the same millisecond -- two readings on a fast machine, two frames
taken at once -- would have the same name, and the second would be written over
the first.

``claim`` gives each its own. It makes the file only if no file has the name,
by the operating system's exclusive create, so of two threads or two processes
reaching for one name at once exactly one has it; the other takes the name
with ``-2`` after it, then ``-3``, as a view's id and an upload's name already
do. The moment stays first and whole, so a name still reads as its time and
sorts by it, and whatever reads the rest of a name reads it as before, with at
most a number after it.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


def stamp(at: datetime) -> str:
    """The moment, to the millisecond: ``20261004T120000.123``."""
    return f"{at:%Y%m%dT%H%M%S}.{at.microsecond // 1000:03d}"


def claim(folder: Path, stem: str, suffix: str) -> Path:
    """A new empty file in ``folder``, this caller's alone: ``stem`` + ``suffix``, or,
    when that name is taken, ``stem-2`` + ``suffix``, ``stem-3`` + ``suffix``… The
    record's id is the name it got; it is written into the file afterwards."""
    n = 1
    while True:
        path = folder / (f"{stem}{suffix}" if n == 1 else f"{stem}-{n}{suffix}")
        try:
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666))
        except FileExistsError:
            n += 1
            continue
        return path
