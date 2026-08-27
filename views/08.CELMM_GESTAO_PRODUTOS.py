import streamlit as st
import pandas as pd
import datetime
import os
import shutil
import time
import inspect
import html
import ee

from modules.db import (
    obter_metadados_salvos,
    salvar_metadados,
    verificar_metadados_existentes,
    obter_ids_imagens_com_pixels,
    obter_df_pixels_por_imagem_ids,
    criar_tarefa_background,
    obter_tarefa_ativa,
    obter_status_tarefa,
    cancelar_tarefa
)
from modules.api_gee import init_gee
from modules.api_gdrive import (
    listar_arquivos_pasta_drive,
    baixar_arquivo_drive_para_disco
)
from modules.data_export import preparar_arquivo_exportacao, limpar_arquivos_exportacao_disco
from modules.task_monitor import render_conteudo_monitoramento_tarefa, card_destacado

# Configuração da página
st.set_page_config(page_title="CELMM | Gerenciamento de Produtos Orbitais", page_icon="🛰️", layout="wide")

# Diretório temporário para downloads de arquivos CSV
module_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(module_dir)
temp_dir = os.path.join(project_root, "temp_downloads")

# Controle de estado e reset de filtros
if 'reset_counter' not in st.session_state:
    st.session_state['reset_counter'] = 0

if 'show_buscar_modal' not in st.session_state:
    st.session_state['show_buscar_modal'] = False

if 'show_acoes_modal' not in st.session_state:
    st.session_state['show_acoes_modal'] = False

if 'show_download_modal' not in st.session_state:
    st.session_state['show_download_modal'] = False

if 'show_export_modal' not in st.session_state:
    st.session_state['show_export_modal'] = False

if 'export_ids_selecionados' not in st.session_state:
    st.session_state['export_ids_selecionados'] = []

def limpar_filtros_callback():
    st.session_state['reset_counter'] += 1
    listar_arquivos_pasta_drive.clear()
    resetar_estado_processamento()

def resetar_estado_processamento():
    st.session_state["confirmar_sobrescrever_pixels"] = False
    st.session_state["pixels_dados_conflito"] = []

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

def on_dismiss_tarefa_callback():
    if "tarefa_id_monitorada" in st.session_state:
        tid = st.session_state["tarefa_id_monitorada"]
        st.session_state[f"tarefa_dismissed_{tid}"] = True
        del st.session_state["tarefa_id_monitorada"]

def on_dismiss_acoes_callback():
    st.session_state['show_acoes_modal'] = False
    if 'export_in_place_formato' in st.session_state:
        del st.session_state['export_in_place_formato']
    limpar_arquivos_exportacao_disco()

def on_dismiss_download_callback():
    st.session_state['show_download_modal'] = False
    limpar_pasta_temporaria()
    limpar_arquivos_exportacao_disco()

def limpar_pasta_temporaria():
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
    os.makedirs(temp_dir, exist_ok=True)

# ==============================================================================
# 1. MODAL: BUSCAR NOVOS PRODUTOS NO GEE
# ==============================================================================
def _buscar_produtos_modal_impl():
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

sig_dialog = inspect.signature(st.dialog)
dialog_kwargs = {"width": "large"} if "width" in sig_dialog.parameters else {}

if 'on_dismiss' in sig_dialog.parameters:
    @st.dialog("Buscar Novos Produtos", on_dismiss=on_dismiss_busca_callback, **dialog_kwargs)
    def buscar_produtos_modal():
        _buscar_produtos_modal_impl()
else:
    @st.dialog("Buscar Novos Produtos", dismissible=True, **dialog_kwargs)
    def buscar_produtos_modal():
        _buscar_produtos_modal_impl()

# ==============================================================================
# 2. MODAL: MONITORAMENTO DE TAREFAS EM BACKGROUND (GEE, CSV & FULL PIPELINE)
# ==============================================================================
def monitorar_tarefa_modal(tid, titulo="Processamento"):
    if 'on_dismiss' in sig_dialog.parameters:
        @st.dialog(titulo, on_dismiss=on_dismiss_tarefa_callback, **dialog_kwargs)
        def _inner(t_id):
            render_conteudo_monitoramento_tarefa(t_id, live_polling=True, show_download_log=False)
        _inner(tid)
    else:
        @st.dialog(titulo, dismissible=True, **dialog_kwargs)
        def _inner(t_id):
            render_conteudo_monitoramento_tarefa(t_id, live_polling=True, show_download_log=False)
        _inner(tid)

