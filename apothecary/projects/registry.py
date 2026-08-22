from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import import_module
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


def stl_output_for(item: ProjectInfo) -> Path:
    """Where this part's STL belongs. The part decides, not the caller.

    `item.path.with_suffix(".stl")` is the obvious guess and it is wrong for
    any part whose SCAD is not in the folder the render belongs in. gridfinity
    is the live example: its source sits inside a third-party submodule and its
    wrapper overrides this precisely so a render does not land in somebody
    else's checkout. Every caller that guessed wrote a stray file in there.
    """
    if item.wrapper:
        try:
            part = getattr(import_module(item.wrapper), "DEFAULT", None)
            getter = getattr(part, "get_stl_output_path", None)
            if callable(getter):
                return Path(getter())
        except Exception:  # a wrapper that will not import is not a path answer
            pass
    return item.path.with_suffix(".stl")


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

        # Add each part as a separate item
        # Support both flat structure (parts/*.scad) and folder structure (parts/<name>/<name>.scad)
        scad_files = set()

        # Flat structure
        for scad in parts_dir.glob("*.scad"):
            scad_files.add(scad)

        # Folder structure: parts/<part_name>/<part_name>.scad
        for subdir in parts_dir.iterdir():
            if subdir.is_dir():
                # Look for a SCAD file with the same name as the folder
                folder_name = subdir.name
                scad_candidates = [
                    subdir / f"{folder_name}.scad",
                    # Also handle underscored names
                    subdir / f"{folder_name.replace('-', '_')}.scad",
                    subdir / f"{folder_name.replace('_', '-')}.scad",
                ]
                for candidate in scad_candidates:
                    if candidate.exists():
                        scad_files.add(candidate)
                        break
                else:
                    # Fallback: any SCAD file in the folder
                    for scad in subdir.glob("*.scad"):
                        scad_files.add(scad)
                        break

        for scad in sorted(scad_files):
            wrapper = _locate_wrapper_for_part(scad)
            items.append(
                ProjectInfo(
                    name=scad.stem,
                    path=scad,
                    kind="part",
                    files=[scad],
                    readme=False,
                    wrapper=wrapper,
                )
            )

        # Also scan for submodule parts (wrappers that point to nested submodule SCAD files)
        discovered_names = {p.name for p in items if p.kind == "part"}
        submodule_parts = _scan_submodule_parts(root, discovered_names)
        items.extend(submodule_parts)

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
    module_name = _sanitize_module_name(scad_path.stem)
    parts_pkg_dir = Path(__file__).resolve().parent / "parts"
    candidate = parts_pkg_dir / f"{module_name}.py"
    if candidate.exists():
        return f"apothecary.projects.parts.{module_name}"
    return None


def _scan_submodule_parts(root: Path, already_discovered: set) -> List[ProjectInfo]:
    """
    Scan for part wrappers that reference submodule SCAD files.

    These are parts like 'gridfinity' where the SCAD file lives inside a git
    submodule and wasn't discovered by the normal directory scan.
    """
    items: List[ProjectInfo] = []
    parts_pkg_dir = Path(__file__).resolve().parent / "parts"

    # Known submodule parts - wrappers that reference nested SCAD files
    # Format: (wrapper_module_name, part_name)
    SUBMODULE_PARTS = [
        ("gridfinity", "gridfinity"),
    ]

    for module_name, part_name in SUBMODULE_PARTS:
        if part_name in already_discovered:
            continue

        wrapper_file = parts_pkg_dir / f"{module_name}.py"
        if not wrapper_file.exists():
            continue

        # Try to import and get the DEFAULT instance
        try:
            from importlib import import_module

            mod = import_module(f"apothecary.projects.parts.{module_name}")
            if hasattr(mod, "DEFAULT"):
                part = mod.DEFAULT
                scad_path = part.source_file

                items.append(
                    ProjectInfo(
                        name=part_name,
                        path=scad_path,
                        kind="part",
                        files=[scad_path] if scad_path.exists() else [],
                        readme=(root / "parts" / part_name / "README.md").exists(),
                        wrapper=f"apothecary.projects.parts.{module_name}",
                    )
                )
        except Exception:
            # If import fails, still register as a known part
            items.append(
                ProjectInfo(
                    name=part_name,
                    path=root / "parts" / part_name,
                    kind="part",
                    files=[],
                    readme=(root / "parts" / part_name / "README.md").exists(),
                    wrapper=f"apothecary.projects.parts.{module_name}",
                )
            )

    return items
