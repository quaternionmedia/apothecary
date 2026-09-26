# The shape finder, with a model behind it: a plan

*Written 2026-09-21 on `consolidate/2026-09-19`, from a fan-out of four
readers (the seam, the open local frameworks, plugin shapes, governance)
and a critic who checked their claims on this machine. Every line reference
was re-read against the tree; every web fact is dated; where something was
measured, the measurement is here. Nothing in this page is built.*

## What this plans

The photo path finds shapes in a picture with a finder that is 284 lines
of pixel arithmetic (`apothecary/vision/plain.py`). It runs with the network
off, it is measured (`apothecary photo check`), and it is honest about what
it cannot do: it does not name things, it does not see depth, and it does
not know how big anything is. The ask: extend the finder with an *optional*
local model, plan it so more finders can be added the same way, plug into
the open local frameworks rather than write an engine, and leave hooks for
proprietary or paid services.

The plan lives under two rules that decide most of it before a model is
chosen:

- **Personal data stays on the device, by construction** (the draft record
  in `governance/qm/adr/`, enforced by `apothecary/stays_local.py`). The
  process cannot connect or resolve past loopback; there is one tool fetch
  with one caller, held to one by a test; a paid service can be reached
  only under that record's named exception, *secured user accounts*, which
  is a future record, not a setting. A photograph is exactly the personal
  data the record names first.
- **The house stack** (`governance/qm/records/DRAFT-house-stack.md`): §2,
  any addition to it is an org-level record; §3, a component imported into
  seam code is house stack and needs that record, while one reached only
  across a protocol seam is an engine selection. **Build the seam, buy the
  engines** (`DRAFT-build-the-seam-buy-the-engines.md`): §3's ordering rule
  asks which existing engine should own a capability before QM writes one;
  §5 lets a QM-authored engine exist only as its own published project. And
  **seams on standard protocols** (`DRAFT-seams-on-standard-protocols.md`):
  a third party is reached over a protocol with independent implementations,
  or a project-level exception record says why not and how to leave. The
  detector-selection page already says the plain finder has become an
  engine (`docs/plans/features/detector-selection.md`, the size smell) --
  which is the argument *for* a model behind the seam, not against it.

So: a model is an engine. It is reached over a protocol on loopback, or
run as a subprocess the seam starts and configures, and never imported
into `apothecary/` -- not a model library, and not OpenCV either. Its
weights are files the person brings. A hook to a paid service is the same
seam with an address the guard refuses.

## Where the seam stands (read 2026-09-21)

- `apothecary/vision/finder.py:26-35`: `ShapeFinder(Protocol)` with two
  methods, `name()` and `look(image: Path) -> Picture`. No configuration,
  no capabilities, no lifecycle, no "is available".
- `finder.py:42-62`: a lazy registry, `register(name, build)` / `names()` /
  `get(name)`, with an `isinstance` check against the protocol; two
  built-ins, `stated` and `plain`, registered at import (`:65-73`). No
  entry-point discovery: a third finder registers by being imported.
- `apothecary/vision/models.py:31-67`: `FoundShape` carries `kind`, a box in
  picture fractions, `points`, `confidence`, `origin`, `label`,
  `turned_degrees`, `long_side`/`short_side`. Two of those nobody consumes
  today: `points` is set only by `stated` and read nowhere; `label` is read
  only by `ScaleReference.known_shape` and the CLI's `--known-shape`.
- Scale is a person's statement or nothing (`ScaleReference`, `models.py:130`):
  millimetres across the picture, or one labelled shape of known width. No
  default, nothing inferred. `compose.build` marks pieces `unsized` without it.
- The finder is chosen by name, defaulting to `"plain"`, in the API
  (`LookAtPicture.finder`, `GatherRequest.finder`) and every `apothecary
  photo` command (`--finder`); the browser panel never sends one
  (`apothecary/static/widgets/camera.js`), so it is wired to `plain`.
- `Picture.finder` travels into every piece's comment and provenance, the
  album, `GET /photos/{name}`, the viewer's provenance panel, and the
  walkthrough's text; `whole_gathering` labels a mixed gathering with the
  first picture's finder (`gathering/combine.py`).
- Gathering *trusts* confidence: `ENOUGH_CONFIDENCE = 0.45`
  (`gathering/resolve.py`), `Album.unsure(below=0.6)`. A model's score is
  not a confidence until `photo check` shows it drops when the model is wrong.
