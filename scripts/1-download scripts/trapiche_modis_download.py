# Script para descargar datos de MODIS (MOD09GQ/MYD09GQ) para puntos de Trapiche
# Importar librerias necesarias
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
pixels = ee.FeatureCollection('users/CarlosNavarro/Trapiche_NDVI/Trapiche_Modis')

# Filtrar por categorias de tratamiento de interes (sector restaurado, sector no restaurado, control 1, control 2)
pointsOn = pixels.filter(ee.Filter.inList('status', ['restaurado', 'no_rest', 'control1', 'control2']))

# Rango de años a procesar para MODIS Terra + Aqua
years = list(range(2026, 2027))  

# definicion de output CSV
output_csv = base_dir.parent.parent / 'data' / 'datos_trapiche_modis.csv'
# Proyección de MODIS para extracción puntual
MODIS_CRS = 'SR-ORG:6974'

# Función para convertir milisegundos a fecha legible
def format_date_from_millis(millis):
    if millis is None:
        return None
    return datetime.fromtimestamp(float(millis) / 1000, tz=timezone.utc).strftime('%Y-%m-%d')

# Función para preparar imágenes MODIS: aplicar máscara de calidad y escalar reflectancias
def prep_modis(img):
    # MOD09GQ/MYD09GQ entregan bandas 1 (rojo) y 2 (NIR) con factor 0.0001.
    # Se usa un filtro QA conservador: MODLAND QA == 0.
    qc_250m = img.select('QC_250m')
    qa_mask = qc_250m.bitwiseAnd(3).eq(0)

    scaled = img.select(['sur_refl_b01', 'sur_refl_b02'], ['Red', 'NIR']).multiply(0.0001)
    acq_time = ee.Image.constant(ee.Number(img.get('system:time_start'))).rename('AcqTime').toInt64()
    return scaled.updateMask(qa_mask).addBands(acq_time)

# Función para obtener colección armonizada de MODIS Terra + Aqua con bandas renombradas
def get_modis_collection(year, roi):
    start_date = f'{year}-01-01'
    end_date = f'{year + 1}-01-01'

    terra = (
        ee.ImageCollection('MODIS/061/MOD09GQ')
        .filterBounds(roi)
        .filterDate(start_date, end_date)
        .map(prep_modis)
    )

    aqua = (
        ee.ImageCollection('MODIS/061/MYD09GQ')
        .filterBounds(roi)
        .filterDate(start_date, end_date)
        .map(prep_modis)
    )

    return terra.merge(aqua)

# Función para calcular índices y agregar como bandas al imagen
def calculate_indices(img):
    ndvi = img.normalizedDifference(['NIR', 'Red']).rename('NDVI')
    savi = img.expression(
        '((NIR - Red) / (NIR + Red + 0.5)) * 1.5',
        {'NIR': img.select('NIR'), 'Red': img.select('Red')},
    ).rename('SAVI')
    return img.addBands([ndvi, savi])


# Ejecucion robusta por puntos
point_count = pointsOn.size().getInfo()
if point_count == 0:
    print('No se encontraron puntos con los tratamientos filtrados; usando toda la coleccion Trapiche_Modis.')
    source_points = pixels
else:
    source_points = pointsOn

point_list = source_points.toList(source_points.size()).getInfo()
roi = source_points.geometry()

with open(output_csv, mode='w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Point_ID', 'tratamiento', 'Year', 'Date', 'Red', 'NIR', 'NDVI', 'SAVI'])

    for y in years:
        print(f'--- Procesando ano {y} ---')
        col = get_modis_collection(y, roi).map(calculate_indices)

        for p in point_list:
            geom = ee.Geometry(p['geometry']).transform(MODIS_CRS, 1)
            point_id = p['properties'].get('ID', p['id'])
            point_tratamiento = p['properties'].get('tratamiento')
            data = col.getRegion(geom, scale=250, crs=MODIS_CRS).getInfo()

            if len(data) <= 1:
                print(f"Punto {p['id']} sin datos validos tras filtro QA.")
                continue

            header = data[0]
            idx = {name: header.index(name) for name in ['AcqTime', 'Red', 'NIR', 'NDVI', 'SAVI']}

            # Escribir filas con redondeo a 3 decimales
            for row in data[1:]:
                writer.writerow([
                    point_id,
                    point_tratamiento,
                    y,
                    format_date_from_millis(row[idx['AcqTime']]),
                    round(float(row[idx['Red']]), 3) if row[idx['Red']] is not None else None,
                    round(float(row[idx['NIR']]), 3) if row[idx['NIR']] is not None else None,
                    round(float(row[idx['NDVI']]), 3) if row[idx['NDVI']] is not None else None,
                    round(float(row[idx['SAVI']]), 3) if row[idx['SAVI']] is not None else None,
                ])
            print(f"Punto {p['id']} procesado.")

print(f'Extracción MODIS finalizada: {output_csv}')