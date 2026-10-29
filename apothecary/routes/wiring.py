"""A site's bench as carlos reads a rig: ``apothecary/wiring/``'s doors.

Plain ``def``, since finding the ports shells out to the toolchains, which
runs in the threadpool rather than on the event loop; neither touches a port
the scan does not already, and neither changes anything:

- ``GET /sites/{s}/wiring``: ``{site, patch, evidence, unplaced}`` -- the
  ``carlos.patch`` document, how each of its modules is known, and the nodes
  with a board or a sketch that have no device to be.
- ``GET /sites/{s}/wiring/patch``: the document alone, as carlos's Import
  reads a file.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from ..firmware import devices as firmware_devices
from ..firmware.bindings import bindings_for_site
from ..firmware.toolchains import ToolchainError
from ..wiring.patch import Wiring, wiring_for_site

router = APIRouter()


def _wiring(name: str) -> Wiring:
    from ..api import _get_site_or_404

    site = _get_site_or_404(name)
    try:
        found = firmware_devices.detected_devices()
    except ToolchainError:
        found = []
    return wiring_for_site(name, site, bindings_for_site(name, site, devices=found))


@router.get("/sites/{name}/wiring")
def site_wiring(name: str) -> Dict[str, Any]:
    """The site's bench as a ``carlos.patch``, with the evidence and the unplaced."""
    return _wiring(name).model_dump(mode="json")


@router.get("/sites/{name}/wiring/patch")
def site_wiring_patch(name: str) -> Dict[str, Any]:
    """The ``carlos.patch`` document alone."""
    return _wiring(name).patch
