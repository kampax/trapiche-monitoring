"""
Analyze ERA5-Land hydrological-year precipitation and 2-m air temperature
(1986-2026) alongside Landsat NDVI, EVI, LSWI, and LST (aggregated identically
to generate_landsat_figures.R).
Computes trend statistics, period comparisons, and Spearman/Pearson correlations,
and generates publication-ready Figure A4 (350 DPI, English labels).
"""

from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
LANDSAT_CSV = DATA_DIR / "datos_trapiche_landsat.csv"
ERA5_HYDRO_CSV = DATA_DIR / "datos_trapiche_era5_hydroyear.csv"
FIG_DIR = ROOT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

EXCLUDED_POINT_IDS = {
    6088, 6089, 5895, 5517, 4349, 4156, 4350, 24900, 25279, 25278,
    26827, 26826, 26650, 26649, 26965,
}

# 1. Load and aggregate Landsat identically to generate_landsat_figures.R
raw = pd.read_csv(LANDSAT_CSV)
raw["Point_ID"] = pd.to_numeric(raw["Point_ID"], errors="coerce")
raw["Snow"] = pd.to_numeric(raw["Snow"], errors="coerce")
raw["DateR"] = pd.to_datetime(raw["Date"], errors="coerce")
for col in ["NDVI", "EVI", "LSWI", "LST"]:
    raw[col] = pd.to_numeric(raw[col], errors="coerce")
raw.loc[~raw["EVI"].between(-1, 1), "EVI"] = np.nan

raw = raw[
    raw["DateR"].notna()
    & raw["tratamiento"].notna()
    & raw["Snow"].notna()
    & (raw["Snow"] != 1)
    & (~raw["Point_ID"].isin(EXCLUDED_POINT_IDS))
].copy()

raw["MonthStart"] = raw["DateR"].dt.to_period("M").dt.to_timestamp()


def get_annual_index(df, col):
    monthly = (
        df[df[col].notna()]
        .groupby(["MonthStart", "tratamiento"], as_index=False)[col]
        .median()
    )
    monthly["HydroYear"] = monthly["MonthStart"].dt.year + (monthly["MonthStart"].dt.month >= 7).astype(int)
    monthly = monthly[monthly["HydroYear"] <= 2026]
    annual = (
        monthly.groupby(["tratamiento", "HydroYear"], as_index=False)[col]
        .mean()
    )
    return annual


dfs_idx = []
for col in ["NDVI", "EVI", "LSWI", "LST"]:
    a = get_annual_index(raw, col)
    dfs_idx.append(a.set_index(["tratamiento", "HydroYear"]))

landsat_annual = pd.concat(dfs_idx, axis=1).reset_index()

# Add combined control mean
ctrl_mean = (
    landsat_annual[landsat_annual["tratamiento"].isin(["control 1", "control 2"])]
    .groupby("HydroYear", as_index=False)[["NDVI", "EVI", "LSWI", "LST"]]
    .mean()
)
ctrl_mean["tratamiento"] = "control_mean"
landsat_annual = pd.concat([landsat_annual, ctrl_mean], ignore_index=True)

# 2. Load ERA5 HydroYear data
era5 = pd.read_csv(ERA5_HYDRO_CSV)
era5["Precip_site_lag1"] = era5["Precip_site_mm"].shift(1)
era5["Precip_basin_lag1"] = era5["Precip_basin_mm"].shift(1)

# Trend test on ERA5 precipitation (1986-2026)
slope_s, intercept_s, r_s, p_s, se_s = stats.linregress(era5["HydroYear"], era5["Precip_site_mm"])
tau_s, p_mk_s = stats.kendalltau(era5["HydroYear"], era5["Precip_site_mm"])
slope_t, _, r_t, p_t, _ = stats.linregress(era5["HydroYear"], era5["Temp_site_C"])

print("=== ERA5-Land Long-term Trend (1986-2026, n=41) ===")
print(f"Precipitation (site): slope = {slope_s:.2f} mm/yr ({slope_s*10:.1f} mm/decade), r = {r_s:.3f}, p = {p_s:.4f}; Kendall tau = {tau_s:.3f}, p = {p_mk_s:.4f}")
print(f"Temperature (site):   slope = {slope_t:.3f} C/yr ({slope_t*10:.2f} C/decade), r = {r_t:.3f}, p = {p_t:.4f}")

