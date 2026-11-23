"""
Download ERA5-Land Monthly Aggregated precipitation (total_precipitation_sum)
and 2-m air temperature (temperature_2m) for the Trapiche peatland
(Catamarca, Argentina) from Google Earth Engine, aggregated by Southern
Hemisphere hydrological/phenological year (July 1 - June 30), matching the
Landsat NDVI/EVI/LSWI/LST time series (HydroYears 1986-2026).

Uses the ECMWF/ERA5_LAND/MONTHLY_AGGR collection
(bands: total_precipitation_sum in meters -> mm; temperature_2m in K -> °C).
"""

from pathlib import Path
import ee
import pandas as pd
import numpy as np

# Paths (script lives in scripts/1-download scripts/, two levels under Analisis/)
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Initialize Google Earth Engine (run `earthengine authenticate` once beforehand)
try:
    ee.Initialize()
    print("Earth Engine initialized")
except Exception as e:
    print("Earth Engine not initialized. Run `earthengine authenticate` if needed:")
    raise e

# Study area geometry:
# Lower Trapiche peatland (restored/unrestored): 25°32'23.64"S, 67°06'01.13"W (-25.5399, -67.1003)
# Upstream Trapiche peatland (controls): 25°33'38.49"S, 67°04'45.33"W (-25.5607, -67.0793)
# Midpoint of Trapiche peatland study sectors: (-67.090, -25.550)
site_point = ee.Geometry.Point([-67.090, -25.550])
# Also define a 15 km basin buffer covering Trapiche peatland + headwaters (~15 km SE)
basin_geom = ee.Geometry.Point([-67.050, -25.580]).buffer(15000)

# Period: July 1985 through June 2026 -> complete HydroYears 1986 to 2026
START_DATE = "1985-07-01"
END_DATE = "2026-07-01"  # exclusive in GEE filterDate -> includes June 2026

era5 = (
    ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR")
    .filterDate(START_DATE, END_DATE)
    .select(["total_precipitation_sum", "temperature_2m"])
)

print("Number of monthly ERA5-Land images:", era5.size().getInfo())


def extract_series(img):
    # total_precipitation_sum is in meters -> convert to mm (* 1000)
    # temperature_2m is in Kelvin -> convert to °C (- 273.15)
    site_stats = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=site_point,
        scale=11132,
        bestEffort=True,
    )
    basin_stats = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=basin_geom,
        scale=11132,
        bestEffort=True,
    )
    return ee.Feature(
        None,
        {
            "date": img.date().format("YYYY-MM-dd"),
            "year": img.date().get("year"),
            "month": img.date().get("month"),
            "precip_site_m": site_stats.get("total_precipitation_sum"),
            "precip_basin_m": basin_stats.get("total_precipitation_sum"),
            "temp_site_K": site_stats.get("temperature_2m"),
            "temp_basin_K": basin_stats.get("temperature_2m"),
        },
    )


fc = era5.map(extract_series)
features = fc.getInfo()["features"]

rows = []
for feat in features:
    p = feat["properties"]
    rows.append(
        {
            "Date": p["date"],
            "Year": int(p["year"]),
            "Month": int(p["month"]),
            "Precip_site_mm": round(float(p["precip_site_m"]) * 1000.0, 3) if p.get("precip_site_m") is not None else np.nan,
            "Precip_basin_mm": round(float(p["precip_basin_m"]) * 1000.0, 3) if p.get("precip_basin_m") is not None else np.nan,
            "Temp_site_C": round(float(p["temp_site_K"]) - 273.15, 3) if p.get("temp_site_K") is not None else np.nan,
            "Temp_basin_C": round(float(p["temp_basin_K"]) - 273.15, 3) if p.get("temp_basin_K") is not None else np.nan,
        }
    )

df_monthly = pd.DataFrame(rows).sort_values("Date").reset_index(drop=True)

# Assign HydroYear: July of Y-1 through June of Y -> HydroYear = Y
# Exact same definition as generate_landsat_figures.R:
# mutate(HydroYear = year(Month) + if_else(month(Month) >= 7, 1L, 0L))
df_monthly["HydroYear"] = df_monthly["Year"] + (df_monthly["Month"] >= 7).astype(int)

monthly_out = DATA_DIR / "datos_trapiche_era5_monthly.csv"
df_monthly.to_csv(monthly_out, index=False)
print(f"Saved monthly ERA5-Land data: {monthly_out} ({len(df_monthly)} rows)")

