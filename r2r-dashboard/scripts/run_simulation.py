from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.models.simulation import SimulationConfig, simulate
from backend.validation.excitations import get_excitation_profile


if __name__ == "__main__":
    result = simulate(
        config=SimulationConfig(output_name="script_simulation.csv"),
        excitation=get_excitation_profile("ET3", 0.08),
    )
    print({"metrics": result.metrics, "csv_path": result.csv_path})
