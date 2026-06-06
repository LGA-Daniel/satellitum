import streamlit as st
import streamlit as st
import ee
import datetime
import pandas as pd

st.set_page_config(page_title="CELMM | Metadados", page_icon="🛰️", layout="wide")

st.title("CELMM - Análise de Metadados")

st.divider()

# 1. Inicialização do Earth Engine (Certifique-se de que o ambiente/Docker já está autenticado)
try:
    ee.Initialize()
except Exception as e:
    st.error("Erro ao inicializar o Earth Engine. Verifique as credenciais.")
    st.stop()

# 2. Configuração da Interface no Streamlit

st.markdown("Selecione o período desejado para verificar a disponibilidade de imagens.")

# Layout em colunas para os inputs de data
col1, col2 = st.columns(2)
with col1:
    date_start = st.date_input("Data de Início", datetime.date(2023, 12, 1))
    date_end = st.date_input("Data de Fim", datetime.date(2023, 12, 31))

with col2:
    pixel_size = st.number_input("Tamanho do Pixel (m)", value=20, step=10)
    max_clouds = st.slider("Cobertura Máxima de Nuvens (%)", 0, 100, 100)

bands = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12']
drive_location = 'CSV_Sentinel2'

# 3. Funções de Processamento do Earth Engine (Traduzidas para Python)
def preprocess_1(image):
    scl = image.select('SCL')
    # Na API Python, operadores lógicos em imagens usam métodos com letra maiúscula, ex: .And()
    mask = (scl.neq(1)
            .And(scl.neq(3))
            .And(scl.neq(8))
            .And(scl.neq(9))
            .And(scl.neq(10)))
    return image.updateMask(mask)

def preprocess_2(image, bands, CRS_original, pixel_size, ROI):
    select_image = image.select(bands)
    
    if pixel_size > 10:
        CRS_target = CRS_original.atScale(pixel_size)
        final_image = (select_image.setDefaultProjection(CRS_original)
                       .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=40000)
                       .reproject(crs=CRS_target)
                       .clip(ROI))
    else:
        final_image = select_image.clip(ROI)
    
    mask_B4 = final_image.select('B4').mask()
    
    # Redutor para contagem quantitativa de pixels válidos
    pixel_count = mask_B4.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=ROI.geometry(),
        scale=pixel_size,
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

# 4. Execução e Exibição no Streamlit
if st.button("Processar Metadados"):
    with st.spinner("Processando no Google Earth Engine...", show_time=True):
        try:
            ROI = ee.FeatureCollection("projects/ppgrhs/assets/CELMM_2025_AJUSTADO")
            
            # Formatação de datas para o GEE
            str_start = date_start.strftime('%Y-%m-%d')
            str_end = date_end.strftime('%Y-%m-%d')

            collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                          .filterBounds(ROI)
                          .filterDate(str_start, str_end)
                          .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_clouds)))
            
            # Pega a projeção base da primeira imagem
            CRS_base = collection.first().select('B4').projection()

            # Aplica a máscara SCL
            collection_SCL = collection.map(preprocess_1)

            # Função auxiliar para mapear o preprocess_2 com parâmetros extras
            def resize_with_scl(img):
                return preprocess_2(img, bands, CRS_base, pixel_size, ROI)

            # Mapeia a coleção final
            final_collection = collection_SCL.map(resize_with_scl)

            # Extração das propriedades calculadas (data e quantidade de pixels)
            def extract_properties(image):
                return ee.Feature(None, {
                    'Data': image.get('date_formatted'),
                    'Pixels_Validos': image.get('available_pixels'),
                    'Satelite': image.get('spacecraft'),
                    'Zenital': image.get('solar_zenith'),
                    'Z_Grade_MGRS': image.get('mgrs_tile')
                })

            feature_collection = final_collection.map(extract_properties)
            
            # Executa a requisição para trazer os dados ao Python local (.getInfo())
            results_info = feature_collection.getInfo()
            features = results_info.get('features', [])

            if not features:
                st.warning("Nenhuma imagem encontrada com os critérios definidos.")
            else:
                # Transforma a resposta JSON em um DataFrame Pandas para melhor visualização
                dados_tabela = [f['properties'] for f in features]
                df_resultados = pd.DataFrame(dados_tabela)
                
                # Tratamento de valores nulos caso o redutor não encontre pixels
                df_resultados['Pixels_Validos'] = df_resultados['Pixels_Validos'].fillna(0).astype(int)
                
                st.success(f"Processamento concluído! {len(df_resultados)} imagens analisadas.")
                
                # Exibe a tabela no front-end
                st.dataframe(df_resultados, use_container_width=True)
    

        except Exception as e:
            st.error(f"Erro durante o processamento: {e}")