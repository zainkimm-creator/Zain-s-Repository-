# R2R Dashboard Guide and Research Validation Report

## Table of Contents

1. [Purpose](#1-purpose)
2. [Current Scope and Important Assumption](#2-current-scope-and-important-assumption)
3. [System Overview](#3-system-overview)
4. [How the Site Works](#4-how-the-site-works)
5. [Backend Architecture](#5-backend-architecture)
6. [Frontend Architecture](#6-frontend-architecture)
7. [Research Paper Validation Workflow](#7-research-paper-validation-workflow)
8. [Validation Target Traceability](#8-validation-target-traceability)
9. [Equation and Unit Reference](#9-equation-and-unit-reference)
10. [Simulation Workflow](#10-simulation-workflow)
11. [System Identification Workflow](#11-system-identification-workflow)
12. [Logging-Rate Study](#12-logging-rate-study)
13. [Excitation-Design Study](#13-excitation-design-study)
14. [Drift Study](#14-drift-study)
15. [Retuning Study](#15-retuning-study)
16. [API Reference](#16-api-reference)
17. [Generated Files and Reports](#17-generated-files-and-reports)
18. [How to Run the Project](#18-how-to-run-the-project)
19. [How to Test the Project](#19-how-to-test-the-project)
20. [How to Add the Paper as a Strict Reference](#20-how-to-add-the-paper-as-a-strict-reference)
21. [Frequently Asked Questions](#21-frequently-asked-questions)
22. [Known Limitations](#22-known-limitations)

## 1. Purpose

This project is a backend-supported dashboard for validating a roll-to-roll web tension control research paper. It is designed to reproduce the paper-style workflow:

- Define the governing roll-to-roll equations.
- Implement cascade PI plus feedforward control.
- Simulate the closed-loop plant.
- Estimate the seven requested SysID parameters.
- Run validation studies for logging rate, excitation design, drift, and retuning.
- Expose all workflows through FastAPI and a React dashboard.
- Save generated data, plots, and summary reports for comparison against the paper.

## 2. Current Scope and Important Assumption

The code implements a reduced three-span roll-to-roll model and now exposes the extracted main-paper, supplementary, and DOCX equation register in the dashboard. The model equations are mapped to the paper equations, while the runnable simulator keeps a reduced implementation for fast validation and step-by-step inspection.

Paper reference material is tracked under:

- `data/paper_reference/`

The current reference JSON includes supplement Table S4 ranges and Table S12 plants. Strict reproduction of the paper figures still requires exact per-roller arrays, original plot data, and final paper tolerances where those are not present in the extracted JSON.

## 3. System Overview

```text
React Dashboard
      |
      | JSON requests
      v
FastAPI Backend
      |
      | calls
      v
Models, Controller, Simulation, SysID, Validation, Retuning
      |
      | writes
      v
data/processed/ and reports/
```

Main runtime pieces:

| Layer | Location | Responsibility |
|---|---|---|
| Mathematical model | `backend/models/equations.py` | R2R state, input, tension dynamics, roller dynamics, units |
| Controller | `backend/models/controller.py` | Cascade PI plus feedforward torque |
| Simulation | `backend/models/simulation.py` | RK4 integration, zero-order hold, logging, CSV export |
| SysID | `backend/sysid/estimator.py` | One-step prediction-error parameter estimation |
| Validation studies | `backend/validation/studies.py` | Logging-rate, excitation, drift, retuning workflows |
| API | `backend/api/main.py` | FastAPI routes for dashboard and scripts |
| UI | `frontend/src/App.jsx` | Dashboard pages and API interaction |
| Reports | `reports/validation_summary/` | JSON and Markdown validation summaries |
| Figures | `reports/figures/` | SVG plots and UI screenshots |

## 4. How the Site Works

The site is a React dashboard that calls FastAPI endpoints. Each page is tied to a backend workflow.

| Dashboard Page | Backend Route | What It Does | Main Output |
|---|---|---|---|
| Simulation | `POST /simulate` | Shows the labeled R2R schematic and runs closed-loop RK4 simulation | Schematic, metrics, CSV path, preview table, calculation examples |
| Paper parts | `POST /validate/part/1` | Runs modular paper-validation Part 1 | Parameter comparison table, plot, summary, one calculation per basic parameter |
| Plants | `GET /plants` | Lists supplement Table S12 plants and selects the active plant preset | Plant table, selected plant summary, applied parameter note |
| SysID | `POST /sysid` | Estimates seven SysID parameters | Estimates, error table, RMSE_theta, one calculation per estimated parameter |
| Logging rate | `POST /validate/logging-rate` | Sweeps `Tlog` values | RMSE plot, JSON summary, noisy optimum calculation |
| Excitation | `POST /validate/excitation` | Compares excitation profiles | Bar chart, JSON summary, best excitation calculation |
| Drift | `POST /validate/drift` | Compares `EA`, `f`, and `J` drift | Degradation chart, JSON summary, dominant drift calculation |
| Retuning | `POST /retune` | Compares retuning strategies | Cost table, JSON summary, cost and evaluation-budget calculations |
| Equations | `GET /equations` | Shows paper, supplement, DOCX, model, derivation, and unit equations | Paper equation register and implementation mapping |

The frontend default API base URL is:

- `http://127.0.0.1:8000`

The dashboard runs at:

- `http://localhost:5173`

The API serves generated artifacts through:

- `/artifacts/...`

For example, a generated plot can be opened from the dashboard using a URL like:

- `http://127.0.0.1:8000/artifacts/reports/figures/logging_rate_vs_rmse.svg`

## 5. Backend Architecture

The backend is intentionally organized in the same order as the required development rule:

1. Equations
2. Controller
3. Simulation
4. SysID
5. Validation
6. Retuning
7. API
8. Dashboard
9. Testing/report

Important backend files:

| File | Why It Exists |
|---|---|
| `backend/models/equations.py` | Single source of truth for model equations, parameters, state order, input order, and units |
| `backend/models/controller.py` | Implements the cascade PI plus feedforward controller |
| `backend/models/simulation.py` | Runs RK4 simulation with controller sample time and logging sample time |
| `backend/sysid/estimator.py` | Estimates the seven paper-requested SysID parameters |
| `backend/validation/excitations.py` | Defines `ET1`, `ET3`, `ET6`, `E_Toggle`, and `EVR` |
| `backend/validation/studies.py` | Runs paper-style validation studies |
| `backend/validation/plants.py` | Loads supplement Table S12 plant presets and applies selected plant EA |
| `backend/api/main.py` | Exposes the workflows as JSON API routes |

## 6. Frontend Architecture

The frontend is a Vite React application.

Important frontend files:

| File | Why It Exists |
|---|---|
| `frontend/src/App.jsx` | Page navigation, forms, route calls, equation page |
| `frontend/src/api.js` | API helpers and artifact URL handling |
| `frontend/src/styles.css` | Dashboard layout and visual styling |
| `frontend/components/ResultPanel.jsx` | Shared result, plot, table, download, and Calculation display |
| `frontend/components/MetricTable.jsx` | Shared metric/error table rendering |
| `frontend/components/RunButton.jsx` | Shared action button |

The UI is designed as an engineering dashboard rather than a landing page. It puts the working tools on the first screen and exposes plots, metrics, and downloadable artifacts directly.

The Plants page uses supplement Table S12 to select among `P01` through `P10`. The selected plant is sent as `plant_id` to runnable workflows. Current extracted data includes plant-specific `EA_N` and plant metadata; the exact per-roller arrays for `R`, `L`, `J`, `f`, and `b` are not present in the extracted JSON, so those arrays remain at the current baseline until supplied.

For plants whose `EA_N` is outside the extracted Table S4 baseline range, the UI sets the recommended excitation amplitude to `0` by default. This avoids numerically invalid reduced-model runs while still allowing the plant to be selected and inspected.

## 7. Research Paper Validation Workflow

The dashboard validates the research paper through this evidence chain:

1. Paper equations and constants are represented in backend model code.
2. The controller reproduces the paper-style cascade PI plus feedforward structure.
3. The simulation produces time-series CSV data under configurable sampling and logging.
4. SysID estimates the seven requested parameters from simulation or logged data.
5. Validation studies reproduce paper-style claims:
   - Best noisy logging rate near `10-20 ms`
   - Better SysID from multi-channel excitation under noise
   - Dominant degradation from reel inertia `J` drift
   - Fewer real evaluations for `HGS+BO(5)` than `CS-BO(30)`
6. Plots and metrics are written into `reports/`.
7. The dashboard exposes the same outputs interactively.

This is not just a visualization site. The frontend triggers the same backend validation functions used by scripts and tests.

## 8. Validation Target Traceability

| Paper Validation Target | Implemented Where | Output Evidence |
|---|---|---|
| Tension dynamics | `backend/models/equations.py` | `GET /equations`, Equations UI page |
| Roller velocity dynamics | `backend/models/equations.py` | `GET /equations`, Equations UI page |
| Cascade PI plus feedforward controller | `backend/models/controller.py` | Simulation metrics and tests |
| State vector `x = [T1, T2, T3, omega_UW, omega_Nip, omega_RW]` | `backend/models/equations.py` | `STATE_NAMES`, `GET /equations` |
| Input vector `u = [u_UW, u_Nip, u_RW]` | `backend/models/equations.py` | `INPUT_NAMES`, `GET /equations` |
| Seven SysID parameters | `backend/sysid/estimator.py` | SysID route, error table, tests |
| Logging-rate sweep | `backend/validation/studies.py` | `logging_rate_summary.json`, `logging_rate_vs_rmse.svg` |
| Excitation comparison | `backend/validation/studies.py` and `excitations.py` | `excitation_summary.json`, `excitation_vs_rmse.svg` |
| Drift comparison | `backend/validation/studies.py` | `drift_summary.json`, `drift_degradation.svg` |
| Retuning comparison | `backend/validation/studies.py` | `retuning_summary.json`, `retuning_cost.svg` |
| Modular validation parts | `backend/validation/parts.py` | `part1_parameter_validation.json`, `part1_parameter_difference.svg` |
| Backend API | `backend/api/main.py` | FastAPI routes and API tests |
| Dashboard UI | `frontend/src/App.jsx` | Local UI at `http://localhost:5173` |
| Tests and reports | `backend/tests/`, `scripts/generate_validation_report.py` | `pytest`, `validation_report.md` |

## 9. Equation and Unit Reference

Primary source:

- `backend/models/equations.py`

API display:

- `GET /equations`

Dashboard display:

- Equations page

The Equations page includes a Backend Equation Register. It now lists only equations used by the backend to produce dashboard results:

- Web transport kinematics
- Reduced three-span tension dynamics
- Web torque balance on rollers
- Roller velocity dynamics
- Outer tension PI correction
- Velocity reference coupling
- Inner velocity PI plus feedforward
- RK4 state update
- Simulation RMSE and effort metrics
- SysID roller, EA, and `RMSE_theta` equations

Formula text is styled with the document-style math stack:

```text
Cambria Math, Cambria, Times New Roman, serif
```

It also includes a derivation/usage flow explaining how kinematics, tension dynamics, torque balance, roller dynamics, RK4 integration, and SysID are connected.

State vector:

```text
x = [T1, T2, T3, omega_UW, omega_Nip, omega_RW]
```

Input vector:

```text
u = [u_UW, u_Nip, u_RW]
```

Reduced-model tension dynamics:

```text
dT1/dt = (EA/L1)(R_Nip*omega_Nip - R_UW*omega_UW) - lambda_T(T1 - T1_ref)
dT2/dt = (EA/L2)(R_RW*omega_RW - R_Nip*omega_Nip) - lambda_T(T2 - T2_ref)
dT3/dt = (EA/L3)(R_RW*omega_RW - 0.5(R_UW*omega_UW + R_Nip*omega_Nip)) - lambda_T(T3 - T3_ref)
```

Reduced-model roller velocity dynamics:

```text
J_UW*domega_UW/dt = kt_UW*u_UW + (T3 - T1)R_UW - kf_UW*omega_UW
J_Nip*domega_Nip/dt = kt_Nip*u_Nip + (T1 - T2)R_Nip - kf_Nip*omega_Nip
J_RW*domega_RW/dt = kt_RW*u_RW + (T2 - T3)R_RW - kf_RW*omega_RW
```

Unit reference:

| Symbol | Unit | Meaning |
|---|---|---|
| `T` | N | Web tension |
| `omega` | rad/s | Roller angular velocity |
| `u` | V | Motor voltage command |
| `R` | m | Roller radius |
| `L` | m | Web span length |
| `J` | kg*m^2 | Roller inertia |
| `kt` | N*m/V | Motor torque constant |
| `kf` | N*m*s/rad | Viscous friction coefficient |
| `EA` | N | Elastic modulus-area product |

## 10. Simulation Workflow

Primary file:

- `backend/models/simulation.py`

Frontend schematic:

- `frontend/components/R2RSchematic.jsx`

The Simulation page contains a labeled R2R transport diagram based on the paper-style layout. It labels the web direction, unwinder, feeder boundary condition, nip pair, rewinder, input voltages, angular velocities, web tensions, span lengths, tension sensors, and controller block.

Command:

```powershell
python scripts/run_simulation.py
```

The simulator:

- Uses RK4 integration.
- Uses `dt = 1 ms` by default.
- Uses controller sample time `Ts = 10 ms` by default.
- Makes `Tlog` configurable.
- Uses zero-order hold between controller updates.
- Writes CSV files to `data/processed/`.

Why RK4 is used:

- It gives better numerical stability and accuracy than forward Euler for the same time step.
- It is still simple enough to audit directly in the backend model.

Where simulation output goes:

- `data/processed/*.csv`

## 11. System Identification Workflow

Primary file:

- `backend/sysid/estimator.py`

Command:

```powershell
python scripts/run_sysid.py
```

The estimator uses one-step finite-difference prediction-error equations.

Estimated parameters:

| Parameter | Meaning |
|---|---|
| `kt_UW` | Unwinder torque constant |
| `kt_Nip` | Nip roller torque constant |
| `kt_RW` | Rewinder torque constant |
| `kf_UW` | Unwinder viscous friction |
| `kf_Nip` | Nip roller viscous friction |
| `kf_RW` | Rewinder viscous friction |
| `EA` | Web elastic modulus-area product |

Main SysID outputs:

- Parameter estimates
- Absolute error
- Relative error
- `RMSE_theta`

Why this validates the paper:

- The paper claims depend on whether the key physical parameters can be recovered under different sampling, excitation, noise, and drift conditions.
- The estimator provides a comparable error metric for every validation scenario.

## 12. Logging-Rate Study

Primary route:

- `POST /validate/logging-rate`

Primary script:

```powershell
python scripts/run_validation_logging_rate.py
```

Sweep:

```text
Tlog = [1, 2, 5, 10, 20, 50, 100] ms
```

Cases:

- Noise-free
- Sensor-noise

Outputs:

- `reports/figures/logging_rate_vs_rmse.svg`
- `reports/validation_summary/logging_rate_summary.json`

Question answered:

- Does the noisy case give the best result near `10-20 ms`?

Current generated answer:

- Yes. The generated report shows the noisy optimum at `20 ms`.

## 13. Excitation-Design Study

Primary route:

- `POST /validate/excitation`

Primary script:

```powershell
python scripts/run_validation_excitation.py
```

Excitation profiles:

| Profile | Purpose |
|---|---|
| `ET1` | Single-channel sinusoidal excitation |
| `ET3` | Three-channel multi-frequency sinusoidal excitation |
| `ET6` | Multi-channel multi-tone excitation |
| `E_Toggle` | Multi-channel toggle/square excitation |
| `EVR` | Deterministic random voltage excitation |

Outputs:

- `reports/figures/excitation_vs_rmse.svg`
- `reports/validation_summary/excitation_summary.json`

Question answered:

- Does multi-channel/toggle excitation perform better under noise?

Current generated answer:

- Yes. The generated summary marks the multi-channel condition as supported, with `ET3` currently best under the default generated run.

## 14. Drift Study

Primary route:

- `POST /validate/drift`

Primary script:

```powershell
python scripts/run_validation_drift.py
```

Compared drift scenarios:

| Scenario | Meaning |
|---|---|
| `EA` | Web stiffness drift |
| `f` | Friction drift |
| `J` | Reel inertia drift |

Outputs:

- `reports/figures/drift_degradation.svg`
- `reports/validation_summary/drift_summary.json`

Questions answered:

- Is reel inertia `J` drift dominant?
- Is `EA` drift partly absorbed by cascade feedforward?

Current generated answer:

- `J` drift is dominant under the default generated run.
- `EA` drift is lower than `J` drift in the default generated run, which is consistent with partial absorption by the cascade/feedforward structure.

## 15. Retuning Study

Primary route:

- `POST /retune`

Primary script:

```powershell
python scripts/run_retuning.py
```

Compared methods:

| Method | Meaning |
|---|---|
| `CS-BO(30)` | Cold-start Bayesian-style search with 30 real evaluations |
| `HGS-only` | Heuristic gain scheduling only |
| `HGS+BO(5)` | Heuristic gain scheduling plus 5 local search evaluations |
| `HGS+BO(10)` | Heuristic gain scheduling plus 10 local search evaluations |

Cost function:

```text
cost = RMSE + 0.25*overshoot + 0.15*t90 + 0.015*control_effort
```

Outputs:

- `reports/figures/retuning_cost.svg`
- `reports/validation_summary/retuning_summary.json`

Question answered:

- Does `HGS+BO(5)` reduce real-plant evaluations compared with `CS-BO(30)`?

Current generated answer:

- Yes. `HGS+BO(5)` uses fewer real evaluations than `CS-BO(30)` in the generated comparison.

## 16. API Reference

Run API:

```powershell
python -m uvicorn backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

Routes:

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | Confirms API is running |
| `GET` | `/metadata` | Returns route and excitation metadata |
| `GET` | `/equations` | Returns model equations, vectors, units |
| `GET` | `/plants` | Returns supplement Table S12 plant presets |
| `POST` | `/simulate` | Runs simulation |
| `POST` | `/sysid` | Runs SysID |
| `POST` | `/validate/logging-rate` | Runs logging-rate validation |
| `POST` | `/validate/excitation` | Runs excitation validation |
| `POST` | `/validate/drift` | Runs drift validation |
| `POST` | `/retune` | Runs retuning comparison |

Every workflow route returns JSON with metrics, selected `plant` metadata, a `calculation_summary`, a `calculations` list, and, where applicable, artifact paths and artifact URLs. In the dashboard, run a workflow and open the `Calculation` action above the result to see the worked examples.

## 17. Generated Files and Reports

| Output | Location |
|---|---|
| Simulation CSVs | `data/processed/` |
| Validation plots | `reports/figures/` |
| JSON summaries | `reports/validation_summary/` |
| Consolidated Markdown report | `reports/validation_summary/validation_report.md` |
| Consolidated JSON report | `reports/validation_summary/validation_report.json` |

Generate consolidated report:

```powershell
python scripts/generate_validation_report.py
```

## 18. How to Run the Project

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Start backend:

```powershell
python -m uvicorn backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

Install frontend dependencies:

```powershell
cd frontend
npm install
```

Start frontend:

```powershell
npm run dev -- --port 5173
```

Open dashboard:

```text
http://localhost:5173
```

## 19. How to Test the Project

Backend tests:

```powershell
python -m pytest
```

Frontend production build:

```powershell
cd frontend
npm run build
```

Current verified status:

- Backend tests pass.
- Frontend build passes.
- API health route returns OK.
- Dashboard loads.

## 20. How to Add Strict Paper Reference Data

Place paper reference materials here:

- `data/paper_reference/`

Recommended files:

| File | Purpose |
|---|---|
| `paper.pdf` | Original research paper |
| `paper_constants.json` | Physical constants and controller gains from the paper |
| `paper_figures_reference.csv` | Digitized paper figure data |
| `paper_tables_reference.csv` | Paper table values for comparison |
| `equation_map.md` | Mapping from paper equation numbers to code functions |

After adding the missing strict-reference data:

1. Add exact per-plant arrays for `R_i`, `J_i`, `f_i`, `L_i`, and `b_i` under `data/paper_reference/`.
2. Update `backend/validation/plants.py` to apply those arrays instead of the current baseline arrays.
3. Add digitized paper figure/table data and paper-specific tolerances.
4. Add regression tests comparing generated outputs to paper tables/figures.
5. Update `reports/validation_summary/validation_report.md` with paper-specific tolerances and references.

Reference format recommendation:

```text
Paper Eq. (X) -> backend/models/equations.py:function_name
Paper Fig. (Y) -> reports/figures/generated_plot.svg
Paper Table (Z) -> reports/validation_summary/generated_summary.json
```

## 21. Frequently Asked Questions

### How does the dashboard validate the paper?

It runs the same workflows described in the requested paper-validation targets: equations, controller, simulation, SysID, logging-rate sweep, excitation comparison, drift study, and retuning comparison. It then saves comparable metrics and plots.

### Why is the backend more important than the frontend for validation?

The validation evidence comes from backend equations, simulation, SysID, and metrics. The frontend is a control and visualization layer over that backend evidence.

### Where are the equations?

The source equations are in:

- `backend/models/equations.py`

They are also exposed through:

- `GET /equations`
- Dashboard `Equations` page

### Where are the results saved?

CSV outputs are saved in:

- `data/processed/`

Plots are saved in:

- `reports/figures/`

Summary reports are saved in:

- `reports/validation_summary/`

### What does the Calculation button show?

Each runnable dashboard tab returns worked examples from the backend. Simulation shows metric formulas such as tension RMSE and control effort RMS. Paper Part 1 shows one calculation for each basic parameter: `EA`, `R`, `L`, `J`, `f`, and `b`. SysID shows one relative-error calculation for every estimated parameter, then combines them into `RMSE_theta`. The validation tabs show the selection or scoring calculation used to decide the reported result.

### Where is the plant selection data?

The plant selector uses:

- `data/paper_reference/paper1_isa_supplement_parameters.json`
- `backend/validation/plants.py`
- `GET /plants`

The ten selected plants are from supplement Table S12. The app applies each plant's `EA_N` to the model. The exact per-roller arrays mentioned by the supplement are not yet available in the extracted JSON.

High-EA plants outside the extracted Table S4 baseline range use zero excitation by default until exact per-roller arrays or retuned input values are supplied.

### How do I compare against the actual paper?

Add the paper constants, tables, and digitized figures to `data/paper_reference/`, then update tests and report tolerances to compare generated outputs against those paper references.

### Why is `Tlog = 10-20 ms` checked?

The requested validation target asks whether sensor noise makes the best logging rate occur near `10-20 ms`. The logging-rate study sweeps the requested values and reports the best noisy case.

### Why compare excitation profiles?

SysID depends on whether the input excites enough system dynamics. Multi-channel and toggle profiles can reveal more parameters under noise than a single-channel excitation.

### Why compare `EA`, `f`, and `J` drift?

The requested drift study asks which physical drift source degrades identification/control most. The dashboard compares each scenario with the same scoring method.

### Why compare retuning methods?

The paper-style retuning claim is about reducing real-plant evaluations. The retuning study reports both final cost and real-evaluation count.

### Where do I change controller gains?

Default controller gains are in:

- `backend/models/controller.py`
- `configs/default.yaml`

### Where do I change simulation timing?

Default timing is in:

- `backend/models/simulation.py`
- `configs/default.yaml`

Dashboard simulation timing can also be changed from the Simulation page.

### Where is API route behavior defined?

API routes are defined in:

- `backend/api/main.py`

### Where are tests?

Tests are in:

- `backend/tests/`

## 22. Known Limitations

The current implementation is complete as a working validation scaffold, but strict paper reproduction still requires the exact research-paper reference data.

Current limitations:

- Exact per-plant arrays for `R_i`, `J_i`, `f_i`, `L_i`, and `b_i` are not present in the extracted JSON, so only plant-specific `EA_N` is applied today.
- Original paper plot traces and strict numerical tolerances are not in the repository.
- The simulator is a reduced three-span implementation mapped to the paper equations for dashboard validation, not a full production digital twin.
- The retuning workflow is deterministic and lightweight, intended to represent the requested method comparison rather than a full production Bayesian optimizer.
- The validation plots are generated as dependency-light SVG charts rather than publication plotting scripts.

These limitations can be removed once the paper reference package is added under `data/paper_reference/`.
