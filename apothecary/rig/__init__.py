"""A rig of synths photographed, its controls read, and held in carlos.

Carlos knows what each device is: its catalogue entry places every control and
socket on the device's panel, and a ``carlos.patch`` says what the rig is. This
package looks. A setup pins each device's face in a camera's picture
(``reading.Setup``); the reader reads every knob, fader, drawbar and switch and
every socket off a picture through that face (``look``); a reading is held in
carlos as the rig at the values read, with each module's and lead's state
(``reading.held``); and a folder of frames is followed through a concert, its
record kept beside them (``concert``). ``simulated`` draws pictures of a rig at
known values, so the reader can be measured where every answer is known.

The plan is docs/plans/carlos-concert-rig-2026-10-29.md.
"""

# An install point of the guard (apothecary/stays_local.py), before any module
# in this package runs: it reads photographs.
from ..stays_local import install_guard as _install_guard

_install_guard()
