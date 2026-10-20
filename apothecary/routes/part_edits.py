"""A part's SCAD edited from the browser: drafts checked and rendered, and
saves as variants in git.

The server side of the part editor and the SCAD editor (docs/viewer.md). A
draft is the part's SCAD as the page holds it, sent whole with each request; nothing is
kept between requests but what the variant cache and git keep.

- ``POST /parts/{name}/draft/check`` ``{scad, params}``: the draft evaluated
  and not rendered (apothecary/projects/parts/drafts.py) -- what OpenSCAD said
  of it by line, naming the part's SCAD, alone and with the staged values as
  ``-D``; the fields an editor builds its controls from (the part's model's,
  or, for a part without one, what the draft itself declares where OpenSCAD
  lists it); and the staged ``params`` checked against them. What a page asks
  once typing pauses.
- ``POST /parts/{name}/draft/render`` ``{scad, params}``: the draft rendered
  into the variant cache, answered as ``POST /parts/{name}/stl/generate``
  answers (``draft`` naming the text), errors by line in a 422 as Apply's are.
  A newer request from the same ``page`` stops this one's OpenSCAD run (409),
  an Apply's included. A draft the same as the part's SCAD is the part.
- ``GET /parts/{name}/variants/{key}/scad``: the draft a cached variant was
  rendered from, for a tab reloaded on it (``?download=true``: as a file).
- ``POST /parts/{name}/draft/scad`` ``{scad}``: the draft handed back as a file
  to save, named as the part's SCAD: Download of the edit.
- ``GET /parts/{name}/assignments``, ``POST /parts/{name}/assignments``
  ``{scad}``: a text's top-level assignments with their spans, read without
  OpenSCAD (the page's first load); the check answers them too, computed
  values evaluated.
- ``GET /parts/{name}/saved``, ``POST /parts/{name}/saved`` ``{name, scad?,
  params}``, ``GET /parts/{name}/saved/{variant}``: a part's variants saved in
  git (apothecary/projects/parts/saved.py), listed from the part's refs, saved
  as a commit to ``refs/apothecary/variants/<part>/<name>`` by git's plumbing,
  and read back with their SCAD. No route here merges one or writes the
  working tree: making a variant the part's source is a merge the person does.
- Managing them, by git's plumbing alone: ``POST .../saved/{variant}/rename``
  and ``/duplicate`` ``{to}``; ``GET .../saved/{variant}/history`` and ``POST
  .../saved/{variant}/restore`` ``{commit}``; ``DELETE .../saved/{variant}``,
  which moves it to the trash (``refs/apothecary/trash/<part>/<name>``), ``GET
  /parts/{name}/trash``, ``POST .../trash/{variant}/restore`` ``{to?}``, and
  emptying it, a separate route that asks ``confirm=true``: ``DELETE
  /parts/{name}/trash`` (all) or ``DELETE /parts/{name}/trash/{variant}``.
- ``GET /parts/{name}/compare?a=&b=``: two variants side by side -- saved ones
  by name, ``@part`` for the part's own SCAD at its defaults, ``@<key>`` for a
  cached render -- their SCAD's diff, the parameters that differ, and each
  one's measured bounds (rendered, through the queue, where not cached).

A part whose geometry is Python (the snowplow) is read-only: its SCAD is the
one its geometry generates (``GET /parts/{name}/scad``), and a draft or a save
of it is a 403.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..projects.parts.assignments import Assignment, differences
from ..projects.parts.base import BasePart
from ..projects.parts.customizer import (
    INSTALL_HINT,
    lists_parameters,
    merged,
    part_check,
    scad_fields,
)
from ..projects.parts.drafts import (
    DRAFT_LIMIT,
    ReadOnly,
    check_and_compile,
    check_draft,
    compile_draft,
    draft_digest,
    refuse_read_only,
)
from ..projects.parts.openscad_messages import OpenSCADMessage
from ..projects.parts.params import (
    FROM_CUSTOMIZER,
    FROM_MODEL,
    FieldError,
    ParamField,
    params_spec,
)
from ..projects.parts.saved import (
    KEEP_DEFAULT,
    GitError,
    Moved,
    NoSuchVariant,
    NotInGit,
    SavedVariant,
    Taken,
    UpstreamEdit,
    VariantCommit,
    check_name,
    delete_variant,
    duplicate_variant,
    empty_trash,
    list_saved,
    list_trash,
    read_saved,
    rename_variant,
    restore_from_trash,
    restore_variant,
    save_variant,
    variant_history,
)
from ..projects.parts.stl_renderer import SUPERSEDED, get_renderer, part_renderer, runs_for
from ..projects.parts.texts import (
    ValueCheck,
    as_edited,
    assignments_of,
    check_values,
    is_overlaid,
    own_text,
    upstream_path,
    with_params,
)
from ..projects.parts.variants import (
    first_error,
    make_variant,
    read_variant_draft,
)

router = APIRouter(tags=["parts"])

PAGE = Query(
    None,
    max_length=128,
    description="An id the page makes up once per load. A newer request from the same page "
    "for the same part stops this one's OpenSCAD run (409).",
)


def _api():
    from .. import api

    return api


def _editable(name: str) -> BasePart:
    """The part, or a 403 for one whose SCAD is generated by its Python geometry."""
    part = _api()._load_part_wrapper(name)
    try:
        refuse_read_only(part)
    except ReadOnly as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return part


def _openscad_or_503() -> None:
    if not get_renderer().is_available:
        raise HTTPException(
            status_code=503, detail="OpenSCAD not installed. Cannot check or render."
        )


class DraftRequest(BaseModel):
    """A part's text as the page holds it: its values are in it."""

    scad: str = Field(
        ...,
        max_length=DRAFT_LIMIT,
        description="The whole text, as edited: the part's SCAD, or for a part in a "
        "submodule its overlay",
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Values sent on the side: written into the text first (the answer's "
        "text says how)",
    )
    editor_version: Optional[Union[int, Annotated[str, Field(max_length=64)]]] = Field(
        None,
        description="The page's own name for the state of its editor when it asked: "
        "handed back in the answer as it came",
    )


class DraftCheck(BaseModel):
    """A draft evaluated, not rendered, and its staged parameters checked."""

    part: str
    draft: str = Field(description="The sha256 of the text checked")
    edited: bool = Field(description="It differs from the part's SCAD on disk")
    valid: bool = Field(
        description="OpenSCAD evaluated it without an error, and the staged parameters are valid"
    )
    checked_by: str = Field(
        description='"param": the customizer\'s export, which lists parameters; '
        '"echo": the echo export (2021.01), which only evaluates'
    )
    openscad: Optional[str] = None
    listed: bool = Field(description="OpenSCAD listed the parameters the draft declares")
    with_values: bool = Field(
        False,
        description="OpenSCAD also compiled it (the CSG export), as a render would: what "
        "it said is in messages, each computed assignment's value in assignments",
    )
    kind: str = Field(
        "source", description='"source": the part\'s SCAD; "overlay": a part in a submodule'
    )
    assignments: List[Assignment] = Field(
        default_factory=list,
        description="The text's top-level assignments, with where each value stands: what "
        "the page's controls are, and rewrite",
    )
    values: List[ValueCheck] = Field(
        default_factory=list,
        description="Each value the text gives, as the part's model (or listing) checks it",
    )
    text: Optional[str] = Field(
        None, description="The text checked, where params were written into it; else null"
    )
    messages: List[OpenSCADMessage] = Field(default_factory=list)
    source: Optional[str] = Field(
        None, description='Where ``fields`` come from: "model" or "customizer"; None for none'
    )
    fields: List[ParamField] = Field(default_factory=list)
    params: Dict[str, Any] = Field(default_factory=dict)
    errors: List[FieldError] = Field(default_factory=list)
    note: Optional[str] = Field(None, description="What could not be done, and why")
    editor_version: Optional[Union[int, str]] = Field(
        None, description="As the request named the state of the editor it was asked for"
    )


def the_text(
    api, part: BasePart, scad: Optional[str], params, renderer=None, lenient: bool = False
) -> str:
    """The text a request means (``texts.as_edited``: a part in a submodule's is
    its overlay, an edit of its upstream file a 403), with any ``params`` sent
    on the side written into it -- checked as a render's are (422) -- so there
    is one path. ``lenient`` (a check): a value its checks refuse is written in
    as it came, for the check of the text to say why."""
    try:
        text = as_edited(part, scad)
    except UpstreamEdit as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    if not params:
        return text
    listing = None
    if part.params_model is None:
        renderer = renderer or part_renderer(part)
        if renderer.is_available and lists_parameters(renderer.openscad_path):
            listing = _listing_for(part, text, renderer)
    # Their names are checked against the text's -- an overlay's, its upstream's.
    names_from = None if is_overlaid(part) else text
    try:
        overrides = api.checked_overrides(part, params, listing, scad_text=names_from)
    except HTTPException:
        if not lenient:
            raise
        return _written_as_they_came(part, text, params)
    return with_params(part, text, overrides)


def _written_as_they_came(part: BasePart, text: str, params: Dict[str, Any]) -> str:
    """``params`` written into ``text`` unchecked: a number sent as text read as
    one, and anything no SCAD literal carries left out."""
    raw: Dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str):
            try:
                value = float(value) if "." in value or "e" in value.lower() else int(value)
            except ValueError:
                pass
        raw[key] = value
    try:
        return with_params(part, text, raw)
    except (TypeError, ValueError):
        written = text
        for key, value in raw.items():
            try:
                written = with_params(part, written, {key: value})
            except (TypeError, ValueError):
                continue
        return written


