import streamlit as st
import pandas as pd
import datetime
import ee
from modules.core import obter_metadados_salvos, init_gee, salvar_metadados

st.set_page_config(page_title="CELMM | Explorar Metadados", page_icon="🛰️", layout="wide")
if 'show_buscar_modal' not in st.session_state:
    st.session_state['show_buscar_modal'] = False

if 'reset_counter' not in st.session_state:
    st.session_state['reset_counter'] = 0

def limpar_filtros_callback():
    st.session_state['reset_counter'] += 1

def reset_busca_callback():
    st.session_state['busca_modal_dados'] = None
    st.session_state['busca_modal_pixel_salvo'] = None
    st.session_state['busca_modal_confirmar_salvar'] = False
    st.session_state['busca_modal_datas_conflito'] = []
    if 'busca_modal_periodo' in st.session_state:
        del st.session_state['busca_modal_periodo']
    if 'busca_modal_pixel_size' in st.session_state:
        del st.session_state['busca_modal_pixel_size']

def on_dismiss_callback():
    st.session_state['show_buscar_modal'] = False
    reset_busca_callback()

def _buscar_produtos_modal_impl():
    if not init_gee():
        st.error("Erro ao inicializar o Google Earth Engine.")
        return

    if st.session_state.get('busca_modal_sucesso_mensagem'):
        st.success(st.session_state['busca_modal_sucesso_mensagem'])
        del st.session_state['busca_modal_sucesso_mensagem']

    # Se estiver em estado de confirmação de sobrescrita, exibe APENAS a tela de aviso (muda a página)
    if st.session_state.get('busca_modal_confirmar_salvar', False):
        st.warning(f"Já existem metadados no banco para as datas: {', '.join(st.session_state['busca_modal_datas_conflito'])}. Deseja sobrescrever os registros existentes?")
        st.text("")
        col_conf_spacer, col_reset, col_conf_save = st.columns([6, 3, 3])
        with col_reset:
            st.button("Reiniciar Busca", type="secondary", use_container_width=True, key="busca_modal_btn_reset_conf", on_click=reset_busca_callback)
        with col_conf_save:
            salvo_sucesso = False
            if st.button("Sim, Sobrescrever", type="primary", use_container_width=True, key="busca_modal_btn_save_conf"):
                with st.spinner("Salvando registros no PostgreSQL..."):
                    if salvar_metadados(
                        st.session_state['busca_modal_dados'], 
                        st.session_state['busca_modal_pixel_salvo']
                    ):
                        salvo_sucesso = True
            
            if salvo_sucesso:
                st.session_state['busca_modal_sucesso_mensagem'] = "Dados salvos com sucesso no banco de dados!"
                st.session_state['busca_modal_dados'] = None
                st.session_state['busca_modal_pixel_salvo'] = None
                st.session_state['busca_modal_confirmar_salvar'] = False
                st.session_state['busca_modal_datas_conflito'] = []
                st.rerun()
        return

    col1, col2 = st.columns(2)
    with col1:
        periodo = st.date_input(
            "Período:",
            value=(datetime.date(2023, 12, 1), datetime.date(2023, 12, 31)),
            key="busca_modal_periodo"
        )
        if isinstance(periodo, tuple) and len(periodo) == 2:
            date_start, date_end = periodo
        else:
            st.warning("Por favor, selecione as datas de início e de fim no calendário.")
            st.stop()

    with col2:
        pixel_size_input = st.number_input("Tamanho do Pixel (m):", min_value=10, value=20, step=10, key="busca_modal_pixel_size")
        pixel_size = int(pixel_size_input)

    # Validação do tamanho do pixel
    is_valid_pixel = True
    if pixel_size < 100:
        if pixel_size % 10 != 0:
            is_valid_pixel = False
    else:
        if pixel_size % 100 != 0:
            is_valid_pixel = False

    if not is_valid_pixel:
        st.error("Tamanho do pixel inválido! O valor deve ser múltiplo de 10 (até 90) ou múltiplo de 100 (a partir de 100).")

    # Trava a cobertura máxima de nuvens em 100%
    max_clouds = 100
    bands = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12']

    # Funções de Processamento do Earth Engine (Traduzidas para Python)
    def preprocess_1(image):
        scl = image.select('SCL')
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

    # Inicializa as variáveis de busca no session_state da modal
    if 'busca_modal_dados' not in st.session_state:
        st.session_state['busca_modal_dados'] = None
    if 'busca_modal_pixel_salvo' not in st.session_state:
        st.session_state['busca_modal_pixel_salvo'] = None

    col_spacer, col_run = st.columns([8, 4])
    with col_run:
        btn_processar = st.button(
            "Buscar Produtos", 
            type="primary", 
            use_container_width=True,
            disabled=not is_valid_pixel,
            key="busca_modal_btn_processar"
        )

    if btn_processar:
        st.session_state['busca_modal_dados'] = None
        st.session_state['busca_modal_pixel_salvo'] = None
        
        with st.spinner("Processando no Google Earth Engine...", show_time=True):
            try:
                ROI = ee.FeatureCollection("projects/ppgrhs/assets/CELMM_2025_AJUSTADO")
                
                # Divide o período de busca em sub-períodos de no máximo 1 ano (365 dias)
                # O filtro do GEE filterDate(start, end) é exclusivo da data final, então somamos 1 dia ao date_end
                target_end = date_end + datetime.timedelta(days=1)
                intervals = []
                current_start = date_start
                while current_start < target_end:
                    current_end = current_start + datetime.timedelta(days=365)
                    if current_end > target_end:
                        current_end = target_end
                    intervals.append((current_start, current_end))
                    current_start = current_end
                
                dados_tabela = []
                
                total_lotes = len(intervals)
                logs_processamento = []
                status_placeholder = st.empty()
                
                for idx, (sub_start, sub_end) in enumerate(intervals):
                    str_start = sub_start.strftime('%Y-%m-%d')
                    str_end = sub_end.strftime('%Y-%m-%d')
                    
                    p_start = sub_start.strftime('%d/%m/%Y')
                    p_end = (sub_end - datetime.timedelta(days=1)).strftime('%d/%m/%Y')
                    log_msg = f"[PROCESSANDO] Período {idx + 1}/{total_lotes}: {p_start} a {p_end} - Iniciando busca..."
                    logs_processamento.append(log_msg)
                    status_placeholder.code("\n".join(logs_processamento))
                    print(f"[GEE SEARCH] {log_msg}", flush=True)
                    
                    collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                                  .filterBounds(ROI)
                                  .filterDate(str_start, str_end)
                                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_clouds)))
                    
                    size = collection.size().getInfo()
                    if size == 0:
                        log_msg = f"[SEM REGISTROS] Período {idx + 1}/{total_lotes}: {p_start} a {p_end} - Nenhum produto encontrado."
                        logs_processamento[-1] = log_msg
                        status_placeholder.code("\n".join(logs_processamento))
                        print(f"[GEE SEARCH] {log_msg}", flush=True)
                        continue
                        
                    log_msg = f"[ANALISANDO] Período {idx + 1}/{total_lotes}: {p_start} a {p_end} - Encontrados {size} produtos. Processando metadados..."
                    logs_processamento[-1] = log_msg
                    status_placeholder.code("\n".join(logs_processamento))
                    print(f"[GEE SEARCH] {log_msg}", flush=True)
                    
                    CRS_base = collection.first().select('B4').projection()
                    collection_SCL = collection.map(preprocess_1)

                    def resize_with_scl(img):
                        return preprocess_2(img, bands, CRS_base, pixel_size, ROI)

                    final_collection = collection_SCL.map(resize_with_scl)

                    def extract_properties(image):
                        return ee.Feature(None, {
                            'Data': image.get('date_formatted'),
                            'Pixels_Validos': image.get('available_pixels'),
                            'Satelite': image.get('spacecraft'),
                            'Zenital': image.get('solar_zenith'),
                            'Z_Grade_MGRS': image.get('mgrs_tile')
                        })

                    feature_collection = final_collection.map(extract_properties)
                    results_info = feature_collection.getInfo()
                    features = results_info.get('features', [])

                    sub_dados = []
                    if features:
                        sub_dados = [f['properties'] for f in features]
                        for item in sub_dados:
                            if item.get('Pixels_Validos') is None:
                                item['Pixels_Validos'] = 0
                            else:
                                item['Pixels_Validos'] = int(item['Pixels_Validos'])
                        dados_tabela.extend(sub_dados)
                    
                    log_msg = f"[SUCESSO] Período {idx + 1}/{total_lotes}: {p_start} a {p_end} - {len(sub_dados)} produtos processados."
                    logs_processamento[-1] = log_msg
                    status_placeholder.code("\n".join(logs_processamento))
                    print(f"[GEE SEARCH] {log_msg}", flush=True)
                
                if not dados_tabela:
                    st.warning("Nenhum produto encontrado com os critérios definidos.")
                else:
                    st.session_state['busca_modal_dados'] = dados_tabela
                    st.session_state['busca_modal_pixel_salvo'] = pixel_size
                        
            except Exception as e:
                st.error(f"Erro durante o processamento: {e}")

    # Exibe resultados salvos no session_state
    if st.session_state['busca_modal_dados'] is not None:
        df_resultados = pd.DataFrame(st.session_state['busca_modal_dados'])
        st.success(f"Busca concluída! {len(df_resultados)} produtos analisados.")
        st.dataframe(df_resultados, use_container_width=True)

        salvo_sucesso = False
        
        # Inicializa o estado de confirmação se não existir
        if 'busca_modal_confirmar_salvar' not in st.session_state:
            st.session_state['busca_modal_confirmar_salvar'] = False
            st.session_state['busca_modal_datas_conflito'] = []

        col_spacer2, col_reset, col_save = st.columns([6, 3, 3])
        with col_reset:
            st.button("Reiniciar Busca", type="secondary", use_container_width=True, key="busca_modal_btn_reset", on_click=reset_busca_callback)
        with col_save:
            if st.button("Salvar no Banco", type="primary", use_container_width=True, key="busca_modal_btn_save"):
                from modules.core import verificar_metadados_existentes
                conflitos = verificar_metadados_existentes(
                    st.session_state['busca_modal_dados'], 
                    st.session_state['busca_modal_pixel_salvo']
                )
                if conflitos:
                    st.session_state['busca_modal_confirmar_salvar'] = True
                    st.session_state['busca_modal_datas_conflito'] = conflitos
                    st.rerun()
                else:
                    with st.spinner("Salvando registros no PostgreSQL..."):
                        if salvar_metadados(
                            st.session_state['busca_modal_dados'], 
                            st.session_state['busca_modal_pixel_salvo']
                        ):
                            salvo_sucesso = True

        if salvo_sucesso:
            st.session_state['busca_modal_sucesso_mensagem'] = "Dados salvos com sucesso no banco de dados!"
            # Limpa o state para a próxima busca
            st.session_state['busca_modal_dados'] = None
            st.session_state['busca_modal_pixel_salvo'] = None
            st.rerun()

