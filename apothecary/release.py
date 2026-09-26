"""Whether this commit is something a downstream project may depend on.

Apothecary is consumed by pinned downstreams. The enclosure record binds one of
them explicitly:

    5. **This project depends on a released apothecary version**, pinned, and
       consumes parts through apothecary's CLI or API rather than by path.
       Geometry changes land upstream and arrive here by version bump.

That sentence is an obligation on *this* repository as much as on the consumer,
and it was documented in only one direction: a contributor here had no way to
learn that a downstream pins this repo, or that publishing is how geometry
reaches it. So the obligation is stated where the code is, and answered by a
command rather than by prose.

Nothing here publishes anything. Tagging and releasing is a human act, and the
corpus is explicit that assistants draft and humans decide. This reports
whether the act would be legitimate right now, and what is missing if not.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

REPO = Path(__file__).resolve().parents[1]

# A downstream that pins this repository. Not a dependency in either direction
# -- parts know nothing about consumers, per clause 2 -- but a fact about who
# is watching, so a contributor can find out that publishing matters to
# somebody.
KNOWN_CONSUMERS = ("quaternionmedia/datum",)

_SEMVER_TAG = re.compile(r"^v?\d+\.\d+\.\d+")


@dataclass(frozen=True)
class Readiness:
    """Whether this commit could legitimately become a release."""

    releasable: bool
    reasons: List[str]
    version: str
    published: List[str]


def _git(*args: str, timeout: int = 30) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=timeout
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def declared_version() -> str:
    """The version this repository claims, from pyproject.

        >>> declared_version().count(".") >= 1
        True
    """
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return match.group(1) if match else ""


def published_versions() -> List[str]:
    """Version tags that exist in this checkout.

    Local tags, deliberately: a release is something this repository made, and
    asking the remote would answer a different question about a machine that
    may be offline.
    """
    output = _git("tag", "--list")
    if not output:
        return []
    return sorted(tag for tag in output.splitlines() if _SEMVER_TAG.match(tag.strip()))


def readiness() -> Readiness:
    """What stands between this commit and being something downstream may pin.

    Deliberately narrow. It answers questions this repository can answer from
    its own state -- is there a version, is it already used, is this commit on
    a branch anyone else can obtain -- and does not try to judge whether the
    change is any good. That is what review is for.
    """
    version = declared_version()
    published = published_versions()
    reasons: List[str] = []

    if not version:
        reasons.append("pyproject declares no version")
    elif f"v{version}" in published or version in published:
        reasons.append(f"version {version} is already tagged; bump it before releasing again")

    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch and branch != "main":
        reasons.append(
            f"on branch {branch}, not main -- a downstream pinning this commit "
            "would depend on a state nobody else can obtain"
        )

    dirty = _git("status", "--porcelain")
    if dirty:
        reasons.append("the working tree has uncommitted changes")

    return Readiness(
        releasable=not reasons, reasons=reasons, version=version, published=published
    )


def consumers_waiting() -> List[str]:
    """Downstreams that pin this repository and are affected by a release.

        >>> consumers_waiting()
        ['quaternionmedia/datum']
    """
    return list(KNOWN_CONSUMERS)
