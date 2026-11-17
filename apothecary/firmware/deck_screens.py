"""What the deck's touch strip shows, one screen at a time, and the swipe that changes it.

``firmware/deck_control.py`` is the layout on a deck; this module is the part of it that
needs no deck, no machine and no clock of its own, so each piece is read and tested from
what it is given:

- **The screens**, in order: ``knobs`` (the strip the layout always drew: which machine,
  its control, where the tool is, the step and what the last turn did), ``progress`` (the
  job the chosen machine is running, or ran last) and ``status`` (the machine's own
  state). ``Screens`` holds which one is showing and moves one along or back; at either
  end a swipe stops and moves nothing, as a page of a book does, so a swipe the same way
  twice never lands where it began.
- **The swipe**, recognised here and nowhere else: ``swipe_of`` reads the strip's touch
  as ``firmware/deck.py`` reports it -- ``{"kind": "drag", "x", "y", "x_out", "y_out"}``,
  where ``x`` and ``y`` are where the finger went down and ``x_out`` and ``y_out`` where
  it came up -- and says forward (the finger moved left, as a page is turned), back, or
  neither. A tap or a long press is neither, and keeps its meaning.
- **What a screen says**, ``progress_strip`` and ``status_strip`` as pure functions of
  the job and the machine's last status. Nothing here states a number the job record or
  the status does not carry: a remaining time is not shown, because neither carries one.

Nothing here sends a line to a machine, asks one for a reading or touches a port.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence, Tuple

KNOBS, PROGRESS, STATUS = "knobs", "progress", "status"
ORDER: Tuple[str, ...] = (KNOBS, PROGRESS, STATUS)

FORWARD, BACK = 1, -1
SWIPE_MIN_PX = 200  # a quarter of the strip's 800: shorter is a slip, not a swipe
READING_FRESH_S = 10.0  # a status older than this is shown with its age

NAME_MAX = 26  # characters of a file's or part's name the strip has room for


def screens_for(kind: str) -> Tuple[str, ...]:
    """The screens of a machine of ``kind`` ("printer" or "router"), in the order a swipe
    walks them. Both have all three: a cut is a job as a print is."""
    return ORDER


def swipe_of(touch: object) -> int:
    """``FORWARD`` or ``BACK`` for the strip's touch if it is a swipe, else 0. A drag of
    at least ``SWIPE_MIN_PX`` along the strip (it is 100 tall, so what is across it never
    outweighs that); a finger moving left is forward."""
    if not isinstance(touch, dict) or touch.get("kind") != "drag":
        return 0
    try:
        dx = int(touch["x_out"]) - int(touch["x"])
    except (KeyError, TypeError, ValueError):
        return 0
    if abs(dx) < SWIPE_MIN_PX:
        return 0
    return FORWARD if dx < 0 else BACK


class Screens:
    """Which of a machine's screens is showing."""

    def __init__(self, order: Sequence[str] = ORDER):
        self.order: Tuple[str, ...] = tuple(order)
        self.index = 0

    @property
    def current(self) -> str:
        return self.order[self.index]

    def swipe(self, direction: int) -> bool:
        """One screen forward (``FORWARD``) or back (``BACK``); False, and nothing moved,
        at the end of the order."""
        wanted = self.index + (1 if direction > 0 else -1)
        if not 0 <= wanted < len(self.order):
            return False
        self.index = wanted
        return True

    def show(self, name: str) -> bool:
        """``name`` brought forward; False when this machine has no such screen."""
        if name not in self.order:
            return False
        self.index = self.order.index(name)
        return True

    def reorder(self, order: Sequence[str]) -> None:
        """A new order, keeping the screen showing when it is still there."""
        kept = self.current
        self.order = tuple(order)
        self.index = self.order.index(kept) if kept in self.order else 0

    @property
    def position(self) -> str:
        return f"{self.index + 1}/{len(self.order)}"


@dataclass(frozen=True)
class Strip:
    """What the strip is drawn with: a big line, a small one under it, a colour and, when
    there is a bar, how full it is (0 to 1)."""

    text: str
    small: Optional[str]
    colour: str
    bar: Optional[float] = None


def clock(seconds: float) -> str:
    """``m:ss``, or ``h:mm:ss`` from the hour."""
    whole = max(0, int(seconds))
    hours, rest = divmod(whole, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"


def _clip(name: str) -> str:
    return name if len(name) <= NAME_MAX else name[: NAME_MAX - 1] + "…"


def _age(status, now: datetime) -> Optional[float]:
    at = getattr(status, "polled_at", None)
    if at is None:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - at).total_seconds())


def job_name(job) -> str:
    """The part a job makes, else the file it ran."""
    part = getattr(job, "part", None)
    return _clip(part.name if part is not None else job.input.name)


