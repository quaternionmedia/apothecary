"""Save is a variant in git (decided 2026-09-27): the edited SCAD and its
parameters committed to ``refs/apothecary/variants/<part>/<name>`` with git's
plumbing, so the working tree, the index and the checked-out branch are never
touched; listed from those refs; made the part's source by a merge the person
does.

Every repository here is the test's own, made in a temporary folder, with an
identity of its own and none of the person's git configuration: no test makes
a ref in this checkout's repository (tests/conftest.py refuses one).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scripted_openscad import scripted_openscad

from apothecary import api
from apothecary.api import app
from apothecary.projects.parts import saved, stl_renderer
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.saved import (
    GitError,
    Moved,
    NotInGit,
    check_name,
    list_saved,
    read_saved,
    save_variant,
)

SCAD = "include <dims.scad>\nwidth = 34; // [10:100]\ncube([width, depth, 3]);\n"
EDITED = SCAD.replace("cube([width, depth, 3])", "cube([width, depth, 9])")
PERSON = ("A Person", "person@example.invalid")


def git(repo: Path, *args: str, input: str | None = None) -> str:
    done = subprocess.run(
        ["git", *args], cwd=repo, input=input, capture_output=True, text=True, check=True
    )
    return done.stdout


@pytest.fixture(autouse=True)
def _none_of_the_persons_git(monkeypatch, tmp_path):
    """No global or system git configuration: no signing, no hooks path, no identity."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)
    # The OpenSCAD that lists a SCAD's parameters for a save's check is scripted.
    lister = scripted_openscad(tmp_path / "bin" / "openscad")
    monkeypatch.setenv("APOTHECARY_OPENSCAD", str(lister))
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(stl_renderer, "_renderer", None)


@pytest.fixture
def checkout(tmp_path) -> Path:
    """A repository with a part in it, a commit on main, and work in progress of
    every kind: a file changed and not staged, one staged, one untracked."""
    repo = tmp_path / "checkout"
    (repo / "parts" / "block").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", PERSON[0])
    git(repo, "config", "user.email", PERSON[1])
    (repo / "parts" / "block" / "block.scad").write_text(SCAD)
    (repo / "parts" / "block" / "dims.scad").write_text("depth = 20;\n")
    (repo / "README.md").write_text("A checkout.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A part")
    (repo / "README.md").write_text("A checkout, being edited.\n")
    (repo / "notes.txt").write_text("staged\n")
    git(repo, "add", "notes.txt")
    (repo / "scratch.txt").write_text("untracked\n")
    (repo / "parts" / "block" / "block.scad").write_text(SCAD + "// not committed\n")
    return repo


@pytest.fixture
def block(checkout, monkeypatch) -> BasePart:
    part = BasePart(name="block", source_file=checkout / "parts" / "block" / "block.scad")
    real = api._load_part_wrapper
    monkeypatch.setattr(
        api, "_load_part_wrapper", lambda name: part if name == "block" else real(name)
    )
    return part


def _as_it_stands(repo: Path) -> dict:
    """Everything a save must leave as it was."""
    files = sorted(p for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts)
    return {
        "status": git(repo, "status", "--porcelain=v2", "--branch", "--untracked-files=all"),
        "HEAD": git(repo, "rev-parse", "HEAD"),
        "branch": git(repo, "symbolic-ref", "HEAD"),
        "index": hashlib.sha256((repo / ".git" / "index").read_bytes()).hexdigest(),
        "files": {str(p.relative_to(repo)): p.read_bytes() for p in files},
        "refs": git(
            repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/tags"
        ),
        "stash": git(repo, "stash", "list"),
    }


