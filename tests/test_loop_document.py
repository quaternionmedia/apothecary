"""A machine's control loop as one document (``apothecary.loop_document``, ``control/loop/1``).

The contract: five group ids, open keys, finite values, and every figure resting on a part
the document carries -- a measured or identified figure on one of its experiments, a
computed one on its plant or one of its controllers. The builder's figures are
``apothecary.control_loops``'s on the parts the document carries; the Markdown view rounds
and recomputes nothing.
"""

from __future__ import annotations

import functools
import json

import pytest
from pydantic import ValidationError

from apothecary import control_loops as cl
from apothecary.loop_document import (
    SCHEMA,
    Controller,
    Experiment,
    Figure,
    LoopDocument,
    LoopName,
    Machine,
    Samples,
    build,
    curves,
    figures,
    format_value,
    gains_of,
    load_document,
    now,
    plant_model,
    render_markdown,
    samples_from_columns,
)

HEATER = cl.FOPDT(2.0, 60.0, 8.0)  # made up: no machine's


def _built() -> LoopDocument:
    return LoopDocument.model_validate_json(_built_once())


@functools.lru_cache(maxsize=1)
def _built_once() -> str:
    """A closed-loop step of a simulated heater, its plant fitted, a controller designed
    by SIMC, the board's own gains read, and the figures that follow."""
    pid = cl.PID(kp=1.875, ki=0.03125, dt=1.0)
    trace = cl.closed_loop(HEATER, pid, lambda s: 200.0 if s < 60 else 205.0, 600, ambient=25.0)
    step = Experiment(
        id="step-1",
        kind="step",
        started_at=now(),
        sample_period_s=1.0,
        ceiling_c=215.0,
        max_duration_s=900.0,
        samples=Samples(t=trace.t, target=trace.r, actual=trace.y, power=trace.u),
    )
    read = Experiment(
        id="read-1",
        kind="read",
        started_at=now(),
        sample_period_s=1.0,
        lines=["echo:  M301 P1.875 I0.03125 D0.00"],
    )
    found = cl.fit_fopdt(trace.u, trace.y, 1.0)
    designed = cl.design("simc", plant=found.plant, kind="pi", dt=1.0)
    doc = LoopDocument(
        generated_at=now(),
        machine=Machine(kind="printer", port="/dev/ttySIM", simulated=True),
        loop=LoopName(heater="hotend", index=0),
        units={"temperature": "°C", "time": "s", "power": "PWM count"},
        experiments=[step, read],
        plant=plant_model(found, "step-1", ambient=found.initial),
        controller=Controller(
            designed=gains_of(designed.pid, "computed", "plant", rule="simc"),
            on_machine=gains_of(pid, "measured", "read-1"),
        ),
    )
    doc.groups = figures(doc, step_of="step-1", step_time=60.0)
    return LoopDocument.model_validate(doc.model_dump(by_alias=True)).model_dump_json(by_alias=True)


