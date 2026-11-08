# The family's hub

apothecary is the `irl` family's hub: it runs hearth's coordinator, so a member of
the family is handed its part of whatever fires and every outcome is kept.
[hearth](https://github.com/quaternionmedia/hearth) holds the contract, `family/1`,
and the coordinator, imported from `qm-hearth`, never copied.
[Walkthrough page 22](../walkthrough/22-the-irl-hub.md) runs it, and
[page 23](../walkthrough/23-a-procedure.md) a procedure through it;
[the plan](plans/irl-hub-2026-11-02.md) is what is built on it next.

## What it answers

| Route | Answer |
|---|---|
| `GET /family/identity` | What the hub is: `apothecary`, of `irl`, the contract it keeps, the conformance version it replayed, this running instance |
| `GET /family/` | Each member, how it is reached, and each recent delivery's outcome: status, error, milliseconds from the fire, the instance that took it |
| `GET /family/members/<name>` | A pull member's last cue and action |
| `GET /family/members/<name>/events` | The same, as a stream |
| `/machine/family/*`, `/board/family/*` | A hosted member's own four routes |
| `GET /family/beside` | What each member the hub started itself is doing now: its state, pid, instance and restarts |
| `GET /sites/<s>/procedures` | The names of the site's procedures |
| `GET /sites/<s>/procedures/<p>` | One as it stands: each step's status, why, whether GO will fire it, and the outcome of its last fire per member |
| `PUT /sites/<s>/procedures/<p>` | One written, whole |
| `POST /sites/<s>/procedures/<p>/steps/<n>/go` | One step fired through the hub, and the procedure as it then stands; a 409 for a step not standing by |
| `POST /sites/<s>/procedures/<p>/again` | The procedure started over |

`hearth check` judges it from outside, by these routes alone:

```bash
uv run apothecary serve --demo
uv run hearth check --hub http://127.0.0.1:6283
```

`hearth check` judges a hosted member the same way, under its name:

```bash
uv run hearth check http://127.0.0.1:6283/board \
  --action '{"expect": {"node": "garage:esp32_blink"}}'
```

`tests/test_family_hub.py` replays the hub's check against a real port and pins the
version of hearth's vector set it replayed; `tests/test_family_members.py` replays
each member's, with one real action on the simulated bench.

## Its own members

The family's own members are hosted in the hub's process, whatever the table says. An
action names what it is for by its `node`, the address the evidence log uses.

| Member | Verbs | On |
|---|---|---|
| `machine` | `home`, `run` {`file`, `part`}, `pause`, `resume` | a printer or a router pinned to a node. `{"home": true}` will do where one is pinned. `home` sends the line of the machine's own dialect |
| `board` | `flash` {`sketch`, `fqbn`}, `expect` {`hello`} | a board at a node, or on a `port` no node has yet. A node's own sketch is the one meant when none is named |

Each keeps apothecary's own bounds under the contract:

- **The latch.** Every verb of `machine` but `pause` is refused with its control
  latch down, which a person arms in the Machine window. A delivery never arms it.
- **A held port** is refused while a task writes to it.
- **A refusal changes nothing.** It is answered 422 in the member's words, and the
  audit keeps them.

The work runs after the answer, one piece at a time in the order the cues came, so a
member answers 202 and `GET /<name>/family/state` says what it is working on and how
the last piece ended: `ok`, and its `error` when it failed.

A camera's device is a browser's, so `camera` is a pull member: it stands in the table
as a page's to read.

## Its table

`family.json` in the state folder names the members beside the hub, in the shape
hearth's `from_table` reads. Each key is optional, and with no file there are none.

```json
{"members": {"carlos": "http://127.0.0.1:<its port>"}, "pull": ["a-page"], "timeout": 5}
```

- **`members`** are pushed to at `<url>/family/cue`. A member is on this machine: any
  other address is left out, and the log says so.
- **`pull`** names members with no server, a page that reads its action from the hub.
- **`timeout`** is how long a delivery waits, in seconds.

`serve --carlos URL` adds carlos to the members. The table is read at each use. A
changed table starts a new coordinator, whose audit starts empty, and the audit is
not kept across a restart.

### Members it starts

- **`start`** names a member beside the hub by how it is started, and the hub keeps it
  running with `hearth.supervise`: it knows the member is up when `ready` answers, and
  starts it again when it stops. It is a push member at its `url`, which is on this
  machine.

```json
{"start": {"carlos": {"command": ["carlos", "serve", "--port", "<its port>"],
                      "url": "http://127.0.0.1:<its port>",
                      "cwd": "<its checkout>", "ready": "/family/state"}}}
```

`ready` is the path that answers 200 once it is up, a redirect not counting:
`/family/identity` unless named, for a member that does not keep that route yet. A
member that does not answer it within two minutes is stopped and started again, so a
wrong `ready` restarts a healthy member. `cwd` is optional. `start` is read when the
server starts, each member's output is in `family-logs/` in the state folder, and every
member stops with the server. A member is its own program, as the slicer is, so
this process's guard does not reach it; it is started without the variables that would
redirect a fetch. Its own record of what it reaches is its own repository's.

## A procedure

What the family fires is a step of a procedure, one file under its site in the state
folder, `procedures/<site>/<name>.json`:

```json
{"steps": [
  {"number": "1", "name": "Fit the lead", "discipline": "electrical", "node": "garage:esp32_blink"},
  {"number": "2", "name": "Home the printer", "discipline": "mechanical",
   "node": "garage:printer_1.frame_system.mainboard",
   "notes": "Arm its control in the Machine window first.",
   "waits": {"subject": "garage:printer_1", "property": "state", "value": "idle"},
   "family": {"machine": {"home": {"node": "garage:printer_1.frame_system.mainboard"}}}}
]}
```

- **`discipline`** is what the step touches: mechanical, electrical, firmware, network,
  optical, audio or lighting.
- **`family`** is what each member is handed when the step fires. An empty one is a
  person's own step, and its GO says the person did it.
- **`waits`** is the evidence it waits for: a subject's property at a value, as the log
  last said it.

Every step waits for a person's GO, and only the step standing by fires: the one whose
predecessor has fired, once the evidence it names is in. GO is in the **Procedure**
window, which says how each step stands. It stands beside the world
whenever the site has a procedure, without being asked for, and gives its room back on a site
with none; a window a person closed stays closed, and one a person opened is the person's.
It is also ⊞ Windows › Procedure, in the Family group with **Members**, each member, how it is
reached, its state where the hub started it and its door, and **Deliveries**, the hub's audit,
newest first, each delivery's step, member, status, milliseconds and the instance that took
it. Panels › Windows › Family view lays the three out with the world.
`apothecary serve --demo` starts with one, `bring-up`, on the garage's simulated bench.

The window leads to where each step's work is. A step's node is a door: pressed, the
node's window opens, a machine's or a board's Machine or a camera's Pictures, or the
status line says why it cannot. A step fired opens the section its member works in,
where that Machine is open: a machine's step the Status, a board's flash the Flashing,
its expect the Log; a Machine not open is not opened by a fire. A refused or failed
step keeps the member's words, with the node's door right after them, so a machine's
latch is one press away. A member's name, in Members, is a door too: a member hosted here to the
window of the node its next step names, a member beside the hub to its own page in a
new tab; a pull member leads nowhere. GO never arms a latch.
[Walkthrough page 25](../walkthrough/25-a-procedure-through-the-window.md) pictures it.

| Status | What it means |
|---|---|
| waiting | For the step before it, or for its evidence; `why` says which |
| standing by | GO fires it |
| fired | Delivered, and not finished: a page has not read it, or a member beside the hub answered 202. The next step may go on |
| done | Every member took it, and a hosted member's work has ended well |
| refused | A member refused it, in the words `why` holds. It may be fired again |
| failed | A member is down, is not in the hub's table, or its work failed. It may be fired again |

Each delivery's outcome is kept in the evidence log, `actions/<day>.jsonl`, each naming
its procedure, its step and its node, so a restart leaves what each step did. What a
member says later is read live and is not kept: a page's read of its action, or how
work answered 202 ended, which reads as fired after a restart.

## What goes through it

A procedure's steps, and carlos's holds. A site's wiring sent to carlos, by the
follower, by `POST /sites/{name}/wiring/send` or by a step whose block says `{"carlos":
{"hold": {"wiring": "garage"}}}`, is a delivery through the hub, so it is in the audit.
A carlos named in the table is carlos to all three, as `serve --carlos` names one. `apothecary rig` runs outside the server, where there is no hub, and
sends to carlos directly.

Carlos on its `feat/hold-the-rig` and joe on its `feat/family-control` answer no
`/family/identity` and no `/family/events`, so a delivery to either is kept with no
instance, and `hearth check` says that neither conforms. Each side is its own
repository's to close: [the review](validation/2026-11-05-family-integrations.md), and
[the family's first run](validation/2026-11-05-family-started.md).

## Not built

Everything else the plan orders: a page reading the camera's actions, the reader as a
member hosted here, a step that fires itself, and the corpus's `irl` phase.
