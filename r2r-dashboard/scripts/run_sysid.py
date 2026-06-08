from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.models.simulation import SimulationConfig, simulate
from backend.sysid.estimator import estimate_parameters
from backend.validation.excitations import get_excitation_profile


if __name__ == "__main__":
    sim = simulate(
        config=SimulationConfig(output_name="script_sysid_source.csv"),
        excitation=get_excitation_profile("E_Toggle", 0.08),
    )
    result = estimate_parameters(sim.rows, summary_name="script_sysid_result.json")
    print(result.to_dict())
