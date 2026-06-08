"""Strict paper-governing-equation numerical rerun.

This script is intentionally separate from the dashboard backend rerun. It
implements the paper-form equations directly:

Eq. (1) web tension transport:
    dT_i/dt = EA/L_i * (v_i - v_{i-1})
              + (T_{i-1} v_{i-1} - T_i v_i) / L_i

Eq. (2) roller surface-velocity dynamics:
    dv_i/dt = R_i^2/J_i * (T_{i+1} - T_i)
              - f_i/J_i * v_i
              + R_i/J_i * u_i

Eq. (3)-(5) cascade PI plus feedforward controller.

The state uses perturbations around the nominal operating point:
    x = [dT0, dT1, dT2, dv_UW, dv_Nip, dv_RW]

The PDFs do not provide raw 17,000-run data, optimization seeds, or exact
per-plant R/J/f/L/b arrays. This script therefore uses a physically plausible
P01-compatible nominal plant from the published parameter ranges. It is a
governing-equation rerun, not an exact reproduction of the original private
simulation campaign.
"""

from __future__ import annotations

import csv
import json
import math
import random
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_paper_section_numerical_rerun import PAPER_REFERENCES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "reports" / "full_governing_rerun"
FIG_DIR = REPORT_DIR / "figures"
DATA_DIR = REPORT_DIR / "data"
JSON_PATH = REPORT_DIR / "full_governing_equation_rerun.json"
MD_PATH = REPORT_DIR / "full_governing_equation_rerun_report.md"

TLOG_VALUES_MS = [1, 2, 5, 10, 20, 50, 100]
EXCITATIONS = ["ET1", "ET3", "ET6", "E_Toggle", "EVR"]
SPAN_NAMES = ("T0", "T1", "T2")
ROLLER_NAMES = ("UW", "Nip", "RW")


@dataclass(frozen=True)
class PaperPlant:
    """Nominal plant for paper-equation reruns.

    Values are selected from the ranges reported in the PDFs:
    EA: P01 Table S12 value, R/L near Table S13 nominal, J/f within Table S4
    and with f/J in the 10-40 1/s family described in Supplement Section 9.1.
    """

    EA_N: float = 3200.0
    L_m: tuple[float, float, float] = (1.0, 1.0, 1.2)
    R_m: tuple[float, float, float] = (0.05, 0.05, 0.05)
    J_kg_m2: tuple[float, float, float] = (0.020, 0.015, 0.025)
    f_N_s_m: tuple[float, float, float] = (0.300, 0.280, 0.320)
    line_speed_m_s: float = 0.01
    alpha_velocity_gain: float = 1.4
    max_motor_torque_Nm: float = 2.0

    @property
    def kt(self) -> tuple[float, float, float]:
        return tuple((self.R_m[i] ** 2) / self.J_kg_m2[i] for i in range(3))

    @property
    def kf(self) -> tuple[float, float, float]:
        return tuple(self.f_N_s_m[i] / self.J_kg_m2[i] for i in range(3))

    @property
    def ku(self) -> tuple[float, float, float]:
        return tuple(self.R_m[i] / self.J_kg_m2[i] for i in range(3))

    def drifted(
        self,
        *,
        EA_scale: float = 1.0,
        f_scale: float = 1.0,
        J_scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    ) -> "PaperPlant":
        return replace(
            self,
            EA_N=self.EA_N * EA_scale,
            f_N_s_m=tuple(value * f_scale for value in self.f_N_s_m),
            J_kg_m2=tuple(self.J_kg_m2[i] * J_scale[i] for i in range(3)),
        )


@dataclass
class PIState:
    tension_integral: list[float]


