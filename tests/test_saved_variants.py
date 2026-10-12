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
    KEPT_IN,
    GitError,
    Moved,
    NotBuilt,
    NotInGit,
    check_name,
    keeping,
    list_saved,
    read_saved,
    save_variant,
    saved_names,
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
        # Where git keeps it: a submodule's .git is a file naming its git directory.
        "index": hashlib.sha256(
            (Path(git(repo, "rev-parse", "--absolute-git-dir").strip()) / "index").read_bytes()
        ).hexdigest(),
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


class TestWhatEachChanges:
    def test_a_variant_is_listed_with_its_diff_against_the_parts_scad(self, checkout, block):
        save_variant(block, "wider", EDITED, {"width": 50})
        plain = list_saved(block)[0]
        assert plain.diff is None
        listed = list_saved(block, with_diff=True)[0]
        assert "-cube([width, depth, 3]);" in listed.diff
        assert "+cube([width, depth, 9]);" in listed.diff
        assert listed.diff.startswith("--- a/parts/block/block.scad\n+++ b/parts/block/block.scad")
        r = TestClient(app).get("/parts/block/saved", params={"diff": "true"}).json()
        assert r[0]["diff"] == listed.diff

    def test_the_same_scad_changes_nothing(self, checkout, block):
        save_variant(block, "as-is", block.source_file.read_text())
        assert list_saved(block, with_diff=True)[0].diff == ""

    def test_the_names_a_ring_offers_newest_first(self, checkout, block):
        assert saved_names(block) == []
        save_variant(block, "wider", EDITED)
        save_variant(block, "thin", SCAD.replace("3]", "1]"))
        assert set(saved_names(block)) == {"wider", "thin"} and saved_names(block)[0] == "thin"


class TestWhereItsParametersAreKept:
    """Beside its SCAD for now; the part's own description is the aim, a stub until then."""

    def test_beside_its_scad_is_built_and_the_description_is_a_stub(self):
        assert [(k.id, k.stub) for k in KEPT_IN] == [
            ("variant-file", False),
            ("part-description", True),
        ]
        assert keeping("variant-file").id == "variant-file"
        with pytest.raises(NotBuilt, match="stub, not built yet .what it will do: .*part.json"):
            keeping("part-description")
        with pytest.raises(ValueError, match="no place"):
            keeping("somewhere")

    def test_saving_into_the_stub_is_refused_saying_what_it_will_do(self, checkout, block):
        with pytest.raises(NotBuilt):
            save_variant(block, "wider", EDITED, kept_in="part-description")
        assert git(checkout, "for-each-ref", "refs/apothecary/") == ""
        r = TestClient(app).post(
            "/parts/block/saved",
            json={"name": "wider", "scad": EDITED, "params_in": "part-description"},
        )
        assert r.status_code == 422 and "what it will do" in r.json()["detail"]
        assert git(checkout, "for-each-ref", "refs/apothecary/") == ""


class TestAnotherRepositoryToSaveInto:
    """APOTHECARY_VARIANTS_REPO: a clone to save into -- a test server's, which must
    never write the checkout's refs. The paths in it are still the part's."""

    def test_a_save_goes_to_the_clone_and_the_checkout_is_as_it_was(
        self, checkout, block, tmp_path, monkeypatch
    ):
        clone = tmp_path / "variants.git"
        git(tmp_path, "clone", "-q", "--bare", "--shared", str(checkout), str(clone))
        git(clone, "config", "user.name", PERSON[0])
        git(clone, "config", "user.email", PERSON[1])
        before = _as_it_stands(checkout)
        monkeypatch.setenv("APOTHECARY_VARIANTS_REPO", str(clone))
        variant = save_variant(block, "wider", EDITED, {"width": 50})
        assert _as_it_stands(checkout) == before
        assert git(checkout, "for-each-ref", "refs/apothecary/") == ""
        assert git(clone, "show", f"{variant.ref}:parts/block/block.scad") == EDITED
        assert variant.parent == git(checkout, "rev-parse", "HEAD").strip()
        assert [v.name for v in list_saved(block)] == ["wider"]
        assert saved_names(block) == ["wider"]


