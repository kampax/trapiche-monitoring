# Importar librerías necesarias
import ee
import csv
import os
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
pixels = ee.FeatureCollection('users/CarlosNavarro/Trapiche_NDVI/Trapiche_Landsat')

# Escenas a excluir manualmente por presencia de nubes en los pixeles de interés
EXCLUDED_SCENES = [
    # Landsat 5
    'LT05_232078_19840624', 'LT05_232078_19850307', 'LT05_232078_20000128',
    'LT05_232078_20000604', 'LT05_232078_20000722', 'LT05_232078_20000807',
    'LT05_232078_20000823', 'LT05_232078_20000908', 'LT05_232078_20010114',
    'LT05_232078_20010319', 'LT05_232078_20010826', 'LT05_232078_20010911',
    'LT05_232078_20011029', 'LT05_232078_20020202', 'LT05_232078_20020306',
    'LT05_232078_20020728', 'LT05_232078_20030715', 'LT05_232078_20030731',
    'LT05_232078_20030816', 'LT05_232078_20040208', 'LT05_232078_20040530',
    'LT05_232078_20040615', 'LT05_232078_20040701', 'LT05_232078_20040717',
    'LT05_232078_20040802', 'LT05_232078_20040818', 'LT05_232078_20050210',
    'LT05_232078_20050720', 'LT05_232078_20050805', 'LT05_232078_20060504',
    'LT05_232078_20060605', 'LT05_232078_20060909', 'LT05_232078_20061027',
    'LT05_232078_20061230', 'LT05_232078_20070507', 'LT05_232078_20070624',
    'LT05_232078_20070710', 'LT05_232078_20090120', 'LT05_232078_20090731',
    'LT05_232078_20090816', 'LT05_232078_20090901', 'LT05_232078_20100328',
    'LT05_232078_20100531', 'LT05_232078_20100819', 'LT05_232078_20110126',
    'LT05_232078_20110822',

    # Landsat 7
    'LE07_232078_20000628', 'LE07_232078_20000831', 'LE07_232078_20010412',
    'LE07_232078_20010514', 'LE07_232078_20010717', 'LE07_232078_20011224',
    'LE07_232078_20020618', 'LE07_232078_20020720', 'LE07_232078_20020805',
    'LE07_232078_20020821', 'LE07_232078_20030520', 'LE07_232078_20100624',
    'LE07_232078_20110219', 'LE07_232078_20110713', 'LE07_232078_20110729',
    'LE07_232078_20120105', 'LE07_232078_20120222', 'LE07_232078_20120410',
    'LE07_232078_20120715', 'LE07_232078_20120731', 'LE07_232078_20120816',

    # Landsat 8
    'LC08_232078_20130710', 'LC08_232078_20130726', 'LC08_232078_20130827',
    'LC08_232078_20130928', 'LC08_232078_20131014', 'LC08_232078_20140102',
    'LC08_232078_20140526', 'LC08_232078_20140627', 'LC08_232078_20140713',
    'LC08_232078_20140729', 'LC08_232078_20150105', 'LC08_232078_20150326',
    'LC08_232078_20150411', 'LC08_232078_20151020', 'LC08_232078_20170619',
    'LC08_232078_20170721', 'LC08_232078_20180113', 'LC08_232078_20180724',
    'LC08_232078_20180809', 'LC08_232078_20190201', 'LC08_232078_20190625',
    'LC08_232078_20191031', 'LC08_232078_20200103', 'LC08_232078_20200119',
    'LC08_232078_20200220', 'LC08_232078_20200408', 'LC08_232078_20200611',
    'LC08_232078_20200915', 'LC08_232078_20210121', 'LC08_232078_20210513',
    'LC08_232078_20210801', 'LC08_232078_20220108', 'LC08_232078_20220124',
    'LC08_232078_20220601', 'LC08_232078_20221210', 'LC08_232078_20230503',
    'LC08_232078_20250116', 'LC08_232078_20250422', 'LC08_232078_20250508',

    # Landsat 9
    'LC09_232078_20220201', 'LC09_232078_20220508', 'LC09_232078_20230204',
    'LC09_232078_20230324', 'LC09_232078_20250108',
]

# Filtrar por categorias de tratamiento de interes (sector restaurado, sector no restaurado, control 1, control 2)
pointsOn = pixels.filter(ee.Filter.inList('status', ['restaurado', 'no_rest', 'control1', 'control2']))

