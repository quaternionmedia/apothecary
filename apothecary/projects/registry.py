from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass
class ProjectInfo:
    name: str
    path: Path
    kind: str  # e.g., 'fifel', 'footpedal', 'parts', 'part'
    files: List[Path]
    readme: bool
    wrapper: str | None = None  # dotted module path for part wrapper if available

    def to_json(self) -> Dict[str, Any]:
        d = asdict(self)
        d["path"] = str(self.path)
        d["files"] = [str(p) for p in self.files]
        return d


def _gather(dirpath: Path, patterns: Iterable[str]) -> List[Path]:
    files: List[Path] = []
    for pat in patterns:
        files.extend(sorted(dirpath.glob(pat)))
    return files


def scan_projects(root: Path) -> List[ProjectInfo]:
    """Scan the repository root for known projects and parts.

    - Detects 'fifel', 'footpedal', and 'parts' directories if present
    - For 'parts', returns a top-level ProjectInfo and per-part entries
    """
    items: List[ProjectInfo] = []

    # Fifel project (canonical location under 'fifel/')
    fifel_dir = root / "fifel"
    if fifel_dir.is_dir():
        files = _gather(fifel_dir, ["*.scad", "*.jscad", "*.md"])
        items.append(
            ProjectInfo(
                name="fifel",
                path=fifel_dir,
                kind="fifel",
                files=files,
                readme=(fifel_dir / "README.md").exists(),
            )
        )

    # Footpedal project (canonical location under 'footpedal/')
    foot_dir = root / "footpedal"
    if foot_dir.is_dir():
        files = _gather(foot_dir, ["*.scad", "*.ino", "*.md"])
        items.append(
            ProjectInfo(
                name="footpedal",
                path=foot_dir,
                kind="footpedal",
                files=files,
                readme=(foot_dir / "README.md").exists(),
            )
        )

    # Parts collection (canonical location under 'parts/')
    parts_dir = root / "parts"
    if parts_dir.is_dir():
        # Gather all SCAD files in both flat and folder structures
        part_files = _gather(parts_dir, ["*.scad", "*.md"])
        # Also include files in subdirectories
        part_files.extend(sorted(parts_dir.glob("*/*.scad")))
        part_files.extend(sorted(parts_dir.glob("*/*.md")))

        items.append(
            ProjectInfo(
                name="parts",
                path=parts_dir,
                kind="parts",
                files=part_files,
                readme=(parts_dir / "README.md").exists(),
            )
        )

        # Gather all unique SCAD files in parts/ and subfolders
        scad_files = set(parts_dir.rglob("*.scad"))

        # Add each part as a separate item
        for scad in sorted(scad_files):
            wrapper = _locate_wrapper_for_part(scad)
            display_name = None
            dotted_name = scad.stem
            # If wrapper is a subfolder (e.g., rc/snowplow/__init__.py), use its DEFAULT
            if wrapper:
                try:
                    import importlib
                    mod = importlib.import_module(wrapper)
                    display_name = getattr(mod.DEFAULT, "display_name", None)
                    dotted_name = getattr(mod.DEFAULT, "name", dotted_name)
                except Exception:
                    display_name = None
            items.append(
                ProjectInfo(
                    name=display_name or dotted_name,
                    path=scad,
                    kind="part",
                    files=[scad],
                    readme=False,
                    wrapper=wrapper,
                )
            )

    return items


def scan_templates(root: Path) -> List[Path]:
    """Find template files under a 'templates' directory if it exists."""
    tpl_root = root / "templates"
    if not tpl_root.exists():
        return []
    return sorted(tpl_root.rglob("*.j2"))


def summarize_structure(root: Path) -> Dict[str, Any]:
    projects = scan_projects(root)
    templates = scan_templates(root)
    summary = {
        "root": str(root),
        "projects": len({p.kind for p in projects if p.kind in {"fifel", "footpedal", "parts"}}),
        "parts": len([p for p in projects if p.kind == "part"]),
        "templates": len(templates),
        "missing_readmes": [
            p.name for p in projects if p.kind in {"fifel", "footpedal", "parts"} and not p.readme
        ],
    }
    return summary


def _sanitize_module_name(filename: str) -> str:
    base = filename.lower().replace(" ", "_").replace("-", "_")
    base = base.replace(".", "_")
    return base


def _locate_wrapper_for_part(scad_path: Path) -> str | None:
    """Return dotted module path for a wrapper if it exists, else None."""
    # Support wrappers in subfolders (e.g., rc/snowplow/__init__.py)
    parts_pkg_dir = Path(__file__).resolve().parent / "parts"
    try:
        rel = scad_path.relative_to(parts_pkg_dir.parent.parent.parent / "parts")
    except ValueError:
        # Fallback: try relative to just 'parts' in cwd
        try:
            rel = scad_path.relative_to(Path.cwd() / "parts")
        except ValueError:
            rel = scad_path.name  # fallback to just the filename

    # Try <parts>/<name>.py
    flat_candidate = parts_pkg_dir / f"{scad_path.stem}.py"
    if flat_candidate.exists():
        return f"apothecary.projects.parts.{scad_path.stem}"

    # Try <parts>/<subdir>/<name>.py and <parts>/<subdir>/__init__.py
    if isinstance(rel, Path) and rel.parent != Path('.'):
        submod = ".".join(rel.parts[:-1])
        sub_candidate = parts_pkg_dir / rel.parent / f"{scad_path.stem}.py"
        if sub_candidate.exists():
            return f"apothecary.projects.parts.{submod}.{scad_path.stem}"
        init_candidate = parts_pkg_dir / rel.parent / "__init__.py"
        if init_candidate.exists():
            return f"apothecary.projects.parts.{submod}"
    return None
