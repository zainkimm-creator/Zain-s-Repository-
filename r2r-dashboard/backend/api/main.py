"""FastAPI routes for simulation, SysID, validation, and retuning workflows."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.models.equations import R2RParameters, equation_summary
from backend.models.simulation import DEFAULT_DATA_DIR, SimulationConfig, simulate
from backend.sysid.estimator import estimate_parameters, load_rows_from_csv
from backend.validation.calculations import (
    drift_calculation_payload,
    excitation_calculation_payload,
    logging_rate_calculation_payload,
    part1_calculation_payload,
    retuning_calculation_payload,
    simulation_calculation_payload,
    sysid_calculation_payload,
)
from backend.validation.excitations import excitation_names, get_excitation_profile
from backend.validation.parts import run_part_1_parameter_validation, validation_parts_registry
from backend.validation.plants import DEFAULT_PLANT_ID, parameters_for_plant, plant_registry
from backend.validation.studies import (
    drift_study,
    excitation_study,
    logging_rate_study,
    retuning_study,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"

app = FastAPI(
    title="R2R System-Identification Dashboard API",
    version="0.1.0",
    description="Backend API for R2R simulation, SysID, validation, and retuning studies.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/artifacts", StaticFiles(directory=str(PROJECT_ROOT)), name="artifacts")


class SimulationRequest(BaseModel):
    plant_id: str | None = DEFAULT_PLANT_ID
    duration_s: float = Field(default=4.0, gt=0)
    dt_ms: float = Field(default=1.0, gt=0)
    controller_sample_time_ms: float = Field(default=10.0, gt=0)
    log_sample_time_ms: float = Field(default=10.0, gt=0)
    line_speed_m_s: float = Field(default=1.0, gt=0)
    excitation: str = "ET3"
    excitation_amplitude_V: float = 0.08
    sensor_noise_tension_N: float = Field(default=0.0, ge=0)
    sensor_noise_omega_rad_s: float = Field(default=0.0, ge=0)
    seed: int = 7
    output_name: str = "api_simulation.csv"


class SysIDRequest(BaseModel):
    plant_id: str | None = DEFAULT_PLANT_ID
    csv_path: str | None = None
    duration_s: float = Field(default=4.0, gt=0)
    log_sample_time_ms: float = Field(default=10.0, gt=0)
    excitation: str = "E_Toggle"
    excitation_amplitude_V: float = 0.08
    sensor_noise_tension_N: float = Field(default=0.0, ge=0)
    sensor_noise_omega_rad_s: float = Field(default=0.0, ge=0)


class LoggingRateRequest(BaseModel):
    plant_id: str | None = DEFAULT_PLANT_ID
    tlog_ms_values: list[int] | None = None


class EmptyRequest(BaseModel):
    plant_id: str | None = DEFAULT_PLANT_ID


def _artifact_url(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value).resolve()
    try:
        rel = path.relative_to(PROJECT_ROOT)
    except ValueError:
        return None
    return f"/artifacts/{rel.as_posix()}"


def _attach_urls(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("csv_path", "xlsx_path", "plot_path", "summary_path", "markdown_path"):
        if key in payload:
            payload[key.replace("_path", "_url")] = _artifact_url(payload.get(key))
    return payload


def _preview_rows(rows: Sequence[dict[str, float]], limit: int = 8) -> list[dict[str, float]]:
    if len(rows) <= limit:
        return list(rows)
    half = max(1, limit // 2)
    return list(rows[:half]) + list(rows[-half:])


def _plant_params_or_400(plant_id: str | None) -> tuple[R2RParameters, dict[str, Any]]:
    try:
        return parameters_for_plant(plant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run_or_422(label: str, fn: Any) -> Any:
    try:
        return fn()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{label} became numerically invalid: {exc}") from exc


def _assert_finite_numbers(value: Any, label: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int | float):
        if not math.isfinite(float(value)):
            raise HTTPException(
                status_code=422,
                detail=f"{label} produced a non-finite value. Reduce excitation amplitude or select a baseline-range plant.",
            )
        return
    if isinstance(value, dict):
        for item in value.values():
            _assert_finite_numbers(item, label)
        return
    if isinstance(value, list | tuple):
        for item in value:
            _assert_finite_numbers(item, label)


def _safe_upload_path(filename: str | None) -> Path:
    safe_name = Path(filename or "").name
    if not safe_name:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
    return UPLOAD_DIR / safe_name


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def dashboard_redirect() -> RedirectResponse:
    return RedirectResponse("http://127.0.0.1:5173/")


@app.get("/equations")
def equations() -> dict[str, object]:
    return equation_summary()


@app.get("/plants")
def plants_route() -> dict[str, object]:
    return {
        "default_plant_id": DEFAULT_PLANT_ID,
        "plants": plant_registry(),
        "note": "Plant presets come from supplement Table S12. Current extracted data gives plant-specific EA_N and metadata; baseline R, L, J, f, and b arrays are retained until exact per-roller arrays are supplied. High-EA plants outside the baseline range default to zero excitation for numerical safety.",
    }


@app.post("/simulate")
def simulate_route(request: SimulationRequest) -> dict[str, object]:
    params, plant = _plant_params_or_400(request.plant_id)
    config = SimulationConfig(
        duration_s=request.duration_s,
        dt_s=request.dt_ms / 1000.0,
        controller_sample_time_s=request.controller_sample_time_ms / 1000.0,
        log_sample_time_s=request.log_sample_time_ms / 1000.0,
        line_speed_m_s=request.line_speed_m_s,
        sensor_noise_tension_N=request.sensor_noise_tension_N,
        sensor_noise_omega_rad_s=request.sensor_noise_omega_rad_s,
        seed=request.seed,
        output_name=request.output_name,
    )
    result = _run_or_422(
        "Simulation",
        lambda: simulate(
            params,
            config=config,
            excitation=get_excitation_profile(request.excitation, request.excitation_amplitude_V),
            output_dir=DEFAULT_DATA_DIR,
        ),
    )
    _assert_finite_numbers(result.metrics, "Simulation metrics")
    payload: dict[str, Any] = {
        "metrics": result.metrics,
        "csv_path": result.csv_path,
        "xlsx_path": result.xlsx_path,
        "plot_path": None,
        "plant": plant,
        "equation_sample": result.equation_sample,
        "preview_rows": _preview_rows(result.rows),
    }
    payload.update(simulation_calculation_payload(result.metrics, result.rows, config, params))
    return _attach_urls(payload)


@app.post("/sysid")
def sysid_route(request: SysIDRequest) -> dict[str, object]:
    params, plant = _plant_params_or_400(request.plant_id)
    csv_path = request.csv_path
    if csv_path:
        rows = load_rows_from_csv(csv_path)
    else:
        sim = _run_or_422(
            "SysID source simulation",
            lambda: simulate(
                params,
                config=SimulationConfig(
                    duration_s=request.duration_s,
                    log_sample_time_s=request.log_sample_time_ms / 1000.0,
                    sensor_noise_tension_N=request.sensor_noise_tension_N,
                    sensor_noise_omega_rad_s=request.sensor_noise_omega_rad_s,
                    output_name="api_sysid_source.csv",
                ),
                excitation=get_excitation_profile(request.excitation, request.excitation_amplitude_V),
                output_dir=DEFAULT_DATA_DIR,
            ),
        )
        _assert_finite_numbers(sim.metrics, "SysID source simulation metrics")
        rows = sim.rows
        csv_path = sim.csv_path
    result = _run_or_422(
        "SysID estimation",
        lambda: estimate_parameters(rows, params, params, summary_name="api_sysid_result.json"),
    )
    _assert_finite_numbers(result.to_dict(), "SysID result")
    metrics = {"RMSE_theta": result.rmse_theta, "samples": len(rows)}
    payload: dict[str, Any] = {
        "metrics": metrics,
        "estimates": result.estimates,
        "error_table": result.error_table,
        "plant": plant,
        "csv_path": csv_path,
        "plot_path": None,
        "summary_path": result.summary_path,
    }
    payload.update(sysid_calculation_payload(metrics, result.error_table))
    return _attach_urls(payload)


@app.post("/validate/logging-rate")
def logging_rate_route(request: LoggingRateRequest) -> dict[str, object]:
    params, plant = _plant_params_or_400(request.plant_id)
    payload = _run_or_422("Logging-rate study", lambda: logging_rate_study(request.tlog_ms_values, params=params))
    _assert_finite_numbers(payload, "Logging-rate study")
    payload["plant"] = plant
    payload.update(logging_rate_calculation_payload(payload))
    return _attach_urls(payload)


@app.get("/validation/parts")
def validation_parts_route() -> dict[str, object]:
    return {"parts": validation_parts_registry()}


@app.post("/validate/part/1")
def validation_part_1_route(_: EmptyRequest | None = None) -> dict[str, object]:
    request = _ or EmptyRequest()
    params, plant = _plant_params_or_400(request.plant_id)
    payload = _run_or_422(
        "Part 1 parameter validation",
        lambda: run_part_1_parameter_validation(params=params, selected_plant=plant),
    )
    _assert_finite_numbers(payload["metrics"], "Part 1 metrics")
    payload["plant"] = plant
    payload.update(part1_calculation_payload(payload))
    return _attach_urls(payload)


@app.post("/validate/excitation")
def excitation_route(_: EmptyRequest | None = None) -> dict[str, object]:
    request = _ or EmptyRequest()
    params, plant = _plant_params_or_400(request.plant_id)
    payload = _run_or_422("Excitation study", lambda: excitation_study(params=params))
    _assert_finite_numbers(payload, "Excitation study")
    payload["plant"] = plant
    payload.update(excitation_calculation_payload(payload))
    return _attach_urls(payload)


@app.post("/validate/drift")
def drift_route(_: EmptyRequest | None = None) -> dict[str, object]:
    request = _ or EmptyRequest()
    params, plant = _plant_params_or_400(request.plant_id)
    payload = _run_or_422("Drift study", lambda: drift_study(params=params))
    _assert_finite_numbers(payload, "Drift study")
    payload["plant"] = plant
    payload.update(drift_calculation_payload(payload))
    return _attach_urls(payload)


@app.post("/retune")
def retune_route(_: EmptyRequest | None = None) -> dict[str, object]:
    request = _ or EmptyRequest()
    params, plant = _plant_params_or_400(request.plant_id)
    payload = _run_or_422("Retuning study", lambda: retuning_study(params=params))
    _assert_finite_numbers(payload, "Retuning study")
    payload["plant"] = plant
    payload.update(retuning_calculation_payload(payload))
    return _attach_urls(payload)


@app.get("/metadata")
def metadata() -> dict[str, object]:
    return {
        "excitation_profiles": list(excitation_names()),
        "default_plant_id": DEFAULT_PLANT_ID,
        "plants": plant_registry(),
        "state_vector": equation_summary()["state_vector"],
        "input_vector": equation_summary()["input_vector"],
        "routes": [
            "POST /simulate",
            "POST /sysid",
            "GET /plants",
            "GET /validation/parts",
            "POST /validate/part/1",
            "POST /validate/logging-rate",
            "POST /validate/excitation",
            "POST /validate/drift",
            "POST /retune",
            "POST /upload",
        ],
    }


@app.post("/upload")
async def upload_data_file(file: UploadFile = File(...)) -> dict[str, object]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = _safe_upload_path(file.filename)
    contents = await file.read()
    destination.write_bytes(contents)
    rel_path = destination.relative_to(PROJECT_ROOT)
    return {
        "filename": destination.name,
        "bytes": len(contents),
        "path": str(destination),
        "url": f"/artifacts/{rel_path.as_posix()}",
    }