# Rango de años a procesar (1986-2026)
years = list(range(1986,2027)) 
# definicion de output CSV
output_csv = base_dir.parent.parent / 'data' / 'datos_trapiche_landsat.csv'

# Función para convertir milisegundos a fecha legible
def format_date_from_millis(millis):
    if millis is None:
        return None
    return datetime.fromtimestamp(float(millis) / 1000, tz=timezone.utc).strftime('%Y-%m-%d')

# Función para excluir escenas problemáticas
def apply_scene_exclusions(collection):
    if not EXCLUDED_SCENES:
        return collection
    return (
        collection
        .filter(ee.Filter.Not(ee.Filter.inList('LANDSAT_PRODUCT_ID', EXCLUDED_SCENES)))
        .filter(ee.Filter.Not(ee.Filter.inList('system:index', EXCLUDED_SCENES)))
    )

# Función para obtener colección armonizada de Landsat 5/7/8/9 con bandas renombradas
def get_harmonized_collection(year, start_d=None, end_d=None):
    names = ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2', 'Thermal', 'QA_PIXEL', 'QA_RADSAT']

    start_date = start_d if start_d else f'{year}-01-01'
    end_date = end_d if end_d else ('2026-07-14' if year == 2026 else f'{year + 1}-01-01')

    # Armonizacion de nombres para Landsat 5/7 vs 8/9
    l5 = (
        ee.ImageCollection('LANDSAT/LT05/C02/T1_L2')
        .filterDate(start_date, end_date)
        .select(['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7', 'ST_B6', 'QA_PIXEL', 'QA_RADSAT'], names)
    )

    # Excluir Landsat 7 posterior a mayo de 2003 (SLC-off)
    l7 = (
        ee.ImageCollection('LANDSAT/LE07/C02/T1_L2')
        .filterDate(start_date, end_date)
        .filterDate('1999-01-01', '2003-06-01')
        .select(['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7', 'ST_B6', 'QA_PIXEL', 'QA_RADSAT'], names)
    )

    l8 = (
        ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
        .filterDate(start_date, end_date)
        .select(['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7', 'ST_B10', 'QA_PIXEL', 'QA_RADSAT'], names)
    )

    l9 = (
        ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
        .filterDate(start_date, end_date)
        .select(['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7', 'ST_B10', 'QA_PIXEL', 'QA_RADSAT'], names)
    )

    merged = l5.merge(l7).merge(l8).merge(l9)
    return apply_scene_exclusions(merged)


# Función para aplicar escalado radiométrico a Landsat Collection 2 Level-2.
# En estas colecciones, los factores de reflectancia superficial son los mismos
# para Landsat 5/7/8/9; lo que cambia es el nombre de la banda térmica (ST_B6 vs ST_B10).
def scale_landsat_c2_l2(img):
    sr_scaled = img.select(['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2']).multiply(0.0000275).add(-0.2)
    thermal_scaled = img.select('Thermal').multiply(0.00341802).add(149.0)
    return img.addBands(sr_scaled, None, True).addBands(thermal_scaled, None, True)

# Función para enmascarar pixeles de baja calidad usando QA_PIXEL y QA_RADSAT
def mask_quality_pixels(img):
    qa_pixel = img.select('QA_PIXEL')
    qa_radsat = img.select('QA_RADSAT')

    # Mantener pixeles sin fill, nube dilatada, cirrus, nube, sombra y nieve.
    clear_mask = (
        qa_pixel.bitwiseAnd(1 << 0).eq(0)  # Fill
        .And(qa_pixel.bitwiseAnd(1 << 1).eq(0))  # Dilated cloud
        .And(qa_pixel.bitwiseAnd(1 << 2).eq(0))  # Cirrus
        .And(qa_pixel.bitwiseAnd(1 << 3).eq(0))  # Cloud
        .And(qa_pixel.bitwiseAnd(1 << 4).eq(0))  # Cloud shadow
        .And(qa_pixel.bitwiseAnd(1 << 5).eq(0))  # Snow
    )

    # QA_RADSAT == 0: sin saturacion radiometrica
    no_saturation_mask = qa_radsat.eq(0)
    return img.updateMask(clear_mask.And(no_saturation_mask))

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
    lst = img.select('Thermal').subtract(273.15).rename('LST')
    ndwi = img.normalizedDifference(['Green', 'NIR']).rename('NDWI')
    lswi = img.normalizedDifference(['NIR', 'SWIR1']).rename('LSWI')
    snow = img.select('QA_PIXEL').bitwiseAnd(1 << 5).neq(0).rename('Snow')
    return img.addBands([ndvi, evi, savi, lst, ndwi, lswi, snow])


