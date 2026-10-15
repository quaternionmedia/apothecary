"""The lighting model: address parsing, the export loader, DMX decoding, and the checks.

The synthetic export is written into tmp_path so CI does not need the venue's
files. The venue's own export is read when it is present, and skipped otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from apothecary.lighting import (
    FixtureType,
    LightingRig,
    Patch,
    decode,
    fixture_color,
    load_rig,
    parse_address,
    validate_rig,
)
from apothecary.models.vectors import Vector3D

REPO = Path(__file__).resolve().parent.parent
VENUE = Path(os.environ.get("APOTHECARY_ECHS_PAC_DIR", REPO / "ECHS-PAC"))

PARAMS_HEADER = "FIXTURE_TYPE_NAME,FIXTURE_TYPE_MANUFACTURER,PARAMETER_TYPE,PARAMETER_TYPE_TEXT_SHORT,PARAMETER_TYPE_TEXT_LONG,PARAMETER_ADDRESS_OFFSET,PARAMETER_CATEGORY,PARAMETER_CATEGORY_AS_TEXT\n"
PATCH_HEADER = "CHANNEL,FIXTURE_TYPE,MANUFACTURER,ADDRESS,LABEL,LOCATION_X,LOCATION_Y,LOCATION_Z,ORIENTATION_X,ORIENTATION_Y,ORIENTATION_Z\n"


def _write_synthetic(tmp_path: Path, patch_rows: str) -> tuple[Path, Path]:
    params = tmp_path / "params.csv"
    params.write_text(
        PARAMS_HEADER
        + "".join(
            f"ColorSource_SPOT_5ch,ETC,{i},{p},{p},0,0,x\n"
            for i, p in enumerate(["Intens", "Red", "Green", "Blue", "Shutter_Strobe"])
        )
        + "Dimmer,ETC,0,Intens,Intens,0,0,x\n",
        encoding="utf-8",
    )
    patches = tmp_path / "patches.csv"
    patches.write_text(PATCH_HEADER + patch_rows, encoding="utf-8")
    return patches, params


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2/400<404,406", (2, [400, 401, 402, 403, 404, 406])),
        (" 2/1<5", (2, [1, 2, 3, 4, 5])),
        ("1/121", (1, [121])),
        ("", (None, [])),
    ],
)
def test_parse_address(text, expected):
    assert parse_address(text) == expected


def test_load_synthetic_export(tmp_path):
    patches, params = _write_synthetic(
        tmp_path,
        "1,ColorSource_SPOT_5ch,ETC, 1/1<5,Front,-1,2,3,24,41,49\n"
        "2,Dimmer,ETC, 1/10,Wash,,,,,,\n",
    )
    rig = load_rig(patches, params)
    assert set(rig.types) == {"ColorSource_SPOT_5ch", "Dimmer"}
    assert rig.types["ColorSource_SPOT_5ch"].params[0] == "Intens"
    assert rig.patches[0].addresses == [1, 2, 3, 4, 5]
    assert rig.patches[0].location == Vector3D(x=-1, y=2, z=3)
    assert rig.patches[1].location is None
    assert [p.channel for p in rig.unplaced()] == [2]
    assert validate_rig(rig).is_valid


def test_decode_reads_named_slots_and_scales_to_unit_range():
    rig = LightingRig(
        types={},
        patches=[Patch(channel=7, fixture_type="ColorSource_SPOT_5ch", universe=1, addresses=[10, 11, 12, 13, 14])],
    )
    slots = bytearray(512)
    slots[9], slots[10], slots[11], slots[12] = 255, 255, 0, 51
    levels = decode(rig, {1: bytes(slots)})[7]
    assert levels["Intens"] == 1.0
    assert levels["Red"] == 1.0
    assert levels["Green"] == 0.0
    assert levels["Blue"] == pytest.approx(0.2)


def test_decode_skips_unmapped_and_unaddressed_patches():
    rig = LightingRig(
        patches=[
            Patch(channel=1, fixture_type="Mac_III_Performance_16B"),
            Patch(channel=2, fixture_type="Dimmer", universe=1, addresses=[]),
            Patch(channel=3, fixture_type="Dimmer", universe=2, addresses=[1]),
        ],
    )
    assert decode(rig, {1: bytes(512)}) == {}


def test_validator_flags_overlap_bad_map_unknown_type_and_range():
    rig = LightingRig(
        types={"Dimmer": FixtureType(name="Dimmer"), "Slimpar_64_3ch": FixtureType(name="Slimpar_64_3ch")},
        patches=[
            Patch(channel=1, fixture_type="Dimmer", label="a", universe=1, addresses=[5]),
            Patch(channel=2, fixture_type="Dimmer", label="b", universe=1, addresses=[5]),
            Patch(channel=3, fixture_type="Slimpar_64_3ch", universe=1, addresses=[1, 2]),
            Patch(channel=4, fixture_type="Nope", universe=1, addresses=[600]),
        ],
    )
    kinds = sorted(v.kind for v in validate_rig(rig).violations)
    assert kinds == ["address_overlap", "address_range", "dmx_map_length", "unknown_type"]


def test_fixture_color_scales_colour_by_intensity():
    assert fixture_color({"Intens": 0.5, "Red": 1.0, "Green": 0.0, "Blue": 0.0}) == (128, 0, 0)
    assert fixture_color({"Intens": 1.0}) == (255, 255, 255)
    assert fixture_color({"Intens": 0.0, "Red": 1.0}) == (0, 0, 0)


@pytest.mark.skipif(not (VENUE / "ECHS-PAC-patches.csv").exists(), reason="venue export not present")
def test_venue_export_loads_and_validates_clean():
    rig = load_rig(VENUE / "ECHS-PAC-patches.csv", VENUE / "ECHS-PAC-fixture-parameters.csv")
    assert len(rig.patches) == 183
    report = validate_rig(rig)
    assert report.is_valid, [v.message for v in report.violations]
