"""``/jobs``: what the machines here ran, of every kind (``apothecary/jobs.py``).

A job is started by its machine's own route -- ``POST /firmware/printers/print``
for a print, from the Print card -- and never here. These read:

- ``GET /jobs?site=&machine=&kind=``: jobs, the running ones first, then the
  newest: a site's (Site's Jobs section), a machine's (the Print card's history;
  the port's board is looked up, so a printer whose port number moved keeps its
  history), a kind's. Without what each machine said.
- ``GET /jobs/choices?machine=``: what a job started on the machine on a port
  would record -- the kind of machine and what that kind offers, where it is
  pinned, and the parts and pieces of that site a job there can name as the
  part it makes. The Print card's part drop-down is filled from it.
- ``GET /jobs/{id}``: one job, with the tail of what its machine said.

Plain ``def``: each reads the state folder, and looking a port's board up may
scan the ports.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import jobs
from ..firmware import devices
from ..firmware.models import Port

router = APIRouter(prefix="/jobs", tags=["jobs"])

SITE_NAME = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
KIND = r"^[a-z][a-z0-9_-]{0,31}$"


class MachineChosen(BaseModel):
    kind: Optional[str] = None  # the kind of machine, when the board is one
    port: str
    identity: Optional[str] = None
    path: Optional[str] = None  # the node its port is pinned to


class Offered(BaseModel):
    kind: str
    label: str
    inputs: List[str]


class JobChoices(BaseModel):
    machine: MachineChosen
    site: Optional[str] = None
    operations: List[Offered]
    parts: List[jobs.JobPart]


def _identity(port: str) -> Optional[str]:
    board = devices.known_device(port)
    return board.identity if board is not None else None


@router.get("", response_model=List[jobs.JobFacts])
def list_jobs(
    site: Annotated[Optional[str], Query(pattern=SITE_NAME, description="the site's jobs")] = None,
    machine: Annotated[
        Port | Literal[""], Query(description="the jobs of the machine on this port")
    ] = "",
    kind: Annotated[Optional[str], Query(pattern=KIND, description="the jobs of this kind")] = None,
):
    """Jobs, the running ones first, then the newest first."""
    if kind is not None and jobs.operation(kind) is None:
        kinds = ", ".join(op.kind for op in jobs.operations())
        raise HTTPException(
            status_code=422, detail=f"no machine offers {kind!r}; the kinds are {kinds}"
        )
    found = jobs.list_jobs(
        site=site,
        machine=machine or None,
        identity=_identity(machine) if machine else None,
        kind=kind,
    )
    return [job.model_dump(mode="json", exclude={"log"}) for job in found]


@router.get("/choices", response_model=JobChoices)
def job_choices(machine: Annotated[Port, Query(description="the port of the machine")]):
    """What a job started on this machine would record, and what it may name."""
    board = devices.known_device(machine)
    kind = devices.machine_kind(board)
    place = jobs.place_of(machine)
    return JobChoices(
        machine=MachineChosen(
            kind=kind,
            port=machine,
            identity=board.identity if board is not None else None,
            path=place.path if place is not None else None,
        ),
        site=place.site if place is not None else None,
        operations=[
            Offered(kind=op.kind, label=op.label, inputs=list(op.inputs))
            for op in (jobs.operations(kind) if kind else [])
        ],
        parts=place.parts if place is not None else [],
    )


@router.get("/{job_id}", response_model=jobs.Job)
def get_job(job_id: str):
    """One job, with the tail of what its machine said."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="no such job")
    return job
