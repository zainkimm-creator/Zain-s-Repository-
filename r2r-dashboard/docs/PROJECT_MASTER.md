# R2R Dashboard Master Project Notes

## Purpose

This folder keeps the project Markdown files in one place for review. The root-level Markdown files still remain in the project root for normal repository use, while this folder provides a consolidated documentation location.

## Safety Copy

Before the plant-selector changes were made, a safety copy was created here:

```text
C:\Users\user\Documents\Git+ Learning\r2r-dashboard-safety-copy-20260602-170624
```

That copy excludes generated dependency/build folders such as `node_modules`, `dist`, caches, and logs.

## Project Structure

```text
r2r-dashboard/
|-- AGENTS.md
|-- README.md
|-- GUIDE.md
|-- REVIEW_CHECKLIST.md
|-- docs/
|   |-- PROJECT_MASTER.md
|   |-- AGENTS.md
|   |-- README.md
|   |-- GUIDE.md
|   `-- REVIEW_CHECKLIST.md
|-- backend/
|-- frontend/
|-- data/
|-- reports/
|-- scripts/
`-- notebooks/
```

## Current Plant Selector Behavior

The dashboard now has a `Plants` tab backed by supplement Table S12. The table contains ten plants:

```text
P01, P02, P03, P04, P05, P06, P07, P08, P09, P10
```

Each selected plant is sent to:

- Simulation
- Paper parts
- SysID
- Logging rate
- Excitation
- Drift
- Retuning

The extracted supplement data currently includes plant-specific:

- `EA_N`
- material
- scale
- regime
- `zeta_cl_min`
- `overshoot_percent`

The supplementary PDF states that exact per-roller arrays also exist for `R_i`, `J_i`, `f_i`, `L_i`, and `b_i`, but those arrays are not present in the extracted JSON table. Until those exact arrays are supplied, the app applies the selected plant's `EA_N` and retains the current baseline arrays for `R`, `L`, `J`, `f`, and `b`.

For plants whose `EA_N` is outside the extracted Table S4 baseline range, the dashboard sets the recommended excitation amplitude to `0` by default. This prevents unstable reduced-model runs while still allowing the plant to be selected, inspected, and used for zero-excitation baseline checks.

## Current Equation and Calculation Behavior

The `Equations` tab now includes a Backend Equation Register with only equations used by the backend to produce dashboard results:

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

Formula text uses the document-style math font stack:

```text
Cambria Math, Cambria, Times New Roman, serif
```

Every runnable result panel exposes a `Calculation` action when worked examples are available. The calculation cards include the formula, input values, substitution, final result, and ordered steps that explain how the backend computes the output from the selected plant/input values.

Strict paper reproduction still needs exact per-plant arrays for `R_i`, `J_i`, `f_i`, `L_i`, and `b_i`, plus original paper figure/table tolerances where they are not present in the extracted JSON.

## Main Runtime Files

| Area | File |
|---|---|
| API routes | `backend/api/main.py` |
| Plant presets | `backend/validation/plants.py` |
| Paper reference loader | `backend/validation/paper_reference.py` |
| R2R parameters and equations | `backend/models/equations.py` |
| Worked calculations | `backend/validation/calculations.py` |
| Simulation | `backend/models/simulation.py` |
| SysID | `backend/sysid/estimator.py` |
| Dashboard app | `frontend/src/App.jsx` |
| Dashboard result panel | `frontend/components/ResultPanel.jsx` |
| Simulator schematic | `frontend/components/R2RSchematic.jsx` |
| Dashboard styles | `frontend/src/styles.css` |

## Verification Commands

```powershell
python -m pytest
cd frontend
npm run build
```