# ==============================================================================
# 3. MODAL: BAIXAR ARQUIVOS DO GOOGLE DRIVE
# ==============================================================================
def _baixar_arquivos_modal_impl(valid_selected, map_nome_id, map_nome_id_lower):
    st.write(f"Você selecionou **{len(valid_selected)}** arquivo(s) disponível(is) para download.")
    
    with st.spinner("Baixando arquivos do Drive diretamente para o servidor..."):
        try:
            limpar_pasta_temporaria()
            files_downloaded = []
            
            for idx, row in valid_selected.iterrows():
                date_str = row["Data do Produto"].strftime('%Y-%m-%d') if isinstance(row["Data do Produto"], (datetime.date, datetime.datetime)) else str(row["Data do Produto"])
                nome_esperado = f"CELMM_Data_{date_str}_{int(row['Tamanho Pixel (m)'])}m.csv"
                fid = map_nome_id.get(nome_esperado) or map_nome_id_lower.get(nome_esperado.lower())
                if fid:
                    dest_path = os.path.join(temp_dir, nome_esperado)
                    baixar_arquivo_drive_para_disco(fid, dest_path)
                    files_downloaded.append(dest_path)
            
            if not files_downloaded:
                st.warning("Nenhum arquivo correspondente encontrado no Google Drive.")
            elif len(files_downloaded) == 1:
                local_file_path = files_downloaded[0]
                filename = os.path.basename(local_file_path)
                
                with open(local_file_path, "rb") as f:
                    st.download_button(
                        label="Salvar Arquivo CSV no Computador",
                        data=f,
                        file_name=filename,
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )
            else:
                import zipfile
                zip_filename = f"CELMM_CSVs_{datetime.date.today().strftime('%Y%m%d')}.zip"
                zip_path = os.path.join(temp_dir, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for filepath in files_downloaded:
                        zip_file.write(filepath, os.path.basename(filepath))
                        
                with open(zip_path, "rb") as f:
                    st.download_button(
                        label="Salvar Pacote ZIP no Computador",
                        data=f,
                        file_name=zip_filename,
                        mime="application/zip",
                        type="primary",
                        use_container_width=True
                    )
        except Exception as e:
            st.error(f"Erro ao processar arquivos do Drive: {e}")

if 'on_dismiss' in sig_dialog.parameters:
    @st.dialog("Baixar Arquivos do Google Drive", on_dismiss=on_dismiss_download_callback, **dialog_kwargs)
    def baixar_arquivos_modal(valid_selected, map_nome_id, map_nome_id_lower):
        _baixar_arquivos_modal_impl(valid_selected, map_nome_id, map_nome_id_lower)
else:
    @st.dialog("Baixar Arquivos do Google Drive", dismissible=True, **dialog_kwargs)
    def baixar_arquivos_modal(valid_selected, map_nome_id, map_nome_id_lower):
        _baixar_arquivos_modal_impl(valid_selected, map_nome_id, map_nome_id_lower)

# ==============================================================================
# 4. MODAL: GRADE CENTRAL DE AÇÕES
# ==============================================================================
def _acoes_produtos_modal_impl(selected_rows, valid_drive_selected, valid_db_selected, df_filtrado, map_nome_id, map_nome_id_lower):
    total_sel = len(selected_rows)
    total_drive = len(valid_drive_selected)
    total_db = len(valid_db_selected)
    
    st.markdown(f"""
        <div style="background-color: rgba(2, 132, 199, 0.08); border: 1px solid rgba(2, 132, 199, 0.25); border-radius: 8px; padding: 10px 16px; margin-bottom: 18px; display: flex; justify-content: space-around; text-align: center;">
            <div><strong>Selecionados:</strong> <span style="color: var(--primary-color);">{total_sel}</span></div>
            <div><strong>Processados:</strong> <span style="color: #22c55e;">{total_drive}</span></div>
            <div><strong>Sincronizados:</strong> <span style="color: #3b82f6;">{total_db}</span></div>
        </div>
    """, unsafe_allow_html=True)
    
    col_g1, col_g2 = st.columns(2)
    
    # ------------------ COLUNA 1 ------------------
    with col_g1:
        # AÇÃO 1: Processo Completo
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">⚙️ Processamento Automático</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Executa toda a série de processamento: GEE + Banco de Dados.</p>
                </div>
            """, unsafe_allow_html=True)
            if st.button("Executar Processamento Automático", type="primary", use_container_width=True, disabled=total_sel == 0, key="modal_btn_full"):
                st.session_state['show_acoes_modal'] = False
                selected_rows_list = []
                for _, r in selected_rows.iterrows():
                    d_str = r['Data do Produto'].strftime('%Y-%m-%d') if isinstance(r['Data do Produto'], (datetime.date, datetime.datetime)) else str(r['Data do Produto'])
                    selected_rows_list.append({
                        "id": int(r['id']),
                        "Data do Produto": d_str,
                        "Tamanho Pixel (m)": int(r['Tamanho Pixel (m)']),
                        "Satélite": str(r['Satélite']),
                        "Grade MGRS": str(r['Grade MGRS']) if pd.notna(r['Grade MGRS']) else None,
                        "Pixels Válidos": int(r['Pixels Válidos']),
                        "zenital": float(r['zenital']) if pd.notna(r['zenital']) else None
                    })
                
                df_filtrado_list = []
                for _, r in df_filtrado.iterrows():
                    d_str = r['data'].strftime('%Y-%m-%d') if isinstance(r['data'], (datetime.date, datetime.datetime)) else str(r['data'])
                    df_filtrado_list.append({
                        "id": int(r['id']),
                        "data": d_str,
                        "satelite": str(r['satelite']),
                        "z_grade_mgrs": str(r['z_grade_mgrs']) if pd.notna(r['z_grade_mgrs']) else None,
                        "tamanho_pixel": int(r['tamanho_pixel']),
                        "zenital": float(r['zenital']) if pd.notna(r['zenital']) else None
                    })

                payload = {
                    "selected_rows": selected_rows_list,
                    "df_filtrado_data": df_filtrado_list,
                    "map_nome_id": map_nome_id
                }
                
                tarefa_id = criar_tarefa_background("FULL_PIPELINE", payload, len(selected_rows_list))
                if tarefa_id:
                    st.session_state[f"tarefa_dismissed_{tarefa_id}"] = False
                    st.session_state["tarefa_id_monitorada"] = tarefa_id
                    st.rerun()

        # AÇÃO 2: Sincronizar com o Banco
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">🔄 Sincronizar Produtos</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Realiza a leitura de produtos previamente processados e sincroniza com a a base de dados.</p>
                </div>
            """, unsafe_allow_html=True)
            if st.button("Sincronizar com o Banco de Dados", type="secondary", use_container_width=True, disabled=total_drive == 0, key="modal_btn_sinc"):
                st.session_state['show_acoes_modal'] = False
                selected_rows_list = []
                for _, r in valid_drive_selected.iterrows():
                    d_str = r['Data do Produto'].strftime('%Y-%m-%d') if isinstance(r['Data do Produto'], (datetime.date, datetime.datetime)) else str(r['Data do Produto'])
                    selected_rows_list.append({
                        "id": int(r['id']),
                        "Data do Produto": d_str,
                        "Tamanho Pixel (m)": int(r['Tamanho Pixel (m)']),
                        "Satélite": str(r['Satélite']),
                        "Grade MGRS": str(r['Grade MGRS']) if pd.notna(r['Grade MGRS']) else None,
                        "zenital": float(r['zenital']) if pd.notna(r['zenital']) else None
                    })
                
                payload = {
                    "selected_rows": selected_rows_list,
                    "map_nome_id": map_nome_id
                }
                
                tarefa_id = criar_tarefa_background("CSV_INGEST", payload, len(selected_rows_list))
                if tarefa_id:
                    st.session_state[f"tarefa_dismissed_{tarefa_id}"] = False
                    st.session_state["tarefa_id_monitorada"] = tarefa_id
                    st.rerun()

    # ------------------ COLUNA 2 ------------------
    with col_g2:
        # AÇÃO 3: Processar no GEE
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">🌍 Processar no GEE</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Submete o Processamento da cena no Google Earth Engine e disponibiliza o produto para sincronização futura.</p>
                </div>
            """, unsafe_allow_html=True)
            if st.button("Processar no GEE", type="secondary", use_container_width=True, disabled=total_sel == 0, key="modal_btn_gee"):
                st.session_state['show_acoes_modal'] = False
                selected_rows_list = []
                for _, r in selected_rows.iterrows():
                    d_str = r['Data do Produto'].strftime('%Y-%m-%d') if isinstance(r['Data do Produto'], (datetime.date, datetime.datetime)) else str(r['Data do Produto'])
                    selected_rows_list.append({
                        "Data do Produto": d_str,
                        "Satélite": str(r['Satélite']),
                        "Pixels Válidos": int(r['Pixels Válidos'])
                    })
                
                df_filtrado_list = []
                for _, r in df_filtrado.iterrows():
                    d_str = r['data'].strftime('%Y-%m-%d') if isinstance(r['data'], (datetime.date, datetime.datetime)) else str(r['data'])
                    df_filtrado_list.append({
                        "data": d_str,
                        "satelite": str(r['satelite']),
                        "z_grade_mgrs": str(r['z_grade_mgrs']) if pd.notna(r['z_grade_mgrs']) else None,
                        "tamanho_pixel": int(r['tamanho_pixel'])
                    })

                payload = {
                    "selected_rows": selected_rows_list,
                    "df_filtrado_data": df_filtrado_list
                }
                
                tarefa_id = criar_tarefa_background("GEE_EXPORT", payload, len(selected_rows_list))
                if tarefa_id:
                    st.session_state[f"tarefa_dismissed_{tarefa_id}"] = False
                    st.session_state["tarefa_id_monitorada"] = tarefa_id
                    st.rerun()

        # AÇÃO 4: Baixar CSVs
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">📥 Baixar Produtos</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Baixa os produtos processados em formato CSV diretamente para o seu computador.</p>
                </div>
            """, unsafe_allow_html=True)
            if st.button("Baixar Arquivos CSV", type="secondary", use_container_width=True, disabled=total_drive == 0, key="modal_btn_download"):
                st.session_state['show_acoes_modal'] = False
                st.session_state['show_download_modal'] = True
                st.rerun()

    # ------------------ LINHA INFERIOR ------------------
    col_inf1, col_inf2 = st.columns(2)
    
    with col_inf1:
        # AÇÃO 5: Visualizar Dados
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">🗺️ Visualizar Dados</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Visualizar prévia dos dados/pixels brutos e imagens reconstituídas.</p>
                </div>
            """, unsafe_allow_html=True)
            pode_ver = (total_db == 1 and total_sel == 1)
            
            if pode_ver:
                help_vis = "Abre a prévia de dados e composição RGB para o produto selecionado."
            elif total_sel == 0:
                help_vis = "Selecione exatamente 1 produto na tabela para visualizar seus dados."
            elif total_sel > 1:
                help_vis = f"A visualização de dados suporta apenas 1 produto por vez. Você selecionou {total_sel} produtos."
            else:
                help_vis = "O produto selecionado ainda não foi sincronizado com o banco de dados. Sincronize-o antes de visualizar."

            if st.button(
                "Abrir Visualização de Dados", 
                type="secondary", 
                use_container_width=True, 
                disabled=not pode_ver, 
                help=help_vis,
                key="modal_btn_vis"
            ):
                st.session_state['show_acoes_modal'] = False
                id_img = int(valid_db_selected.iloc[0]['id'])
                with st.spinner("Carregando amostra de dados para visualização..."):
                    df_pixels = obter_df_pixels_por_imagem_ids([id_img], limit=500)
                    st.session_state["df_pixels_carregados"] = df_pixels
                    st.session_state["ids_pixels_carregados"] = [id_img]
                    st.session_state["carregado_parcial"] = True
                    st.switch_page("views/06.CELMM_PREVIA_DADOS.py")

    with col_inf2:
        # AÇÃO 6: Exportar Dados (CSV / Excel)
        formato_in_place = st.session_state.get('export_in_place_formato')
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">📊 Exportar Dados</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Exportar o conjunto de dados dos produtos selecionados em um arquivo único. </p>
                </div>
            """, unsafe_allow_html=True)
            pode_exportar = total_db >= 1
            
            if pode_exportar:
                help_csv = f"Gera arquivo CSV para os {total_db} produto(s) sincronizado(s)."
                help_xlsx = f"Gera planilha Excel (.xlsx) para os {total_db} produto(s) sincronizado(s)."
            elif total_sel == 0:
                help_csv = help_xlsx = "Selecione ao menos 1 produto na tabela para exportar."
            else:
                help_csv = help_xlsx = "Nenhum dos produtos selecionados possui dados salvos no banco. Sincronize antes de exportar."

            if formato_in_place and pode_exportar:
                ids_exp = [int(x) for x in valid_db_selected['id'].tolist()]
                with st.spinner(f"Processando e gravando {formato_in_place.upper()}..."):
                    try:
                        cache = preparar_arquivo_exportacao(ids_exp, formato_in_place)
                        col_dl, col_reset = st.columns([5, 5])
                        with col_dl:
                            with open(cache["file_path"], "rb") as f_exp:
                                st.download_button(
                                    label=f"⬇️ Baixar {formato_in_place.upper()} ({cache['file_size_mb']} MB)",
                                    data=f_exp,
                                    file_name=cache["file_name"],
                                    mime=cache["mime_type"],
                                    type="primary",
                                    use_container_width=True,
                                    key="btn_download_direct_inplace"
                                )
                        with col_reset:
                            if st.button("🔄 Alternar formato", help="Alternar formato", use_container_width=True, key="btn_reset_export_fmt"):
                                del st.session_state['export_in_place_formato']
                                limpar_arquivos_exportacao_disco()
                                st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
            else:
                col_btn_csv, col_btn_xlsx = st.columns(2)
                with col_btn_csv:
                    if st.button(
                        "📄 Gerar CSV", 
                        type="secondary", 
                        use_container_width=True, 
                        disabled=not pode_exportar, 
                        help=help_csv, 
                        key="modal_btn_export_csv"
                    ):
                        st.session_state['export_in_place_formato'] = 'csv'
                        st.rerun()

                with col_btn_xlsx:
                    if st.button(
                        "📊 Gerar Excel", 
                        type="secondary", 
                        use_container_width=True, 
                        disabled=not pode_exportar, 
                        help=help_xlsx, 
                        key="modal_btn_export_xlsx"
                    ):
                        st.session_state['export_in_place_formato'] = 'xlsx'
                        st.rerun()

