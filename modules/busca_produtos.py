import streamlit as st
import pandas as pd
import datetime
import time
import html
import ee
import inspect
from modules.api_gee import init_gee
from modules.db import salvar_metadados, verificar_metadados_existentes

def reset_busca_callback():
    st.session_state['busca_modal_dados'] = None
    st.session_state['busca_modal_pixel_salvo'] = None
    st.session_state['busca_modal_confirmar_salvar'] = False
    st.session_state['busca_modal_datas_conflito'] = []
    if 'busca_modal_periodo' in st.session_state:
        del st.session_state['busca_modal_periodo']
    if 'busca_modal_pixel_size' in st.session_state:
        del st.session_state['busca_modal_pixel_size']

def on_dismiss_busca_callback():
    st.session_state['show_buscar_modal'] = False
    reset_busca_callback()

def _buscar_produtos_dialog_impl():
    if not init_gee():
        st.error("Erro ao inicializar o Google Earth Engine.")
        return

    if st.session_state.get('busca_modal_sucesso_mensagem'):
        st.success(st.session_state['busca_modal_sucesso_mensagem'])
        del st.session_state['busca_modal_sucesso_mensagem']
        time.sleep(3)
        st.session_state['show_buscar_modal'] = False
        st.rerun()

    if st.session_state.get('busca_modal_confirmar_salvar', False):
        conflitos = st.session_state.get('busca_modal_datas_conflito', [])
        total_encontrados = len(st.session_state.get('busca_modal_dados', []))
        total_novos = total_encontrados - len(conflitos)
        
        with st.container(border=True):
            if conflitos:
                if len(conflitos) > 8:
                    datas_str = ", ".join(conflitos[:8]) + f" ... (+{len(conflitos) - 8} datas)"
                else:
                    datas_str = ", ".join(conflitos)

                st.markdown(f"""
                    <div style="margin-bottom: 12px;">
                        <h4 style="margin: 0 0 6px 0; font-size: 1.1em; font-weight: 600; color: #f59e0b;">⚠️ Conflito de Metadados Existentes</h4>
                        <p style="margin: 0 0 8px 0; font-size: 0.88em; line-height: 1.4;">
                            Foram identificados <strong>{len(conflitos)}</strong> registro(s) que já existem no Banco de Dados para as datas: <code>{datas_str}</code>.
                        </p>
                        <p style="margin: 0; font-size: 0.85em; opacity: 0.8;">
                            Total consultado: <strong>{total_encontrados}</strong> produto(s) | Novos a inserir: <strong>{total_novos}</strong> produto(s).
                        </p>
                    </div>
                """, unsafe_allow_html=True)
                
                st.divider()
                
                col_desc, col_merge, col_over = st.columns(3)
                
                with col_desc:
                    if st.button("🗑️ Descartar Dados", type="secondary", use_container_width=True, key="busca_modal_btn_desc"):
                        st.session_state['show_buscar_modal'] = False
                        reset_busca_callback()
                        st.rerun()

                with col_merge:
                    if st.button("🔀 Mesclar Somente Novos", type="secondary", use_container_width=True, disabled=total_novos <= 0, key="busca_modal_btn_merge"):
                        dados_novos = [
                            item for item in st.session_state['busca_modal_dados']
                            if str(item.get('Data')) not in conflitos
                        ]
                        if dados_novos and salvar_metadados(dados_novos, st.session_state['busca_modal_pixel_salvo']):
                            st.session_state['busca_modal_sucesso_mensagem'] = f"{len(dados_novos)} produto(s) mesclado(s) com sucesso!"
                        else:
                            st.session_state['busca_modal_sucesso_mensagem'] = "Nenhum produto novo para mesclar."
                        
                        st.session_state['busca_modal_dados'] = None
                        st.session_state['busca_modal_pixel_salvo'] = None
                        st.session_state['busca_modal_confirmar_salvar'] = False
                        st.session_state['busca_modal_datas_conflito'] = []
                        st.rerun()

                with col_over:
                    if st.button("🔄 Sobrescrever Todos", type="primary", use_container_width=True, key="busca_modal_btn_over"):
                        if salvar_metadados(st.session_state['busca_modal_dados'], st.session_state['busca_modal_pixel_salvo']):
                            st.session_state['busca_modal_sucesso_mensagem'] = f"{total_encontrados} produto(s) sobrescrito(s) com sucesso!"
                            st.session_state['busca_modal_dados'] = None
                            st.session_state['busca_modal_pixel_salvo'] = None
                            st.session_state['busca_modal_confirmar_salvar'] = False
                            st.session_state['busca_modal_datas_conflito'] = []
                            st.rerun()
            else:
                st.markdown(f"""
                    <div style="margin-bottom: 12px;">
                        <h4 style="margin: 0 0 6px 0; font-size: 1.1em; font-weight: 600; color: #10b981;">📋 Confirmação de Salvamento</h4>
                        <p style="margin: 0 0 8px 0; font-size: 0.88em; line-height: 1.4;">
                            Todos os <strong>{total_encontrados}</strong> produto(s) consultados são novos e estão prontos para serem salvos no Banco de Dados.
                        </p>
                        <p style="margin: 0; font-size: 0.85em; opacity: 0.8;">
                            Nenhum conflito de datas existente foi detectado.
                        </p>
                    </div>
                """, unsafe_allow_html=True)
                
                st.divider()
                
                col_desc, col_conf_save = st.columns(2)
                
                with col_desc:
                    if st.button("🗑️ Descartar Dados", type="secondary", use_container_width=True, key="busca_modal_btn_desc_new"):
                        st.session_state['show_buscar_modal'] = False
                        reset_busca_callback()
                        st.rerun()

                with col_conf_save:
                    if st.button("💾 Confirmar e Salvar", type="primary", use_container_width=True, key="busca_modal_btn_save_new"):
                        if salvar_metadados(st.session_state['busca_modal_dados'], st.session_state['busca_modal_pixel_salvo']):
                            st.session_state['busca_modal_sucesso_mensagem'] = f"{total_encontrados} produto(s) salvos com sucesso!"
                            st.session_state['busca_modal_dados'] = None
                            st.session_state['busca_modal_pixel_salvo'] = None
                            st.session_state['busca_modal_confirmar_salvar'] = False
                            st.session_state['busca_modal_datas_conflito'] = []
                            st.rerun()
        return

    hoje = datetime.date.today()
    data_padrao_inicio = hoje - datetime.timedelta(days=180)
    data_padrao_fim = hoje

    with st.container(border=True):
        st.markdown("""
            <div style="margin-bottom: 12px;">
                <h4 style="margin: 0 0 4px 0; font-size: 1.1em; font-weight: 600;">🔍 Parâmetros de Busca</h4>
                <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Defina o intervalo temporal e a resolução espacial desejada para consultar novos produtos disponíveis no Google Earth Engine.</p>
            </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            periodo = st.date_input(
                "Período:",
                value=(data_padrao_inicio, data_padrao_fim),
                max_value=hoje,
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

    is_valid_pixel = True
    if pixel_size < 100:
        if pixel_size % 10 != 0:
            is_valid_pixel = False
    else:
        if pixel_size % 100 != 0:
            is_valid_pixel = False

    if not is_valid_pixel:
        st.error("Tamanho do pixel inválido! O valor deve ser múltiplo de 10 (até 90) ou múltiplo de 100 (a partir de 100).")

    col_spacer, col_run = st.columns([8, 4])
    with col_run:
        btn_processar = st.button(
            "🔍 Buscar Produtos", 
            type="primary", 
            use_container_width=True,
            disabled=not is_valid_pixel,
            key="busca_modal_btn_processar"
        )

    max_clouds = 100
    bands = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12']

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

    if 'busca_modal_dados' not in st.session_state:
        st.session_state['busca_modal_dados'] = None
    if 'busca_modal_pixel_salvo' not in st.session_state:
        st.session_state['busca_modal_pixel_salvo'] = None

    if btn_processar:
        st.session_state['busca_modal_dados'] = None
        st.session_state['busca_modal_pixel_salvo'] = None
        
        try:
            ROI = ee.FeatureCollection("projects/ppgrhs/assets/CELMM_2025_AJUSTADO")
            
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
            
            st.markdown("#### Log de Execução:")
            ph_terminal_busca = st.empty()
            
            def render_log_terminal(log_items):
                log_text = "\n".join(log_items) if log_items else "Aguardando início da consulta..."
                escaped_logs = html.escape(log_text)
                ph_terminal_busca.markdown(f"""
                    <div style="
                        background-color: #0d1117; 
                        border: 1px solid rgba(255, 255, 255, 0.12); 
                        border-radius: 8px; 
                        padding: 12px 16px; 
                        height: 240px; 
                        overflow-y: auto; 
                        font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; 
                        font-size: 0.82rem; 
                        line-height: 1.5; 
                        color: #58a6ff; 
                        white-space: pre-wrap; 
                        word-break: break-word; 
                        margin-bottom: 12px;
                    ">{escaped_logs}</div>
                """, unsafe_allow_html=True)
            
            def add_log(msg):
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logs_processamento.append(f"[{ts}] {msg}")
                render_log_terminal(logs_processamento)
            
            add_log(f"[INÍCIO] Conectado ao Earth Engine (GEE). Área de Interesse Carregada.")
            add_log(f"[PARÂMETROS] Período: {date_start.strftime('%d/%m/%Y')} a {date_end.strftime('%d/%m/%Y')} | Resolução: {pixel_size}m")
            
            for idx, (sub_start, sub_end) in enumerate(intervals):
                str_start = sub_start.strftime('%Y-%m-%d')
                str_end = sub_end.strftime('%Y-%m-%d')
                
                p_start = sub_start.strftime('%d/%m/%Y')
                p_end = (sub_end - datetime.timedelta(days=1)).strftime('%d/%m/%Y')
                
                add_log(f"[CONSULTA] Lote {idx + 1}/{total_lotes} ({p_start} a {p_end}) - Filtrando catálogo Sentinel-2 L2A...")
                
                collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                              .filterBounds(ROI)
                              .filterDate(str_start, str_end)
                              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_clouds)))
                
                size = collection.size().getInfo()
                if size == 0:
                    add_log(f"[SEM PRODUTOS] Lote {idx + 1}/{total_lotes} - Nenhuma cena orbital encontrada no intervalo.")
                    continue
                    
                add_log(f"[COLEÇÃO] Lote {idx + 1}/{total_lotes} - {size} cena(s) identificada(s) no Earth Engine.")
                add_log(f"[PROCESSANDO] Aplicando máscara de Qualidade (SCL) e reprojeção espacial...")
                
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

                add_log(f"[ANÁLISE] Calculando contagem de pixels válidos...")

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
                
                add_log(f"[SUCESSO] Lote {idx + 1}/{total_lotes} - {len(sub_dados)} produto(s) estruturado(s).")
            
            logs_processamento.append("--------------------------------------------------")
            add_log(f"[FINALIZADO] Busca concluída com sucesso! Total de {len(dados_tabela)} produto(s) pronto(s).")

            st.markdown("")
            if not dados_tabela:
                st.warning("Nenhum produto encontrado com os critérios definidos.")
            else:
                st.session_state['busca_modal_dados'] = dados_tabela
                st.session_state['busca_modal_pixel_salvo'] = pixel_size
        except Exception as e:
            st.error(f"Erro durante o processamento: {e}")

    if st.session_state['busca_modal_dados'] is not None:
        salvo_sucesso = False
        if 'busca_modal_confirmar_salvar' not in st.session_state:
            st.session_state['busca_modal_confirmar_salvar'] = False
            st.session_state['busca_modal_datas_conflito'] = []

        with st.container(border=True):
            col_reset, col_save = st.columns(2)
            with col_reset:
                st.button("🔄 Reiniciar Busca", type="secondary", use_container_width=True, key="busca_modal_btn_reset", on_click=reset_busca_callback)
            with col_save:
                if st.button("💾 Salvar no Banco", type="primary", use_container_width=True, key="busca_modal_btn_save"):
                    conflitos = verificar_metadados_existentes(
                        st.session_state['busca_modal_dados'], 
                        st.session_state['busca_modal_pixel_salvo']
                    )
                    st.session_state['busca_modal_confirmar_salvar'] = True
                    st.session_state['busca_modal_datas_conflito'] = conflitos if conflitos else []
                    st.rerun()

def buscar_produtos_dialog():
    sig_dialog = inspect.signature(st.dialog)
    dialog_kwargs = {"width": "large"} if "width" in sig_dialog.parameters else {}

    if 'on_dismiss' in sig_dialog.parameters:
        @st.dialog("Buscar Novos Produtos", on_dismiss=on_dismiss_busca_callback, **dialog_kwargs)
        def _inner():
            _buscar_produtos_dialog_impl()
        _inner()
    else:
        @st.dialog("Buscar Novos Produtos", dismissible=True, **dialog_kwargs)
        def _inner():
            _buscar_produtos_dialog_impl()
        _inner()
