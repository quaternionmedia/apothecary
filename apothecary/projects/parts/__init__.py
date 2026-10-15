"""Per-part wrappers with metadata and parameter schemas, and what they share.

A wrapper module corresponds to a .scad file in the `parts/<part_name>/`
directory and exposes `DEFAULT`, a `BasePart` describing the part; a wrapper
whose parameters are modelled also has a `Params` Pydantic model. The other
modules here are the machinery every part uses: `base`, `params`,
`stl_renderer`, `variants`, `saved`, `readiness` and the rest.
"""
