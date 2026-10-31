# Image models through qmcp: a plan

*Nothing in this page is built.*

## What this plans

Apothecary reads pictures with pixel arithmetic: the plain finder's shapes
(`apothecary/vision/plain.py`) and the rig reader's knobs, faders, switches and
plugs (`apothecary/rig/look.py`). Both are measured, both need nothing but
Pillow, and neither names a thing, counts things of a kind, or says what
something is made of.

This plan adds a layer through which image models answer those questions: how
many of a kind a picture shows, how big, what shape, what material, what colour,
and what it is. The models are engines that qmcp, the QM family's tool server,
serves as tools on this machine. Apothecary asks qmcp when a person has
configured it and it answers; otherwise apothecary does exactly what it does
without the layer. What comes back is a list of **observations**, each about one
subject and one property, with a value, a unit, a confidence, an origin and a
time. Apothecary weighs them as evidence beside its own readers' and never above
a person's word. A layer that correlates observations, pictures and a person's
data into a view of a working space is planned beside this one, and takes them
in this shape.

**This extends [the finders plan](photo-finders-local-models-2026-09-21.md)**
and keeps every rule of it: a model is an engine, a subprocess or a server on
loopback, never imported into `apothecary/`; OpenCV is not imported either;
weights are files the person brings; the paid-service hook stays shut. This is
that plan's loopback reach, made once, through qmcp, rather than one client per
model server, and it replaces that plan's phase 2, a namer over loopback. Its
phases 0, 1 and 3 stand: the seam hardened, markers, masks and depth.

What moves is where the standard protocol sits. In the finders plan apothecary
speaks the OpenAI-compatible chat API, or the Open Inference Protocol, to an
engine itself. Here qmcp does. Apothecary speaks the family contract below to
qmcp, as it speaks `POST /family/cue` to carlos, and qmcp speaks the standard
protocols to the engines. Model output then reaches apothecary through one door,
the one charter `shrink-the-black-box` names: what cannot be moved into a
command goes through qmcp, which records what passes.

## The seam: qmcp's vision tools

