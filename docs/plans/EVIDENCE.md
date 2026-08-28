# Evidence

Every non-obvious claim made anywhere in `docs/plans/`, with how it was
established and how to re-establish it. Read this before building on anything
here: **another agent's report is evidence, not a finding.**

Session of record: 2026-08-14. apothecary at `f1c1543` (`main`), rad at
`b854747` (`main`), qm at `main` and at `project/apothecary`.

Three grades are used, and they are not interchangeable:

- **Executed** — a command was run and its output is quoted. A finding.
- **Read** — a file was read and the claim is what it says. Reliable for "the
  code contains X", unreliable for "the code does X".
- **Inference** — reasoned from other facts. Marked as such everywhere it
  appears; treat as a hypothesis with a named way to settle it.

---

## A. Executed

### A1 — `_rehydrate` ignores an explicit `type` discriminator

Grade: **executed**. The single most actionable finding in this work.

```bash
cd apothecary && uv sync
uv run python - <<'PY'
from apothecary.api import _rehydrate
for c in [{"type":"cylinder","h":10,"r":5},
          {"type":"cylinder","h":10,"r1":3,"r2":5},
          {"type":"sphere","r":5},
          {"h":10,"r":5}]:
    o = _rehydrate(c)
    print(f"{str(c):48} -> {type(o).__name__:10} {o.render()}")
PY
```

Output at `f1c1543`:

```
{'type': 'cylinder', 'h': 10, 'r': 5}            -> Sphere     sphere(r=5.0);
{'type': 'cylinder', 'h': 10, 'r1': 3, 'r2': 5}  -> Cylinder   cylinder(h=10.0, r1=3.0, r2=5.0, center=false);
{'type': 'sphere', 'r': 5}                       -> Sphere     sphere(r=5.0);
{'h': 10, 'r': 5}                                -> Sphere     sphere(r=5.0);
```

Also executed: `_rehydrate({"wat": 1})` → `Union(children=[], comment='unrecognized
object')`. Wrong geometry and empty geometry respectively, neither raising.

`docs/scene-json.md` promises an explicit `type` is honoured, so line 1 of that
output is a bug against the documented contract rather than the documented
looseness. See `features/scene-document-validation.md`.

### A1b — the no-network check was watched failing

Grade: **executed**, and the important one for the local-only rule.

`tests/test_stays_local.py` replaces every way Python opens a connection with one
that refuses. A green run of it proves nothing unless the guard bites, so a
deliberate fault was inserted into the shape finder:

```python
urllib.request.urlopen("http://example.com")   # inserted into PlainFinder.look
```

Four tests went red and named the call. The fault was removed and they went
green. The file also contains `test_the_guard_itself_works`, so the guard cannot
silently stop guarding.

Limits, stated in the file: it does not catch a separately started helper
program, a swallowed failure on another thread, or a connection opened before
the tests began.

### A1c — the picture path runs end to end

Grade: **executed** at the tip of this work.

```bash
uv run apothecary photo look  /tmp/bench.png
uv run apothecary photo build /tmp/bench.png --width-mm 800 --out /tmp/bench.scad
```

On a generated picture holding a rectangle, a circle, a triangle and a long thin
bar, the finder reported four shapes, read them as `plate`, `disc`, `wedge` and
`slot`, and produced drawing instructions in which every piece carries a note
saying which finder found it, how sure it was, and that the thickness is a guess.
Confidences ran 0.71 to 0.79 — never near certain, by design.

47 tests cover the path. Two failures elsewhere in the suite
(`test_parts_listing_contains_known_part`, `test_source_file_exists[gridfinity]`)
were confirmed pre-existing by stashing this work and re-running, and later by
running them on the starting point itself. Both were a part of the parts library
that had never been fetched; fetching it clears them. See A16.

**Not checked:** nothing renders a printable model in this sandbox, so no
generated instructions were ever turned into a solid.

### A2 — apothecary's dependency tree contains no CV or ML stack

Grade: **executed** (`uv sync` succeeded, then the lockfile was enumerated).

```bash
grep -icE 'opencv|torch|onnx|tensorflow|scikit|numpy|scipy' apothecary/uv.lock   # -> 0
```

`pillow` is present in the `dev` dependency group only, used by
`apothecary/cli/docs.py::_assemble_gif`.

### A3 — no menu, no photo, no rad anywhere in apothecary

