"""Worked calculation payloads for frontend result panels."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from backend.models.controller import ControllerConfig
from backend.models.equations import INPUT_NAMES, R2RParameters


def _clean_number(value: float) -> float:
    number = float(value)
    if not math.isfinite(number):
        return number
    return round(number, 8)


def _format_number(value: float) -> str:
    number = float(value)
    if not math.isfinite(number):
        return str(number)
    return f"{number:.6g}"


def _safe_relative(value: float, reference: float) -> float:
    if abs(reference) < 1e-12:
        return 0.0 if abs(value) < 1e-12 else math.inf
    return (value - reference) / reference


def _calculation(
    *,
    title: str,
    parameter: str,
    formula: str,
    values: Mapping[str, object],
    substitution: str,
    result: str,
    summary: str,
    steps: Sequence[str] | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "parameter": parameter,
        "formula": formula,
        "values": dict(values),
        "substitution": substitution,
        "result": result,
        "summary": summary,
        "steps": list(steps or []),
    }


def simulation_calculation_payload(
    metrics: Mapping[str, float],
    rows: Sequence[Mapping[str, float]],
    config: object,
    params: R2RParameters,
) -> dict[str, object]:
    """Return worked calculations for closed-loop simulation metrics."""

    if not rows:
        return {"calculation_summary": "No rows were available for calculations.", "calculations": []}

    tension_names = ("T1", "T2", "T3")
    target = ControllerConfig(line_speed_m_s=getattr(config, "line_speed_m_s", 1.0)).target_tension_N
    squared_errors = [
        (float(row[name]) - target[index]) ** 2
        for row in rows
        for index, name in enumerate(tension_names)
    ]
    sse = sum(squared_errors)
    tension_terms = len(squared_errors)
    rmse = math.sqrt(sse / tension_terms)

    effort_squares = [float(row[name]) ** 2 for row in rows for name in INPUT_NAMES]
    effort_sse = sum(effort_squares)
    effort_terms = len(effort_squares)
    effort_rms = math.sqrt(effort_sse / effort_terms)

    derivative_row = max(
        rows,
        key=lambda row: abs(float(row["v_UW_m_s"]) - params.feeder_velocity_m_s)
        + abs(float(row["T1"]) * float(row["v_UW_m_s"])),
    )
    v_prev = params.feeder_velocity_m_s
    v_i = float(derivative_row["v_UW_m_s"])
    t_prev = 0.0
    t_i = float(derivative_row["T1"])
    speed_delta = v_i - v_prev
    elastic_term = (params.EA / params.span_length_m[0]) * speed_delta
    convective_term = (t_prev * v_prev - t_i * v_i) / params.span_length_m[0]
    d_t1 = elastic_term + convective_term

    calculations = [
        _calculation(
            title="Tension RMSE",
            parameter="tension_rmse_N",
            formula="sqrt(sum((T_i - T_ref_i)^2) / (3*N))",
            values={
                "logged_rows": float(len(rows)),
                "terms": float(tension_terms),
                "target_T1_N": target[0],
                "target_T2_N": target[1],
                "target_T3_N": target[2],
                "squared_error_sum_N2": _clean_number(sse),
            },
            substitution=f"sqrt({_format_number(sse)} / {tension_terms})",
            result=f"tension_rmse_N = {_format_number(rmse)} N",
            summary="This measures average tension tracking error across all three spans and all logged samples.",
            steps=[
                f"Use {len(rows)} logged rows from the simulation output.",
                f"For each row, compare T1, T2, and T3 with target tensions {tuple(_format_number(v) for v in target)} N.",
                "Square every tension error so positive and negative tracking errors both count.",
                f"Add all squared errors: sum(error^2) = {_format_number(sse)} N^2.",
                f"Divide by the number of tension samples: {tension_terms}.",
                f"Take the square root to get tension_rmse_N = {_format_number(rmse)} N.",
            ],
        ),
        _calculation(
            title="Control Effort RMS",
            parameter="control_effort_rms_V",
            formula="sqrt(sum(u_UW^2 + u_Nip^2 + u_RW^2) / (3*N))",
            values={
                "logged_rows": float(len(rows)),
                "terms": float(effort_terms),
                "input_square_sum_V2": _clean_number(effort_sse),
            },
            substitution=f"sqrt({_format_number(effort_sse)} / {effort_terms})",
            result=f"control_effort_rms_V = {_format_number(effort_rms)} V",
            summary="This shows how much voltage effort the controller used while regulating the web.",
            steps=[
                f"Read u_UW, u_Nip, and u_RW from every one of the {len(rows)} logged rows.",
                "Square each voltage command so positive and negative effort contribute equally.",
                f"Add all squared voltage commands: sum(u^2) = {_format_number(effort_sse)} V^2.",
                f"Divide by the number of command samples: {effort_terms}.",
                f"Take the square root to get control_effort_rms_V = {_format_number(effort_rms)} V.",
            ],
        ),
        _calculation(
            title="T1 Derivative Example",
            parameter="dT1/dt",
            formula="(EA/L1)*(v1 - v0) + (T0*v0 - T1*v1)/L1",
            values={
                "time_s": _clean_number(float(derivative_row["time_s"])),
                "EA_N": params.EA,
                "L1_m": params.span_length_m[0],
                "T0_N": t_prev,
                "T1_N": _clean_number(float(derivative_row["T1"])),
                "v0_feeder_m_s": _clean_number(v_prev),
                "v1_UW_m_s": _clean_number(v_i),
                "elastic_term_N_per_s": _clean_number(elastic_term),
                "convective_term_N_per_s": _clean_number(convective_term),
            },
            substitution=(
                f"({params.EA}/{params.span_length_m[0]})*({_format_number(speed_delta)}) "
                f"+ (({_format_number(t_prev)}*{_format_number(v_prev)}) "
                f"- ({_format_number(t_i)}*{_format_number(v_i)}))/{params.span_length_m[0]}"
            ),
            result=f"dT1/dt = {_format_number(d_t1)} N/s",
            summary="The PDF tension equation combines elastic stretch from velocity mismatch with convective transport of tension across the span.",
            steps=[
                f"Pick the logged row at time { _format_number(float(derivative_row['time_s'])) } s as a worked example.",
                f"Use the boundary tension T0 = {_format_number(t_prev)} N and feeder speed v0 = {_format_number(v_prev)} m/s.",
                f"Read T1 = {_format_number(t_i)} N and v1 = v_UW = {_format_number(v_i)} m/s from the logged row.",
                f"Compute velocity mismatch: v1 - v0 = {_format_number(speed_delta)} m/s.",
                f"Compute the elastic term: (EA/L1)*(v1 - v0) = {_format_number(elastic_term)} N/s.",
                f"Compute the convective term: (T0*v0 - T1*v1)/L1 = {_format_number(convective_term)} N/s.",
                f"Add both terms to obtain dT1/dt = {_format_number(d_t1)} N/s.",
            ],
        ),
    ]

    return {
        "calculation_summary": (
            "Simulation calculations recompute the reported tracking, effort, and one governing-equation derivative "
            "from the generated rows."
        ),
        "calculations": calculations,
    }


def sysid_calculation_payload(
    metrics: Mapping[str, float],
    error_table: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Return one worked example for each SysID parameter plus RMSE_theta."""

    calculations: list[dict[str, object]] = []
    rel_errors: list[float] = []
    for row in error_table:
        name = str(row["parameter"])
        estimate = float(row["estimate"])
        truth = float(row["truth"])
        relative_error = _safe_relative(estimate, truth)
        rel_errors.append(relative_error)
        calculations.append(
            _calculation(
                title=f"{name} Relative Error",
                parameter=name,
                formula="(estimate - truth) / truth",
                values={
                    "estimate": _clean_number(estimate),
                    "truth": _clean_number(truth),
                    "absolute_error": _clean_number(estimate - truth),
                    "relative_error": _clean_number(relative_error),
                },
                substitution=f"({_format_number(estimate)} - {_format_number(truth)}) / {_format_number(truth)}",
                result=f"{name} relative_error = {_format_number(relative_error)}",
                summary="This parameter contribution is squared before it enters RMSE_theta.",
                steps=[
                    f"Read the SysID estimate for {name}: {_format_number(estimate)}.",
                    f"Read the true/reference value for {name}: {_format_number(truth)}.",
                    f"Compute absolute error: estimate - truth = {_format_number(estimate - truth)}.",
                    f"Normalize by truth: {_format_number(estimate - truth)} / {_format_number(truth)} = {_format_number(relative_error)}.",
                    "This relative error is later squared and included in RMSE_theta.",
                ],
            )
        )

    if rel_errors:
        rmse_theta = math.sqrt(sum(error * error for error in rel_errors) / len(rel_errors))
        calculations.append(
            _calculation(
                title="SysID Parameter RMSE",
                parameter="RMSE_theta",
                formula="sqrt(mean(relative_error_i^2))",
                values={
                    "parameters": float(len(rel_errors)),
                    "relative_error_square_sum": _clean_number(sum(error * error for error in rel_errors)),
                },
                substitution=(
                    f"sqrt({_format_number(sum(error * error for error in rel_errors))} / {len(rel_errors)})"
                ),
                result=f"RMSE_theta = {_format_number(rmse_theta)}",
                summary="A lower RMSE_theta means the identified parameters are closer to the true model parameters.",
                steps=[
                    f"Collect the {len(rel_errors)} relative errors from kt_UW, kt_Nip, kt_RW, kf_UW, kf_Nip, kf_RW, and EA.",
                    "Square each relative error so signs do not cancel.",
                    f"Add squared errors: {_format_number(sum(error * error for error in rel_errors))}.",
                    f"Divide by parameter count: {len(rel_errors)}.",
                    f"Take the square root to obtain RMSE_theta = {_format_number(rmse_theta)}.",
                ],
            )
        )

    return {
        "calculation_summary": (
            "SysID calculations show one relative-error example for every estimated parameter, then combine them "
            "into RMSE_theta."
        ),
        "calculations": calculations,
    }