if 'on_dismiss' in sig_dialog.parameters:
    @st.dialog("Central de Processamento", on_dismiss=on_dismiss_acoes_callback, **dialog_kwargs)
    def acoes_produtos_modal(selected_rows, valid_drive_selected, valid_db_selected, df_filtrado, map_nome_id, map_nome_id_lower):
        _acoes_produtos_modal_impl(selected_rows, valid_drive_selected, valid_db_selected, df_filtrado, map_nome_id, map_nome_id_lower)
else:
    @st.dialog("Central de Processamento", dismissible=True, **dialog_kwargs)
    def acoes_produtos_modal(selected_rows, valid_drive_selected, valid_db_selected, df_filtrado, map_nome_id, map_nome_id_lower):
        _acoes_produtos_modal_impl(selected_rows, valid_drive_selected, valid_db_selected, df_filtrado, map_nome_id, map_nome_id_lower)

# ==============================================================================
# 5. CABEÇALHO & CARREGAMENTO PRINCIPAL DOS DADOS
# ==============================================================================
col_title, col_top_btn = st.columns([8, 4], vertical_alignment="center")
with col_title:
    st.title("Gerenciamento de Produtos Orbitais")
    st.markdown("### Sentinel 2 - CELMM")
with col_top_btn:
    if st.button("🔍 Buscar Novos Produtos", type="primary", use_container_width=True, key="btn_top_buscar_produtos"):
        st.session_state['show_buscar_modal'] = True
        st.session_state['busca_modal_confirmar_salvar'] = False
        st.session_state['busca_modal_datas_conflito'] = []
        st.rerun()

