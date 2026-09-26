"""Firmware toolchain seam: program Arduinos, ESP32s and similar from Apothecary.

Apothecary owns only the control plane here -- discovering sketches under
``parts/``, locating/installing the toolchain, validating inputs, and
streaming task output to the CLI and the web GUI. The engines that actually
compile and flash are bought, not built: ``arduino-cli`` (boards, cores,
libraries, compile, upload) and ``esptool`` (raw binary flashing for
Espressif chips). Both are invoked over a subprocess seam with a stable CLI
and JSON output contract, never linked or vendored -- the same disposition as
the ``openscad`` binary.
"""