import inspect
sig = inspect.signature(st.dialog)
if 'on_dismiss' in sig.parameters:
    @st.dialog("Buscar Produtos no GEE", on_dismiss=on_dismiss_callback)
    def buscar_produtos_modal():
        _buscar_produtos_modal_impl()
else:
    @st.dialog("Buscar Produtos no GEE", dismissible=True)
    def buscar_produtos_modal():
        _buscar_produtos_modal_impl()

st.title("CELMM - Explorar Metadados")
st.caption("Visualização de Metadados Processados e Salvos.")
st.divider()
st.text("")

# Busca os dados no banco
dados = obter_metadados_salvos()

if not dados:
    st.info("Nenhum metadado de produto foi encontrado no banco de dados.")
    
    col_spacer, col_btn = st.columns([9, 3])
    with col_btn:
        btn_buscar = st.button("Buscar Novos Produtos", type="primary", use_container_width=True, key="busca_vazia_btn")
    
    if btn_buscar:
        st.session_state['show_buscar_modal'] = True
        st.session_state['busca_modal_confirmar_salvar'] = False
        st.session_state['busca_modal_datas_conflito'] = []
        st.rerun()
        
    st.markdown("""
    Para popular o banco:
    1. Clique no botão **Buscar Novos Produtos** acima.
    2. Selecione o período e tamanho de pixel na janela modal.
    3. Realize a busca no Google Earth Engine e salve no banco de dados.
    """)