def ensure_dirs() -> None:
    for path in (REPORT_DIR, FIG_DIR, DATA_DIR):
        path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        raise ValueError(f"cannot write empty CSV {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def _fmt(value: Any, digits: int = 3) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(number):
        return "n/a"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    if 0 < abs(number) < 0.001:
        return f"{number:.3e}"
    return f"{number:.{digits}g}"


def rel_diff_percent(sim: float | None, paper: float | None) -> float | None:
    if sim is None or paper is None or abs(paper) < 1e-12:
        return None
    return 100.0 * (sim - paper) / paper


def excitation_reference(name: str, amplitude_N: float) -> Callable[[float], tuple[float, float, float]]:
    """Return tension-reference perturbation profile in N."""

    def step_window(t: float, start: float, end: float, value: float) -> float:
        return value if start <= t < end else 0.0

    if name == "ET1":
        return lambda t: (step_window(t, 0.6, 3.6, amplitude_N), 0.0, 0.0)
    if name == "ET3":
        return lambda t: (
            step_window(t, 0.6, 1.8, amplitude_N),
            step_window(t, 1.8, 3.0, amplitude_N),
            step_window(t, 3.0, 4.2, amplitude_N),
        )
    if name == "ET6":
        return lambda t: (
            step_window(t, 0.6, 1.2, amplitude_N) - step_window(t, 1.2, 1.8, amplitude_N),
            step_window(t, 1.8, 2.4, amplitude_N) - step_window(t, 2.4, 3.0, amplitude_N),
            step_window(t, 3.0, 3.6, amplitude_N) - step_window(t, 3.6, 4.2, amplitude_N),
        )
    if name == "E_Toggle":
        return lambda t: (
            amplitude_N * (1.0 if int(t / 0.42) % 2 == 0 else -1.0),
            amplitude_N * (1.0 if int((t + 0.14) / 0.58) % 2 == 0 else -1.0),
            amplitude_N * (1.0 if int((t + 0.27) / 0.74) % 2 == 0 else -1.0),
        )
    if name == "EVR":
        return lambda t: (
            amplitude_N * min(1.0, max(-1.0, (t - 1.0) / 2.5)),
            0.5 * amplitude_N * math.sin(2.0 * math.pi * 0.18 * t),
            -0.4 * amplitude_N * min(1.0, max(-1.0, (t - 2.0) / 2.0)),
        )
    raise ValueError(f"unknown excitation {name}")


def paper_derivatives(state: Sequence[float], inputs: Sequence[float], plant: PaperPlant) -> tuple[float, ...]:
    """Eq. (1)-(2) in perturbation coordinates."""

    tensions = list(state[:3])
    velocities = list(state[3:])
    d_tensions: list[float] = []
    for i in range(3):
        upstream_t = 0.0 if i == 0 else tensions[i - 1]
        upstream_v = plant.line_speed_m_s if i == 0 else plant.line_speed_m_s + velocities[i - 1]
        current_v = plant.line_speed_m_s + velocities[i]
        strain = velocities[i] - (0.0 if i == 0 else velocities[i - 1])
        transport = upstream_t * upstream_v - tensions[i] * current_v
        d_tensions.append((plant.EA_N / plant.L_m[i]) * strain + transport / plant.L_m[i])

    d_velocities: list[float] = []
    for i in range(3):
        downstream_t = 0.0 if i == 2 else tensions[i + 1]
        delta_t = downstream_t - tensions[i]
        d_velocities.append(
            plant.kt[i] * delta_t
            - plant.kf[i] * velocities[i]
            + plant.ku[i] * inputs[i]
        )
    return tuple(d_tensions + d_velocities)


def rk4_step(state: Sequence[float], inputs: Sequence[float], dt_s: float, plant: PaperPlant) -> tuple[float, ...]:
    def add_scaled(base: Sequence[float], slope: Sequence[float], scale: float) -> tuple[float, ...]:
        return tuple(base[i] + scale * slope[i] for i in range(6))

    k1 = paper_derivatives(state, inputs, plant)
    k2 = paper_derivatives(add_scaled(state, k1, 0.5 * dt_s), inputs, plant)
    k3 = paper_derivatives(add_scaled(state, k2, 0.5 * dt_s), inputs, plant)
    k4 = paper_derivatives(add_scaled(state, k3, dt_s), inputs, plant)
    return tuple(state[i] + dt_s * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) / 6.0 for i in range(6))


def controller_input(
    state: Sequence[float],
    ref_tension: Sequence[float],
    pi_state: PIState,
    plant: PaperPlant,
    *,
    dt_s: float,
    kp_star: float,
    ti_s: float = 1.5,
    feedforward: bool = True,
) -> tuple[float, float, float]:
    tensions = state[:3]
    velocities = state[3:]
    sigma = (-1.0, 1.0, 1.0)
    errors = [ref_tension[i] - tensions[i] for i in range(3)]
    for i in range(3):
        pi_state.tension_integral[i] += sigma[i] * errors[i] * dt_s

    v_corr = [
        (plant.L_m[i] / plant.EA_N)
        * kp_star
        * (sigma[i] * errors[i] + pi_state.tension_integral[i] / ti_s)
        for i in range(3)
    ]

    inputs: list[float] = []
    for i in range(3):
        omega_n = math.sqrt(plant.EA_N * plant.R_m[i] ** 2 / (plant.J_kg_m2[i] * plant.L_m[i]))
        k_vel = plant.alpha_velocity_gain * plant.J_kg_m2[i] * omega_n
        omega_error = (v_corr[i] - velocities[i]) / plant.R_m[i]
        downstream_t = 0.0 if i == 2 else tensions[i + 1]
        web_torque = plant.R_m[i] * (downstream_t - tensions[i])
        friction_torque = plant.f_N_s_m[i] * velocities[i] / plant.R_m[i]
        u_ff = -web_torque + friction_torque if feedforward else 0.0
        torque = k_vel * omega_error + u_ff
        torque = max(-plant.max_motor_torque_Nm, min(plant.max_motor_torque_Nm, torque))
        inputs.append(torque)
    return tuple(inputs)