st.divider()

if not init_gee():
    st.stop()

with st.spinner("Carregando metadados, arquivos do Google Drive e status do banco..."):
    dados = obter_metadados_salvos()
    arquivos_drive = listar_arquivos_pasta_drive("CSV_Sentinel2")
    ids_com_pixels = obter_ids_imagens_com_pixels()

map_nome_id = {arq.get('name', '').strip(): arq.get('id') for arq in arquivos_drive if arq.get('name') and arq.get('id')}
map_nome_id_lower = {arq.get('name', '').strip().lower(): arq.get('id') for arq in arquivos_drive if arq.get('name') and arq.get('id')}
nomes_arquivos_drive = set(map_nome_id.keys())
nomes_arquivos_drive_lower = set(map_nome_id_lower.keys())

if not dados:
    st.info("Nenhum metadado de produto foi encontrado no banco de dados.")
    if st.session_state.get('show_buscar_modal', False):
        buscar_produtos_modal()
    st.stop()

df = pd.DataFrame(dados)
df['data'] = pd.to_datetime(df['data']).dt.date
df = df.sort_values(by='data', ascending=False)

def verificar_disponibilidade_drive(row):
    nome_esperado = f"CELMM_Data_{row['data'].strftime('%Y-%m-%d')}_{int(row['tamanho_pixel'])}m.csv"
    if (
        nome_esperado in nomes_arquivos_drive 
        or nome_esperado.lower() in nomes_arquivos_drive_lower
        or (row['id'] in ids_com_pixels and row.get('pixels_validos') == 0)
    ):
        return "Disponível ✅"
    return "Não Encontrado ❌"

