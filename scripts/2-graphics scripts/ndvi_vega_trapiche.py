"""
NDVI (Landsat) - Vega Trapiche
Recrea la figura de 4 paneles (2x2) con los periodos:
  A) 1986-1991
  B) 2000-2004
  C) 2005-2009
  D) 2025-2026

Requisitos:
    pip install earthengine-api geemap matplotlib numpy

Antes de correr por primera vez, autenticar GEE:
    earthengine authenticate
o dentro de Python:
    import ee; ee.Authenticate()
"""

import ee
import geemap
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# ---------------------------------------------------------------
# 1) Inicializar Earth Engine
# ---------------------------------------------------------------
try:
    ee.Initialize()
except Exception:
    ee.Authenticate()
    ee.Initialize()

# ---------------------------------------------------------------
# 2) Geometria (poligono provisto por el usuario)
# ---------------------------------------------------------------
geometry = ee.Geometry.Polygon(
    [[[-67.10904468159458, -25.53309894350404],
      [-67.10904468159458, -25.541172642140538],
      [-67.09732879261753, -25.541172642140538],
      [-67.09732879261753, -25.53309894350404]]], None, False)

# ---------------------------------------------------------------
# 3) Periodos a comparar
# ---------------------------------------------------------------
periods = {
    "1986-1993": ("1985-07-01", "1993-07-01"),
    "2000-2004": ("1999-07-01", "2004-07-01"),
    "2021-2026": ("2020-07-01", "2026-07-01"),
    "2025-2026": ("2024-07-01", "2026-07-01"),
}

# ---------------------------------------------------------------
# 4) Funciones auxiliares: mascara de nubes + NDVI por sensor
# ---------------------------------------------------------------
def mask_l457_sr(img):
    qa = img.select('QA_PIXEL')
    cloud_mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
    sat_mask = img.select('QA_RADSAT').eq(0)
    optical = img.select('SR_B.').multiply(0.0000275).add(-0.2)
    return img.addBands(optical, None, True).updateMask(cloud_mask).updateMask(sat_mask)


def mask_l89_sr(img):
    qa = img.select('QA_PIXEL')
    cloud_mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
    sat_mask = img.select('QA_RADSAT').eq(0)
    optical = img.select('SR_B.').multiply(0.0000275).add(-0.2)
    return img.addBands(optical, None, True).updateMask(cloud_mask).updateMask(sat_mask)


def ndvi_l457(img):
    return img.normalizedDifference(['SR_B4', 'SR_B3']).rename('NDVI')


def ndvi_l89(img):
    return img.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI')


def get_ndvi_composite(start, end, geom, month_ranges=None):
    """Combina L5/L7 (para <2013) y L8/L9 (para >=2013) segun el rango de fechas."""
    month_filter = None
    if month_ranges:
        for start_month, end_month in month_ranges:
            range_filter = ee.Filter.calendarRange(start_month, end_month, 'month')
            month_filter = range_filter if month_filter is None else ee.Filter.Or(month_filter, range_filter)

    def build_collection(collection_id, mask_fn, ndvi_fn):
        collection = (ee.ImageCollection(collection_id)
                      .filterDate(start, end)
                      .filterBounds(geom))
        if month_filter is not None:
            collection = collection.filter(month_filter)
        return collection.map(mask_fn).map(ndvi_fn)

    l5 = build_collection('LANDSAT/LT05/C02/T1_L2', mask_l457_sr, ndvi_l457)
    l7 = build_collection('LANDSAT/LE07/C02/T1_L2', mask_l457_sr, ndvi_l457)
    l8 = build_collection('LANDSAT/LC08/C02/T1_L2', mask_l89_sr, ndvi_l89)
    l9 = build_collection('LANDSAT/LC09/C02/T1_L2', mask_l89_sr, ndvi_l89)

    merged = l5.merge(l7).merge(l8).merge(l9)
    composite = merged.median().clip(geom)
    return composite, merged.size()


# ---------------------------------------------------------------
# 5) Descargar arrays NDVI por periodo (via geemap.ee_to_numpy)
# ---------------------------------------------------------------
SCALE = 30  # resolucion Landsat en metros

results = {}
for label, (start, end) in periods.items():
    month_ranges = [(9, 12), (1, 6)] if label == "2025-2026" else None
    composite, n_imgs = get_ndvi_composite(start, end, geometry, month_ranges=month_ranges)
    print(f"{label}: {n_imgs.getInfo()} imagenes Landsat encontradas")

    arr = geemap.ee_to_numpy(
        composite, bands=['NDVI'], region=geometry, scale=SCALE
    )
    results[label] = arr[:, :, 0] if arr is not None else None

# ---------------------------------------------------------------
# 6) Coordenadas del poligono para los ejes
# ---------------------------------------------------------------
coords = geometry.bounds().getInfo()['coordinates'][0]
lons = [c[0] for c in coords]
lats = [c[1] for c in coords]
extent = [min(lons), max(lons), min(lats), max(lats)]

# ---------------------------------------------------------------
# 7) Colormap marron -> amarillo -> verde (0 a 0.5), igual al original
# ---------------------------------------------------------------
ndvi_cmap = LinearSegmentedColormap.from_list(
    "ndvi_brown_yellow_green",
    ["#7b4a12", "#c69214", "#f2e60d", "#a4c400", "#2f6b00"],
    N=256,
)

# ---------------------------------------------------------------
# 8) Graficar 2x2
# ---------------------------------------------------------------
panel_letters = ["a", "b", "c", "d"]
lon_margin = (extent[1] - extent[0]) * 0.2
lon_ticks = [extent[0] + lon_margin, extent[1] - lon_margin]
lat_margin = (extent[3] - extent[2]) * 0.2
lat_ticks = [extent[2] + lat_margin, extent[3] - lat_margin]

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.subplots_adjust(left=0.08, right=0.88, bottom=0.08, top=0.92, hspace=0.04, wspace=0.06)
fig.suptitle("NDVI (Normalized Difference Vegetation Index) - Vega Trapiche",
             fontsize=18, fontweight='bold')

im = None
for ax, letter, (label, arr) in zip(axes.flat, panel_letters, results.items()):
    ax.set_title(f"{letter}) {label}", fontsize=15, fontweight='bold', loc='left')
    if arr is None:
        ax.text(0.5, 0.5, "Sin datos", ha='center', va='center', transform=ax.transAxes)
        continue
    im = ax.imshow(arr, cmap=ndvi_cmap, vmin=0, vmax=0.5, extent=extent, origin='upper')
    ax.set_xticks(lon_ticks)
    ax.set_yticks(lat_ticks)
    ax.set_xticklabels([f"{v:.2f}" for v in lon_ticks], fontsize=16)
    ax.set_yticklabels([f"{v:.2f}" for v in lat_ticks], fontsize=16)
    if letter in ("a", "b"):
        ax.tick_params(axis='x', labelbottom=False)
    else:
        ax.set_xlabel("Longitud", fontsize=16)
    if letter in ("b", "d"):
        ax.tick_params(axis='y', labelleft=False)
    else:
        ax.set_ylabel("Latitud", fontsize=16)

cbar = fig.colorbar(im, ax=axes.ravel().tolist(), label="NDVI", fraction=0.046, pad=0.01)
cbar.ax.tick_params(labelsize=14)
cbar.set_label("NDVI", fontsize=16)

plt.savefig("ndvi_vega_trapiche.png", dpi=200, bbox_inches='tight')
plt.show()
