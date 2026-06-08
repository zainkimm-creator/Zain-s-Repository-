"""One-step prediction-error system identification for the seven paper parameters."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from backend.models.equations import (
    INPUT_NAMES,
    PARAMETER_NAMES,
    R2RParameters,
    STATE_NAMES,
    roller_tension_differences,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUMMARY_DIR = PROJECT_ROOT / "reports" / "validation_summary"


@dataclass
class SysIDResult:
    estimates: dict[str, float]
    rmse_theta: float
    error_table: list[dict[str, float | str]]
    summary_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "estimates": self.estimates,
            "RMSE_theta": self.rmse_theta,
            "error_table": self.error_table,
            "summary_path": self.summary_path,
        }


def load_rows_from_csv(path: str | Path) -> list[dict[str, float]]:
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [{key: float(value) for key, value in row.items()} for row in reader]


def _solve_2x2(a11: float, a12: float, a22: float, b1: float, b2: float) -> tuple[float, float]:
    det = a11 * a22 - a12 * a12
    if abs(det) < 1e-12:
        raise ValueError("ill-conditioned 2x2 normal equation")
    return ((b1 * a22 - b2 * a12) / det, (a11 * b2 - a12 * b1) / det)


def _safe_relative_error(estimate: float, truth: float) -> float:
    denom = abs(truth) if abs(truth) > 1e-12 else 1.0
    return (estimate - truth) / denom


def _time_steps(rows: Sequence[Mapping[str, float]]) -> list[float]:
    return [rows[i + 1]["time_s"] - rows[i]["time_s"] for i in range(len(rows) - 1)]


def estimate_parameters(
    rows: Sequence[Mapping[str, float]],
    nominal_params: R2RParameters | None = None,
    true_params: R2RParameters | None = None,
    summary_name: str | None = "sysid_result.json",
    summary_dir: Path | None = None,
) -> SysIDResult:
    """Estimate `kt_UW`, `kt_Nip`, `kt_RW`, `kf_UW`, `kf_Nip`, `kf_RW`, and `EA`.

    The estimator uses one-step finite-difference prediction equations. For roller
    dynamics, each roller solves a two-parameter least-squares problem in the
    paper Eq. (6) ratio form:

        dv_i = kt_i*(T_{i+1}-T_i + k_motor_i*u_i/R_i) - kf_i*v_i

    For tension dynamics, all three spans share one least-squares estimate of EA
    derived from paper Eq. (1):

        dT_i - (T_{i-1}v_{i-1} - T_i v_i)/L_i = EA*(v_i - v_{i-1})/L_i
    """

    if len(rows) < 3:
        raise ValueError("at least 3 logged rows are required for SysID")
    params = nominal_params or R2RParameters()
    true = true_params or params
    dt_values = _time_steps(rows)
    if any(dt <= 0 for dt in dt_values):
        raise ValueError("row time_s values must be strictly increasing")

    kt_estimates: list[float] = []
    kf_estimates: list[float] = []
    for roller_idx in range(3):
        a11 = a12 = a22 = b1 = b2 = 0.0
        input_name = INPUT_NAMES[roller_idx]
        radius = params.roller_radius_m[roller_idx]
        motor_gain = params.kt[roller_idx]
        velocity_name = ("v_UW_m_s", "v_Nip_m_s", "v_RW_m_s")[roller_idx]
        for i in range(len(rows) - 1):
            dt = dt_values[i]
            row = rows[i]
            next_row = rows[i + 1]
            velocity = row[velocity_name]
            dv = (next_row[velocity_name] - velocity) / dt
            state = tuple(float(row[name]) for name in STATE_NAMES)
            tension_delta = roller_tension_differences(state)[roller_idx]
            y = dv
            x1 = tension_delta + (motor_gain * row[input_name] / radius)
            x2 = -velocity
            a11 += x1 * x1
            a12 += x1 * x2
            a22 += x2 * x2
            b1 += x1 * y
            b2 += x2 * y
        kt_i, kf_i = _solve_2x2(a11, a12, a22, b1, b2)
        kt_estimates.append(max(1e-6, kt_i))
        kf_estimates.append(max(1e-6, kf_i))

    ea_num = 0.0
    ea_den = 0.0
    span_rows = (
        ("T1", 0, lambda row: (0.0, row["T1"]), lambda row: (params.feeder_velocity_m_s, row["v_UW_m_s"])),
        ("T2", 1, lambda row: (row["T1"], row["T2"]), lambda row: (row["v_UW_m_s"], row["v_Nip_m_s"])),
        ("T3", 2, lambda row: (row["T2"], row["T3"]), lambda row: (row["v_Nip_m_s"], row["v_RW_m_s"])),
    )
    for i in range(len(rows) - 1):
        dt = dt_values[i]
        row = rows[i]
        next_row = rows[i + 1]
        for tension_name, span_idx, tension_pair_fn, speed_pair_fn in span_rows:
            d_tension = (next_row[tension_name] - row[tension_name]) / dt
            t_prev, t_i = tension_pair_fn(row)
            v_prev, v_i = speed_pair_fn(row)
            length = params.span_length_m[span_idx]
            convective = (t_prev * v_prev - t_i * v_i) / length
            y = d_tension - convective
            x = (v_i - v_prev) / length
            ea_num += x * y
            ea_den += x * x
    ea_estimate = ea_num / ea_den if ea_den > 1e-12 else params.EA

    estimates = {
        "kt_UW": kt_estimates[0],
        "kt_Nip": kt_estimates[1],
        "kt_RW": kt_estimates[2],
        "kf_UW": kf_estimates[0],
        "kf_Nip": kf_estimates[1],
        "kf_RW": kf_estimates[2],
        "EA": max(1e-6, ea_estimate),
    }
    error_table: list[dict[str, float | str]] = []
    rel_errors = []
    truth_values = true.sysid_values()
    for name in PARAMETER_NAMES:
        estimate = estimates[name]
        truth = truth_values[name]
        abs_error = estimate - truth
        rel_error = _safe_relative_error(estimate, truth)
        rel_errors.append(rel_error)
        error_table.append(
            {
                "parameter": name,
                "estimate": estimate,
                "truth": truth,
                "absolute_error": abs_error,
                "relative_error": rel_error,
            }
        )
    rmse_theta = math.sqrt(sum(value * value for value in rel_errors) / len(rel_errors))

    summary_path = None
    if summary_name:
        target_dir = summary_dir or DEFAULT_SUMMARY_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / summary_name
        target_path.write_text(
            json.dumps(
                {
                    "estimates": estimates,
                    "RMSE_theta": rmse_theta,
                    "error_table": error_table,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        summary_path = str(target_path)
    return SysIDResult(estimates=estimates, rmse_theta=rmse_theta, error_table=error_table, summary_path=summary_path)
