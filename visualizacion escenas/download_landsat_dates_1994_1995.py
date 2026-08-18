import os
import ee
import urllib.request
from pathlib import Path

# Inicializar Earth Engine
try:
    ee.Initialize()
    print("Earth Engine inicializado exitosamente.")
except Exception as e:
    print(f"Error al inicializar Earth Engine: {e}")
    raise

# 1. Definición de Geometría
geometry = ee.Geometry.Polygon(
    [[[-67.11075295829585, -25.530870781324296],
      [-67.11075295829585, -25.553251625895754],
      [-67.08096970939448, -25.553251625895754],
      [-67.08096970939448, -25.530870781324296]]], None, False)

# Directorio de salida para imágenes
output_dir = Path("landsat_dates_1994_1995_images")
output_dir.mkdir(parents=True, exist_ok=True)

# 2. Máscara de Nubes, Sombras y Escala para Landsat 5
def mask_landsat5_sr(image):
    qa_pixel = image.select('QA_PIXEL')
    qa_radsat = image.select('QA_RADSAT')
    
    clear_mask = (
        qa_pixel.bitwiseAnd(1 << 0).eq(0)  # Fill
        .And(qa_pixel.bitwiseAnd(1 << 1).eq(0))  # Dilated Cloud
        .And(qa_pixel.bitwiseAnd(1 << 2).eq(0))  # Cirrus
        .And(qa_pixel.bitwiseAnd(1 << 3).eq(0))  # Cloud
        .And(qa_pixel.bitwiseAnd(1 << 4).eq(0))  # Cloud Shadow
    )
    no_saturation = qa_radsat.eq(0)
    
    optical_bands = image.select(['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7']).multiply(0.0000275).add(-0.2)
    return image.addBands(optical_bands, None, True).updateMask(clear_mask.And(no_saturation))

def add_indices(image):
    # NDVI = (NIR - Red) / (NIR + Red)
    ndvi = image.normalizedDifference(['SR_B4', 'SR_B3']).rename('NDVI')
    
    # NDWI = (Green - NIR) / (Green + NIR)
    ndwi = image.normalizedDifference(['SR_B2', 'SR_B4']).rename('NDWI')
    
    # EVI = 2.5 * ((NIR - Red) / (NIR + 6.0 * Red - 7.5 * Blue + 1.0))
    evi = image.expression(
        '2.5 * ((NIR - RED) / (NIR + 6.0 * RED - 7.5 * BLUE + 1.0))',
        {
            'NIR': image.select('SR_B4'),
            'RED': image.select('SR_B3'),
            'BLUE': image.select('SR_B1')
        }
    ).rename('EVI')
    
    # Enmascarar valores no físicos
    evi_masked = evi.updateMask(evi.gte(-1.0).And(evi.lte(1.0)))
    
    return image.addBands([ndvi, ndwi, evi_masked])

# 3. Consulta de Escenas entre 01-Nov-1994 y 31-Dic-1995
START_DATE = '1994-11-01'
END_DATE = '1995-12-31'

collection = (
    ee.ImageCollection('LANDSAT/LT05/C02/T1_L2')
    .filterBounds(geometry)
    .filterDate(START_DATE, END_DATE)
    .sort('system:time_start')
)

image_list = collection.toList(collection.size().getInfo())
count = image_list.size().getInfo()

print(f"Total de imágenes Landsat 5 encontradas en el período {START_DATE} a {END_DATE}: {count}")

# Visualizaciones
vis_rgb = {'bands': ['SR_B3', 'SR_B2', 'SR_B1'], 'min': 0.02, 'max': 0.25, 'gamma': 1.2}
vis_ndvi = {'min': -0.1, 'max': 0.7, 'palette': ['#d7191c', '#fdae61', '#ffffbf', '#a6d96a', '#1a9641', '#006837']}
vis_evi = {'min': -0.05, 'max': 0.6, 'palette': ['#d7191c', '#fdae61', '#ffffbf', '#a6d96a', '#1a9641', '#006837']}
vis_ndwi = {'min': -0.4, 'max': 0.3, 'palette': ['#a6611a', '#dfc27d', '#f5f5f5', '#80bfac', '#018571', '#003c30']}

region_geojson = geometry.getInfo()
results = []