else:
    # Transforma em DataFrame
    df = pd.DataFrame(dados)
    
    # Conversões e ordenação
    df['data'] = pd.to_datetime(df['data']).dt.date
    df = df.sort_values(by='data', ascending=False)

    # 1. Filtros no Expander no topo da página
    with st.expander("Filtros", expanded=True):
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            # Filtro de Satélite
            satelites_disponiveis = df['satelite'].unique().tolist()
            satelites_selecionados = st.multiselect(
                "Satélite",
                options=satelites_disponiveis,
                default=satelites_disponiveis,
                key=f"filtro_satelite_{st.session_state['reset_counter']}"
            )

            # Filtro de Grade MGRS
            grades_disponiveis = df['z_grade_mgrs'].dropna().unique().tolist()
            grades_selecionadas = st.multiselect(
                "Grade MGRS",
                options=grades_disponiveis,
                default=grades_disponiveis,
                key=f"filtro_grade_{st.session_state['reset_counter']}"
            )

        with col_f2:
            # Filtro de Tamanho de Pixel (Seleção Única)
            pixels_disponiveis = sorted(df['tamanho_pixel'].unique().tolist())
            opcoes_pixel = [int(p) for p in pixels_disponiveis]
            pixel_selecionado = st.selectbox(
                "Tamanho do Pixel (m)",
                options=opcoes_pixel,
                index=0,
                key=f"filtro_pixel_sz_{st.session_state['reset_counter']}"
            )

            # Filtro de Período
            data_min = df['data'].min()
            data_max = df['data'].max()
            
            if data_min == data_max:
                data_inicio = data_min
                data_fim = data_max
                st.info(f"Período de datas disponível: {data_min}")
            else:
                periodo = st.date_input(
                    "Período",
                    value=(data_min, data_max),
                    min_value=data_min,
                    max_value=data_max,
                    key=f"filtro_periodo_{st.session_state['reset_counter']}"
                )
                if isinstance(periodo, tuple) and len(periodo) == 2:
                    data_inicio, data_fim = periodo
                else:
                    data_inicio, data_fim = data_min, data_max

        # Filtro de Intervalo de Pixels Válidos (Slider de Intervalo) e Botão de Limpar Filtro
        has_valign = 'vertical_alignment' in inspect.signature(st.columns).parameters
        if has_valign:
            col_slider, col_clear = st.columns([9, 3], vertical_alignment="bottom")
        else:
            col_slider, col_clear = st.columns([9, 3])
        with col_slider:
            min_pixels_val = int(df['pixels_validos'].min()) if not df.empty else 0
            max_pixels_val = int(df['pixels_validos'].max()) if not df.empty else 0
            
            if min_pixels_val < max_pixels_val:
                pixels_range = st.slider(
                    "Pixels Válidos",
                    min_value=min_pixels_val,
                    max_value=max_pixels_val,
                    value=(min_pixels_val, max_pixels_val),
                    key=f"filtro_pixels_range_{st.session_state['reset_counter']}"
                )
            else:
                pixels_range = (min_pixels_val, max_pixels_val)
        with col_clear:
            if not has_valign:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            st.button("Limpar Filtro", type="secondary", use_container_width=True, on_click=limpar_filtros_callback)

    # Filtro de tamanho de pixel
    filtro_pixel = df['tamanho_pixel'] == int(pixel_selecionado)

    # Aplicação dos filtros
    df_filtrado = df[
        (df['satelite'].isin(satelites_selecionados)) &
        (df['z_grade_mgrs'].isin(grades_selecionadas)) &
        filtro_pixel &
        (df['data'] >= data_inicio) &
        (df['data'] <= data_fim) &
        (df['pixels_validos'] >= pixels_range[0]) &
        (df['pixels_validos'] <= pixels_range[1])
    ]



    # 2. Seção de Indicadores Gerais
    if not df_filtrado.empty:
        total_imagens = len(df_filtrado)
        
        # Encontra o maior valor de pixels válidos
        max_pixels = int(df_filtrado['pixels_validos'].max())
        
        # Filtra todas as linhas que têm esse valor máximo e extrai as datas únicas ordenadas
        df_max = df_filtrado[df_filtrado['pixels_validos'] == max_pixels]
        datas_max = sorted(df_max['data'].unique())
        
        # Junta todas as datas formatadas separadas por vírgula
        data_max_pixels = ", ".join([d.strftime('%d/%m/%Y') for d in datas_max])
    else:
        total_imagens = 0
        max_pixels = 0
        data_max_pixels = "N/A"

    st.text("")
    col1, col2, col3 = st.columns(3)
    
    def card_destacado(label, value, title_tooltip=None):
        tooltip_attr = f'title="{title_tooltip}"' if title_tooltip else ""
        return f"""
            <div style="
                background-color: rgba(2, 132, 199, 0.08); 
                border: 1px solid rgba(2, 132, 199, 0.25); 
                border-radius: 8px; 
                padding: 12px 15px; 
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                text-align: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                margin-bottom: 15px;
                width: 100%;
            " {tooltip_attr}>
                <p style="margin: 0; font-size: 0.85em; font-weight: 500; color: var(--text-color); opacity: 0.8; text-align: center; width: 100%;">{label}</p>
                <div style="margin: 4px 0 0 0; font-size: 1.6em; color: var(--primary-color); font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; width: 100%;">{value}</div>
            </div>
        """

    with col1:
        st.markdown(card_destacado("Total de Produtos", str(total_imagens)), unsafe_allow_html=True)
    with col2:
        st.markdown(card_destacado("Máximo Pixels", f"{max_pixels:,}"), unsafe_allow_html=True)
    with col3:
        st.markdown(card_destacado("Melhor Produto", data_max_pixels, title_tooltip=data_max_pixels), unsafe_allow_html=True)
    st.text("")
    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
       
        # Renomeia as colunas para exibição amigável
        df_exibicao = df_filtrado[[
            'id', 'data', 'satelite', 'z_grade_mgrs', 'tamanho_pixel', 'pixels_validos', 'data_registro'
        ]].rename(columns={
            'id': 'ID',
            'data': 'Data do Produto',
            'satelite': 'Satélite',
            'z_grade_mgrs': 'Grade MGRS',
            'tamanho_pixel': 'Tamanho Pixel (m)',
            'pixels_validos': 'Pixels Válidos',
            'data_registro': 'Data de Gravação'
        })
        
        # Exibe a tabela interativa
        st.dataframe(df_exibicao, use_container_width=True)

    st.text("")
    col_spacer, col_btn = st.columns([9, 3])
    with col_btn:
        btn_buscar = st.button("Buscar Novos Produtos", type="primary", use_container_width=True, key="busca_filtro_btn")

    if btn_buscar:
        st.session_state['show_buscar_modal'] = True
        st.session_state['busca_modal_confirmar_salvar'] = False
        st.session_state['busca_modal_datas_conflito'] = []
        st.rerun()

if st.session_state.get('show_buscar_modal', False):
    buscar_produtos_modal()