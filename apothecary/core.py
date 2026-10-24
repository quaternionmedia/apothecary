from typing import Iterable, Optional

from pydantic import BaseModel


class OpenSCADObject(BaseModel):
    """Base class for all OpenSCAD objects.

    Subclasses implement :meth:`render`, returning an OpenSCAD code snippet.
    """

    comment: Optional[str] = None

    def render(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def _comment(self) -> str:
        """The comment as ``//`` lines: a newline in it cannot become code."""
        if not self.comment:
            return ""
        return "".join(f"// {line}\n" for line in self.comment.splitlines())

    def _block(self, head: str, children: Iterable["OpenSCADObject"]) -> str:
        """``head { child; child; }``, the children indented one step."""
        inner = "\n".join(f"  {child.render()}" for child in children)
        return f"{self._comment()}{head} {{\n{inner}\n}}"


def scad_vec(v) -> str:
    """A Vector3D as an OpenSCAD list."""
    return f"[{v.x}, {v.y}, {v.z}]"
