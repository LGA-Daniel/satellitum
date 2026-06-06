import streamlit as st
import ee
import datetime
import pandas as pd
from modules.core import init_gee, salvar_metadados

st.set_page_config(page_title="CELMM | Metadados", page_icon="🛰️", layout="wide")

st.title("CELMM - Análise de Metadados")

st.divider()

# 1. Inicialização do Earth Engine
if not init_gee():
    st.stop()

# 2. Configuração da Interface no Streamlit

st.markdown("Selecione o período desejado para verificar a disponibilidade de imagens.")

# Layout em colunas para os inputs de data e pixel
col1, col2 = st.columns(2)
with col1:
    periodo = st.date_input(
        "Período de Análise",
        value=(datetime.date(2023, 12, 1), datetime.date(2023, 12, 31))
    )
    if isinstance(periodo, tuple) and len(periodo) == 2:
        date_start, date_end = periodo
    else:
        st.warning("Por favor, selecione as datas de início e de fim no calendário.")
        st.stop()

with col2:
    pixel_size = st.number_input("Tamanho do Pixel (m)", value=20, step=10)

# Trava a cobertura máxima de nuvens em 100%
max_clouds = 100

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

# Inicializa as variáveis no session_state se não existirem
if 'dados_tabela' not in st.session_state:
    st.session_state['dados_tabela'] = None
if 'tamanho_pixel_salvo' not in st.session_state:
    st.session_state['tamanho_pixel_salvo'] = None

col_run, col_reset, _ = st.columns([2, 4, 4])
with col_run:
    btn_processar = st.button("Processar Metadados", type="primary", use_container_width=True)
with col_reset:
    btn_resetar = st.button("Reiniciar Processamento", type="secondary", use_container_width=True)

if btn_resetar:
    st.session_state['dados_tabela'] = None
    st.session_state['tamanho_pixel_salvo'] = None
    st.rerun()

if btn_processar:
    st.session_state['dados_tabela'] = None
    st.session_state['tamanho_pixel_salvo'] = None
    
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
                
                # Tratamento de valores nulos caso o redutor não encontre pixels
                for item in dados_tabela:
                    if item.get('Pixels_Validos') is None:
                        item['Pixels_Validos'] = 0
                    else:
                        item['Pixels_Validos'] = int(item['Pixels_Validos'])
                
                # Salva no session_state
                st.session_state['dados_tabela'] = dados_tabela
                st.session_state['tamanho_pixel_salvo'] = pixel_size
                
        except Exception as e:
            st.error(f"Erro durante o processamento: {e}")

# Renderiza os resultados se estiverem salvos no session_state
if st.session_state['dados_tabela'] is not None:
    df_resultados = pd.DataFrame(st.session_state['dados_tabela'])
    st.success(f"Processamento concluído! {len(df_resultados)} imagens analisadas.")
    st.dataframe(df_resultados, use_container_width=True)

    st.subheader("Ações do Banco de Dados")
    col_save, _ = st.columns([1, 3])
    with col_save:
        if st.button("Salvar no Banco de Dados", type="primary"):
            with st.spinner("Salvando registros no PostgreSQL..."):
                sucesso = salvar_metadados(
                    st.session_state['dados_tabela'], 
                    st.session_state['tamanho_pixel_salvo']
                )
                if sucesso:
                    st.success("Dados salvos/atualizados com sucesso no banco de dados!")