def test_git_is_told_to_fetch_nothing_and_to_prompt_for_nothing(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("GIT_DIR", "/somewhere/else")
    env = saved._environment()
    assert "HTTPS_PROXY" not in env and "GIT_DIR" not in env
    assert (env["GIT_NO_LAZY_FETCH"], env["GIT_TERMINAL_PROMPT"]) == ("1", "0")


# --- where the ref is, and what a merge does ----------------------------------------


class TestTheMergeAdvice:
    def test_it_names_the_checkout_and_says_the_parameters_are_not_applied(
        self, checkout, block, monkeypatch
    ):
        from apothecary.projects.parts import skeleton

        monkeypatch.setattr(skeleton, "ROOT", checkout)
        variant = save_variant(block, "wider", EDITED, {"width": 50})
        assert variant.repository == "." and variant.kind == "scad"
        merge = variant.merge
        assert merge.repository == merge.checkout == "."
        assert merge.commands == [f"git merge {variant.ref}"] and merge.applies_params is False
        assert "does not apply the variant's parameters" in merge.advice
        assert "block.variant.json, which nothing reads" in merge.advice
        listed = TestClient(app).get("/parts/block/saved").json()[0]
        assert listed["merge"] == merge.model_dump() and listed["repository"] == "."

    def test_a_ref_in_another_repository_is_fetched_first_and_named(
        self, checkout, block, tmp_path, monkeypatch
    ):
        from apothecary.projects.parts import skeleton

        monkeypatch.setattr(skeleton, "ROOT", checkout)
        clone = tmp_path / "variants.git"
        git(tmp_path, "clone", "-q", "--bare", "--shared", str(checkout), str(clone))
        git(clone, "config", "user.name", PERSON[0])
        git(clone, "config", "user.email", PERSON[1])
        monkeypatch.setenv("APOTHECARY_VARIANTS_REPO", str(clone))
        variant = save_variant(block, "wider", EDITED, {"width": 50})
        assert variant.repository == str(clone.resolve())
        assert variant.merge.commands == [
            f"git fetch {clone.resolve()} {variant.ref}:{variant.ref}",
            f"git merge {variant.ref}",
        ]
        assert variant.merge.advice.startswith(
            f"The ref is in {clone.resolve()}, not this checkout"
        )
        # The advice is true: fetched and merged as it says, the edit is the part's.
        git(checkout, "stash", "-u", "-q")
        for command in variant.merge.commands:
            git(checkout, *command.split()[1:])
        assert (checkout / "parts" / "block" / "block.scad").read_text() == EDITED


# --- a part inside a submodule: an overlay in the checkout's ref -------------------------

UPSTREAM = "size = 10; // [1:50]\ncube(size);\n"


@pytest.fixture
def superproject(tmp_path) -> Path:
    """A checkout with a part whose SCAD is in a submodule, as gridfinity's is:
    ``parts/thing/upstream/lib.scad``, the submodule a repository of its own."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git(upstream, "init", "-q", "-b", "main")
    git(upstream, "config", "user.name", "Upstream")
    git(upstream, "config", "user.email", "upstream@example.invalid")
    (upstream / "lib.scad").write_text(UPSTREAM)
    git(upstream, "add", "-A")
    git(upstream, "commit", "-q", "-m", "A library")
    repo = tmp_path / "super"
    (repo / "parts" / "thing").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", PERSON[0])
    git(repo, "config", "user.email", PERSON[1])
    (repo / "parts" / "thing" / "README.md").write_text("A thing.\n")
    git(
        repo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(upstream),
        "parts/thing/upstream",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "A part from upstream")
    return repo


@pytest.fixture
def thing(superproject, monkeypatch) -> BasePart:
    part = BasePart(
        name="thing", source_file=superproject / "parts" / "thing" / "upstream" / "lib.scad"
    )
    real = api._load_part_wrapper
    monkeypatch.setattr(
        api, "_load_part_wrapper", lambda name: part if name == "thing" else real(name)
    )
    return part


class TestAPartInASubmodule:
    def test_a_save_is_an_overlay_in_the_checkouts_ref_and_the_submodule_is_untouched(
        self, superproject, thing
    ):
        module = superproject / "parts" / "thing" / "upstream"
        before, inside = _as_it_stands(superproject), _as_it_stands(module)
        variant = save_variant(thing, "big", UPSTREAM, {"size": 20})
        assert _as_it_stands(superproject) == before and _as_it_stands(module) == inside
        assert git(module, "for-each-ref", "refs/apothecary/") == ""
        ref = "refs/apothecary/variants/thing/big"
        assert variant.ref == ref and variant.kind == "overlay"
        assert variant.scad_path == "parts/thing/lib.overlay.scad"
        assert variant.upstream == "parts/thing/upstream/lib.scad"
        overlay = git(superproject, "show", f"{ref}:parts/thing/lib.overlay.scad")
        assert "include <upstream/lib.scad>\n" in overlay and overlay.endswith("size = 20;\n")
        record = json.loads(git(superproject, "show", f"{ref}:parts/thing/lib.variant.json"))
        assert record["params"] == {"size": 20}
        # The commit adds the overlay and its values; the submodule's pin is HEAD's.
        head = before["HEAD"].strip()
        assert git(superproject, "diff", "--name-only", head, ref).split() == [
            "parts/thing/lib.overlay.scad",
            "parts/thing/lib.variant.json",
        ]
        assert "submodule" in variant.merge.advice and "not changed" in variant.merge.advice
        assert "does not apply" not in variant.merge.advice

    def test_an_edit_of_the_upstream_file_is_refused_saying_why(self, superproject, thing):
        with pytest.raises(saved.UpstreamEdit, match="in a submodule"):
            save_variant(thing, "edited", UPSTREAM.replace("cube", "sphere"))
        r = TestClient(app).post(
            "/parts/thing/saved", json={"name": "edited", "scad": UPSTREAM + "// more\n"}
        )
        assert r.status_code == 403 and "is in a submodule" in r.json()["detail"]
        assert git(superproject, "for-each-ref", "refs/apothecary/") == ""

    def test_through_the_route_its_values_are_saved_as_the_overlay(self, superproject, thing):
        client = TestClient(app)
        r = client.post("/parts/thing/saved", json={"name": "big", "params": {"size": 30}})
        assert r.status_code == 201, r.text
        body = r.json()
        assert (body["kind"], body["params"]) == ("overlay", {"size": 30.0})
        one = client.get("/parts/thing/saved/big").json()
        assert one["scad"].endswith("size = 30.0;\n") and one["upstream"].endswith("lib.scad")
        listed = client.get("/parts/thing/saved", params={"diff": "true"}).json()
        assert "+size = 30.0;" in listed[0]["diff"]

    def test_a_draft_beside_it_is_ignored_by_the_submodule_in_its_own_exclude(
        self, superproject, thing
    ):
        from apothecary.projects.parts import drafts

        module = superproject / "parts" / "thing" / "upstream"
        tracked = git(module, "ls-files")
        with drafts.written_beside(thing, "cube(1);\n") as path:
            assert path.parent == module and path.exists()
            assert git(module, "status", "--porcelain", "--untracked-files=all") == ""
            assert git(superproject, "status", "--porcelain", "--untracked-files=all") == ""
        where = git(module, "rev-parse", "--absolute-git-dir").strip()
        exclude = Path(where) / "info" / "exclude"
        assert drafts.DRAFT_PATTERN in exclude.read_text().splitlines()
        assert git(module, "ls-files") == tracked and not (module / ".gitignore").exists()
        drafts._EXCLUDED.clear()  # asked again, it is not written twice
        with drafts.written_beside(thing, "cube(2);\n"):
            pass
        assert exclude.read_text().splitlines().count(drafts.DRAFT_PATTERN) == 1

    def test_a_part_that_is_in_no_submodule_writes_no_exclude(self, checkout, block):
        from apothecary.projects.parts import drafts

        assert drafts.ignored_in_its_submodule(block.source_file.parent) is None
        exclude = checkout / ".git" / "info" / "exclude"
        assert not exclude.exists() or drafts.DRAFT_PATTERN not in exclude.read_text()


def _a_rendering_openscad():
    from apothecary.projects.parts.customizer import lists_parameters

    for path in stl_renderer._openscad_candidates():
        if lists_parameters(path):
            return path
    return None


RENDERING = _a_rendering_openscad()


@pytest.mark.skipif(RENDERING is None, reason="no snapshot here (`apothecary openscad install`)")
def test_a_real_snapshot_renders_the_overlay_as_it_renders_the_values(
    superproject, thing, tmp_path
):
    """The overlay is the variant: rendered, it measures what -D renders."""
    from apothecary.projects.parts.stl_renderer import OpenSCADRenderer

    variant = save_variant(thing, "big", UPSTREAM, {"size": 23})
    overlay = superproject / variant.scad_path
    overlay.write_text(git(superproject, "show", f"{variant.ref}:{variant.scad_path}"))
    renderer = OpenSCADRenderer(str(RENDERING))
    as_overlay = renderer.render_stl(overlay, tmp_path / "o.stl")
    as_values = renderer.render_stl(thing.source_file, tmp_path / "d.stl", params={"size": 23})
    assert as_overlay.success and as_values.success, as_overlay.stderr
    assert as_overlay.measured["size"] == as_values.measured["size"] == [23.0, 23.0, 23.0]
