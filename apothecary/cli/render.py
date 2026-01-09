"""Render-related CLI commands: testrun, render, render-jscad, templategenerate, validate."""

from pathlib import Path

import click

from ..example import create_example_scene
from ..scene import SceneLoadError, load_scene_from_json
from ..templates import TemplateRenderer


@click.command()
@click.option(
    "--output", "-o", type=click.Path(dir_okay=False, writable=True), default="example.scad"
)
def testrun(output: str):
    """Render the built-in example scene to a file."""
    scene = create_example_scene()
    code = scene.render()
    Path(output).write_text(code, encoding="utf-8")
    click.echo(f"Wrote {output} ({len(code.splitlines())} lines)")


@click.command("render")
@click.option(
    "--scene-file",
    type=click.Path(exists=True, dir_okay=False),
    help="JSON file describing a Scene model",
)
@click.option("--scene-json", type=str, help="Inline JSON string describing a Scene model")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default="scene.scad")
def render_scene(scene_file: str | None, scene_json: str | None, output: str):
    """Render a Scene from JSON into SCAD code."""
    try:
        scene = load_scene_from_json(
            scene_file=Path(scene_file) if scene_file else None,
            scene_json=scene_json,
            allow_example_fallback=True,
        )
    except SceneLoadError as e:
        raise click.ClickException(str(e))
    code = scene.render()
    Path(output).write_text(code, encoding="utf-8")
    click.echo(f"Rendered scene '{scene.name}' -> {output}")


@click.command("render-jscad")
@click.option(
    "--scene-file",
    type=click.Path(exists=True, dir_okay=False),
    help="JSON file describing a Scene model",
)
@click.option("--scene-json", type=str, help="Inline JSON string describing a Scene model")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default="scene.jscad.js")
def render_scene_jscad(scene_file: str | None, scene_json: str | None, output: str):
    """Render a Scene from JSON into a JSCAD JS module."""
    try:
        scene = load_scene_from_json(
            scene_file=Path(scene_file) if scene_file else None,
            scene_json=scene_json,
            allow_example_fallback=True,
        )
    except SceneLoadError as e:
        raise click.ClickException(str(e))

    code = scene.render_jscad()
    Path(output).write_text(code, encoding="utf-8")
    click.echo(f"Rendered JSCAD scene '{scene.name}' -> {output}")


@click.command("templategenerate")
@click.option(
    "--template", "-t", required=True, help="Jinja2 template string or @path/to/template.j2"
)
@click.option("--scene-file", type=click.Path(exists=True, dir_okay=False), help="Scene JSON file")
@click.option("--scene-json", type=str, help="Inline JSON string describing a Scene model")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default="templated.scad")
def template_generate(template: str, scene_file: str | None, scene_json: str | None, output: str):
    """Render a scene with a Jinja2 template."""
    template_content = (
        Path(template[1:]).read_text(encoding="utf-8") if template.startswith("@") else template
    )

    try:
        scene = load_scene_from_json(
            scene_file=Path(scene_file) if scene_file else None,
            scene_json=scene_json,
            allow_example_fallback=True,
        )
    except SceneLoadError as e:
        raise click.ClickException(str(e))

    renderer = TemplateRenderer()
    code = renderer.render_scene_template(scene, template_content)
    Path(output).write_text(code, encoding="utf-8")
    click.echo(f"Templated scene '{scene.name}' -> {output}")


@click.command()
@click.option("--scene-file", type=click.Path(exists=True, dir_okay=False))
@click.option("--scene-json", type=str, help="Inline JSON string describing a Scene model")
def validate(scene_file: str | None, scene_json: str | None):
    """Validate a scene JSON file."""
    try:
        scene = load_scene_from_json(
            scene_file=Path(scene_file) if scene_file else None,
            scene_json=scene_json,
            allow_example_fallback=False,
        )
    except SceneLoadError as e:
        raise click.ClickException(str(e))
    click.echo(f"Valid scene '{scene.name}' with {len(scene.objects)} top-level objects")
