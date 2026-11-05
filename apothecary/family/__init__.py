"""apothecary as the irl family's hub, on hearth's contract (docs/family.md).

hearth (``qm-hearth``) holds the contract a family's members keep, ``family/1``,
and the coordinator that keeps it from a hub's side. This package is what an
exemplar supplies around that coordinator: what it is, where its table is, and
the guard that keeps its members on this machine (``hub``).
"""

# An install point of the guard (apothecary/stays_local.py): a delivery carries
# what the bench holds.
from ..stays_local import install_guard as _install_guard

_install_guard()
