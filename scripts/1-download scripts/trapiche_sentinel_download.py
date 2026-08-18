# Script para extracción robusta de índices Sentinel-2 en puntos de Trapiche
# importar librerias necesarias
import ee
import csv
from datetime import datetime, timezone
import geemap
from pathlib import Path

# Ruta base del script
base_dir = Path(__file__).resolve().parent

# Inicializar Earth Engine
try:
    ee.Initialize()
    print('Earth Engine inicializado')
except Exception as e:
    print('Earth Engine no inicializado. Ejecuta ee.Authenticate() si es necesario:')
    print(e)
    # ee.Authenticate()  # Descomenta si necesitas autenticar interactivo
    # ee.Initialize()

# Inicializar geemap (requiere ee.Initialize())
try:
    geemap.ee_initialize()
except Exception:
    pass

# Cargar colección de puntos de interés desde assets
pixels = ee.FeatureCollection('users/CarlosNavarro/Trapiche_NDVI/Trapiche_Sentinel')

# Escenas a excluir manualmente por presencia de nubes en los pixeles de interés
EXCLUDED_SCENES = [
    '20181217T142741_20181217T143739_T19JFM',
    '20190131T142759_20190131T143600_T19JFM',
    '20190511T142759_20190511T143148_T19JFM',
    '20190526T142801_20190526T143809_T19JFM',
    '20190615T142801_20190615T143809_T19JFM',
    '20190625T142801_20190625T143810_T19JFM',
    '20190630T142759_20190630T143601_T19JFM',
    '20190908T142759_20190908T143811_T19JFM',
    '20191013T142731_20191013T143747_T19JFM',
    '20191212T142731_20191212T143721_T19JFM',
    '20200116T142649_20200116T143614_T19JFM',
]

# Filtrar por categorias de tratamiento de interes (sector restaurado, sector no restaurado, control 1, control 2)
pointsOn = pixels.filter(ee.Filter.inList('status', ['restaurado', 'no_rest', 'control1', 'control2']))
# pointsOn = pixels.filter(ee.Filter.eq('ID', 41282))

# Rango de años a procesar (2015-2026)
years = list(range(2016, 2027))  

# definicion de output CSV
output_csv = base_dir.parent.parent / 'data' / 'datos_trapiche_sentinel.csv'

# Función para convertir milisegundos a fecha legible
def format_date_from_millis(millis):
    if millis is None:
        return None
    return datetime.fromtimestamp(float(millis) / 1000, tz=timezone.utc).strftime('%Y-%m-%d')

# Función para excluir escenas problemáticas
def apply_scene_exclusions(collection):
    if not EXCLUDED_SCENES:
        return collection
    return collection.filter(ee.Filter.Not(ee.Filter.inList('system:index', EXCLUDED_SCENES)))

# Función para obtener colección armonizada de Sentinel-2 con bandas renombradas
def get_sentinel_collection(year, roi, start_d=None, end_d=None):
    start_date = start_d if start_d else f'{year}-01-01'
    end_date = end_d if end_d else ('2026-07-14' if year == 2026 else f'{year + 1}-01-01')

    col = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterDate(start_date, end_date)
        .filterBounds(roi)
        .filterMetadata('CLOUD_COVERAGE_ASSESSMENT', 'less_than', 100)
    )

    return apply_scene_exclusions(col)