class TestASave:
    def test_it_is_a_commit_on_the_parts_ref_and_touches_nothing_else(self, checkout, block):
        before = _as_it_stands(checkout)
        head = before["HEAD"].strip()
        variant = save_variant(block, "wider", EDITED, {"width": 50.0})

        assert _as_it_stands(checkout) == before
        ref = "refs/apothecary/variants/block/wider"
        assert variant.ref == ref and git(checkout, "rev-parse", ref).strip() == variant.commit
        assert variant.parent == head == git(checkout, "rev-parse", f"{ref}^").strip()
        assert git(checkout, "show", f"{ref}:parts/block/block.scad") == EDITED
        record = json.loads(git(checkout, "show", f"{ref}:parts/block/block.variant.json"))
        assert record == {"part": "block", "variant": "wider", "params": {"width": 50.0}}
        # The rest of the tree is HEAD's: the edit and its parameters are all it adds.
        changed = git(checkout, "diff", "--name-only", head, ref).split()
        assert changed == ["parts/block/block.scad", "parts/block/block.variant.json"]
        assert (variant.params, variant.merged, variant.scad_path) == (
            {"width": 50.0},
            False,
            "parts/block/block.scad",
        )

    def test_its_author_is_the_checkouts_identity_and_it_has_no_trailer(self, checkout, block):
        variant = save_variant(block, "wider", EDITED)
        who = git(checkout, "log", "-1", "--format=%an <%ae>%n%cn <%ce>", variant.commit)
        assert who.splitlines() == [f"{PERSON[0]} <{PERSON[1]}>"] * 2
        assert (variant.author, variant.author_email) == PERSON
        message = git(checkout, "log", "-1", "--format=%B", variant.commit)
        assert git(checkout, "interpret-trailers", "--parse", input=message).strip() == ""
        assert message.startswith("block is saved as the variant wider\n")
        assert variant.subject == "block is saved as the variant wider"
        for word in ("Co-Authored-By", "Signed-off-by", "Generated", "Tools:"):
            assert word.lower() not in message.lower()

    def test_saving_again_is_the_variants_next_commit(self, checkout, block):
        first = save_variant(block, "wider", EDITED, {"width": 50})
        second = save_variant(block, "wider", EDITED + "// more\n", {"width": 60})
        assert second.parent == first.commit and second.params == {"width": 60}
        log = git(checkout, "log", "--format=%H", "refs/apothecary/variants/block/wider")
        assert log.split()[:2] == [second.commit, first.commit]
        same = save_variant(block, "wider", EDITED + "// more\n", {"width": 60})
        assert same.commit == second.commit

    def test_a_variant_saved_meanwhile_is_not_overwritten(self, checkout, block, monkeypatch):
        """Two tabs saving one name: the second to move the ref is refused."""
        real = saved._message
        raced = []

        def another_tab_saves_first(part, name, where):
            if not raced:
                raced.append(True)
                save_variant(block, "wider", SCAD + "// the other tab\n")
            return real(part, name, where)

        monkeypatch.setattr(saved, "_message", another_tab_saves_first)
        with pytest.raises(Moved):
            save_variant(block, "wider", EDITED)
        kept = git(checkout, "show", "refs/apothecary/variants/block/wider:parts/block/block.scad")
        assert kept == SCAD + "// the other tab\n"

    def test_a_checkout_with_no_identity_is_refused_in_gits_words(self, checkout, block):
        git(checkout, "config", "--unset", "user.name")
        git(checkout, "config", "--unset", "user.email")
        git(checkout, "config", "user.useConfigOnly", "true")
        with pytest.raises(GitError, match="commit-tree"):
            save_variant(block, "wider", EDITED)
        assert git(checkout, "for-each-ref", "refs/apothecary/") == ""

    def test_a_part_outside_git_has_nowhere_to_save(self, tmp_path):
        loose = tmp_path / "loose" / "part.scad"
        loose.parent.mkdir()
        loose.write_text("cube(1);\n")
        part = BasePart(name="loose", source_file=loose)
        with pytest.raises(NotInGit):
            save_variant(part, "wider", "cube(2);\n")

    @pytest.mark.parametrize(
        "name", ["", "a b", "../x", "x/y", ".x", "-x", "x.", "x-", "a..b", "x.lock", "x" * 65, "é"]
    )
    def test_a_name_that_is_not_one_is_refused(self, name, checkout, block):
        with pytest.raises(ValueError):
            check_name(name)
        with pytest.raises(ValueError):
            save_variant(block, name, EDITED)
        assert git(checkout, "for-each-ref", "refs/apothecary/") == ""

    @pytest.mark.parametrize("name", ["wider", "v2", "Thin_Walls", "a.b-c", "x"])
    def test_a_name_a_person_would_type_is_taken(self, name):
        assert check_name(name) == name


