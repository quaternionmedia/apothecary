"""Retired command names, kept hidden for one release so a script that calls one
learns what replaced it instead of meeting "No such command"."""

import click


def retired(name: str, instead: str) -> click.Command:
    """A hidden command that takes any arguments, prints `instead` and exits 1."""

    @click.command(
        name,
        hidden=True,
        help=f"Retired: {instead}.",
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )
    def command() -> None:
        raise click.ClickException(f"`apothecary {name}` is retired; {instead}")

    return command