def part1_calculation_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Return one paper-reference calculation for each physical parameter."""

    rows = payload.get("comparison_table", [])
    calculations: list[dict[str, object]] = []
    if isinstance(rows, Sequence):
        for row_obj in rows:
            if not isinstance(row_obj, Mapping):
                continue
            name = str(row_obj["parameter"])
            model_value = float(row_obj["model_value"])
            reference = float(row_obj["paper_reference"])
            range_min = float(row_obj["paper_range_min"])
            range_max = float(row_obj["paper_range_max"])
            absolute_difference = model_value - reference
            relative_percent = _safe_relative(model_value, reference) * 100.0
            in_range = range_min <= model_value <= range_max
            calculations.append(
                _calculation(
                    title=f"{name} Paper Difference",
                    parameter=name,
                    formula="relative_difference_percent = ((model_value - paper_reference) / paper_reference) * 100",
                    values={
                        "model_value": _clean_number(model_value),
                        "paper_reference": _clean_number(reference),
                        "paper_range_min": _clean_number(range_min),
                        "paper_range_max": _clean_number(range_max),
                        "absolute_difference": _clean_number(absolute_difference),
                    },
                    substitution=(
                        f"(({_format_number(model_value)} - {_format_number(reference)}) / "
                        f"{_format_number(reference)}) * 100"
                    ),
                    result=(
                        f"{name} difference = {_format_number(relative_percent)}%; "
                        f"in_paper_range = {str(in_range).lower()}"
                    ),
                    summary="The model value is compared with the selected reference value and accepted range.",
                    steps=[
                        f"Read model value for {name}: {_format_number(model_value)}.",
                        f"Read paper/supplement reference for {name}: {_format_number(reference)}.",
                        f"Compute absolute difference: {_format_number(model_value)} - {_format_number(reference)} = {_format_number(absolute_difference)}.",
                        f"Compute percent difference: ({_format_number(absolute_difference)} / {_format_number(reference)}) * 100 = {_format_number(relative_percent)}%.",
                        f"Check range: {_format_number(range_min)} <= {_format_number(model_value)} <= {_format_number(range_max)} is {str(in_range).lower()}.",
                    ],
                )
            )

    return {
        "calculation_summary": (
            "Paper Part 1 gives one worked calculation for each extracted physical parameter: EA, R, L, J, f, and b."
        ),
        "calculations": calculations,
    }


def _study_metrics(payload: Mapping[str, object]) -> Mapping[str, object]:
    metrics = payload.get("metrics", {})
    return metrics if isinstance(metrics, Mapping) else {}


def _inner_rows(study_metrics: Mapping[str, object]) -> list[Mapping[str, object]]:
    rows = study_metrics.get("metrics", [])
    if not isinstance(rows, Sequence):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def logging_rate_calculation_payload(payload: Mapping[str, object]) -> dict[str, object]:
    study_metrics = _study_metrics(payload)
    rows = _inner_rows(study_metrics)
    noisy_rows = [row for row in rows if row.get("case") == "sensor_noise"]
    best = min(noisy_rows, key=lambda row: float(row["RMSE_theta"])) if noisy_rows else None
    calculations: list[dict[str, object]] = []
    if best:
        best_tlog = float(best["Tlog_ms"])
        best_rmse = float(best["RMSE_theta"])
        calculations.append(
            _calculation(
                title="Best Noisy Logging Rate",
                parameter="best_noisy_Tlog_ms",
                formula="argmin_Tlog RMSE_theta(Tlog, sensor_noise)",
                values={
                    "tested_noisy_Tlog_ms": ", ".join(_format_number(float(row["Tlog_ms"])) for row in noisy_rows),
                    "best_noisy_Tlog_ms": _clean_number(best_tlog),
                    "best_noisy_RMSE_theta": _clean_number(best_rmse),
                },
                substitution=f"minimum noisy RMSE_theta is {_format_number(best_rmse)} at Tlog={_format_number(best_tlog)} ms",
                result=f"best_noisy_Tlog_ms = {_format_number(best_tlog)} ms",
                summary="The selected logging rate is the noisy case with the lowest parameter-estimation error.",
                steps=[
                    "Filter the sweep table to rows where case = sensor_noise.",
                    "For each noisy logging rate, run SysID and record RMSE_theta.",
                    f"Compare tested noisy Tlog values: {', '.join(_format_number(float(row['Tlog_ms'])) for row in noisy_rows)} ms.",
                    f"Select the row with minimum RMSE_theta: {_format_number(best_rmse)}.",
                    f"Report its logging period: Tlog = {_format_number(best_tlog)} ms.",
                ],
            )
        )
        calculations.append(
            _calculation(
                title="10-20 ms Window Check",
                parameter="supports_noisy_optimum_near_10_20ms",
                formula="best_noisy_Tlog_ms in {10, 20}",
                values={
                    "best_noisy_Tlog_ms": _clean_number(best_tlog),
                    "paper_window_ms": "10, 20",
                },
                substitution=f"{_format_number(best_tlog)} in {{10, 20}}",
                result=f"supports_noisy_optimum_near_10_20ms = {str(best_tlog in (10.0, 20.0)).lower()}",
                summary="This validates whether the simulated noisy optimum falls in the logging-rate window discussed in the paper.",
                steps=[
                    f"Use the previously selected noisy optimum Tlog = {_format_number(best_tlog)} ms.",
                    "Compare it with the paper-supported window {10 ms, 20 ms}.",
                    f"Return true only if {_format_number(best_tlog)} equals 10 or 20.",
                ],
            )
        )
    return {
        "calculation_summary": "Logging-rate calculations solve the noisy optimum and compare it with the paper window.",
        "calculations": calculations,
    }


def excitation_calculation_payload(payload: Mapping[str, object]) -> dict[str, object]:
    study_metrics = _study_metrics(payload)
    rows = _inner_rows(study_metrics)
    noisy_rows = [row for row in rows if row.get("case") == "sensor_noise"]
    best = min(noisy_rows, key=lambda row: float(row["RMSE_theta"])) if noisy_rows else None
    calculations: list[dict[str, object]] = []
    if best:
        excitation = str(best["excitation"])
        rmse = float(best["RMSE_theta"])
        multi_channel = excitation in {"ET3", "ET6", "E_Toggle", "EVR"}
        calculations.append(
            _calculation(
                title="Best Noisy Excitation",
                parameter="best_noisy_excitation",
                formula="argmin_excitation RMSE_theta(excitation, sensor_noise)",
                values={
                    "tested_noisy_excitations": ", ".join(str(row["excitation"]) for row in noisy_rows),
                    "best_noisy_excitation": excitation,
                    "best_noisy_RMSE_theta": _clean_number(rmse),
                },
                substitution=f"minimum noisy RMSE_theta is {_format_number(rmse)} for {excitation}",
                result=f"best_noisy_excitation = {excitation}",
                summary="The excitation with the smallest noisy RMSE_theta gives the strongest validation signal for SysID.",
                steps=[
                    "Filter the excitation table to rows where case = sensor_noise.",
                    "For each noisy excitation profile, run SysID and record RMSE_theta.",
                    f"Compare profiles: {', '.join(str(row['excitation']) for row in noisy_rows)}.",
                    f"Select the minimum RMSE_theta row: {_format_number(rmse)} for {excitation}.",
                ],
            )
        )
        calculations.append(
            _calculation(
                title="Multi-Channel Excitation Check",
                parameter="supports_multi_channel_or_toggle_under_noise",
                formula="best_noisy_excitation in {ET3, ET6, E_Toggle, EVR}",
                values={
                    "best_noisy_excitation": excitation,
                    "accepted_profiles": "ET3, ET6, E_Toggle, EVR",
                },
                substitution=f"{excitation} in {{ET3, ET6, E_Toggle, EVR}}",
                result=f"supports_multi_channel_or_toggle_under_noise = {str(multi_channel).lower()}",
                summary="This checks whether a multi-channel or toggle excitation wins under noisy measurement conditions.",
                steps=[
                    f"Use best noisy excitation = {excitation}.",
                    "Compare with accepted multi-channel/toggle profiles: ET3, ET6, E_Toggle, EVR.",
                    f"Return {str(multi_channel).lower()} for the multi-channel/toggle check.",
                ],
            )
        )
    return {
        "calculation_summary": "Excitation calculations identify the lowest-RMSE noisy excitation and classify its type.",
        "calculations": calculations,
    }


def drift_calculation_payload(payload: Mapping[str, object]) -> dict[str, object]:
    study_metrics = _study_metrics(payload)
    rows = _inner_rows(study_metrics)
    dominant = max(rows, key=lambda row: float(row["degradation_score"])) if rows else None
    calculations: list[dict[str, object]] = []
    if dominant:
        rmse = float(dominant["RMSE_theta"])
        tension_rmse = float(dominant["tension_rmse_N"])
        overshoot = max(0.0, float(dominant["max_overshoot_N"]))
        effort = float(dominant["control_effort_rms_V"])
        score = tension_rmse + 0.30 * overshoot + 0.02 * effort + 8.0 * rmse
        scenario = str(dominant["scenario"])
        calculations.append(
            _calculation(
                title="Dominant Drift Score",
                parameter="degradation_score",
                formula="tension_rmse + 0.30*max(0, overshoot) + 0.02*control_effort + 8*RMSE_theta",
                values={
                    "scenario": scenario,
                    "tension_rmse_N": _clean_number(tension_rmse),
                    "max_overshoot_N": _clean_number(overshoot),
                    "control_effort_rms_V": _clean_number(effort),
                    "RMSE_theta": _clean_number(rmse),
                },
                substitution=(
                    f"{_format_number(tension_rmse)} + 0.30*{_format_number(overshoot)} + "
                    f"0.02*{_format_number(effort)} + 8*{_format_number(rmse)}"
                ),
                result=f"{scenario} degradation_score = {_format_number(score)}",
                summary="The drift case with the largest degradation score is treated as the dominant degradation source.",
                steps=[
                    f"Use the candidate drift scenario {scenario}.",
                    f"Read tension RMSE = {_format_number(tension_rmse)} N.",
                    f"Read positive overshoot = {_format_number(overshoot)} N.",
                    f"Read control effort RMS = {_format_number(effort)} V.",
                    f"Read parameter RMSE_theta = {_format_number(rmse)}.",
                    f"Apply the weighted score equation to get {_format_number(score)}.",
                ],
            )
        )
        calculations.append(
            _calculation(
                title="J Drift Dominance Check",
                parameter="supports_J_drift_dominance",
                formula="dominant_degradation_source == J",
                values={"dominant_degradation_source": scenario, "paper_expected_source": "J"},
                substitution=f"{scenario} == J",
                result=f"supports_J_drift_dominance = {str(scenario == 'J').lower()}",
                summary="This directly checks whether inertia drift is the dominant sensitivity case.",
                steps=[
                    f"Select the scenario with largest degradation score: {scenario}.",
                    "Compare selected scenario with paper expectation J.",
                    f"Return {str(scenario == 'J').lower()} for J drift dominance.",
                ],
            )
        )
    return {
        "calculation_summary": "Drift calculations recompute the degradation score and compare the dominant source with the paper claim.",
        "calculations": calculations,
    }


def retuning_calculation_payload(payload: Mapping[str, object]) -> dict[str, object]:
    study_metrics = _study_metrics(payload)
    rows = _inner_rows(study_metrics)
    best = min(rows, key=lambda row: float(row["final_cost"])) if rows else None
    by_method = {str(row["method"]): row for row in rows}
    calculations: list[dict[str, object]] = []
    if best:
        rmse = float(best["tension_rmse_N"])
        overshoot = max(0.0, float(best["overshoot_N"]))
        t90 = float(best["t90_s"])
        effort = float(best["control_effort_rms_V"])
        cost = rmse + 0.25 * overshoot + 0.15 * t90 + 0.015 * effort
        calculations.append(
            _calculation(
                title="Final Cost Example",
                parameter="final_cost",
                formula="RMSE + 0.25*overshoot + 0.15*t90 + 0.015*control_effort",
                values={
                    "method": str(best["method"]),
                    "tension_rmse_N": _clean_number(rmse),
                    "overshoot_N": _clean_number(overshoot),
                    "t90_s": _clean_number(t90),
                    "control_effort_rms_V": _clean_number(effort),
                },
                substitution=(
                    f"{_format_number(rmse)} + 0.25*{_format_number(overshoot)} + "
                    f"0.15*{_format_number(t90)} + 0.015*{_format_number(effort)}"
                ),
                result=f"{best['method']} final_cost = {_format_number(cost)}",
                summary="The best retuning method is the row with the lowest final cost.",
                steps=[
                    f"Use retuning method {best['method']}.",
                    f"Read tension RMSE = {_format_number(rmse)}.",
                    f"Read positive overshoot = {_format_number(overshoot)}.",
                    f"Read t90 = {_format_number(t90)} s.",
                    f"Read control effort RMS = {_format_number(effort)} V.",
                    f"Apply the cost equation to obtain {_format_number(cost)}.",
                ],
            )
        )
    cs = by_method.get("CS-BO(30)")
    hgs5 = by_method.get("HGS+BO(5)")
    if cs and hgs5:
        cs_evals = float(cs["real_evaluations"])
        hgs5_evals = float(hgs5["real_evaluations"])
        savings = cs_evals - hgs5_evals
        calculations.append(
            _calculation(
                title="Real-Evaluation Savings",
                parameter="supports_HGS_BO5_fewer_real_evaluations_than_CS_BO30",
                formula="CS_BO30_real_evaluations - HGS_BO5_real_evaluations",
                values={
                    "CS_BO30_real_evaluations": _clean_number(cs_evals),
                    "HGS_BO5_real_evaluations": _clean_number(hgs5_evals),
                    "saved_real_evaluations": _clean_number(savings),
                },
                substitution=f"{_format_number(cs_evals)} - {_format_number(hgs5_evals)}",
                result=(
                    "supports_HGS_BO5_fewer_real_evaluations_than_CS_BO30 = "
                    f"{str(hgs5_evals < cs_evals).lower()}"
                ),
                summary="This validates the retuning-budget claim by comparing real evaluation counts directly.",
                steps=[
                    f"Read CS-BO(30) real evaluations = {_format_number(cs_evals)}.",
                    f"Read HGS+BO(5) real evaluations = {_format_number(hgs5_evals)}.",
                    f"Subtract to get saved evaluations = {_format_number(savings)}.",
                    f"Return {str(hgs5_evals < cs_evals).lower()} because HGS+BO(5) uses fewer evaluations than CS-BO(30).",
                ],
            )
        )
    return {
        "calculation_summary": "Retuning calculations solve the cost formula and compare the real-evaluation budgets.",
        "calculations": calculations,
    }
