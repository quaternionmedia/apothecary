"""The picture root: the one folder pictures are read from, and the check that a
picture is inside it.

A server that reads any path it is handed is a server that will read
``/etc/shadow`` the day somebody points it at a network it did not expect.
Everything here is meant to run on one machine and listen only to it, and that is
still not a reason to leave the door open. So a picture is read from one folder,
named once, and a path is settled and checked against it every time it is used.

A root that is no folder of pictures, and a path that is no picture inside it, are
each an exception of this module's that says why in words for the person; the
server answers each kind with a status of its own (``apothecary/api.py``).
"""

# An install point of the guard (apothecary/stays_local.py), before any code of
# this module runs: a person's pictures are theirs.
from .stays_local import install_guard as _install_guard

_install_guard()

import os  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import List  # noqa: E402

from .state_folder import state_dir  # noqa: E402


class PictureRefused(Exception):
    """A root that is no folder of pictures, or a path that is no picture inside it."""


class NotAPictureRoot(PictureRefused):
    """The folder pictures are to be read from is not there, or holds everything."""


class OutsideRoot(PictureRefused):
    """A path that settles outside the picture root."""


class CannotLook(PictureRefused):
    """A path that cannot be asked about at all."""


class NoPicture(PictureRefused):
    """Nothing at the path, or nothing that is an ordinary file."""


def picture_root() -> Path:
    """The one folder pictures may be read from.

    Set ``APOTHECARY_PICTURE_ROOT`` to say where pictures live. Without it, the
    folder the server was started in. Never the whole machine, and never the
    person's home folder or anything above it: a picture root is a folder of
    pictures, and those hold everything else of theirs.
    """
    named = os.environ.get("APOTHECARY_PICTURE_ROOT") or str(Path.cwd())
    root = Path(named).resolve()
    if not root.is_dir():
        raise NotAPictureRoot(
            f"pictures are supposed to be read from {root}, and there is no "
            "folder there. Set APOTHECARY_PICTURE_ROOT to one that exists."
        )
    if root == Path(root.anchor):
        raise NotAPictureRoot(
            f"pictures are supposed to be read from {root}, which is the whole "
            "machine. That turns the restriction off rather than setting it."
        )
    homes = _home_folders()
    state = _state_folder()
    if any(root == home or root in home.parents for home in homes) or (
        root == state or state in root.parents
    ):
        raise NotAPictureRoot(
            f"pictures are supposed to be read from {root}, which holds everything "
            "of yours, not a folder of pictures. Start the server in a folder of "
            "pictures, or set APOTHECARY_PICTURE_ROOT to one."
        )
    return root


def _home_folders() -> List[Path]:
    """The person's home: by HOME, and by the account, which a variable cannot move."""
    folders = [Path.home()]
    try:
        import pwd

        folders.append(Path(pwd.getpwuid(os.getuid()).pw_dir))
    except (ImportError, KeyError, AttributeError):
        pass
    return [f.expanduser().resolve() for f in folders]


def _state_folder() -> Path:
    """Where the serial numbers, camera labels and readings live: never pictures."""
    return state_dir().expanduser().resolve()


def picture_within_root(where: Path) -> Path:
    """Check a picture is inside the one folder, following any links first.

    Checked every time it is used, not only when it arrives. A file that passed
    on the way in can be swapped for a link pointing anywhere afterwards, and
    then the door that refused it is serving it.
    """
    root = picture_root()
    try:
        settled = Path(where).resolve()
        settled.relative_to(root)
    except (ValueError, OSError):
        raise OutsideRoot(f"pictures are read from {root} and nowhere else") from None
    # `is_file` rather than `exists`: a pipe exists, and opening one waits for
    # somebody to write to it, which is never. It also has to be guarded,
    # because asking about an impossible path is itself an error rather than a
    # no.
    try:
        real = settled.is_file()
    except OSError as exc:
        raise CannotLook(f"{settled} cannot be looked at: {exc}") from None
    if not real:
        raise NoPicture(f"there is no picture at {settled}, or it is not an ordinary file")
    return settled
