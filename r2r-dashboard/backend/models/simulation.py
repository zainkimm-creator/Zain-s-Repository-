"""RK4 simulation and CSV export for the R2R validation model."""

from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .controller import CascadePIController, ControllerConfig
from .equations import (
    INPUT_NAMES,
    STATE_NAMES,
    R2RParameters,
    as_named_dict,
    derivatives,
    nominal_state,
    rk4_step,
    validate_vector,
    velocities,
)

ExcitationFn = Callable[[float], Sequence[float]]
DriftFn = Callable[[float, R2RParameters], R2RParameters]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "processed"


@dataclass(frozen=True)
class SimulationConfig:
    """Simulation settings with explicit units."""

    duration_s: float = 6.0
    dt_s: float = 0.001
    controller_sample_time_s: float = 0.010
    log_sample_time_s: float = 0.010
    line_speed_m_s: float = 1.0
    sensor_noise_tension_N: float = 0.0
    sensor_noise_omega_rad_s: float = 0.0
    seed: int = 7
    output_name: str = "simulation.csv"

    def __post_init__(self) -> None:
        for field_name in ("duration_s", "dt_s", "controller_sample_time_s", "log_sample_time_s"):
            value = getattr(self, field_name)
            if value <= 0 or not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite and positive")
        if self.controller_sample_time_s < self.dt_s:
            raise ValueError("controller_sample_time_s must be >= dt_s")
        if self.log_sample_time_s < self.dt_s:
            raise ValueError("log_sample_time_s must be >= dt_s")


@dataclass
class SimulationResult:
    rows: list[dict[str, float]]
    metrics: dict[str, float]
    csv_path: str | None
    xlsx_path: str | None
    equation_sample: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "rows": self.rows,
            "metrics": self.metrics,
            "csv_path": self.csv_path,
            "xlsx_path": self.xlsx_path,
            "equation_sample": self.equation_sample,
        }


def _add_vectors(a: Sequence[float], b: Sequence[float]) -> tuple[float, ...]:
    return tuple(float(a[i]) + float(b[i]) for i in range(len(a)))


def _no_excitation(_: float) -> tuple[float, float, float]:
    return (0.0, 0.0, 0.0)


def _no_drift(_: float, params: R2RParameters) -> R2RParameters:
    return params


def write_csv(rows: Iterable[dict[str, float]], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    row_list = list(rows)
    if not row_list:
        raise ValueError("cannot write empty simulation CSV")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row_list[0].keys()))
        writer.writeheader()
        writer.writerows(row_list)
    return str(path)


def write_simulation_workbook(
    rows: Iterable[dict[str, float]],
    metrics: dict[str, float],
    path: Path,
) -> str:
    """Write simulation data and summary metrics to an Excel workbook."""

    import xlsxwriter

    path.parent.mkdir(parents=True, exist_ok=True)
    row_list = list(rows)
    if not row_list:
        raise ValueError("cannot write empty simulation workbook")

    workbook = xlsxwriter.Workbook(str(path))
    header_format = workbook.add_format(
        {"bold": True, "bg_color": "#E8F1FF", "font_color": "#17324D", "border": 1}
    )
    value_format = workbook.add_format({"num_format": "0.000000", "border": 1})
    text_format = workbook.add_format({"border": 1})

    summary = workbook.add_worksheet("Summary")
    summary.write(0, 0, "metric", header_format)
    summary.write(0, 1, "value", header_format)
    for row_idx, (metric, value) in enumerate(metrics.items(), start=1):
        summary.write(row_idx, 0, metric, text_format)
        summary.write(row_idx, 1, value, value_format)
    summary.set_column(0, 0, 28)
    summary.set_column(1, 1, 18)
    summary.freeze_panes(1, 0)

    data = workbook.add_worksheet("Simulation Data")
    headers = list(row_list[0].keys())
    for col_idx, header in enumerate(headers):
        data.write(0, col_idx, header, header_format)
    for row_idx, row in enumerate(row_list, start=1):
        for col_idx, header in enumerate(headers):
            data.write(row_idx, col_idx, row[header], value_format)
    data.freeze_panes(1, 1)
    data.autofilter(0, 0, len(row_list), len(headers) - 1)
    data.set_column(0, len(headers) - 1, 16)

    workbook.close()
    return str(path)