- The fence that keeps engines out of `vision/`
  (`tests/test_working_together.py`) is an exact-name set over a
  non-recursive glob: `import onnxruntime`, `cv2`, `numpy`, `http`, `ollama`
  in `vision/*.py`, and anything under `vision/engines/`, pass it. It has to
  be tightened before it is relied on.

## What a model can add, and where it lands

| The model gives | Where it lands today | What it needs |
|---|---|---|
| **Labels** ("ruler", "credit card", "an M3 bolt") | `FoundShape.label` → `ScaleReference.known_shape` → millimetres, with no hand-written JSON; and a `default_bounds` lookup in the parts registry for a part in frame (`features/scale-references.md`) | `label` on `Provenance` so the viewer shows it; nothing else. **The cheapest real win.** |
| **Oriented boxes** | `long_side`/`short_side`/`turned_degrees` → `compose.build` already prefers measured sides and turns the piece | An axis-aligned-only detector leaves them at 0, or it sizes pieces wrongly |
| **Masks / polygons** | `FoundShape.points` → run `vision/geometry.py`'s outline and smallest-box on them → kind, fullness, sides | A consumer of `points` (none exists); a polygon *word* is `features/word-parameters.md` and stays unbuilt |
| **Depth** (relative or metric) | Nowhere: thickness is a guess (`compose.py`, `THICKNESS_GUESS`), no z-order | New fields (`depth_relative`, `thickness_hint`) with an origin; metric depth is metric only with a focal length -- a `CameraReference(focal_px)` from EXIF beside `ScaleReference`, never a default |
| **A scale** | Refused by design: a finder never sets millimetres | A model returns *labelled candidate references*; a person names one |

