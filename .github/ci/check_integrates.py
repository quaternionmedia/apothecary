#!/usr/bin/env python3
"""Refuse a pull request whose head does not merge into the integration of the open ones before it.

A review here walks the whole codebase at once: every open pull request merged into
one tree (the README's map, and the record *Apothecary is reviewed as one integrated
whole*). A pull request that conflicts with that tree cannot be part of it, so it is
not eligible to merge until its own branch is fixed and the merge is clean.

THE ORDER. The open pull requests form a tree: a pull request's base is the default
branch, another branch nobody has a pull request for, or another open pull request's
head branch. They are merged depth first from each base, the pull requests on one
base in the order they were opened (lowest number first). A pull request is checked
against the tree made by merging, in that order, every one before it.

WHAT FAILS. A pull request whose head conflicts with that tree; the files are named.
Every pull request stacked on it waits on it and is reported as waiting, since its
head carries the conflict too. The fix is in the conflicting pull request's branch:
make the text agree with what it meets, or merge in what it conflicts with, so the
merge is clean. The pull requests after it are checked without it meanwhile.

Automation authors' pull requests (dependency bumps) are neither merged into the tree
nor judged: they wait for the stack, and a bump is opened again on top of it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field

# The merges this builds are never kept, signed or pushed: they exist to be merged into.
SCRATCH_IDENTITY = {
    "GIT_AUTHOR_NAME": "check_integrates",
    "GIT_AUTHOR_EMAIL": "check_integrates@localhost",
    "GIT_COMMITTER_NAME": "check_integrates",
    "GIT_COMMITTER_EMAIL": "check_integrates@localhost",
}


@dataclass
class Pull:
    number: int
    base: str
    head: str
    sha: str
    bot: bool = False
    children: list["Pull"] = field(default_factory=list)


@dataclass
class Verdict:
    number: int
    conflicts: list[str] = field(default_factory=list)  # files, when its head conflicts
    waits_on: int | None = None  # the pull request beneath it whose head conflicts

    @property
    def eligible(self) -> bool:
        return not self.conflicts and self.waits_on is None


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=check,
        env={**os.environ, **SCRATCH_IDENTITY},
    )


def fetch_open_prs(repo: str) -> list[dict]:
    """Every open pull request in ``repo``, via gh."""
    done = subprocess.run(
        ["gh", "api", "--paginate", f"repos/{repo}/pulls?state=open&per_page=100"],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise SystemExit(f"check_integrates: gh api repos/{repo}/pulls failed:\n{done.stderr}")
    # --paginate concatenates one JSON array per page.
    decoder, text, prs, at = json.JSONDecoder(), done.stdout.strip(), [], 0
    while at < len(text):
        page, at = decoder.raw_decode(text, at)
        prs.extend(page)
        while at < len(text) and text[at].isspace():
            at += 1
    return prs


def pulls(raw: list[dict]) -> list[Pull]:
    return [
        Pull(
            number=pr["number"],
            base=pr["base"]["ref"],
            head=pr["head"]["ref"],
            sha=pr["head"]["sha"],
            bot=pr["user"].get("type") == "Bot" or pr["user"]["login"].endswith("[bot]"),
        )
        for pr in raw
    ]


def order(prs: list[Pull]) -> list[tuple[str, list[Pull]]]:
    """Each base nobody's pull request heads, with its pull requests depth first, siblings
    oldest first."""
    by_head = {pr.head: pr for pr in prs}
    roots: dict[str, list[Pull]] = {}
    for pr in sorted(prs, key=lambda p: p.number):
        parent = by_head.get(pr.base)
        (parent.children if parent else roots.setdefault(pr.base, [])).append(pr)

    def walk(pr: Pull) -> list[Pull]:
        return [pr] + [each for child in pr.children for each in walk(child)]

    return [(base, [each for pr in tops for each in walk(pr)]) for base, tops in roots.items()]


def resolve(ref: str) -> str | None:
    for name in (f"refs/remotes/origin/{ref}", f"refs/heads/{ref}", ref):
        found = git("rev-parse", "--verify", "--quiet", f"{name}^{{commit}}", check=False)
        if found.returncode == 0:
            return found.stdout.strip()
    return None


def ensure(pr: Pull) -> None:
    """The pull request's head is here, fetched from the host if it is not."""
    if git("cat-file", "-e", f"{pr.sha}^{{commit}}", check=False).returncode != 0:
        git("fetch", "--quiet", "origin", f"+refs/pull/{pr.number}/head")


def integrate(prs: list[Pull]) -> list[Verdict]:
    verdicts = []
    for base, line in order([pr for pr in prs if not pr.bot]):
        tip = resolve(base)
        if tip is None:
            raise SystemExit(f"check_integrates: base {base!r} is not here; fetch it first")
        blocked: dict[str, int] = {}  # a head branch whose pull request cannot be merged
        for pr in line:
            if pr.base in blocked:
                verdicts.append(Verdict(pr.number, waits_on=blocked[pr.base]))
                blocked[pr.head] = blocked[pr.base]
                continue
            ensure(pr)
            merged = git("merge-tree", "--write-tree", "--name-only", tip, pr.sha, check=False)
            if merged.returncode != 0:
                lines = merged.stdout.splitlines()
                files = [f for f in lines[1 : lines.index("") if "" in lines else None] if f]
                verdicts.append(Verdict(pr.number, conflicts=files or ["(unnamed)"]))
                blocked[pr.head] = pr.number
                continue
            tree = merged.stdout.splitlines()[0]
            tip = git(
                "commit-tree", "--no-gpg-sign", tree, "-p", tip, "-p", pr.sha, "-m", f"#{pr.number}"
            ).stdout.strip()
            verdicts.append(Verdict(pr.number))
    return verdicts


def report(verdicts: list[Verdict], only: int | None) -> int:
    shown = [v for v in verdicts if only is None or v.number == only]
    if only is not None and not shown:
        print(f"#{only} is not an open pull request this check integrates (a bump, or closed).")
        return 0
    for v in shown:
        if v.conflicts:
            print(
                f"#{v.number} is not eligible: its head conflicts with the open pull requests "
                f"before it in {', '.join(v.conflicts)}. Fix its branch so the merge is clean."
            )
        elif v.waits_on is not None:
            print(f"#{v.number} waits on #{v.waits_on}, beneath it, whose head conflicts.")
        else:
            print(f"#{v.number} merges cleanly into the open pull requests before it.")
    return 0 if all(v.eligible for v in shown) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", help="owner/name, to read the open pull requests with gh")
    parser.add_argument("--prs-file", help="the open pull requests as gh api returns them")
    parser.add_argument("--pr", type=int, help="judge this one; without it, every one")
    args = parser.parse_args(argv)
    if bool(args.repo) == bool(args.prs_file):
        parser.error("give one of --repo and --prs-file")
    if args.prs_file:
        with open(args.prs_file, encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = fetch_open_prs(args.repo)
    return report(integrate(pulls(raw)), args.pr)


if __name__ == "__main__":
    sys.exit(main())
