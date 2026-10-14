"""A managed slicer: a part or a made piece, sliced for the pinned printer, from the page.

Decided with the owner on 2026-10-10 (docs/plans/slicer-2026-10-10.md):

- **A slicer is a module** behind one interface (``modules/__init__.py``), as a
  firmware toolchain is. OrcaSlicer's command line is the first
  (``modules/orcaslicer.py``); another slicer is a module added, and the owner
  switches which is used with one line of the printer's profile.
- **Installed by apothecary**, as OpenSCAD is: a pinned release from its
  publisher, checked before it is opened, into the tools dir
  (``orcaslicer_installer.py``; ``apothecary slicer install``).
- **The printer's profile is kept with the printer's part**
  (``parts/ender3/slicer.json``; ``profiles.py``): OrcaSlicer's Creality Ender-3
  profile, and what the bench measured.
- **Print settings come from the part**: what its wrapper declares, the
  printer's profile filling the rest; a slice says which value came from where.
- **Slice is a step of the page**: its G-code is kept where the Print card's
  file box keeps a file (``service.py``), so Print follows Slice. The routes
  are ``api.py``'s; the page's step comes later.

Slicing writes files only: nothing here opens a serial port or sends anything
to a printer.
"""