# Compare pre-dam (1986-1993) vs restoration (2021-2026)
p_predam = era5[era5["HydroYear"].between(1986, 1993)]["Precip_site_mm"]
p_rest = era5[era5["HydroYear"].between(2021, 2026)]["Precip_site_mm"]
u_stat, p_mw = stats.mannwhitneyu(p_predam, p_rest, alternative="two-sided")
print(f"Pre-dam (1986-1993) mean={p_predam.mean():.1f} mm vs Restoration (2021-2026) mean={p_rest.mean():.1f} mm (Mann-Whitney p={p_mw:.4f})")

# 3. Correlations between ERA5 precipitation and Landsat indices
merged = pd.merge(landsat_annual, era5, on="HydroYear", how="inner")
merged.to_csv(DATA_DIR / "merged_landsat_era5_hydroyear.csv", index=False)

corr_rows = []
periods = [
    ("Full (1986-2026)", 1986, 2026),
    ("Post-dam pre-restoration (1996-2019)", 1996, 2019),
    ("Restoration (2020-2026)", 2020, 2026),
]
for period_name, y0, y1 in periods:
    sub_p = merged[merged["HydroYear"].between(y0, y1)]
    for trat in ["control 1", "control 2", "control_mean", "sector restaurado", "sector no restaurado"]:
        sub_t = sub_p[sub_p["tratamiento"] == trat]
        for idx_col in ["NDVI", "EVI", "LSWI", "LST"]:
            for precip_col in ["Precip_site_mm", "Precip_site_lag1"]:
                valid = sub_t[[idx_col, precip_col]].dropna()
                if len(valid) >= 5:
                    rho, p_rho = stats.spearmanr(valid[precip_col], valid[idx_col])
                    r_p, p_r = stats.pearsonr(valid[precip_col], valid[idx_col])
                    corr_rows.append({
                        "Period": period_name,
                        "Treatment": trat,
                        "Index": idx_col,
                        "Precip_var": precip_col,
                        "n": len(valid),
                        "Spearman_rho": round(rho, 3),
                        "Spearman_p": round(p_rho, 4),
                        "Pearson_r": round(r_p, 3),
                        "Pearson_p": round(p_r, 4),
                    })

df_corr = pd.DataFrame(corr_rows)
df_corr.to_csv(DATA_DIR / "era5_ndvi_correlations.csv", index=False)

print("\n=== Correlations: Contemporaneous ERA5 Precip vs Landsat Indices (Full 1986-2026) ===")
print(df_corr[(df_corr["Period"] == "Full (1986-2026)") & (df_corr["Precip_var"] == "Precip_site_mm") & (df_corr["Treatment"].isin(["control_mean", "sector restaurado", "sector no restaurado"]))].to_string(index=False))

print("\n=== Correlations: Contemporaneous ERA5 Precip vs Landsat Indices (Post-dam 1996-2019) ===")
print(df_corr[(df_corr["Period"] == "Post-dam pre-restoration (1996-2019)") & (df_corr["Precip_var"] == "Precip_site_mm") & (df_corr["Treatment"].isin(["control_mean", "sector restaurado", "sector no restaurado"]))].to_string(index=False))

print("\n=== Correlations: 1-yr Lagged ERA5 Precip vs Landsat Indices (Post-dam 1996-2019) ===")
print(df_corr[(df_corr["Period"] == "Post-dam pre-restoration (1996-2019)") & (df_corr["Precip_var"] == "Precip_site_lag1") & (df_corr["Treatment"].isin(["control_mean", "sector restaurado", "sector no restaurado"]))].to_string(index=False))

print("\n=== Correlations: Contemporaneous ERA5 Precip vs Landsat Indices (Restoration 2020-2026) ===")
print(df_corr[(df_corr["Period"] == "Restoration (2020-2026)") & (df_corr["Precip_var"] == "Precip_site_mm") & (df_corr["Treatment"].isin(["control_mean", "sector restaurado", "sector no restaurado"]))].to_string(index=False))

