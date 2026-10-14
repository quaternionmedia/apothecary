"""Records named for the moment they were made (``apothecary/stamped.py``): the moment's
form, and a name claimed by one writer alone however many reach for it at once."""

import threading
from datetime import datetime, timezone

from apothecary import stamped


def test_the_stamp_is_the_moment_to_the_millisecond():
    at = datetime(2026, 10, 14, 12, 0, 5, 7890, tzinfo=timezone.utc)
    assert stamped.stamp(at) == "20261014T120005.007"


def test_a_name_many_reach_for_at_once_is_each_ones_alone(tmp_path):
    """Twenty writers claim one name at the same moment: each has a file of its own, one
    the name itself and the rest it with -2 to -20 after it; a file already there is
    left as it was."""
    (tmp_path / "20261014T120000.123-cube-7.gcode").write_text("someone else's")
    ready = threading.Barrier(20)
    claimed = []

    def reach():
        ready.wait()
        claimed.append(stamped.claim(tmp_path, "20261014T120000.123-cube", ".gcode"))

    writers = [threading.Thread(target=reach) for _ in range(20)]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join(5)
    names = {path.name for path in claimed}
    assert len(claimed) == 20 and len(names) == 20
    wanted = {"20261014T120000.123-cube.gcode"}
    wanted |= {f"20261014T120000.123-cube-{n}.gcode" for n in range(2, 22) if n != 7}
    assert names == wanted
    assert (tmp_path / "20261014T120000.123-cube-7.gcode").read_text() == "someone else's"