Confidence: a model's score maps onto `confidence` only after `apothecary
photo check --finder <name>` shows a positive *honest* gap (the number
drops on the ones it gets wrong, `vision/bench.py`). Until then the score
rides in `origin` and the confidence is the plain finder's rule.

## The plugin shape

Keep what is there: `ShapeFinder` and the lazy registry are the house
pattern (the G-code seam's `Transport` + `ENGINES` + an env pin; the
toolchain seam's argv builders over a bought engine). Add three things.

1. **Discovery by entry point.** `importlib.metadata.entry_points(group="apothecary.finders")`
   (verified on the venv's 3.12.3: the group exists as a mechanism, empty
   today). A finder package that installs itself into apothecary's own
   environment is the person's act (`uv add`, or `uv tool install apothecary
   --with <finder>` for a tool install; a plain `uv tool install <finder>`
   lands in an environment apothecary never sees), like `uv sync`; it runs
   under the guard because the guard is under the process. Loaded lazily by `get()`, never at import. Not
   pluggy (a runtime dependency in seam code for two finders; revisit past
   three external packages), not a plugins folder (running files from a
   folder is code the person put in the process).
2. **A `Backend` descriptor**, pydantic, beside every registered finder:
   - *needs*: a weights file path, its SHA-256, its SPDX licence, a device,
     a memory figure;
   - *gives*: labels, boxes, masks, depth, text -- so a pipeline composes
     what it has;
   - *reach*: `engine` (a subprocess the seam starts and configures) |
     `loopback` (a server on this machine) | `account` (the named
     exception). There is no `in-process` reach: a model library, or
     OpenCV, imported into `apothecary/` is a C extension the guard cannot
     see and an addition to the house stack that needs an org-level record.
     A test in the shape of `test_only_the_installer_may_fetch_a_tool`
     enumerates every registered backend's reach and refuses `account`
     while no record allows it.
3. **Composition behind one `look()`.** Optional stage protocols --
   `Segmenter`, `Labeller`, `Ranger` (depth) -- that a composite finder
   chains; `compose`, gathering and the shelf see one `Picture`. Every
   shape's `origin` names the backend and its model digest, so a person can
   tell which model said what. Model output -- what a model saw of the
   person's room -- is cached under an account-only folder the program
   makes (`captures/`-style, 0700: the picture root itself carries whatever
   mode the person's folder has), keyed by picture hash, backend, model
   digest and prompt version; the personal-data record's §6 list of where
   things are kept gains that folder.

Testing: a `recorded` finder that replays JSON a person recorded against a
local engine on `bench.py`'s synthetic pictures (no personal data in
fixtures). Every model finder is split into `ask(bytes) -> reply` and
`parse(reply, w, h) -> Picture`, and `parse` is the unit-tested half.

Where it lives: a new package, `apothecary/finders/` -- never under
`apothecary/vision/`, which `HANDOFF.md` fences off -- and the fence itself
is tightened in the same commit (recursive glob, prefix match, `http`,
`ollama`, `onnxruntime`, `cv2`, `numpy` on the list).

## Reach: what is lawful, and what each shape costs

**In-process is a C extension outside the guard.** The record's risk
register names it. It is not hypothetical:

- ONNX Runtime 1.30.0 (PyPI, 2026-09-10): telemetry is **on by default in
  the official Linux builds** (`docs/Privacy.md`, fetched 2026-09-21).
  Measured here: five `InferenceSession`s on a one-node model, default
  environment, `strace -f -e trace=network` -- a DNS question for
  `mobile.events.data.microsoft.com` and three `connect()` calls to
  13.69.116.105:443 from a native thread, plus a device id written under
  `~/.cache/Microsoft/`. With `ORT_DISABLE_TELEMETRY=1`: zero. The Python
  guard saw none of it.
- `huggingface_hub` 1.32 pulls `hf-xet`, a Rust transfer client. Under the
  guard a `from_pretrained("org/model")` does not fetch -- the metadata
  request goes through Python sockets, is refused, retried five times over
  some twenty seconds, and ends in an error that blames the network -- but
  the same call in a runner *outside* the guard fetches through a client
  the guard never sees. Ultralytics sends analytics by default; under the
  guard that fails silently (`LeftTheMachine` is an `OSError` it catches).
- `torch` 2.14.0 on Linux pins `nvidia-*-cu13` packages: one of them
  (`nvidia-cusparselt-cu13`) declares *NVIDIA Proprietary Software*, which
  the open-license record excludes outright (§1, no waivers; its own
  Context names closed GPU runtimes), and three carry no declaration at
  all, which §4 reads as a failure to investigate. torch's own metadata is
  a compound licence expression that the gate as it stands cannot read
  (below), whichever index it comes from.

So an in-process model library is never imported by `apothecary/`. A model
is a **managed engine**: a subprocess the seam starts, with an argv it
builds, an environment from `subprocess_env()` that *also* sets
`ORT_DISABLE_TELEMETRY=1` (and, since that variable is for non-Windows
builds, the runner calls `onnxruntime.disable_telemetry_events()` before
its first session), `HF_HUB_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`,
`HF_HUB_DISABLE_XET=1`, `DO_NOT_TRACK=1`, and a contract over stdin/stdout -- exactly `ARDUINO_CLI_CONFIG` and the
scrubbed environment, applied to a model runner -- with an `strace -e
trace=network` run recorded in the record as the personal-data record did
for arduino-cli.

Three things that makes true, which the personal-data record does not yet
say and must (it is a Draft: rewritten in place, not amended): its §5 rests
on "nothing personal is in it" for the three subprocesses it names, and a
model runner is the first subprocess the seam starts *that is handed a
photograph*; so §5 names the runner and the seam-started `llama-server`,
what each is given (a picture, a weights path, nothing else), that neither
fetches, and how that is held (the scrubbed environment, the argv, the
`strace`); §6 gains the model-output cache. That rewrite is part of the
phase that adds each engine.

The runner is a QM-authored engine, and build-the-seam §3 is asked first:
which existing engine should own "segment and range a picture over a
protocol on this machine"? The OpenAI-compatible servers do text and
labels, not masks or depth. There is a standard protocol for the rest: the
Open Inference Protocol (KServe V2, REST and gRPC), implemented
independently by OpenVINO Model Server, Triton, MLServer and TorchServe,
each serving an arbitrary ONNX graph -- an EfficientSAM or a Depth Anything
export is one. That is the seams record's answer, and phase 3 evaluates
it (OVMS and Triton: licence, a CPU build, telemetry, and what pre- and
post-processing then lives where) before a runner is written. If none of
those passes the gates, the runner is written, and §5's four conditions
apply: its own repository and release line, public and
compliant, its own tests, docs and decision records -- its manifest carries
the same licence gate, so numpy blocks it there too until the gate is fixed
-- and it reaches this machine by a person-run install, found the way
`ARDUINO_CLI` is found (a path, or the tools folder). Its protocol is the
Open Inference Protocol or the OpenAI-compatible endpoint phase 2's client
already speaks, both with independent implementations; a stdin/stdout
contract of QM's own has one, which the seams record's §1 refuses without
a §3 exception record naming the protocol, why no standard one fits, and
how to leave. The plan prefers a standard protocol.

**Loopback is a server the person runs, or the seam starts.** The
OpenAI-compatible chat API is the lingua franca of local servers --
llama.cpp's `llama-server`, Ollama, vLLM, LocalAI -- and one client covers
them: `LoopbackModel(base_url, model)` that checks `is_loopback()` on the
host at construction and raises `LeftTheMachine` itself when it is not
(`require_loopback()` raises `ValueError`; the finder's error names the
record, not "could not be read"), sends pictures only as base64 data URIs
(a server handed a URL or a path would fetch or read it itself), asks for
a JSON-schema'd reply and validates it with pydantic. What it must refuse:
Ollama's cloud models (`*:cloud`, served on the same port from a signed-in
account, which is *loopback that forwards* -- the record's risk row made
concrete for pictures); the finder asks `/api/show` and refuses a remote
model, and documents `OLLAMA_NO_CLOUD=1`. What it cannot detect: a proxy on
loopback that forwards (LiteLLM, an `ssh -L`) -- the risk register already
says that is the person's program. Preferred over a server the person
runs: a server the seam starts (`llama-server -m <weights> --mmproj
<proj> --host 127.0.0.1 --port <free> --api-key <random>`, never `-hf`),
so the engine's reach is the program's shape. llama.cpp and Ollama are
components with licences (MIT), so they go in the adoption record's
component audit, not the service inventory; the inventory's rows are for
the hosted endpoints a loopback server could forward to, all refused.

**Weights are files the person brings.** A models folder under the state
folder (`~/.apothecary/models`, 0700 like the rest), or a server the person
already filled with `ollama pull`. The record classes the install-time
fetches a person runs by hand (`uv sync`, `playwright install`) as not
runtime paths; reading a person's one-time *model* download as the same
class is an analogy, and `docs/plans/CONCERNS.md` §2 says that question is
open -- so it is in *Pends on* for the sponsor rather than decided here. A
program-side weights download is a second `tool_fetch` caller, and the
record says a second caller is a second door, reviewed as one. What it
costs, all of it: §2's definition of a tool fetch (a release archive at a
three-number version) rewritten to admit a weights file at a pinned digest,
and the version test with it; the host in `TOOL_SOURCES` and in the service
inventory with the ownability answer; the one-caller test; a SHA-256
checked before use; an explicit click. This plan **defers** that door: no
model in phases 1-3 needs it. A gated model (a token to download) is an
account, which is the §8 record, not a tool fetch.

**Hooks to proprietary or paid services** are the same OpenAI-compatible
seam. The hook exists the day the loopback client does; its paid backends
are not built. A pull request adding one is a proposal of the
secured-user-accounts record -- per-account authenticated consent, per kind
of data, revocable; nothing under a shared, default or anonymous account;
nothing the person did not name -- and goes to the governance branch, not
the code branch. The UI does not list them in the meantime: naming a hook
to a service the guard refuses is deciding §8 by stealth. LangChain,
LiteLLM and Instructor are worth reading and not worth importing: each
chooses the destination by a string or an environment variable, infers a
provider from a model name and takes credentials from the ambient
environment, and two of them turn on outbound tracing by a variable --
every one of them the "a setting is a decision" the record rejected.

## Candidates (licences and behaviour checked 2026-09-21)

This machine: Intel i5-4570, 4 cores, AVX2, no AVX-512, 32 GB, GeForce GT
755M under `nouveau` -- CPU-only is the hardware, not a preference. The plain
finder does 57 ms per picture (`photo check`, 160 pictures, 9.1 s, 56 MB).
**No model has been timed on this machine**; every figure below is upstream's.

| Candidate | Gives | Licence | Verdict |
|---|---|---|---|
| ArUco / AprilTag markers (OpenCV `cv2.aruco`, `pupil-apriltags`) | a labelled shape of known size: the one scale reference that is correct by construction | Apache-2.0 / MIT | **First**, as the first managed engine: no weights, and OpenCV stays out of `apothecary/` like every other C extension |
| EfficientSAM-Ti, SAM 2.1 Hiera-tiny, MobileSAM (from the repo, not the mislabelled mirror) | masks → `points` → kind and sides | Apache-2.0 | Second, as a managed ONNX engine; SAM 3 is excluded (the "SAM License": trade-control, military and share-alike terms) |
| Florence-2-base | labels, boxes, polygons | MIT | Namer; transformers-native, so a managed engine, not an import |
| Qwen3-VL (2B, GGUF), SmolVLM2-500M, Gemma 4 E2B/E4B | labels and text over the loopback chat API | Apache-2.0 (Gemma 4: verified `apache-2.0`, not gated; Gemma ≤ 3 and PaliGemma are under the Gemma terms and excluded) | The loopback namer's documented models |
| Depth Anything V2 Small | relative depth | Apache-2.0 | Thickness and z-order; Base/Large were CC-BY-NC and are excluded |
| MoGe-2 | metric depth, and its own field-of-view estimate | MIT (code and the weights the README links, verified) | The phase-3 metric candidate |
| Metric3D v2 | metric depth | unresolved (official weights untagged; mirrors disagree) | Not until upstream states it: an absent declaration is a failure to investigate |
| Ultralytics YOLO / YOLO-World / YOLOE | boxes | AGPL-3.0, analytics on by default | Excluded for phoning home; AGPL is OSI-approved and copyleft is admissible under the record, but the gate's list does not name it and an allowlist addition is an org amendment |
| Moondream 3 | labels | BSL-1.1 | Excluded (BSL is named in the record) |
| LM Studio | a loopback server | proprietary | The person's own program if they run it; never a listed backend |
| OpenVINO | a runtime | Apache-2.0, but `openvino-telemetry` is a hard dependency, and this CPU is below its supported list (6th-generation Core and up; it has the AVX2 the runtime needs) | Skip as a runtime; OpenVINO Model Server is evaluated in phase 3 as an Open Inference Protocol server |

**The licence gate as it stands** (`.github/workflows/license-check.yml`):
`pip-licenses --allow-only` with a string list, run over `uv sync --locked
--dev`. Two facts the plan cannot ignore: optional extras are never
installed, so never scanned (the record wants every shape a project ships
gated); and pip-licenses takes a compound `License-Expression` as one name,
so **numpy 2.5.3 (`BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`)
fails it** (run here: exit 1), and with numpy every model runtime and
OpenCV. Two tasks, two owners: normalising to SPDX, evaluating `AND`/`OR`/
`WITH`, and scanning every shape a project ships are *this project's* CI
obligation under the record's §4, done in phase 0; adding a licence to the
allowlist is an org amendment, and with expressions evaluated numpy still
needs one -- `CC0-1.0` is FSF-free and not OSI-approved, exactly the case
§4 says is the signal to adjudicate. A runner published as its own project
carries the same gate in its own CI, so the blocker moves with it rather
than away.

## Accuracy: the number the argument rests on

`features/finder-accuracy.md` is the plain finder's reading and the frame
every finder is held to. A model-backed finder becomes the default for
anything only when, on the same table plus a row of real bench photographs
with a marker in frame:

- *found* and *named right* do not fall on any row;
- *made up* stays at zero (an invented shape is worse than a missed one);
- the *honest* gap is positive (confidence drops on the ones it gets wrong);
- seconds per picture on this machine are printed beside the row.

`apothecary photo check --finder <name>` gets the marker row and the timing
column in phase 0, so the comparison exists before there is anything to
compare.

## Phases

**0. The seam, hardened** (no model yet).
Entry-point discovery; the `Backend` descriptor with reach; the `recorded`
finder (`stated` with a backend name and digest); `label` on `Provenance`;
`ask`/`parse` split as the pattern; the fence tightened; the marker row and
timing column in `photo check`; tests in `tests/test_stays_local.py`'s
style: every backend's reach is `engine` or `loopback`, a non-loopback URL
raises `LeftTheMachine` at construction, a cloud model is refused, and the
one-caller test is untouched. The licence gate rewritten (SPDX, expressions,
every shape) and the `CC0-1.0` adjudication filed with the org. The finder
seam record drafted on the governance branch (phase 4 says what it holds).

**1. Markers.** An `aruco` finder: a marker's corners as a labelled
`FoundShape`, so `--known-shape` fills itself and a bench photograph is in
millimetres. The first managed engine -- OpenCV in a runner the seam
starts, never imported -- which is the shape phase 3 needs anyway, with
the personal-data record's §5 rewritten to name it.

**2. A namer over loopback.** `LoopbackModel` and one finder,
`vlm:<model>`: labels for the shapes the plain finder found (or the
marker finder measured), so `ScaleReference.known_shape` and the part-in-frame
reference (`scale-references.md`) work without hand-written JSON. A
seam-started `llama-server` over a weights file in the models folder as the
managed shape; Ollama as the person's own server, with the cloud-model
refusal. A selection record for the model, and the component audit rows
for llama.cpp and Ollama. Measured on this machine before it is offered.

**3. Masks and depth as a managed engine.** First the §3 question: an
Open Inference Protocol server the seam starts over ONNX exports
(EfficientSAM / SAM 2.1 tiny, Depth Anything V2 Small or MoGe-2) --
OpenVINO Model Server and Triton evaluated for licence, a CPU build,
telemetry and where pre- and post-processing live; failing that, one
runner, its own project, serving that protocol or the OpenAI-compatible
endpoint phase 2 speaks, ONNX Runtime with telemetry off in its
environment and by the API call, `strace` recorded (Linux; the Windows
measurement is named as not made); `points` consumed by `geometry.py`, `depth_relative` on shapes,
`CameraReference(focal_px)` from EXIF (or MoGe-2's own estimate, named as
such) for the metric case, and `Provenance.thickness_guessed = False` when
a depth said so. A selection record per model.

**4. The records** -- one decision each, as the drafting contract asks.
(i) *Shape finder seam: finders are an engine slot, reached behind a
managed runner or over an OpenAI-compatible protocol on loopback* --
shaped like the G-code seam record (an engine slot, a scripted engine for
tests, an env pin that chooses *which local engine*, never *where data
goes*), with the size-smell thresholds as revision triggers and the
sentence that a paid hook is the seam whose non-loopback address is
unlawful until the secured-user-accounts record exists; filed with phase
0. (ii) One selection record per engine, filed with the phase that adds
it, carrying that engine's row of the licence table, naming its protocol
and answering replaceability (the obligations table's *seam protocol
named* row). (iii) The personal-data draft rewritten in place for each
engine the seam starts: §5, §6, and the service inventory's rows for the
hosted endpoints a loopback server could forward to, each marked refused.
(iv) The adoption record's component audit extended for llama.cpp,
Ollama and any runner. (v) The §7 declaration of what the distributed
artifact is actually licensed under, once a copyleft component is in it
(the record admits copyleft; it asks that the deliverable's licence be
stated, not that copyleft be kept out). A QM-authored runner is its own
project with its own records. `detector-selection.md` graduates the way
its header says, into a selection record that cites the seam record --
(ii), with its four obligations as that record's checklist; only its size
smell belongs in (i) -- and its `ShapeProvider`/`NaiveProvider` names
become `ShapeFinder`/`PlainFinder` on the way.

**5. The paid hook.** Not built. What it would take is written down in
phase 4's seam record so nobody rediscovers it: the §8 record first; then
the edits that record names as the review -- `stays_local.py` (the guard
refuses every non-loopback address today, whatever a descriptor says) and
`tests/test_stays_local.py`; then the loopback client's construction
check; then a `reach: account` backend the descriptor test stops
refusing. The seam's shape does not change; its guard does, under a
record.

## Pends on

| Question | Whose | What unblocks it |
|---|---|---|
| The licence gate: SPDX normalisation, expression evaluation, every shape scanned | this project (open-license §4) | phase 0 |
| `CC0-1.0` (numpy) on the allowlist | the org (an allowlist addition is an amendment) | the adjudication §4 describes, with the FSF listing cited |
| Whether a person's one-time model download is the same class as the record's install-time fetches | the sponsor (`CONCERNS.md` §2 is open) | a sentence in the personal-data draft, or a *Pends on* row in the seam record |
| A second tool-fetch door for weights | the sponsor, against the personal-data record | not needed for phases 1-3; deferred |
| The runner's protocol: an existing one, or a seams §3 exception | phase 3 | the OpenAI-compatible endpoint if the runner can serve it; else the exception record with its exit plan |
| Metric depth weights' licences | upstream | an upstream statement, or the mirror with a coherent declaration |
| Whether the browser panel offers a finder choice | the one-screen plan | phase 2 puts a `finder` field on the panel's requests; the census counts one more control |

## What this page is not

Not a model selection (that is a record), not a promise of accuracy (that
is a measurement), not a hook to a paid service (that is a record the
organisation has not written). It is the shape that lets all three happen
without a setting, a string or an environment variable deciding where a
photograph goes.
