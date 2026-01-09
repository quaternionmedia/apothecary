"""
Apothecary CLI entry point.

This module re-exports the CLI from the cli subpackage for backward compatibility.
The actual implementation is in apothecary/cli/.
"""

from .cli import cli, main

__all__ = ["cli", "main"]