df['Status do Processamento'] = df.apply(verificar_disponibilidade_drive, axis=1)
df['Importado para o Banco'] = df.apply(
    lambda r: "Salvo ✅" if r['id'] in ids_com_pixels else "Pendente ⏳",
    axis=1
)

# ==============================================================================
# 6. FILTROS
# ==============================================================================
with st.expander("**Filtros de Produtos**", expanded=False):
    col_f1, col_f2 = st.columns(2)
    
    with col_f1:
        satelites_disponiveis = df['satelite'].unique().tolist()
        satelites_selecionados = st.multiselect(
            "Satélite",
            options=satelites_disponiveis,
            default=satelites_disponiveis,
            on_change=resetar_estado_processamento,
            key=f"filtro_satelite_{st.session_state['reset_counter']}"
        )

        grades_disponiveis = df['z_grade_mgrs'].dropna().unique().tolist()
        grades_selecionadas = st.multiselect(
            "Grade MGRS",
            options=grades_disponiveis,
            default=grades_disponiveis,
            on_change=resetar_estado_processamento,
            key=f"filtro_grade_{st.session_state['reset_counter']}"
        )

    with col_f2:
        pixels_disponiveis = sorted(df['tamanho_pixel'].unique().tolist())
        opcoes_pixel = [int(p) for p in pixels_disponiveis]
        pixel_selecionado = st.selectbox(
            "Tamanho do Pixel (m)",
            options=opcoes_pixel,
            index=0,
            on_change=resetar_estado_processamento,
            key=f"filtro_pixel_sz_{st.session_state['reset_counter']}"
        )

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
                on_change=resetar_estado_processamento,
                key=f"filtro_periodo_{st.session_state['reset_counter']}"
            )
            if isinstance(periodo, tuple) and len(periodo) == 2:
                data_inicio, data_fim = periodo
            else:
                data_inicio, data_fim = data_min, data_max

    # Slider de Pixels Válidos em linha dedicada
    min_pixels_val = int(df['pixels_validos'].min()) if not df.empty else 0
    max_pixels_val = int(df['pixels_validos'].max()) if not df.empty else 0
    
    if min_pixels_val < max_pixels_val:
        pixels_range = st.slider(
            "Pixels Válidos",
            min_value=min_pixels_val,
            max_value=max_pixels_val,
            value=(min_pixels_val, max_pixels_val),
            on_change=resetar_estado_processamento,
            key=f"filtro_pixels_range_{st.session_state['reset_counter']}"
        )
    else:
        pixels_range = (min_pixels_val, max_pixels_val)
        
    st.text("")

    # Linha inferior dedicada para Toggles e Botão Limpar Filtros
    has_valign = 'vertical_alignment' in inspect.signature(st.columns).parameters
    if has_valign:
        col_sp1, col_t1, col_t2, col_t3, col_sp_filtros, col_clear = st.columns([7, 3, 3, 3, 0.01, 3], vertical_alignment="center")
    else:
        _, col_t1, col_t2, col_t3, col_sp_filtros, col_clear = st.columns([7, 3, 3, 3, 0.01, 3])
        
    with col_t1:
        status_drive_toggle = st.toggle(
            "Somente Processados", 
            value=False, 
            on_change=resetar_estado_processamento, 
            key=f"filtro_status_drive_{st.session_state['reset_counter']}"
        )
    with col_t2:
        status_salvo_toggle = st.toggle(
            "Somente no Banco", 
            value=False, 
            on_change=resetar_estado_processamento, 
            key=f"filtro_status_salvo_{st.session_state['reset_counter']}"
        )
    with col_t3:
        status_banco_toggle = st.toggle(
            "Somente Pendentes", 
            value=False, 
            on_change=resetar_estado_processamento, 
            key=f"filtro_status_banco_{st.session_state['reset_counter']}"
        )
    with col_clear:
        st.button("Limpar Filtros", type="secondary", use_container_width=True, on_click=limpar_filtros_callback)

