"""Shared utilities for CLI commands."""

from importlib import import_module

import click

from ..projects.parts.skeleton import ROOT
from ..projects.registry import resolve_wrapper_module


def _safe_echo(message: str, **style):
    """Echo message with safe encoding handling for Windows.

    Accepts the same styling keywords as ``click.secho``; with none it behaves
    as ``click.echo``. A console on a legacy code page -- cp1252 is still the
    default on Windows -- raises rather than dropping the glyph, so every line
    carrying one has to come through here.
    """
    try:
        click.secho(message, **style)
    except UnicodeEncodeError:
        # Fallback: replace special characters with ASCII equivalents
        message = message.replace("✓", "[OK]").replace("✗", "[X]").replace("⚠️", "[!]")
        message = message.replace("•", "-")
        click.secho(message, **style)


def _load_part_wrapper(name: str):
    """Import a part wrapper by part name (stem)."""
    full = resolve_wrapper_module(name, ROOT)
    try:
        mod = import_module(full)
    except ModuleNotFoundError as e:
        raise click.ClickException(
            f"No wrapper module found for part '{name}'. Tried module '{full}'. "
            "Run 'apothecary parts list' to see available parts."
        ) from e
    if not hasattr(mod, "DEFAULT"):
        raise click.ClickException(f"Wrapper module '{full}' has no DEFAULT instance")
    return mod


def _coerce_scalar(text: str):
    """Best-effort literal for a part that declares no parameter model."""
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def _parse_param_overrides(part, pairs) -> dict:
    """Turn ``name=value`` strings into validated parameter overrides.

    Validation happens against the part's own ``params_model``, so a misspelled
    name or an out-of-range value fails here rather than after a render that
    silently ignored it -- OpenSCAD accepts any ``-D`` name, defined or not.
    """
    raw: dict[str, str] = {}
    for pair in pairs or ():
        if "=" not in pair:
            raise click.ClickException(f"--param expects name=value, got {pair!r}")
        name, value = pair.split("=", 1)
        raw[name.strip()] = value.strip()

    if not raw:
        return {}

    model_cls = getattr(part, "params_model", None)
    if model_cls is None:
        # No Python model: the part checks the names against its SCAD's variables.
        overrides = {name: _coerce_scalar(value) for name, value in raw.items()}
        try:
            return part.validate_overrides(overrides)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from None

    known = set(model_cls.model_fields)
    unknown = sorted(set(raw) - known)
    if unknown:
        raise click.ClickException(
            f"unknown parameter(s): {', '.join(unknown)}. "
            f"{part.name} declares: {', '.join(sorted(known))}"
        )

    try:
        validated = model_cls(**raw)
    except Exception as exc:
        raise click.ClickException(f"invalid parameters: {exc}") from exc

    return {name: getattr(validated, name) for name in raw}
