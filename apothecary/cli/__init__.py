"""
Apothecary CLI module.

This module contains all CLI commands organized by functionality.
"""

# An install point of the guard (apothecary/stays_local.py), before any module
# of the command line runs: the `apothecary` console script and
# `python -m apothecary` both import this package first.
from ..stays_local import install_guard as _install_guard

_install_guard()

from .main import cli, main

__all__ = ["cli", "main"]
