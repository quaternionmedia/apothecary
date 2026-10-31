"""The qmcp client: image models asked through qmcp, only when a person asks.

Configured, never found: ``APOTHECARY_QMCP`` names qmcp, and with it unset (or
``off``) nothing is asked and nothing is probed. ``simulated`` (or ``simulated:<mode>``)
is the in-process qmcp of ``finders/simulated.py``. An address is loopback or
refused. Reaching a qmcp at an address speaks MCP over streamable HTTP, which
waits on MCP on qmcp's own server (qmcp's slice 2) and on the ``qmcp`` extra:
until then such an address is said to be unreachable, and apothecary reads
without it.

Every way the layer can be missing gives the answer apothecary gives without it,
and says which (``STATES``). ``ask`` is the call, run under its own deadline;
``parse`` is the tested half, and refuses a malformed answer whole.
"""

from __future__ import annotations

import os
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from ..evidence.observation import Instance, Observation, Origin, Ref, Region, Sighting, now
from ..evidence.words import COLOURS, MATERIALS
from ..stays_local import is_loopback

ENV = "APOTHECARY_QMCP"
CONTRACT = "qm.vision"
VERSION = 1

# What can be asked, and how long the asker waits for an answer.
PROPERTIES = ("colour", "material", "label", "quantity", "shape", "size", "covered")
DEADLINE_MS = 4000

# Each way qmcp can be there or not, and what apothecary says.
NOT_CONFIGURED = "not configured"
REFUSED_ADDRESS = "refused"
NOT_REACHABLE = "not reachable"
NOT_ANSWERING = "not answering"
NO_MODEL = "no model"
ANSWERING = "answering"
STATES = (NOT_CONFIGURED, REFUSED_ADDRESS, NOT_REACHABLE, NOT_ANSWERING, NO_MODEL, ANSWERING)

Transport = Callable[[str, Dict[str, Any]], Dict[str, Any]]


class Refused(ValueError):
    """An answer apothecary does not take: malformed, or about something not asked."""


class TooLate(TimeoutError):
    """The deadline passed before qmcp answered."""


def configured() -> str:
    return os.environ.get(ENV, "").strip()


def picture_roots() -> List[Path]:
    from ..api import _picture_root

    return [_picture_root()]


class Qmcp:
    """One configured qmcp: its address, how it is reached, and why it cannot be."""

    def __init__(
        self,
        address: str,
        transport: Optional[Transport],
        unreachable: Optional[Tuple[str, str]] = None,
    ):
        self.address = address
        self.transport = transport
        self.unreachable = unreachable  # (state, why) when it cannot be asked at all

    def named(self) -> str:
        """How it is said: the simulated qmcp by its mode, any other by its address."""
        if self.address.startswith("simulated"):
            mode = self.address.partition(":")[2]
            return f"the simulated qmcp ({mode})" if mode else "the simulated qmcp"
        return f"qmcp at {self.address}"

    def call(self, tool: str, arguments: Dict[str, Any], deadline_ms: int) -> Dict[str, Any]:
        """One tool call, given up at the deadline: the call is left to finish on
        its own thread, and nothing it answers afterwards is read."""
        answers: "queue.Queue[Tuple[bool, Any]]" = queue.Queue(maxsize=1)

        def run() -> None:
            try:
                answers.put((True, self.transport(tool, arguments)))
            except BaseException as error:  # handed to the asker, whatever it is
                answers.put((False, error))

        threading.Thread(target=run, name=f"qmcp {tool}", daemon=True).start()
        try:
            ok, answer = answers.get(timeout=deadline_ms / 1000)
        except queue.Empty:
            raise TooLate(f"no answer within {deadline_ms / 1000:g} s") from None
        if not ok:
            raise answer
        return answer


def connect(address: Optional[str] = None) -> Optional[Qmcp]:
    """The qmcp configured, or None when none is."""
    address = configured() if address is None else address.strip()
    if address in ("", "off"):
        return None
    if address == "simulated" or address.startswith("simulated:"):
        from .simulated import SimulatedQmcp

        try:
            simulated = SimulatedQmcp(address.partition(":")[2], roots=picture_roots())
        except ValueError as unknown:
            return Qmcp(address, None, (REFUSED_ADDRESS, str(unknown)))
        return Qmcp(address, simulated.call)
    host = urlparse(address).hostname
    if not host or not is_loopback(host):
        return Qmcp(
            address,
            None,
            (REFUSED_ADDRESS, "it is not on this machine: personal data stays on the device"),
        )
    try:
        import mcp  # noqa: F401  (the qmcp extra)
    except ImportError:
        return Qmcp(address, None, (NOT_REACHABLE, "the qmcp extra is not installed"))
    return Qmcp(
        address,
        None,
        (NOT_REACHABLE, "asking a qmcp over MCP waits on MCP on qmcp's own server"),
    )