def _listing_for(part: BasePart, text: str, renderer, cancel=None):
    """What the customizer lists for ``text``: for an overlay, its upstream's."""
    if is_overlaid(part):
        return part_check(part, renderer).parameters
    return check_draft(part, text, renderer, cancel).parameters


def _filled(assignments: List[Assignment], compiled) -> List[Assignment]:
    """Each computed assignment with the value its compile evaluated it to."""
    if compiled is None:
        return assignments
    out = []
    for a in assignments:
        if a.computed and a.name in compiled.printed:
            a = a.model_copy(
                update={
                    "value": compiled.evaluated.get(a.name),
                    "value_known": a.name in compiled.evaluated,
                    "printed": compiled.printed[a.name],
                }
            )
        out.append(a)
    return out


@router.post("/parts/{name}/draft/check", response_model=DraftCheck)
def check_part_draft(name: str, body: DraftRequest, page: Optional[str] = PAGE):
    """A draft of the part's text, evaluated by OpenSCAD and not rendered.

    The text is the truth: its values are what it assigns, and nothing is
    passed on the side. ``params``, where a caller sends them, are written
    into it first, and ``text`` is then what was checked. Two runs at
    once, written beside where the text stands so its includes resolve: the
    parameter export (or the echo export, on 2021.01) and the CSG export, which
    compiles it as a render would and echoes each computed assignment's value
    after it. ``messages`` are what both said, by line of the text.

    ``assignments`` are its top-level assignments, each with its value (a
    computed one's as OpenSCAD evaluated it), its line and its value's span:
    what the page builds its controls from and rewrites (the grammar is
    apothecary/projects/parts/assignments.py's). For a part in a submodule the
    text is its overlay: its own assignments, then each upstream parameter it
    does not set (``set`` false). ``values`` are those values checked by the
    part's model -- a range, a type, a whole number -- or against what its
    SCAD's customizer lists, each with its field and why it is refused; a
    refused one makes the draft not ``valid``. ``fields`` are the model's, or
    the customizer's listing. A newer check from the same ``page`` stops this
    one (409). A part built by Python geometry is a 403: its SCAD is generated,
    and its controls drive its model."""
    api = _api()
    part = _editable(name)
    _openscad_or_503()
    renderer = part_renderer(part)
    text = the_text(api, part, body.scad, body.params, renderer, lenient=True)
    digest = draft_digest(text)
    slot = f"{page}#check" if page else None
    cancel = api._page_renders.begin(part.name, slot, digest)
    try:
        with runs_for(part.name, page):
            check, compiled = check_and_compile(part, text, {}, renderer, cancel)
            overlaid = is_overlaid(part)
            listing = part_check(part, renderer).parameters if overlaid else check.parameters
    finally:
        api._page_renders.end(part.name, slot, cancel)
    if check.cancelled or compiled.cancelled:
        raise HTTPException(
            status_code=409,
            detail={
                "message": check.error_message or compiled.error_message,
                "superseded": True,
                "editor_version": body.editor_version,
            },
        )

    note = None
    if part.params_model is not None:
        fields, source = params_spec(part).fields, FROM_MODEL
    else:
        shown = part.source_file.read_text(encoding="utf-8") if overlaid else text
        fields = scad_fields(listing, text=shown) if listing else []
        source = FROM_CUSTOMIZER if listing else None
        if not check.lists:
            note = f"{check.openscad} cannot list the draft's parameters ({INSTALL_HINT})"
    if check.error_message:
        note = check.error_message if note is None else f"{check.error_message}; {note}"
    with_values = compiled.openscad is not None
    messages = merged(check.messages, compiled.messages) if with_values else check.messages
    said_error = any(m.level == "error" for m in messages)
    checked = check_values(
        part, text, compiled.evaluated, listing if part.params_model is None else None
    )
    params = (
        jsonable_encoder(checked.model_params)
        if part.params_model is not None
        else {v.name: v.value for v in checked.values if v.valid}
    )
    return DraftCheck(
        part=part.name,
        draft=digest,
        edited=text != own_text(part),
        valid=check.ok and not said_error and checked.valid,
        checked_by=check.how,
        openscad=check.openscad,
        listed=listing is not None,
        with_values=with_values,
        kind="overlay" if overlaid else "source",
        assignments=_filled(assignments_of(part, text), compiled),
        values=checked.values,
        text=text if text != body.scad else None,
        messages=messages,
        source=source,
        fields=fields,
        params=params,
        errors=checked.errors,
        note=note,
        editor_version=body.editor_version,
    )


