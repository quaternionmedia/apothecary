# The family's hub

apothecary is the `irl` family's hub: it runs hearth's coordinator, so a member of
the family is handed its part of whatever fires and every outcome is kept.
[hearth](https://github.com/quaternionmedia/hearth) holds the contract, `family/1`,
and the coordinator, imported from `qm-hearth`, never copied.
[Walkthrough page 22](../walkthrough/22-the-irl-hub.md) runs it;
[the plan](plans/irl-hub-2026-11-02.md) is what is built on it next.

## What it answers

| Route | Answer |
|---|---|
| `GET /family/identity` | What the hub is: `apothecary`, of `irl`, the contract it keeps, the conformance version it replayed, this running instance |
| `GET /family/` | Each member, how it is reached, and each recent delivery's outcome: status, error, milliseconds from the fire, the instance that took it |
| `GET /family/members/<name>` | A pull member's last cue and action |
| `GET /family/members/<name>/events` | The same, as a stream |
| `/machine/family/*`, `/board/family/*` | A hosted member's own four routes |

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

## What goes through it

Carlos's holds. A site's wiring sent to carlos, by the follower or by
`POST /sites/{name}/wiring/send`, is a delivery through the hub, so it is in the
audit. `apothecary rig` runs outside the server, where there is no hub, and sends to
carlos directly.

Carlos on its `feat/hold-the-rig` answers no `/family/identity` and no
`/family/events`, so a delivery to it is kept with no instance, and `hearth check`
says that carlos does not conform. Its side is carlos's to close:
[the review](validation/2026-11-05-family-integrations.md).

## Not built

Everything else the plan orders: steps on the blueprint and their GO, a page reading
the camera's actions, the reader as a member hosted here, and the corpus's `irl`
phase. Nothing but a delivery of carlos's fires yet.
