import streamlit as st
import pandas as pd
import datetime
import time
import ee
from modules.core import init_gee, obter_metadados_salvos

# Inicializa o contador de reset de filtros se não existir
if 'reset_counter' not in st.session_state:
    st.session_state['reset_counter'] = 0

# Callbacks para resetar os filtros antes da reinstanciação dos widgets
def limpar_filtros_callback():
    st.session_state['reset_counter'] += 1

def reiniciar_pagina_callback():
    st.session_state['reset_counter'] += 1
    st.session_state['filtro_aplicado'] = False
    st.session_state['logs_execucao'] = ""

st.set_page_config(page_title="CELMM | Processar Produtos", page_icon="🛰️", layout="wide")

st.title("CELMM - Processar Produtos")
st.caption("Processamento de produtos no GEE. | Produtos em CSV armazenados no Google Drive.")
st.divider()
st.text("")
# Inicialização do Earth Engine
if not init_gee():
    st.stop()

# Inicializa logs de execução no session_state
if 'logs_execucao' not in st.session_state:
    st.session_state['logs_execucao'] = ""

# Inicializa estado do filtro aplicado no session_state
if 'filtro_aplicado' not in st.session_state:
    st.session_state['filtro_aplicado'] = False

# Busca os dados salvos no banco
dados = obter_metadados_salvos()

if not dados:
    st.info("Nenhum metadado foi encontrado no banco de dados.")
    st.markdown("""
    Para popular o banco:
    1. Vá para a página **CELMM - Processar Metadados** no menu lateral.
    2. Realize uma busca no Google Earth Engine.
    3. Clique no botão **Salvar no Banco de Dados** que aparecerá abaixo dos resultados.
    """)