# Aplicação dos Filtros
df_filtrado = df[
    (df['satelite'].isin(satelites_selecionados)) &
    (df['z_grade_mgrs'].isin(grades_selecionadas)) &
    (df['tamanho_pixel'] == int(pixel_selecionado)) &
    (df['data'] >= data_inicio) &
    (df['data'] <= data_fim) &
    (df['pixels_validos'] >= pixels_range[0]) &
    (df['pixels_validos'] <= pixels_range[1])
]

if not df_filtrado.empty:
    if status_drive_toggle:
        df_filtrado = df_filtrado[df_filtrado['Status do Processamento'] == "Disponível ✅"]
    if status_salvo_toggle:
        df_filtrado = df_filtrado[df_filtrado['Importado para o Banco'] == "Salvo ✅"]
    if status_banco_toggle:
        df_filtrado = df_filtrado[df_filtrado['Importado para o Banco'] == "Pendente ⏳"]

# ==============================================================================
# 7. CARDS DE MÉTRICAS / INDICADORES
# ==============================================================================

if not df_filtrado.empty:
    total_produtos = len(df_filtrado)
    max_pixels = int(df_filtrado['pixels_validos'].max())
    df_max = df_filtrado[df_filtrado['pixels_validos'] == max_pixels]
    datas_max = sorted(df_max['data'].unique())
    data_max_pixels = ", ".join([d.strftime('%d/%m/%Y') for d in datas_max])
    total_csv_disp = len(df_filtrado[df_filtrado['Status do Processamento'] == "Disponível ✅"])
    total_db_salvo = len(df_filtrado[df_filtrado['Importado para o Banco'] == "Salvo ✅"])
