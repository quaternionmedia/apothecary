"""The origins switched off are written whole or not at all (apothecary/finders/switches.py)."""

import io

import pytest

from apothecary.finders import switches


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path))
    return tmp_path


def test_a_switch_is_read_back(state):
    switches.switch("qmcp/some-model@1", False)
    assert switches.read() == {"qmcp/some-model@1": False}
    assert not switches.is_on("qmcp/some-model@1")


def test_a_write_that_fails_midway_leaves_the_previous_file_readable(state, monkeypatch):
    switches.switch("plain/colour", False)
    before = switches.path().read_bytes()

    real_open = io.open

    def open_that_breaks_midway(file, mode="r", *args, **kwargs):
        handle = real_open(file, mode, *args, **kwargs)
        if "w" not in mode:
            return handle

        class Breaking:
            def write(self, text):
                handle.write(text[: len(text) // 2])
                handle.flush()
                raise OSError("disk full")

            def __getattr__(self, name):
                return getattr(handle, name)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                handle.close()

        return Breaking()

    with monkeypatch.context() as breaking:
        breaking.setattr(io, "open", open_that_breaks_midway)
        with pytest.raises(OSError, match="disk full"):
            switches.switch("qmcp/some-model@1", False)

    assert switches.path().read_bytes() == before
    assert switches.read() == {"plain/colour": False}
    assert [p.name for p in switches.path().parent.iterdir()] == ["switches.json"]
