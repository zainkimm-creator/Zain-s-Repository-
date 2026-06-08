"""Generate a PDF simulation comparison report without changing the model.

The script runs the existing dashboard backend simulator for every plant and
excitation pair, stores the summary data, draws comparison graphs, and writes a
PDF report. It does not modify model equations, plant definitions, excitations,
or frontend files.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image as PdfImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.models.simulation import SimulationConfig, simulate
from backend.validation.excitations import excitation_names, get_excitation_profile
from backend.validation.plants import parameters_for_plant, plant_registry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
FIGURE_DIR = PROJECT_ROOT / "reports" / "figures"
SUMMARY_DIR = PROJECT_ROOT / "reports" / "validation_summary"

PDF_PATH = SUMMARY_DIR / "simulation_plant_excitation_report.pdf"
JSON_PATH = SUMMARY_DIR / "simulation_plant_excitation_report.json"
CSV_PATH = DATA_DIR / "simulation_plant_excitation_sweep.csv"

CHART_PATHS = {
    "heatmap": FIGURE_DIR / "simulation_tension_rmse_heatmap.png",
    "best_by_plant": FIGURE_DIR / "simulation_best_excitation_by_plant.png",
    "average_by_excitation": FIGURE_DIR / "simulation_average_by_excitation.png",
    "ea_scatter": FIGURE_DIR / "simulation_ea_vs_best_rmse.png",
}

DEFAULT_DURATION_S = 4.0
DEFAULT_TLOG_MS = 10.0
DEFAULT_DT_MS = 1.0
DEFAULT_CONTROLLER_TS_MS = 10.0

TEXT = (27, 39, 55)
MUTED = (88, 99, 114)
GRID = (218, 225, 232)
BLUE = (41, 112, 219)
ORANGE = (229, 126, 36)
GREEN = (44, 151, 92)
RED = (201, 64, 64)
GRAY = (151, 160, 171)


EXCITATION_DESCRIPTIONS = {
    "ET1": {
        "kind": "single-channel sine",
        "channels": "UW only",
        "changing_factors": "0.70 Hz sine on u_UW; u_Nip and u_RW are zero.",
    },
    "ET3": {
        "kind": "three-channel sine",
        "channels": "UW, Nip, RW",
        "changing_factors": "0.55, 0.80, and 1.10 Hz sine waves with phase offsets.",
    },
    "ET6": {
        "kind": "three-channel multi-sine",
        "channels": "UW, Nip, RW",
        "changing_factors": "Two sine components per motor input; richer frequency content than ET3.",
    },
    "E_Toggle": {
        "kind": "three-channel square/toggle",
        "channels": "UW, Nip, RW",
        "changing_factors": "Square waves with staggered 0.42, 0.58, and 0.74 s periods.",
    },
    "EVR": {
        "kind": "event-varying random",
        "channels": "UW, Nip, RW",
        "changing_factors": "Random held voltage values updated in 0.15 s buckets.",
    },
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = [
        "arialbd.ttf" if bold else "arial.ttf",
        "segoeuib.ttf" if bold else "segoeui.ttf",
    ]
    for name in names:
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _format_metric(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "n/a"
    if abs(number) >= 1_000_000:
        return f"{number:.3e}"
    if 0 < abs(number) < 0.001:
        return f"{number:.3e}"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    if abs(number) >= 10:
        return f"{number:.2f}"
    return f"{number:.{digits}g}"


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _finite_values(rows: Iterable[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = _safe_float(row.get(key))
        if value is not None:
            values.append(value)
    return values


def _csv_write(path: Path, rows: Sequence[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    return value


def run_simulation_case(plant: dict[str, Any], excitation: str) -> dict[str, Any]:
    params, active_plant = parameters_for_plant(str(plant["plant_id"]))
    amplitude = float(active_plant["recommended_excitation_amplitude_V"])
    row: dict[str, Any] = {
        "plant_id": active_plant["plant_id"],
        "material": active_plant["material"],
        "scale": active_plant["scale"],
        "regime": active_plant["regime"],
        "EA_N": float(active_plant["EA_N"]),
        "zeta_cl_min": float(active_plant["zeta_cl_min"]),
        "paper_overshoot_percent": float(active_plant["overshoot_percent"]),
        "baseline_range_compatible": bool(active_plant["baseline_range_compatible"]),
        "excitation": excitation,
        "excitation_kind": EXCITATION_DESCRIPTIONS[excitation]["kind"],
        "recommended_amplitude_V": amplitude,
        "input_status": "zero excitation" if abs(amplitude) < 1e-12 else "dynamic excitation",
        "duration_s": DEFAULT_DURATION_S,
        "dt_ms": DEFAULT_DT_MS,
        "controller_sample_time_ms": DEFAULT_CONTROLLER_TS_MS,
        "Tlog_ms": DEFAULT_TLOG_MS,
        "status": "ok",
    }
    try:
        result = simulate(
            params,
            config=SimulationConfig(
                duration_s=DEFAULT_DURATION_S,
                dt_s=DEFAULT_DT_MS / 1000.0,
                controller_sample_time_s=DEFAULT_CONTROLLER_TS_MS / 1000.0,
                log_sample_time_s=DEFAULT_TLOG_MS / 1000.0,
                sensor_noise_tension_N=0.0,
                sensor_noise_omega_rad_s=0.0,
                seed=7,
                output_name="simulation_report_source.csv",
            ),
            excitation=get_excitation_profile(excitation, amplitude),
            write_output=False,
        )
        row.update(
            {
                "tension_rmse_N": result.metrics["tension_rmse_N"],
                "max_overshoot_N": result.metrics["max_overshoot_N"],
                "t90_s": result.metrics["t90_s"],
                "control_effort_rms_V": result.metrics["control_effort_rms_V"],
                "samples": result.metrics["samples"],
            }
        )
    except Exception as exc:  # noqa: BLE001 - report should capture failures.
        row.update(
            {
                "status": "error",
                "error": str(exc),
                "tension_rmse_N": None,
                "max_overshoot_N": None,
                "t90_s": None,
                "control_effort_rms_V": None,
                "samples": 0.0,
            }
        )
    return row


def run_sweep() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for plant in plant_registry():
        for excitation in excitation_names():
            rows.append(run_simulation_case(plant, excitation))
    return rows


def summarize_best_by_plant(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for plant in plant_registry():
        plant_rows = [row for row in rows if row["plant_id"] == plant["plant_id"]]
        valid = [row for row in plant_rows if _safe_float(row.get("tension_rmse_N")) is not None]
        if not valid:
            continue
        best = min(valid, key=lambda row: float(row["tension_rmse_N"]))
        zero_policy = all(abs(float(row["recommended_amplitude_V"])) < 1e-12 for row in valid)
        summary.append(
            {
                "plant_id": plant["plant_id"],
                "material": plant["material"],
                "scale": plant["scale"],
                "EA_N": plant["EA_N"],
                "regime": plant["regime"],
                "recommended_amplitude_V": plant["recommended_excitation_amplitude_V"],
                "best_excitation": "zero-input policy" if zero_policy else best["excitation"],
                "best_tension_rmse_N": best["tension_rmse_N"],
                "best_max_overshoot_N": best["max_overshoot_N"],
                "best_control_effort_rms_V": best["control_effort_rms_V"],
            }
        )
    return summary


def summarize_average_by_excitation(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for excitation in excitation_names():
        excitation_rows = [row for row in rows if row["excitation"] == excitation]
        all_values = _finite_values(excitation_rows, "tension_rmse_N")
        dynamic_values = [
            float(row["tension_rmse_N"])
            for row in excitation_rows
            if _safe_float(row.get("tension_rmse_N")) is not None
            and abs(float(row["recommended_amplitude_V"])) > 1e-12
        ]
        summary.append(
            {
                "excitation": excitation,
                "all_plants_mean_tension_rmse_N": mean(all_values) if all_values else None,
                "dynamic_cases_mean_tension_rmse_N": mean(dynamic_values) if dynamic_values else None,
                "valid_cases": len(all_values),
                "dynamic_cases": len(dynamic_values),
            }
        )
    return summary


def _draw_title(draw: ImageDraw.ImageDraw, title: str, subtitle: str | None = None) -> None:
    draw.text((42, 30), title, fill=TEXT, font=_font(30, True))
    if subtitle:
        draw.text((42, 70), subtitle, fill=MUTED, font=_font(18))


def _color_interp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _heat_color(t: float) -> tuple[int, int, int]:
    if t < 0.5:
        return _color_interp((63, 171, 103), (255, 205, 86), t * 2.0)
    return _color_interp((255, 205, 86), (214, 73, 73), (t - 0.5) * 2.0)


def write_heatmap(rows: Sequence[dict[str, Any]], path: Path) -> str:
    plants = [plant["plant_id"] for plant in plant_registry()]
    excitations = list(excitation_names())
    width, height = 1270, 880
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    _draw_title(
        draw,
        "Simulation Tension RMSE: Plant x Excitation",
        "Cell values are tension_rmse_N. Lower values are better; color uses log scaling.",
    )
    left, top, cell_w, cell_h = 210, 140, 190, 58
    lookup = {(row["plant_id"], row["excitation"]): row for row in rows}
    positive_values = [max(value, 1e-12) for value in _finite_values(rows, "tension_rmse_N")]
    log_values = [math.log10(value) for value in positive_values]
    lo, hi = min(log_values), max(log_values)
    if hi == lo:
        hi = lo + 1.0

    for col, excitation in enumerate(excitations):
        x = left + col * cell_w
        tw, _ = _text_size(draw, excitation, _font(17, True))
        draw.text((x + (cell_w - tw) / 2, top - 34), excitation, fill=TEXT, font=_font(17, True))

    for row_idx, plant_id in enumerate(plants):
        y = top + row_idx * cell_h
        plant = next(item for item in plant_registry() if item["plant_id"] == plant_id)
        draw.text((30, y + 10), f"{plant_id}  EA={_format_metric(plant['EA_N'], 3)}", fill=TEXT, font=_font(15, True))
        for col, excitation in enumerate(excitations):
            x = left + col * cell_w
            item = lookup[(plant_id, excitation)]
            value = _safe_float(item.get("tension_rmse_N"))
            if value is None:
                color = (226, 232, 240)
                label = "error"
            else:
                log_value = math.log10(max(value, 1e-12))
                score = (log_value - lo) / (hi - lo)
                color = _heat_color(score)
                label = _format_metric(value, 3)
            draw.rounded_rectangle([x, y, x + cell_w - 10, y + cell_h - 8], radius=8, fill=color, outline="white", width=2)
            label_font = _font(16, True)
            tw, th = _text_size(draw, label, label_font)
            draw.text((x + (cell_w - 10 - tw) / 2, y + (cell_h - 8 - th) / 2), label, fill=(17, 24, 39), font=label_font)

    legend_y = top + len(plants) * cell_h + 35
    draw.text((left, legend_y), "Lower RMSE", fill=MUTED, font=_font(15))
    for i in range(160):
        draw.line((left + 105 + i, legend_y + 8, left + 105 + i, legend_y + 28), fill=_heat_color(i / 159.0))
    draw.text((left + 295, legend_y), "Higher RMSE", fill=MUTED, font=_font(15))
    draw.text(
        (42, height - 58),
        "Note: P03-P10 use zero recommended excitation in the current dashboard model because EA is outside the extracted baseline range.",
        fill=MUTED,
        font=_font(15),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return str(path)


def _draw_log_axes(
    draw: ImageDraw.ImageDraw,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
    values: Sequence[float],
    ylabel: str,
) -> tuple[float, float]:
    positive = [max(value, 1e-12) for value in values if value is not None]
    if not positive:
        positive = [1.0]
    log_min = math.floor(min(math.log10(value) for value in positive))
    log_max = math.ceil(max(math.log10(value) for value in positive))
    if log_max <= log_min:
        log_max = log_min + 1
    draw.line((left, bottom, right, bottom), fill=TEXT, width=2)
    draw.line((left, top, left, bottom), fill=TEXT, width=2)
    tick_count = min(7, log_max - log_min + 1)
    step = (log_max - log_min) / max(1, tick_count - 1)
    for idx in range(tick_count):
        tick = log_min + idx * step
        y = bottom - (bottom - top) * (tick - log_min) / (log_max - log_min)
        draw.line((left, y, right, y), fill=GRID, width=1)
        draw.text((left - 92, y - 10), f"1e{int(round(tick))}", fill=MUTED, font=_font(14))
    draw.text((left, top - 30), ylabel, fill=MUTED, font=_font(15))
    return float(log_min), float(log_max)


def write_best_by_plant_chart(rows: Sequence[dict[str, Any]], path: Path) -> str:
    width, height = 1240, 760
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    _draw_title(
        draw,
        "Best Simulation Result by Plant",
        "Lowest tension_rmse_N across the five excitation choices; log scale keeps zero-input and outlier cases visible.",
    )
    left, top, right, bottom = 105, 135, 1165, 580
    values = _finite_values(rows, "best_tension_rmse_N")
    log_min, log_max = _draw_log_axes(
        draw,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        values=values,
        ylabel="tension_rmse_N (log scale)",
    )

    def y_to_px(value: float) -> float:
        log_value = math.log10(max(value, 1e-12))
        return bottom - (bottom - top) * (log_value - log_min) / (log_max - log_min)

    group_w = (right - left) / len(rows)
    for idx, row in enumerate(rows):
        value = _safe_float(row.get("best_tension_rmse_N"))
        if value is None:
            continue
        cx = left + group_w * idx + group_w / 2
        bar_w = min(54, group_w * 0.58)
        y_value = y_to_px(value)
        color = GREEN if row["recommended_amplitude_V"] else GRAY
        draw.rounded_rectangle([cx - bar_w / 2, y_value, cx + bar_w / 2, bottom], radius=7, fill=color)
        text = _format_metric(value, 3)
        tw, _ = _text_size(draw, text, _font(13, True))
        draw.text((cx - tw / 2, max(top + 5, y_value - 22)), text, fill=TEXT, font=_font(13, True))
        plant_label = str(row["plant_id"])
        tw, _ = _text_size(draw, plant_label, _font(14, True))
        draw.text((cx - tw / 2, bottom + 14), plant_label, fill=TEXT, font=_font(14, True))
        short = "zero" if "zero" in str(row["best_excitation"]) else str(row["best_excitation"])
        tw, _ = _text_size(draw, short, _font(12))
        draw.text((cx - tw / 2, bottom + 36), short, fill=MUTED, font=_font(12))
    legend_y = 650
    draw.rounded_rectangle([left + 15, legend_y, left + 32, legend_y + 17], radius=3, fill=GREEN)
    draw.text((left + 42, legend_y - 2), "Dynamic excitation", fill=MUTED, font=_font(14))
    draw.rounded_rectangle([left + 185, legend_y, left + 202, legend_y + 17], radius=3, fill=GRAY)
    draw.text((left + 212, legend_y - 2), "Zero-input safety policy", fill=MUTED, font=_font(14))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return str(path)


def write_average_by_excitation_chart(rows: Sequence[dict[str, Any]], path: Path) -> str:
    width, height = 1180, 720
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    _draw_title(
        draw,
        "Average Tension RMSE by Excitation",
        "Grouped bars compare all plants to dynamic-amplitude cases only.",
    )
    left, top, right, bottom = 105, 135, 1110, 580
    values = _finite_values(rows, "all_plants_mean_tension_rmse_N") + _finite_values(rows, "dynamic_cases_mean_tension_rmse_N")
    log_min, log_max = _draw_log_axes(
        draw,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        values=values,
        ylabel="tension_rmse_N (log scale)",
    )

    def y_to_px(value: float) -> float:
        log_value = math.log10(max(value, 1e-12))
        return bottom - (bottom - top) * (log_value - log_min) / (log_max - log_min)

    group_w = (right - left) / len(rows)
    bar_w = 42
    for idx, row in enumerate(rows):
        cx = left + group_w * idx + group_w / 2
        for offset, key, color, label_shift, label_floor in (
            (-bar_w / 2 - 4, "all_plants_mean_tension_rmse_N", BLUE, -50, top + 5),
            (bar_w / 2 + 4, "dynamic_cases_mean_tension_rmse_N", ORANGE, -15, top + 24),
        ):
            value = _safe_float(row.get(key))
            if value is None:
                continue
            y_value = y_to_px(value)
            x0 = cx + offset - bar_w / 2
            x1 = cx + offset + bar_w / 2
            draw.rounded_rectangle([x0, y_value, x1, bottom], radius=6, fill=color)
            text = _format_metric(value, 3)
            label_font = _font(12, True)
            tw, _ = _text_size(draw, text, label_font)
            draw.text((x0 + (bar_w - tw) / 2, max(label_floor, y_value + label_shift)), text, fill=TEXT, font=label_font)
        label = str(row["excitation"])
        tw, _ = _text_size(draw, label, _font(14, True))
        draw.text((cx - tw / 2, bottom + 16), label, fill=TEXT, font=_font(14, True))
    draw.rounded_rectangle([left + 15, 610, left + 32, 627], radius=3, fill=BLUE)
    draw.text((left + 42, 608), "All P01-P10", fill=MUTED, font=_font(14))
    draw.rounded_rectangle([left + 175, 610, left + 192, 627], radius=3, fill=ORANGE)
    draw.text((left + 202, 608), "Dynamic P01-P02 only", fill=MUTED, font=_font(14))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return str(path)


def write_ea_scatter_chart(rows: Sequence[dict[str, Any]], path: Path) -> str:
    width, height = 1120, 680
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    _draw_title(
        draw,
        "Plant EA vs Best Tension RMSE",
        "This shows how plant stiffness maps to the best available simulation error in the current dashboard model.",
    )
    left, top, right, bottom = 110, 135, 1045, 540
    x_values = [max(float(row["EA_N"]), 1e-12) for row in rows]
    y_values = [max(float(row["best_tension_rmse_N"]), 1e-12) for row in rows if _safe_float(row.get("best_tension_rmse_N")) is not None]
    x_lo, x_hi = math.floor(min(math.log10(x) for x in x_values)), math.ceil(max(math.log10(x) for x in x_values))
    y_lo, y_hi = _draw_log_axes(draw, left=left, top=top, right=right, bottom=bottom, values=y_values, ylabel="best tension_rmse_N (log scale)")
    draw.text((left, bottom + 52), "EA_N (log scale)", fill=MUTED, font=_font(15))
    for idx in range(x_lo, x_hi + 1):
        x = left + (right - left) * (idx - x_lo) / max(1, x_hi - x_lo)
        draw.line((x, top, x, bottom), fill=GRID, width=1)
        draw.text((x - 16, bottom + 17), f"1e{idx}", fill=MUTED, font=_font(13))

    def x_to_px(value: float) -> float:
        return left + (right - left) * (math.log10(max(value, 1e-12)) - x_lo) / max(1, x_hi - x_lo)

    def y_to_px(value: float) -> float:
        return bottom - (bottom - top) * (math.log10(max(value, 1e-12)) - y_lo) / (y_hi - y_lo)

    label_offsets = {
        "P01": (12, -10),
        "P02": (12, -10),
        "P03": (-38, -22),
        "P04": (12, -14),
        "P05": (12, -22),
        "P06": (-42, 8),
        "P07": (12, 8),
        "P08": (12, -14),
        "P09": (-42, -2),
        "P10": (12, 18),
    }
    for row in rows:
        value = _safe_float(row.get("best_tension_rmse_N"))
        if value is None:
            continue
        x = x_to_px(float(row["EA_N"]))
        y = y_to_px(value)
        color = GREEN if row["recommended_amplitude_V"] else GRAY
        draw.ellipse([x - 9, y - 9, x + 9, y + 9], fill=color, outline="white", width=2)
        dx, dy = label_offsets.get(str(row["plant_id"]), (12, -10))
        draw.text((x + dx, y + dy), str(row["plant_id"]), fill=TEXT, font=_font(13, True))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return str(path)


def build_pdf(summary: dict[str, Any]) -> str:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=landscape(A4),
        rightMargin=0.42 * inch,
        leftMargin=0.42 * inch,
        topMargin=0.38 * inch,
        bottomMargin=0.38 * inch,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CenterTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=22, leading=26, textColor=colors.HexColor("#17324D")))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8.2, leading=10.2, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="Note", parent=styles["BodyText"], fontSize=8.5, leading=10.5, textColor=colors.HexColor("#586372")))
    story: list[Any] = []

    story.append(Paragraph("Simulation Plant and Excitation Comparison Report", styles["CenterTitle"]))
    story.append(Paragraph(f"Generated from the existing dashboard model on {summary['generated_at']}", styles["Note"]))
    story.append(Spacer(1, 0.12 * inch))

    story.append(Paragraph("1. What Was Run", styles["Heading1"]))
    story.append(
        Paragraph(
            "The existing simulation model was run for every plant P01-P10 and every excitation profile ET1, ET3, ET6, E_Toggle, and EVR. "
            "No model equations, plant values, excitation functions, or dashboard UI files were changed. Each run used the Simulation tab defaults: "
            "4 s duration, 1 ms RK4 physics step, 10 ms controller update, 10 ms logging, no sensor noise, and the plant's current recommended excitation amplitude.",
            styles["BodyText"],
        )
    )
    story.append(Paragraph("Important model note: the current extracted reference applies plant-specific EA. The per-roller R, J, f, L, and b arrays remain the current baseline arrays unless those exact arrays are supplied in the project reference.", styles["Note"]))

    story.append(Paragraph("2. Plant Definitions and Differences", styles["Heading1"]))
    plant_rows = [["Plant", "Material", "Scale", "EA (N)", "Regime", "ζ CL,min", "Paper OS%", "Recommended amp (V)", "Dynamic?"]]
    for plant in plant_registry():
        plant_rows.append(
            [
                plant["plant_id"],
                plant["material"],
                plant["scale"],
                _format_metric(plant["EA_N"]),
                plant["regime"],
                _format_metric(plant["zeta_cl_min"], 3),
                _format_metric(plant["overshoot_percent"], 3),
                _format_metric(plant["recommended_excitation_amplitude_V"], 4),
                "yes" if plant["recommended_excitation_amplitude_V"] else "zero input",
            ]
        )
    story.append(_pdf_table(plant_rows, repeat_rows=1, font_size=7.2))
    story.append(Paragraph("Plants differ by material, production scale, axial stiffness EA, damping/regime label, and supplement overshoot value. In this dashboard model run, EA is the plant parameter that is numerically applied to the simulator.", styles["Note"]))

    story.append(Paragraph("3. Excitation Definitions and Changing Factors", styles["Heading1"]))
    excitation_rows = [["Excitation", "Type", "Channels", "Changing factors"]]
    for name in excitation_names():
        desc = EXCITATION_DESCRIPTIONS[name]
        excitation_rows.append([name, desc["kind"], desc["channels"], desc["changing_factors"]])
    story.append(_pdf_table(excitation_rows, repeat_rows=1, font_size=7.2, col_widths=[0.85 * inch, 1.55 * inch, 1.25 * inch, 6.8 * inch]))
    story.append(Paragraph("Changing excitation changes waveform type, active motor channels, frequency content, phase/staggering, and how much the web-tension states move during the run. That is why the metrics are different when the excitation type changes.", styles["Note"]))

    story.append(PageBreak())
    story.append(Paragraph("4. Graph Comparison", styles["Heading1"]))
    for key, caption in (
        ("heatmap", "Figure 1. Plant x excitation heatmap using tension RMSE."),
        ("best_by_plant", "Figure 2. Best excitation choice by plant."),
        ("average_by_excitation", "Figure 3. Average tension RMSE by excitation."),
        ("ea_scatter", "Figure 4. Plant EA compared with best available tension RMSE."),
    ):
        story.append(PdfImage(str(CHART_PATHS[key]), width=7.6 * inch, height=4.3 * inch))
        story.append(Paragraph(caption, styles["Note"]))
        story.append(Spacer(1, 0.08 * inch))

    story.append(PageBreak())
    story.append(Paragraph("5. Best Result by Plant", styles["Heading1"]))
    best_rows = [["Plant", "EA (N)", "Regime", "Amp (V)", "Best excitation", "Best RMSE (N)", "Overshoot (N)", "Control RMS (V)"]]
    for row in summary["best_by_plant"]:
        best_rows.append(
            [
                row["plant_id"],
                _format_metric(row["EA_N"]),
                row["regime"],
                _format_metric(row["recommended_amplitude_V"], 4),
                row["best_excitation"],
                _format_metric(row["best_tension_rmse_N"], 4),
                _format_metric(row["best_max_overshoot_N"], 4),
                _format_metric(row["best_control_effort_rms_V"], 4),
            ]
        )
    story.append(_pdf_table(best_rows, repeat_rows=1, font_size=7.2))

    story.append(Paragraph("6. Full Simulation Table", styles["Heading1"]))
    full_rows = [["Plant", "Excitation", "Amp (V)", "Input", "Tension RMSE (N)", "Max overshoot (N)", "t90 (s)", "Control RMS (V)"]]
    for row in summary["matrix_rows"]:
        full_rows.append(
            [
                row["plant_id"],
                row["excitation"],
                _format_metric(row["recommended_amplitude_V"], 4),
                row["input_status"],
                _format_metric(row["tension_rmse_N"], 4),
                _format_metric(row["max_overshoot_N"], 4),
                _format_metric(row["t90_s"], 4),
                _format_metric(row["control_effort_rms_V"], 4),
            ]
        )
    story.append(_pdf_table(full_rows, repeat_rows=1, font_size=6.2))

    story.append(PageBreak())
    story.append(Paragraph("7. Main Interpretation", styles["Heading1"]))
    for item in summary["interpretation"]:
        story.append(Paragraph(item, styles["BodyText"]))
    story.append(Paragraph("8. Stored Artifacts", styles["Heading1"]))
    artifact_rows = [["Type", "Description", "Path"]]
    for artifact in summary["artifacts"]:
        artifact_rows.append([artifact["type"], artifact["description"], artifact["path"]])
    story.append(_pdf_table(artifact_rows, repeat_rows=1, font_size=7.0, col_widths=[0.8 * inch, 2.35 * inch, 7.0 * inch]))

    doc.build(story)
    return str(PDF_PATH)


def _pdf_table(
    rows: Sequence[Sequence[Any]],
    *,
    repeat_rows: int = 1,
    font_size: float = 7.0,
    col_widths: Sequence[float] | None = None,
) -> Table:
    safe_rows = [[Paragraph(str(cell), getSampleStyleSheet()["BodyText"]) if isinstance(cell, str) and len(cell) > 34 else cell for cell in row] for row in rows]
    table = Table(safe_rows, repeatRows=repeat_rows, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F1FF")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17324D")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("LEADING", (0, 0), (-1, -1), font_size + 1.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]
        )
    )
    return table


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    matrix_rows = run_sweep()
    best_by_plant = summarize_best_by_plant(matrix_rows)
    average_by_excitation = summarize_average_by_excitation(matrix_rows)
    csv_path = _csv_write(CSV_PATH, matrix_rows)

    chart_paths = {
        "heatmap": write_heatmap(matrix_rows, CHART_PATHS["heatmap"]),
        "best_by_plant": write_best_by_plant_chart(best_by_plant, CHART_PATHS["best_by_plant"]),
        "average_by_excitation": write_average_by_excitation_chart(average_by_excitation, CHART_PATHS["average_by_excitation"]),
        "ea_scatter": write_ea_scatter_chart(best_by_plant, CHART_PATHS["ea_scatter"]),
    }

    valid = [row for row in matrix_rows if _safe_float(row.get("tension_rmse_N")) is not None]
    dynamic = [row for row in valid if abs(float(row["recommended_amplitude_V"])) > 1e-12]
    best_dynamic = min(dynamic, key=lambda row: float(row["tension_rmse_N"])) if dynamic else None
    worst_dynamic = max(dynamic, key=lambda row: float(row["tension_rmse_N"])) if dynamic else None

    summary: dict[str, Any] = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "method": {
            "duration_s": DEFAULT_DURATION_S,
            "dt_ms": DEFAULT_DT_MS,
            "controller_sample_time_ms": DEFAULT_CONTROLLER_TS_MS,
            "Tlog_ms": DEFAULT_TLOG_MS,
            "plants": len(plant_registry()),
            "excitations": list(excitation_names()),
            "matrix_cases": len(matrix_rows),
        },
        "matrix_rows": matrix_rows,
        "best_by_plant": best_by_plant,
        "average_by_excitation": average_by_excitation,
        "best_dynamic_case": best_dynamic,
        "worst_dynamic_case": worst_dynamic,
        "interpretation": [
            "Changing plant changes the simulation because plant EA changes the web stiffness and therefore the speed-to-tension coupling. The current project reference also labels plants by material, scale, closed-loop damping regime, and paper overshoot percentage.",
            "Changing excitation changes the simulation because each excitation has a different input waveform, active channel set, frequency content, and phase/staggering. These differences change how strongly each roller and span is disturbed.",
            "P01 and P02 are the only plants inside the extracted baseline EA range, so the dashboard gives them nonzero recommended excitation. P03-P10 are outside that range and use zero recommended excitation for numerical safety in this current model.",
            "The high-EA zero-input rows are not a full dynamic validation of those plants. They show the current dashboard safety policy. To dynamically validate P03-P10, the model should be supplied with the exact per-plant R, J, f, L, and b arrays plus retuned excitation limits.",
        ],
        "csv_path": csv_path,
        "chart_paths": chart_paths,
        "artifacts": [
            {"type": "PDF", "description": "Simulation comparison report", "path": str(PDF_PATH)},
            {"type": "CSV", "description": "50-row plant x excitation simulation sweep", "path": str(CSV_PATH)},
            {"type": "JSON", "description": "Machine-readable report summary", "path": str(JSON_PATH)},
            {"type": "PNG", "description": "Tension RMSE heatmap", "path": str(CHART_PATHS["heatmap"])},
            {"type": "PNG", "description": "Best-by-plant chart", "path": str(CHART_PATHS["best_by_plant"])},
            {"type": "PNG", "description": "Average-by-excitation chart", "path": str(CHART_PATHS["average_by_excitation"])},
            {"type": "PNG", "description": "EA scatter chart", "path": str(CHART_PATHS["ea_scatter"])},
        ],
    }
    pdf_path = build_pdf(summary)
    summary["pdf_path"] = pdf_path
    JSON_PATH.write_text(json.dumps(_json_ready(summary), indent=2), encoding="utf-8")
    print(json.dumps({"pdf_path": pdf_path, "json_path": str(JSON_PATH), "csv_path": csv_path, "chart_paths": chart_paths}, indent=2))


if __name__ == "__main__":
    main()
