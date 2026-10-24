# Video frames into the same provider seam

| | |
|---|---|
| **Kind** | repo-edit |
| **Repo** | quaternionmedia/alfred |
| **State** | stub |
| **Depends on** | Photo → shapes → words → placed scenes → links |
| **Graduates to** | nothing yet; an integration stub, not a decision |
| **Verified** | alfred cloned and read. `alfred/core/routes/preview.py` extracts one JPEG at time `t` via `video.save_frame(...)`. `governance-status.yaml` shows `project/alfred` exists with four proposed records while the repo itself has `corpus_mounted_at: null` and all three IDE pointers missing — confirmed against the checkout. |

## What
alfred already extracts frames: `POST /preview/` takes a `Render` and a time `t`,
builds the EDL and calls `save_frame`, returning a JPEG path. `GET /videos/{video}`
serves partial content. That is the whole video path into the same
`ShapeProvider` Protocol at zero new capability — a frame is a photo.

## Why now
Not yet. The photo path should work end to end first; video adds a time axis to
a pipeline that does not yet have a scale axis. But it is worth knowing the seam
is already there, because it changes what the Protocol should look like now — a
`Detection` carrying a source identifier rather than assuming a file on disk.

## Seam
`ShapeProvider.detect()` takes a path today. If alfred is a plausible second
source, it should take something addressable instead, and that is a decision to
make in the seam record rather than to retrofit.

## Open questions
- **The local-only rule bites here.** Two programs on one machine talking to each
  other is arguably still local; two programs on two machines is not. Same line
  as item 1 in `../CONCERNS.md`, and this connection cannot be designed until it
  is drawn.
- alfred has a `project/alfred` branch with four proposed records but **no
  adoption in its own repository** — no `AGENTS.md`, no `governance/qm`
  submodule, no seed workflows, licence `NOASSERTION`, last pushed 2024-09-03.
  It cannot currently receive a record, so anything binding lives on apothecary's
  side of the seam.
- Its object storage is Google Cloud Storage (`tower-renders`, v4 signed URLs),
  which under §6 is a hosted service needing an inventory row and an ownability
  answer. Not this feature line's problem, but it is the same seam moat's MinIO
  would replace.
