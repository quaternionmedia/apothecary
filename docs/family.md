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

`hearth check` judges it from outside, by these routes alone:

```bash
uv run apothecary serve --demo
uv run hearth check --hub http://127.0.0.1:6283
```

`tests/test_family_hub.py` replays the same check against a real port, and pins the
version of hearth's vector set it replayed.

## Its table

`family.json` in the state folder names the members, in the shape hearth's
`from_table` reads. Each key is optional, and with no file the hub has no members.

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

Everything else the plan orders: steps on the blueprint and their GO, the printer, a
board, a camera and the reader as members hosted here, and the corpus's `irl` phase.
Nothing but a delivery of carlos's fires yet.