# 4. Generate publication-ready 3-panel Figure A4 (350 DPI, English, matching manuscript serif style)
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.titlesize": 12.5,
    "axes.labelsize": 11.5,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "legend.fontsize": 10.2,
})

fig, (ax1, ax2, ax3) = plt.subplots(
    3, 1, figsize=(11.0, 10.2), sharex=True,
    gridspec_kw={"height_ratios": [1.08, 0.92, 1.0], "hspace": 0.24}
)

# Panel a: ERA5-Land Hydrological-Year Precipitation
mean_p = era5["Precip_site_mm"].mean()
bar_colors = np.where(era5["Precip_site_mm"] >= mean_p, "#2B6CB0", "#B7957B")
ax1.bar(era5["HydroYear"], era5["Precip_site_mm"], color=bar_colors, alpha=0.85, width=0.72, edgecolor="none", zorder=2)

ax1.axhline(mean_p, color="#333333", linestyle=":", linewidth=1.3, zorder=3,
            label=f"1986–2026 mean ({mean_p:.0f} mm)")
trend_y = intercept_s + slope_s * era5["HydroYear"]
ax1.plot(era5["HydroYear"], trend_y, color="#1A365D", linestyle="-", linewidth=1.6, zorder=4,
         label=f"Linear trend ({slope_s*10:.1f} mm decade$^{{-1}}$, p = {p_s:.3f})")

ax1.axvline(1995, color="#C62828", linestyle="--", linewidth=1.2, zorder=5)
ax1.axvline(2020, color="#2E7D32", linestyle="-.", linewidth=1.2, zorder=5)

ax1.text(1995, 430, "Dam construction", color="#C62828", ha="center", va="bottom",
         fontsize=10.5, fontweight="bold",
         bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="none", alpha=0.9))
ax1.text(2020, 430, "Restoration", color="#2E7D32", ha="center", va="bottom",
         fontsize=10.5, fontweight="bold",
         bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="none", alpha=0.9))

ax1.annotate(
    "2011–2012 La Niña\n(359 mm)",
    xy=(2012, 362), xytext=(2004.8, 375),
    fontsize=9.6, color="#1A365D", fontweight="bold", ha="center",
    arrowprops=dict(arrowstyle="->", color="#1A365D", lw=1.1, connectionstyle="arc3,rad=-0.1"),
    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#2B6CB0", alpha=0.95, lw=0.8)
)

ax1.axvspan(2024.5, 2026.5, color="#F6E05E", alpha=0.22, zorder=1)
ax1.text(2025.5, 312, "2025–2026\n(below mean)", fontsize=9.0, ha="center", va="center",
         color="#744210", fontweight="bold",
         bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="#D69E2E", alpha=0.95, lw=0.8))

ax1.set_ylim(0, 475)
ax1.set_ylabel("Precipitation (mm yr$^{-1}$)")
ax1.set_title("a) Annual precipitation by hydrological year (July–June, ERA5-Land)", loc="left", fontweight="bold", pad=24)
ax1.grid(axis="y", color="grey", linestyle="-", linewidth=0.35, alpha=0.45, zorder=0)
ax1.spines["top"].set_visible(False)
ax1.spines["right"].set_visible(False)
ax1.legend(loc="upper center", bbox_to_anchor=(0.5, 1.13), ncol=2, frameon=False, fontsize=10.2)

# Panel b: ERA5-Land Hydrological-Year Mean 2-m Air Temperature
mean_t = era5["Temp_site_C"].mean()
slope_t2, intercept_t2, r_t2, p_t2, _ = stats.linregress(era5["HydroYear"], era5["Temp_site_C"])
trend_t = intercept_t2 + slope_t2 * era5["HydroYear"]

