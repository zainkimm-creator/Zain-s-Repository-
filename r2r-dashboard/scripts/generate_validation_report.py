from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.validation.studies import (
    drift_study,
    excitation_study,
    logging_rate_study,
    retuning_study,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "reports" / "validation_summary"


def main() -> None:
    studies = {
        "logging_rate": logging_rate_study()["metrics"],
        "excitation": excitation_study()["metrics"],
        "drift": drift_study()["metrics"],
        "retuning": retuning_study()["metrics"],
    }
    report = {
        "title": "R2R Validation Summary",
        "paper_style_findings": {
            "logging_rate_best_near_10_20ms": studies["logging_rate"][
                "supports_noisy_optimum_near_10_20ms"
            ],
            "multi_channel_excitation_better_under_noise": studies["excitation"][
                "supports_multi_channel_or_toggle_under_noise"
            ],
            "J_drift_dominant": studies["drift"]["supports_J_drift_dominance"],
            "HGS_BO5_fewer_real_evaluations_than_CS_BO30": studies["retuning"][
                "supports_HGS_BO5_fewer_real_evaluations_than_CS_BO30"
            ],
        },
        "studies": studies,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "validation_report.json"
    md_path = REPORT_DIR / "validation_report.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print({"json_path": str(json_path), "markdown_path": str(md_path)})


def render_markdown(report: dict[str, object]) -> str:
    findings = report["paper_style_findings"]
    studies = report["studies"]
    lines = [
        "# R2R Validation Summary",
        "",
        "## Paper-Style Findings",
    ]
    for key, value in findings.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Study Highlights"])
    lines.append(
        f"- Logging-rate noisy optimum: `{studies['logging_rate']['best_noisy_Tlog_ms']} ms` "
        f"with `RMSE_theta={studies['logging_rate']['best_noisy_RMSE_theta']}`."
    )
    lines.append(
        f"- Best noisy excitation: `{studies['excitation']['best_noisy_excitation']}`."
    )
    lines.append(
        f"- Dominant drift source: `{studies['drift']['dominant_degradation_source']}`."
    )
    lines.append(
        "- Retuning cost function: "
        f"`{studies['retuning']['cost_function']}`."
    )
    lines.extend(
        [
            "",
            "## Assumption",
            "",
            "This report compares generated reduced-model validation outputs against the requested paper-style claims. Replace or extend `data/paper_reference/` with exact paper constants/results to perform strict paper reproduction.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