# Aggregate by HydroYear (1986-2026)
df_hydro = (
    df_monthly.groupby("HydroYear", as_index=False)
    .agg(
        n_months=("Month", "count"),
        Precip_site_mm=("Precip_site_mm", "sum"),
        Precip_basin_mm=("Precip_basin_mm", "sum"),
        Temp_site_C=("Temp_site_C", "mean"),
        Temp_basin_C=("Temp_basin_C", "mean"),
        Precip_wet_site_mm=("Precip_site_mm", lambda s: s[df_monthly.loc[s.index, "Month"].isin([11, 12, 1, 2, 3, 4])].sum()),
        Precip_wet_basin_mm=("Precip_basin_mm", lambda s: s[df_monthly.loc[s.index, "Month"].isin([11, 12, 1, 2, 3, 4])].sum()),
    )
)

# Compute anomalies and z-scores relative to 1986-2026 mean
for col in ["Precip_site_mm", "Precip_basin_mm"]:
    mean_val = df_hydro[col].mean()
    sd_val = df_hydro[col].std(ddof=1)
    prefix = col.replace("_mm", "")
    df_hydro[f"{prefix}_anom_mm"] = (df_hydro[col] - mean_val).round(2)
    df_hydro[f"{prefix}_zscore"] = ((df_hydro[col] - mean_val) / sd_val).round(3)
    df_hydro[f"{prefix}_pct_of_mean"] = (df_hydro[col] / mean_val * 100.0).round(1)

df_hydro["Precip_site_mm"] = df_hydro["Precip_site_mm"].round(2)
df_hydro["Precip_basin_mm"] = df_hydro["Precip_basin_mm"].round(2)
df_hydro["Precip_wet_site_mm"] = df_hydro["Precip_wet_site_mm"].round(2)
df_hydro["Precip_wet_basin_mm"] = df_hydro["Precip_wet_basin_mm"].round(2)
df_hydro["Temp_site_C"] = df_hydro["Temp_site_C"].round(2)
df_hydro["Temp_basin_C"] = df_hydro["Temp_basin_C"].round(2)

hydro_out = DATA_DIR / "datos_trapiche_era5_hydroyear.csv"
df_hydro.to_csv(hydro_out, index=False)
print(f"Saved hydrological-year ERA5-Land data: {hydro_out} ({len(df_hydro)} rows)")

print("\n--- Summary of ERA5-Land HydroYear Precipitation (1986-2026) ---")
print(f"Site mean ± SD:  {df_hydro['Precip_site_mm'].mean():.1f} ± {df_hydro['Precip_site_mm'].std(ddof=1):.1f} mm/yr (median: {df_hydro['Precip_site_mm'].median():.1f})")
print(f"Basin mean ± SD: {df_hydro['Precip_basin_mm'].mean():.1f} ± {df_hydro['Precip_basin_mm'].std(ddof=1):.1f} mm/yr (median: {df_hydro['Precip_basin_mm'].median():.1f})")
print(f"Site-Basin Pearson r: {df_hydro['Precip_site_mm'].corr(df_hydro['Precip_basin_mm']):.4f}")
print("\nKey periods (Site / Basin mm, z-score):")
for label, yrs in [
    ("Pre-dam (1986-1993)", range(1986, 1994)),
    ("Post-dam dry (1995-2010)", range(1995, 2011)),
    ("2011-2013 wet pulse", [2011, 2012, 2013]),
    ("2011", [2011]),
    ("2012", [2012]),
    ("2013", [2013]),
    ("Restoration (2021-2026)", range(2021, 2027)),
    ("2025", [2025]),
    ("2026", [2026]),
    ("Last 2 seasons (2025-2026)", [2025, 2026]),
]:
    sub = df_hydro[df_hydro["HydroYear"].isin(yrs)]
    print(f"  {label:28s}: Site={sub['Precip_site_mm'].mean():6.1f} mm (z={sub['Precip_site_zscore'].mean():+.2f}) | Basin={sub['Precip_basin_mm'].mean():6.1f} mm (z={sub['Precip_basin_zscore'].mean():+.2f})")

print("\nTop 8 wettest HydroYears (Site):")
print(df_hydro.sort_values("Precip_site_mm", ascending=False)[["HydroYear", "Precip_site_mm", "Precip_site_zscore", "Precip_basin_mm"]].head(8).to_string(index=False))

print("\nLast 10 HydroYears (2017-2026):")
print(df_hydro[df_hydro["HydroYear"] >= 2017][["HydroYear", "Precip_site_mm", "Precip_site_zscore", "Precip_basin_mm", "Temp_site_C"]].to_string(index=False))
