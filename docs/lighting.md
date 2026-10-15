# Lighting: a venue's rig, and a console's levels

A site can carry a lighting rig: fixture types, a patch (channel, universe and
address, position, orientation), and live levels from a console. The viewer draws
each placed fixture in the colour its levels give it, with a beam, and lists the
patches that have no position in a panel. `apothecary/lighting.py` is the model
and is not tied to one venue; `apothecary/echs_pac_site.py` is the first rig.

## The ECHS PAC

The school's exports (`ECHS-PAC-patches.csv`, `ECHS-PAC-fixture-parameters.csv`,
the as-built PDF) are read at runtime from `ECHS-PAC/` in the checkout, or from
`$APOTHECARY_ECHS_PAC_DIR`. They are not committed (`.gitignore`). Without them
the `echs_pac` site is not registered and its tests skip.

The shell is six boxes read off drawing AV1.0 at about 0.039 m per point of the
PDF; it is a stand-in until the drawing's outline is traced and the height is
known. Positions in the patch are metres, the site is millimetres.

## Getting levels in

- `apothecary serve --console-sacn` listens on UDP 5568 for a console's sACN
  (E1.31), multicast or unicast to this machine, for the universes the rig
  patches. Point the console's (or Eos Visualizer's) sACN output at this machine.
  Only addressed fixtures carry DMX; the DMX channel order of each fixture type
  is in `lighting.DMX_MAPS`.
- `apothecary serve --console-osc` listens on UDP 8001 for an Eos console's OSC
  output and shows its status (command line, active channels) beside the lighting.
  In Eos, Setup > System > Show Control, set OSC to UDP, the TX IP to this
  machine's address and the TX port to 8001. It keeps the latest arguments of each
  `/eos/out/...` message (`status` in the state). It carries no levels: Eos sends
  per-channel levels only to a program that has subscribed, and a subscription is a
  message sent to the console, which the guard refuses.
- `PUT /sites/{site}/lighting/state` takes levels by channel number
  (`{"levels": {"1": {"Intens": 0.5}}}`) or a universe's slots as base64. This is
  how a bridge feeds what has no address: movers, virtual layers and servers,
  scenic elements.
- `apothecary lighting simulate` sweeps every fixture, for a demo with no console.
- `GET /sites/{site}/lighting` is the rig and its checks; `GET .../lighting/state`
  is the latest levels, their age, and each channel's colour.

## What the guard allows

`apothecary/stays_local.py` still refuses every connect and send beyond this
machine. The one change is `console_listener()`: a UDP socket on a console port
that may bind beyond loopback, on 5568 (sACN) or 8001 (OSC) alone, and receives
only. A test holds it to the two receivers.

Not built: asking the console for anything (OSC subscribe or get).
