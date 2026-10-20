"""`apothecary preflight` stages each workflow before the governance runner reads it: the
staged copy gives every step its job's env, as a runner does and the pinned runner
does not, so a job that differs from another only in its env runs as itself here."""

import shutil

import yaml

from apothecary.cli.preflight import _steps_carry_their_jobs_env
from apothecary.projects.parts.skeleton import ROOT

SHARED = """\
name: Two shards
on:
  pull_request:
jobs:
  one:
    runs-on: ubuntu-latest
    env:
      SHARD: 1
    steps: &steps
    - name: says its shard
      run: echo "$SHARD"
    - name: has its own
      env:
        SHARD: 9
      run: echo "$SHARD"
  two:
    runs-on: ubuntu-latest
    env:
      SHARD: 2
    steps: *steps
"""


def _steps(path, job):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"][job]["steps"]


def test_each_step_carries_its_jobs_env_beneath_its_own(tmp_path):
    staged = tmp_path / "two.yml"
    staged.write_text(SHARED, encoding="utf-8")
    _steps_carry_their_jobs_env(staged)
    loaded = yaml.safe_load(staged.read_text(encoding="utf-8"))
    assert loaded[True] == {"pull_request": None}  # `on:` is still the trigger the runner reads
    assert [s["env"] for s in _steps(staged, "one")] == [{"SHARD": 1}, {"SHARD": 9}]
    assert [s["env"] for s in _steps(staged, "two")] == [{"SHARD": 2}, {"SHARD": 9}]


def test_a_workflow_with_no_job_env_is_left_as_written(tmp_path):
    staged = tmp_path / "plain.yml"
    text = "name: Plain\non:\n  push:\njobs:\n  a:\n    steps:\n    - run: true\n"
    staged.write_text(text, encoding="utf-8")
    _steps_carry_their_jobs_env(staged)
    assert staged.read_text(encoding="utf-8") == text


def test_the_browser_shards_each_run_their_own_third(tmp_path):
    staged = tmp_path / "pytest.yml"
    shutil.copy2(ROOT / ".github" / "workflows" / "pytest.yml", staged)
    _steps_carry_their_jobs_env(staged)
    for job, shard in (("e2e-1", 1), ("e2e-2", 2), ("e2e-3", 3)):
        (browser,) = [s for s in _steps(staged, job) if "--shard" in s.get("run", "")]
        assert browser["env"]["SHARD"] == shard, job
