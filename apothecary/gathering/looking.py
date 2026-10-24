"""Looking at a pile of picture files before they are gathered.

Shared by ``apothecary photo gather`` and ``POST /photos/gather``. A file the
finder cannot read (a half-downloaded photo, a HEIC, a text file) is set aside
with the reason, like a picture that gave too few shapes, and the rest are
gathered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..vision.finder import ShapeFinder
from ..vision.models import Picture
from .judgement import NOT_WORTH_USING, Judgement
from .models import Gathering, Reading

# The files taken as pictures, by suffix in any case.
PICTURE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"})


@dataclass
class Looked:
    """What the finder made of each file, in the order the files were handed in."""

    order: List[Path]
    pictures: List[Picture] = field(default_factory=list)
    paths: List[Path] = field(default_factory=list)  # where each of ``pictures`` came from
    unopened: List[Reading] = field(default_factory=list)  # one per file it could not read

    def names(self) -> List[str]:
        return [p.name for p in self.pictures] + [r.picture for r in self.unopened]

    def clash(self) -> Optional[Tuple[str, List[Path]]]:
        """The first name two files share, with those files; None if every name is its own."""
        files: Dict[str, List[Path]] = {}
        for picture, path in zip(self.pictures, self.paths, strict=True):
            files.setdefault(picture.name, []).append(path)
        for reading in self.unopened:
            files.setdefault(reading.picture, []).append(reading.path)
        shared = sorted((name, found) for name, found in files.items() if len(found) > 1)
        return shared[0] if shared else None


def look_at_each(finder: ShapeFinder, paths: Sequence[Path]) -> Looked:
    """Every file through the finder; a file it cannot read becomes an unreadable Reading."""
    looked = Looked(order=list(paths))
    for path in paths:
        try:
            picture = finder.look(path)
        except (OSError, ValueError) as exc:
            looked.unopened.append(
                Reading(
                    picture=path.stem,
                    path=path,
                    shapes_found=0,
                    readable=False,
                    because=f"the finder could not read it: {exc}",
                )
            )
            continue
        looked.pictures.append(picture)
        looked.paths.append(path)
    return looked


def set_aside_unopened(
    gathering: Gathering, looked: Looked, answers: Sequence[Judgement] = ()
) -> Gathering:
    """The gathering with every unopened file among its readings and set aside.

    Anything a person said about such a file, bar throwing it out, is ignored and
    said so: no answer makes a file the finder cannot read usable.
    """
    if not looked.unopened:
        return gathering
    place = {path: at for at, path in enumerate(looked.order)}
    readings = sorted(
        [*gathering.readings, *looked.unopened], key=lambda r: place.get(r.path, len(place))
    )
    set_aside = {**gathering.set_aside, **{r.picture: r.because for r in looked.unopened}}
    ignored = dict(gathering.ignored)
    unopened = {r.picture for r in looked.unopened}
    for said in answers:
        named = [n for n in (said.left, said.right) if n in unopened]
        if named and said.verdict != NOT_WORTH_USING:
            ignored[said.sentence()] = (
                f"the finder could not read {named[0]} at all, so this could not be used"
            )
    return gathering.model_copy(
        update={"readings": readings, "set_aside": set_aside, "ignored": ignored}
    )


__all__ = ["PICTURE_SUFFIXES", "Looked", "look_at_each", "set_aside_unopened"]
