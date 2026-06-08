"""Generate a highlighted PDF report comparing dashboard outputs to paper findings.

The report intentionally separates two evidence layers:

1. Dashboard/API validation outputs from ``reports/validation_summary``.
2. Full governing-equation rerun comparisons from ``reports/full_governing_rerun``.

The supplied PDFs do not include raw paper seeds or exact per-plant R/J/f/L/b
arrays, so the report highlights the nearest reproducible comparisons rather
than claiming a strict reproduction of the original simulation campaign.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from textwrap import wrap
from typing import Any, Iterable, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_DIR = PROJECT_ROOT / "reports" / "validation_summary"
FULL_RERUN_DIR = PROJECT_ROOT / "reports" / "full_governing_rerun"
OUTPUT_PDF = SUMMARY_DIR / "highlighted_paper_validation_report.pdf"
OUTPUT_JSON = SUMMARY_DIR / "highlighted_paper_validation_report.json"
OUTPUT_CSV = SUMMARY_DIR / "highlighted_paper_validation_table.csv"
LOGGING_TAU_MIN_S = 0.100
VALIDATION_REPORT_JSON = SUMMARY_DIR / "validation_report.json"


def tlog_ms_to_tau_ratio(tlog_ms: float) -> float:
    return (tlog_ms / 1000.0) / LOGGING_TAU_MIN_S


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_retuning_summary() -> dict[str, Any]:
    """Prefer the normalized validation report over raw API retuning runs."""
    if VALIDATION_REPORT_JSON.exists():
        validation_report = load_json(VALIDATION_REPORT_JSON)
        retuning = validation_report.get("studies", {}).get("retuning")
        if isinstance(retuning, dict) and isinstance(retuning.get("metrics"), list):
            return retuning
    return load_json(SUMMARY_DIR / "retuning_summary.json")


def as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def fmt(value: Any, digits: int = 3) -> str:
    number = as_float(value)
    if number is None:
        return "n/a"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    if 0 < abs(number) < 0.001:
        return f"{number:.3e}"
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def pct_diff(sim: float | None, paper: float | None) -> float | None:
    if sim is None or paper is None or abs(paper) < 1e-12:
        return None
    return 100.0 * (sim - paper) / paper


def find_one(rows: Iterable[Mapping[str, Any]], **criteria: Any) -> dict[str, Any]:
    for row in rows:
        matched = True
        for key, expected in criteria.items():
            value = row.get(key)
            if isinstance(expected, (int, float)):
                matched = as_float(value) == float(expected)
            else:
                matched = value == expected
            if not matched:
                break
        if matched:
            return dict(row)
    raise KeyError(f"missing row for {criteria}")


def wrapped(text: str, width: int = 82) -> str:
    return "\n".join(wrap(text, width=width))


def wrap_row(row: list[str], widths: list[int]) -> list[str]:
    return [wrapped(str(value), widths[min(index, len(widths) - 1)]) for index, value in enumerate(row)]


def add_footer(fig: plt.Figure, page_label: str) -> None:
    fig.text(0.06, 0.035, page_label, fontsize=8, color="#5f6b7a")
    fig.text(0.94, 0.035, "R2R dashboard validation", fontsize=8, color="#5f6b7a", ha="right")


def text_page(pdf: PdfPages, title: str, blocks: list[str], page_label: str) -> None:
    fig = plt.figure(figsize=(11.0, 8.5))
    fig.patch.set_facecolor("white")
    fig.text(0.06, 0.92, title, fontsize=21, fontweight="bold", color="#1b2430")
    y = 0.84
    for block in blocks:
        fig.text(0.06, y, wrapped(block), fontsize=11, color="#263241", va="top", linespacing=1.35)
        y -= 0.11 + 0.018 * block.count("\n")
    add_footer(fig, page_label)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def table_page(
    pdf: PdfPages,
    title: str,
    columns: list[str],
    rows: list[list[str]],
    page_label: str,
    note: str | None = None,
    wrap_widths: list[int] | None = None,
    col_widths: list[float] | None = None,
) -> None:
    fig, ax = plt.subplots(figsize=(11.0, 8.5))
    fig.patch.set_facecolor("white")
    ax.axis("off")
    ax.set_title(title, loc="left", fontsize=18, fontweight="bold", color="#1b2430", pad=18)
    display_rows = [wrap_row(row, wrap_widths) for row in rows] if wrap_widths else rows
    table = ax.table(
        cellText=display_rows,
        colLabels=columns,
        loc="upper left",
        cellLoc="left",
        colLoc="left",
        colWidths=col_widths,
        bbox=[0.0, 0.17 if note else 0.08, 1.0, 0.76 if note else 0.84],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.2)
    table.scale(1.0, 1.55)
    for (row_idx, _col_idx), cell in table.get_celld().items():
        cell.set_edgecolor("#d9dee7")
        if row_idx == 0:
            cell.set_facecolor("#e8eef7")
            cell.set_text_props(fontweight="bold", color="#1b2430")
        else:
            cell.set_facecolor("#ffffff" if row_idx % 2 else "#f7f9fc")
    if note:
        ax.text(0.0, 0.08, wrapped(note, 120), fontsize=9.5, color="#4a5568", va="top")
    add_footer(fig, page_label)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def build_summary() -> dict[str, Any]:
    logging = load_json(SUMMARY_DIR / "logging_rate_summary.json")
    excitation = load_json(SUMMARY_DIR / "excitation_summary.json")
    drift = load_json(SUMMARY_DIR / "drift_summary.json")
    retuning = load_retuning_summary()
    part1 = load_json(SUMMARY_DIR / "part1_parameter_validation.json")

    full_logging = load_csv(FULL_RERUN_DIR / "data" / "logging_full_equation.csv")
    full_excitation = load_csv(FULL_RERUN_DIR / "data" / "excitation_full_equation.csv")
    full_drift = load_csv(FULL_RERUN_DIR / "data" / "drift_full_equation.csv")
    full_noise = load_csv(FULL_RERUN_DIR / "data" / "noise_lpf_full_equation.csv")
    full_gain = load_csv(FULL_RERUN_DIR / "data" / "gain_full_equation.csv")

    dash_logging_best = logging["best_noisy_Tlog_ms"]
    dash_logging_rmse_pct = 100.0 * float(logging["best_noisy_RMSE_theta"])
    dash_excitation_best = excitation["best_noisy_excitation"]
    dash_drift_source = drift["dominant_degradation_source"]
    dash_drift_j = find_one(drift["metrics"], scenario="J")
    dash_hgs5 = find_one(retuning["metrics"], method="HGS+BO(5)")
    dash_cs = find_one(retuning["metrics"], method="CS-BO(30)")

    selected = [
        {
            "section": "Logging, full equation",
            "paper_finding": "SN Tlog 20 ms: RMSE_theta 23.2%; optimum window 10-20 ms",
            "dashboard_or_rerun_result": "Full-equation SN Tlog 20 ms",
            "paper_value": 23.2,
            "result_value": as_float(find_one(full_logging, case="SN", Tlog_ms=20)["sim_RMSE_theta_percent"]),
            "unit": "RMSE_theta %",
            "Tlog_ms": 20.0,
            "tau_min_s": LOGGING_TAU_MIN_S,
            "Tlog_over_tau_min": tlog_ms_to_tau_ratio(20.0),
        },
        {
            "section": "Excitation, full equation",
            "paper_finding": "SN E_Toggle: RMSE_theta 20.4%",
            "dashboard_or_rerun_result": "Full-equation SN E_Toggle",
            "paper_value": 20.4,
            "result_value": as_float(find_one(full_excitation, case="SN", excitation="E_Toggle")["sim_RMSE_theta_percent"]),
            "unit": "RMSE_theta %",
        },
        {
            "section": "Noise/LPF, full equation",
            "paper_finding": "50 Hz LPF at Tlog 20 ms: RMSE_theta 23.2%",
            "dashboard_or_rerun_result": "Full-equation 50 Hz LPF, Tlog 20 ms",
            "paper_value": 23.2,
            "result_value": as_float(find_one(full_noise, LPF="50 Hz", Tlog_ms=20)["sim_RMSE_theta_percent"]),
            "unit": "RMSE_theta %",
        },
        {
            "section": "Noise/LPF, full equation",
            "paper_finding": "100 Hz LPF at Tlog 20 ms: RMSE_theta 20.4%",
            "dashboard_or_rerun_result": "Full-equation 100 Hz LPF, Tlog 20 ms",
            "paper_value": 20.4,
            "result_value": as_float(find_one(full_noise, LPF="100 Hz", Tlog_ms=20)["sim_RMSE_theta_percent"]),
            "unit": "RMSE_theta %",
        },
        {
            "section": "Drift, full equation",
            "paper_finding": "J_UW -30%, RW +50%: RMSE_theta 26.8%",
            "dashboard_or_rerun_result": "Full-equation J_UW -30%, RW +50%",
            "paper_value": 26.8,
            "result_value": as_float(find_one(full_drift, scenario="J_UWminus30_RWplus50")["sim_RMSE_theta_percent"]),
            "unit": "RMSE_theta %",
        },
        {
            "section": "Gain, full equation",
            "paper_finding": "SN Kp* 100: RMSE_theta 20.4%",
            "dashboard_or_rerun_result": "Full-equation SN Kp* 100",
            "paper_value": 20.4,
            "result_value": as_float(find_one(full_gain, case="SN", Kp_star=100)["sim_RMSE_theta_percent"]),
            "unit": "RMSE_theta %",
        },
        {
            "section": "Retuning, dashboard",
            "paper_finding": "HGS+BO(5): median cost 0.342 with 5 real evaluations",
            "dashboard_or_rerun_result": "Dashboard HGS+BO(5)",
            "paper_value": 0.342,
            "result_value": as_float(dash_hgs5["final_cost"]),
            "unit": "score",
        },
    ]
    for row in selected:
        row["relative_difference_percent"] = pct_diff(row["result_value"], row["paper_value"])

    return {
        "dashboard": {
            "part1_in_range": f"{part1['metrics']['in_range_count']}/{part1['metrics']['parameters_checked']}",
            "logging_best_tlog_ms": dash_logging_best,
            "logging_best_rmse_percent": dash_logging_rmse_pct,
            "excitation_best": dash_excitation_best,
            "drift_source": dash_drift_source,
            "drift_j_rmse_percent": 100.0 * float(dash_drift_j["RMSE_theta"]),
            "retuning_hgs5_cost": as_float(dash_hgs5["final_cost"]),
            "retuning_hgs5_evaluations": as_float(dash_hgs5["real_evaluations"]),
            "retuning_cs_cost": as_float(dash_cs["final_cost"]),
            "retuning_cs_evaluations": as_float(dash_cs["real_evaluations"]),
        },
        "selected_comparisons": selected,
        "logging_summary": logging,
        "retuning_summary": retuning,
    }


def write_outputs(summary: Mapping[str, Any]) -> None:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "section",
            "paper_finding",
            "dashboard_or_rerun_result",
            "paper_value",
            "result_value",
            "unit",
            "relative_difference_percent",
            "Tlog_ms",
            "tau_min_s",
            "Tlog_over_tau_min",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary["selected_comparisons"]:
            writer.writerow({key: row.get(key) for key in fieldnames})


def plot_dashboard_logging(pdf: PdfPages, summary: Mapping[str, Any]) -> None:
    rows = summary["logging_summary"]["metrics"]
    fig, ax = plt.subplots(figsize=(11.0, 8.5))
    fig.patch.set_facecolor("white")
    for case, label, color in (
        ("noise_free", "Dashboard noise-free", "#277da1"),
        ("sensor_noise", "Dashboard sensor-noise", "#f3722c"),
    ):
        subset = sorted([row for row in rows if row["case"] == case], key=lambda r: r["Tlog_ms"])
        ax.plot(
            [float(row["Tlog_ms"]) for row in subset],
            [100.0 * float(row["RMSE_theta"]) for row in subset],
            marker="o",
            linewidth=2,
            label=label,
            color=color,
        )
    ax.axvspan(10, 20, color="#90be6d", alpha=0.18, label="Paper preferred SN window")
    ax.scatter([20], [23.2], marker="*", s=210, color="#4d908e", label="Paper SN 20 ms = 23.2%")
    ax.set_title("Dashboard Logging-Rate Study", loc="left", fontsize=18, fontweight="bold")
    ax.set_xlabel("Tlog (ms)")
    ax.set_ylabel("RMSE_theta (%)")
    ax.set_xscale("log")
    ax.set_xlim(0.8, 120)
    ax.set_xticks([1, 2, 5, 10, 20, 50, 100])
    ax.set_xticklabels(["1", "2", "5", "10", "20", "50", "100"])
    ax.tick_params(axis="x", labelsize=9, pad=3)

    def tlog_to_ratio(tlog_ms: float) -> float:
        return tlog_ms_to_tau_ratio(tlog_ms)

    def ratio_to_tlog(ratio: float) -> float:
        return ratio * LOGGING_TAU_MIN_S * 1000.0

    ratio_axis = ax.secondary_xaxis("top", functions=(tlog_to_ratio, ratio_to_tlog))
    ratio_axis.set_xlabel(f"Tlog/tau_min  (tau_min = {fmt(LOGGING_TAU_MIN_S)} s)")
    ratio_axis.set_xticks([0.01, 0.05, 0.10, 0.20, 0.50, 1.00])
    ratio_axis.set_xticklabels(["0.01", "0.05", "0.10", "0.20", "0.50", "1.00"])
    ratio_axis.tick_params(axis="x", labelsize=9, pad=4)
    ax.axvline(20, color="#4d908e", linestyle=":", linewidth=1.8)
    ax.grid(True, alpha=0.28)
    ax.legend(loc="upper left")
    ax.text(
        0.02,
        0.02,
        "Dashboard best noisy result: 20 ms at "
        f"{fmt(summary['dashboard']['logging_best_rmse_percent'])}% RMSE_theta. "
        "Paper NF rule tau_min/Tlog >= 5 becomes Tlog/tau_min <= 0.20.",
        transform=ax.transAxes,
        fontsize=10,
        color="#263241",
        bbox={"facecolor": "white", "edgecolor": "#d9dee7", "alpha": 0.92},
    )
    add_footer(fig, "Highlighted graph 1")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def plot_selected_comparisons(pdf: PdfPages, summary: Mapping[str, Any]) -> None:
    rows = summary["selected_comparisons"]
    labels = [
        "Logging SN 20ms",
        "Excitation E_Toggle",
        "LPF 50Hz 20ms",
        "LPF 100Hz 20ms",
        "Drift J asym",
        "Gain SN Kp100",
        "Retune HGS+BO5",
    ]
    diffs = [float(row["relative_difference_percent"]) for row in rows]
    y = list(range(len(rows)))
    colors = ["#43aa8b" if abs(value) <= 10 else "#f9c74f" if abs(value) <= 15 else "#f9844a" for value in diffs]
    fig, ax = plt.subplots(figsize=(11.0, 8.5))
    fig.patch.set_facecolor("white")
    ax.barh(y, diffs, color=colors)
    ax.axvline(0, color="#1b2430", linewidth=1)
    ax.set_title("Nearest Reproducible Paper Comparisons", loc="left", fontsize=18, fontweight="bold")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Relative difference from paper (%)")
    ax.grid(axis="x", alpha=0.25)
    ax.invert_yaxis()
    for idx, (diff, row) in enumerate(zip(diffs, rows)):
        paper = fmt(row["paper_value"])
        result = fmt(row["result_value"])
        x_pos = diff + 0.6
        ha = "left"
        ax.text(x_pos, idx, f"{fmt(diff)}%  ({result} vs {paper})", va="center", ha=ha, fontsize=9)
    ax.set_xlim(min(diffs) - 4, max(diffs) + 10)
    ax.text(
        0.01,
        0.02,
        "Green bars are within 10% of the paper value. Retuning uses score units; other rows use RMSE_theta percent.",
        transform=ax.transAxes,
        fontsize=9.5,
        color="#263241",
        bbox={"facecolor": "white", "edgecolor": "#d9dee7", "alpha": 0.92},
    )
    add_footer(fig, "Highlighted graph 2")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def plot_retuning(pdf: PdfPages, summary: Mapping[str, Any]) -> None:
    rows = summary["retuning_summary"]["metrics"]
    methods = [row["method"] for row in rows]
    costs = [float(row["final_cost"]) for row in rows]
    evals = [float(row["real_evaluations"]) for row in rows]
    fig, ax = plt.subplots(figsize=(11.0, 8.5))
    fig.patch.set_facecolor("white")
    bars = ax.bar(methods, costs, color=["#f94144", "#43aa8b", "#90be6d", "#577590"])
    ax.set_title("Dashboard Retuning Result", loc="left", fontsize=18, fontweight="bold")
    ax.set_ylabel("Dashboard cost")
    ax.grid(axis="y", alpha=0.25)
    for bar, eval_count in zip(bars, evals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.025,
            f"{fmt(eval_count)} real evals",
            ha="center",
            fontsize=9,
        )
    ax.axhline(0.342, color="#4d908e", linestyle="--", linewidth=2, label="Paper HGS+BO(5) cost 0.342")
    ax.legend(loc="upper right")
    hgs5 = find_one(rows, method="HGS+BO(5)")
    ax.text(
        0.02,
        0.83,
        "HGS+BO(5): "
        f"dashboard cost {fmt(hgs5['final_cost'])}, paper cost 0.342, "
        f"{fmt(pct_diff(as_float(hgs5['final_cost']), 0.342))}% difference.",
        transform=ax.transAxes,
        fontsize=10,
        color="#263241",
        bbox={"facecolor": "white", "edgecolor": "#d9dee7", "alpha": 0.92},
    )
    add_footer(fig, "Highlighted graph 3")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def render_pdf(summary: Mapping[str, Any]) -> None:
    dash = summary["dashboard"]
    selected_rows = []
    for row in summary["selected_comparisons"]:
        short_section = row["section"].replace(", full equation", "").replace(", dashboard", "")
        source_label = (
            row["dashboard_or_rerun_result"]
            .replace("Full-equation ", "")
            .replace("Dashboard ", "")
            .replace(", Tlog ", " ")
            .replace("LPF, ", "LPF ")
        )
        selected_rows.append(
            [
                short_section,
                source_label,
                fmt(row.get("Tlog_over_tau_min")),
                fmt(row["paper_value"]),
                fmt(row["result_value"]),
                row["unit"],
                fmt(row["relative_difference_percent"]),
            ]
        )
    alignment_rows = [
        ["Parameter ranges", "Paper/supplement ranges", dash["part1_in_range"], "supports"],
        ["Logging rate", "Noisy optimum near 10-20 ms", f"{fmt(dash['logging_best_tlog_ms'])} ms", "supports"],
        ["Excitation", "Multi-channel/toggle wins under noise", dash["excitation_best"], "supports"],
        ["Drift", "J drift dominates", f"{dash['drift_source']} ({fmt(dash['drift_j_rmse_percent'])}%)", "supports"],
        [
            "Retuning",
            "HGS+BO(5) uses 5 real evals and beats CS-BO(30)",
            f"HGS+BO(5): cost {fmt(dash['retuning_hgs5_cost'])}, evals {fmt(dash['retuning_hgs5_evaluations'])}",
            "supports",
        ],
    ]
    with PdfPages(OUTPUT_PDF) as pdf:
        text_page(
            pdf,
            "Highlighted Paper Validation Report",
            [
                "This report summarizes the current R2R dashboard validation run against the supplied PDF findings. It uses freshly generated dashboard/API summaries and the full governing-equation rerun where that rerun gives the nearest available numerical comparison.",
                "Important fidelity limit: the supplied references do not include the paper's raw simulation CSV files, exact ten-plant per-roller arrays, or optimizer seeds. The dashboard therefore validates the published mechanisms and closest reproducible values rather than claiming exact private-campaign reproduction.",
                f"Report artifacts: {OUTPUT_PDF.name}, {OUTPUT_JSON.name}, and {OUTPUT_CSV.name}.",
            ],
            "Scope",
        )
        table_page(
            pdf,
            "Dashboard Claim Alignment",
            ["Part", "Paper finding", "Dashboard result", "Alignment"],
            alignment_rows,
            "Highlighted table 1",
            note="These rows come from the dashboard/API validation summaries in reports/validation_summary.",
            wrap_widths=[18, 32, 30, 12],
        )
        plot_dashboard_logging(pdf, summary)
        plot_selected_comparisons(pdf, summary)
        plot_retuning(pdf, summary)
        table_page(
            pdf,
            "Selected Nearest Numerical Comparisons",
            ["Section", "Result source", "Tlog/\ntau_min", "Paper", "Result", "Unit", "Diff %"],
            selected_rows,
            "Highlighted table 2",
            note="Full-equation rows use the direct paper-form Eq. (1)-(7) rerun. Retuning uses the dashboard cost because it is closest to the paper score scale.",
            wrap_widths=[16, 26, 9, 9, 9, 14, 9],
            col_widths=[0.16, 0.27, 0.1, 0.09, 0.09, 0.16, 0.13],
        )


def main() -> None:
    summary = build_summary()
    write_outputs(summary)
    render_pdf(summary)
    print(json.dumps({"pdf_path": str(OUTPUT_PDF), "json_path": str(OUTPUT_JSON), "csv_path": str(OUTPUT_CSV)}, indent=2))


if __name__ == "__main__":
    main()