def status(address: Optional[str] = None) -> Dict[str, Any]:
    """Whether qmcp is there, and what it has: its state, a sentence saying it,
    and its models."""
    qmcp = connect(address)
    if qmcp is None:
        return {
            "state": NOT_CONFIGURED,
            "address": None,
            "says": f"qmcp is not configured ({ENV})",
            "models": [],
        }
    if qmcp.unreachable:
        state, why = qmcp.unreachable
        return {
            "state": state,
            "address": qmcp.address,
            "says": f"{qmcp.named()}: {why}",
            "models": [],
        }
    try:
        listed = qmcp.call("vision.models", {}, DEADLINE_MS)
    except Exception as down:  # refused, reset, the deadline: qmcp is not answering
        return {
            "state": NOT_ANSWERING,
            "address": qmcp.address,
            "says": f"{qmcp.named()} is not answering ({_why(down)})",
            "models": [],
        }
    models = listed.get("models") if isinstance(listed, dict) else None
    if not isinstance(models, list):
        return {
            "state": NOT_ANSWERING,
            "address": qmcp.address,
            "says": f"{qmcp.named()} answered vision.models malformed",
            "models": [],
        }
    if not models:
        return {
            "state": NO_MODEL,
            "address": qmcp.address,
            "says": f"{qmcp.named()} is answering, with no model",
            "models": [],
        }
    names = ", ".join(f"{m.get('name')} {m.get('version')}" for m in models)
    return {
        "state": ANSWERING,
        "address": qmcp.address,
        "says": f"{qmcp.named()} is answering: {names}",
        "models": models,
    }


def among_for(prop: str, labels: Sequence[str] = ()) -> Optional[List[str]]:
    """The words a property is asked among: the family's for colour and material,
    those built for the question for a label; none for a count or a size."""
    if prop == "colour":
        return list(COLOURS)
    if prop == "material":
        return list(MATERIALS)
    if prop == "label":
        return sorted(set(labels))
    return None


def request(
    picture: Path,
    digest: str,
    taken: str,
    regions: Sequence[Tuple[str, Tuple[float, float, float, float]]],
    asked: Sequence[str],
    labels: Sequence[str] = (),
    deadline_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """``vision.observe``'s arguments: the picture as a path and its digest, the
    regions, and what is asked, each word-answered property with its words."""
    wanted = []
    for prop in asked:
        if prop not in PROPERTIES:
            raise ValueError(f"no property {prop!r}; have {list(PROPERTIES)}")
        one: Dict[str, Any] = {"property": prop}
        words = among_for(prop, labels)
        if words is not None:
            one["among"] = words
        wanted.append(one)
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "picture": {"path": str(picture), "sha256": digest, "taken": taken},
        "regions": [{"id": rid, "box": list(box)} for rid, box in regions],
        "asked": wanted,
        "deadline_ms": deadline_ms or DEADLINE_MS,
    }


def unread_all(req: Dict[str, Any], why: str) -> List[Observation]:
    """What apothecary keeps when nothing could be taken from qmcp: each region's
    every property unread, with one why."""
    out = []
    for region in req["regions"]:
        for asked in req["asked"]:
            out.append(
                Observation(
                    subject=Sighting(
                        sighting=Region(
                            picture=req["picture"]["sha256"],
                            region=region["id"],
                            box=tuple(region["box"]),
                        )
                    ),
                    property=asked["property"],
                    origin=Origin(kind="guessed", by=NO_MODEL_BY),
                    at=req["picture"]["taken"],
                    recorded_at=now(),
                    why=why,
                    apothecary=Instance(trusted=False),
                )
            )
    return out


# What answered when no model did: qmcp, by its tool.
NO_MODEL_BY = {"name": "qmcp", "tool": "vision.observe"}


def _evidence(raw: Any) -> Ref:
    """qmcp's reference, in the instance's kinds: a picture's region, or the
    invocation the call wrote in qmcp."""
    if isinstance(raw, dict) and "picture" in raw:
        return Ref(kind="picture", id=raw["picture"], path=raw.get("path"), box=raw.get("box"))
    if isinstance(raw, dict) and "qmcp_invocation" in raw:
        return Ref(kind="invocation", id=str(raw["qmcp_invocation"]))
    raise ValueError(f"evidence that is neither a picture nor an invocation: {raw!r}")