else:
    # Transforma em DataFrame
    df = pd.DataFrame(dados)
    
    # Conversões e ordenação
    df['data'] = pd.to_datetime(df['data']).dt.date
    df = df.sort_values(by='data', ascending=False)

    # 1. Filtros no Expander no topo da página (Cópia exata do layout da página 2)
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

        # Filtro de Intervalo de Pixels Válidos (Slider de Intervalo)
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

    # Botões de controle de filtro alinhados à direita
    col_spacer, col_clear, col_apply = st.columns([6, 3, 3])
    with col_clear:
        st.button("Limpar Filtro", type="secondary", use_container_width=True, on_click=limpar_filtros_callback)
    with col_apply:
        if st.button("Aplicar Filtro", type="primary", use_container_width=True):
            st.session_state['filtro_aplicado'] = True
            st.rerun()

    # Interrompe a renderização caso o filtro não tenha sido aplicado
    if not st.session_state['filtro_aplicado']:
        st.stop()

    # 2. Aplicação final dos filtros
    df_filtrado = df[
        (df['satelite'].isin(satelites_selecionados)) &
        (df['z_grade_mgrs'].isin(grades_selecionadas)) &
        (df['tamanho_pixel'] == int(pixel_selecionado)) &
        (df['data'] >= data_inicio) &
        (df['data'] <= data_fim) &
        (df['pixels_validos'] >= pixels_range[0]) &
        (df['pixels_validos'] <= pixels_range[1])
    ]

    # Calcula a coluna de aproveitamento em relação à melhor imagem do período filtrado
    if not df_filtrado.empty:
        max_pixels_filtrado = int(df_filtrado['pixels_validos'].max())
        if max_pixels_filtrado > 0:
            df_filtrado = df_filtrado.copy()
            df_filtrado['aproveitamento'] = (df_filtrado['pixels_validos'] / max_pixels_filtrado) * 100
        else:
            df_filtrado = df_filtrado.copy()
            df_filtrado['aproveitamento'] = 0.0
    else:
        df_filtrado = df_filtrado.copy()
        df_filtrado['aproveitamento'] = 0.0

    st.text("")

    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
        # Adiciona caixa para controle rápido de marcação
        selecionar_padrao = st.checkbox("Marcar todas", value=False)
        
        # Prepara o DataFrame de exibição formatado
        df_display = df_filtrado.copy()
        df_display.insert(0, "Selecionar", selecionar_padrao)
        df_display['Aproveitamento (%)'] = df_display['aproveitamento'].round(2)
        
        df_to_edit = df_display[[
            'Selecionar', 'data', 'satelite', 'pixels_validos'
        ]].rename(columns={
            'data': 'Data do Produto',
            'satelite': 'Satélite',
            'pixels_validos': 'Pixels Válidos'
        })
        
        # Exibe a lista interativa com caixa de seleção (checkbox) por linha
        edited_df = st.data_editor(
            df_to_edit,
            hide_index=True,
            column_config={
                "Selecionar": st.column_config.CheckboxColumn(
                    "Selecionar",
                    help="Selecione os produtos para download no CSV",
                    default=selecionar_padrao,
                )
            },
            disabled=[c for c in df_to_edit.columns if c != "Selecionar"],
            use_container_width=True
        )

        st.divider()

        # Seleciona os registros marcados
        selected_rows = edited_df[edited_df["Selecionar"] == True]
        
        # Lógicas de processamento auxiliares do Earth Engine
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
            return final_image

        def processar_gee_conteudo(selected_rows_data, df_filtrado_data):
            if st.session_state.get("executar_processamento_gee") and not st.session_state.get("processamento_gee_concluido"):
                st.write(f"Processando {len(selected_rows_data)} produtos no Google Earth Engine...")
                progresso_geral = st.progress(0.0, text="Iniciando...")
                log_placeholder = st.empty()
                
                st.session_state['logs_execucao'] = ""
                
                def append_log(message):
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.session_state['logs_execucao'] += f"[{timestamp}] {message}\n"
                    log_placeholder.code(st.session_state['logs_execucao'])

                append_log(f"Iniciando fila de processamento para {len(selected_rows_data)} produtos...")
                
                try:
                    ROI = ee.FeatureCollection("projects/ppgrhs/assets/CELMM_2025_AJUSTADO")
                except Exception as e:
                    append_log(f"[ERRO] Falha ao carregar a ROI CELMM no GEE: {e}")
                    st.session_state["processamento_gee_concluido"] = True
                    st.session_state["executar_processamento_gee"] = False
                    st.rerun()
                    
                success_count = 0
                fail_count = 0
                total = len(selected_rows_data)
                
                for index, rdata in enumerate(selected_rows_data.to_dict('records')):
                    pct = index / total
                    progresso_geral.progress(pct, text=f"Progresso Geral: {index}/{total} produtos ({int(pct*100)}%)")
                    
                    match = df_filtrado_data[
                        (df_filtrado_data['data'] == rdata['Data do Produto']) &
                        (df_filtrado_data['satelite'] == rdata['Satélite'])
                    ]
                    
                    if match.empty:
                        append_log(f"[ERRO] [{index + 1}/{total}] Não foi possível recuperar os metadados do produto de {rdata['Data do Produto']}.")
                        fail_count += 1
                        continue
                        
                    row_data = match.iloc[0]
                    date_obj = row_data['data']
                    date_str = date_obj.strftime('%Y-%m-%d')
                    sat = row_data['satelite']
                    grade = row_data['z_grade_mgrs']
                    pixel_sz = int(row_data['tamanho_pixel'])
                    
                    append_log(f"[{index + 1}/{total}] Processando data: {date_str} | Satélite: {sat} | Grade: {grade} | Pixel: {pixel_sz}m")
                    
                    try:
                        str_start = date_str
                        str_end = (date_obj + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                        
                        collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                                      .filterBounds(ROI)
                                      .filterDate(str_start, str_end)
                                      .filter(ee.Filter.eq('MGRS_TILE', grade))
                                      .filter(ee.Filter.eq('SPACECRAFT_NAME', sat)))
                        
                        size = collection.size().getInfo()
                        if size == 0:
                            append_log(f"[ERRO] [{index + 1}/{total}] Nenhum produto correspondente encontrado no Earth Engine.")
                            fail_count += 1
                            continue
                            
                        image = collection.first()
                        CRS_base = image.select('B4').projection()
                        
                        img_with_SCL = preprocess_1(image)
                        bands = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12']
                        final_img = preprocess_2(img_with_SCL, bands, CRS_base, pixel_sz, ROI)
                        
                        image_for_extraction = final_img.addBands(ee.Image.pixelLonLat())
                        final_CRS = CRS_base.atScale(pixel_sz) if pixel_sz > 10 else CRS_base
                        
                        extracted_points = image_for_extraction.sample(
                            region=ROI,
                            scale=pixel_sz,
                            projection=final_CRS,
                            geometries=False,
                            tileScale=4
                        )
                        
                        task_desc = f"Exportar_CSV_{date_str}_{pixel_sz}m"
                        file_prefix = f"CELMM_Data_{date_str}_{pixel_sz}m"
                        
                        task = ee.batch.Export.table.toDrive(
                            collection=extracted_points,
                            description=task_desc,
                            folder='CSV_Sentinel2',
                            fileNamePrefix=file_prefix,
                            fileFormat='CSV'
                        )
                        
                        append_log(f"[{index + 1}/{total}] Submetendo tarefa ao GEE...")
                        task.start()
                        task_id = task.status().get('id')
                        append_log(f"[{index + 1}/{total}] Tarefa iniciada no GEE. ID: {task_id}")
                        
                        start_time = time.time()
                        last_state = None
                        
                        while True:
                            status = task.status()
                            state = status.get('state')
                            elapsed = int(time.time() - start_time)
                            
                            if state != last_state:
                                append_log(f"[{index + 1}/{total}] Status: {state} ({elapsed}s decorridos)")
                                last_state = state
                                
                            if state in ['COMPLETED', 'FAILED', 'CANCELLED']:
                                if state == 'COMPLETED':
                                    append_log(f"[{index + 1}/{total}] Sucesso! Exportação concluída em {elapsed}s.")
                                    success_count += 1
                                else:
                                    err_msg = status.get('error_message', 'Sem detalhes de erro.')
                                    append_log(f"[ERRO] [{index + 1}/{total}] Tarefa falhou/cancelou. Erro: {err_msg}")
                                    fail_count += 1
                                break
                                
                            time.sleep(5)
                            
                    except Exception as e:
                        append_log(f"[ERRO] [{index + 1}/{total}] Erro durante processamento: {e}")
                        fail_count += 1
                        
                append_log("--------------------------------------------------")
                append_log(f"Processamento concluído! Sucesso: {success_count} | Falhas: {fail_count}")
                st.session_state["processamento_gee_concluido"] = True
                st.session_state["executar_processamento_gee"] = False
                st.rerun()

            if st.session_state.get("processamento_gee_concluido"):
                st.subheader("Processamento Concluído! 📋")
                st.progress(1.0, text="Todos os produtos processados (100%)")
                st.subheader("Logs de Execução")
                st.code(st.session_state.get('logs_execucao', ""))
                
                col_l1, col_l2 = st.columns(2)
                with col_l1:
                    st.download_button(
                        label="Baixar Logs (.txt)",
                        data=st.session_state.get('logs_execucao', ""),
                        file_name=f"log_processamento_{datetime.date.today()}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                with col_l2:
                    if st.button("Fechar", type="primary", use_container_width=True):
                        st.session_state["processamento_gee_concluido"] = False
                        st.session_state["executar_processamento_gee"] = False
                        st.rerun()

        if hasattr(st, "dialog"):
            processar_gee_modal = st.dialog("Processando no GEE ⚙️")(processar_gee_conteudo)
        else:
            def processar_gee_modal(selected_rows_data, df_filtrado_data):
                with st.expander("Processando no GEE ⚙️", expanded=True):
                    processar_gee_conteudo(selected_rows_data, df_filtrado_data)

        col_spacer, col_reset, col_process = st.columns([6, 3, 3])
        with col_reset:
            st.button("Reiniciar Página", type="secondary", use_container_width=True, on_click=reiniciar_pagina_callback)
        with col_process:
            btn_processar = st.button(
                f"Iniciar Processamento ({len(selected_rows)})", 
                type="primary", 
                use_container_width=True,
                disabled=selected_rows.empty
            )

        if btn_processar and not selected_rows.empty:
            st.session_state["executar_processamento_gee"] = True
            st.session_state["processamento_gee_concluido"] = False
            st.session_state["logs_execucao"] = ""
            st.rerun()

        if st.session_state.get("executar_processamento_gee") or st.session_state.get("processamento_gee_concluido"):
            processar_gee_modal(selected_rows, df_filtrado)
