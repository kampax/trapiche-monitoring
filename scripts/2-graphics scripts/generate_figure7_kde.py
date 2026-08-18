"""Generate the phenological KDE comparison used as Figure 7.

The figure compares observations from 2000--2004 and 2020--2026 against the
two-dimensional NDVI density observed in the 1986--1993 reference period.
Observations from July 2025 onward are highlighted in green.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import gaussian_kde


# El script vive en scripts/2-graphics scripts/, dos niveles bajo la raiz del
# proyecto (Analisis/): parents[0] = "2-graphics scripts", parents[1] =
# "scripts", parents[2] = raiz del proyecto.
ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = ROOT / "data" / "datos_trapiche_landsat.csv"
OUTPUT_FILE = ROOT / "figures" / "Figure7.png"

EXCLUDED_POINT_IDS = {
    6088, 6089, 5895, 5517, 4349, 4156, 4350, 24900, 25279, 25278,
    26827, 26826, 26650, 26649, 26965,
}

SEASONS = ["Invierno", "Primavera", "Verano", "Otoño"]
SEASON_COLORS = {
    "Invierno": "#8ecae6", "Primavera": "#95d5b2",
    "Verano": "#ffd166", "Otoño": "#e29578",
}


def southern_doy(day_of_year: pd.Series | np.ndarray) -> np.ndarray:
    """Transform calendar DOY so that day 1 is July 1 in the Southern Hemisphere."""
    values = np.asarray(day_of_year)
    return np.where(values >= 182, values - 181, values + 184)


def season_boundaries() -> list[int]:
    """Return seasonal boundaries on the July--June DOY axis."""
    starts = [(7, 1), (9, 21), (12, 21), (3, 21)]
    boundaries = [
        int(southern_doy([pd.Timestamp(2001, month, day).dayofyear])[0])
        for month, day in starts
    ]
    return boundaries + [365]


def scene_medians() -> pd.DataFrame:
    """Filter Landsat observations and calculate spatial median NDVI per scene."""
    data = pd.read_csv(INPUT_FILE, on_bad_lines="skip", engine="python")
    data["Point_ID"] = pd.to_numeric(data["Point_ID"], errors="coerce").astype("Int64")
    data["Snow"] = pd.to_numeric(data["Snow"], errors="coerce")
    data["NDVI"] = pd.to_numeric(data["NDVI"], errors="coerce")
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce", utc=True).dt.tz_convert(None)
    data = data.dropna(subset=["Date", "tratamiento", "Snow", "NDVI"])
    data = data[(data["Snow"] != 1) & (~data["Point_ID"].isin(EXCLUDED_POINT_IDS))].copy()
    data["Year"] = data["Date"].dt.year
    data["DOY_HS"] = southern_doy(data["Date"].dt.dayofyear)
    return (
        data.groupby(["tratamiento", "Date", "Year", "DOY_HS"], as_index=False)["NDVI"]
        .median().rename(columns={"NDVI": "value"})
    )


def add_season_background(axis: plt.Axes, boundaries: list[int]) -> None:
    """Shade Southern Hemisphere seasons and draw their boundaries."""
    for index, season in enumerate(SEASONS):
        axis.axvspan(boundaries[index], boundaries[index + 1],
                     color=SEASON_COLORS[season], alpha=0.14, linewidth=0, zorder=0)
    for boundary in boundaries[1:-1]:
        axis.axvline(boundary, color="gray", linestyle=":", linewidth=0.8,
                     alpha=0.5, zorder=1)


def generate_figure() -> None:
    """Create the two-panel reference-density comparison."""
    scenes = scene_medians()
    restored = scenes[scenes["tratamiento"] == "sector restaurado"]
    reference = restored[restored["Year"].between(1986, 1993)]
    period_1 = restored[restored["Year"].between(2000, 2004)]
    period_2 = restored[restored["Year"].between(2020, 2026)]

    x_reference = reference["DOY_HS"].to_numpy()
    y_reference = reference["value"].to_numpy()
    x_grid = np.linspace(1, 365, 160)
    y_padding = max((y_reference.max() - y_reference.min()) * 0.08, 0.02)
    y_grid = np.linspace(y_reference.min() - y_padding,
                         y_reference.max() + y_padding, 160)
    x_mesh, y_mesh = np.meshgrid(x_grid, y_grid)
    kernel = gaussian_kde(np.vstack([x_reference, y_reference]), bw_method="scott")
    density = kernel(np.vstack([x_mesh.ravel(), y_mesh.ravel()])).reshape(x_mesh.shape)
    density /= density.max() + 1e-10

    reference_curve = (
        reference.groupby("DOY_HS")["value"].mean()
        .rolling(window=15, min_periods=1, center=True).mean()
    )
    levels = [0.10, 0.30, 0.50, 0.70, 0.85, 0.95, 1.00]
    contour_colors = ["#fff7bc", "#fee391", "#fec44f", "#fe9929", "#ec7014", "#cc4c02"]
    boundaries = season_boundaries()

    sns.set_theme(style="whitegrid", context="talk")
    figure, (top_axis, bottom_axis) = plt.subplots(
        2, 1, figsize=(12, 11.2), sharex=True, sharey=True
    )
    for axis in (top_axis, bottom_axis):
        add_season_background(axis, boundaries)
        axis.contourf(x_mesh, y_mesh, density, levels=levels,
                      colors=contour_colors, alpha=0.70)
        axis.contour(x_mesh, y_mesh, density, levels=levels,
                     colors="black", linewidths=0.4)
        axis.plot(reference_curve.index, reference_curve.values, color="#D4A574",
                  linewidth=2.8, label="Media referencia (1986-1993)")
        axis.set_ylabel("NDVI", fontsize=16)
        axis.tick_params(axis="both", which="major", labelsize=15)
        axis.grid(True, linestyle="--", alpha=0.3)

    secondary_axis = top_axis.secondary_xaxis("top")
    midpoints = [(boundaries[i] + boundaries[i + 1]) / 2 for i in range(4)]
    secondary_axis.set_xticks(midpoints)
    secondary_axis.set_xticklabels(SEASONS, fontsize=13, weight="bold")
    secondary_axis.tick_params(length=0)

    top_axis.scatter(period_1["DOY_HS"], period_1["value"], color="black",
                     s=36, alpha=0.75, label="Obs. 2000-2004", zorder=5)
    top_axis.set_title("a) Período 2000-2004", fontsize=17, weight="bold", pad=32)
    top_axis.legend(loc="upper right", frameon=True, fontsize=12)

    highlighted = period_2[period_2["Date"].between("2025-07-01", "2026-07-31")]
    other_recent = period_2.drop(highlighted.index)
    bottom_axis.scatter(other_recent["DOY_HS"], other_recent["value"], color="black",
                        s=36, alpha=0.75, label="Obs. 2020-2025", zorder=5)
    bottom_axis.scatter(highlighted["DOY_HS"], highlighted["value"], color="green",
                        s=46, alpha=0.9, label="Obs. Jul 2025-Jul 2026", zorder=6)
    bottom_axis.set_title("b) Período 2020-2025", fontsize=17, weight="bold", pad=6)
    bottom_axis.set_xlabel("Día del año (DOY Hemisferio Sur)", fontsize=15, weight="bold")
    bottom_axis.legend(loc="upper right", frameon=True, fontsize=12)

    figure.tight_layout()
    figure.savefig(OUTPUT_FILE, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    print(f"Created {OUTPUT_FILE}")


if __name__ == "__main__":
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    generate_figure()