else:
    total_produtos = 0
    max_pixels = 0
    data_max_pixels = "N/A"
    total_csv_disp = 0
    total_db_salvo = 0

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(card_destacado("Total de Produtos", str(total_produtos)), unsafe_allow_html=True)
with col2:
    st.markdown(card_destacado("Máximo Pixels", f"{max_pixels:,}".replace(",", ".")), unsafe_allow_html=True)
with col3:
    st.markdown(card_destacado("Produtos Processados", f"{total_csv_disp} / {total_produtos}"), unsafe_allow_html=True)
with col4:
    st.markdown(card_destacado("Produtos Sincronizados", f"{total_db_salvo} / {total_produtos}"), unsafe_allow_html=True)

st.text("")

# ==============================================================================
# 8. TABELA INTERATIVA DE PRODUTOS
# ==============================================================================
if df_filtrado.empty:
    st.warning("Nenhum produto encontrado para os filtros selecionados.")
    col_spacer, col_btn = st.columns([9, 3])
    with col_btn:
        if st.button("Buscar Novos Produtos", type="primary", use_container_width=True, key="btn_buscar_empty"):
            st.session_state['show_buscar_modal'] = True
            st.rerun()
else:
    col_chk, col_sp = st.columns([3, 9])
    with col_chk:
        selecionar_padrao = st.checkbox("Marcar todos", value=False, on_change=resetar_estado_processamento)
    
    df_display = df_filtrado.copy()
    df_display.insert(0, "Selecionar", selecionar_padrao)
    
    df_to_edit = df_display[[
        'Selecionar', 'id', 'data', 'satelite', 'z_grade_mgrs', 'tamanho_pixel', 'pixels_validos', 'zenital', 'Status do Processamento', 'Importado para o Banco'
    ]].rename(columns={
        'data': 'Data do Produto',
        'satelite': 'Satélite',
        'z_grade_mgrs': 'Grade MGRS',
        'tamanho_pixel': 'Tamanho Pixel (m)',
        'pixels_validos': 'Pixels Válidos'
    })
    
    filtro_str = f"{sorted(satelites_selecionados)}_{sorted(grades_selecionadas)}_{pixel_selecionado}_{data_inicio}_{data_fim}_{pixels_range}_{status_drive_toggle}_{status_salvo_toggle}_{status_banco_toggle}"
    editor_key = f"editor_unificado_{hash(filtro_str)}"
    
    edited_df = st.data_editor(
        df_to_edit,
        key=editor_key,
        on_change=resetar_estado_processamento,
        hide_index=True,
        column_config={
            "Selecionar": st.column_config.CheckboxColumn(
                "Selecionar",
                help="Selecione produtos para executar ações em lote",
                default=selecionar_padrao,
            ),
            "id": None,
            "zenital": None,
            "Data do Produto": st.column_config.DateColumn("Data do Produto", format="YYYY-MM-DD", width="medium"),
            "Satélite": st.column_config.TextColumn("Satélite", width="small"),
            "Grade MGRS": st.column_config.TextColumn("Grade MGRS", width="small"),
            "Tamanho Pixel (m)": st.column_config.NumberColumn("Tamanho Pixel (m)", width="small"),
            "Pixels Válidos": st.column_config.NumberColumn("Pixels Válidos", width="medium"),
            "Status do Processamento": st.column_config.TextColumn("Status do Processamento", width="medium"),
            "Importado para o Banco": st.column_config.TextColumn("Banco de Dados", width="medium")
        },
        disabled=[c for c in df_to_edit.columns if c != "Selecionar"],
        use_container_width=True
    )
    
    st.divider()

    # ==============================================================================
    # 9. BARRA DE CONTROLE: BOTÃO ÚNICO DE AÇÕES
    # ==============================================================================
    selected_rows = edited_df[edited_df["Selecionar"] == True]
    valid_drive_selected = selected_rows[selected_rows["Status do Processamento"] == "Disponível ✅"]
    valid_db_selected = selected_rows[selected_rows["Importado para o Banco"] == "Salvo ✅"]
    
    # Verifica tarefas ativas ao carregar a tela
    if "tarefa_id_monitorada" not in st.session_state:
        tarefa_ativa = obter_tarefa_ativa()
        if tarefa_ativa:
            if not st.session_state.get(f"tarefa_dismissed_{tarefa_ativa['id']}", False):
                st.session_state["tarefa_id_monitorada"] = tarefa_ativa["id"]

    is_task_running = st.session_state.get("tarefa_id_monitorada") is not None
    total_sel = len(selected_rows)

    col_spacer, col_btn_acoes = st.columns([8, 4])
    
    with col_btn_acoes:
        label_btn = f"Ações - Selecionados: {total_sel}" if total_sel > 0 else " Selecione os Produtos"
        if st.button(
            label_btn,
            type="primary",
            use_container_width=True,
            disabled=is_task_running or total_sel == 0,
            help="Abre o painel em grade com todas as ações disponíveis para os produtos.",
            key="btn_abrir_acoes_modal"
        ):
            st.session_state['show_acoes_modal'] = True
            st.rerun()

# ==============================================================================
# 10. MODAIS CONDICIONAIS
# ==============================================================================
if st.session_state.get('show_buscar_modal', False):
    buscar_produtos_modal()

if st.session_state.get('show_acoes_modal', False):
    acoes_produtos_modal(
        selected_rows, 
        valid_drive_selected, 
        valid_db_selected, 
        df_filtrado, 
        map_nome_id, 
        map_nome_id_lower
    )

if st.session_state.get('show_download_modal', False):
    baixar_arquivos_modal(valid_drive_selected, map_nome_id, map_nome_id_lower)

if st.session_state.get("tarefa_id_monitorada") and not st.session_state.get(f"tarefa_dismissed_{st.session_state.get('tarefa_id_monitorada')}", False):
    tid = st.session_state["tarefa_id_monitorada"]
    t = obter_status_tarefa(tid)
    tipo_cod = t.get("tipo_tarefa") if t else ""
    if tipo_cod == "FULL_PIPELINE":
        tipo_desc = "Processamento Automático"
    elif tipo_cod == "GEE_EXPORT":
        tipo_desc = "Processamento no GEE"
    else:
        tipo_desc = "Sincronização de Produtos"
    monitorar_tarefa_modal(tid, tipo_desc)
