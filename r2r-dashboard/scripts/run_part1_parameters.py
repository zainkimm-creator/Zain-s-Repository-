from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.validation.parts import run_part_1_parameter_validation


if __name__ == "__main__":
    result = run_part_1_parameter_validation()
    print(
        {
            "metrics": result["metrics"],
            "plot_path": result["plot_path"],
            "summary_path": result["summary_path"],
            "markdown_path": result["markdown_path"],
            "csv_path": result["csv_path"],
        }
    )
