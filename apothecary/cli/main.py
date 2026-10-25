"""Main CLI entry point that combines all command groups."""

import click

from .census import census
from .docs import docs
from .firmware import firmware
from .inventory import inventory
from .kernels import kernel_reference
from .openscad import openscad
from .parts import parts
from .photo import photo
from .preflight import preflight
from .release import release
from .render import render_scene, render_scene_jscad, template_generate, testrun, validate
from .server import dev, serve
from .slicer import slicer
from .spaces import problems, solutions
from .system import check, install, submodules, system
from .testing import test

# Commands for working on this repository rather than with it: its tests, its CI
# run here, its generated docs and its own measures. Listed after the rest.
REPOSITORY_COMMANDS = frozenset(
    {"census", "docs", "kernel-reference", "preflight", "release", "templategenerate", "test"}
)

START = """\b
Start here:
  1. apothecary check              what is installed here, and what is missing
  2. apothecary openscad install   an OpenSCAD with Manifold: fast renders, and the
                                   parts OpenSCAD 2021.01 is too old to build
  3. apothecary serve --demo       the viewer, with a simulated printer and board
walkthrough/00-getting-started.md says each step, then the four loops through the page."""


class _Cli(click.Group):
    """A group whose help lists a person's commands first, then the repository's own."""

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        listed = [
            (name, cmd)
            for name in self.list_commands(ctx)
            if (cmd := self.get_command(ctx, name)) is not None and not cmd.hidden
        ]
        for title, own in (("Commands", False), ("Working on Apothecary itself", True)):
            section = [(name, cmd) for name, cmd in listed if (name in REPOSITORY_COMMANDS) is own]
            if not section:
                continue
            limit = formatter.width - 6 - max(len(name) for name, _ in section)
            with formatter.section(title):
                formatter.write_dl([(name, cmd.get_short_help_str(limit)) for name, cmd in section])


@click.group(cls=_Cli, epilog=START)
def cli():
    """Apothecary: parts as OpenSCAD from Python, a viewer that zooms through them,
    and the boards, printers, slicer and pictures that make them real."""


# Register individual commands
cli.add_command(problems)
cli.add_command(solutions)
cli.add_command(system)
cli.add_command(check)
cli.add_command(install)
cli.add_command(submodules)
cli.add_command(testrun)
cli.add_command(render_scene)
cli.add_command(render_scene_jscad)
cli.add_command(template_generate)
cli.add_command(validate)
cli.add_command(serve)
cli.add_command(dev)

# Register command groups
cli.add_command(inventory)
cli.add_command(parts)
cli.add_command(preflight)
cli.add_command(release)
cli.add_command(photo)
cli.add_command(test)
cli.add_command(docs)
cli.add_command(census)
cli.add_command(kernel_reference)
cli.add_command(firmware)
cli.add_command(openscad)
cli.add_command(slicer)


def main():  # pragma: no cover - entry point
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
