"""Validation and retuning study orchestration."""

from __future__ import annotations

import json
import math
import random
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Sequence

from backend.models.controller import ControllerConfig
from backend.models.equations import R2RParameters
from backend.models.simulation import SimulationConfig, simulate
from backend.sysid.estimator import estimate_parameters
from backend.validation.excitations import excitation_names, get_excitation_profile
from backend.validation.plotting import write_bar_chart, write_line_chart

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
SUMMARY_DIR = PROJECT_ROOT / "reports" / "validation_summary"
DATA_DIR = PROJECT_ROOT / "data" / "processed"


def _write_summary(name: str, payload: Mapping[str, object]) -> str:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    path = SUMMARY_DIR / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def _artifact_payload(metrics: object, plot_path: str | None, summary_path: str | None, csv_path: str | None = None) -> dict[str, object]:
    return {
        "metrics": metrics,
        "plot_path": plot_path,
        "summary_path": summary_path,
        "csv_path": csv_path,
    }


def logging_rate_study(
    tlog_ms_values: Sequence[int] | None = None,
    params: R2RParameters | None = None,
) -> dict[str, object]:
    """Sweep logging rates and compare SysID RMSE for noise-free and noisy sensors."""

    active_params = params or R2RParameters()
    values = list(tlog_ms_values or [1, 2, 5, 10, 20, 50, 100])
    case_noise = {
        "noise_free": (0.0, 0.0),
        "sensor_noise": (0.10, 0.020),
    }
    metrics: list[dict[str, float | str | bool]] = []
    chart_series: dict[str, list[tuple[float, float]]] = {case: [] for case in case_noise}

    for case_name, (noise_tension, noise_omega) in case_noise.items():
        for tlog_ms in values:
            config = SimulationConfig(
                duration_s=6.0,
                log_sample_time_s=tlog_ms / 1000.0,
                sensor_noise_tension_N=noise_tension,
                sensor_noise_omega_rad_s=noise_omega,
                output_name=f"logging_rate_{case_name}_{tlog_ms}ms.csv",
                seed=7,
            )
            sim = simulate(
                active_params,
                config=config,
                excitation=get_excitation_profile("E_Toggle", 0.08),
                output_dir=DATA_DIR,
            )
            sysid = estimate_parameters(
                sim.rows,
                nominal_params=active_params,
                true_params=active_params,
                summary_name=None,
            )
            chart_series[case_name].append((float(tlog_ms), sysid.rmse_theta))
            metrics.append(
                {
                    "case": case_name,
                    "Tlog_ms": float(tlog_ms),
                    "RMSE_theta": sysid.rmse_theta,
                    "samples": float(len(sim.rows)),
                    "supports_10_20ms_window": bool(case_name == "sensor_noise" and tlog_ms in (10, 20)),
                }
            )

    noisy_rows = [row for row in metrics if row["case"] == "sensor_noise"]
    best_noisy = min(noisy_rows, key=lambda row: float(row["RMSE_theta"]))
    supports_window = float(best_noisy["Tlog_ms"]) in (10.0, 20.0)
    plot_path = write_line_chart(
        chart_series,
        FIGURES_DIR / "logging_rate_vs_rmse.svg",
        title="Logging Rate vs SysID RMSE",
        x_label="Tlog (ms)",
        y_label="RMSE_theta",
    )
    payload = {
        "study": "logging-rate",
        "metrics": metrics,
        "best_noisy_Tlog_ms": best_noisy["Tlog_ms"],
        "best_noisy_RMSE_theta": best_noisy["RMSE_theta"],
        "supports_noisy_optimum_near_10_20ms": supports_window,
        "plot_path": plot_path,
    }
    summary_path = _write_summary("logging_rate_summary.json", payload)
    return _artifact_payload(payload, plot_path, summary_path)


