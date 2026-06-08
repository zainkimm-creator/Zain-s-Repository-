# R2R Dashboard Agent Plan

This project validates a roll-to-roll web tension control paper by reproducing the governing equations, controller, simulation workflow, system-identification studies, drift analysis, retuning workflow, backend API, and final dashboard.

## Development Rule

Work must proceed in this order:

1. Equations
2. Controller
3. Simulation
4. SysID
5. Validation
6. Retuning
7. API
8. Dashboard
9. Testing/report

Do not build the frontend before the backend model, controller, simulation, SysID, validation, and retuning foundations are implemented.

## Shared Task Report Format

Every task should end with:

1. Files changed
2. What was implemented
3. How to run it
4. How to test it
5. Assumptions
6. Remaining issues

## Agent Responsibilities

### 1. Repository Setup Agent

Scope:

- Maintain the clean repository structure.
- Add backend, frontend, data, scripts, tests, reports, and configs paths.
- Keep root documentation current.
- Create or update this `AGENTS.md` when workflow ownership changes.

Primary outputs:

- Project skeleton
- Root README
- Configuration defaults
- Developer workflow notes

### 2. Mathematical Model Agent

Scope:

- Implement R2R governing equations.
- Implement web tension dynamics.
- Implement roller velocity dynamics.
- Use state vector `x = [T1, T2, T3, omega_UW, omega_Nip, omega_RW]`.
- Use input vector `u = [u_UW, u_Nip, u_RW]`.
- Keep all physical units explicit in parameters, docstrings, and outputs.

Expected files:

- `backend/models/`
- `backend/tests/`

Acceptance checks:

- Model derivatives return finite values for nominal parameters.
- Units and state ordering are documented.
- Tests cover nominal dynamics and parameter validation.

### 3. Controller Agent

Scope:

- Implement cascade PI plus feedforward controller.
- Include outer tension PI loop.
- Include inner velocity loop.
- Include `Kp_star` and `TI`.
- Include feedforward torque terms.

Expected files:

- `backend/models/`
- `backend/tests/`

Acceptance checks:

- Controller output matches expected sign conventions.
- Integrator state updates are deterministic.
- Feedforward terms can be enabled, disabled, and inspected.

### 4. Simulation Agent

Scope:

- Implement RK4 simulation.
- Use integration step `dt = 1 ms`.
- Use controller sample time `Ts = 10 ms`.
- Make `Tlog` configurable.
- Include zero-order hold between controller updates.
- Export simulation data to CSV.

Expected files:

- `backend/models/`
- `scripts/`
- `data/processed/`
- `backend/tests/`

Acceptance checks:

- Simulation produces a CSV output.
- Controller updates occur at `Ts`.
- Logged samples respect `Tlog`.
- RK4 output is stable for a nominal scenario.

### 5. SysID Agent

Scope:

- Implement one-step prediction error minimization.
- Estimate the seven SysID parameters:
  - `kt_UW`
  - `kt_Nip`
  - `kt_RW`
  - `kf_UW`
  - `kf_Nip`
  - `kf_RW`
  - `EA`
- Output parameter estimates, `RMSE_theta`, and an error table.

Expected files:

- `backend/sysid/`
- `backend/tests/`
- `reports/validation_summary/`

Acceptance checks:

- Estimator recovers known synthetic parameters within tolerance.
- Output includes estimates, absolute error, relative error, and aggregate RMSE.

### 6. Logging-Rate Validation Agent

Scope:

- Sweep `Tlog = [1, 2, 5, 10, 20, 50, 100] ms`.
- Run noise-free and sensor-noise cases.
- Plot `Tlog` vs `RMSE_theta`.
- Verify whether the noisy case gives optimum near `10-20 ms`.

Expected files:

- `backend/validation/`
- `reports/figures/`
- `reports/validation_summary/`
- `backend/tests/`

Acceptance checks:

- Sweep creates metrics and plot files.
- Summary explicitly states whether `10-20 ms` is supported by the run.

### 7. Excitation Validation Agent

Scope:

- Implement `ET1`, `ET3`, `ET6`, `E_Toggle`, and `EVR` excitation profiles.
- Compare SysID accuracy under noise-free and sensor-noise data.
- Generate a bar chart of excitation type vs `RMSE_theta`.

Expected files:

- `backend/validation/`
- `reports/figures/`
- `reports/validation_summary/`
- `backend/tests/`