Grade: **executed**.

```bash
grep -ril 'menu'  apothecary/apothecary apothecary/templates | wc -l   # -> 0
grep -ril 'photo' apothecary/apothecary apothecary/templates | wc -l   # -> 0
grep -rn  '\brad\b' apothecary/apothecary                              # -> only `rad = math.radians(...)`
```

### A4 — the three constructs this feature line would introduce first

Grade: **executed**.

```bash
grep -rc 'APIRouter'   apothecary/apothecary | grep -v ':0' | wc -l   # -> 0
grep -rc 'StaticFiles' apothecary/apothecary | grep -v ':0' | wc -l   # -> 0
grep -c 'optional-dependencies' apothecary/pyproject.toml             # -> 0
```

All 26 module-level routes are `@app.<verb>` decorators in `api.py`
(`grep -cE '^@app\.(get|post|put|delete)' apothecary/apothecary/api.py` → 26).

### A5 — rad's conformance vectors

Grade: **executed**.

```bash
jq -r '.version'      rad/conformance/vectors.json   # -> 0.3.0
jq   '.cases|length'  rad/conformance/vectors.json   # -> 34
```

### A6 — the viewer template's size

Grade: **executed**. `wc -l apothecary/templates/fractal_viewer.html.j2` → 1837.

### A7 — the site registry is a hardcoded dict

Grade: **executed**. `grep -n '_site_store = SiteStore' apothecary/apothecary/api.py`
→ line 618. Two entries: `garage`, `parts_library`.

### A8 — the sandbox's own limits

Grade: **executed**. `gh` absent; `openscad` absent; `uv`, `python3` 3.11,
`node` 22, `npm`, `jq`, `rg` present; Chromium preinstalled at `/opt/pw-browsers`
with `PLAYWRIGHT_BROWSERS_PATH` set. `git clone` over https to github.com
succeeds; `curl https://api.github.com/orgs/quaternionmedia/repos` returns
**403** with `sessions are bound to their configured repositories`.

This is why §9 of `HANDOFF.md` exists.

### A9 — four repository names do not resolve over anonymous git

Grade: **executed, and deliberately inconclusive.**

```bash
for r in looksatphotos LooksAtPhotos looksatphoto looks-at-photos looksAtPhotos \
         looksatvideos LooksAtVideos rad-android rad_android radandroid RadAndroid; do
  git ls-remote https://github.com/quaternionmedia/$r.git >/dev/null 2>&1 \
    && echo "EXISTS $r" || echo "no     $r"
done
```

All eleven printed `no`. A control in the same run — `alfred`, lowercase —
printed `EXISTS`, which is what makes the harness trustworthy and the result
useless: **a private repository fails identically to a nonexistent one.** This
establishes that the names are not public. It establishes nothing about whether
they exist. `rad-menu` was not probed in that run and is in the same position.

Settled by one command from a session with the credential:
`gh api orgs/quaternionmedia/repos --paginate --jq '.[].name' | sort`.

---

### A10 — the measured accuracy of the plain finder

Grade: **executed**, `apothecary photo check --count 20`. Table and reading in
`features/finder-accuracy.md`. Found 100% in every condition, named right
between 51% and 100%, nothing invented anywhere, and confidence measurably lower
on wrong answers in every hard condition.

### A11 — an independent review broke it in ways the harness could not

Grade: **executed** by a reviewer with no knowledge of the reasoning, asked to
break the code rather than check it, running its own scripts.

Twenty-two findings. The serious ones: non-square pictures stretched by a third;
a subject filling more than half the frame reported as the background at higher
confidence than a correct answer; see-through backgrounds finding nothing; phone
photographs read a quarter turn round; a tilted reference scaling the build a
third too big; pictures smaller than the working size losing their shapes.

All fixed, each with a test in `tests/test_photo_hard_cases.py` that failed
first. Also fixed: two regressions the label fix had introduced, an empty
vocabulary being silently replaced, invalid shapes being accepted, scratch
pictures never being cleared up, and three ways round the no-network guard —
including that replacing `socket.socket.connect` leaves the C-level socket
underneath untouched, so the guard was weaker than its own docstring claimed.

**Performance, measured by the reviewer:** 168–434 ms on a 4000×3000 picture,
2.34 s on a 108-megapixel one. No runaway growth found.

