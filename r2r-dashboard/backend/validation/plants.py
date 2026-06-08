"""Plant presets extracted from the supplementary reference."""

from __future__ import annotations

from dataclasses import replace
from math import sqrt
from typing import Any

from backend.models.equations import R2RParameters
from backend.validation.paper_reference import load_paper_reference

DEFAULT_PLANT_ID = "P01"
BASELINE_EA_N = 3200.0
BASELINE_EXCITATION_AMPLITUDE_V = 0.08
BASELINE_EA_RANGE_MAX_N = 12000.0


def _recommended_excitation_amplitude(ea_n: float) -> float:
    if ea_n > BASELINE_EA_RANGE_MAX_N:
        return 0.0
    return round(BASELINE_EXCITATION_AMPLITUDE_V * min(1.0, sqrt(BASELINE_EA_N / ea_n)), 6)


def _plant_rows() -> list[dict[str, Any]]:
    reference = load_paper_reference()
    return list(reference["table_s12_heterogeneous_plants"]["plants"])


def plant_registry() -> list[dict[str, Any]]:
    """Return display-ready plant metadata from supplement Table S12."""

    params = R2RParameters()
    plants = []
    for row in _plant_rows():
        plant_id = str(row["plant"])
        ea_n = float(row["EA_N"])
        in_baseline_range = ea_n <= BASELINE_EA_RANGE_MAX_N
        plants.append(
            {
                "plant": plant_id,
                "plant_id": plant_id,
                "label": f"{plant_id} | {row['material']} {row['scale']} | EA={ea_n:g} N",
                "EA_N": ea_n,
                "material": row["material"],
                "scale": row["scale"],
                "regime": row["regime"],
                "zeta_cl_min": float(row["zeta_cl_min"]),
                "overshoot_percent": float(row["overshoot_percent"]),
                "recommended_excitation_amplitude_V": _recommended_excitation_amplitude(ea_n),
                "baseline_range_compatible": in_baseline_range,
                "roller_radius_m": list(params.roller_radius_m),
                "span_length_m": list(params.span_length_m),
                "inertia_kg_m2": list(params.inertia_kg_m2),
                "viscous_friction": list(params.kf),
                "process_noise_b": params.process_noise_b,
                "simulation_note": (
                    "Within extracted Table S4 EA range; recommended excitation is scaled from the P01 input."
                    if in_baseline_range
                    else "EA is outside the extracted Table S4 baseline range; use zero excitation or supply exact per-roller arrays/retuned inputs before dynamic validation."
                ),
            }
        )
    return plants


def get_plant(plant_id: str | None = None) -> dict[str, Any]:
    """Return one Table S12 plant by id."""

    selected_id = (plant_id or DEFAULT_PLANT_ID).strip()
    for plant in plant_registry():
        if plant["plant_id"] == selected_id:
            return plant
    valid = ", ".join(plant["plant_id"] for plant in plant_registry())
    raise ValueError(f"Unknown plant_id '{selected_id}'. Valid plants: {valid}.")


def parameters_for_plant(plant_id: str | None = None) -> tuple[R2RParameters, dict[str, Any]]:
    """Return model parameters with plant-specific EA applied."""

    plant = get_plant(plant_id)
    params = replace(R2RParameters(), EA=float(plant["EA_N"]))
    return params, {
        **plant,
        "applied_parameters": {
            "EA_N": params.EA,
            "roller_radius_m": list(params.roller_radius_m),
            "span_length_m": list(params.span_length_m),
            "inertia_kg_m2": list(params.inertia_kg_m2),
            "viscous_friction": list(params.kf),
            "process_noise_b": params.process_noise_b,
        },
    }