class TestListing:
    def test_a_parts_variants_are_read_from_its_refs_newest_first(self, checkout, block):
        save_variant(block, "wider", EDITED, {"width": 50})
        git(checkout, "update-ref", "refs/apothecary/variants/other/x", "HEAD")
        later = save_variant(block, "thin", SCAD.replace("3]", "1]"), {"width": 20})
        found = list_saved(block)
        assert [v.name for v in found][0] == "thin" and {v.name for v in found} == {"wider", "thin"}
        assert found[0].commit == later.commit and found[0].scad is None
        one = read_saved(block, "wider")
        assert one.scad == EDITED and one.params == {"width": 50}

    def test_making_one_the_parts_source_is_a_merge_the_person_does(self, checkout, block):
        variant = save_variant(block, "wider", EDITED, {"width": 50})
        assert not read_saved(block, "wider").merged
        # The person's own merge, with their own work put aside first.
        git(checkout, "stash", "-u", "-q")
        git(checkout, "merge", "-q", "--no-edit", variant.ref)
        assert (checkout / "parts" / "block" / "block.scad").read_text() == EDITED
        assert read_saved(block, "wider").merged

    def test_no_route_writes_the_working_tree(self):
        paths = {getattr(r, "path", "") for r in app.routes}
        assert not [p for p in paths if any(w in p for w in ("merge", "checkout", "apply-variant"))]


class TestTheRoutes:
    def test_save_list_and_read(self, checkout, block):
        client = TestClient(app)
        before = _as_it_stands(checkout)
        r = client.post(
            "/parts/block/saved", json={"name": "wider", "scad": EDITED, "params": {"width": 50}}
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["ref"] == "refs/apothecary/variants/block/wider" and body["merged"] is False
        assert (body["author"], body["author_email"]) == PERSON
        assert _as_it_stands(checkout) == before

        listed = client.get("/parts/block/saved").json()
        assert [(v["name"], v["commit"], v["params"]) for v in listed] == [
            ("wider", body["commit"], {"width": 50.0})
        ]
        one = client.get("/parts/block/saved/wider").json()
        assert one["scad"] == EDITED and one["commit"] == body["commit"]
        assert client.get("/parts/block/saved/narrower").status_code == 404
        assert client.get("/parts/block/saved/..%2Fx").status_code == 404

    def test_without_scad_it_saves_the_parts_scad_as_it_is_on_disk(self, checkout, block):
        r = TestClient(app).post("/parts/block/saved", json={"name": "as-is"})
        assert r.status_code == 201, r.text
        on_disk = block.source_file.read_text()
        assert git(checkout, "show", f"{r.json()['ref']}:parts/block/block.scad") == on_disk

    def test_what_a_render_refuses_a_save_refuses(self, checkout, block):
        client = TestClient(app)
        assert client.post("/parts/block/saved", json={"name": "a b"}).status_code == 422
        r = client.post("/parts/block/saved", json={"name": "x", "params": {"deep": 1}})
        assert r.status_code == 422 and r.json()["detail"] == "deep: no such parameter"
        assert git(checkout, "for-each-ref", "refs/apothecary/") == ""

    def test_a_variant_saved_meanwhile_is_a_409(self, checkout, block, monkeypatch):
        real = saved._message

        def raced(part, name, where):
            git(checkout, "update-ref", "refs/apothecary/variants/block/wider", "HEAD")
            return real(part, name, where)

        monkeypatch.setattr(saved, "_message", raced)
        r = TestClient(app).post("/parts/block/saved", json={"name": "wider", "scad": EDITED})
        assert r.status_code == 409 and "saved meanwhile" in r.json()["detail"]

    def test_git_saying_no_is_a_500_in_its_words(self, checkout, block):
        git(checkout, "config", "--unset", "user.name")
        git(checkout, "config", "--unset", "user.email")
        git(checkout, "config", "user.useConfigOnly", "true")
        r = TestClient(app).post("/parts/block/saved", json={"name": "wider", "scad": EDITED})
        assert r.status_code == 500 and "git commit-tree" in r.json()["detail"]

    def test_a_part_outside_git_lists_none(self, tmp_path, monkeypatch):
        loose = tmp_path / "loose" / "part.scad"
        loose.parent.mkdir()
        loose.write_text("cube(1);\n")
        part = BasePart(name="loose", source_file=loose)
        monkeypatch.setattr(api, "_load_part_wrapper", lambda name: part)
        client = TestClient(app)
        assert client.get("/parts/loose/saved").json() == []
        assert client.post("/parts/loose/saved", json={"name": "x"}).status_code == 409


def test_git_is_told_to_fetch_nothing_and_to_prompt_for_nothing(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("GIT_DIR", "/somewhere/else")
    env = saved._environment()
    assert "HTTPS_PROXY" not in env and "GIT_DIR" not in env
    assert (env["GIT_NO_LAZY_FETCH"], env["GIT_TERMINAL_PROMPT"]) == ("1", "0")