# Función para aplicar máscara de calidad y escalar reflectancias
def mask_and_scale_sentinel(img):
    scl = img.select('SCL')

    # Replica la mascara SCL del script de referencia.
    scl_mask = scl.eq(1).Or(scl.eq(4)).Or(scl.eq(5)).Or(scl.eq(11))
    snow_mask = scl.eq(11).rename('Snow')

    # Escalado de reflectancias a [0, 1] y renombrado armonizado.
    scaled = (
        img.select(['B2', 'B3', 'B4', 'B8', 'B11', 'B12'], ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2'])
        .multiply(0.0001)
    )
    acq_time = ee.Image.constant(ee.Number(img.get('system:time_start'))).rename('AcqTime').toInt64()

    return scaled.updateMask(scl_mask).addBands([snow_mask, acq_time])

# Función para calcular índices y agregar como bandas al imagen
def calculate_indices(img):
    ndvi = img.normalizedDifference(['NIR', 'Red']).rename('NDVI')
    evi = img.expression(
        '2.5 * ((NIR - Red) / (NIR + 6 * Red - 7.5 * Blue + 1))',
        {'NIR': img.select('NIR'), 'Red': img.select('Red'), 'Blue': img.select('Blue')},
    ).rename('EVI')
    savi = img.expression(
        '((NIR - Red) / (NIR + Red + 0.5)) * 1.5',
        {'NIR': img.select('NIR'), 'Red': img.select('Red')},
    ).rename('SAVI')
    ndwi = img.normalizedDifference(['Green', 'NIR']).rename('NDWI')
    lswi = img.normalizedDifference(['NIR', 'SWIR1']).rename('LSWI')
    return img.addBands([ndvi, evi, savi, ndwi, lswi])


def clean_id(val):
    if val is None:
        return ""
    try:
        return str(int(float(val)))
    except ValueError:
        return str(val).strip()


# Ejecucion robusta por puntos
point_list = pointsOn.toList(pointsOn.size()).getInfo()
roi = pointsOn.geometry()

import pandas as pd

# Check if CSV exists
if output_csv.exists():
    print(f"Reading existing Sentinel data from {output_csv}...")
    df = pd.read_csv(output_csv)
    
    expected_cols = ['Point_ID', 'tratamiento', 'Year', 'Date', 'NDVI', 'EVI', 'SAVI', 'NDWI', 'LSWI', 'Snow']
    for col_name in expected_cols:
        if col_name not in df.columns:
            df[col_name] = None
    df = df[expected_cols]
    
    # Check if we need to download/update 2026 data
    df_2026 = df[df['Year'] == 2026]
    if df_2026.empty:
        max_date_2026 = None
    else:
        max_date_2026 = df_2026['Date'].max()
        
    print(f"Max date in 2026 for Sentinel in CSV: {max_date_2026}")
    
    if max_date_2026 is None or max_date_2026 < '2026-07-13':
        if max_date_2026 is not None:
            # get day after
            from datetime import timedelta
            start_dt = (datetime.strptime(max_date_2026, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            start_dt = '2026-01-01'
            
        end_dt = '2026-07-14'
        
        if start_dt < end_dt:
            print(f"Downloading Sentinel data for 2026 from {start_dt} to {end_dt}...")
            new_records = []
            
            col = get_sentinel_collection(2026, roi, start_d=start_dt, end_d=end_dt).map(mask_and_scale_sentinel).map(calculate_indices)
            
            for p in point_list:
                geom = ee.Geometry(p['geometry'])
                point_id = p['properties'].get('ID', p['id'])
                point_status = p['properties'].get('status', '')
                point_tratamiento = {
                    'control1': 'control 1',
                    'control2': 'control 2',
                    'no_rest': 'sector no restaurado',
                    'restaurado': 'sector restaurado'
                }.get(point_status, '')
                try:
                    data = col.getRegion(geom, scale=10).getInfo()
                    if len(data) <= 1:
                        continue
                    
                    header = data[0]
                    idx = {name: header.index(name) for name in ['AcqTime', 'NDVI', 'EVI', 'SAVI', 'NDWI', 'LSWI', 'Snow']}
                    
                    for row in data[1:]:
                        new_records.append({
                            'Point_ID': clean_id(point_id),
                            'tratamiento': point_tratamiento,
                            'Year': 2026,
                            'Date': format_date_from_millis(row[idx['AcqTime']]),
                            'NDVI': round(float(row[idx['NDVI']]), 3) if row[idx['NDVI']] is not None else None,
                            'EVI': round(float(row[idx['EVI']]), 3) if row[idx['EVI']] is not None else None,
                            'SAVI': round(float(row[idx['SAVI']]), 3) if row[idx['SAVI']] is not None else None,
                            'NDWI': round(float(row[idx['NDWI']]), 3) if row[idx['NDWI']] is not None else None,
                            'LSWI': round(float(row[idx['LSWI']]), 3) if row[idx['LSWI']] is not None else None,
                            'Snow': row[idx['Snow']],
                        })
                    print(f"Punto {point_id} (2026) procesado.")
                except Exception as e:
                    print(f"Error procesando punto {point_id} en 2026: {e}")
                    
            if new_records:
                df_new = pd.DataFrame(new_records)
                df_new['Point_ID'] = df_new['Point_ID'].apply(clean_id)
                df['Point_ID'] = df['Point_ID'].apply(clean_id)
                df = pd.concat([df, df_new], ignore_index=True)
                df.drop_duplicates(subset=['Point_ID', 'Date', 'NDVI', 'NDWI'], inplace=True)
    
    df.to_csv(output_csv, index=False)
    print(f"Sentinel update complete: {output_csv}")
    
else:
    print(f"CSV not found. Performing full Sentinel download from scratch...")
    # Crear carpeta de resultados si no existe
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Point_ID', 'tratamiento', 'Year', 'Date', 'NDVI', 'EVI', 'SAVI', 'NDWI', 'LSWI', 'Snow'])

        for y in years:
            print(f'--- Procesando ano {y} ---')
            col = get_sentinel_collection(y, roi).map(mask_and_scale_sentinel).map(calculate_indices)

            for p in point_list:
                geom = ee.Geometry(p['geometry'])
                point_id = p['properties'].get('ID', p['id'])
                point_status = p['properties'].get('status', '')
                point_tratamiento = {
                    'control1': 'control 1',
                    'control2': 'control 2',
                    'no_rest': 'sector no restaurado',
                    'restaurado': 'sector restaurado'
                }.get(point_status, '')
                try:
                    data = col.getRegion(geom, scale=10).getInfo()

                    if len(data) <= 1:
                        print(f"Punto {p['id']} sin datos validos tras filtros SCL.")
                        continue

                    header = data[0]
                    idx = {name: header.index(name) for name in ['AcqTime', 'NDVI', 'EVI', 'SAVI', 'NDWI', 'LSWI', 'Snow']}

                    # Escribir filas con redondeo a 3 decimales
                    for row in data[1:]:
                        writer.writerow([
                            clean_id(point_id),
                            point_tratamiento,
                            y,
                            format_date_from_millis(row[idx['AcqTime']]),
                            round(float(row[idx['NDVI']]), 3) if row[idx['NDVI']] is not None else None,
                            round(float(row[idx['EVI']]), 3) if row[idx['EVI']] is not None else None,
                            round(float(row[idx['SAVI']]), 3) if row[idx['SAVI']] is not None else None,
                            round(float(row[idx['NDWI']]), 3) if row[idx['NDWI']] is not None else None,
                            round(float(row[idx['LSWI']]), 3) if row[idx['LSWI']] is not None else None,
                            row[idx['Snow']],
                        ])
                    print(f"Punto {p['id']} procesado.")
                except Exception as e:
                    print(f"Error procesando punto {p['id']} en ano {y}: {e}")

    print(f'Extracción Sentinel finalizada: {output_csv}')