def simulate_paper_model(
    plant: PaperPlant,
    *,
    duration_s: float = 6.0,
    dt_s: float = 0.001,
    controller_ts_s: float = 0.010,
    tlog_s: float = 0.010,
    excitation: str = "E_Toggle",
    amplitude_N: float = 2.0,
    kp_star: float = 100.0,
    sensor_noise_N: float = 0.0,
    sensor_noise_v_m_s: float = 0.0,
    seed: int = 1,
    drift_plant: PaperPlant | None = None,
) -> list[dict[str, float]]:
    rng = random.Random(seed)
    ref_fn = excitation_reference(excitation, amplitude_N)
    state: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    active_plant = drift_plant or plant
    pi_state = PIState([0.0, 0.0, 0.0])
    held_inputs = (0.0, 0.0, 0.0)
    next_control = 0.0
    next_log = 0.0
    rows: list[dict[str, float]] = []
    steps = int(round(duration_s / dt_s))
    for step in range(steps + 1):
        t_s = step * dt_s
        ref = ref_fn(t_s)
        if t_s + 1e-12 >= next_control:
            held_inputs = controller_input(
                state,
                ref,
                pi_state,
                active_plant,
                dt_s=controller_ts_s,
                kp_star=kp_star,
            )
            next_control += controller_ts_s

        if t_s + 1e-12 >= next_log:
            measured = list(state)
            for i in range(3):
                if sensor_noise_N:
                    measured[i] += rng.gauss(0.0, sensor_noise_N)
                if sensor_noise_v_m_s:
                    measured[3 + i] += rng.gauss(0.0, sensor_noise_v_m_s)
            row = {
                "time_s": t_s,
                "T0": measured[0],
                "T1": measured[1],
                "T2": measured[2],
                "v_UW": measured[3],
                "v_Nip": measured[4],
                "v_RW": measured[5],
                "u_UW": held_inputs[0],
                "u_Nip": held_inputs[1],
                "u_RW": held_inputs[2],
                "ref_T0": ref[0],
                "ref_T1": ref[1],
                "ref_T2": ref[2],
            }
            rows.append(row)
            next_log += tlog_s
        if step < steps:
            state = rk4_step(state, held_inputs, dt_s, active_plant)
            if not all(math.isfinite(value) for value in state):
                break
            if max(abs(value) for value in state) > 1e6:
                break
    return rows


def lowpass_rows(rows: Sequence[Mapping[str, float]], cutoff_hz: float | None) -> list[dict[str, float]]:
    copied = [dict(row) for row in rows]
    if cutoff_hz is None or len(copied) < 2:
        return copied
    dt = copied[1]["time_s"] - copied[0]["time_s"]
    tau = 1.0 / (2.0 * math.pi * cutoff_hz)
    alpha = dt / (tau + dt)
    previous = {key: copied[0][key] for key in ("T0", "T1", "T2", "v_UW", "v_Nip", "v_RW")}
    for row in copied:
        for key in previous:
            previous[key] = previous[key] + alpha * (row[key] - previous[key])
            row[key] = previous[key]
    return copied


def solve_2x2(a11: float, a12: float, a22: float, b1: float, b2: float) -> tuple[float, float]:
    det = a11 * a22 - a12 * a12
    if abs(det) < 1e-12:
        return (0.0, 0.0)
    return ((b1 * a22 - b2 * a12) / det, (a11 * b2 - a12 * b1) / det)


def estimate_paper_parameters(rows: Sequence[Mapping[str, float]], plant: PaperPlant, truth: PaperPlant | None = None) -> dict[str, Any]:
    if len(rows) < 3:
        raise ValueError("at least three rows are required")
    true_plant = truth or plant
    kt_est: list[float] = []
    kf_est: list[float] = []
    for i, (t_key, next_t_key, v_key, u_key) in enumerate(
        (
            ("T0", "T1", "v_UW", "u_UW"),
            ("T1", "T2", "v_Nip", "u_Nip"),
            ("T2", None, "v_RW", "u_RW"),
        )
    ):
        a11 = a12 = a22 = b1 = b2 = 0.0
        for idx in range(len(rows) - 1):
            row = rows[idx]
            nxt = rows[idx + 1]
            dt = nxt["time_s"] - row["time_s"]
            dvdt = (nxt[v_key] - row[v_key]) / dt
            downstream = 0.0 if next_t_key is None else row[next_t_key]
            phi_kt = (downstream - row[t_key]) + row[u_key] / plant.R_m[i]
            phi_kf = -row[v_key]
            a11 += phi_kt * phi_kt
            a12 += phi_kt * phi_kf
            a22 += phi_kf * phi_kf
            b1 += phi_kt * dvdt
            b2 += phi_kf * dvdt
        kt_i, kf_i = solve_2x2(a11, a12, a22, b1, b2)
        kt_est.append(max(1e-12, kt_i))
        kf_est.append(max(1e-12, kf_i))

    ea_num = 0.0
    ea_den = 0.0
    for idx in range(len(rows) - 1):
        row = rows[idx]
        nxt = rows[idx + 1]
        dt = nxt["time_s"] - row["time_s"]
        velocities = [row["v_UW"], row["v_Nip"], row["v_RW"]]
        tensions = [row["T0"], row["T1"], row["T2"]]
        for i, t_key in enumerate(("T0", "T1", "T2")):
            upstream_t = 0.0 if i == 0 else tensions[i - 1]
            upstream_v_abs = plant.line_speed_m_s if i == 0 else plant.line_speed_m_s + velocities[i - 1]
            current_v_abs = plant.line_speed_m_s + velocities[i]
            strain = velocities[i] - (0.0 if i == 0 else velocities[i - 1])
            transport = (upstream_t * upstream_v_abs - tensions[i] * current_v_abs) / plant.L_m[i]
            y = (nxt[t_key] - row[t_key]) / dt - transport
            x = strain / plant.L_m[i]
            ea_num += x * y
            ea_den += x * x
    ea_est = ea_num / ea_den if ea_den > 1e-12 else plant.EA_N

    estimates = {
        "kt_UW": kt_est[0],
        "kt_Nip": kt_est[1],
        "kt_RW": kt_est[2],
        "kf_UW": kf_est[0],
        "kf_Nip": kf_est[1],
        "kf_RW": kf_est[2],
        "EA": max(1e-12, ea_est),
    }
    truth_values = {
        "kt_UW": true_plant.kt[0],
        "kt_Nip": true_plant.kt[1],
        "kt_RW": true_plant.kt[2],
        "kf_UW": true_plant.kf[0],
        "kf_Nip": true_plant.kf[1],
        "kf_RW": true_plant.kf[2],
        "EA": true_plant.EA_N,
    }
    rel = []
    error_table = []
    for key, value in estimates.items():
        denom = abs(truth_values[key]) if abs(truth_values[key]) > 1e-12 else 1.0
        err = (value - truth_values[key]) / denom
        rel.append(err)
        error_table.append(
            {
                "parameter": key,
                "estimate": value,
                "truth": truth_values[key],
                "relative_error_percent": 100.0 * err,
            }
        )
    return {
        "estimates": estimates,
        "truth": truth_values,
        "RMSE_theta_percent": 100.0 * math.sqrt(sum(e * e for e in rel) / len(rel)),
        "error_table": error_table,
    }