def compute_metrics(rows: Sequence[dict[str, float]], config: SimulationConfig) -> dict[str, float]:
    if not rows:
        return {}
    target = ControllerConfig(line_speed_m_s=config.line_speed_m_s).target_tension_N
    tension_names = ("T1", "T2", "T3")
    sq_error = []
    max_overshoot = 0.0
    for row in rows:
        for idx, name in enumerate(tension_names):
            err = row[name] - target[idx]
            sq_error.append(err * err)
            max_overshoot = max(max_overshoot, row[name] - target[idx])
    rmse = math.sqrt(sum(sq_error) / len(sq_error))
    effort = math.sqrt(
        sum(row[name] * row[name] for row in rows for name in INPUT_NAMES) / (len(rows) * 3.0)
    )
    settling_band = 0.02 * max(target)
    t90 = rows[-1]["time_s"]
    for row in rows:
        if all(abs(row[name] - target[idx]) <= settling_band for idx, name in enumerate(tension_names)):
            t90 = row["time_s"]
            break
    return {
        "tension_rmse_N": rmse,
        "max_overshoot_N": max_overshoot,
        "t90_s": t90,
        "control_effort_rms_V": effort,
        "samples": float(len(rows)),
        "duration_s": rows[-1]["time_s"],
    }


def simulate(
    params: R2RParameters | None = None,
    controller_config: ControllerConfig | None = None,
    config: SimulationConfig | None = None,
    excitation: ExcitationFn | None = None,
    drift: DriftFn | None = None,
    output_dir: Path | None = None,
    write_output: bool = True,
) -> SimulationResult:
    """Run the closed-loop R2R simulation with RK4 and zero-order-held control."""

    active_config = config or SimulationConfig()
    active_params = replace(params or R2RParameters(), feeder_velocity_m_s=active_config.line_speed_m_s)
    active_controller_config = controller_config or ControllerConfig(
        line_speed_m_s=active_config.line_speed_m_s,
        target_tension_N=active_params.tension_ref_N,
    )
    controller = CascadePIController(active_controller_config)
    excitation_fn = excitation or _no_excitation
    drift_fn = drift or _no_drift
    rng = random.Random(active_config.seed)
    state = nominal_state(active_params, active_config.line_speed_m_s)
    held_inputs = (0.0, 0.0, 0.0)
    rows: list[dict[str, float]] = []
    next_control_s = 0.0
    next_log_s = 0.0
    step_count = int(round(active_config.duration_s / active_config.dt_s))

    for step in range(step_count + 1):
        t_s = step * active_config.dt_s
        current_params = drift_fn(t_s, active_params)
        if t_s + 1e-12 >= next_control_s:
            action = controller.update(
                state,
                active_config.controller_sample_time_s,
                current_params,
            )
            held_inputs = _add_vectors(action.inputs_V, excitation_fn(t_s))
            next_control_s += active_config.controller_sample_time_s

        if t_s + 1e-12 >= next_log_s:
            measured_state = list(validate_vector(state, 6, "state"))
            if active_config.sensor_noise_tension_N:
                for i in range(3):
                    measured_state[i] += rng.gauss(0.0, active_config.sensor_noise_tension_N)
            if active_config.sensor_noise_omega_rad_s:
                for i in range(3, 6):
                    measured_state[i] += rng.gauss(0.0, active_config.sensor_noise_omega_rad_s)
            v_uw, v_nip, v_rw = velocities(measured_state, current_params)
            row = {"time_s": t_s}
            row.update(as_named_dict(measured_state, STATE_NAMES))
            row.update(as_named_dict(held_inputs, INPUT_NAMES))
            row.update({"v_UW_m_s": v_uw, "v_Nip_m_s": v_nip, "v_RW_m_s": v_rw})
            rows.append(row)
            next_log_s += active_config.log_sample_time_s

        if step < step_count:
            state = rk4_step(state, held_inputs, active_config.dt_s, current_params)

    equation_state = [rows[0][name] for name in STATE_NAMES]
    equation_inputs = [rows[0][name] for name in INPUT_NAMES]
    equation_sample = as_named_dict(derivatives(equation_state, equation_inputs, active_params), STATE_NAMES)
    metrics = compute_metrics(rows, active_config)

    csv_path = None
    xlsx_path = None
    if write_output:
        target_dir = output_dir or DEFAULT_DATA_DIR
        csv_target = target_dir / active_config.output_name
        csv_path = write_csv(rows, csv_target)
        xlsx_path = write_simulation_workbook(rows, metrics, csv_target.with_suffix(".xlsx"))

    return SimulationResult(
        rows=rows,
        metrics=metrics,
        csv_path=csv_path,
        xlsx_path=xlsx_path,
        equation_sample=equation_sample,
    )


def write_json(payload: dict[str, object], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)
