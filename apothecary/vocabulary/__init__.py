"""Words: named, reusable pieces that arrangements are built from.

A word has a name, a short description of what it is, and a recipe that builds
an ordinary assembly node in whatever size is asked for. Ask for the same word
twice and you get two of them; ask by name and you always get the same thing.

PROTOTYPE — not ratified. See ``docs/plans/edits/apothecary-model.md``.
"""

from .match import Choice, Rule, word_for
from .starter import starter_words
from .word import UnknownWordError, Word, WordList, WordShape

__all__ = [
    "Choice",
    "Rule",
    "UnknownWordError",
    "Word",
    "WordList",
    "WordShape",
    "starter_words",
    "word_for",
]