def render_text(
    api,
    name: str,
    part: BasePart,
    text: str,
    force: bool,
    page: Optional[str],
    editor_version=None,
    sent: Optional[str] = None,
    values: Optional[Dict[str, Any]] = None,
):
    """A part's text rendered into the variant cache, as generate and a draft's
    render answer it: its values checked first (a refused one is a 422 saying
    which and why), nothing passed on the side. A newer request from the same
    ``page`` stops this one wherever it is (409). ``values``: the text is the
    part's own with these written in (Apply of its numbers), recorded as the
    part with them -- ``params`` them, ``draft`` null."""
    renderer = part_renderer(part)
    cancel = api._page_renders.begin(part.name, page, f"{force}\0{draft_digest(text)}")
    try:
        with runs_for(part.name, page):
            listing = None
            if part.params_model is None and lists_parameters(renderer.openscad_path):
                if is_overlaid(part):
                    listing = part_check(part, renderer).parameters
                else:
                    listed = check_draft(part, text, renderer, cancel)
                    if listed.cancelled:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "message": SUPERSEDED,
                                "superseded": True,
                                "editor_version": editor_version,
                            },
                        )
                    listing = listed.parameters
            checked = check_values(part, text, None, listing)
            if not checked.valid:
                raise HTTPException(
                    status_code=422,
                    detail="; ".join(f"{e.field}: {e.message}" for e in checked.errors),
                )
            made = make_variant(part, {}, force=force, cancel=cancel, draft=text, values=values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    finally:
        api._page_renders.end(part.name, page, cancel)
    return api.made_answer(
        name,
        part,
        made,
        checked.model_params,
        editor_version,
        shown_params=None if values is not None else differences(text, own_text(part)),
        text=text if sent is not None and text != sent else None,
    )


@router.post("/parts/{name}/draft/render")
def render_part_draft(
    name: str,
    body: DraftRequest,
    force: bool = Query(False, description="Render even what the cache already has"),
    page: Optional[str] = PAGE,
):
    """A draft of the part's text rendered into the variant cache.

    Answered as ``POST /parts/{name}/stl/generate`` answers, ``draft`` the
    sha256 of the text (None when it is the part's own text, which is then the
    part). The text carries its values: nothing is passed on the side, and
    ``params``, where a caller sends them, are written into it first (the
    answer's ``text`` is then what was rendered). Its values are checked
    by the part's model, or what its customizer lists (422). The draft is
    written beside where the text stands for the one run -- for a part in a
    submodule, where its overlay is -- and the part's own SCAD and STL are
    never touched. OpenSCAD's errors come back by line in a 422, as Apply's do;
    a newer request from the same ``page`` stops this one (409). A part built
    by Python geometry is a 403."""
    api = _api()
    part = _editable(name)
    _openscad_or_503()
    text = the_text(api, part, body.scad, body.params)
    return render_text(api, name, part, text, force, page, body.editor_version, sent=body.scad)


@router.get("/parts/{name}/variants/{variant}/scad", response_class=PlainTextResponse)
def get_variant_draft(
    name: str,
    variant: str,
    download: bool = Query(False, description="As a file to save, named as the part's SCAD"),
):
    """The draft a cached variant was rendered from: what a tab reloaded on that
    variant shows in its editor, or, with ``download``, saves. 404 for a variant
    of the part's own SCAD (``GET /parts/{name}/scad`` is that), or one the cache
    has let go. Its text never changes under its key: the browser keeps it."""
    part = _api()._load_part_wrapper(name)
    text = read_variant_draft(part, variant)
    if text is None:
        raise HTTPException(
            status_code=404,
            detail=f"No draft is cached for variant '{variant}' of '{name}': a variant of the "
            f"part's own SCAD has none (GET /parts/{name}/scad), and the cache lets go of old ones",
        )
    headers = {"X-Part-Variant": variant, "Cache-Control": _api().IMMUTABLE}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{part.source_file.name}"'
    return PlainTextResponse(text, headers=headers)


class TextRequest(BaseModel):
    """A part's text as the page holds it."""

    scad: str = Field(..., max_length=DRAFT_LIMIT, description="The whole text, as edited")


class AssignmentsAnswer(BaseModel):
    """A text's top-level assignments, read without OpenSCAD."""

    part: str
    kind: str = Field(description='"source": the part\'s SCAD; "overlay": a part in a submodule')
    draft: str = Field(description="The sha256 of the text read")
    upstream: Optional[str] = Field(
        None, description="An overlay's upstream SCAD (GET /parts/{name}/upstream serves it)"
    )
    assignments: List[Assignment] = Field(default_factory=list)


def _assignments_answer(part: BasePart, text: str) -> AssignmentsAnswer:
    """``text``'s assignments, computed values filled in where a check of the
    same text remembers them; no OpenSCAD runs."""
    from ..projects.parts.customizer import known_compile
    from ..projects.parts.texts import edit_file

    renderer = part_renderer(part)
    known = known_compile(edit_file(part), text, {}, renderer) if renderer.is_available else None
    overlaid = is_overlaid(part)
    return AssignmentsAnswer(
        part=part.name,
        kind="overlay" if overlaid else "source",
        draft=draft_digest(text),
        upstream=upstream_path(part) if overlaid else None,
        assignments=_filled(assignments_of(part, text), known),
    )


@router.get("/parts/{name}/assignments", response_model=AssignmentsAnswer)
def part_assignments(name: str):
    """The top-level assignments of the part's own text -- its SCAD as saved, or
    for a part in a submodule its overlay -- for a page's first load: each
    with its value (a literal's; a computed one's where a check of this text
    remembers it, ``value_known``), its line and its value's span, its comment
    and what the comment tells (range, step, options, unit), its caption and
    group, and whether it is a ``parameter`` (what gets a control). Read in
    Python, no OpenSCAD run: light. The grammar is
    apothecary/projects/parts/assignments.py's. A part built by Python
    geometry is a 403: its controls drive its model, its text follows."""
    part = _editable(name)
    return _assignments_answer(part, own_text(part))


@router.post("/parts/{name}/assignments", response_model=AssignmentsAnswer)
def text_assignments(name: str, body: TextRequest):
    """The same, of the text the page holds: no OpenSCAD run. For a part in a
    submodule a text that is no overlay is a 403 (an edit of its upstream)."""
    part = _editable(name)
    try:
        text = as_edited(part, body.scad)
    except UpstreamEdit as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return _assignments_answer(part, text)


@router.post("/parts/{name}/draft/scad", response_class=PlainTextResponse)
def download_part_draft(name: str, body: DraftRequest):
    """The draft the page holds, handed back as a file to save: Download SCAD of
    the edit, rendered or not. Named as the part's SCAD
    (``Content-Disposition: attachment``), its text exactly as sent; nothing is
    written or kept. A part built by Python geometry is a 403: its SCAD is
    generated (``GET /parts/{name}/scad`` serves it)."""
    part = _editable(name)
    return PlainTextResponse(
        body.scad,
        media_type="application/x-openscad",
        headers={
            "Content-Disposition": f'attachment; filename="{part.source_file.name}"',
            "Cache-Control": "no-store",
            "X-Part-Scad": "draft",
            "X-Part-Draft": draft_digest(body.scad),
        },
    )


# --- saved in git -------------------------------------------------------------------


class SaveRequest(BaseModel):
    """A variant to save: its name and its text, which carries its values."""

    name: str = Field(..., max_length=64, description="The variant's name, e.g. wider")
    scad: Optional[str] = Field(
        None,
        max_length=DRAFT_LIMIT,
        description="The text to save -- the part's SCAD, or for a part in a submodule "
        "its overlay; omitted, the part's own",
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Values sent on the side: written into the text first",
    )
    params_in: str = Field(
        KEEP_DEFAULT,
        description="Where its values are kept: 'text', in its SCAD; 'part-description' "
        "is a stub, refused, saying what it will do",
    )


@router.get("/parts/{name}/saved", response_model=List[SavedVariant])
def list_saved_variants(
    name: str,
    diff: bool = Query(False, description="With what each changes against the part's SCAD"),
):
    """The part's variants saved in git, newest first: each one's ref, commit,
    who saved it and when, its parameters, whether ``HEAD`` already holds it
    (``merged``) and, with ``diff``, what it changes: a unified diff of its
    SCAD against the part's SCAD as it is on disk. Read from
    ``refs/apothecary/variants/<part>/`` in the repository that tracks its SCAD;
    none for a part outside git."""
    part = _api()._load_part_wrapper(name)
    try:
        return list_saved(part, with_diff=diff)
    except NotInGit:
        return []
    except GitError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None


@router.get("/parts/{name}/saved/{variant}", response_model=SavedVariant)
def get_saved_variant(name: str, variant: str):
    """One saved variant, with its SCAD (``scad``) and parameters: what an editor
    opens. 404 when the part has none by that name."""
    part = _api()._load_part_wrapper(name)
    try:
        check_name(variant)
        return read_saved(part, variant)
    except (ValueError, NoSuchVariant, NotInGit) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except GitError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None


def refuse_a_failure(part: BasePart, text: str, overrides: Dict[str, Any]) -> None:
    """A 422 for a variant that would be a failed render: its text, compiled
    (with ``overrides`` as ``-D``, where a caller has any), makes OpenSCAD say
    an error. ``detail`` carries what it said, by line, as a render's 422
    does. Nothing is refused where no OpenSCAD is installed to ask."""
    renderer = part_renderer(part)
    if not renderer.is_available:
        return
    compiled = compile_draft(part, text, part.scad_overrides(overrides), renderer)
    error = first_error(compiled.messages)
    if error is None:
        return
    where = f" ({error.file}, line {error.line})" if error.line is not None else ""
    raise HTTPException(
        status_code=422,
        detail={
            "message": f"Not saved: with these values OpenSCAD says an error{where}: "
            f"{error.message}. A failed render is not saved as a variant.",
            "messages": jsonable_encoder(compiled.messages),
        },
    )


@router.post("/parts/{name}/saved", response_model=SavedVariant, status_code=201)
def save_part_variant(name: str, body: SaveRequest):
    """Save: the SCAD and its parameters committed to the part's own ref,
    ``refs/apothecary/variants/<part>/<name>``, with git's plumbing alone, so
    the working tree, the index and the checked-out branch are never touched.
    The commit is the person's: its author is the git identity of the checkout,
    and its message has no trailer. Its parent is the variant's last save, else
    ``HEAD``; saving what the variant already holds makes no commit.

    ``params`` are checked as a render's are (422), and so is what they make:
    the SCAD compiled with them as ``-D``; an error OpenSCAD says there is a
    422 whose ``detail`` has its ``messages`` -- a failed render is never
    saved. A bad name is a 422; a
    variant saved meanwhile by another tab, or a part outside git, a 409; a
    part built by Python geometry a 403; git's own refusal (no identity
    configured, for one) a 500 in git's words. Making a variant the part's
    source is a merge the person does: the answer's ``repository`` names where
    the ref lives and ``merge`` what it takes (a fetch first, where the ref is
    in another repository) and that a merge does not apply the variant's
    parameters.

    A part whose SCAD is in a submodule is saved as an overlay in the
    checkout's ref (``kind: "overlay"``): ``<stem>.overlay.scad`` beside the
    submodule, which includes the upstream SCAD and sets the values; the
    submodule is never touched. An edit of the upstream SCAD itself is a 403
    saying so."""
    api = _api()
    part = _editable(name)
    try:
        check_name(body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    text = the_text(api, part, body.scad, body.params)
    renderer = part_renderer(part)
    listing = None
    if part.params_model is None and renderer.is_available:
        if lists_parameters(renderer.openscad_path):
            listing = _listing_for(part, text, renderer)
    checked = check_values(part, text, None, listing)
    if not checked.valid:
        raise HTTPException(
            status_code=422, detail="; ".join(f"{e.field}: {e.message}" for e in checked.errors)
        )
    refuse_a_failure(part, text, {})
    try:
        return save_variant(part, body.name, text, kept_in=body.params_in)
    except UpstreamEdit as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    except (Moved, NotInGit) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except GitError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


# --- managing saved variants ------------------------------------------------------------


def _managed(call):
    """``call()``, git's and the plumbing's refusals as answers: no such variant
    (or outside git) 404, a bad name 422, a name taken or a ref moved 409,
    anything else git said 500 in its words."""
    try:
        return call()
    except (NoSuchVariant, NotInGit) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except (Taken, Moved) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except GitError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


class NameRequest(BaseModel):
    """The name a variant goes by after a rename, or its copy's."""

    to: str = Field(..., max_length=64, description="The new name, e.g. wider-2")


class RestoreRequest(BaseModel):
    """One of a variant's own commits, by its hash (a prefix of seven or more)."""

    commit: str = Field(..., pattern=r"^[0-9a-f]{7,64}$")


class TrashRestoreRequest(BaseModel):
    """Where a deleted variant goes back to: its own name, or ``to``."""

    to: Optional[str] = Field(None, max_length=64)


@router.post("/parts/{name}/saved/{variant}/rename", response_model=SavedVariant)
def rename_saved_variant(name: str, variant: str, body: NameRequest):
    """The variant called ``to``: its ref moved in one transaction, its commits
    as they are. 409 when a variant is called that already (nothing is
    overwritten), 404 when there is no ``variant``, 422 for a bad name."""
    part = _editable(name)
    return _managed(lambda: rename_variant(part, check_name(variant), check_name(body.to)))


@router.post(
    "/parts/{name}/saved/{variant}/duplicate", response_model=SavedVariant, status_code=201
)
def duplicate_saved_variant(name: str, variant: str, body: NameRequest):
    """A copy of the variant called ``to``: a ref of its own on the same commit,
    sharing its history until it is saved again. 409 when ``to`` is taken."""
    part = _editable(name)
    return _managed(lambda: duplicate_variant(part, check_name(variant), check_name(body.to)))


@router.get("/parts/{name}/saved/{variant}/history", response_model=List[VariantCommit])
def saved_variant_history(name: str, variant: str):
    """The variant's own commits, newest first, back to its first save: each one's
    author, date, subject and parameters, and which it is now (``current``)."""
    part = _api()._load_part_wrapper(name)
    return _managed(lambda: variant_history(part, check_name(variant)))


@router.post("/parts/{name}/saved/{variant}/restore", response_model=SavedVariant)
def restore_saved_variant(name: str, variant: str, body: RestoreRequest):
    """The variant as it was at ``commit``, one of its own (404 otherwise): a new
    commit on its ref with that commit's SCAD and parameters, so its history
    keeps what came between. Restoring what it holds makes no commit."""
    part = _editable(name)
    return _managed(lambda: restore_variant(part, check_name(variant), body.commit))


@router.delete("/parts/{name}/saved/{variant}", response_model=SavedVariant)
def delete_saved_variant(name: str, variant: str):
    """The variant moved to the trash, ``refs/apothecary/trash/<part>/<name>``,
    and answered as it is there (``deleted``): restorable, gone only when the
    trash is emptied. 409 while a deleted variant of that name is in the trash
    already: restore it or empty the trash first, as nothing in it is
    overwritten."""
    part = _editable(name)
    return _managed(lambda: delete_variant(part, check_name(variant)))


@router.get("/parts/{name}/trash", response_model=List[SavedVariant])
def list_deleted_variants(name: str):
    """The part's deleted variants, as the variants are listed (``deleted``)."""
    part = _api()._load_part_wrapper(name)
    try:
        return list_trash(part)
    except NotInGit:
        return []
    except GitError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None


@router.post("/parts/{name}/trash/{variant}/restore", response_model=SavedVariant)
def restore_deleted_variant(name: str, variant: str, body: Optional[TrashRestoreRequest] = None):
    """A deleted variant back among the part's variants, under its own name or
    ``to``. 409 when a variant is called that: restore it under another."""
    part = _editable(name)
    to = body.to if body is not None and body.to else None
    return _managed(
        lambda: restore_from_trash(part, check_name(variant), check_name(to) if to else None)
    )


CONFIRM = Query(
    False, description="Emptying the trash deletes for good: it is done only when this is true"
)


def _confirmed(confirm: bool) -> None:
    if not confirm:
        raise HTTPException(
            status_code=422,
            detail="Emptying the trash deletes its variants for good: ask again with confirm=true",
        )


@router.delete("/parts/{name}/trash")
def empty_the_trash(name: str, confirm: bool = CONFIRM):
    """Every deleted variant of the part deleted for good, its refs gone:
    ``{"emptied": [names]}``. Only with ``confirm=true`` (422 without)."""
    part = _editable(name)
    _confirmed(confirm)
    return {"emptied": _managed(lambda: empty_trash(part))}


@router.delete("/parts/{name}/trash/{variant}")
def empty_one_from_the_trash(name: str, variant: str, confirm: bool = CONFIRM):
    """One deleted variant deleted for good: ``{"emptied": [name]}``. Only with
    ``confirm=true``; 404 when it is not in the trash."""
    part = _editable(name)
    _confirmed(confirm)
    return {"emptied": _managed(lambda: empty_trash(part, check_name(variant)))}


# --- comparing two -----------------------------------------------------------------------


class Side(BaseModel):
    """One side of a comparison: what it is, its SCAD and parameters, and the
    bounds its render measured."""

    name: str = Field(description="As asked: a saved variant's name, @part, or @<key>")
    kind: str = Field(description='"saved", "part" or "cached"')
    commit: Optional[str] = None
    scad_path: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    variant: Optional[str] = Field(None, description="Its render's key in the variant cache")
    stl_url: Optional[str] = None
    measured: Optional[Dict[str, Any]] = None
    measured_from: Optional[str] = None
    error: Optional[str] = Field(None, description="Why it has no measured bounds")


class ParamDifference(BaseModel):
    name: str
    a: Any = Field(None, description="Its value on side a; null: not set, the default")
    b: Any = None


class Comparison(BaseModel):
    part: str
    a: Side
    b: Side
    diff: str = Field(description="A unified diff of a's SCAD to b's (empty: the same)")
    params: List[ParamDifference] = Field(default_factory=list)


def _side(part: BasePart, name: str, page: Optional[str], measure: bool):
    """A side as asked for, and its text, values in it: (Side, text)."""
    from ..projects.parts.variants import KEY_PATTERN, measured_box, read_variant

    own = own_text(part)
    if name == "@part":
        side, text = Side(name=name, kind="part"), own
    elif name.startswith("@"):
        key = name[1:]
        record = read_variant(part, key) if KEY_PATTERN.match(key) else None
        if record is None:
            raise HTTPException(status_code=404, detail=f"No variant '{key}' is cached")
        text = read_variant_draft(part, key) or own
        # A render recorded with values on the side (``params``): written into its text.
        text = with_params(part, text, dict(record.get("params") or {}))
        side = Side(
            name=name,
            kind="cached",
            variant=key,
            stl_url=f"/parts/{part.name}/variants/{key}/stl",
            measured=jsonable_encoder(measured_box(record.get("measured"))),
            measured_from=record.get("measured_from"),
        )
        side.params = differences(text, own)
        return side, text
    else:
        saved = _managed(lambda: read_saved(part, check_name(name)))
        side = Side(name=name, kind="saved", commit=saved.commit, scad_path=saved.scad_path)
        text = saved.scad or ""
    side.params = differences(text, own)
    if measure:
        _measure(part, side, None if text == own else text, page)
    return side, text


def _measure(part: BasePart, side: Side, draft: Optional[str], page) -> None:
    api = _api()
    try:
        with runs_for(part.name, page):
            # Only to measure: nothing is written beside the part.
            made = make_variant(part, {}, draft=draft, place=False)
    except ValueError as exc:
        side.error = str(exc)
        return
    if not made.success:
        side.error = made.error_message
        return
    side.variant = made.key or side.variant
    side.stl_url = (
        f"/parts/{part.name}/variants/{made.key}/stl" if made.key else f"/parts/{part.name}/stl"
    )
    side.measured = jsonable_encoder(api.measured_box(made.measured))
    side.measured_from = made.measured_from


@router.get("/parts/{name}/compare", response_model=Comparison)
def compare_variants(
    name: str,
    a: str = Query(..., max_length=80, description="A saved variant's name, @part, or @<key>"),
    b: str = Query(..., max_length=80, description="The same, for the other side"),
    measure: bool = Query(True, description="Render each where it is not cached, to measure it"),
    page: Optional[str] = PAGE,
):
    """Two variants side by side: a unified diff of a's text to b's (for a part
    in a submodule, their overlays; a .variant.json variant has its values
    written in), every value whose text differs (by the names the SCAD uses;
    null: that side sets nothing otherwise than the part), and each one's
    measured bounds --
    from the variant cache, rendered (through the queue) where it is not there,
    with its ``stl_url`` to draw. A side that does not render says why
    (``error``). 404 for a side that is no variant."""
    part = _api()._load_part_wrapper(name)
    side_a, text_a = _side(part, a, page, measure)
    side_b, text_b = _side(part, b, page, measure)
    import difflib

    diff = "".join(
        difflib.unified_diff(
            text_a.splitlines(keepends=True),
            text_b.splitlines(keepends=True),
            fromfile=f"a/{a}",
            tofile=f"b/{b}",
        )
    )
    names = sorted(set(side_a.params) | set(side_b.params))
    differ = [
        ParamDifference(name=n, a=side_a.params.get(n), b=side_b.params.get(n))
        for n in names
        if side_a.params.get(n) != side_b.params.get(n)
    ]
    return Comparison(part=part.name, a=side_a, b=side_b, diff=diff, params=differ)


__all__ = ["router"]