ax2.axvspan(2024.5, 2026.5, color="#F6E05E", alpha=0.22, zorder=1)
ax2.axvline(1995, color="#C62828", linestyle="--", linewidth=1.2, zorder=3)
ax2.axvline(2020, color="#2E7D32", linestyle="-.", linewidth=1.2, zorder=3)
ax2.axvline(2012, color="#2B6CB0", linestyle=":", linewidth=1.1, alpha=0.75, zorder=2)

ax2.axhline(mean_t, color="#333333", linestyle=":", linewidth=1.2, zorder=2,
            label=f"1986–2026 mean ({mean_t:.1f} °C)")
ax2.plot(era5["HydroYear"], era5["Temp_site_C"], color="#C05621", linewidth=1.5,
         marker="o", markersize=4.0, alpha=0.9, zorder=4, label="Mean annual temperature")
ax2.plot(era5["HydroYear"], trend_t, color="#7B341E", linestyle="-", linewidth=1.6, zorder=5,
         label=f"Linear trend (+{slope_t2*10:.2f} °C decade$^{{-1}}$, p = {p_t2:.3f})")

ax2.annotate(
    "2024 (6.7 °C)",
    xy=(2024, 6.65), xytext=(2017.0, 6.55),
    fontsize=9.3, color="#7B341E", fontweight="bold", ha="center",
    arrowprops=dict(arrowstyle="->", color="#7B341E", lw=1.0),
    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#C05621", alpha=0.92, lw=0.7)
)

ax2.set_ylim(2.5, 7.2)
ax2.set_ylabel("2-m air temperature (°C)")
ax2.set_title("b) Mean annual 2-m air temperature by hydrological year (ERA5-Land)", loc="left", fontweight="bold", pad=22)
ax2.grid(axis="y", color="grey", linestyle="-", linewidth=0.35, alpha=0.45, zorder=0)
ax2.spines["top"].set_visible(False)
ax2.spines["right"].set_visible(False)
ax2.legend(loc="upper center", bbox_to_anchor=(0.5, 1.15), ncol=3, frameon=False, fontsize=9.8)

# Panel c: Landsat EVI by treatment to show decoupling during restoration
COLORS = {
    "control_mean": "#1B4D3E",
    "sector restaurado": "#D4A574",
    "sector no restaurado": "#A62C2C",
}
LABELS = {
    "control_mean": "Control (mean)",
    "sector restaurado": "Restored",
    "sector no restaurado": "Unrestored",
}

ax3.axvspan(2024.5, 2026.5, color="#F6E05E", alpha=0.22, zorder=1)
ax3.axvline(1995, color="#C62828", linestyle="--", linewidth=1.2, zorder=3)
ax3.axvline(2020, color="#2E7D32", linestyle="-.", linewidth=1.2, zorder=3)
ax3.axvline(2012, color="#2B6CB0", linestyle=":", linewidth=1.1, alpha=0.75, zorder=2)

for trat in ["control_mean", "sector restaurado", "sector no restaurado"]:
    sub = landsat_annual[landsat_annual["tratamiento"] == trat].sort_values("HydroYear")
    ax3.plot(sub["HydroYear"], sub["EVI"], color=COLORS[trat], linewidth=1.7,
             marker="o", markersize=4.0, label=LABELS[trat], zorder=4)

ax3.set_ylabel("Mean annual EVI (Landsat)")
ax3.set_xlabel("Hydrological year (July–June)")
ax3.set_title("c) Annual Landsat EVI by treatment (2012 wet/cool pulse vs. post-2020 divergence)", loc="left", fontweight="bold", pad=8)
ax3.set_xlim(1985.2, 2026.8)
ax3.xaxis.set_major_locator(mticker.MultipleLocator(5))
ax3.xaxis.set_minor_locator(mticker.MultipleLocator(1))
ax3.grid(axis="y", color="grey", linestyle="-", linewidth=0.35, alpha=0.45, zorder=0)
ax3.spines["top"].set_visible(False)
ax3.spines["right"].set_visible(False)
ax3.legend(loc="upper right", ncol=3, frameon=True, framealpha=0.92, edgecolor="grey")

fig_out = FIG_DIR / "FigureA4_ERA5_precipitation.png"
fig.savefig(fig_out, dpi=350, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"\nSaved figure: {fig_out}")