for i in range(count):
    raw_img = ee.Image(image_list.get(i))
    img_id = raw_img.id().getInfo()
    date_str = raw_img.date().format('YYYY-MM-dd').getInfo()
    
    print(f"\n[{i+1}/{count}] Procesando fecha: {date_str} (ID: {img_id})")
    
    processed_img = add_indices(mask_landsat5_sr(raw_img)).clip(geometry)
    
    # Thumbnails URLs
    rgb_url = processed_img.getThumbURL({'region': region_geojson, 'dimensions': 600, 'format': 'png', **vis_rgb})
    ndvi_url = processed_img.select('NDVI').getThumbURL({'region': region_geojson, 'dimensions': 600, 'format': 'png', **vis_ndvi})
    evi_url = processed_img.select('EVI').getThumbURL({'region': region_geojson, 'dimensions': 600, 'format': 'png', **vis_evi})
    ndwi_url = processed_img.select('NDWI').getThumbURL({'region': region_geojson, 'dimensions': 600, 'format': 'png', **vis_ndwi})
    
    # Rutas locales
    rgb_path = output_dir / f"rgb_{date_str}.png"
    ndvi_path = output_dir / f"ndvi_{date_str}.png"
    evi_path = output_dir / f"evi_{date_str}.png"
    ndwi_path = output_dir / f"ndwi_{date_str}.png"
    
    urllib.request.urlretrieve(rgb_url, rgb_path)
    urllib.request.urlretrieve(ndvi_url, ndvi_path)
    urllib.request.urlretrieve(evi_url, evi_path)
    urllib.request.urlretrieve(ndwi_url, ndwi_path)
    
    print(f"Descargadas imágenes para {date_str}")
    
    results.append({
        "date": date_str,
        "id": img_id,
        "rgb_file": f"landsat_dates_1994_1995_images/rgb_{date_str}.png",
        "ndvi_file": f"landsat_dates_1994_1995_images/ndvi_{date_str}.png",
        "evi_file": f"landsat_dates_1994_1995_images/evi_{date_str}.png",
        "ndwi_file": f"landsat_dates_1994_1995_images/ndwi_{date_str}.png",
    })

print("\nGenerando HTML Dashboard interactivo por fechas...")

