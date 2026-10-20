# A part that computes itself

**Hermetic.** Nothing here runs OpenSCAD; the mirror is what computes.

Most parts are a SCAD file whose top-level assignments are dimensions and a
wrapper that says how big the result is. The `airgap` part is the same shape
taken further: its assignments are a design -- two base curves, the features
each wears, how the stator is cut and framed, how it is wound -- and its SCAD
computes every surface from them. The part *is* its text, which is what
[page 06](06-editing-a-parts-scad.md)'s editor edits: a base form changed,
a slot string typed, and the part follows.

    >>> from apothecary.projects.parts.airgap import DEFAULT, Params
    >>> DEFAULT.name, DEFAULT.category
    ('airgap', 'electromechanical')

The model groups its fields as the SCAD's sections group its assignments, and
names each field as the SCAD names the assignment, so a control writes its own
line of the text.

    >>> list(Params.model_fields)
    ['r0', 'stack', 'gap', 'phi', 'resolution', 'show_rotor', 'show_stator', 'show_windings', 'rotor', 'stator', 'windings']
    >>> p = Params()
    >>> len(p.flat()), p.flat()["stator_teeth_n"], p.flat()["topology"]
    (71, 12, 'tooth')

The flat form -- the names as the SCAD has them, beside each other -- folds
into the groups, and a group's field reaches OpenSCAD by its own name.

    >>> moved = Params(rotor_base_form="ellipse", stator_teeth_n=18, topology="lap")
    >>> moved.rotor.rotor_base_form, moved.stator.stator_teeth_n, moved.windings.topology
    ('ellipse', 18, 'lap')
    >>> DEFAULT.scad_overrides(DEFAULT.validate_overrides({"rotor_rib_k": 5}))
    {'rotor_rib_k': 5}

## The SCAD as saved is the default

A part's default is its SCAD file as saved ([page 06](06-editing-a-parts-scad.md)):
the model starts where the file does, and `apothecary problems` names any
value where the two disagree. For the airgap there is none.

    >>> from apothecary.projects.parts.texts import defaults_disagree
    >>> defaults_disagree(DEFAULT)
    []

## The mirror

Python cannot run the SCAD's functions, and the envelope a part declares must
not wait for a render. `apothecary.projects.parts.airgap` computes the same
pipeline -- base curve, feature stack, placement, re-sampling about the axis,
the bore scaled so the closest approach is the nominal gap -- in the same
degrees and with the same nudges, and `tests/test_airgap_part.py` holds the two
together by running the SCAD with `-D echo_surfaces=true`. Here, at a coarse
resolution:

    >>> from apothecary.projects.parts.airgap import build_surfaces, build_winding
    >>> surfaces = build_surfaces(p, nt=360, m=1440)
    >>> round(surfaces.s0 * p.r0, 2)        # the bore's scale, in mm: solved, not set
    37.67
    >>> round(max(surfaces.rotor_r) * p.r0, 2), round(min(surfaces.bore_r) * p.r0, 2)
    (33.36, 34.86)
    >>> sum(surfaces.mask) == len(surfaces.mask)   # a full ring: every sample has iron behind it
    True

The gap at the closest approach is the nominal gap: the bore's minimum less
the rotor's maximum.

    >>> round(min(surfaces.bore_r) * p.r0 - max(surfaces.rotor_r) * p.r0, 2) == p.gap
    True

The winding reduces to conductor stations, two per tooth coil, each a signed
turn count at a stator angle; the same reduction feeds the Airgap panel's
field and torque tables.

    >>> winding = build_winding(p, surfaces)
    >>> len(winding.stations), winding.phases
    (24, 3)
    >>> sorted({s[2] for s in winding.stations})   # the phases the stations belong to
    [0, 1, 2]

The envelope follows the frame and the end-turns, from the mirror's own
geometry; the slow test holds it to the rendered STL within 0.05 mm.

    >>> size = DEFAULT.get_bounds().size
    >>> round(size.x, 1), round(size.y, 1), round(size.z, 1)
    (87.3, 87.3, 23.6)
    >>> round(DEFAULT.get_bounds({"show_windings": False}).size.z, 1)   # the stack alone
    20.0

## The panel's figures leave as a document

The Airgap panel of the viewer ([docs/airgap.md](../docs/airgap.md)) computes
the field, torque and dynamics model from this text in the browser, and says
its figures as one document, `airgap/metrics/1`. Python validates and renders
that document and computes none of it -- the split the org's monitoring-seam
record draws between a collector and a view.

    >>> from apothecary.airgap_metrics import AirgapMetrics, render_markdown
    >>> doc = AirgapMetrics.model_validate({
    ...     "schema": "airgap/metrics/1", "generated_at": "2026-10-20T09:00:00Z",
    ...     "groups": [{"id": "field", "metrics": [
    ...         {"key": "mean_torque", "label": "mean torque", "value": 0.00716, "unit": "N·m"}]}]})
    >>> doc.get("field.mean_torque").value
    0.00716
    >>> print(render_markdown(doc))
    # Airgap metrics
    <BLANKLINE>
    Schema `airgap/metrics/1` · generated 2026-10-20T09:00:00Z
    <BLANKLINE>
    ## Field and torque (static)
    <BLANKLINE>
    | Metric | Value | Note |
    |---|---|---|
    | mean torque (`field.mean_torque`) | 0.007 N·m |  |
    <BLANKLINE>

A group the contract does not name is refused, so a reader of a `/1` document
is never surprised.

    >>> from pydantic import ValidationError
    >>> try:
    ...     AirgapMetrics.model_validate({"schema": "airgap/metrics/1", "generated_at": "now",
    ...         "groups": [{"id": "thermal", "metrics": []}]})
    ... except ValidationError:
    ...     print("refused")
    refused

## Recipes

| | |
|---|---|
| Render it | `apothecary parts generate-stl airgap` |
| Render it rewound | `apothecary parts generate-stl airgap -p topology=lap -p pitch=3` |
| Check the envelope is true | `apothecary parts verify airgap` |
| Edit it as text | the parts library site, its ring, Part › Edit ([page 06](06-editing-a-parts-scad.md)) |
| Analyse it | the viewer's Airgap tab, or the canvas ring's Panels › Airgap ([docs/airgap.md](../docs/airgap.md)) |
| Read a copied metrics document back | `apothecary airgap metrics validate metrics.json --format md` |
| The document's contract | `apothecary airgap metrics schema` |