qmcp lists tools at `GET /v1/tools` and runs one at `POST /v1/tools/{name}` with
`{"input": {...}, "correlation_id": ...}`. It answers `{"result", "error",
"invocation_id"}` and writes an invocation row (qmcp's `docs/tools.md`). The
layer is two tools there, in a contract named `qm.vision`, version 1.

### `vision.models`: what can be asked

No input. The result lists every model qmcp can reach, each with:

- `name`, `version`, and `weights_sha256`, the digest of its weights file;
- `licence`, the weights' SPDX expression, and `engine`, the server that runs
  it, with its version;
- `answers`: the properties it can be asked, and, for a property answered in
  words, the vocabulary its words come from;
- `warm`: whether it is loaded, so a first call's seconds are not taken for
  every call's.

An empty list is an answer: qmcp is up and has no model.

### `vision.observe`: a picture, its regions, and what is asked

The request:

```json
{
  "contract": "qm.vision",
  "version": 1,
  "picture": {"sha256": "<digest of the whole picture's bytes>", "taken": "2026-10-30T14:02:11+00:00"},
  "regions": [
    {"id": "uno/barrel", "box": [0.41, 0.22, 0.47, 0.31],
     "image": {"bytes": "<base64>", "media_type": "image/png"}}
  ],
  "asked": [
    {"property": "quantity", "of": "plug"},
    {"property": "colour"},
    {"property": "material", "among": ["plastic", "metal", "rubber"]}
  ],
  "deadline_ms": 4000
}
```

- **The picture** is named by its digest and arrives in one of two forms.
  *Bytes:* each region's own pixels, cropped and turned upright by the asker, so
  qmcp needs no image library and a model sees exactly the region. *A path:*
  `"picture": {"path": ..., "sha256": ...}` and no bytes, for a client that
  cannot crop; qmcp opens the file, applies its EXIF orientation and crops.
  Apothecary sends bytes. It already holds every picture through Pillow, upright
  (`ImageOps.exif_transpose`, as `rig/look.Grey.open` applies it).
- **A region** is a box in fractions of the picture as it is seen, upright:
  left, top, right, bottom, from 0 at the top left to 1 at the bottom right, the
  convention of `FoundShape`. No box is the whole picture. Its `id` is the
  asker's, and comes back on every observation about it.
- **What is asked** is drawn from a closed set: `label`, `quantity` (with `of`,
  the kind counted), `size`, `shape`, `material`, `colour`. A property answered
  in words may name `among`, the only words it may answer with; without it, the
  model's vocabulary from `vision.models` applies.
- **No scale crosses the seam.** A size comes back in fractions of the picture.
  Turning it into millimetres is apothecary's, with a reference a person stated
  (*Which measurements come first*).
- **`deadline_ms`** is how long the asker waits. qmcp passes it to the engine as
  a timeout, and a model past it is answered with a `why`.

The answer, as the tool's `result`:

```json
{
  "contract": "qm.vision",
  "version": 1,
  "picture": "<the digest asked about>",
  "observations": [
    {"region": "uno/barrel", "property": "quantity", "of": "plug",
     "value": 1, "unit": "count", "confidence": 0.91,
     "model": {"name": "...", "version": "...", "weights_sha256": "...", "engine": "..."},
     "why": null},
    {"region": "uno/barrel", "property": "material",
     "value": null, "unit": null, "confidence": null, "model": null,
     "why": "no model that answers material is loaded"}
  ],
  "elapsed_ms": 812
}
```

- **Every region has an observation for every property asked**, in the order
  asked. One that could not be answered has `value: null` and a `why`, as the
  rig reader's `Seen` and `Plug` do. An answer missing one is malformed.
- **`value` and `unit` go together.** A count is in `count`. A size is in
  `picture-width`, a fraction of the picture's width, as `FoundShape`'s sides
  are. A colour is a word whose `unit` names its vocabulary, with a second
  observation in `sRGB`, a hex value, when the engine gives one. A shape, a
  material and a label are words whose `unit` names their vocabulary.
- **`confidence`** is what the model reports of itself, from 0 to 1, or null
  when it reports nothing. It is a report, not a measurement; what apothecary
  makes of it is in the next section.
- **`model`** names what answered, and is null only when no model was reached.
- **`why`** says why a value is null, as one of a fixed set: no model answers the
  property; the region is too small for the model, with its size in pixels; the
  model declined; the deadline passed; the picture could not be read; a size was
  asked of a model that gives no outline.

Apothecary refuses an answer whole when its `picture` is not the digest asked
about, its version is not one it reads, it names a region not asked about, or it
does not validate against the contract's schema. Nothing from a refused answer
is kept.

## How apothecary consumes it

### The client

`apothecary/finders/qmcp.py`, in the package the finders plan keeps for model
finders, never under `apothecary/vision/`.

- **Configured, never found.** qmcp's address is `--qmcp URL` or
  `APOTHECARY_QMCP`, as carlos's is `--carlos` or `APOTHECARY_CARLOS`
  (`apothecary/wiring/carlos.py`). With neither set, nothing is asked and
  nothing is probed: apothecary does not look for qmcp at qmcp's default port.
- **Loopback or nothing.** The address is checked when the client is made, with
  `stays_local.is_loopback`, and any other is refused there, naming the
  personal-data record, as `--carlos` refuses one. The guard refuses it again
  at connect.
- **The standard library and Pydantic.** `urllib.request`, as
  `wiring/carlos.py` uses, and a Pydantic model of the contract. No new
  dependency.
- **`ask` and `parse`**, the finders plan's split. `ask(request) -> bytes` is the
  transport, injected, so the tests drive the client against recorded replies
  with no socket, as the monitoring record's §10 has a collector tested.
  `parse(reply, request) -> List[Observation]` is the tested half, and refuses a
  malformed reply whole.
- **A deadline of its own.** The client's socket timeout is the request's
  `deadline_ms` and a margin. qmcp's own bound on a model call is measured and
  not enforced (`qmcp/governed.py`, `Bound.seconds`), so the asker enforces what
  it waits for.
- **Answers are cached** in `apothecary/vision/cache.py`'s cache, whose key is
  already the picture's hash, the backend, the model's digest and the prompt's
  version; here the prompt is the region and what was asked. In memory, until
  what "this machine" means is decided (`todo.md`).

### An observation

`apothecary/observation.py` holds `Observation`, the format
`apothecary.observation` version 1. It is what this layer makes and what the
correlating layer takes.

| Field | Holds |
|---|---|
| `subject` | what it is about, as an address: a rig's socket (`rig/<module>/<jack>`), a site's piece, or, when apothecary cannot name the thing, the region itself (`picture/<sha256>/<box>`) |
| `property` | `label`, `quantity`, `size`, `shape`, `material` or `colour`; `of`, beside a quantity, says what was counted |
| `value`, `unit` | as the seam has them; a size is in `mm` only when apothecary turned it into millimetres with a stated reference |
| `confidence` | a number apothecary trusts, or null: the model's report, once a check has shown it drops when the model is wrong (*How each is measured*), and null until then |
| `reported` | the model's own confidence, as it came |
| `origin` | where it came from, in one string: `qmcp/vision.observe/<model>@<version>/<weights digest>`, or `plain/<reader>` for apothecary's own |
| `time` | when the picture was taken, which is when the fact held: a PNG's `taken` text, a JPEG's EXIF time, else its file's time, as `rig/concert.taken` reads it |
| `made` | when the observation was made |
| `seen` | the picture's digest and the region's box, always, whatever `subject` names |
| `why` | why `value` is null |

Apothecary's own readers give observations in the same shape (`plain/colour`,
`plain/rig`), so a model's and the plain reader's stand side by side and the
correlating layer reads one format. The format is apothecary's to start with;
when a second family app gives observations, it moves to a family contract.