class TestTheDocument:
    def test_a_built_document_carries_each_figure_with_its_basis(self):
        doc = _built()
        assert doc.schema_ == SCHEMA
        assert doc.get("plant.gain").value == pytest.approx(2.0, rel=1e-6)
        assert (
            doc.get("plant.gain").basis == "identified" and doc.get("plant.gain").source == "step-1"
        )
        assert doc.get("controller.kp_on_machine").basis == "measured"
        assert doc.get("controller.kp_designed").basis == "computed"
        pm = doc.get("loop.phase_margin_designed")
        assert pm.basis == "computed" and pm.source == "plant+controller.designed"
        assert doc.get("response.overshoot").basis == "measured"
        assert {g.id for g in doc.groups} == {
            "plant",
            "controller",
            "loop",
            "response",
            "experiment",
        }

    def test_the_figures_are_the_maths_on_the_parts_carried(self):
        """The builder's margins are ``control_loops``'s for the plant and gains the
        document carries, read back from it, not from anywhere else."""
        doc = _built()
        m = cl.loop_margins(cl.Loop(doc.plant.plant(), doc.controller.designed.pid()))
        assert doc.get("loop.phase_margin_designed").value == pytest.approx(m.phase_margin)
        assert doc.get("loop.ms_designed").value == pytest.approx(m.ms)

    def test_the_schema_key_keeps_its_name(self):
        dumped = _built().model_dump(by_alias=True)
        assert dumped["schema"] == SCHEMA and "schema_" not in dumped

    @pytest.mark.parametrize(
        "mutate, says",
        [
            (lambda d: d.update(schema="control/loop/0"), "schema"),
            (lambda d: d["groups"].append({"id": "thermal", "figures": []}), "groups"),
            (lambda d: d["groups"].append({"id": "plant", "figures": []}), "duplicate groups"),
            (
                lambda d: d["groups"][0]["figures"].append(dict(d["groups"][0]["figures"][0])),
                "duplicate figure",
            ),
            (lambda d: d["groups"][0]["figures"][0].update(key="Bad Key"), "pattern"),
            (lambda d: d["groups"][0]["figures"][0].update(source="step-9"), "no experiment"),
            (
                lambda d: d["groups"][2]["figures"][0].update(source="plant+controller.guessed"),
                "not one of",
            ),
            (lambda d: d["controller"]["on_machine"].update(basis="computed"), "measured"),
            (lambda d: d["controller"].update(designed=None), "lacks"),
            (lambda d: d["experiments"][0]["samples"]["t"].pop(), "one length"),
            (lambda d: d["experiments"][0].update(samples=None), "carries its samples"),
            (lambda d: d["experiments"][1].update(lines=[]), "lines the board answered"),
            (lambda d: d["experiments"].append(dict(d["experiments"][1])), "duplicate experiments"),
            (lambda d: d["machine"].update(kind="router"), "machine"),
            (lambda d: d.pop("generated_at"), "generated_at"),
        ],
        ids=[
            "schema",
            "unknown-group",
            "duplicate-group",
            "duplicate-key",
            "bad-key",
            "measured-from-nothing",
            "computed-from-nothing",
            "board-gains-not-measured",
            "computed-from-a-missing-part",
            "samples-of-two-lengths",
            "no-samples-no-job",
            "a-read-with-no-lines",
            "duplicate-experiment",
            "not-a-printer",
            "no-timestamp",
        ],
    )
    def test_a_document_off_the_contract_is_refused(self, mutate, says):
        bad = json.loads(json.dumps(_built().model_dump(by_alias=True)))
        assert [g["id"] for g in bad["groups"]][:3] == ["plant", "controller", "loop"]
        mutate(bad)
        with pytest.raises(ValidationError, match=says):
            LoopDocument.model_validate(bad)

    def test_a_value_that_is_not_finite_is_refused(self):
        with pytest.raises(ValidationError, match="finite"):
            Figure(key="a", label="a", value=float("nan"), basis="computed", source="plant")
        with pytest.raises(ValidationError, match="finite"):
            Samples(t=[0.0], target=[1.0], actual=[float("inf")], power=[None])

    def test_a_document_loads_from_a_file(self, tmp_path):
        p = tmp_path / "loop.json"
        p.write_text(json.dumps(_built().model_dump(by_alias=True)), encoding="utf-8")
        assert load_document(p).loop.label == "hotend 0"


class TestTheView:
    def test_the_markdown_rounds_for_display_and_says_each_basis(self):
        doc = _built()
        md = render_markdown(doc)
        assert md.startswith("# Control loop: hotend 0")
        assert "(simulated)" in md and "## Experiments" in md and "## Loop (from the model)" in md
        assert (
            "| gain (`plant.gain`) | 2 °C per power unit | identified | `step-1` | fit_fopdt |"
            in md
        )
        assert "| `read-1` | read | done |" in md

    def test_a_value_is_shown_by_its_size(self):
        def f(v, u=""):
            return Figure(key="a", label="a", value=v, unit=u, basis="computed", source="plant")

        assert format_value(f(61.35211, "°")) == "61.4 °"
        assert format_value(f(0.00012, "rad/s")) == "1.200e-04 rad/s"
        assert format_value(f(None)) == "—"

    def test_samples_read_from_columns(self):
        rows = [
            {"t": "0", "target": "200", "actual": "199.5", "power": ""},
            {"t": "1", "target": "200", "actual": "199.9", "power": "80"},
        ]
        s = samples_from_columns(rows)
        assert s.power == [None, 80.0]
        with pytest.raises(ValueError, match="columns"):
            samples_from_columns([{"t": "0"}])


