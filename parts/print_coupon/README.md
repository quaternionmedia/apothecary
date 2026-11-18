# Print coupon

The printer's piece made to be measured: a plate with two square blocks standing on
it, a square pocket in each, a square window through the plate and a single-wall fin.
Every size on it is one a person reads with calipers, and each feature is labelled in
the print: **A** and **B** the blocks, **W** the window, **F** the fin, and **X** at the
plate's long side's far end. It prints flat on the bed with nothing over air, so it
needs no support.

It is a turn of the print tuning loop ([docs/print-tuning.md](../../docs/print-tuning.md)):
printed, read, and the readings typed in. Its sizes are chosen so what they read
separates what the loop solves for:

| Read | Its features | Separates |
|---|---|---|
| Outside sizes of three nominals along X and along Y | the plate (54 × 36), block A (20), block B (12) | a scale from the outer faces' offset |
| Inside sizes of three nominals along each | A's pocket (12), B's pocket (6), the window (8) | the holes' offset, with the same scale |
| At the base and above it | the plate and the window take in the first layer; the blocks and the pockets stand above it | the first layer's spread from the faces' |
| Three tops | the plate (2), B (8) and A (12) over the bed face | a scale in Z from the first layer's height |
| One line | the fin, 0.45 mm across | kept and said; it moves nothing |

The wrapper, `apothecary/projects/parts/print_coupon.py`, declares the plan (`measures`):
each feature in the order to read it, the jaws that read it, and the line they close
along with the two faces they meet, its nominal the distance between them.

```bash
uv run apothecary parts verify print_coupon     # the envelope, and each feature found on the render
uv run apothecary parts info print_coupon       # its parameters
```

## Reading it

- **The plate**, outside jaws flat on the table across its ends, X and then Y: the jaws
  take in its whole thickness, the first layer with it.
- **A and B**, outside jaws above the plate, X and Y. Keep the jaws off the plate: they
  read the block alone.
- **The pockets**, inside jaws, X and Y; **the window**, inside jaws through the plate,
  where it is narrowest.
- **The tops**, bed face to top: the plate at its front-left corner, B, then A.
- **The fin**, outside jaws halfway up.

Read each twice or more: a single reading's uncertainty is the caliper's resolution
alone, which understates it.

## Parameters worth tuning first

| | | |
|---|---|---|
| `a_size`, `b_size` | 20, 12 | The blocks: two sizes, or a scale is not told from an offset |
| `a_pocket`, `b_pocket` | 12, 6 | The pockets: two sizes, each leaving 2 mm of wall or more |
| `a_height`, `b_height`, `plate_t` | 10, 6, 2 | The tops: each a whole number of the slice's layers over its first |
| `fin_t` | 0.45 | One line of printer_1's 0.20 mm process (its `outer_wall_line_width`) |
| `gap`, `margin` | 6, 4 | Room for a jaw between features, and from the plate's edge |

A coupon whose blocks or pockets are of one size, or that does not fit its plate, is
refused saying why. It declares 0.2 mm layers and a 0.4 mm nozzle, so a slice puts
each top on a layer's; a top between two layers carries a layer's quantization in its
uncertainty.
