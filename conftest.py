"""What every pytest session in this repository starts from -- the unit tests
under ``tests/``, the browser tests under ``tests/e2e/``, and the walkthrough
pages under ``walkthrough/``, whose examples run as doctests.

The app answers this machine only (``apothecary/stays_local.py``). Starlette's
``TestClient`` presents itself as "testclient" at "testserver", which is
nowhere; every test here runs on this machine, so what the client presents is
this machine. Importing ``apothecary`` first puts the guard on the process
before any test connects anywhere.
"""

import starlette.testclient as _st

import apothecary  # noqa: F401  -- the guard, before any test connects anywhere

_test_client_init = _st.TestClient.__init__


def _from_this_machine(
    self, app, base_url="http://127.0.0.1", *args, client=("127.0.0.1", 50000), **kwargs
):
    _test_client_init(self, app, base_url, *args, client=client, **kwargs)


_st.TestClient.__init__ = _from_this_machine