### As a finder

`qmcp` is registered in `vision/finder.py`'s lazy registry beside `stated` and
`plain`. It runs the plain finder, then asks qmcp, for each shape found, its
`label` and `shape`, and, for the whole picture, the `quantity` of each kind
found. Its `Picture` is the plain finder's, with:

- `FoundShape.label` filled from a label observation apothecary trusts, so
  `ScaleReference.known_shape` finds it: the finders plan's cheapest real win;
- `FoundShape.origin` naming both, `plain+qmcp/<model>@<version>`;
- each shape's `confidence` the plain finder's, since `ENOUGH_CONFIDENCE` is
  measured against it;
- no shape that the model found and the plain finder did not, until `photo
  check` has measured the model finding shapes. Until then a model's own
  detection is an observation, not a shape.

Chosen with qmcp absent, it says so in `Picture.finder` (`plain; qmcp not
configured`) and answers as `plain` does. The default finder stays `plain`.

### Beside the rig reader

The rig reader's readings stay the readings. For each face a setup pins,
apothecary crops each socket, and the face itself, through the face's mapping;
asks for the `quantity` of plugs, a socket's `colour` and the face's `label`;
and sets each observation beside what the reader said.

- **They agree:** nothing changes, and the record keeps both.
- **They disagree:** the socket's state in carlos is a warning that says both
  (`the reader saw a plug; <model> saw none`), and the reader's value stands.
  Nothing is merged on a maybe (`gathering/resolve.py`).
- **The reader could not read it** (too small, no pointer to see): a trusted
  observation fills it, held in carlos as the model's (`seen by <model>`), at
  warn. An untrusted one is said in the module's state and fills nothing.

In a concert, a frame's reading is held as soon as the reader has it. An answer
that comes later joins the frame's line in `readings.jsonl`; one that comes
after the next frame is held is recorded and not held.

### A person's word, and switching a model off

