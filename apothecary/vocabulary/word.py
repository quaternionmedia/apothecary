"""A word: one named, reusable piece you can put into an arrangement.

A word is not a new kind of thing. It is a recipe that builds an ordinary
``Assembly`` node — the same node everything else in this tool is made of. What
makes it a word is that it has a name, the name is how you ask for it again, and
the recipe takes a few numbers so the same word can come out in many sizes.

A word sits alongside a part from the parts folder rather than underneath it. A
part is one drawing file plus printing notes; a word is a small tree with no
file at all.

PROTOTYPE — not ratified. See ``docs/plans/edits/apothecary-model.md``.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from ..hierarchy import Assembly


class WordShape(BaseModel):
    """The numbers every word accepts. Millimetres, unless the size is unknown.

    ``sized`` is False when the picture had no real-world reference. The numbers
    are then fractions of the picture rather than millimetres, and whatever is
    built from them is marked so nobody mistakes it for a measurement.
    """

    width: float = Field(1.0, gt=0)
    depth: float = Field(1.0, gt=0)
    height: float = Field(1.0, gt=0)
    sized: bool = True


Recipe = Callable[[str, WordShape], Assembly]


class Word(BaseModel):
    """One entry in the vocabulary."""

    model_config = {"arbitrary_types_allowed": True}

    name: str
    describes: str
    build: Recipe
    tags: List[str] = Field(default_factory=list)

    def make(self, instance_name: str, shape: Optional[WordShape] = None) -> Assembly:
        """Build one of these, named for where it will sit."""
        return self.build(instance_name, shape or WordShape())


class UnknownWordError(KeyError):
    """Asked for a word nobody registered."""


class WordList:
    """Every word that can be used, looked up by name.

    A plain dictionary rather than a scan of the disk, because words have no
    files. Names must be unique — the name is how a word is addressed inside an
    arrangement, so two words sharing one would make an address ambiguous.
    """

    def __init__(self) -> None:
        self._words: Dict[str, Word] = {}

    def add(self, word: Word) -> Word:
        if word.name in self._words:
            raise ValueError(f"a word named {word.name!r} is already registered")
        self._words[word.name] = word
        return word

    def get(self, name: str) -> Word:
        if name not in self._words:
            raise UnknownWordError(f"no word named {name!r}; have {self.names()}")
        return self._words[name]

    def names(self) -> List[str]:
        return sorted(self._words)

    def all(self) -> List[Word]:
        return [self._words[n] for n in self.names()]

    def __len__(self) -> int:
        return len(self._words)

    def __contains__(self, name: object) -> bool:
        return name in self._words


__all__ = ["Recipe", "Type", "UnknownWordError", "Word", "WordList", "WordShape"]
