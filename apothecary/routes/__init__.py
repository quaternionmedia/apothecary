"""Routers this project mounts on the application in `apothecary/api.py`.

The application's own routes are defined directly on `app` in that module. New
surfaces arrive here instead, one router per thing, because the file they would
otherwise join is already long enough that a reader cannot hold it.
"""

# An install point of the guard (apothecary/stays_local.py), before any module
# in this package runs: it reads camera frames, uploads and camera placements.
from ..stays_local import install_guard as _install_guard

_install_guard()
