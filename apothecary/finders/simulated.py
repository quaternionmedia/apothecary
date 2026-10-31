"""A qmcp that answers in process: its vision tools over a simulated engine.

It speaks the contract, ``qm.vision`` version 1, as qmcp's own tools would, and
its one model is said to be simulated wherever it is named. Its answers are
worked from the pixels, plainly: a colour from the region's mean rather than the
plain reader's median, so the two disagree where a region holds more than one
colour; a material from how grey the region is; and a label in words of its own
(a block, a bar), which fall outside the words apothecary asks among, as a
model's often do.

``APOTHECARY_QMCP=simulated`` is the answering qmcp; ``simulated:slow`` answers
after every deadline, ``simulated:empty`` has no model, ``simulated:broken``
answers malformed, and ``simulated:down`` does not answer. ``apothecary serve
--demo`` runs with ``simulated`` unless another is set.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Dict, List

from ..evidence.observation import now
from ..evidence.words import COLOURS, colour_distance, rgb_of
from ..vision.colour import mean_rgb

MODES = ("", "slow", "empty", "broken", "down")

MODEL = {
    "name": "simulated-vlm",
    "version": "0",
    "weights_sha256": hashlib.sha256(b"apothecary simulated-vlm 0").hexdigest(),
    "licence": "CC0-1.0",
    "engine": {"name": "simulated", "version": "0"},
    "answers": {"colour": "qm.colours/1", "material": "qm.materials/1", "label": "its own words"},
    "warm": True,
}

# How long the slow mode takes: past any deadline apothecary asks with.
SLOW_SECONDS = 30.0


class NotAnswering(ConnectionError):
    """The simulated qmcp is down."""


class SimulatedQmcp:
    """qmcp's vision tools, answered here. ``roots`` are the folders a picture may
    be read under, as MCP's roots would declare them."""

    def __init__(self, mode: str = "", roots: List[Path] = ()):
        if mode not in MODES:
            raise ValueError(
                f"no simulated qmcp mode {mode!r}; have {[m or 'answering' for m in MODES]}"
            )
        self.mode = mode
        self.roots = [Path(r).resolve() for r in roots]

    def address(self) -> str:
        return "simulated" + (f":{self.mode}" if self.mode else "")

    def call(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if self.mode == "down":
            raise NotAnswering("connection refused")
        if tool == "vision.models":
            return {
                "contract": "qm.vision",
                "version": 1,
                "models": [] if self.mode == "empty" else [MODEL],
            }
        if tool != "vision.observe":
            raise KeyError(f"no tool named {tool!r}")
        if self.mode == "slow":
            time.sleep(SLOW_SECONDS)
        if self.mode == "broken":
            picture = arguments.get("picture", {}).get("sha256")
            return {
                "contract": "qm.vision",
                "version": 1,
                "picture": picture,
                "observations": "not a list",
            }
        return self._observe(arguments)

    def _observe(self, request: Dict[str, Any]) -> Dict[str, Any]:
        from ..vision.colour import crop

        started = time.monotonic()
        picture = request["picture"]
        where = Path(picture["path"]).resolve()
        refused = None
        if self.roots and not any(where.is_relative_to(root) for root in self.roots):
            refused = "the picture is outside the declared roots"
        elif not where.is_file():
            refused = "the picture could not be read"
        elif hashlib.sha256(where.read_bytes()).hexdigest() != picture["sha256"]:
            refused = "the picture changed since it was asked about"
        out = []
        for region in request["regions"]:
            pixels = None if refused else crop(where, tuple(region["box"]))
            for asked in request["asked"]:
                out.append(self._one(picture, region, asked, pixels, refused))
        return {
            "contract": "qm.vision",
            "version": 1,
            "picture": picture["sha256"],
            "observations": out,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    def _one(self, picture, region, asked, pixels, refused) -> Dict[str, Any]:
        prop = asked["property"]
        by = {
            "tool": "vision.observe",
            "model": MODEL["name"],
            "version": MODEL["version"],
            "weights_sha256": MODEL["weights_sha256"],
            "engine": "simulated",
        }
        if self.mode == "empty":
            by = {"tool": "vision.observe", "model": None}
        seen = {
            "subject": {
                "sighting": {
                    "picture": picture["sha256"],
                    "region": region["id"],
                    "box": region["box"],
                }
            },
            "property": prop,
            "value": None,
            "unit": None,
            "confidence": None,
            "origin": {"kind": "guessed", "by": by},
            "at": picture.get("taken") or now(),
            "recorded_at": now(),
            "evidence": [
                {"picture": picture["sha256"], "path": picture["path"], "box": region["box"]},
                {"qmcp_invocation": "simulated"},
            ],
            "why": None,
        }
        if refused:
            seen["why"] = refused
            return seen
        if self.mode == "empty" or prop not in MODEL["answers"]:
            seen["why"] = f"no model that answers {prop} is loaded"
            return seen
        if min(pixels.size) < 4:
            seen["why"] = (
                f"the region is too small for the model: {pixels.size[0]} × {pixels.size[1]} pixels"
            )
            return seen
        mean = mean_rgb(pixels)
        if prop == "colour":
            among = asked.get("among") or list(COLOURS)
            word, distance = min(
                ((w, colour_distance(mean, rgb_of(COLOURS[w]))) for w in among if w in COLOURS),
                key=lambda pair: pair[1],
            )
            seen.update(
                value=word, unit="qm.colours/1", confidence=round(max(0.05, 1 - distance / 120), 2)
            )
        elif prop == "material":
            spread = max(mean) - min(mean)
            word = "metal" if spread < 24 and sum(mean) / 3 > 90 else "plastic"
            seen.update(
                value=word, unit="qm.materials/1", confidence=0.35 if word == "metal" else 0.5
            )
        elif prop == "label":
            width, height = pixels.size
            word = "bar" if max(width, height) > 1.6 * min(width, height) else "block"
            seen.update(value=word, unit="its own words", confidence=0.4)
        return seen
