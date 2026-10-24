"""One check every server fixture makes before it starts anything.

Its own module, imported by name, because ``conftest`` is a name two files
share here and which one wins depends on collection order.
"""

import socket

import pytest


def refuse_a_held_port(port: int | str) -> None:
    """Stop the run if something already listens on ``port``.

    A server left behind by an interrupted run answers the health check, so
    the fixture that "started" a server would run the suite against stale
    code and call it green. Refusing is the only honest answer.
    """
    with socket.socket() as sock:
        # As uvicorn binds: a port in TIME_WAIT from the last run's server is
        # free, a port something still listens on is not.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", int(port)))
        except OSError:
            pytest.exit(
                f"port {port} is already held -- a server from an interrupted run? "
                f"Find it with `ss -ltnp | grep :{port}` and stop it, then run again.",
                returncode=1,
            )