# stage -> colour while the job runs: a held or ending job is amber, a plain run blue
_STAGE_COLOUR = {"paused": "amber", "cancelling": "amber", "finishing": "blue"}
_ENDED = {
    "done": ("done", "green"),
    "cancelled": ("cancelled", "amber"),
    "failed": ("failed", "red"),
}


def _said_once(reason: str, word: str) -> str:
    """A job's reason without the word the strip already says before it: a host's cancel
    is recorded "cancelled; heaters and fan off, motors free", which the strip would say
    as "cancelled (cancelled; ...)"."""
    if reason.lower().startswith(word):
        return reason[len(word) :].lstrip(" ;:,-")
    return reason


def progress_strip(machine: str, job, status, now: datetime, position: str) -> Strip:
    """The Progress screen of ``machine``: ``job`` is the host's job record (a print, a
    cut) as it stands, running or ended, or None; ``status`` the machine's newest poll,
    whose card print is shown when no job of the host's is. The elapsed time is the job's
    own, from when it began; no remaining time is shown, since no record carries one."""
    if job is not None:
        percent = int(round(job.progress * 100))
        elapsed = ((job.finished_at or now) - job.started_at).total_seconds()
        if job.running:
            stage = str(job.detail.get("stage") or "running")
            colour = _STAGE_COLOUR.get(stage, "blue")
            small = f"{machine} · {stage} · elapsed {clock(elapsed)} · {position}"
        else:
            word, colour = _ENDED.get(job.outcome, (job.outcome, "grey"))
            reason = _said_once(job.reason or "", word)
            why = f" ({reason})" if reason and job.outcome != "done" else ""
            small = f"{machine} · {word}{why} after {clock(elapsed)} · tap to clear · {position}"
        return Strip(
            f"{job_name(job)} · {percent}%", small, colour, max(0.0, min(1.0, job.progress))
        )
    if getattr(status, "sd_printing", False) and status.sd_progress is not None:
        small = f"{machine} · from the card"
        if status.print_time_s is not None:
            small += f" · elapsed {clock(status.print_time_s)}"
        return Strip(
            f"card print · {int(round(status.sd_progress * 100))}%",
            f"{small} · {position}",
            "blue",
            max(0.0, min(1.0, status.sd_progress)),
        )
    return Strip(f"{machine} · no job", f"nothing is printing or cutting · {position}", "grey")


def _heat(name: str, heater) -> str:
    if heater is None:
        return f"{name} -"
    target = f"/{heater.target:g}" if heater.target > 0 else " off"
    return f"{name} {heater.actual:.0f}{target}"


def needs(status) -> Optional[str]:
    """The first thing the machine asks of a person: what ``todo`` lists first, else its
    alarm in the dialect's words."""
    todo = getattr(status, "todo", None) or []
    if todo:
        return str(todo[0])
    alarm = getattr(status, "alarm", None)
    if alarm is not None:
        return str(getattr(status, "alarm_text", None) or f"alarm {alarm}")
    return None


def status_strip(machine: str, kind: str, status, now: datetime, position: str) -> Strip:
    """The Status screen of ``machine``: its state; a printer's hotends and bed, or a
    router's spindle and feed; and the first thing it needs of a person. Read from the
    newest poll, its age said when it is old: a deck that asks a machine nothing mid-job
    shows the last reading anyone's poll made."""
    if status is None:
        return Strip(f"{machine} · no reading", f"not polled yet · {position}", "grey")
    if kind == "printer":
        hotends = ", ".join(_heat("hotend", h) for h in status.hotends) or "hotend -"
        numbers = f"{hotends} · {_heat('bed', status.bed)}"
    else:
        spindle = getattr(status, "spindle", None)
        speed = f"{spindle.rpm:.0f} rpm" if spindle is not None and spindle.on else "off"
        feed = getattr(status, "feed", None)
        numbers = f"spindle {speed} · feed {feed:g}" if feed is not None else f"spindle {speed}"
    need = needs(status)
    parts = [numbers]
    if need:
        parts.append(need)
    age = _age(status, now)
    if age is not None and age > READING_FRESH_S:
        parts.append(f"read {clock(age)} ago")
    parts.append(position)
    if need and (status.state == "alarm" or getattr(status, "alarm", None) is not None):
        colour = "red"
    elif need:
        colour = "amber"
    elif status.state in ("printing", "running"):
        colour = "green"
    else:
        colour = "grey"
    return Strip(f"{machine} · {status.state}", " · ".join(parts), colour)


def held_strip(machine: str, kind: str, words: str, position: str) -> Strip:
    """The knobs screen of a machine a job holds: not live. ``words`` is what the server
    itself says when it refuses a jog (``PortHeld``). A cut still takes a spindle speed,
    which the dialect lets through; a print takes nothing from the knobs."""
    can = "knob 4 still turns the spindle" if kind == "router" else "no knob moves it"
    return Strip(f"{machine} · held", f"{words} · jogs refused, {can}", "amber")