def clean_id(val):
    if val is None:
        return ""
    try:
        return str(int(float(val)))
    except ValueError:
        return str(val).strip()


def fill_missing_lswi(df, pointsOn, point_list):
    print("LSWI column is missing in the existing CSV. Fetching historical LSWI from Earth Engine...")
    import pandas as pd
    
    names = ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2', 'Thermal', 'QA_PIXEL', 'QA_RADSAT']
    start_date = '1986-01-01'
    end_date = '2026-01-01'
    
    l5 = ee.ImageCollection('LANDSAT/LT05/C02/T1_L2').filterDate(start_date, end_date).select(['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7', 'ST_B6', 'QA_PIXEL', 'QA_RADSAT'], names)
    l7 = ee.ImageCollection('LANDSAT/LE07/C02/T1_L2').filterDate(start_date, end_date).filterDate('1999-01-01', '2003-06-01').select(['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7', 'ST_B6', 'QA_PIXEL', 'QA_RADSAT'], names)
    l8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2').filterDate(start_date, end_date).select(['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7', 'ST_B10', 'QA_PIXEL', 'QA_RADSAT'], names)
    l9 = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2').filterDate(start_date, end_date).select(['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7', 'ST_B10', 'QA_PIXEL', 'QA_RADSAT'], names)
    
    merged = l5.merge(l7).merge(l8).merge(l9)
    col = apply_scene_exclusions(merged).map(scale_landsat_c2_l2).map(mask_quality_pixels).map(calculate_indices)
    col_selected = col.select(['NDVI', 'NDWI', 'LSWI'])
    
    lswi_records = []
    
    for idx_p, p in enumerate(point_list):
        geom = ee.Geometry(p['geometry'])
        point_id = p['properties'].get('ID', p['id'])
        print(f"[{idx_p+1}/{len(point_list)}] Fetching historical LSWI for Point_ID: {point_id}...")
        try:
            data = col_selected.getRegion(geom, scale=30).getInfo()
            if len(data) <= 1:
                continue
                
            header = data[0]
            idx_map = {name: header.index(name) for name in ['time', 'NDVI', 'NDWI', 'LSWI']}
            
            for row in data[1:]:
                date_str = format_date_from_millis(row[idx_map['time']])
                ndvi = round(float(row[idx_map['NDVI']]), 3) if row[idx_map['NDVI']] is not None else None
                ndwi = round(float(row[idx_map['NDWI']]), 3) if row[idx_map['NDWI']] is not None else None
                lswi = round(float(row[idx_map['LSWI']]), 3) if row[idx_map['LSWI']] is not None else None
                
                lswi_records.append({
                    'Point_ID': clean_id(point_id),
                    'Date': date_str,
                    'NDVI': ndvi,
                    'NDWI': ndwi,
                    'LSWI_new': lswi
                })
        except Exception as e:
            print(f"Error fetching LSWI for point {point_id}: {e}")
            
    if lswi_records:
        df_lswi = pd.DataFrame(lswi_records)
        df_lswi.drop_duplicates(subset=['Point_ID', 'Date', 'NDVI', 'NDWI'], inplace=True)
        
        df['Point_ID'] = df['Point_ID'].apply(clean_id)
        df['NDVI'] = df['NDVI'].round(3)
        df['NDWI'] = df['NDWI'].round(3)
        
        df = pd.merge(df, df_lswi, on=['Point_ID', 'Date', 'NDVI', 'NDWI'], how='left')
        if 'LSWI_new' in df.columns:
            df['LSWI'] = df['LSWI_new']
            df.drop(columns=['LSWI_new'], inplace=True)
        else:
            df['LSWI'] = None
    else:
        df['LSWI'] = None
        
    return df


# Ejecucion robusta por puntos
point_list = pointsOn.toList(pointsOn.size()).getInfo()

import pandas as pd

