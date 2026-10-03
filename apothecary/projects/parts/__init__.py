"""Per-part wrappers with metadata and parameter schemas.

Each module in this package corresponds to a .scad file in the
`parts/<part_name>/` directory. Modules expose a `Part` class that inherits from
`BasePart` and a `Params` Pydantic model describing tunable parameters.
"""
