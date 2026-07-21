"""Tests for the first-slice revision/branch/diff building blocks (prototype, unratified)."""

import pytest

from apothecary.hierarchy import Site, Structure
from apothecary.models.vectors import Vector3D
from apothecary.revisions import RevisionGraph, diff_assemblies


def _tree(printer_x=100.0, printer_status="idle"):
    return Site(
        name="garage",
        structures=[
            Structure(name="printer_1", position=Vector3D(x=printer_x), status=printer_status)
        ],
    )


def test_commit_creates_a_root_revision_with_no_parent():
    graph = RevisionGraph()
    revision = graph.commit("garage", _tree(), label="initial layout")
    assert revision.parent_ids == []
    assert graph.get("garage", revision.id) is revision


def test_commit_with_unknown_parent_raises():
    graph = RevisionGraph()
    with pytest.raises(KeyError):
        graph.commit("garage", _tree(), label="orphan", parent_id="nope")


def test_checkout_returns_a_deep_copy_not_the_stored_tree():
    graph = RevisionGraph()
    revision = graph.commit("garage", _tree(), label="initial layout")

    checked_out = graph.checkout("garage", revision.id)
    checked_out.children[0].position = Vector3D(x=999.0)

    assert graph.get("garage", revision.id).tree.children[0].position == Vector3D(x=100.0)


def test_branch_forks_from_a_revision_without_disturbing_it():
    graph = RevisionGraph()
    root = graph.commit("garage", _tree(printer_x=100.0), label="v1")

    branch = graph.branch("garage", root.id, label="airflow-experiment")
    assert branch.parent_ids == [root.id]
    assert branch.tree.children[0].position == Vector3D(x=100.0)

    # mutate the branch's own tree, then commit it as a new revision
    branch.tree.children[0].position = Vector3D(x=300.0)
    moved = graph.commit("garage", branch.tree, label="moved printer_1", parent_id=branch.id)

    assert root.tree.children[0].position == Vector3D(x=100.0)  # untouched
    assert moved.tree.children[0].position == Vector3D(x=300.0)


def test_history_walks_the_first_parent_chain_oldest_first():
    graph = RevisionGraph()
    v1 = graph.commit("garage", _tree(printer_x=100.0), label="v1")
    v2 = graph.commit("garage", _tree(printer_x=200.0), label="v2", parent_id=v1.id)
    v3 = graph.commit("garage", _tree(printer_x=300.0), label="v3", parent_id=v2.id)

    history = graph.history("garage", v3.id)
    assert [r.label for r in history] == ["v1", "v2", "v3"]


def test_children_of_reports_every_branch_point():
    graph = RevisionGraph()
    root = graph.commit("garage", _tree(), label="v1")
    branch_a = graph.branch("garage", root.id, label="branch-a")
    branch_b = graph.branch("garage", root.id, label="branch-b")

    children = {r.id for r in graph.children_of("garage", root.id)}
    assert children == {branch_a.id, branch_b.id}


def test_sites_do_not_share_revisions():
    graph = RevisionGraph()
    graph.commit("garage", _tree(), label="v1")
    with pytest.raises(KeyError):
        graph.history("other_site", "anything")


def test_diff_reports_position_and_status_changes_by_path():
    a = _tree(printer_x=100.0, printer_status="idle")
    b = _tree(printer_x=300.0, printer_status="printing")

    diffs = diff_assemblies(a, b)
    kinds_by_path = {(d.path, d.kind) for d in diffs}
    assert ("garage.printer_1", "position_changed") in kinds_by_path
    assert ("garage.printer_1", "status_changed") in kinds_by_path


def test_diff_reports_added_and_removed_nodes():
    a = Site(name="garage", structures=[Structure(name="printer_1")])
    b = Site(
        name="garage",
        structures=[Structure(name="printer_1"), Structure(name="printer_2")],
    )

    added = diff_assemblies(a, b)
    assert any(d.kind == "added" and d.path == "garage.printer_2" for d in added)

    removed = diff_assemblies(b, a)
    assert any(d.kind == "removed" and d.path == "garage.printer_2" for d in removed)


def test_diff_of_identical_trees_is_empty():
    assert diff_assemblies(_tree(), _tree()) == []