class TestTheBuilder:
    """``build``: one experiment's samples to a document, its figures computed on them."""

    def _experiment(self, kind, setpoint, duration, **params):
        pid = cl.design("simc", plant=HEATER, kind="pi", dt=0.1).pid
        tr = cl.closed_loop(HEATER, pid, setpoint, duration, ambient=25.0, sample=1.0)
        return Experiment(
            id=f"{kind}-1",
            kind=kind,
            started_at=now(),
            sample_period_s=1.0,
            parameters=params,
            samples=Samples(t=tr.t, target=tr.r, actual=tr.y, power=tr.u),
        )

    def test_a_step_is_fitted_designed_for_and_measured(self):
        exp = self._experiment("step", lambda s: 200.0 if s < 300.5 else 205.0, 900, settle_s=300.0)
        doc = build(
            exp, Machine(kind="printer", port="(a recorded file)"), LoopName(heater="hotend")
        )
        assert doc.plant.gain == pytest.approx(2.0, rel=0.02)
        assert doc.controller.designed.rule == "simc" and doc.controller.designed.dt is None
        assert doc.get("response.steady_error").value == pytest.approx(0.0, abs=0.05)
        assert doc.get("plant.time_constant").basis == "identified"

    def test_a_perturbation_carries_its_frequency_response(self):
        def square(s):
            if s < 600.5:
                return 200.0
            return 200.0 + (2.0 if ((s - 600.5) % 120) < 60 else -2.0)

        exp = self._experiment(
            "perturbation", square, 600 + 120 * 5, settle_s=600.0, period_s=120.0
        )
        doc = build(exp, Machine(kind="printer", port="x"), LoopName(heater="hotend"))
        first = doc.frequency[0]
        assert first.segments == 4 and first.trust == "good"
        assert first.magnitude == pytest.approx(abs(HEATER.response(first.frequency)), rel=0.03)
        assert render_markdown(doc).count("## Frequency response") == 1

    def test_an_autotune_s_own_gains_are_the_designed_controller(self):
        exp = self._experiment("autotune", lambda s: 200.0, 120)
        doc = build(
            exp,
            Machine(kind="printer", port="x"),
            LoopName(heater="bed"),
            autotune={"kp": 19.15, "ki": 1.52, "kd": 60.49, "ku": 31.9, "tu": 25.3},
        )
        assert doc.plant is None  # a relay names a point of the plant, not the plant
        g = doc.controller.designed
        assert (g.kp, g.basis, g.rule, g.parameters["tu"]) == (
            19.15,
            "identified",
            "firmware_autotune",
            25.3,
        )


class TestTheCurves:
    def test_a_page_s_curves_are_computed_here_from_the_document(self):
        """The model's step through the experiment's own targets, beside what was
        measured: with the plant the data came from it lies on the measurement, to the
        noise-free record's own hundredths; and the open loop over frequency."""
        doc = _built()
        drawn = curves(doc)
        step = drawn["step"]
        assert len(step["measured"]) == len(step["t"]) and "model_designed" in step
        pid = doc.controller.on_machine
        assert pid.kp == 1.875
        error = max(
            abs(a - b) for a, b in zip(step["model_on_machine"], step["measured"], strict=False)
        )
        assert error < 0.1
        assert set(drawn["bode"]) == {"designed", "on_machine"}
        assert drawn["model_pid_dt"] == 0.1
        assert (
            curves(
                LoopDocument.model_validate(
                    {**doc.model_dump(by_alias=True), "plant": None, "groups": [], "controller": {}}
                )
            )["step"]
            is None
        )
