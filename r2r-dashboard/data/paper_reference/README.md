# Paper Reference Data

Place the source research-paper reference material for strict validation in this folder.

Recommended contents:

| File | Purpose |
|---|---|
| `paper.pdf` | Original paper used as the validation reference |
| `paper_constants.json` | Physical parameters, controller gains, timing values, and units from the paper |
| `paper_equation_map.md` | Mapping from paper equation numbers to backend functions |
| `paper_figures_reference.csv` | Digitized paper figure curves for overlay/comparison |
| `paper_tables_reference.csv` | Paper table values for regression checks |

Reference mapping format:

```text
Paper Eq. (1) -> backend/models/equations.py:tension_derivatives
Paper Eq. (2) -> backend/models/equations.py:roller_velocity_derivatives
Paper Table X -> reports/validation_summary/<generated_summary>.json
Paper Figure Y -> reports/figures/<generated_plot>.svg
```

Current status:

- The project currently uses a reduced three-span R2R model.
- Strict paper reproduction should begin by adding exact paper constants and equation references here.
