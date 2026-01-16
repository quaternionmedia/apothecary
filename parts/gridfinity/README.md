# Gridfinity Parts

This directory contains 3D printable parts designed for the [Gridfinity](https://gridfinity.com) modular storage system. Gridfinity is a customizable and scalable storage solution that allows users to create organized storage units using standardized parts.

## Quick Start

```bash
# Initialize the submodule
uv run apothecary submodules

# List gridfinity part
uv run apothecary parts list | grep gridfinity

# Get part info
uv run apothecary parts info gridfinity
```

## Apothecary Integration

Gridfinity is integrated into Apothecary as a parametric part wrapper. You can use it programmatically:

```python
from apothecary.projects.parts.gridfinity import DEFAULT, BinParams, get_bin_dimensions

# Get dimensions for a 2x2x3 bin
dims = get_bin_dimensions(gridx=2, gridy=2, gridz=3)
print(f"Bin size: {dims['width_mm']}x{dims['depth_mm']}x{dims['height_mm']}mm")

# Create custom parameters
params = BinParams(
    gridx=3,
    gridy=2,
    gridz=6,
    divx=3,
    divy=2,
    scoop=1.0,
)

# Get bounds for the parametric bin
bounds = DEFAULT.get_bounds(params.model_dump())
print(f"Volume: {bounds.volume:.0f} mm³")

# Get OpenSCAD customizer parameters
scad_params = DEFAULT.get_scad_customizer_params(params.model_dump())
```

### Available Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gridx` | 1 | Grid units in X (1 unit = 42mm) |
| `gridy` | 1 | Grid units in Y |
| `gridz` | 3 | Height units (1 unit = 7mm) |
| `divx` | 1 | X compartment divisions |
| `divy` | 1 | Y compartment divisions |
| `include_lip` | true | Include stacking lip |
| `scoop` | 1.0 | Scoop percentage (0-1) |
| `style_tab` | AUTO | Tab style for compartments |

### Pre-configured Variants

The wrapper includes common bin configurations:

- `1x1x3` - Single unit bin, 3 height units
- `2x1x3` - 2-wide bin, 3 height units
- `2x2x3` - 2x2 bin, 3 height units
- `3x2x6` - Large bin, 6 height units
- `1x1x2_divided` - Small bin with 2x2 compartments

## Submodules

### gridfinity-rebuilt-openscad

This repository includes a Git submodule that contains the OpenSCAD designs for Gridfinity parts. The submodule is located at `parts/gridfinity/gridfinity-rebuilt-openscad`.

To initialize and update the submodule, run the following commands in the root directory of the main repository:

```bash
# Using Apothecary CLI (recommended)
uv run apothecary submodules

# Or manually with git
git submodule init --recursive
```

Update the submodule to ensure you have the latest designs:

```bash
git submodule update --remote --merge
```

## Gridfinity Specifications

The standard Gridfinity system uses:

- **Grid unit**: 42mm × 42mm base
- **Height unit**: 7mm increments
- **Stacking lip**: ~3.55mm (with fillet)

Standard bin heights (from Zack Freedman's original design):
- Z unit 2 → 18.4mm total
- Z unit 3 → 25.4mm total
- Z unit 6 → 46.4mm total

## References

- [Gridfinity](https://gridfinity.com) - Official Gridfinity site
- [gridfinity-rebuilt-openscad](https://github.com/kennetek/gridfinity-rebuilt-openscad) - OpenSCAD library
- [Gridfinity on Printables](https://www.printables.com/search/models?q=gridfinity) - Community designs
