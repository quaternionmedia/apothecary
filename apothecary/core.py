from typing import Optional

from pydantic import BaseModel


class OpenSCADObject(BaseModel):
    """Base class for all OpenSCAD objects.

    Subclasses must implement :meth:`render` with a strict no-args
    signature returning an OpenSCAD code snippet.
    """

    comment: Optional[str] = None

    def render(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError
