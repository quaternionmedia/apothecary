"""Utility to help resolve repository root for wrappers.

Wrappers can import ROOT to compute absolute paths to the `parts/` directory.
Resolves robustly by walking up for a directory that looks like the repo root
(has pyproject.toml and a parts/ folder). Falls back to parents[3].
"""

from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "parts").exists():
            return parent
    # Fallback: <repo>/apothecary/apothecary/projects/parts -> parents[3] == <repo>
    return here.parents[3]


ROOT = repo_root()