### A12 — the option builder holds both limits, and the viewer groups by word

Grade: **executed**. `tests/test_menu.py` (33 checks) covers the eight-option
ceiling, the twelve-character labels across every kind of ring, that shortening
never trails off, that working out the options changes nothing, and that a ring
which cannot fit refuses rather than quietly dropping the ninth thing.

`tests/test_photo_in_the_viewer.py` shows an arrangement built from a picture
appearing beside the others over the API, its pieces carrying their word as the
group the viewer already filters by, what is known about each piece served
alongside, and the picture itself served from where it was left.

Found while doing it: adding an arrangement to the register leaked between
tests, because the register only grew. It can now be taken off again, and a test
covers that.

### A13 — the walkthrough runs in a real browser and produces itself

Grade: **executed**, and **watched failing.**

`apothecary docs generate` runs `tests/e2e/test_docs_photo_walkthrough.py` in
Chromium and turns a green run into `docs/generated/photo-walkthrough/` — nine
steps, nine screenshots, an animated walkthrough and the actual recording of the
run. Each step is both a point where the run has to be correct and a sentence of
the walkthrough, so it cannot describe something that did not just happen.

Watched failing: removing the line that gives each piece its word turned both
tests red, naming what broke. Putting it back turned them green. A red run
publishes nothing rather than publishing something stale — the runner prints
"Doc-workflow tests failed; docs were not regenerated", which was seen for real.

### A14 — the viewer did not work at all without a way out to the internet

Grade: **executed**, and the reason the browser test was worth writing.

The first run reported `ERR_TUNNEL_CONNECTION_FAILED` four times and the page sat
on "Loading site…". The viewer fetched its 3D drawing library from a public
website through an import map, so in a sandbox with no route out the code never
arrived. This had been recorded as untidiness for a long time; it was a total
failure, and nobody had noticed because nobody had opened it without a network.

The four files are now kept beside the software and served from it.

**Correction to an earlier claim in this folder.** It said the viewer's grouping
worked with no new drawing code. It did not: the filter chips were drawn only for
categories on a list written into the page, so a word nobody had written down got
no chip. One change fixed it. The claim was made from reading the code and was
wrong until the browser ran it.

**Since corrected — see A16.** This section previously ended by saying fourteen
browser tests fail in a full run and pass individually, and blamed the shared
server. That explanation was a guess, it was wrong, and it is now withdrawn.

### A15 — a second independent review, and what it broke

Grade: **executed**.

The work was handed to a second reviewer with the same instruction as the first:
break it, do not confirm it. Seventeen faults came back, two of which let a
person reach files the software was supposed to refuse:

- A picture could be swapped for a shortcut pointing outside the one allowed
  folder after the check had passed, and the swap was honoured when the file was
  served. The path is now re-checked at the moment of serving, not only when it
  is accepted.
- The type of file being served was taken from the name of the file, so a name
  could make the browser treat a picture as something else. Serving now picks
  from a short list of picture types and tells the browser not to guess.

The rest: names that are not names were accepted; a name with a dot in it could
address something other than itself; a queue-file instead of a picture hung the
reader for ever; a very long path produced a server crash instead of a refusal;
shortening a label destroyed decimal numbers and could make two different things
read the same; a grouped ring's inner rings were never size-checked; a photo
arrangement could quietly replace a built-in one; resetting one did nothing; a
loop between arrangements could hang the option builder; the picture code and
the word list imported each other.

All seventeen are fixed, each with a test that failed first. The refusal tests
are in `tests/test_photo_in_the_viewer.py`.

### A16 — everything passes together, and the earlier explanation was wrong

Grade: **executed**.

Whole suite in one run, ordinary tests and browser tests in the same process:
**697 tests, none failed, two skipped.** Reproduce with a server running and the
picture folder named:

    APOTHECARY_PICTURE_ROOT=/tmp/pics apothecary serve --port 8765 &
    APOTHECARY_PICTURE_ROOT=/tmp/pics uv run pytest tests -q

The fourteen failures reported in A14 had three causes, none of them the one
that was guessed:

1. **A part of the parts library had never been fetched.** One part is kept in a
   separate place that has to be pulled down once. It had not been, so three
   ordinary tests failed. `git submodule update --init` fixes it. This was true
   of the starting point too, before any of this work — checked on the original
   commit.
