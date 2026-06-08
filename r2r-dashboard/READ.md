# R2R Dashboard Project Guide

## Table of Contents

1. Project Purpose
2. Folder Structure
3. Quick Start
4. Dashboard Tabs
5. Backend Model Equations
6. SysID and Validation Workflow
7. Plant and Excitation Inputs
8. Generated Outputs
9. Troubleshooting

## 1. Project Purpose

This project is a roll-to-roll web transport dashboard for simulation, system identification, and paper-validation studies.
It uses the supplied paper equation set to simulate web tension, roller speed, plant changes, excitation profiles, and SysID accuracy.

The dashboard supports:

- Closed-loop R2R simulation.
- Plant selection from 10 supplement plant presets.
- Excitation selection such as ET1, ET3, ET6, E_Toggle, and EVR.
- SysID estimation for the paper parameter vector.
- Validation studies for logging rate, excitation, drift, and retuning.
- Downloadable CSV/XLSX outputs and result summaries.

## 2. Folder Structure

```text
r2r-dashboard/
  backend/
    api/              FastAPI routes
    models/           equations, controller, simulation
    sysid/            parameter estimation
    validation/       plant data, excitations, studies, calculations
    tests/            backend tests
  frontend/
    src/              React app
    components/       dashboard components and schematic
  data/
    paper_reference/  extracted paper/supplement reference data
    processed/        generated CSV/XLSX outputs
    raw_physical/     optional raw data
  reports/
    figures/          generated plots
    validation_summary/ reports, logs, exported documents
  scripts/            command-line runners
```

## 3. Quick Start

Install backend dependencies:

```powershell
cd "C:\Users\user\Documents\Git+ Learning\r2r-dashboard"
pip install -r requirements.txt
```

Install frontend dependencies:

```powershell
cd "C:\Users\user\Documents\Git+ Learning\r2r-dashboard\frontend"
npm install
```

Run the backend:

```powershell
cd "C:\Users\user\Documents\Git+ Learning\r2r-dashboard"
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

Run the frontend in a second terminal:

```powershell
cd "C:\Users\user\Documents\Git+ Learning\r2r-dashboard\frontend"
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://127.0.0.1:5173/
```

## 4. Dashboard Tabs

- Simulation: runs the R2R model and reports tension RMSE, overshoot, t90, and control effort.
- Paper parts: validates extracted physical parameters against paper/supplement references.
- Plants: selects one of the 10 plant presets.
- SysID: estimates the paper parameter vector from logged simulation data.
- Logging rate: compares Tlog choices and SysID error.
- Excitation: compares excitation profiles and their effect on SysID.
- Drift: compares EA, friction, and inertia drift sensitivity.
- Retuning: compares retuning strategies and final cost.
- Equations: shows paper equations, runnable system equations, time scales, and excitation information.

## 5. Backend Model Equations

The current backend dynamics are aligned with the supplied paper equations.

State:

```text
x = [T1, T2, T3, omega_UW, omega_Nip, omega_RW]
```

Input:

```text
u = [u_UW, u_Nip, u_RW]
```

Output:

```text
y = [T1, T2, T3]
```

Roller surface velocity:

```text
v_i = R_i * omega_i
```

Web tension dynamics, paper Eq. (1):

```text
dT_i/dt = (EA/L_i)(v_i - v_{i-1}) + (T_{i-1}v_{i-1} - T_i v_i)/L_i
```

Roller velocity dynamics, paper Eq. (2):

```text
dv_i/dt = (R_i^2/J_i)(T_{i+1} - T_i) - (f_i/J_i)v_i + (R_i/J_i)u_i
```

SysID ratio parameters, paper Eq. (6):

```text
k_t,i = R_i^2/J_i
k_f,i = f_i/J_i
k_u,i = R_i/J_i
theta = [kt_UW, kt_Nip, kt_RW, kf_UW, kf_Nip, kf_RW, EA]
```

In the dashboard API, the controller command is voltage-like. The backend uses an internal motor gain `Kmotor_i` to convert that command into the motor torque input used by Eq. (2). The reported SysID `kt` remains the paper ratio `R^2/J`.

## 6. SysID and Validation Workflow

1. Select a plant.
2. Select an excitation type and amplitude.
3. Run Simulation to generate tension, speed, and input logs.
4. Run SysID to estimate `kt_UW`, `kt_Nip`, `kt_RW`, `kf_UW`, `kf_Nip`, `kf_RW`, and `EA`.
5. Compare estimated values with the paper/reference values.
6. Use validation tabs to compare logging rate, excitation design, drift sensitivity, and retuning cost.

Key metrics:

- `tension_rmse_N`: average tension tracking error.
- `max_overshoot_N`: maximum positive overshoot above reference tension.
- `control_effort_rms_V`: RMS motor command effort.
- `RMSE_theta`: parameter-estimation error across the SysID vector.

## 7. Plant and Excitation Inputs

Plants:

- The dashboard includes 10 plant presets from the supplement reference extraction.
- Each plant mainly changes `EA`, metadata, and recommended excitation amplitude.
- Baseline arrays for `R`, `L`, `J`, `f`, and `b` are used until exact per-plant arrays are supplied.

Excitations:

- ET1: single-channel sine excitation on UW.
- ET3: three-channel sine excitation.
- ET6: three-channel multi-sine excitation.
- E_Toggle: square/toggle excitation.
- EVR: event-varying random excitation.

Changing excitation changes the information content in the logged data, so SysID estimates can change.
Changing amplitude changes signal strength. Increasing tension noise or omega noise reduces the quality of finite-difference estimates and can increase `RMSE_theta`.

## 8. Generated Outputs

Common outputs are written under:

```text
data/processed/
reports/figures/
reports/validation_summary/
```

Simulation downloads include workbook sheets for:

- Summary metrics.
- Simulation data rows.

## 9. Troubleshooting

If the frontend does not load:

```powershell
cd "C:\Users\user\Documents\Git+ Learning\r2r-dashboard\frontend"
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

If the backend does not respond:

```powershell
cd "C:\Users\user\Documents\Git+ Learning\r2r-dashboard"
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

Run tests:

```powershell
cd "C:\Users\user\Documents\Git+ Learning\r2r-dashboard"
python -m pytest backend\tests
```

Build frontend:

```powershell
cd "C:\Users\user\Documents\Git+ Learning\r2r-dashboard\frontend"
npm run build
```
