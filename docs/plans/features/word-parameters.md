# Fitting a word's parameters to a detected shape

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | stub |
| **Depends on** | Photo → shapes → words → placed scenes → links |
| **Graduates to** | an extension of the word record |
| **Verified** | `word_for(shape)` as planned is a table lookup on kind and aspect ratio — no fitting. |

## What
Today a detected shape picks a word from a table and gets default parameters.
Fitting would solve for the word's parameters that best reproduce the detected
outline — a rectangle's corner radius, a slot's width, a wedge's angle.

## Why now
After scale references, because fitting to dimensionless coordinates produces
dimensionless parameters and the interesting parameters are all metric.

## Seam
`ShapeWord.params_model` is already a Pydantic model per word, so a fitter has a
typed target. The fit itself is numerical and belongs behind its own small
interface rather than inside `match.py`.

## Open questions
- A fitter is arguably an engine under P4. A least-squares fit over four
  parameters probably is not; a general shape-fitting library certainly is.
  The line needs drawing before the first import.
