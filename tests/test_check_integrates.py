""".github/ci/check_integrates.py: a pull request whose head conflicts with the open ones
merged before it is not eligible, the ones stacked on it wait on it, and fixing its branch
so the text agrees makes it eligible."""

import importlib.util
import subprocess
import sys

import pytest

from apothecary.projects.parts.skeleton import ROOT

spec = importlib.util.spec_from_file_location(
    "check_integrates", ROOT / ".github" / "ci" / "check_integrates.py"
)
check = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check  # its dataclasses look their module up there
spec.loader.exec_module(check)


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return done.stdout.strip()


def _branch(name: str, base: str, text: str, file: str = "notes.md") -> str:
    """A branch off ``base`` that writes ``text`` into ``file``; its head."""
    _git("checkout", "-q", "-b", name, base)
    with open(file, "w", encoding="utf-8") as f:
        f.write(text)
    _git("add", file)
    _git("commit", "-q", "--no-gpg-sign", "-m", name)
    return _git("rev-parse", "HEAD")


def _pr(number: int, base: str, head: str, sha: str, login: str = "someone") -> dict:
    return {
        "number": number,
        "base": {"ref": base},
        "head": {"ref": head, "sha": sha},
        "user": {"login": login, "type": "Bot" if login.endswith("[bot]") else "User"},
    }


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for k, v in check.SCRATCH_IDENTITY.items():
        monkeypatch.setenv(k, v)
    _git("init", "-q", "-b", "main")
    with open("notes.md", "w", encoding="utf-8") as f:
        f.write("one\ntwo\nthree\n")
    _git("add", "notes.md")
    _git("commit", "-q", "--no-gpg-sign", "-m", "base")
    return tmp_path


def _verdicts(prs: list[dict]) -> dict[int, "check.Verdict"]:
    return {v.number: v for v in check.integrate(check.pulls(prs))}


def test_the_later_of_two_conflicting_pull_requests_is_not_eligible(repo):
    first = _branch("first", "main", "one\nTWO, as the first says\nthree\n")
    second = _branch("second", "main", "one\ntwo, as the second says\nthree\n")
    above = _branch("above", "second", "one\ntwo, as the second says\nthree\nfour\n")
    apart = _branch("apart", "main", "elsewhere\n", file="other.md")
    verdicts = _verdicts(
        [
            _pr(4, "main", "apart", apart),
            _pr(3, "second", "above", above),
            _pr(2, "main", "second", second),
            _pr(1, "main", "first", first),
        ]
    )
    assert verdicts[1].eligible
    assert verdicts[2].conflicts == ["notes.md"]
    assert verdicts[3].waits_on == 2 and not verdicts[3].eligible
    assert verdicts[4].eligible, "a pull request after the conflict is checked without it"


def test_a_branch_fixed_to_agree_is_eligible(repo):
    first = _branch("first", "main", "one\nTWO, as the first says\nthree\n")
    second = _branch("second", "main", "one\nTWO, as the first says\nthree\nand more\n")
    verdicts = _verdicts([_pr(1, "main", "first", first), _pr(2, "main", "second", second)])
    assert verdicts[2].eligible


def test_a_bots_pull_request_is_neither_merged_nor_judged(repo):
    bump = _branch("bump", "main", "one\nbumped\nthree\n")
    ours = _branch("ours", "main", "one\nours\nthree\n")
    prs = [_pr(1, "main", "bump", bump, login="dependabot[bot]"), _pr(2, "main", "ours", ours)]
    verdicts = _verdicts(prs)
    assert 1 not in verdicts and verdicts[2].eligible


def test_the_exit_status_judges_the_one_asked_about(repo, capsys):
    first = _branch("first", "main", "one\nTWO, as the first says\nthree\n")
    second = _branch("second", "main", "one\ntwo, as the second says\nthree\n")
    verdicts = check.integrate(
        check.pulls([_pr(1, "main", "first", first), _pr(2, "main", "second", second)])
    )
    assert check.report(verdicts, only=1) == 0
    assert check.report(verdicts, only=2) == 1
    assert "#2 is not eligible" in capsys.readouterr().out
