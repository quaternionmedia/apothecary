"""Inventory-related CLI commands: inventory group and subcommands."""

import json
from pathlib import Path

import click

from ..projects.registry import scan_projects, scan_templates, summarize_structure


@click.group()
def inventory():
    """Inventory projects, templates, and structure."""


@inventory.command("projects")
@click.option("--root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--json-out/--text", default=False)
def inventory_projects(root: str, json_out: bool):
    """List detected projects and parts in the repository."""
    root_path = Path(root).resolve()
    items = scan_projects(root_path)
    if json_out:
        click.echo(json.dumps([i.to_json() for i in items], indent=2))
        return
    for p in items:
        if p.kind == "part":
            suffix = f" [wrapper={p.wrapper}]" if p.wrapper else ""
            click.echo(f"part: {p.name} -> {p.path}{suffix}")
        else:
            click.echo(f"project: {p.name} (kind={p.kind}, readme={'yes' if p.readme else 'no'})")


@inventory.command("templates")
@click.option("--root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--json-out/--text", default=False)
def inventory_templates_cmd(root: str, json_out: bool):
    """List Jinja templates if a 'templates/' dir exists."""
    root_path = Path(root).resolve()
    templates = [str(p) for p in scan_templates(root_path)]
    if json_out:
        click.echo(json.dumps(templates, indent=2))
        return
    if not templates:
        click.echo("No templates found.")
        return
    for t in templates:
        click.echo(f"template: {t}")


@inventory.command("structure")
@click.option("--root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--json-out/--text", default=False)
def inventory_structure(root: str, json_out: bool):
    """Summarize repository structure: projects, parts, templates, missing READMEs."""
    root_path = Path(root).resolve()
    summary = summarize_structure(root_path)
    if json_out:
        click.echo(json.dumps(summary, indent=2))
        return
    click.echo(f"root: {summary['root']}")
    click.echo(f"projects: {summary['projects']}")
    click.echo(f"parts: {summary['parts']}")
    click.echo(f"templates: {summary['templates']}")
    click.echo(
        "missing READMEs: "
        + (", ".join(summary["missing_readmes"]) if summary["missing_readmes"] else "none")
    )