2. **The program that turns a design into a printable file was not installed.**
   Every browser test that asked for one got a refusal, and the viewer test that
   watches for errors saw eleven of them. Installing it clears them.
3. **A fixture of mine switched the whole browser suite off.** Naming the picture
   folder is something only picture tests need, but starting the server was made
   to depend on it. When nobody named a folder, the server fixture skipped, and
   every browser test skipped with it — twenty-six of them, silently, while the
   run reported success.

The third is the one worth keeping. A count of passing tests cannot see it,
because what it would have to notice is tests that were never there. There is now
a check that reads the setup file and refuses to let anything the server is built
on be a thing that can skip: `tests/test_browser_suite_is_not_gated.py`. It was
watched failing — the server fixture was temporarily pointed back at the skipping
one, the check went red with the right sentence, and it was put back.

### A17 — the count of controls, and the withdrawal of "twelve"

Grade: **executed**, and a correction to this folder's most-quoted number.

    apothecary census

reads the viewer's page and reports **twenty controls of its own** — four things
done to the scene, six places in the lists, three ways of taking hold of a piece,
and no ring. Reproduce it in one command; it needs no server and no browser.

**"Twelve" is withdrawn.** It was a hand count (B6). A counter was written to
make it reproducible, and it agreed — because it had been built until it agreed.
A third reviewer, given only the counter and asked to break it, showed:

- It counted **names, not controls.** The two buttons on a job are fetched the
  same way, so they counted once. Three boxes for typing a position counted once.
  A drop-down of machines, which nothing listens to, was invisible entirely.
- **Its own rule did not produce its own number.** Stepping out of a piece by
  button was filed as a control; stepping out by clicking the trail was filed as
  moving your attention. The two run the same three lines. Applied evenly the
  rule gives nine, or sixteen — never twelve. The reviewer ran both and showed
  the working.
- **A new control could hide inside an old one.** A delete button added to a row
  of a list attaches exactly as the buttons already there attach; the counter
  absorbed it, reported the same number as before, and described it with the old
  button's words.
- **Failing to read the page and finding nothing gave the same answer.** Only one
  style of quotation mark was accepted. Reformatting the page with an ordinary
  tidying tool took the count to zero, with no complaint and a successful exit.
- The claim that navigation "changes nothing" was **false**: moving your
  attention makes the program build shapes, and building a shape writes a file
  through the very same request the rebuild button sends.

All of it was reproduced before being accepted. The counter was rebuilt:

- Two scans that are **not added together** — the page's own markup, one control
  at a time, and every place the page listens.
- Each listening place identified by what it listens on, what it listens for,
  **and the first thing it then does**, which is what makes two buttons in a row
  two entries and makes a new one impossible to hide.
- Two questions asked separately — what kind of surface it is, and what it
  changes — because collapsing them is what let the same behaviour be called two
  different things depending on the answer wanted.
- Refusals with line numbers for anything unclassified, and a **separate refusal
  for finding nothing**, so an unreadable page can never score perfectly.

23 tests, each named for the attack it came from. The meter is the first number
and it has to reach **nothing**: a ring that leaves five buttons behind has not
replaced them.

**What it still cannot do**, stated in the module itself: it reads the page as
text, so a listener inside a comment would be counted; the drawing library brings
listeners of its own that are real and uncounted; and it is one page, so the
command line and anything talking straight to the machine are outside the number.

### A18 — many photographs at once, and what two reviewers broke

Grade: **executed**, measured on drawn pictures whose answers are known.

    apothecary photo gather <folder> --map-to went-together.html
    apothecary photo gather-check --each 3

**The measurement.** Thirty-two folders of twenty-seven drawn photographs — eight
hundred and thirty pictures, near enough five thousand pairs. Seventeen of those
folders were never used while the thresholds were being chosen; those are the
ones that count.

| | Groups found | Groups mixing unrelated pictures |
|---|---|---|
| Fifteen folders used for tuning | 41 of 195 there to find | **0** |
| Seventeen folders never used for anything | 41 of 221 | **0** |

Pair by pair: never wrong on any seed tried, and 18–41% of pairs answered rather
than declined. The trade is deliberate and is stated wherever the figure appears:
**about a fifth of the groups that are there, and never one built out of
photographs that did not belong together.**

**How it got there**, which matters more than where it ended up:

| | Groups found | Mixed |
|---|---|---|
| Matching shapes one at a time | — | joined 10 unrelated pairs in one folder |
| Adding the arrangement check | 67 | 9 |
| Requiring three shared shapes, not two | 62 | 5 |
| Refusing shapes too alike to tell apart | 41 | **0** |

Every step of that table came from the meter reporting a failure, not from
reasoning ahead of it.

**Three claims made here were false, and are withdrawn.**

- *"Nothing is merged on a maybe."* There was an exception for the case where
  every shape in both pictures is accounted for — which two pictures holding one
  shape each meet on a single match, with no arrangement to check. Two unrelated
  photographs came back as the same thing at full confidence. The exception is
  gone.
- *"No group has ever mixed unrelated photographs."* True of the three seeds the
  test happened to use. Of twenty-five, thirteen produced a mixed group. The
  table above is the corrected version, and the tests now separate the seeds used
  for tuning from the seeds used as evidence.
- *"The same gathering always gives the same picture."* The fit measured its error
  in the second picture's frame, so it was stricter one way round than the other.
  One folder handed in nine different orders gave five different answers, some of
  them merging a photograph that did not belong.

Also found and fixed: a report that said "held together at 100%" and "nothing was
built" about the same pictures in one run; parts laid side by side that all sat on
top of each other, because width was measured from the middles of the pieces
rather than their edges; two pieces silently sharing one name so the second
replaced the first; pieces dropped for not having a number on the end of their
name; and a picture's typical confidence taken as the upper of two, so one
certainty and one blank guess read as "typically completely sure".

**The finding worth keeping.** The reviewer injected twenty-seven faults into the
code and **twenty-four were caught by no test at all** — including the test named
for the module's central refusal, which never called the function it was named
after. The suite was green throughout. Tests now exist for each, and each was
watched failing with its fault put back.

### A19 — a person's word, and what it is worth

Grade: **executed**.

The sorting on its own is measurably conservative and not very good — a fifth of
the groups that are there. A person is much better and cannot say why. So the
software was rebuilt around that rather than around pretending otherwise.

    apothecary photo gather <folder> --ask questions.txt
    apothecary photo gather <folder> --answers questions.txt

**Measured, on the same nineteen drawn photographs:** the machine alone found
**2** groups. Five sentences typed by hand took it to **5**. Reproduce with
`apothecary/gathering/bench.py::draw_occasions(seed=17, each=2)` and the answers
quoted in `features/gathering.md`.

**What is checked rather than claimed:**

- *A person's word wins.* Tests drive `gather()` with an answer that contradicts
  the machine, both ways round — joining what it split and splitting what it
  joined — and with answers that rescue a picture it discarded and discard one it
  liked.
- *A person's word carries.* One answer about two photographs is shown pulling a
  third along with it through the grouping, because the grouping runs on the
  settled verdicts and cannot tell which came from where.
- *A person's word marks the machine.* `Gathering.scorecard()` counts agreed,
  overruled and silent. The report prints it without being asked.
- *Two people who disagree are refused.* Contradictory answers raise and name
  both lines rather than picking one.
- *Nothing a person wrote is rewritten.* The question sheet appends; it never
  tidies their words.

**The machine's half is arithmetic, and that is enforced.** Two tests parse the
source of `apothecary/gathering/` and fail it if it imports a model, a service,
or anything that speaks over a network; a third fails it if it imports `random`
anywhere on the deciding path. Two more hand the same photographs and answers in
twice — and in the other order — and compare the results exactly.

That is not fastidiousness. The three promises above are only meaningful against
something repeatable: a word can only *win* over a thing that can be overruled, a
question's worth is a number and a number about a guess is a guess, and an answer
only scores the machine if the machine would say the same thing tomorrow.

**Not measured:** whether the questions it chooses to ask are the ones a person
would find worth answering. The ranking is arithmetic — how many other pairs an
answer would settle — and that it is the *right* arithmetic is an argument, not a
finding. It needs somebody to sit down with a real folder of photographs, which
has not happened. See concern 20.

### A20 — what a reviewer found wrong with all of that

Grade: **executed**. Two of the three headline promises were false on one answer
and no unusual input, and are now fixed with a test each, watched failing.

