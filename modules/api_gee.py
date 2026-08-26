import os
import ee
import streamlit as st

@st.cache_resource
def init_gee():
    """Inicializa a conexão com o Google Earth Engine apenas uma vez por sessão."""
    try:
        from modules.google_auth import carregar_credenciais_google
        project = os.getenv("EARTHENGINE_PROJECT") or os.getenv("GOOGLE_PROJECT_ID", "ppgrhs-satellitum")
        creds = carregar_credenciais_google()
        ee.Initialize(credentials=creds, project=project)
        return True
    except Exception as e:
        try:
            st.error(f"Erro ao inicializar o Earth Engine: {e}. Verifique as credenciais.")
        except Exception:
            pass
        return False

def preprocess_1(image):
    """Aplica a máscara de qualidade do sensor SCL (Sentinel-2 L2A)."""
    scl = image.select('SCL')
    mask = (scl.neq(1)
            .And(scl.neq(3))
            .And(scl.neq(8))
            .And(scl.neq(9))
            .And(scl.neq(10)))
    return image.updateMask(mask)

def preprocess_2(image, bands, CRS_original, pixel_size, ROI):
    """Executa a seleção de bandas, reamostragem espacial e contagem de pixels disponíveis."""
    select_image = image.select(bands)
    if pixel_size > 10:
        CRS_target = CRS_original.atScale(pixel_size)
        final_image = (select_image.setDefaultProjection(CRS_original)
                       .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=40000)
                       .reproject(crs=CRS_target)
                       .clip(ROI))
    else:
        final_image = select_image.clip(ROI)
    
    pixel_count = final_image.select('B4').reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=ROI.geometry(),
        crs=final_image.select('B4').projection(),
        maxPixels=800000
    )  
    return final_image.set({
        'date_formatted': image.date().format('YYYY-MM-dd'),
        'system:time_start': image.get('system:time_start'),
        'available_pixels': pixel_count.get('B4'),
        'cloud_cover': image.get('CLOUDY_PIXEL_PERCENTAGE'),
        'water_percent': image.get('WATER_PERCENTAGE'),
        'spacecraft': image.get('SPACECRAFT_NAME'),
        'solar_zenith': image.get('MEAN_SOLAR_ZENITH_ANGLE'),
        'mgrs_tile': image.get('MGRS_TILE')
    })

def buscar_metadados_gee(date_start, date_end, pixel_size: int) -> list:
    """Realiza a consulta da coleção Sentinel-2 L2A no Earth Engine e retorna a lista formatada de metadados extraídos."""
    if not init_gee():
        try:
            st.error("Erro ao inicializar o Earth Engine.")
        except Exception:
            pass
        return []

    # Geometria da ROI pré-definida no projeto
    table = ee.FeatureCollection("projects/ppgrhs/assets/celmm")
    ROI = table.geometry()
    
    bands = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12']
    
    S2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterBounds(ROI)
          .filterDate(str(date_start), str(date_end))
          .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 100))
          .map(preprocess_1))
    
    first_image = S2.first()
    if not first_image.getInfo():
        return []

    CRS_original = first_image.select('B4').projection()

    def process_func(img):
        return preprocess_2(img, bands, CRS_original, pixel_size, table)

    processed_collection = S2.map(process_func)
    
    def extract_info(image):
        return ee.Feature(None, {
            'Data': image.get('date_formatted'),
            'Pixels_Validos': image.get('available_pixels'),
            'Nuvens_Pct': image.get('cloud_cover'),
            'Agua_Pct': image.get('water_percent'),
            'Satelite': image.get('spacecraft'),
            'Zenital': image.get('solar_zenith'),
            'Z_Grade_MGRS': image.get('mgrs_tile')
        })

    info_collection = processed_collection.map(extract_info)
    results = info_collection.getInfo()
    
    lista_dados = []
    for feat in results.get('features', []):
        props = feat.get('properties', {})
        if props.get('Data') is not None:
            lista_dados.append(props)
            
    return lista_dados
