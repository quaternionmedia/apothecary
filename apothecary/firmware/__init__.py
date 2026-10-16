"""Firmware toolchain seam: program Arduinos, ESP32s and similar from Apothecary.

Apothecary owns only the control plane here -- discovering sketches under
``parts/``, locating/installing the toolchain, validating inputs, and
streaming task output to the CLI and the web GUI. The engines that compile
and flash are bought, not built, and each toolchain module (``modules/``)
names its own: ``arduino-cli`` (boards, cores, libraries, compile, upload) and
``esptool`` (raw binary flashing for Espressif chips) for Arduino, ``cargo``
and ``espflash`` for Rust on the ESP32. Each is invoked over a subprocess seam
with a stable command line, never linked or vendored -- the same disposition
as the ``openscad`` binary. Ports are listed and listened to by the module
that finds them: through arduino-cli, or through pyserial
(``serial_monitor.py``).
"""

# An install point of the guard (apothecary/stays_local.py), before any module
# in this package runs: it reads the state folder, the serial link and its comms log.
from ..stays_local import install_guard as _install_guard

_install_guard()
