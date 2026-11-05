# 22 — The irl family's hub

**Hermetic.** Everything here runs in this process; nothing opens a port.

A family's members are separate apps, and a hub hands each its part of whatever
fires and keeps what each answered. apothecary is the `irl` family's hub, on the
contract hearth holds. [docs/family.md](../docs/family.md) is the reference, and
`tests/test_family_hub.py` has hearth's own check judge it on a real port.

    >>> import json, os, tempfile
    >>> before = os.environ.get("APOTHECARY_STATE_DIR")
    >>> os.environ["APOTHECARY_STATE_DIR"] = tempfile.mkdtemp()

## What it says it is

    >>> from fastapi.testclient import TestClient
    >>> from apothecary.api import app
    >>> from apothecary.family import hub
    >>> client = TestClient(app)
    >>> said = client.get("/family/identity").json()
    >>> said["hub"], said["family"], said["contract"]
    ('apothecary', 'irl', 'family/1')

With no table it has the family's own members: a machine and a board hosted in its
process, and a camera, whose device is a browser's, read from the page. Its audit is
empty.

    >>> said = client.get("/family/").json()
    >>> {name: member["via"] for name, member in said["members"].items()}
    {'machine': 'local', 'board': 'local', 'camera': 'pull'}
    >>> said["last"]
    []

## Its table

`family.json` in the state folder names the rest. A member is on this machine, so one
elsewhere is left out.

    >>> table = {"members": {"far": "http://192.168.1.4:9"}, "pull": ["a-page"]}
    >>> _ = hub.table_file().write_text(json.dumps(table), encoding="utf-8")
    >>> hub.members()
    ['a-page', 'board', 'camera', 'machine']

## A fire, and what is kept

A pull member is a page with no server, so it needs no port here: it reads its action
from the hub, and that read is the delivery.

    >>> cue = {"number": "1", "name": "Plug the lead", "fired_at": None}
    >>> hub.running().fire(cue, {"a-page": {"show": "plug the lead"}})
    ['a-page']
    >>> client.get("/family/").json()["last"][-1]["done"]
    False
    >>> client.get("/family/members/a-page").json()["action"]
    {'show': 'plug the lead'}
    >>> last = client.get("/family/").json()["last"][-1]
    >>> last["member"], last["via"], last["done"]
    ('a-page', 'pull', True)

A name the table does not hold is kept too, saying where the hub looked, and nothing
is raised for it.

    >>> hub.deliver("nobody", cue, {"show": "anything"})["error"]
    'nobody is not a member in family.json'

## A member of its own

A hosted member keeps the same contract under its own name, and apothecary's bounds
under that. Nothing is pinned here, so the hub's fire is refused, and the refusal is
what the audit keeps.

    >>> client.get("/machine/family/identity").json()["family"]
    'irl'
    >>> hub.deliver("machine", cue, {"home": True})["error"]
    "name the machine's node: none is pinned"

    >>> hub.close()
    >>> _ = os.environ.pop("APOTHECARY_STATE_DIR") if before is None else os.environ.update(APOTHECARY_STATE_DIR=before)
