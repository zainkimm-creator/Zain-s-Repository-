# R2R System-Identification Dashboard

Backend-supported dashboard for validating a roll-to-roll web tension control paper. The project reproduces the paper's equations, controller, simulation results, SysID findings, drift studies, and retuning workflow before exposing them through a FastAPI backend and React dashboard.

## Validation Targets

- R2R governing equations:
  - Tension dynamics
  - Roller velocity dynamics
- Cascade PI plus feedforward controller
- Seven SysID parameters:
  - `kt_UW`, `kt_Nip`, `kt_RW`
  - `kf_UW`, `kf_Nip`, `kf_RW`
  - `EA`
- Logging-rate study over `Tlog = [1, 2, 5, 10, 20, 50, 100] ms`
- Excitation-design study for `ET1`, `ET3`, `ET6`, `E_Toggle`, and `EVR`
- Drift study for `EA`, friction `f`, and reel inertia `J`
- Retuning study for `CS-BO(30)`, `HGS-only`, `HGS+BO(5)`, and `HGS+BO(10)`
- Plant selection for the ten supplement Table S12 plants `P01` through `P10`

## Required Build Order

1. Equations
2. Controller
3. Simulation
4. SysID
5. Validation
6. Retuning
7. API
8. Dashboard
9. Testing/report

The frontend should not be built before the mathematical model, controller, simulation, SysID, validation, and retuning layers are in place.

## Project Structure

```text
r2r-dashboard/
|-- AGENTS.md
|-- README.md
|-- backend/
|   |-- api/
|   |-- models/
|   |-- sysid/
|   |-- validation/
|   `-- tests/
|-- frontend/
|   |-- src/
|   `-- components/
|-- frontend-html/
|   `-- index.html
|-- data/
|   |-- raw_physical/
|   |-- paper_reference/
|   |-- uploads/
|   `-- processed/
|-- configs/
|-- scripts/
|-- notebooks/
`-- reports/
    |-- figures/
    `-- validation_summary/
```

## Planned Backend API

- `POST /simulate`
- `POST /sysid`
- `POST /validate/logging-rate`
- `POST /validate/excitation`
- `POST /validate/drift`
- `POST /retune`
- `GET /plants`

Each route should accept JSON input and return metrics, CSV output paths, and plot paths when applicable.
Workflow routes also return `calculation_summary` and `calculations`, which the dashboard shows through the result-panel `Calculation` action.
Workflow routes accept `plant_id` so the selected supplement plant is applied consistently across simulation, SysID, validation, and retuning.

## Backend Run Commands

```powershell
python -m pip install -r requirements.txt
python -m pytest
python scripts/run_simulation.py
python scripts/run_part1_parameters.py
python scripts/run_sysid.py
python scripts/run_validation_logging_rate.py
python scripts/run_validation_excitation.py
python scripts/run_validation_drift.py
python scripts/run_retuning.py
python scripts/generate_validation_report.py
python -m uvicorn backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

## Frontend Run Commands

```powershell
cd frontend
npm install
npm run dev -- --port 5173
```

The dashboard expects the API at `http://127.0.0.1:8000` by default. The API base URL can be edited from the dashboard header.

## HTML Frontend and Uploads

The plain HTML frontend is available at `frontend-html/index.html`. When dashboard behavior changes, update the React frontend and this HTML file so the HTML version stays current.

Uploaded files are saved under `data/uploads/` through:

```text
POST /upload
```

The upload form field must be named `file`.

## Equation Inspection

Backend equation source:

- `backend/models/equations.py`

API equation route:

- `GET /equations`

Dashboard equation page:

- `Equations`

## Full Guide and Validation Report

Read the full project guide here:

- `GUIDE.md`

It explains how the site works, how backend validation is performed, where outputs are saved, how to add the research paper as a strict reference, and how each paper-style question is answered.

## Implemented Outputs

- Simulation CSV files are written to `data/processed/`.
- Uploaded input files are written to `data/uploads/`.
- Validation plots are written to `reports/figures/` as SVG files.
- Validation metrics are written to `reports/validation_summary/` as JSON files.
- Dashboard result panels include worked Calculation examples for simulation metrics, paper-parameter checks, SysID errors, validation selections, and retuning costs.
- The Plants tab lists the ten supplementary plants and sends the selected plant to every run workflow.
- The consolidated validation report is written to `reports/validation_summary/validation_report.md` and `.json`.
- API artifact URLs are served under `/artifacts/...`.

## Current Assumptions

- The implementation uses a reduced three-span R2R model until exact paper equations and physical constants are placed in `data/paper_reference/`.
- Plant-specific `EA_N` values come from supplement Table S12. Exact per-roller arrays for `R`, `L`, `J`, `f`, and `b` are not present in the extracted JSON, so baseline arrays are retained until those arrays are supplied.
- The SysID workflow estimates the required seven parameters from one-step finite-difference prediction-error least squares.
- Retuning uses deterministic candidate searches that represent `CS-BO(30)`, `HGS-only`, `HGS+BO(5)`, and `HGS+BO(10)` with explicit real-evaluation counts.
