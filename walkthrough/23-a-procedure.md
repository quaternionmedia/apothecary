# 23 — A procedure

**Hermetic.** Everything here runs in this process; nothing opens a port.

What the irl family fires is a step of a procedure: the steps that bring a site's
blueprint into working order, each sitting on a node and carrying what each member is
handed when it fires. A step waits for a person's GO. [docs/family.md](../docs/family.md)
is the reference, and `tests/test_family_procedures.py` runs the same with a machine
and a board on the simulated bench. [Page 25](25-a-procedure-through-the-window.md) is
the same procedure through the page's Procedure window, pictured step by step.

    >>> import os, tempfile
    >>> before = os.environ.get("APOTHECARY_STATE_DIR")
    >>> os.environ["APOTHECARY_STATE_DIR"] = tempfile.mkdtemp()

    >>> from datetime import datetime, timezone
    >>> from fastapi.testclient import TestClient
    >>> from apothecary.api import app
    >>> from apothecary.evidence import log
    >>> from apothecary.evidence.observation import By, Observation, Origin
    >>> from apothecary.family import hub
    >>> client = TestClient(app)

## Its steps

Each step has a number, a name and a discipline, and may sit on a node. Here a person
fits a lead, the machine is homed, a camera keeps a frame, and joe says something.

    >>> printer = "garage:printer_1"
    >>> steps = [
    ...     {"number": "1", "name": "Fit the lead", "discipline": "electrical",
    ...      "node": "garage:esp32_blink"},
    ...     {"number": "2", "name": "Home the printer", "discipline": "mechanical",
    ...      "waits": {"subject": printer, "property": "state", "value": "idle"},
    ...      "family": {"machine": {"home": True}}},
    ...     {"number": "3", "name": "Keep a frame", "discipline": "optical",
    ...      "family": {"camera": {"keep": {"frame": True}}}},
    ...     {"number": "4", "name": "Say it is ready", "discipline": "audio",
    ...      "family": {"joe": {"say": {"text": "ready"}}}},
    ... ]
    >>> route = "/sites/garage/procedures/bring-up"
    >>> board = client.put(route, json={"steps": steps}).json()
    >>> def stands(board):
    ...     return [(step["number"], step["status"]) for step in board["steps"]]
    >>> stands(board)
    [('1', 'standing by'), ('2', 'waiting'), ('3', 'waiting'), ('4', 'waiting')]

Nothing fires itself, and only the step standing by fires at all.

    >>> answer = client.post(f"{route}/steps/2/go")
    >>> answer.status_code, answer.json()["detail"]
    (409, 'waiting for step 1')

## A person's own step

A step with nothing for any member is a person's: its GO says the person did it.

    >>> board = client.post(f"{route}/steps/1/go").json()
    >>> stands(board)[:2]
    [('1', 'done'), ('2', 'waiting')]

## The evidence a step waits for

The next waits on what the log says of the printer, not only on the step before it.

    >>> board["steps"][1]["why"]
    "waiting for garage:printer_1's state to be idle: it is nothing yet"
    >>> now = datetime.now(timezone.utc)
    >>> log.write("garage", [Observation(subject=printer, property="state", value="idle",
    ...     origin=Origin(kind="measured", by=By(name="a poll")), at=now, recorded_at=now)])
    >>> stands(client.get(route).json())[1]
    ('2', 'standing by')

## A member's refusal

The step fires through the hub, so what a member answers is what the step says. No
machine is pinned here, and a refused step changes nothing and holds the next.

    >>> board = client.post(f"{route}/steps/2/go").json()
    >>> second = board["steps"][1]
    >>> second["status"], second["why"], second["can_go"]
    ('refused', "name the machine's node: none is pinned", True)
    >>> stands(board)[2]
    ('3', 'waiting')

Rewritten as a person's own step, it goes on. The refusal stays in the log, and a
step's last fire is the one that counts.

    >>> steps[1]["family"] = {}
    >>> board = client.put(route, json={"steps": steps}).json()
    >>> board = client.post(f"{route}/steps/2/go").json()
    >>> stands(board)[1:3]
    [('2', 'done'), ('3', 'standing by')]

## A page's member

A camera's device is a browser's, so a page reads what it is to do. Fired, it stands
as fired until one has, which is the delivery.

    >>> board = client.post(f"{route}/steps/3/go").json()
    >>> stands(board)[2:]
    [('3', 'fired'), ('4', 'standing by')]
    >>> client.get("/family/members/camera").json()["action"]
    {'keep': {'frame': True}}
    >>> stands(client.get(route).json())[2]
    ('3', 'done')

## A member that is not there

joe is not in this hub's table. That is a failure, said where the hub looked, and never
a pass.

    >>> fourth = client.post(f"{route}/steps/4/go").json()["steps"][3]
    >>> fourth["status"], fourth["why"]
    ('failed', 'joe is not a member in family.json')

## What is kept

Each delivery's outcome is in the evidence log, beside what it changed.

    >>> [(r["step"], r["member"], r["status"]) for r in log.read("garage", log.ACTIONS).records]
    [('1', None, None), ('2', 'machine', 422), ('2', None, None), ('3', 'camera', None), ('4', 'joe', None)]

Starting over leaves that where it is, and counts none of it.

    >>> stands(client.post(f"{route}/again").json())[0]
    ('1', 'standing by')

    >>> hub.close()
    >>> _ = os.environ.pop("APOTHECARY_STATE_DIR") if before is None else os.environ.update(APOTHECARY_STATE_DIR=before)