Acceptance checks:

- Every excitation profile is reproducible from config.
- Results identify whether multi-channel/toggle excitation performs better under noise.

### 8. Drift Validation Agent

Scope:

- Implement `EA` drift, friction `f` drift, and reel inertia `J` drift scenarios.
- Compare SysID error and controller performance under each drift.
- Check whether reel inertia `J` drift is dominant.
- Check whether `EA` drift is partly absorbed by cascade feedforward.
- Generate plots showing dominant degradation source.

Expected files:

- `backend/validation/`
- `reports/figures/`
- `reports/validation_summary/`
- `backend/tests/`

Acceptance checks:

- Drift scenarios are isolated and comparable.
- Metrics include SysID error and closed-loop performance.
- Summary identifies the dominant degradation source from the run.

### 9. Retuning Agent

Scope:

- Implement PI gain retuning comparison:
  - `CS-BO(30)`
  - `HGS-only`
  - `HGS+BO(5)`
  - `HGS+BO(10)`
- Use a cost function based on RMSE, overshoot, `t90` or rise time, and control effort.
- Output a comparison table with real evaluations and final cost.
- Check whether `HGS+BO(5)` reduces real-plant evaluations compared with `CS-BO(30)`.

Expected files:

- `backend/validation/`
- `backend/models/`
- `reports/validation_summary/`
- `backend/tests/`

Acceptance checks:

- Retuning algorithms share the same cost function.
- Real-plant evaluation counts are reported.
- Results compare model-free and model-informed retuning.

### 10. Backend API Agent

Scope:

- Build FastAPI routes:
  - `POST /simulate`
  - `POST /sysid`
  - `POST /validate/logging-rate`
  - `POST /validate/excitation`
  - `POST /validate/drift`
  - `POST /retune`
- Each route accepts JSON input and returns metrics, CSV path, and plot path when applicable.

Expected files:

- `backend/api/`
- `backend/tests/`

Acceptance checks:

- API starts without import errors.
- Routes return valid JSON.
- Tests cover happy path and invalid input.

### 11. Frontend Dashboard Agent

Scope:

- Connect React dashboard with the backend API.
- Create pages:
  - Simulation
  - SysID
  - Logging-rate validation
  - Excitation validation
  - Drift validation
  - Retuning comparison
- Use clear plots, tables, and downloadable results.

Expected files:

- `frontend/src/`
- `frontend/components/`
- `frontend-html/index.html`

Acceptance checks:

- Dashboard displays backend results.
- Plots and tables are visible for each validation page.
- CSV and report outputs can be downloaded.
- Any dashboard behavior change is also reflected in the plain HTML frontend.

### 11a. Upload Data Handling

Scope:

- Save uploaded project data under `data/uploads/`.
- Keep uploaded filenames constrained to basename-only paths.
- Expose upload support through the API and the HTML frontend.

Expected files:

- `backend/api/`
- `data/uploads/`
- `frontend-html/index.html`

Acceptance checks:

- `POST /upload` accepts a `file` field.
- Uploaded files are saved under `data/uploads/`.
- Upload responses include filename, byte count, filesystem path, and artifact URL.

### 12. Testing and Report Agent

Scope:

- Add pytest tests for every backend module.
- Add regression tests for known paper-style results.
- Generate validation summary reports.
- Save plots in `reports/figures/`.
- Save metrics in `reports/validation_summary/`.

Expected files:

- `backend/tests/`
- `reports/figures/`
- `reports/validation_summary/`
- `scripts/`

Acceptance checks:

- `pytest` passes.
- Scripts regenerate validation outputs.
- Summary reports compare results against paper findings.

## Global Acceptance Criteria

- Code runs without errors.
- `pytest` passes.
- Simulation produces CSV output.
- Validation scripts produce plots.
- Backend API returns correct JSON.
- Dashboard displays simulation and validation results.
- Results can be compared against the paper findings.

## Current Assumptions

- The paper equations and reference values will be added under `data/paper_reference/`.
- Raw experimental or physical logs will be added under `data/raw_physical/`.
- Generated simulation and validation artifacts will be written under `data/processed/`, `reports/figures/`, and `reports/validation_summary/`.
- The backend will be Python-first, with FastAPI for API service and pytest for tests.
- The frontend will be React-based after backend validation workflows exist.
