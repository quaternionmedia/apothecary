"""A projector aimed at a machine's bed (apothecary/projector.py): four points of the
bed and the four pixels lighting them fix one mapping each way, a bed that carries Y
carries its points with it, a set that fixes no mapping is refused saying why, and a
machine's calibration is kept in the state folder."""

from __future__ import annotations

import json

import pytest

from apothecary import projector
from apothecary.state_folder import state_dir

# The Ender's volume, and a projector above it, its output leaning on the bed: the bed's
# front (its low Y) at the output's bottom.
VOLUME = [220.0, 220.0, 250.0]
OUTPUT = (1920, 1080)
LIT = [(400.0, 900.0), (1500.0, 880.0), (1400.0, 200.0), (500.0, 220.0)]


def _calibration(bed_offset: float = 0.0, site: str = "garage", path: str = "printer_1"):
    return projector.checked(
        site, path, projector.starting_points(VOLUME), LIT, OUTPUT, bed_offset=bed_offset
    )


def test_a_calibration_starts_from_the_volume_s_floor_set_in():
    assert projector.starting_points(VOLUME) == [(20, 20), (200, 20), (200, 200), (20, 200)]
    # A side shorter than five insets is set in by a fifth of it.
    assert projector.starting_points([50.0, 400.0, 10.0])[0] == (10.0, 20.0)


def test_a_bed_point_lands_on_its_pixel_and_a_pixel_returns_to_its_millimetres():
    calibration = _calibration()
    for (x, y), (u, v) in zip(calibration.bed, LIT, strict=True):
        assert projector.bed_to_projector(calibration, x, y) == pytest.approx((u, v))
        assert projector.projector_to_bed(calibration, u, v) == pytest.approx((x, y))
    for x, y in [(0.0, 0.0), (110.0, 110.0), (220.0, 37.5)]:
        lit = projector.bed_to_projector(calibration, x, y)
        assert projector.projector_to_bed(calibration, *lit) == pytest.approx((x, y))


def test_a_bed_that_carries_y_carries_its_points_with_it():
    """Marked with the bed standing 30 mm along Y: a point of the bed lands on its pixel
    with the bed standing there again, and where the room's point under it is lit with
    the bed standing anywhere else."""
    calibration = _calibration(bed_offset=30.0)
    for (x, y), (u, v) in zip(calibration.bed, LIT, strict=True):
        assert projector.bed_to_projector(calibration, x, y, bed_offset=30.0) == pytest.approx(
            (u, v)
        )
    moved = projector.bed_to_projector(calibration, 20.0, 20.0, bed_offset=-50.0)
    assert moved == pytest.approx(projector.bed_to_projector(calibration, 20.0, -60.0, 30.0))
    assert projector.projector_to_bed(calibration, *moved, bed_offset=-50.0) == pytest.approx(
        (20.0, 20.0)
    )


@pytest.mark.parametrize(
    "bed, pixels, said",
    [
        (
            [(20, 20), (110, 20), (200, 20), (20, 200)],
            LIT,
            "points 1, 2 and 3 of the four from lie on one line",
        ),
        (
            projector.starting_points(VOLUME),
            [(400, 900), (1500, 880), (400, 900), (500, 220)],
            "points 1, 2 and 3 of the four onto lie on one line",
        ),
        (projector.starting_points(VOLUME), LIT[:3], "four pixels of the output, not 3"),
        (projector.starting_points(VOLUME), [*LIT[:3], (2000, 10)], "outside the 1920 by 1080"),
        ([(20, 20), (200, 20), (200, float("nan")), (20, 200)], LIT, "two finite numbers"),
    ],
    ids=["three-bed-points-on-a-line", "two-pixels-the-same", "three", "off-the-output", "nan"],
)
def test_a_set_that_fixes_no_mapping_is_refused_saying_why(bed, pixels, said):
    with pytest.raises(projector.Refused, match=said):
        projector.checked("garage", "printer_1", bed, pixels, OUTPUT)


def test_an_output_of_no_size_and_a_name_of_another_shape_are_refused():
    bed = projector.starting_points(VOLUME)
    with pytest.raises(projector.Refused, match="two whole numbers of pixels"):
        projector.checked("garage", "printer_1", bed, LIT, (0, 1080))
    with pytest.raises(projector.Refused, match="no calibration can be kept"):
        projector.checked("garage", "../printer_1", bed, LIT, OUTPUT)


def test_a_calibration_is_kept_per_machine_in_the_state_folder():
    projector.clear("garage", "printer_1")
    projector.clear("garage", "cnc_router")
    assert projector.load("garage", "printer_1") is None
    kept = projector.save(_calibration(bed_offset=-12.5))
    projector.save(_calibration(path="cnc_router"))
    assert projector.load("garage", "printer_1") == kept
    on_disk = json.loads((state_dir() / projector.RECORDS).read_text(encoding="utf-8"))
    row = next(r for r in on_disk["projectors"] if r["path"] == "printer_1")
    assert row["format"] == projector.FORMAT and row["bed_offset"] == -12.5
    assert row["size"] == list(OUTPUT) and row["pixels"][0] == list(LIT[0])
    # Kept again, the machine has one calibration, the newer.
    again = projector.save(_calibration(bed_offset=4.0))
    assert [c.bed_offset for c in projector.records("garage") if c.path == "printer_1"] == [4.0]
    assert projector.load("garage", "printer_1") == again
    assert projector.clear("garage", "printer_1") and not projector.clear("garage", "printer_1")
    assert projector.load("garage", "cnc_router") is not None
    projector.clear("garage", "cnc_router")