- **"A person's word wins."** It did not. The check that refuses a group which
  disagrees with itself treated a *machine's* guess as grounds to destroy a group
  a **person** had built — and the report printed "your word was taken as it
  stands" in the same breath. One answer, three photographs, zero groups. A
  machine's disagreement is now only a quarrel inside a group the machine built;
  a person's disagreement always is; and where the machine stands down it says so
  under "Where your word beat the machine's".
- **"A person is never asked for something that follows from what they said."**
  It was, on the very next run: after one answer joined four photographs, the
  next sheet asked three questions whose answers already followed. The guard
  meant to prevent this was dead code — a person's verdict is never "cannot
  tell", so the condition could never fire. Pairs already known to be the same
  thing are now excluded outright, and the dead guard is gone rather than left
  looking like protection.
- **`--ask` destroyed a person's notes.** Writing the question sheet to a file
  that was not also passed as `--answers` replaced it wholesale, no warning. And
  the recommended round trip re-appended the whole question block every run, so a
  file answered three times held the same question three times, and answering two
  copies differently was reported as *two people disagreeing*. There is now one
  marked line: everything above it is the person's and is never touched;
  everything below is the machine's and is replaced.
- **An answer about an unreadable picture vanished silently.** The picture is
  never compared, so the answer went nowhere and nothing anywhere mentioned it.
  Now reported under "Things you said that could not be used", saying what to
  type instead.
- **The flagship refusal came out as a traceback.** `PeopleDisagree` is raised
  inside the sorting, and only the file-reading was wrapped. Two more refusal
  paths named nothing at all: comparing a picture with itself, and a file saved
  in the wrong encoding.
- **The worth of a question was arithmetically wrong** whenever a larger thing
  was involved — it read the size of the composite rather than the group an
  answer would actually merge, advertising a question worth four as worth one and
  sorting it last.
- **The ranking took 22 seconds on two hundred photographs**, longer than
  everything else put together, because the group sizes were recomputed for every
  pair. Now 0.07 seconds.
- **`--most 0` wrote "Nothing else is in doubt"** onto a sheet with four
  questions outstanding, and truncation was never disclosed at any value.
- **The sheet's own instructions parsed as answers.** Uncommenting it wholesale
  fed it its own examples back. The gaps are marked now, so they are refused by
  line rather than read as pictures called "one" and "another".

**And the tests were the bigger finding again.** Mutations that deleted the whole
`--answers` path from the command, made the question ranking return nothing, or
removed the ranking altogether all left the suite green — partly because three
tests *skipped themselves* when the feature they covered was missing. Nothing
exercised the command at all. There are now sixteen tests that drive
`photo gather --answers/--ask/--most` end to end, the skipping fixtures are
replaced with ones that cannot vanish, and each of the eight surviving mutations
was re-applied and watched turning the suite red.

## B. Read

### B1 — apothecary's `adr/` is not in apothecary

`.gitmodules` pins `governance/qm` to `branch = project/apothecary`.
`.github/workflows/adr-lint.yml` states the branch-per-project model explicitly
and globs `governance/qm/adr/DRAFT-*.md`. `find . -type d -name 'adr*'` in the
apothecary working tree returns nothing.

The branch was cloned directly and read:
`git clone --depth 1 -b project/apothecary https://github.com/quaternionmedia/qm.git`
→ `adr/` contains `DRAFT-constitution-adoption-scope.md`,
`DRAFT-site-structure-substructure-feature-hierarchy.md`, `README.md`,
`TEMPLATE.md`. Both records are `Proposed`, both unnumbered.

### B2 — the four governance mechanisms in §5 of the handoff

- `qm/.github/workflows/namespace-guard.yml` — `on: pull_request: branches:
  ['project/**']`, fails paths outside `adr/` that differ from `main`.
- `qm/.github/workflows/one-pr-check.yml` line 69 — `--per-base 'project/*'`.
- `qm/project-seed/ci/adr_lint.py` lines 50–54 — the banned-vocabulary regex,
  quoted verbatim in `HANDOFF.md` §5.5.
- `qm/README.md` "Branch namespaces" — five namespaces, and the statement that a
  `project/<name>` branch is never the head of a pull request.

### B3 — what rad asks of apothecary

`rad/adr/DRAFT-rad-release-milestones.md`, v0.0.2: apothecary and benchmark are
named as proving consumers; the integration standard is called "the real
deliverable of this milestone"; at least one new vector found by a host is
required. `rad/adr/DRAFT-rad-adoption-and-scope.md` §1 puts the host's state
layer outside rad's scope, and §3 lists C13 (the platform-free core is a comment
header inside a file that calls `document`) as open.

