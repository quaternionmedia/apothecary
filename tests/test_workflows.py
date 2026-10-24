"""The count of what a person has to type, and what the count obliges.

**Watched failing.** Each guard below was run with its fault in place before
this note was written: deleting a workflow from `RECORDED` turns
`test_every_workflow_records_what_it_cost` red; raising a workflow's step count
above its recorded number turns `test_a_rise_is_a_regression` red; declaring a
workflow carried by a name that does not exist turns
`test_a_workflow_carried_by_nothing_known_is_refused` red.
"""

import pytest

from apothecary import workflows
from apothecary.workflows import NOTHING, Undeclared, Workflow


def test_every_workflow_records_what_it_cost():
    """The recorded cost is the baseline a rise is measured against.

    A workflow missing from it is a workflow whose cost cannot rise, which is
    the quietest way for this meter to stop meaning anything.
    """
    census = workflows.take()
    assert set(workflows.RECORDED) == {one.name for one in census.workflows}


def test_a_rise_is_a_regression():
    assert workflows.take().risen() == [], (
        "a workflow costs more than was written down. That is a regression, and "
        "the fix is either to make it cheaper or to say why it is not"
    )


def test_the_numbers_are_what_the_steps_actually_are():
    for one in workflows.take().workflows:
        assert one.typed == len(one.steps)
        assert workflows.RECORDED[one.name] == one.typed


def test_a_workflow_carried_by_nothing_known_is_refused():
    with pytest.raises(Undeclared, match="not one of"):
        workflows.take([Workflow(name="x", what_for="y", steps=("z",), carried_by="magic")])


def test_a_workflow_with_no_steps_is_refused():
    with pytest.raises(Undeclared, match="has not been described"):
        workflows.take([Workflow(name="x", what_for="y", steps=(), carried_by=NOTHING)])


def test_two_workflows_may_not_share_a_name():
    same = Workflow(name="x", what_for="y", steps=("z",), carried_by=NOTHING)
    with pytest.raises(Undeclared, match="more than one workflow"):
        workflows.take([same, same])


def test_a_workflow_nothing_carries_becomes_an_open_item():
    """Doing a needed thing by typing is a diagnosis, not a delivery.

    The obligation is not to build an interface. It is to write down, where it
    can be argued with, that the interface stops here.
    """
    only_typed = workflows.take().only_typed()
    assert only_typed, "if nothing is typed-only any more, this whole file can go"
    for one in only_typed:
        assert one.carried_by == NOTHING
        assert one.what_for, f"{one.name} is an open item that does not say what for"


def test_the_expensive_one_says_why_it_is_expensive():
    """A high count that is correctly high is fine. A silent one is not."""
    for one in workflows.take().workflows:
        if one.typed > 1:
            assert one.why_so_many, (
                f"{one.name} costs {one.typed} steps and does not say why. A count "
                "without a reason is either a defect or an excuse, and nobody can "
                "tell which"
            )


def test_the_report_says_what_it_cannot_see():
    text = workflows.report()
    assert "What this cannot see" in text
    assert "written down" in text