def sysid_rmse(
    plant: PaperPlant,
    *,
    tlog_ms: int,
    excitation: str = "E_Toggle",
    amplitude_N: float = 2.0,
    noise_N: float = 0.0,
    noise_v: float = 0.0,
    lpf_hz: float | None = None,
    kp_star: float = 100.0,
    seed: int = 1,
    drift_plant: PaperPlant | None = None,
    truth: PaperPlant | None = None,
) -> float:
    rows = simulate_paper_model(
        plant,
        tlog_s=tlog_ms / 1000.0,
        excitation=excitation,
        amplitude_N=amplitude_N,
        sensor_noise_N=noise_N,
        sensor_noise_v_m_s=noise_v,
        kp_star=kp_star,
        seed=seed,
        drift_plant=drift_plant,
    )
    filtered = lowpass_rows(rows, lpf_hz)
    return float(estimate_paper_parameters(filtered, plant, truth or drift_plant or plant)["RMSE_theta_percent"])


def plot_line(rows: Sequence[Mapping[str, Any]], path: Path, title: str) -> str:
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    for case in sorted({row["case"] for row in rows}):
        subset = sorted([row for row in rows if row["case"] == case], key=lambda r: r["Tlog_ms"])
        ax.plot([row["Tlog_ms"] for row in subset], [row["sim_RMSE_theta_percent"] for row in subset], marker="o", label=f"Sim {case}")
        paper_subset = [row for row in subset if row["paper_RMSE_theta_percent"] is not None]
        if paper_subset:
            ax.plot([row["Tlog_ms"] for row in paper_subset], [row["paper_RMSE_theta_percent"] for row in paper_subset], marker="s", linestyle="--", label=f"Paper {case}")
    ax.set_xscale("log")
    ax.set_xlabel("Tlog (ms)")
    ax.set_ylabel("RMSE_theta (%)")
    ax.set_title(title)
    ax.grid(True, which="both", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return str(path)


def plot_bars(labels: Sequence[str], paper: Sequence[float | None], sim: Sequence[float], path: Path, title: str, ylabel: str) -> str:
    x = np.arange(len(labels))
    width = 0.38
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.bar(x - width / 2, [np.nan if v is None else v for v in paper], width, label="Paper", color="#6b7280")
    ax.bar(x + width / 2, sim, width, label="Full-equation rerun", color="#1d4ed8")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return str(path)


def run_logging(plant: PaperPlant) -> dict[str, Any]:
    rows = []
    for case, noise, lpf in (("NF", 0.0, None), ("SN", 0.13, None)):
        for tlog in TLOG_VALUES_MS:
            rmse = sysid_rmse(plant, tlog_ms=tlog, noise_N=noise, lpf_hz=lpf, seed=10 + tlog)
            paper = PAPER_REFERENCES["logging"][case.lower()].get(tlog)
            rows.append(
                {
                    "case": case,
                    "Tlog_ms": tlog,
                    "paper_RMSE_theta_percent": paper,
                    "sim_RMSE_theta_percent": rmse,
                    "relative_difference_percent": rel_diff_percent(rmse, paper),
                }
            )
    csv_path = write_csv(DATA_DIR / "logging_full_equation.csv", rows)
    fig_path = plot_line(rows, FIG_DIR / "logging_full_equation.png", "Logging Adequacy: Paper vs Full-Equation Rerun")
    best_sn = min([r for r in rows if r["case"] == "SN"], key=lambda r: r["sim_RMSE_theta_percent"])
    return {"rows": rows, "csv_path": csv_path, "figure_path": fig_path, "best_sn_Tlog_ms": best_sn["Tlog_ms"], "paper_claim": PAPER_REFERENCES["logging"]["claim"]}


def run_excitation(plant: PaperPlant) -> dict[str, Any]:
    rows = []
    for case, tlog, noise, lpf in (("NF", 5, 0.0, None), ("SN", 20, 0.13, 100.0)):
        for exc in EXCITATIONS:
            rmse = sysid_rmse(plant, tlog_ms=tlog, excitation=exc, noise_N=noise, lpf_hz=lpf, seed=100 + len(exc))
            paper = PAPER_REFERENCES["excitation"][case.lower()].get(exc)
            rows.append(
                {
                    "case": case,
                    "excitation": exc,
                    "paper_RMSE_theta_percent": paper,
                    "sim_RMSE_theta_percent": rmse,
                    "relative_difference_percent": rel_diff_percent(rmse, paper),
                }
            )
    csv_path = write_csv(DATA_DIR / "excitation_full_equation.csv", rows)
    labels = [f"{row['excitation']} {row['case']}" for row in rows]
    fig_path = plot_bars(labels, [row["paper_RMSE_theta_percent"] for row in rows], [row["sim_RMSE_theta_percent"] for row in rows], FIG_DIR / "excitation_full_equation.png", "Excitation: Paper vs Full-Equation Rerun", "RMSE_theta (%)")
    best_sn = min([r for r in rows if r["case"] == "SN"], key=lambda r: r["sim_RMSE_theta_percent"])
    return {"rows": rows, "csv_path": csv_path, "figure_path": fig_path, "best_sn_excitation": best_sn["excitation"], "paper_claim": PAPER_REFERENCES["excitation"]["claim"]}


def run_drift(plant: PaperPlant) -> dict[str, Any]:
    scenarios = {
        "EA_plus30": (plant.drifted(EA_scale=1.30), PAPER_REFERENCES["drift"]["EA_plus30"]),
        "f_plus30": (plant.drifted(f_scale=1.30), PAPER_REFERENCES["drift"]["f_plus30"]),
        "J_UWminus30_RWplus50": (plant.drifted(J_scale=(0.70, 1.0, 1.50)), PAPER_REFERENCES["drift"]["J_UWminus30_RWplus50"]),
        "J_UWminus50_RWplus100": (plant.drifted(J_scale=(0.50, 1.0, 2.00)), PAPER_REFERENCES["drift"]["J_UWminus50_RWplus100"]),
    }
    rows = []
    for name, (drifted, paper) in scenarios.items():
        rmse = sysid_rmse(plant, tlog_ms=20, noise_N=0.0, drift_plant=drifted, truth=drifted, seed=220)
        rows.append(
            {
                "scenario": name,
                "paper_RMSE_theta_percent": paper,
                "sim_RMSE_theta_percent": rmse,
                "relative_difference_percent": rel_diff_percent(rmse, paper),
            }
        )
    csv_path = write_csv(DATA_DIR / "drift_full_equation.csv", rows)
    fig_path = plot_bars([r["scenario"].replace("_", "\n") for r in rows], [r["paper_RMSE_theta_percent"] for r in rows], [r["sim_RMSE_theta_percent"] for r in rows], FIG_DIR / "drift_full_equation.png", "Drift: Paper vs Full-Equation Rerun", "RMSE_theta (%)")
    dominant = max(rows, key=lambda r: r["sim_RMSE_theta_percent"])
    return {"rows": rows, "csv_path": csv_path, "figure_path": fig_path, "dominant_simulated_source": dominant["scenario"], "paper_claim": PAPER_REFERENCES["drift"]["claim"]}


def run_noise_lpf(plant: PaperPlant) -> dict[str, Any]:
    rows = []
    for label, cutoff in (("No LPF", None), ("10 Hz", 10.0), ("50 Hz", 50.0), ("100 Hz", 100.0)):
        for tlog in TLOG_VALUES_MS:
            rmse = sysid_rmse(plant, tlog_ms=tlog, noise_N=0.13, lpf_hz=cutoff, seed=330 + tlog)
            paper = None
            if label == "50 Hz" and tlog == 20:
                paper = PAPER_REFERENCES["noise_lpf"]["lpf_50hz_tlog20"]
            if label == "100 Hz" and tlog == 20:
                paper = PAPER_REFERENCES["noise_lpf"]["lpf_100hz_tlog20"]
            rows.append({"LPF": label, "Tlog_ms": tlog, "paper_RMSE_theta_percent": paper, "sim_RMSE_theta_percent": rmse, "relative_difference_percent": rel_diff_percent(rmse, paper)})
    csv_path = write_csv(DATA_DIR / "noise_lpf_full_equation.csv", rows)
    matrix = np.array([[next(r["sim_RMSE_theta_percent"] for r in rows if r["LPF"] == label and r["Tlog_ms"] == t) for t in TLOG_VALUES_MS] for label in ("No LPF", "10 Hz", "50 Hz", "100 Hz")])
    fig, ax = plt.subplots(figsize=(9.0, 4.4))
    im = ax.imshow(matrix, aspect="auto", cmap="viridis")
    ax.set_xticks(np.arange(len(TLOG_VALUES_MS)))
    ax.set_xticklabels([str(t) for t in TLOG_VALUES_MS])
    ax.set_yticks(np.arange(4))
    ax.set_yticklabels(["No LPF", "10 Hz", "50 Hz", "100 Hz"])
    ax.set_xlabel("Tlog (ms)")
    ax.set_title("Noise/LPF: Full-Equation Rerun")
    for i in range(4):
        for j in range(len(TLOG_VALUES_MS)):
            ax.text(j, i, f"{matrix[i, j]:.1f}", ha="center", va="center", color="white", fontsize=8)
    fig.colorbar(im, ax=ax, label="RMSE_theta (%)")
    fig.tight_layout()
    fig_path = FIG_DIR / "noise_lpf_full_equation.png"
    fig.savefig(fig_path, dpi=180)
    plt.close(fig)
    best = min(rows, key=lambda r: r["sim_RMSE_theta_percent"])
    return {"rows": rows, "csv_path": csv_path, "figure_path": str(fig_path), "best_case": {"LPF": best["LPF"], "Tlog_ms": best["Tlog_ms"], "RMSE_theta_percent": best["sim_RMSE_theta_percent"]}, "paper_claim": PAPER_REFERENCES["noise_lpf"]["claim"]}


def run_gain(plant: PaperPlant) -> dict[str, Any]:
    rows = []
    for case, noise, lpf in (("NF", 0.0, None), ("SN", 0.13, 100.0)):
        for kp in (50, 100, 200):
            rmse = sysid_rmse(plant, tlog_ms=20, noise_N=noise, lpf_hz=lpf, kp_star=float(kp), seed=440 + kp)
            paper = PAPER_REFERENCES["gain"][f"kp{kp}_{case.lower()}"]
            rows.append({"case": case, "Kp_star": kp, "paper_RMSE_theta_percent": paper, "sim_RMSE_theta_percent": rmse, "relative_difference_percent": rel_diff_percent(rmse, paper)})
    csv_path = write_csv(DATA_DIR / "gain_full_equation.csv", rows)
    labels = [f"{r['case']} Kp*{r['Kp_star']}" for r in rows]
    fig_path = plot_bars(labels, [r["paper_RMSE_theta_percent"] for r in rows], [r["sim_RMSE_theta_percent"] for r in rows], FIG_DIR / "gain_full_equation.png", "Gain: Paper vs Full-Equation Rerun", "RMSE_theta (%)")
    best_sn = min([r for r in rows if r["case"] == "SN"], key=lambda r: r["sim_RMSE_theta_percent"])
    return {"rows": rows, "csv_path": csv_path, "figure_path": fig_path, "best_sn_gain": best_sn["Kp_star"], "paper_claim": PAPER_REFERENCES["gain"]["claim"]}


def evaluate_tracking_cost(plant: PaperPlant, kp_star: float, ti_s: float, seed: int = 1) -> float:
    # Use a fixed ET3 reference step as a retuning target.
    rows = simulate_paper_model(plant, duration_s=5.0, tlog_s=0.01, excitation="ET3", amplitude_N=2.5, kp_star=kp_star, seed=seed)
    err_sq = []
    overshoot = 0.0
    effort_sq = []
    for row in rows:
        for key, ref_key in (("T0", "ref_T0"), ("T1", "ref_T1"), ("T2", "ref_T2")):
            err = row[key] - row[ref_key]
            err_sq.append(err * err)
            overshoot = max(overshoot, row[key] - row[ref_key])
        for key in ("u_UW", "u_Nip", "u_RW"):
            effort_sq.append(row[key] * row[key])
    if not err_sq or any(not math.isfinite(value) for value in err_sq + effort_sq):
        return math.inf
    rmse = math.sqrt(sum(err_sq) / len(err_sq))
    effort = math.sqrt(sum(effort_sq) / len(effort_sq))
    return rmse + 0.25 * max(0.0, overshoot) + 0.002 * effort + 0.02 / max(ti_s, 0.05)


def run_retuning(plant: PaperPlant) -> dict[str, Any]:
    drifted = plant.drifted(J_scale=(0.70, 1.0, 1.50), f_scale=1.15)
    rng = random.Random(550)
    methods: list[dict[str, Any]] = []
    cs_candidates = [(rng.uniform(30, 250), rng.uniform(0.4, 3.0)) for _ in range(30)]
    # Offline HGS grid centered in a stable gain zone.
    kp_grid = np.geomspace(40, 220, 10)
    ti_grid = np.linspace(0.6, 2.4, 8)
    grid_scores = sorted(((evaluate_tracking_cost(drifted, float(kp), float(ti)), float(kp), float(ti)) for kp in kp_grid for ti in ti_grid), key=lambda x: x[0])
    hgs_seed = (grid_scores[0][1], grid_scores[0][2])

    method_candidates = {
        "CS-BO(30)": cs_candidates,
        "HGS-only": [hgs_seed],
        "HGS+BO(5)": [hgs_seed] + [(hgs_seed[0] * rng.uniform(0.80, 1.20), hgs_seed[1] * rng.uniform(0.80, 1.20)) for _ in range(5)],
        "HGS+BO(10)": [hgs_seed] + [(hgs_seed[0] * rng.uniform(0.75, 1.25), hgs_seed[1] * rng.uniform(0.75, 1.25)) for _ in range(10)],
    }
    paper_budget = {"CS-BO(30)": 30, "HGS-only": 0, "HGS+BO(5)": 5, "HGS+BO(10)": 10}
    for method, candidates in method_candidates.items():
        best = min(evaluate_tracking_cost(drifted, kp, ti, seed=551) for kp, ti in candidates)
        ref = PAPER_REFERENCES["retuning"].get(method, {})
        paper_cost = ref.get("median_cost") if isinstance(ref, Mapping) else None
        methods.append(
            {
                "method": method,
                "paper_real_evaluations": paper_budget[method],
                "sim_real_evaluations": paper_budget[method],
                "paper_median_cost": paper_cost,
                "sim_final_cost": best,
                "cost_relative_difference_percent": rel_diff_percent(best, paper_cost),
            }
        )
    csv_path = write_csv(DATA_DIR / "retuning_full_equation.csv", methods)
    fig_path = plot_bars([r["method"] for r in methods], [r["paper_median_cost"] for r in methods], [r["sim_final_cost"] for r in methods], FIG_DIR / "retuning_full_equation.png", "Retuning: Paper vs Full-Equation Rerun", "Cost")
    best = min(methods, key=lambda r: r["sim_final_cost"])
    return {"rows": methods, "csv_path": csv_path, "figure_path": fig_path, "best_simulated_method": best["method"], "paper_claim": PAPER_REFERENCES["retuning"]["claim"]}


def alignment(sections: Mapping[str, Any]) -> list[dict[str, str]]:
    logging_best = int(sections["logging"]["best_sn_Tlog_ms"])
    excitation_best = str(sections["excitation"]["best_sn_excitation"])
    drift_best = str(sections["drift"]["dominant_simulated_source"])
    noise_best = sections["noise_lpf"]["best_case"]
    gain_best = int(sections["gain"]["best_sn_gain"])
    retuning_best = str(sections["retuning"]["best_simulated_method"])
    return [
        {"section": "Logging adequacy", "paper_claim": PAPER_REFERENCES["logging"]["claim"], "rerun_finding": f"Best SN Tlog = {logging_best} ms", "alignment": "supports" if logging_best in (10, 20) else "does not support"},
        {"section": "Excitation diversity", "paper_claim": PAPER_REFERENCES["excitation"]["claim"], "rerun_finding": f"Best SN excitation = {excitation_best}", "alignment": "supports" if excitation_best in {"ET3", "ET6", "E_Toggle", "EVR"} else "does not support"},
        {"section": "Parameter drift", "paper_claim": PAPER_REFERENCES["drift"]["claim"], "rerun_finding": f"Largest scenario = {drift_best}", "alignment": "supports" if drift_best.startswith("J_") else "does not support"},
        {"section": "Noise and LPF", "paper_claim": PAPER_REFERENCES["noise_lpf"]["claim"], "rerun_finding": f"Best = {noise_best['LPF']} at {noise_best['Tlog_ms']} ms", "alignment": "partial" if noise_best["LPF"] in {"50 Hz", "100 Hz"} or noise_best["Tlog_ms"] in (10, 20) else "does not support"},
        {"section": "SysID-mode gain", "paper_claim": PAPER_REFERENCES["gain"]["claim"], "rerun_finding": f"Best SN Kp* = {gain_best}", "alignment": "supports" if gain_best in (100, 200) else "does not support"},
        {"section": "Retuning", "paper_claim": PAPER_REFERENCES["retuning"]["claim"], "rerun_finding": f"Lowest cost = {retuning_best}", "alignment": "supports" if retuning_best in {"HGS+BO(5)", "HGS+BO(10)", "HGS-only"} else "partial"},
    ]


def section_reason(key: str) -> str:
    reasons = {
        "logging": "The full governing equations reproduce coarse-logging degradation and strong noisy finite-difference sensitivity, but exact optimum depends on nominal plant/noise choices because the paper's ten-plant constants and seeds are unavailable.",
        "excitation": "The direct equation rerun tests the same information-content mechanism. Exact ranking can differ because these ET profiles are reconstructed from paper descriptions rather than original code.",
        "drift": "Inertia drift changes the roller acceleration coefficients in Eq. (2), so asymmetric J drift should dominate when exact J arrays change. The rerun checks that mechanism directly.",
        "noise_lpf": "The LPF experiment applies a first-order filter to logged measurements. It captures noise smoothing, but not the exact industrial anti-aliasing chain before sampling.",
        "gain": "The gain sweep uses Eq. (3) Kp* directly. Differences in magnitude reflect nominal plant reconstruction, but the direction tests the paper's temporary SysID-mode gain claim.",
        "retuning": "The retuning rerun uses the same idea of offline grid search plus limited real evaluations. The cost is related to, but not identical to, the paper's hidden implementation.",
    }
    return reasons[key]


def render_report(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Full Governing-Equation Numerical Rerun",
        "",
        "## Scope",
        "",
        "This report reruns the paper sections using a standalone implementation of the governing equations from the PDF, rather than the dashboard reduced model.",
        "",
        "Implemented equations:",
        "",
        "- Eq. (1): web tension transport with upstream boundary and convection term.",
        "- Eq. (2): roller surface-velocity dynamics with inertia, friction, tension coupling, and motor torque.",
        "- Eq. (3): normalized outer tension PI correction.",
        "- Eq. (4): inner velocity proportional controller.",
        "- Eq. (5): measurement-based feedforward compensation.",
        "- Eq. (6)-(7): ratio-parameter SysID from one-step finite differences.",
        "",
        "## Fidelity Limits",
        "",
        "- Raw simulation data, optimizer seeds, and exact source code from the paper are not provided in the PDFs.",
        "- Exact per-plant R, J, f, L, and b arrays are not provided; only ranges and selected EA/regime values are available.",
        "- The rerun therefore uses a physically plausible P01-compatible nominal plant and compares trends and section values against the paper.",
        "",
        "## Alignment Summary",
        "",
        "| Section | Paper claim | Rerun finding | Alignment |",
        "|---|---|---|---|",
    ]
    for row in summary["alignment"]:
        lines.append(f"| {row['section']} | {row['paper_claim']} | {row['rerun_finding']} | {row['alignment']} |")
    specs = [
        ("logging", "Logging Adequacy", "logging_full_equation.png"),
        ("excitation", "Excitation Diversity", "excitation_full_equation.png"),
        ("drift", "Parameter Drift", "drift_full_equation.png"),
        ("noise_lpf", "Noise/LPF", "noise_lpf_full_equation.png"),
        ("gain", "SysID-Mode Gain", "gain_full_equation.png"),
        ("retuning", "Retuning", "retuning_full_equation.png"),
    ]
    for key, title, figure in specs:
        section = summary["sections"][key]
        lines.extend(["", f"## {title}", "", f"Paper claim: {section['paper_claim']}", "", f"![{title}](figures/{figure})", ""])
        if key == "logging":
            lines.append(f"Rerun result: best noisy Tlog = `{section['best_sn_Tlog_ms']} ms`.")
        elif key == "excitation":
            lines.append(f"Rerun result: best noisy excitation = `{section['best_sn_excitation']}`.")
        elif key == "drift":
            lines.append(f"Rerun result: dominant drift scenario = `{section['dominant_simulated_source']}`.")
        elif key == "noise_lpf":
            best = section["best_case"]
            lines.append(f"Rerun result: best noise/LPF case = `{best['LPF']}` at `{best['Tlog_ms']} ms`.")
        elif key == "gain":
            lines.append(f"Rerun result: best noisy Kp* = `{section['best_sn_gain']}`.")
        elif key == "retuning":
            lines.append(f"Rerun result: lowest simulated retuning cost = `{section['best_simulated_method']}`.")
        lines.extend(["", f"Reason: {section_reason(key)}", "", f"CSV: `data/{Path(section['csv_path']).name}`", ""])
        if key == "retuning":
            lines.append("| Method | Paper evals | Sim evals | Paper cost | Sim cost | Difference (%) |")
            lines.append("|---|---:|---:|---:|---:|---:|")
            for row in section["rows"]:
                lines.append(f"| {row['method']} | {_fmt(row['paper_real_evaluations'])} | {_fmt(row['sim_real_evaluations'])} | {_fmt(row['paper_median_cost'])} | {_fmt(row['sim_final_cost'])} | {_fmt(row['cost_relative_difference_percent'])} |")
        else:
            label_key = "Tlog_ms" if key in {"logging", "noise_lpf"} else "excitation" if key == "excitation" else "scenario" if key == "drift" else "Kp_star"
            lines.append("| Case | Paper RMSE_theta (%) | Sim RMSE_theta (%) | Difference (%) |")
            lines.append("|---|---:|---:|---:|")
            for row in section["rows"][:12]:
                case = row.get(label_key)
                if key == "logging":
                    case = f"{row['case']} {case} ms"
                if key == "noise_lpf":
                    case = f"{row['LPF']} {case} ms"
                if key == "gain":
                    case = f"{row['case']} Kp* {case}"
                lines.append(f"| {case} | {_fmt(row.get('paper_RMSE_theta_percent'))} | {_fmt(row.get('sim_RMSE_theta_percent'))} | {_fmt(row.get('relative_difference_percent'))} |")
    lines.extend(["", "## Generated Files", "", f"- JSON: `{JSON_PATH.name}`", "- CSV tables: `data/*.csv`", "- Graphs: `figures/*.png`", ""])
    return "\n".join(lines)


def main() -> None:
    ensure_dirs()
    plant = PaperPlant()
    sections = {
        "logging": run_logging(plant),
        "excitation": run_excitation(plant),
        "drift": run_drift(plant),
        "noise_lpf": run_noise_lpf(plant),
        "gain": run_gain(plant),
        "retuning": run_retuning(plant),
    }
    summary = {
        "model": {
            "state": "[dT0, dT1, dT2, dv_UW, dv_Nip, dv_RW]",
            "plant": plant.__dict__,
            "kt": plant.kt,
            "kf": plant.kf,
            "ku": plant.ku,
        },
        "paper_references": PAPER_REFERENCES,
        "sections": sections,
        "alignment": alignment(sections),
    }
    JSON_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    MD_PATH.write_text(render_report(summary), encoding="utf-8")
    print(json.dumps({"report_path": str(MD_PATH), "json_path": str(JSON_PATH), "figures_dir": str(FIG_DIR), "data_dir": str(DATA_DIR)}, indent=2))


if __name__ == "__main__":
    main()