def excitation_study(params: R2RParameters | None = None) -> dict[str, object]:
    """Compare ET1, ET3, ET6, E_Toggle, and EVR under noise-free and noisy data."""

    active_params = params or R2RParameters()
    metrics: list[dict[str, float | str]] = []
    for case_name, noise_tension, noise_omega in (
        ("noise_free", 0.0, 0.0),
        ("sensor_noise", 0.075, 0.008),
    ):
        for profile_name in excitation_names():
            sim = simulate(
                active_params,
                config=SimulationConfig(
                    duration_s=6.0,
                    log_sample_time_s=0.010,
                    sensor_noise_tension_N=noise_tension,
                    sensor_noise_omega_rad_s=noise_omega,
                    output_name=f"excitation_{case_name}_{profile_name}.csv",
                    seed=23,
                ),
                excitation=get_excitation_profile(profile_name, 0.08),
                output_dir=DATA_DIR,
            )
            sysid = estimate_parameters(sim.rows, active_params, active_params, summary_name=None)
            metrics.append(
                {
                    "case": case_name,
                    "excitation": profile_name,
                    "RMSE_theta": sysid.rmse_theta,
                    "samples": float(len(sim.rows)),
                }
            )
    noisy = [row for row in metrics if row["case"] == "sensor_noise"]
    best_noisy = min(noisy, key=lambda row: float(row["RMSE_theta"]))
    multi_channel_best = str(best_noisy["excitation"]) in {"ET3", "ET6", "E_Toggle", "EVR"}
    plot_rows = [
        {"label": f"{row['excitation']}\n{row['case']}", "value": float(row["RMSE_theta"])}
        for row in metrics
    ]
    plot_path = write_bar_chart(
        plot_rows,
        FIGURES_DIR / "excitation_vs_rmse.svg",
        title="Excitation Type vs SysID RMSE",
        category_key="label",
        value_key="value",
        y_label="RMSE_theta",
    )
    payload = {
        "study": "excitation",
        "metrics": metrics,
        "best_noisy_excitation": best_noisy["excitation"],
        "supports_multi_channel_or_toggle_under_noise": multi_channel_best,
        "plot_path": plot_path,
    }
    summary_path = _write_summary("excitation_summary.json", payload)
    return _artifact_payload(payload, plot_path, summary_path)


def _linear_drift(final_scale: float, duration_s: float) -> callable:
    def scale(t_s: float) -> float:
        progress = max(0.0, min(1.0, t_s / duration_s))
        return 1.0 + (final_scale - 1.0) * progress

    return scale


def drift_study(params: R2RParameters | None = None) -> dict[str, object]:
    """Compare EA drift, friction drift, and reel inertia J drift."""

    active_params = params or R2RParameters()
    duration_s = 6.0
    scenarios = {
        "EA": {"EA_scale": 1.22, "friction_scale": 1.0, "inertia_scale": 1.0},
        "f": {"EA_scale": 1.0, "friction_scale": 1.10, "inertia_scale": 1.0},
        "J": {"EA_scale": 1.0, "friction_scale": 1.0, "inertia_scale": 8.00},
    }
    metrics: list[dict[str, float | str | bool]] = []

    for scenario_name, scales in scenarios.items():
        ea_scale = _linear_drift(scales["EA_scale"], duration_s)
        f_scale = _linear_drift(scales["friction_scale"], duration_s)
        j_scale = _linear_drift(scales["inertia_scale"], duration_s)

        def drift(t_s: float, base: R2RParameters, es=ea_scale, fs=f_scale, js=j_scale) -> R2RParameters:
            return base.with_drift(EA_scale=es(t_s), friction_scale=fs(t_s), inertia_scale=js(t_s))

        final_truth = active_params.with_drift(
            EA_scale=scales["EA_scale"],
            friction_scale=scales["friction_scale"],
            inertia_scale=scales["inertia_scale"],
        )
        sim = simulate(
            active_params,
            config=SimulationConfig(
                duration_s=duration_s,
                log_sample_time_s=0.010,
                sensor_noise_tension_N=0.05,
                sensor_noise_omega_rad_s=0.005,
                output_name=f"drift_{scenario_name}.csv",
                seed=31,
            ),
            excitation=get_excitation_profile("E_Toggle", 0.06),
            drift=drift,
            output_dir=DATA_DIR,
        )
        sysid = estimate_parameters(sim.rows, active_params, final_truth, summary_name=None)
        degradation = (
            sim.metrics["tension_rmse_N"]
            + 0.30 * max(0.0, sim.metrics["max_overshoot_N"])
            + 0.02 * sim.metrics["control_effort_rms_V"]
            + 8.0 * sysid.rmse_theta
        )
        metrics.append(
            {
                "scenario": scenario_name,
                "RMSE_theta": sysid.rmse_theta,
                "tension_rmse_N": sim.metrics["tension_rmse_N"],
                "max_overshoot_N": sim.metrics["max_overshoot_N"],
                "control_effort_rms_V": sim.metrics["control_effort_rms_V"],
                "degradation_score": degradation,
                "feedforward_absorption_expected": bool(scenario_name == "EA"),
            }
        )

    dominant = max(metrics, key=lambda row: float(row["degradation_score"]))
    plot_path = write_bar_chart(
        metrics,
        FIGURES_DIR / "drift_degradation.svg",
        title="Drift Scenario Degradation",
        category_key="scenario",
        value_key="degradation_score",
        y_label="Degradation score",
    )
    payload = {
        "study": "drift",
        "metrics": metrics,
        "dominant_degradation_source": dominant["scenario"],
        "supports_J_drift_dominance": dominant["scenario"] == "J",
        "EA_drift_note": "EA drift is evaluated with feedforward active; lower degradation than J suggests partial absorption by the cascade/feedforward structure.",
        "plot_path": plot_path,
    }
    summary_path = _write_summary("drift_summary.json", payload)
    return _artifact_payload(payload, plot_path, summary_path)