### B4 — no personal-data record exists in the qm corpus

`qm/records/` was listed in full and searched by content for privacy, PII,
personal data, biometric, GDPR. Nothing. `DRAFT-open-license-exclusion-and-
upstream-remediation.md` §6 governs provider replaceability and says nothing
about data. This is the basis for `features/photo-privacy.md` and
`edits/qm-main.md` gap 1.

### B5 — the eight seed obligations, and apothecary's standing

`qm/project-seed/adr/README.md` lists eight. `DRAFT-constitution-adoption-scope.md`
on `project/apothecary` was read against them: **service inventory, risk
register and control-plane size smells are absent**; the quarterly upstream scan
is an unnamed gap. rad's `DRAFT-rad-adoption-and-scope.md` §5 is the format done
correctly and is the model for the rewrite.

### B6 — the hand count of twelve, and its withdrawal

**Withdrawn. Superseded by A17.** This section said twelve, counted by hand from
`bindEvents()` and the DOM ids it binds. The definition of "idiom" was a sentence
rather than something that could be tested, and the number was wrong. Kept here
rather than deleted so that anyone who has quoted twelve can find out why it
moved.

---

## B7 — nothing in the current code reaches the network at run time

Grade: **not established.** Asserted nowhere, and the proposed local-only rule
depends on it being either true or fixable. What is known by reading: the viewer
template fetches its 3D drawing library from a public host via an import map, so
at least one run-time network use exists today.

The check the rule proposes — run the tests with networking disabled — was **not
run** in the session of record and should be written, watched failing, and only
then trusted.

## C. Inference

Each of these is load-bearing somewhere in `docs/plans/` and none is established.

| Claim | Rests on | Settled by |
|---|---|---|
| `rad-menu` is the extracted platform-free core | `rad/adr/DRAFT-rad-core-extraction.md` §3 proposes `core/` + `dom/`; the name fits | reading its README, once it is known to exist |
| `rad-android` does not exist yet | `DRAFT-rad-platform-plans.md` specifies the module in detail, and specifying is not creating; rad's adoption record lists repo creation among the human-only steps | the org enumeration |
| `looksat*` would be a `ShapeProvider` implementation | the name, and P4's doctrine that detectors are engines to select | reading them |
| `project/apothecary` is 19 commits behind `main` | read from `qm/governance-status.yaml`, generated `2026-08-11T23:10:10Z` — **a generated document, not a measurement made here** | `git rev-list --count project/apothecary..main` in a full clone |
| A Pillow-only detector is ~150 lines | estimate from the algorithm (greyscale → Otsu → connected components → bbox + fill ratio + vertex count) | writing it |
| The rings in `edits/apothecary-surface.md` fit ≤8 with ≤12-char labels | composed by hand against the contract's limits | a resolver unit test |
| Removing eleven controls makes accessibility cheaper | argued from the contract's per-control obligations | measuring, after the migration |
| apothecary's best candidate new vector is "same context type, different `role`, different verb set" | reading the contract's four context types against `Assembly.role` being free-form | attempting the integration |

---

## D. Things checked that turned up nothing

Recording these so nobody spends the time twice.

- **A rad reference in apothecary.** 25 hits for `rad`, all `math.radians` locals
  in `models/vectors.py` and `models/shapes.py`, plus `radius` fields.
- **A `word` or `grammar` concept.** Three hits for `word`: a CSS
  `word-break: break-all`, prose in a `.scad` comment, and "404 wording" in
  `api.py`. Zero for `grammar` or `language`.
- **An existing graph or link layer.** Five hits for `graph`: `RevisionGraph` and
  two comments reading "not a node-link graph" about the minimap.
- **A `moat` or `alfred` reference in apothecary.** Zero each.
- **An `Immich`/`PhotoPrism`-style photo service in moat.** None. `charts/frigate`
  is the only object-detection workload; `charts/jellyfin`'s `/dev/dri` hostPath
  is the only hardware-acceleration pattern; no GPU device plugin anywhere.
- **Scene detection or ML in alfred.** None. `alfred/core/routes/preview.py`
  extracts a single JPEG via `video.save_frame(...)`; that is the whole of its
  frame handling.
