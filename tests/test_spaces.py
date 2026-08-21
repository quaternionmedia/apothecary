"""The problem and solution indexes, and the boundary they encode.

Ownership is the interesting field: a problem nobody owns is how a project
accumulates them, and a problem owned by the wrong side is how one project
waits on another that was never told.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.spaces import (
    APOTHECARY,
    DATUM,
    HUMAN,
    KIND_OWNER,
    capabilities,
    problems,
    summary,
)

client = TestClient(app)


class TestOwnershipComesFromOneTable:
    def test_every_problem_has_an_owner(self):
        """A problem nobody owns means the boundary has a hole."""
        for problem in problems():
            assert problem.owner, problem.id

    def test_every_owner_is_one_of_the_four(self):
        allowed = set(KIND_OWNER.values()) | {DATUM}
        for problem in problems():
            assert problem.owner in allowed, (problem.id, problem.owner)

    def test_contested_reads_the_table_rather_than_hardcoding(self):
        """An adversarial pass found this: `KIND_OWNER['contested']` could be
        changed to anything and the index did not notice, because the contested
        branch typed the owner again. Two places declaring one fact is the
        duplication this index exists to avoid.
        """
        import apothecary.spaces as spaces

        original = spaces.KIND_OWNER["contested"]
        spaces.KIND_OWNER["contested"] = APOTHECARY
        try:
            owners = {p.owner for p in problems() if p.kind == "contested"}
            assert owners == {APOTHECARY}
        finally:
            spaces.KIND_OWNER["contested"] = original

    def test_a_disputed_dimension_is_a_humans_to_settle(self):
        contested = [p for p in problems() if p.kind == "contested"]
        assert contested
        assert all(p.owner == HUMAN for p in contested)
        assert all(p.sources for p in contested), "a candidate with no source is an opinion"

    def test_an_unmeasured_board_belongs_to_the_consuming_project(self):
        """The board outline is datum's to supply; WP-4 produces it. Attributing
        it to apothecary would have this repository waiting on itself.
        """
        board = [p for p in problems() if p.kind == "unmeasured" and "board" in p.detail]
        assert board, "expected the board envelope to still be a stub"
        assert all(p.owner == DATUM for p in board)


class TestTheIndexIsDerived:
    def test_problems_carry_what_would_close_them(self):
        for problem in problems():
            assert problem.closes_with, problem.id

    def test_ids_are_stable_and_unique(self):
        ids = [p.id for p in problems()]
        assert len(ids) == len(set(ids))
        assert ids == [p.id for p in problems()]

    def test_a_part_is_only_told_about_black_boxes_it_is_fitted_to(self):
        """`calibration_cube` was once reported as fitted to datum's board,
        because the stub check read the bench for every part in the library.
        """
        unmeasured = {p.subject for p in problems() if p.kind == "unmeasured"}
        assert "calibration_cube" not in unmeasured

    def test_every_open_kind_has_something_that_addresses_it(self):
        """A kind nothing can close is worth naming, not hiding."""
        assert summary()["unaddressed_kinds"] == []

    def test_capabilities_name_the_kinds_they_close(self):
        gates = [c for c in capabilities() if c.kind == "gate"]
        assert gates
        assert all(g.addresses for g in gates)


class TestServedFromTheApi:
    def test_the_route_matches_the_function(self):
        body = client.get("/problems").json()
        assert body["count"] == len(problems())

    @pytest.mark.parametrize("owner", [HUMAN, APOTHECARY, DATUM])
    def test_filtering_by_owner(self, owner):
        body = client.get(f"/problems?owner={owner}").json()
        assert all(p["owner"] == owner for p in body["problems"])

    def test_filtering_by_kind(self):
        body = client.get("/problems?kind=contested").json()
        assert body["count"] > 0
        assert all(p["kind"] == "contested" for p in body["problems"])

    def test_solutions_route(self):
        body = client.get("/solutions").json()
        assert body["count"] == len(capabilities())

    def test_spaces_summary_route(self):
        body = client.get("/spaces").json()
        assert body["problems"] == len(problems())
        assert set(body["by_owner"]) <= {APOTHECARY, DATUM, HUMAN, "measurement"}

    def test_a_bad_build_volume_is_refused_everywhere(self):
        for route in ("/problems", "/spaces"):
            assert client.get(f"{route}?build_volume=nope").status_code == 422
            assert client.get(f"{route}?build_volume=1,2").status_code == 422

    def test_a_build_volume_changes_what_is_open(self):
        """Without one, "fits the printer" cannot be answered, so it is open."""
        without = client.get("/spaces").json()["problems"]
        with_volume = client.get("/spaces?build_volume=220,220,250").json()["problems"]
        assert with_volume < without
