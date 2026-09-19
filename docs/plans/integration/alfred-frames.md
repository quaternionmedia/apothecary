# alfred frames as a Detection source

| | |
|---|---|
| **Kind** | integration |
| **Repo** | quaternionmedia/alfred + quaternionmedia/apothecary |
| **State** | stub |
| **Depends on** | Video frames into the same provider seam |
| **Graduates to** | nothing yet |
| **Verified** | `alfred/core/routes/preview.py` read: `POST /preview/` takes `t: float` and a `Render`, calls `video.save_frame(frame_name, t=t, withmask=False)` and returns the path. |

## What
`POST /preview` → a JPEG → a `ShapeProvider` → a `Detection` → a site. A frame is
a photo; nothing in the pipeline needs to know the difference.

## Why now
After the photo path works. Its value now is as a design constraint: if a frame
is a plausible second source, `ShapeProvider.detect()` should not assume a path
on local disk.

## Seam
The Protocol signature, decided now, in the seam record.

## Open questions
- alfred is behind `Depends(current_active_user)` for everything except `/auth`,
  so any cross-service call needs a credential story that neither project has.
- Its Celery task serialiser is `pickle`. Worth knowing before anything is queued
  across the boundary.