# Check if CSV exists
if output_csv.exists():
    print(f"Reading existing Landsat data from {output_csv}...")
    df = pd.read_csv(output_csv)
    
    # 1. Check if LSWI is missing
    if 'LSWI' not in df.columns:
        df = fill_missing_lswi(df, pointsOn, point_list)
        
    expected_cols = ['Point_ID', 'tratamiento', 'Year', 'Date', 'NDVI', 'EVI', 'SAVI', 'LST', 'NDWI', 'LSWI', 'Snow']
    for col_name in expected_cols:
        if col_name not in df.columns:
            df[col_name] = None
    df = df[expected_cols]
    
    # 2. Check if we need to download/update 2026 data
    df_2026 = df[df['Year'] == 2026]
    if df_2026.empty:
        max_date_2026 = None
    else:
        max_date_2026 = df_2026['Date'].max()
        
    print(f"Max date in 2026 for Landsat in CSV: {max_date_2026}")
    
    if max_date_2026 is None or max_date_2026 < '2026-06-30':
        if max_date_2026 is not None:
            # get day after
            from datetime import timedelta
            start_dt = (datetime.strptime(max_date_2026, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            start_dt = '2026-01-01'
            
        end_dt = '2026-07-14'
        
        if start_dt < end_dt:
            print(f"Downloading Landsat data for 2026 from {start_dt} to {end_dt}...")
            new_records = []
            
            col = get_harmonized_collection(2026, start_d=start_dt, end_d=end_dt).map(scale_landsat_c2_l2).map(mask_quality_pixels).map(calculate_indices)
            
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
                    data = col.getRegion(geom, scale=30).getInfo()
                    if len(data) <= 1:
                        continue
                    
                    header = data[0]
                    idx = {name: header.index(name) for name in ['time', 'NDVI', 'EVI', 'SAVI', 'LST', 'NDWI', 'LSWI', 'Snow']}
                    
                    for row in data[1:]:
                        new_records.append({
                            'Point_ID': clean_id(point_id),
                            'tratamiento': point_tratamiento,
                            'Year': 2026,
                            'Date': format_date_from_millis(row[idx['time']]),
                            'NDVI': round(float(row[idx['NDVI']]), 3) if row[idx['NDVI']] is not None else None,
                            'EVI': round(float(row[idx['EVI']]), 3) if row[idx['EVI']] is not None else None,
                            'SAVI': round(float(row[idx['SAVI']]), 3) if row[idx['SAVI']] is not None else None,
                            'LST': round(float(row[idx['LST']]), 3) if row[idx['LST']] is not None else None,
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
    print(f"Landsat update complete: {output_csv}")
    
else:
    print(f"CSV not found. Performing full Landsat download from scratch...")
    # Crear carpeta de resultados si no existe
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Point_ID', 'tratamiento', 'Year', 'Date', 'NDVI', 'EVI', 'SAVI', 'LST', 'NDWI', 'LSWI', 'Snow'])

        for y in years:
            print(f'--- Procesando ano {y} ---')
            col = get_harmonized_collection(y).map(scale_landsat_c2_l2).map(mask_quality_pixels).map(calculate_indices)

            for p in point_list:
                geom = ee.Geometry(p['geometry'])
                point_id = p['properties'].get('ID', p['id'])
                point_tratamiento = p['properties'].get('tratamiento')
                try:
                    data = col.getRegion(geom, scale=30).getInfo()

                    if len(data) <= 1:
                        print(f"Punto {p['id']} sin datos validos tras filtros QA.")
                        continue

                    header = data[0]
                    idx = {name: header.index(name) for name in ['time', 'NDVI', 'EVI', 'SAVI', 'LST', 'NDWI', 'LSWI', 'Snow']}

                    # Escribir filas con redondeo a 3 decimales
                    for row in data[1:]:
                        writer.writerow([
                            clean_id(point_id),
                            point_tratamiento,
                            y,
                            format_date_from_millis(row[idx['time']]),
                            round(float(row[idx['NDVI']]), 3) if row[idx['NDVI']] is not None else None,
                            round(float(row[idx['EVI']]), 3) if row[idx['EVI']] is not None else None,
                            round(float(row[idx['SAVI']]), 3) if row[idx['SAVI']] is not None else None,
                            round(float(row[idx['LST']]), 3) if row[idx['LST']] is not None else None,
                            round(float(row[idx['NDWI']]), 3) if row[idx['NDWI']] is not None else None,
                            round(float(row[idx['LSWI']]), 3) if row[idx['LSWI']] is not None else None,
                            row[idx['Snow']],
                        ])
                    print(f"Punto {p['id']} procesado.")
                except Exception as e:
                    print(f"Error procesando punto {p['id']} en ano {y}: {e}")

    print(f'Extracción Landsat finalizada: {output_csv}')