def _from_qmcp(raw: Any) -> Observation:
    """One of qmcp's observations, in ``qm.observation``, as apothecary keeps it:
    ``by`` a record named for the model (``qmcp`` when none answered), its evidence
    in the instance's kinds, and not trusted."""
    if not isinstance(raw, dict):
        raise ValueError("an observation is an object")
    raw = {k: v for k, v in raw.items() if k != "apothecary"}
    origin = raw.get("origin") or {}
    by = origin.get("by") or {}
    engine = by.get("engine")
    raw["origin"] = {
        "kind": origin.get("kind"),
        "by": {
            "name": by.get("model") or "qmcp",
            "version": by.get("version"),
            "weights_sha256": by.get("weights_sha256"),
            "tool": by.get("tool") or NO_MODEL_BY["tool"],
            "engine": engine.get("name") if isinstance(engine, dict) else engine,
        },
    }
    raw["evidence"] = [_evidence(each) for each in raw.get("evidence") or []]
    return Observation.model_validate({**raw, "apothecary": {"trusted": False}})


def parse(result: Any, req: Dict[str, Any]) -> List[Observation]:
    """The observations in qmcp's answer, every one a guess and none trusted, a word
    outside the words asked among made unread with the word. Refuses the answer
    whole when it is not the contract's, names another picture or a region not
    asked about, or leaves a question unanswered."""
    if (
        not isinstance(result, dict)
        or result.get("contract") != CONTRACT
        or result.get("version") != VERSION
    ):
        raise Refused("the answer is not qm.vision version 1")
    if "picture" not in result:
        raise Refused("the answer names no picture")
    if result.get("picture") != req["picture"]["sha256"]:
        raise Refused("the answer is about another picture")
    listed = result.get("observations")
    if not isinstance(listed, list):
        raise Refused("the answer's observations are not a list")
    regions = {r["id"]: tuple(r["box"]) for r in req["regions"]}
    among = {a["property"]: a.get("among") for a in req["asked"]}
    out: List[Observation] = []
    for raw in listed:
        try:
            seen = _from_qmcp(raw)
        except Exception as bad:
            raise Refused(f"an observation does not validate: {_why(bad)}") from None
        if seen.region is None or seen.region.region not in regions:
            raise Refused("the answer names a region not asked about")
        if seen.property not in among:
            raise Refused(f"the answer says {seen.property}, which was not asked")
        if seen.origin.kind != "guessed":
            raise Refused("a model's answer is a guess")
        words = among[seen.property]
        if words is not None and not seen.unread and seen.value not in words:
            seen = seen.model_copy(
                update={
                    "value": None,
                    "unit": None,
                    "confidence": None,
                    "why": f"the model answered {seen.value!r}, which is outside the words asked among",
                }
            )
        out.append(seen)
    answered = {(o.region.region, o.property) for o in out}
    wanted = {(rid, prop) for rid in regions for prop in among}
    if answered != wanted:
        raise Refused("the answer leaves a question unanswered")
    return out


def ask(req: Dict[str, Any], address: Optional[str] = None) -> Tuple[List[Observation], str]:
    """Ask qmcp, and say what happened. Past the deadline every question is unread,
    too late; qmcp missing, not answering or answering malformed leaves nothing
    kept. Either way apothecary reads on without the layer."""
    qmcp = connect(address)
    if qmcp is None:
        return [], f"qmcp is not configured ({ENV}): nothing was asked"
    if qmcp.unreachable:
        return [], f"{qmcp.named()}: {qmcp.unreachable[1]}: nothing was asked"
    try:
        result = qmcp.call("vision.observe", req, req.get("deadline_ms", DEADLINE_MS) + 250)
    except TooLate:
        seconds = req.get("deadline_ms", DEADLINE_MS) / 1000
        return unread_all(
            req, "the deadline passed"
        ), f"{qmcp.named()} did not answer within {seconds:g} s: the call was given up"
    except Exception as down:
        return [], f"{qmcp.named()} is not answering ({_why(down)}): no model answered"
    try:
        seen = parse(result, req)
    except Refused as refused:
        return (
            [],
            f"{qmcp.named()} answered, and the answer was refused, so nothing from it is kept: {refused}",
        )
    read = sum(1 for o in seen if not o.unread)
    return seen, f"{qmcp.named()} answered {read} of {len(seen)}"


def _why(error: BaseException) -> str:
    text = str(error).strip().splitlines()[0] if str(error).strip() else ""
    return text or type(error).__name__