html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fechas Landsat 5 (01 Nov 1994 - 31 Dic 1995)</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-dark: #0f172a;
            --card-bg: #1e293b;
            --card-border: #334155;
            --accent-blue: #38bdf8;
            --accent-green: #4ade80;
            --accent-purple: #c084fc;
            --accent-cyan: #2dd4bf;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-primary);
            padding: 2rem;
            line-height: 1.5;
        }}

        header {{
            max-width: 1400px;
            margin: 0 auto 2.5rem auto;
            text-align: center;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 1.5rem;
        }}

        header h1 {{
            font-size: 2.2rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-blue), var(--accent-green));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}

        header p {{
            color: var(--text-secondary);
            font-size: 1.05rem;
        }}

        .meta-info {{
            display: flex;
            justify-content: center;
            gap: 1.5rem;
            margin-top: 1rem;
            font-size: 0.85rem;
            color: var(--accent-cyan);
            flex-wrap: wrap;
        }}

        .meta-info div {{
            background: rgba(51, 65, 85, 0.4);
            padding: 0.4rem 1rem;
            border-radius: 20px;
            border: 1px solid var(--card-border);
        }}

        .section-title {{
            font-size: 1.6rem;
            font-weight: 600;
            margin: 3rem 0 1rem 0;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            max-width: 1400px;
            margin-left: auto;
            margin-right: auto;
        }}

        .section-title::before {{
            content: '';
            display: inline-block;
            width: 8px;
            height: 24px;
            border-radius: 4px;
        }}

        .title-rgb::before {{ background: var(--accent-blue); }}
        .title-ndvi::before {{ background: var(--accent-green); }}
        .title-evi::before {{ background: var(--accent-purple); }}
        .title-ndwi::before {{ background: var(--accent-cyan); }}

        .grid-dates {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            gap: 1.5rem;
            max-width: 1400px;
            margin: 0 auto 2.5rem auto;
        }}

        .image-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: transform 0.25s ease, box-shadow 0.25s ease;
        }}

        .image-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.4);
        }}

        .card-header {{
            padding: 0.75rem 1rem;
            background: rgba(15, 23, 42, 0.7);
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-weight: 600;
            border-bottom: 1px solid var(--card-border);
        }}

        .date-badge {{
            font-size: 0.85rem;
            color: var(--text-primary);
        }}

        .img-wrapper {{
            width: 100%;
            aspect-ratio: 1 / 1;
            background: #020617;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .img-wrapper img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}

        .card-footer {{
            padding: 0.5rem 0.8rem;
            background: rgba(15, 23, 42, 0.4);
            border-top: 1px solid var(--card-border);
            font-size: 0.72rem;
            color: var(--text-secondary);
            margin-top: auto;
            text-align: center;
            word-break: break-all;
        }}

        .legend-bar {{
            max-width: 1400px;
            margin: 0.5rem auto 1.5rem auto;
            padding: 0.75rem 1rem;
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 8px;
        }}

        .legend-gradient {{
            height: 14px;
            border-radius: 4px;
            margin-bottom: 0.4rem;
        }}

        .legend-labels {{
            display: flex;
            justify-content: space-between;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}

        footer {{
            text-align: center;
            color: var(--text-secondary);
            font-size: 0.85rem;
            margin-top: 4rem;
            padding-top: 2rem;
            border-top: 1px solid var(--card-border);
        }}
    </style>
</head>
<body>

    <header>
        <h1>Fechas de Escenas Landsat 5 (01 Nov 1994 - 31 Dic 1995)</h1>
        <p>Visualización individual de las 15 imágenes disponibles libres de nubes en la zona de estudio</p>
        <div class="meta-info">
            <div>Polígono: [-67.1107, -25.5532] a [-67.0810, -25.5309]</div>
            <div>Total de Fechas: 15 Escenas</div>
            <div>Colección: LANDSAT/LT05/C02/T1_L2</div>
        </div>
    </header>

    <!-- 1. SECCIÓN RGB -->
    <div class="section-title title-rgb">Color Real (RGB) por Fecha</div>
    <div class="grid-dates">
"""

for r in results:
    html_content += f"""
        <div class="image-card">
            <div class="card-header">
                <span class="date-badge">📅 {r['date']}</span>
            </div>
            <div class="img-wrapper">
                <img src="{r['rgb_file']}" alt="RGB {r['date']}">
            </div>
            <div class="card-footer">
                ID: {r['id']}
            </div>
        </div>
"""

html_content += """
    </div>

    <!-- 2. SECCIÓN NDVI -->
    <div class="section-title title-ndvi">Índice de Vegetación de Diferencia Normalizada (NDVI)</div>
    <div class="legend-bar">
        <div class="legend-gradient" style="background: linear-gradient(to right, #d7191c, #fdae61, #ffffbf, #a6d96a, #1a9641, #006837);"></div>
        <div class="legend-labels">
            <span>Suelo Desnudo / Agua (-0.1)</span>
            <span>Vegetación Baja (0.3)</span>
            <span>Vegetación Densa (0.7+)</span>
        </div>
    </div>
    <div class="grid-dates">
"""

for r in results:
    html_content += f"""
        <div class="image-card">
            <div class="card-header">
                <span class="date-badge">📅 {r['date']}</span>
            </div>
            <div class="img-wrapper">
                <img src="{r['ndvi_file']}" alt="NDVI {r['date']}">
            </div>
            <div class="card-footer">
                NDVI | {r['date']}
            </div>
        </div>
"""

html_content += """
    </div>

    <!-- 3. SECCIÓN EVI -->
    <div class="section-title title-evi">Índice de Vegetación Mejorado (EVI)</div>
    <div class="legend-bar">
        <div class="legend-gradient" style="background: linear-gradient(to right, #d7191c, #fdae61, #ffffbf, #a6d96a, #1a9641, #006837);"></div>
        <div class="legend-labels">
            <span>Baja Biomasa (-0.05)</span>
            <span>Vegetación Moderada (0.25)</span>
            <span>Vegetación Vigorosa (0.60+)</span>
        </div>
    </div>
    <div class="grid-dates">
"""

for r in results:
    html_content += f"""
        <div class="image-card">
            <div class="card-header">
                <span class="date-badge">📅 {r['date']}</span>
            </div>
            <div class="img-wrapper">
                <img src="{r['evi_file']}" alt="EVI {r['date']}">
            </div>
            <div class="card-footer">
                EVI | {r['date']}
            </div>
        </div>
"""

html_content += """
    </div>

    <!-- 4. SECCIÓN NDWI -->
    <div class="section-title title-ndwi">Índice de Agua de Diferencia Normalizada (NDWI)</div>
    <div class="legend-bar">
        <div class="legend-gradient" style="background: linear-gradient(to right, #a6611a, #dfc27d, #f5f5f5, #80bfac, #018571, #003c30);"></div>
        <div class="legend-labels">
            <span>Zona Seca / Suelo (-0.4)</span>
            <span>Humedad Moderada (0.0)</span>
            <span>Agua / Alta Humedad (0.3+)</span>
        </div>
    </div>
    <div class="grid-dates">
"""

for r in results:
    html_content += f"""
        <div class="image-card">
            <div class="card-header">
                <span class="date-badge">📅 {r['date']}</span>
            </div>
            <div class="img-wrapper">
                <img src="{r['ndwi_file']}" alt="NDWI {r['date']}">
            </div>
            <div class="card-footer">
                NDWI | {r['date']}
            </div>
        </div>
"""

html_content += """
    </div>

    <footer>
        <p>Generado automáticamente mediante Google Earth Engine API & Python</p>
    </footer>

</body>
</html>
"""

html_file = Path("landsat_dates_1994_1995_dashboard.html")
with open(html_file, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"\nHTML Dashboard por fechas generado exitosamente en: {html_file.resolve()}")
