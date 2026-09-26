"""Commands for turning a picture into something you could build.

Everything here runs on your own machine with the network switched off, and
writes only where you point it. See ``docs/plans/proposals/runs-and-stays-local.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click

from ..vision import ScaleReference, get, names
from ..vision import build as build_arrangement
from ..vocabulary import starter_words, word_for


@click.group()
def photo():
    """Look at a picture and turn what is in it into shapes you can build."""


def _loopback_or_explain(host: str) -> str:
    """A server started from here listens on this machine only (apothecary/stays_local.py)."""
    from ..stays_local import require_loopback

    try:
        return require_loopback(host)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from None


def _look_or_explain(finder: str, image: Path):
    """Run a finder, turning every foreseeable failure into a plain sentence.

    Without this a mistyped file name, a half-downloaded picture or a
    hand-written description with a typo all came back as a wall of internal
    detail, which tells the person nothing they can act on.
    """
    try:
        chosen = get(finder)
    except KeyError:
        raise click.ClickException(f"no finder named {finder!r}; try one of {names()}") from None

    try:
        return chosen.look(image)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from None
    except ValueError as exc:
        raise click.ClickException(str(exc)) from None
    except OSError as exc:
        raise click.ClickException(
            f"{image} could not be read as a picture ({exc}). "
            "If it is not an image, or the download stopped part way, that would explain it."
        ) from None


@photo.command("look")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--finder",
    default="plain",
    show_default=True,
    help="Which shape finder to use. 'plain' looks at pixels; 'stated' reads a "
    "hand-written description sitting beside the picture.",
)
@click.option("--as-json", is_flag=True, help="Print the full result instead of a summary.")
def look(image: Path, finder: str, as_json: bool):
    """Report the flat shapes found in a picture.

    Nothing is measured. Positions come back as fractions of the picture,
    because a picture on its own cannot say how big anything is.
    """
    picture = _look_or_explain(finder, image)

    if as_json:
        click.echo(picture.model_dump_json(indent=2))
        return

    click.echo(f"{picture.name}: {len(picture.shapes)} shape(s), found by {picture.finder}")
    click.echo(f"picture is {picture.pixel_width} by {picture.pixel_height} pixels")
    if not picture.shapes:
        click.echo("nothing found — try a picture with clearer, separated shapes")
        return
    click.echo("")
    click.echo(f"{'shape':8} {'reads as':8} {'sure':>5}  where (fractions of the picture)")
    for shape in picture.shapes:
        choice = word_for(shape)
        where = (
            f"{shape.min_point.x:.2f},{shape.min_point.y:.2f} "
            f"to {shape.max_point.x:.2f},{shape.max_point.y:.2f}"
        )
        click.echo(f"{shape.kind.value:8} {choice.word:8} {shape.confidence:5.2f}  {where}")
    click.echo("")
    click.echo("Nothing above is a measurement. To get millimetres, use 'photo build'")
    click.echo("with --width-mm, or name a shape whose real width you know.")


@photo.command("build")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--finder", default="plain", show_default=True, help="Which shape finder to use.")
@click.option("--name", default=None, help="Name for the arrangement. Defaults to the file name.")
@click.option(
    "--width-mm",
    type=float,
    default=None,
    help="How wide the whole picture is in the real world, in millimetres.",
)
@click.option(
    "--known-shape",
    default=None,
    help="The label of one shape whose real width you know. Needs --known-width-mm.",
)
@click.option("--known-width-mm", type=float, default=None, help="That shape's real width.")
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the drawing instructions to this file instead of printing them.",
)
def build(
    image: Path,
    finder: str,
    name: Optional[str],
    width_mm: Optional[float],
    known_shape: Optional[str],
    known_width_mm: Optional[float],
    out: Optional[Path],
):
    """Turn a picture into an arrangement of named pieces.

    Without a real-world size the pieces are still placed, but nothing is
    measured and every piece says so.
    """
    picture = _look_or_explain(finder, image)

    if width_mm is not None and not (width_mm > 0 and width_mm < float("inf")):
        raise click.ClickException(
            f"--width-mm was {width_mm}; a real width is a number greater than zero"
        )
    if bool(known_shape) != bool(known_width_mm):
        raise click.ClickException(
            "--known-shape and --known-width-mm go together; give both or neither"
        )
    if known_shape and not any(s.label == known_shape for s in picture.shapes):
        labelled = sorted({s.label for s in picture.shapes if s.label})
        raise click.ClickException(
            f"nothing in this picture is labelled {known_shape!r}"
            + (
                f"; the labels here are {labelled}"
                if labelled
                else "; nothing here is labelled at all"
            )
            + ". Only a hand-written description carries labels, so try --finder stated."
        )

    scale = None
    if width_mm is not None or (known_shape and known_width_mm):
        scale = ScaleReference(
            millimetres_across=width_mm,
            known_shape=known_shape,
            known_width_mm=known_width_mm,
        )

    try:
        made = build_arrangement(picture, name=name, scale=scale, picture_path=image)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from None
    site, album = made.site, made.album
    report = site.validate()

    click.echo(f"{site.name}: {len(site.children)} piece(s), from {album.picture_name}")

    click.echo("")
    click.echo("grouped by word:")
    for word, paths in album.groups().items():
        click.echo(f"  {word:8} {len(paths):2}  {', '.join(paths)}")

    click.echo("")
    click.echo("where each piece came from:")
    unsized = {piece.name for piece in site.children if piece.status == "unsized"}
    for path, about in album.provenance.items():
        marker = "  (no real size)" if path in unsized else ""
        click.echo(f"  {path:10} {about.summary()}{marker}")

    doubtful = album.unsure()
    if doubtful:
        click.echo("")
        click.echo(f"least sure, worth looking at first: {', '.join(doubtful)}")
    click.echo(
        f"a machine picked the shape of {album.guessed_share():.0%} of these; "
        "nobody has confirmed them"
    )

    if not report.is_valid:
        click.echo("")
        click.echo("overlaps found:")
        for problem in report.violations:
            click.echo(f"  {problem.message}")
    elif any(p.status == "unsized" for p in site.children):
        click.echo("")
        click.echo("Nothing was measured, so the overlap check had nothing to check.")

    drawing = site.render()
    if out:
        if not out.parent.exists():
            raise click.ClickException(f"there is no folder at {out.parent}")
        out.write_text(drawing, encoding="utf-8")
        click.echo("")
        click.echo(f"written to {out}")
    else:
        click.echo("")
        click.echo(drawing)


@photo.command("words")
@click.option("--as-json", is_flag=True, help="Print the full list instead of a summary.")
def words(as_json: bool):
    """List the named pieces a found shape can turn into."""
    vocabulary = starter_words()
    if as_json:
        click.echo(
            json.dumps(
                [
                    {"name": w.name, "describes": w.describes, "tags": w.tags}
                    for w in vocabulary.all()
                ],
                indent=2,
            )
        )
        return
    click.echo(f"{len(vocabulary)} word(s):")
    for word in vocabulary.all():
        tags = f"  [{', '.join(word.tags)}]" if word.tags else ""
        click.echo(f"  {word.name:8} {word.describes}{tags}")


@photo.command("finders")
def finders():
    """List the shape finders available."""
    for finder_name in names():
        click.echo(finder_name)


@photo.command("check")
@click.option("--finder", default="plain", show_default=True, help="Which finder to measure.")
@click.option("--count", default=20, show_default=True, help="Pictures per condition.")
def check(finder: str, count: int):
    """Measure how well a finder does, on pictures whose answers are known.

    Draws its own pictures, so it needs nothing but this machine. A good score
    means it handles clean drawings — not that it handles photographs.
    """
    from ..vision.bench import run

    if count < 1:
        raise click.ClickException(
            "--count is how many pictures to draw, so it needs to be at least 1"
        )

    try:
        chosen = get(finder)
    except KeyError:
        raise click.ClickException(f"no finder named {finder!r}; try one of {names()}") from None

    conditions = [
        ("clear shapes", {}),
        ("turned and speckled", dict(turn=True, speckle=True)),
        ("softly blurred", dict(blur=2.0)),
        ("heavily blurred", dict(blur=5.0)),
        ("faint", dict(faintness=0.85)),
        ("small", dict(smallest=0.05, largest=0.10)),
        ("very small", dict(smallest=0.03, largest=0.06)),
        ("crowded", dict(crowd=8, smallest=0.08, largest=0.14)),
    ]

    click.echo(f"measuring the {finder!r} finder on {count} pictures per row")
    click.echo("")
    click.echo(f"{'condition':22} {'found':>6} {'named':>6} {'made up':>8} {'honest':>7}")
    for label, drawing in conditions:
        result, _ = run(chosen, count=count, **drawing)
        gap = result.honest
        honest = "  n/a" if gap is None else f"{gap:+.2f}"
        click.echo(
            f"{label:22} {result.found_rate:6.0%} {result.kind_rate:6.0%} "
            f"{result.spurious:8d} {honest:>7}"
        )
    click.echo("")
    click.echo("found   — of the shapes drawn, how many were reported in about the right place")
    click.echo("named   — of those, how many were called the right family")
    click.echo("made up — shapes reported that were never drawn; should always be zero")
    click.echo("honest  — how much less sure it is when wrong; positive means the")
    click.echo("          confidence can be trusted to flag its own bad guesses")


@photo.command("view")
@click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--finder", default="plain", show_default=True, help="Which shape finder to use.")
@click.option("--name", default=None, help="Name for the arrangement. Defaults to the file name.")
@click.option(
    "--width-mm",
    type=float,
    default=None,
    help="How wide the whole picture is in the real world, in millimetres.",
)
@click.option("--port", default=8000, show_default=True, help="Which port to listen on.")
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Which address to listen on: this machine only.",
)
def view(
    image: Path,
    finder: str,
    name: Optional[str],
    width_mm: Optional[float],
    port: int,
    host: str,
):
    """Look at a picture and open the viewer on what was built from it.

    Building and showing happen in one command because they happen in one
    program. An arrangement built from a picture is held in memory, so building
    it in one place and serving it from another would lose it in between.

    Listens on this machine only unless you say otherwise.
    """
    import uvicorn

    from ..api import _site_store, app
    from ..vision import ScaleReference
    from ..vision.shelf import shelf

    host = _loopback_or_explain(host)
    picture = _look_or_explain(finder, image)
    if width_mm is not None and not (width_mm > 0 and width_mm < float("inf")):
        raise click.ClickException(
            f"--width-mm was {width_mm}; a real width is a number greater than zero"
        )

    scale = ScaleReference(millimetres_across=width_mm) if width_mm is not None else None
    made = build_arrangement(picture, name=name, scale=scale, picture_path=image)

    stock = shelf()
    stock.put(made)
    _site_store.add(made.site.name, stock.factory(made.site.name), stock.checker(made.site.name))

    album = made.album
    click.echo(f"{made.site.name}: {len(made.site.children)} piece(s) from {album.picture_name}")
    click.echo(f"grouped into {len(album.groups())} word(s): {', '.join(album.groups())}")
    if not album.sized:
        click.echo("Nothing is measured — pass --width-mm to get millimetres.")
    click.echo("")
    click.echo(f"  the arrangement   http://{host}:{port}/viewer/sites/{made.site.name}")
    click.echo(f"  what is known     http://{host}:{port}/photos/{made.site.name}")
    click.echo(f"  the picture       http://{host}:{port}/photos/{made.site.name}/picture")
    click.echo("")
    click.echo("Stop with Ctrl-C.")

    uvicorn.run(app, host=host, port=port, log_level="warning")


def _pictures_in(where: tuple[Path, ...], pattern: str) -> list[Path]:
    """Every picture named, and every picture inside every folder named.

    Sorted, so two runs over one folder hand the pictures in in the same order
    and give the same answer. An unordered listing would make the whole result
    depend on how the machine happened to feel.
    """
    found: list[Path] = []
    for place in where:
        if place.is_dir():
            found.extend(sorted(p for p in place.glob(pattern) if p.is_file()))
        else:
            found.append(place)
    seen: set = set()
    unique: list[Path] = []
    for path in found:
        settled = path.resolve()
        if settled in seen:
            continue
        seen.add(settled)
        unique.append(path)
    return unique


@photo.command("gather")
@click.argument("where", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--finder", default="plain", show_default=True, help="Which shape finder to use.")
@click.option(
    "--pattern",
    default="*.png",
    show_default=True,
    help="Which files to take from a folder.",
)
@click.option(
    "--map-to",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write a picture of which photographs went together to this file.",
)
@click.option(
    "--answers",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="A file of things you have already decided. Your word wins.",
)
@click.option(
    "--ask",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write out the questions worth your time, for you to answer.",
)
@click.option("--most", default=8, show_default=True, help="How many questions to ask at once.")
@click.option("--everything", is_flag=True, help="Also list every pair judged to be unrelated.")
@click.option(
    "--view",
    "open_viewer",
    is_flag=True,
    help="Build one arrangement out of the lot and open the viewer on it.",
)
@click.option("--port", default=8000, show_default=True, help="Which port to listen on.")
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Which address to listen on: this machine only.",
)
def gather_pictures(
    where: tuple[Path, ...],
    finder: str,
    pattern: str,
    map_to: Optional[Path],
    answers: Optional[Path],
    ask: Optional[Path],
    most: int,
    everything: bool,
    open_viewer: bool,
    port: int,
    host: str,
):
    """Take in several pictures at once and work out which are of the same thing.

    Hand it a folder, or a list of pictures, or both. It says which went
    together, which stand alone, which could not be read, and which pairs it
    could not decide about — because a pair it cannot decide about is a real
    answer and not a gap.

    You are better at this than it is. Give it what you already know with
    --answers and your word wins outright; ask it what would help most with
    --ask and it will write the questions out for you to answer.
    """
    from ..gathering import as_text, gather
    from ..gathering.judgement import (
        CannotRead,
        PeopleDisagree,
        read_answers_file,
        unknown_names,
    )
    from ..gathering.picture_map import as_html
    from ..gathering.questions import as_sheet, how_many_worth_asking, theirs, worth_asking

    paths = _pictures_in(where, pattern)
    if not paths:
        raise click.ClickException(
            "no pictures found. Point at some files, or at a folder holding "
            f"files matching {pattern!r}, or pass a different --pattern."
        )
    if len(paths) < 2:
        raise click.ClickException(
            f"only one picture ({paths[0].name}). Working out which pictures go "
            "together needs at least two; for one picture on its own use "
            "`apothecary photo build`."
        )

    pictures = [_look_or_explain(finder, path) for path in paths]
    names_seen: dict = {}
    for path, picture in zip(paths, pictures, strict=True):
        names_seen.setdefault(picture.name, []).append(path)
    clashing = {name: found for name, found in names_seen.items() if len(found) > 1}
    if clashing:
        name, found = next(iter(sorted(clashing.items())))
        raise click.ClickException(
            f"more than one picture is called {name!r} ({', '.join(str(f) for f in found)}). "
            "Every answer here refers to a picture by name, so two pictures "
            "sharing one would make every answer ambiguous. Rename one."
        )

    said = []
    if answers is not None and answers.exists():
        try:
            said = read_answers_file(answers)
        except (CannotRead, PeopleDisagree) as trouble:
            raise click.ClickException(str(trouble)) from None
    elif answers is not None:
        click.echo(f"{answers} does not exist yet — nothing of yours was used.")

    strangers = unknown_names(said, [p.name for p in pictures])
    if strangers:
        raise click.ClickException(
            f"you named picture(s) that are not here: {', '.join(strangers)}. "
            "Almost always a typo or a renamed file — and silently ignoring it "
            "would mean your answer looked as though it had been taken and had "
            "not. The names in use are: "
            + ", ".join(sorted(p.name for p in pictures)[:12])
            + ("…" if len(pictures) > 12 else "")
        )

    try:
        result = gather(pictures, paths=paths, answers=said)
    except PeopleDisagree as trouble:
        # Raised inside gather(), not while reading the file, so catching it only
        # around the reading left this project's flagship refusal coming out as
        # thirty lines of internal detail.
        raise click.ClickException(str(trouble)) from None
    click.echo(as_text(result, everything=everything))

    if ask is not None:
        if most < 1:
            raise click.ClickException(
                f"--most was {most}. One is the fewest question worth writing "
                "out; to ask nothing, leave --ask off."
            )
        ask.parent.mkdir(parents=True, exist_ok=True)
        # Whatever is already in the file a person wrote is kept, whether or not
        # it was the file passed in as answers. Writing over somebody's notes
        # because they used two different file names is not a thing to do once.
        keep = ask.read_text(encoding="utf-8-sig") if ask.exists() else ""
        if answers is not None and answers.exists() and answers.resolve() != ask.resolve():
            keep = (
                theirs(answers.read_text(encoding="utf-8-sig")).rstrip() + "\n\n" + theirs(keep)
            ).strip()
        asked = worth_asking(result, most=most)
        withheld = max(0, how_many_worth_asking(result) - len(asked))
        ask.write_text(as_sheet(result, asked, already=keep, withheld=withheld), encoding="utf-8")
        click.echo(
            f"{len(asked)} question(s) worth your time, written to {ask}"
            + (f" ({withheld} more held back)" if withheld else "")
            + ". Answer them in place and hand the same file back with --answers."
        )

    if map_to is not None:
        map_to.parent.mkdir(parents=True, exist_ok=True)
        map_to.write_text(as_html(result), encoding="utf-8")
        click.echo(f"A picture of what went with what: {map_to}")

    if not open_viewer:
        return

    import uvicorn

    from ..api import _site_store, app
    from ..gathering import whole_gathering
    from ..vision.shelf import shelf

    host = _loopback_or_explain(host)

    by_name = {picture.name: (picture, path) for picture, path in zip(pictures, paths, strict=True)}
    built = {
        reading.picture: build_arrangement(
            by_name[reading.picture][0], picture_path=by_name[reading.picture][1]
        )
        for reading in result.readings
        if reading.readable
    }
    if not built:
        raise click.ClickException(
            "nothing could be read from any of these pictures, so there is "
            "nothing to show. The report above says why for each one."
        )
    together = whole_gathering(result, built)

    stock = shelf()
    stock.put(together)
    _site_store.add(
        together.site.name,
        stock.factory(together.site.name),
        stock.checker(together.site.name),
    )

    click.echo("")
    click.echo(f"  everything together  http://{host}:{port}/viewer/sites/{together.site.name}")
    click.echo(f"  what is known        http://{host}:{port}/photos/{together.site.name}")
    click.echo("")
    click.echo("Stop with Ctrl-C.")
    uvicorn.run(app, host=host, port=port, log_level="warning")


@photo.command("gather-check")
@click.option("--finder", default="plain", show_default=True, help="Which finder to measure.")
@click.option("--each", default=6, show_default=True, help="Occasions of each kind.")
@click.option("--seed", default=20260820, show_default=True, help="Which pictures get drawn.")
def gather_check(finder: str, each: int, seed: int):
    """Measure how well the sorting does on pictures whose answers are known."""
    from ..gathering import bench

    try:
        chosen = get(finder)
    except KeyError:
        raise click.ClickException(f"no finder named {finder!r}; try one of {names()}") from None

    result = bench.run(chosen, each=each, seed=seed)
    click.echo(result.summary())
    if result.joined_wrongly:
        click.echo("")
        click.echo(
            f"{result.joined_wrongly} unrelated pair(s) were joined into one thing. "
            "That is the failure that matters; the rest cost a person a moment, "
            "this one builds an object out of two things that were never together."
        )
    for mistake in result.mistakes:
        click.echo(f"  {mistake}")
