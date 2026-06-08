"""Modular paper-validation parts.

Each part solves one validation problem, writes artifacts, and reports the
difference between the model result and the paper/supplement reference.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from backend.models.equations import R2RParameters
from backend.models.simulation import SimulationConfig, simulate
from backend.validation.paper_reference import load_paper_reference
from backend.validation.plotting import write_bar_chart

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
SUMMARY_DIR = PROJECT_ROOT / "reports" / "validation_summary"
DATA_DIR = PROJECT_ROOT / "data" / "processed"


def validation_parts_registry() -> list[dict[str, str]]:
    return [
        {
            "id": "part-1",
            "title": "Physical Parameter Baseline",
            "problem": "Extract EA, f, R, L, J, and b from the supplementary document and check whether the model parameters are inside the paper/supplement ranges.",
            "route": "POST /validate/part/1",
        },
        {
            "id": "part-2",
            "title": "Section 2 Equation Reproduction",
            "problem": "Map each Section 2 equation to backend functions and compare simulated derivatives against paper equations.",
            "route": "planned",
        },
        {
            "id": "part-3",
            "title": "Logging-Rate Validation",
            "problem": "Validate the Tlog bias-variance result and compare RMSE_theta against paper values.",
            "route": "POST /validate/logging-rate",
        },
        {
            "id": "part-4",
            "title": "Excitation Design Validation",
            "problem": "Compare ET1, ET3, ET6, E_Toggle, and EVR against paper convergence/RMSE findings.",
            "route": "POST /validate/excitation",
        },
        {
            "id": "part-5",
            "title": "Drift Sensitivity Validation",
            "problem": "Compare EA, f, and J drift with paper drift dominance findings.",
            "route": "POST /validate/drift",
        },
        {
            "id": "part-6",
            "title": "Retuning Validation",
            "problem": "Compare CS-BO(30), HGS-only, HGS+BO(5), and HGS+BO(10) against paper retuning budgets and costs.",
            "route": "POST /retune",
        },
    ]


def _range_midpoint(bounds: list[float]) -> float:
    return 0.5 * (float(bounds[0]) + float(bounds[1]))


def _range_status(value: float, bounds: list[float]) -> bool:
    return float(bounds[0]) <= value <= float(bounds[1])


def _relative_difference(value: float, reference: float) -> float:
    if abs(reference) < 1e-12:
        return 0.0 if abs(value) < 1e-12 else float("inf")
    return (value - reference) / reference


def run_part_1_parameter_validation(
    params: R2RParameters | None = None,
    selected_plant: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_params = params or R2RParameters()
    reference = load_paper_reference()
    table_s4 = reference["table_s4_physics_credibility"]["parameters"]
    l_reference = reference["table_s13_matrix_structure"]["parameters"]["L_m"]
    ea_plants = reference["table_s12_heterogeneous_plants"]["plants"]
    selected_ea_plant = selected_plant or ea_plants[0]

    model_values = {
        "EA_N": float(active_params.EA),
        "R_m": mean(active_params.roller_radius_m),
        "L_m": mean(active_params.span_length_m),
        "J_kg_m2": mean(active_params.inertia_kg_m2),
        "f_viscous": mean(active_params.kf),
        "b_process_noise": float(active_params.process_noise_b),
    }
    paper_specs = {
        "EA_N": {
            "reference_value": selected_ea_plant["EA_N"],
            "range": table_s4["EA_N"]["range"],
        },
        "R_m": {
            "reference_value": _range_midpoint(table_s4["R_m"]["range"]),
            "range": table_s4["R_m"]["range"],
        },
        "L_m": {
            "reference_value": l_reference["nominal"],
            "range": [0.8, 1.2],
        },
        "J_kg_m2": {
            "reference_value": _range_midpoint(table_s4["J_kg_m2"]["range"]),
            "range": table_s4["J_kg_m2"]["range"],
        },
        "f_viscous": {
            "reference_value": _range_midpoint(table_s4["f_viscous"]["range"]),
            "range": table_s4["f_viscous"]["range"],
        },
        "b_process_noise": {
            "reference_value": _range_midpoint(table_s4["b_process_noise"]["range"]),
            "range": table_s4["b_process_noise"]["range"],
        },
    }

    comparison_table: list[dict[str, Any]] = []
    for name, value in model_values.items():
        spec = paper_specs[name]
        reference_value = float(spec["reference_value"])
        abs_diff = value - reference_value
        rel_diff = _relative_difference(value, reference_value)
        in_range = _range_status(value, spec["range"])
        comparison_table.append(
            {
                "parameter": name,
                "model_value": value,
                "paper_reference": reference_value,
                "paper_range_min": float(spec["range"][0]),
                "paper_range_max": float(spec["range"][1]),
                "absolute_difference": abs_diff,
                "relative_difference_percent": rel_diff * 100.0,
                "in_paper_range": in_range,
            }
        )

    sim = simulate(
        active_params,
        config=SimulationConfig(duration_s=2.0, log_sample_time_s=0.010, output_name="part1_parameter_baseline.csv"),
        output_dir=DATA_DIR,
    )
    plot_rows = [
        {
            "parameter": row["parameter"],
            "abs_percent_diff": abs(float(row["relative_difference_percent"])),
        }
        for row in comparison_table
    ]
    plot_path = write_bar_chart(
        plot_rows,
        FIGURES_DIR / "part1_parameter_difference.svg",
        title="Part 1 Parameter Difference vs Supplement Reference",
        category_key="parameter",
        value_key="abs_percent_diff",
        y_label="Absolute percent difference",
    )

    metrics = {
        "part_id": "part-1",
        "parameters_checked": len(comparison_table),
        "in_range_count": sum(1 for row in comparison_table if row["in_paper_range"]),
        "out_of_range_count": sum(1 for row in comparison_table if not row["in_paper_range"]),
        "nominal_simulation_tension_rmse_N": sim.metrics["tension_rmse_N"],
        "nominal_simulation_control_effort_rms_V": sim.metrics["control_effort_rms_V"],
    }
    payload: dict[str, Any] = {
        "part": validation_parts_registry()[0],
        "metrics": metrics,
        "comparison_table": comparison_table,
        "paper_extract": {
            "table_s4": reference["table_s4_physics_credibility"],
            "table_s12_selected_plant": selected_ea_plant,
            "table_s13_L_note": l_reference,
        },
        "selected_plant": selected_ea_plant,
        "csv_path": sim.csv_path,
        "plot_path": plot_path,
    }

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = SUMMARY_DIR / "part1_parameter_validation.json"
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path = SUMMARY_DIR / "part1_parameter_validation.md"
    markdown_path.write_text(_render_part_1_markdown(payload), encoding="utf-8")
    payload["summary_path"] = str(summary_path)
    payload["markdown_path"] = str(markdown_path)
    return payload


def _render_part_1_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Part 1: Physical Parameter Baseline",
        "",
        "## Problem",
        "",
        payload["part"]["problem"],
        "",
        "## Result",
        "",
        f"- Parameters checked: `{payload['metrics']['parameters_checked']}`",
        f"- In paper/supplement range: `{payload['metrics']['in_range_count']}`",
        f"- Out of range: `{payload['metrics']['out_of_range_count']}`",
        f"- Nominal simulation tension RMSE: `{payload['metrics']['nominal_simulation_tension_rmse_N']}` N",
        f"- Nominal simulation control effort RMS: `{payload['metrics']['nominal_simulation_control_effort_rms_V']}` V",
        "",
        "## Paper Difference Table",
        "",
        "| Parameter | Model value | Paper reference | Paper range | Absolute difference | Relative difference (%) | In range |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload["comparison_table"]:
        lines.append(
            "| {parameter} | {model_value:.6g} | {paper_reference:.6g} | {paper_range_min:.6g}-{paper_range_max:.6g} | {absolute_difference:.6g} | {relative_difference_percent:.3f} | {in_paper_range} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Extracted Supplement References",
            "",
            "- Table S4, page 4: physics credibility checklist and parameter ranges.",
            "- Table S12, page 21: heterogeneous plant EA values; the selected plant is used as the EA paper reference for this part.",
            "- Table S13, page 22: state-space matrix structure and the note that L is approximately 1 m.",
            "",
            "## Interpretation",
            "",
            "The six basic model parameters are compared with extracted supplement ranges and the selected plant EA reference. Some selected plants have EA values outside the Table S4 physics-credibility range, which is useful to surface because the supplement uses Table S12 to study heterogeneous plants beyond the narrow baseline range.",
            "",
        ]
    )
    return "\n".join(lines)