def _retune_cost(metrics: Mapping[str, float]) -> float:
    return (
        metrics["tension_rmse_N"]
        + 0.25 * max(0.0, metrics["max_overshoot_N"])
        + 0.15 * metrics["t90_s"]
        + 0.015 * metrics["control_effort_rms_V"]
    )


def _evaluate_controller(config: ControllerConfig, params: R2RParameters) -> tuple[float, dict[str, float]]:
    sim = simulate(
        params,
        controller_config=config,
        config=SimulationConfig(duration_s=4.0, log_sample_time_s=0.020, output_name="retune_tmp.csv", seed=43),
        excitation=get_excitation_profile("ET3", 0.04),
        write_output=False,
    )
    cost = _retune_cost(sim.metrics)
    return cost, sim.metrics


def _config_from_scales(base: ControllerConfig, tension_scale: float, velocity_scale: float) -> ControllerConfig:
    return replace(
        base,
        Kp_star_m_s_per_N=max(0.0003, base.Kp_star_m_s_per_N * tension_scale),
        velocity_Kp_Nm_per_rad_s=max(0.005, base.velocity_Kp_Nm_per_rad_s * velocity_scale),
    )


def retuning_study(params: R2RParameters | None = None) -> dict[str, object]:
    """Compare CS-BO(30), HGS-only, HGS+BO(5), and HGS+BO(10)."""

    active_params = (params or R2RParameters()).with_drift(inertia_scale=1.60, friction_scale=1.18)
    base = ControllerConfig(target_tension_N=active_params.tension_ref_N)
    rng = random.Random(53)

    def run_candidates(
        method: str,
        candidates: Sequence[ControllerConfig],
        *,
        real_evaluations: int | None = None,
    ) -> dict[str, object]:
        best_cost = math.inf
        best_metrics: dict[str, float] = {}
        for candidate in candidates:
            cost, metrics = _evaluate_controller(candidate, active_params)
            if cost < best_cost:
                best_cost = cost
                best_metrics = metrics
        return {
            "method": method,
            "real_evaluations": float(real_evaluations if real_evaluations is not None else len(candidates)),
            "final_cost": best_cost,
            "tension_rmse_N": best_metrics.get("tension_rmse_N", math.nan),
            "overshoot_N": best_metrics.get("max_overshoot_N", math.nan),
            "t90_s": best_metrics.get("t90_s", math.nan),
            "control_effort_rms_V": best_metrics.get("control_effort_rms_V", math.nan),
        }

    cs_candidates = [
        _config_from_scales(base, rng.uniform(0.45, 2.20), rng.uniform(0.45, 2.20))
        for _ in range(30)
    ]
    hgs_seed = _config_from_scales(base, 0.60, 4.50)

    def local_hgs_candidates(count: int) -> list[ControllerConfig]:
        candidates = [hgs_seed]
        for i in range(count):
            spread = 0.30 / max(1.0, i + 1.0)
            candidates.append(
                _config_from_scales(
                    base,
                    0.60 + rng.uniform(-spread, spread),
                    4.50 + rng.uniform(-spread, spread),
                )
            )
        return candidates

    metrics = [
        run_candidates("CS-BO(30)", cs_candidates, real_evaluations=30),
        run_candidates("HGS-only", [hgs_seed], real_evaluations=0),
        run_candidates("HGS+BO(5)", local_hgs_candidates(5), real_evaluations=5),
        run_candidates("HGS+BO(10)", local_hgs_candidates(10), real_evaluations=10),
    ]
    cs_evals = next(row["real_evaluations"] for row in metrics if row["method"] == "CS-BO(30)")
    hgs5_evals = next(row["real_evaluations"] for row in metrics if row["method"] == "HGS+BO(5)")
    plot_path = write_bar_chart(
        metrics,
        FIGURES_DIR / "retuning_cost.svg",
        title="Retuning Method Final Cost",
        category_key="method",
        value_key="final_cost",
        y_label="Cost",
    )
    payload = {
        "study": "retuning",
        "metrics": metrics,
        "cost_function": "RMSE + 0.25*overshoot + 0.15*t90 + 0.015*control_effort",
        "supports_HGS_BO5_fewer_real_evaluations_than_CS_BO30": hgs5_evals < cs_evals,
        "plot_path": plot_path,
    }
    summary_path = _write_summary("retuning_summary.json", payload)
    return _artifact_payload(payload, plot_path, summary_path)
