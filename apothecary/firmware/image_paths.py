"""No build path in a flashed image: the check a Rust build ends with.

A build names the folders it was made in -- the sketch's, the toolchain's,
the vendored crates', and so the person's home and user name -- in panic
messages and debug information, unless rustc is told to write them another
way (``--remap-path-prefix``, which the Rust module passes for each of them).
This is what holds that it did: it reads the built ELF, every byte of it,
debug information included (a superset of what is flashed), and fails the
build if any of the folders it is given is in it.

    python -m apothecary.firmware.image_paths ELF --refuse /home/pk --refuse /repo ...

Exit 0 when none is there, 1 naming each one found and where, 2 when the ELF
cannot be read. Stdlib only, so it runs as the task's step in a process of its
own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable, List


def found_in(data: bytes, prefixes: Iterable[str]) -> Dict[str, List[int]]:
    """Each prefix that occurs in ``data``, with the first offsets it occurs at --
    as written, and with a Windows path's other slash."""
    hits: Dict[str, List[int]] = {}
    for prefix in prefixes:
        if not prefix:
            continue
        for form in dict.fromkeys([prefix, prefix.replace("\\", "/"), prefix.replace("/", "\\")]):
            needle = form.encode("utf-8")
            at, offsets = data.find(needle), []
            while at >= 0 and len(offsets) < 5:
                offsets.append(at)
                at = data.find(needle, at + 1)
            if offsets:
                hits.setdefault(prefix, []).extend(offsets)
    return hits


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("elf", type=Path)
    parser.add_argument(
        "--refuse", action="append", default=[], help="a folder that may not appear"
    )
    args = parser.parse_args(argv)
    try:
        data = args.elf.read_bytes()
    except OSError as exc:
        print(f"cannot read {args.elf}: {exc}", file=sys.stderr)
        return 2
    hits = found_in(data, args.refuse)
    if hits:
        for prefix, offsets in hits.items():
            print(f"build path in the image: {prefix} (at byte {', '.join(map(str, offsets))})")
        print(f"{args.elf.name}: refused -- a flashed image may not name where it was built")
        return 1
    print(f"{args.elf.name}: no build path in the image ({len(args.refuse)} folders checked)")
    return 0


if __name__ == "__main__":  # pragma: no cover - run as the build's last step
    sys.exit(main())
