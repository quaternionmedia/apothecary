"""Main CLI entry point that combines all command groups."""

import click

from .docs import docs
from .inventory import inventory
from .parts import parts
from .render import render_scene, render_scene_jscad, template_generate, testrun, validate
from .server import dev, serve
from .system import check, install, system
from .testing import test


@click.group()
def cli():
    """Apothecary OpenSCAD framework CLI."""


# Register individual commands
cli.add_command(system)
cli.add_command(check)
cli.add_command(install)
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
cli.add_command(test)
cli.add_command(docs)


def main():  # pragma: no cover - entry point
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