- **A person's statement is never overruled.** A stated shape (`origin:
  stated`), an answer in `--answers` (`BY_A_PERSON`), a stated scale, a setup's
  pinned faces, a rig's leads and a site as drawn are a person's. An observation
  about the same subject and property that differs is kept, marked `overruled:
  person`, and used for nothing.
- **The order of evidence:** a person's statement; apothecary's own reader; a
  trusted model observation; an untrusted one, which is shown and never used.
  Two at one level that disagree are *cannot tell*.
- **Every observation carries its origin**, so it is weighed per origin and
  property (*How each is measured*) and switched off per origin. The switches
  are a list in the state folder, shown as a window in the viewer, with
  `apothecary vision off <origin>` as its command; apothecary reads it before it
  asks. Unsetting `APOTHECARY_QMCP` switches them all off. Kept observations
  from an origin switched off leave every view and stay in the record, marked.

## What "always optional" means

Each row is what apothecary does, and each is its behaviour without the layer:

| When | Apothecary |
|---|---|
| **qmcp absent:** no address configured | asks nothing and says nothing |
| **qmcp not answering:** configured, and the connection refused or `/health` failing | says so once (`qmcp at URL is not answering; reading without it`), reads as it does without the layer, and tries again after a while, never once a frame |
| **model absent:** `vision.observe` not registered, or no model answers a property | reads as it does without the layer; that property's observation carries the `why` |
| **model slow:** the deadline passes | reads as it does without the layer and does not wait; the observation says it came too late, and a late answer is recorded and not held |
| **call refused:** an error result, an HTTP error, or a reply that does not validate or names another picture | reads as it does without the layer; nothing from the reply is kept, and the record says why |

The test that holds it: `photo check`'s and `rig check`'s tables, `rig read`'s
output and a followed concert's record, with qmcp unset, pointed at a closed
port, answering 404, answering past the deadline from a stub that sleeps, and
answering malformed, are each identical to the same run with the layer not
built. A stub on loopback, bound to port 0, speaks the contract in the tests, so
no qmcp is needed. Its mutation: let a refused connection raise, and watch the
test go red.

## Which measurements come first

| Order | Property | Needs | Why there |
|---|---|---|---|
| 1 | colour | nothing for a colour in the picture; a colour reference for one in the world | Apothecary reads a region's colour itself, its median through Pillow, so the first model is measured against a plain baseline from its first run, and drawn pictures have exact answers. On the rig: a plug's colour, a lead's |
| 2 | quantity | nothing | Counts are exact on drawn pictures and on a known device, since carlos's entry says how many knobs and sockets a face has. On the rig: plugs in a row of sockets, beside the reader's own |
| 3 | label | nothing | Fills `FoundShape.label`, so `known_shape` fills itself, and names a device in a picture ([the bench plan](qm-family-carlos-2026-10-29.md)'s slice 2) |
| 4 | shape | nothing | Measured by `photo check` itself, against the plain finder's kinds |
| 5 | material | nothing | No plain baseline and no drawn truth: measured on real photographs alone |
| 6 | size | **a scale** | A model gives a better outline, in fractions of the picture. Millimetres need a reference a person stated (`ScaleReference`) or a marker of known size (the finders plan's phase 1); without one, a size is a fraction of the picture and says so |

**Size needs a scale, and colour a reference.** A region's colour is the
camera's: under a stage's warm light a white plug reads amber. A named colour is
the picture's, its subject the region, unless a patch of known colour is in
frame and a person has said so, as a scale is stated.

## How each is measured before anything trusts it

`apothecary vision check`, in the style of `apothecary photo check` and
`apothecary rig check`: pictures whose every answer is known, a row for each
condition, a column for each score, and the model named, with its seconds per
picture on this machine beside it.

- **Drawn pictures**, which need nothing but this machine: `vision/bench.py`'s
  shapes drawn in known colours and known numbers, under the conditions `photo
  check` draws (turned, speckled, blurred, faint, small, crowded), with a tinted
  light and JPEG compression added; and `rig/simulated.py`'s faces, whose every
  plug is known. They prove the plumbing, not the eyes, as `rig check` says of
  its own.
- **Real photographs with written answers**, recorded in `docs/validation/` as
  the [rig plan](carlos-concert-rig-2026-10-29.md)'s slice 4 records its first:
  the Uno's power and USB edge, each lead in and out; bench boards, with their
  names; things of known material. Material and label are measured here alone.

The scores:

| Property | Scored as |
|---|---|
| colour | named right; how far off its sRGB value is; declined; the plain reader's row beside it |
| quantity | exactly right; off by one; off by more; declined |
| label | named right; named wrong; declined, which is allowed and counted apart |
| shape | `photo check`'s own columns: found, named, made up, honest |
| material | named right; named wrong; declined |
| size | how far off, as a share of the true size, with the scale stated |

and, for every property, **made up**, an answer about a region holding nothing
of the kind, and **honest**, how much lower the reported confidence is when the
answer is wrong.

**When a model's confidence is trusted.** For one model, at one weights digest,
for one property: made up is zero on every row, the honest gap is positive on
every row, and on the real-photograph row it beats the plain reader where there
is one. The check writes its result to the state folder, keyed by the digest and
the property, with the confidence below which its answers were wrong, the
threshold that `ENOUGH_CONFIDENCE` is for the plain finder. Only then is an
observation's `confidence` its report, and only above that threshold is it used.
New weights are a new digest, measured again.

## What lives where

| | qmcp | apothecary |
|---|---|---|
| the model | the engines it reaches, the weights the person put there, their digests and licences, `vision.models` | nothing: no engine, no weights, no image library but Pillow, no OpenCV, no numpy |
| the call | `vision.observe`: a region to an engine over a standard protocol, the engine's reply into the contract, the deadline passed on, the invocation row | the client: the address, loopback, its own deadline, the schema, `ask` and `parse` |
| the picture | the bytes it is given, for one call; the path form, for other clients | the picture, upright, the regions and their crops, what to ask |
| meaning | none: a count is a count and a word a word | scale, colour reference, subjects, the order of evidence, a person's word |
| trust | reports the model's confidence | measures it (`vision check`), switches origins off, keeps the record |

qmcp's tool rules hold: the vision tools are stateless, call no other tool and
decide nothing (qmcp's `docs/tools.md`). Its human queue is not part of this: an
observation is evidence, and nothing here asks a person about each picture.

### qmcp's own slice

None of this is in qmcp at `ed01fc0`. It is qmcp's work, a pull request each, in
its own repository, started when the owner says so.

1. **A slow tool does not stall the server.** `invoke_tool` calls a tool's
   handler inline in an `async` route (`qmcp/server.py:230`), so a model call
   holds every other route for as long as it runs. Handlers run off the event
   loop.
2. **A picture is recorded as its digest.** An invocation row keeps a tool's
   input verbatim (`input_params`, `qmcp/server.py:217`, a JSON column in
   `qmcp/db/models.py`). A tool declares the fields kept as a digest and a
   length instead, and the vision tools declare their bytes and paths.
   Apothecary sends no bytes before this lands.
3. **The vision tools, on loopback only**, as the thread archive and voice are
   registered only when qmcp is bound to loopback (`qmcp/server.py:141`):
   `vision.models` and `vision.observe`, with a `recorded` engine that replays
   JSON, so the contract is tested with no model.
4. **Engine adapters**, as qmcp's voice integration has `vox` state the contract
   and name no engine while an adapter names one: an OpenAI-compatible adapter
   (`llama-server`; Ollama, with its cloud models refused; vLLM), then the Open
   Inference Protocol, for detectors and segmenters. An engine qmcp starts runs
   with every telemetry and offline switch its libraries have, as the finders
   plan has a managed engine run.
5. **Vision models in `qmcp localmodel`**: `check`, then `plan` with a pinned
   weights digest, the commands printed for a person to run, as it does for its
   judgement worker.
6. **qmcp says which qmcp it is**: the identity endpoint the monitoring record's
   revision triggers name, so an origin names the instance as well as the model.
   Until then apothecary's record names a qmcp by its configured address, which
   two clones on one port would share (that record's *Context*).

## Governance

### What it rests on

- **Build the seam, buy the engines**
  (`governance/qm/records/DRAFT-build-the-seam-buy-the-engines.md`): a model is
  an engine, selected, and the seam is apothecary's client and qmcp's tools.
  Selecting an engine is where the weight goes.
- **Seams on standard protocols**: the engines touch the system at qmcp, through
  the OpenAI-compatible API or the Open Inference Protocol, each served by
  several independent servers. Apothecary to qmcp is a family seam, an internal
  choice that record does not govern (as the monitoring record reads it), held
  by a versioned schema as carlos's is.
- **Open-licence exclusion**: model weights and their toolchains are in its
  scope, restricted "open weights" are excluded, and there are no waivers. A
  model's weights licence is read from what its publisher ships at the digest
  chosen, since a family of models can license its code and its weights, or its
  sizes, differently. A model whose weights do not clear is not offered.
- **House stack**, and the adoption scope
  (`governance/qm/adr/DRAFT-constitution-adoption-scope.md`): apothecary gains
  no dependency. qmcp, each engine and each model's weights are rows in its
  audit when the layer is configured, conflict rows where they do not clear.
- **Shrink the black box**: the model is never the check. A check apothecary runs
  decides whether its confidence is trusted, a person decides whether it is
  used, and its output arrives through one seam that records each call.
- **A check is evidence only after it has failed**: the degrade test's mutation,
  and each check's *made up* column.
- **Nothing unattended spends money**: a local model spends nothing. A paid
  vision service is the finders plan's shut hook; through qmcp it would pass
  `qmcp/spend.py`'s gate, and the secured-user-accounts record first.
- **The monitoring seam, and instance identity**: what qmcp can and cannot say
  about which qmcp it is (qmcp's slice 6).
- **Personal data stays on the device** (apothecary's draft, in qm#121): a
  picture goes to qmcp on loopback, which the draft allows. The draft is
  rewritten in place, as the finders plan asks for each engine, to name qmcp
  and what it is given (a region's pixels and a digest), each engine it starts
  and what that is given, and qmcp's invocation store as a place an observation
  is kept on this machine.

### Records it needs

Each drafted with the slice that needs it; a person ratifies.

- **The observation seam** (apothecary): models answer through qmcp alone;
  optional in each way the table above lists; a person's word first; a model
  never sets a scale; a confidence trusted only after a check. One decision
  each with the finders plan's finder-seam record.
- **A selection record for each model**: its name, version, weights digest,
  licence and engine, the check's table, and its seconds on this machine.
- **qmcp's vision tools** (in qmcp's records): served on loopback only, a
  picture recorded as its digest, the contract `qm.vision` version 1.

### Open for the owner

1. **One door, or two.** This plan has model output reach apothecary through
   qmcp alone, so the finders plan's direct client, `LoopbackModel`, is not
   built. The alternative keeps both.
2. **Which transport.** qmcp's `/v1/tools` is qmcp's own HTTP shape. The Model
   Context Protocol's own transport reaches the same tools only through
   `qmcp_mcp.py`, a stdio server whose `invoke_server_tool` forwards to
   `/v1/tools`; qmcp's server does not speak MCP over HTTP. The client's
   transport is injected either way, so starting on `/v1/tools` and moving later
   is a swap.
3. **Bytes, or a path.** Bytes keep image handling in apothecary and wait on
   qmcp's slice 2; a path needs an image library in qmcp, and leaves a
   picture's path in qmcp's rows.
4. **How long qmcp keeps what it was asked**, and whether its store counts as on
   the device: the "this machine" question in `todo.md`, for a second program.
5. **When to ask**: about every picture and every frame, or only when a person
   asks to look closer. Asking about every frame adds a model's seconds, on this
   machine, to each one.
6. **The vocabularies**: which colour names and materials, and which kinds are
   counted. The correlating layer reads them, so they are fixed once for both.
7. **Where the observation format lives**: apothecary's to start with, or a
   family contract in qm from the first slice.
8. **The model download.** Weights are files the person brings, and `qmcp
   localmodel` prints the commands for a person to run, so neither program
   fetches a model. Whether that settles `todo.md`'s one-time-download question
   for this layer is the owner's to say.

## Slices

Smallest first; each lands alone.

0. **The format and the switch, with no model** (apothecary). `Observation`;
   `--qmcp` and `APOTHECARY_QMCP`, loopback when the client is made; the client
   with its transport injected, and `parse` tested on recorded replies; the
   degrade test against the stub, a case for every row of the table; and a
   walkthrough page that reads an observation from a recorded reply and shows
   each row's degrading.
1. **The plain reader's answers as observations** (apothecary). A region's
   colour from its pixels (`plain/colour`), and the rig reader's plugs
   (`plain/rig`), so the baseline is in the format before any model is.
2. **qmcp's slices 1 to 3**, in qmcp: the server unstalled, digests in its rows,
   the tools with the recorded engine. Apothecary's client reaches a real qmcp,
   in a cross-app test that runs qmcp from a checkout a variable names, as
   `tests/e2e/test_carlos_concert.py` runs carlos. The personal-data rewrite
   lands with it, the first time a picture leaves apothecary's process.
3. **Colour from a model, measured.** qmcp's slices 4 and 5 for one
   vision-language model over the OpenAI-compatible API; `apothecary vision
   check --property colour`, with the plain reader's row beside it; the first
   selection record.
4. **Quantity**: drawn pictures, drawn rig faces, then the Uno's photographs
   from the rig plan's slice 4.
5. **Label**: the `qmcp` finder fills `FoundShape.label`; a device named in a
   picture, measured on bench photographs with their names written down.
6. **Shape**: `photo check --finder qmcp`.
7. **Material**, on real photographs alone.
8. **Size**, with a stated scale, then with the finders plan's marker finder.
9. **The correlating layer takes them**, in its own plan.
