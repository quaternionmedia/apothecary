"""The sorting on drawn folders: never joins unrelated pictures, still finds groups."""

import pytest

from apothecary.gathering import bench
from apothecary.vision.plain import PlainFinder

pytestmark = pytest.mark.slow

# Used while choosing the thresholds. Good for watching that nothing regresses;
# no use at all as evidence that the thresholds generalise.
TUNING_SEEDS = (1, 5, 10)

# Never used while choosing anything. These are the evidence.
HOLD_OUT_SEEDS = (17, 22, 29)


@pytest.fixture(scope="module")
def pairwise():
    return {seed: bench.run(PlainFinder(), each=4, seed=seed) for seed in TUNING_SEEDS}


@pytest.fixture(scope="module")
def tuned_folders():
    return {
        seed: bench.run(PlainFinder(), each=3, seed=seed, together=True) for seed in TUNING_SEEDS
    }


@pytest.fixture(scope="module")
def hold_out_folders():
    return {
        seed: bench.run(PlainFinder(), each=3, seed=seed, together=True) for seed in HOLD_OUT_SEEDS
    }


# --------------------------------------------------------------------------
# The claim that has to hold
# --------------------------------------------------------------------------


def test_no_group_is_ever_built_from_unrelated_photographs(hold_out_folders):
    """The one number that has to be nothing, on folders never tuned against."""
    for seed, score in hold_out_folders.items():
        assert score.groups_mixed == 0, f"seed {seed}: {'; '.join(score.mistakes[:3])}"


def test_no_pair_of_unrelated_photographs_is_ever_joined(hold_out_folders):
    for seed, score in hold_out_folders.items():
        assert score.joined_wrongly == 0, f"seed {seed}: {'; '.join(score.mistakes[:3])}"


def test_the_same_holds_on_the_folders_it_was_tuned_against(tuned_folders):
    for seed, score in tuned_folders.items():
        assert score.groups_mixed == 0, f"seed {seed}: {'; '.join(score.mistakes[:3])}"


# --------------------------------------------------------------------------
# And it still has to be useful
# --------------------------------------------------------------------------


def test_it_still_finds_groups(hold_out_folders):
    """Refusing everything would pass every test above.

    Two clean groups per folder is well under what is actually managed, and it is
    set there on purpose: this is a floor to catch the sorting seizing up, not a
    target to tune towards.
    """
    for seed, score in hold_out_folders.items():
        assert score.groups_clean >= 2, f"seed {seed}: {score.summary()}"


def test_it_finds_about_a_fifth_of_what_is_there(hold_out_folders):
    """Recall as a band: above it the tool is better than stated, below it broke."""
    found = [score.found_rate for score in hold_out_folders.values()]
    typical = sum(found) / len(found)
    assert 0.15 <= typical <= 0.5, f"recall has moved to {typical:.0%}"


def test_a_picture_with_nothing_in_it_is_always_spotted(hold_out_folders):
    for seed, score in hold_out_folders.items():
        assert score.unreadable >= 1, f"seed {seed}: the blank one should be caught"


def test_pair_by_pair_it_is_never_wrong(pairwise):
    for seed, score in pairwise.items():
        assert score.wrong_rate == 0.0, f"seed {seed}: {score.summary()}"


def test_pair_by_pair_it_is_not_completely_silent(pairwise):
    """Measured at 18% to 41% of pairs answered, depending on what was drawn.

    Low, and the floor is set below the lowest seen rather than at some rounder
    number that reads better. Most pairs in a folder are two photographs of
    different things which the sorting declines to call unrelated rather than
    claiming to be sure — on drawn pictures taken in near-identical light there
    is often nothing honest to say.
    """
    for seed, score in pairwise.items():
        assert score.right_rate >= 0.15, f"seed {seed} answers too little: {score.summary()}"
