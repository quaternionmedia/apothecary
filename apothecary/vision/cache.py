"""What a finder saw in a picture, kept so the same picture is not looked at twice.

Keyed as the photo-finders plan keys it: the picture's hash, the finder (its
backend), the model's digest and the prompt's version. A finder that has no
model, or no prompt, gives an empty string for either; a finder whose answer
rests on something besides the picture's bytes names that in its digest (the
stated finder hashes the description beside the picture). So a picture changed
on disk, or a description rewritten, is a different key and is looked at anew.

Held in memory, behind its own lock, and lost on restart. Whether it may reach
the disk waits on what the draft record *Personal data stays on the device*
counts as this machine (todo.md). The lock is held for dictionary reads and
writes only, never while a finder looks: a slow finder does not hold up a
reader of anything else.

PROTOTYPE — not ratified.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional, Tuple

from .finder import ShapeFinder
from .models import Picture

# The most answers kept; the least recently used go first.
CACHE_MOST = 256

Key = Tuple[str, str, str, str]


def picture_hash(image: Path) -> str:
    """The SHA-256 of a picture's bytes."""
    digest = hashlib.sha256()
    with Path(image).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def key_for(finder: ShapeFinder, image: Path) -> Key:
    """(picture hash, backend, model digest, prompt version) for one finder and picture."""
    model = getattr(finder, "model_digest", None)
    prompt = getattr(finder, "prompt_version", "")
    return (
        picture_hash(image),
        finder.name(),
        model(image) if callable(model) else (model or ""),
        prompt() if callable(prompt) else (prompt or ""),
    )


class FinderCache:
    """Answers by key, at most ``most`` of them."""

    def __init__(self, most: int = CACHE_MOST) -> None:
        self._most = most
        self._kept: "OrderedDict[Key, Picture]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Key) -> Optional[Picture]:
        with self._lock:
            found = self._kept.get(key)
            if found is not None:
                self._kept.move_to_end(key)
        return found.model_copy(deep=True) if found is not None else None

    def put(self, key: Key, picture: Picture) -> None:
        with self._lock:
            self._kept[key] = picture.model_copy(deep=True)
            self._kept.move_to_end(key)
            while len(self._kept) > self._most:
                self._kept.popitem(last=False)

    def look(self, finder: ShapeFinder, image: Path) -> Picture:
        """What ``finder`` sees in ``image``: the kept answer, or a fresh look, kept."""
        key = key_for(finder, image)
        found = self.get(key)
        if found is not None:
            return found
        picture = finder.look(image)  # outside the lock: a finder may be slow
        self.put(key, picture)
        return picture

    def __len__(self) -> int:
        with self._lock:
            return len(self._kept)


_cache: Optional[FinderCache] = None
_made = threading.Lock()


def cache() -> FinderCache:
    """The one cache this process uses."""
    global _cache
    with _made:
        if _cache is None:
            _cache = FinderCache()
        return _cache


__all__ = ["CACHE_MOST", "FinderCache", "cache", "key_for", "picture_hash"]
