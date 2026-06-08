# R2R Dashboard Review Checklist

Use this checklist before final acceptance.

## 1. Backend Equation Review

Primary file:

- `backend/models/equations.py`

API route:

- `GET http://127.0.0.1:8000/equations`

Check these items:

- State vector is `x = [T1, T2, T3, omega_UW, omega_Nip, omega_RW]`.
- Input vector is `u = [u_UW, u_Nip, u_RW]`.
- Tension dynamics are explicit for `T1`, `T2`, and `T3`.
- Roller velocity dynamics are explicit for `omega_UW`, `omega_Nip`, and `omega_RW`.
- Section 2 style equation groups are visible in the Equations tab.
- Derivation / usage flow explains how kinematics, tension, torque, roller acceleration, RK4, and SysID connect.
- Units are documented for tension, angular velocity, voltage input, radius, span length, inertia, torque constant, friction, and `EA`.
- The seven SysID parameters are exactly:
  - `kt_UW`
  - `kt_Nip`
  - `kt_RW`
  - `kf_UW`
  - `kf_Nip`
  - `kf_RW`
  - `EA`

Current modeling assumption:

- This implementation uses a reduced three-span R2R model until the exact paper equations/constants are provided under `data/paper_reference/`.

## 2. Frontend UI Review

Dashboard URL:

- `http://localhost:5173`

Check these pages:

- Simulation
- SysID
- Logging rate
- Excitation
- Drift
- Retuning
- Equations

Expected behavior:

- Header status shows `online`.
- Simulation can run and returns metrics plus a downloadable CSV.
- Simulation page shows the labeled R2R web transport schematic.
- SysID can run and returns estimates for all seven parameters.
- Logging-rate validation renders a plot and summary showing noisy optimum near `10-20 ms`.
- Excitation validation renders a plot and summary showing a multi-channel profile performs best under noise.
- Drift validation renders a plot and summary showing `J` drift as dominant.
- Retuning renders a comparison table showing `HGS+BO(5)` uses fewer real evaluations than `CS-BO(30)`.
- Equations page displays the state vector, input vector, tension dynamics, roller dynamics, and units.
- Equations page displays Section 2 equation groups, derivation flow, and implementation mapping.

## 3. Verification Commands

From the project root:

```powershell
python -m pytest
cd frontend
npm run build
```

Optional validation report:

```powershell
python scripts/generate_validation_report.py
```

Generated report:

- `reports/validation_summary/validation_report.md`
