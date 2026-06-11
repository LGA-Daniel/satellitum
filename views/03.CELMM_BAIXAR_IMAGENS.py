import streamlit as st
import pandas as pd
import datetime
import time
import ee
import inspect
from modules.core import (
    init_gee, 
    obter_metadados_salvos, 
    criar_tarefa_background, 
    obter_tarefa_ativa, 
    obter_status_tarefa, 
    cancelar_tarefa,
    listar_arquivos_pasta_drive
)

# Inicializa o contador de reset de filtros se não existir
if 'reset_counter' not in st.session_state:
    st.session_state['reset_counter'] = 0

# Callbacks para resetar os filtros antes da reinstanciação dos widgets
def limpar_filtros_callback():
    st.session_state['reset_counter'] += 1

def reiniciar_pagina_callback():
    st.session_state['reset_counter'] += 1
    st.session_state['logs_execucao'] = ""

def on_dismiss_gee_callback():
    if "tarefa_id_monitorada" in st.session_state:
        tid = st.session_state["tarefa_id_monitorada"]
        st.session_state[f"tarefa_dismissed_{tid}"] = True
        del st.session_state["tarefa_id_monitorada"]


def processar_gee_conteudo(tarefa_id):
    t = obter_status_tarefa(tarefa_id)
    if not t:
        st.error("Tarefa não encontrada.")
        if st.button("Fechar", type="primary", use_container_width=True, key=f"btn_close_not_found_{tarefa_id}"):
            if "tarefa_id_monitorada" in st.session_state:
                st.session_state[f"tarefa_dismissed_{st.session_state['tarefa_id_monitorada']}"] = True
                del st.session_state["tarefa_id_monitorada"]
            st.rerun()
        return

    status = t["status"]
    processados = t["itens_processados"]
    total = t["total_itens"]
    logs = t["logs"] or ""

    # Exibe título e progresso
    if status == "pendente":
        st.info("Tarefa aguardando na fila de execução...")
        st.progress(0.0)
    elif status == "processando":
        pct = processados / total if total > 0 else 0.0
        st.progress(pct, text=f"Processando: {processados}/{total} produtos ({int(pct*100)}%)")
    elif status == "concluido":
        st.success("Processamento concluído com sucesso!")
        st.progress(1.0)
    elif status == "cancelado":
        st.warning("Processamento cancelado pelo usuário.")
        st.progress(processados / total if total > 0 else 0.0)
    else:
        st.error("O processamento falhou.")
        st.progress(processados / total if total > 0 else 0.0)

    st.subheader("Logs de Execução")
    st.code(logs)

    # Botões de ação baseados no status
    if status in ["pendente", "processando"]:
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("Cancelar Processamento", type="secondary", use_container_width=True, key=f"btn_cancel_gee_{tarefa_id}"):
                cancelar_tarefa(tarefa_id)
                st.toast("Cancelamento solicitado.")
                st.rerun()
        with col_btn2:
            if st.button("Fechar Janela", type="primary", use_container_width=True, key=f"btn_hide_gee_{tarefa_id}"):
                st.session_state[f"tarefa_dismissed_{tarefa_id}"] = True
                if "tarefa_id_monitorada" in st.session_state:
                    del st.session_state["tarefa_id_monitorada"]
                st.rerun()
        # Atualização automática da modal
        time.sleep(2)
        st.rerun()
    else:
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.download_button(
                label="Baixar Logs (.txt)",
                data=logs,
                file_name=f"log_gee_tarefa_{tarefa_id}_{datetime.date.today()}.txt",
                mime="text/plain",
                use_container_width=True,
                key=f"btn_download_logs_gee_{tarefa_id}"
            )
        with col_c2:
            if st.button("Fechar", type="primary", use_container_width=True, key=f"btn_close_gee_{tarefa_id}"):
                if "tarefa_id_monitorada" in st.session_state:
                    st.session_state[f"tarefa_dismissed_{st.session_state['tarefa_id_monitorada']}"] = True
                    del st.session_state["tarefa_id_monitorada"]
                st.rerun()

if hasattr(st, "dialog"):
    sig = inspect.signature(st.dialog)
    if 'on_dismiss' in sig.parameters:
        @st.dialog("Processando no GEE", dismissible=False, on_dismiss=on_dismiss_gee_callback)
        def processar_gee_modal(tid):
            processar_gee_conteudo(tid)
    else:
        @st.dialog("Processando no GEE", dismissible=False)
        def processar_gee_modal(tid):
            processar_gee_conteudo(tid)
else:
    def processar_gee_modal(tid):
        with st.expander("Processando no GEE", expanded=True):
            processar_gee_conteudo(tid)


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


# Busca os dados salvos no banco e no Google Drive com indicador visual
with st.spinner("Buscando arquivos"):
    dados = obter_metadados_salvos()
    arquivos_drive = listar_arquivos_pasta_drive("CSV_Sentinel2")

# Cria um set dos nomes dos arquivos no Drive para busca rápida O(1)
nomes_arquivos_drive = {arq.get('name') for arq in arquivos_drive if arq.get('name')}


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

        # Filtro de Intervalo de Pixels Válidos, Toggle de Status e Botão de Limpar Filtro
        has_valign = 'vertical_alignment' in inspect.signature(st.columns).parameters
        if has_valign:
            col_slider, col_toggle, col_clear = st.columns([7, 3, 3.5], vertical_alignment="bottom")
        else:
            col_slider, col_toggle, col_clear = st.columns([7, 3, 3.5])
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
        with col_toggle:
            if not has_valign:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            status_drive_toggle = st.toggle(
                "Ausentes / Disponíveis",
                value=False,
                key=f"filtro_status_drive_{st.session_state['reset_counter']}"
            )
        with col_clear:
            if not has_valign:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            st.button("Limpar Filtro", type="secondary", use_container_width=True, on_click=limpar_filtros_callback)

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

    # Determina o status do produto no Google Drive antes do aproveitamento e filtragem por toggle
    def obter_status_drive(row):
        date_str = row['data'].strftime('%Y-%m-%d') if isinstance(row['data'], (datetime.date, datetime.datetime)) else str(row['data'])
        pixel_size = int(row['tamanho_pixel'])
        nome_esperado = f"CELMM_Data_{date_str}_{pixel_size}m.csv"
        return "Disponível ✅" if nome_esperado in nomes_arquivos_drive else "Ausente ❌"

    if not df_filtrado.empty:
        df_filtrado = df_filtrado.copy()
        df_filtrado['Status no Drive'] = df_filtrado.apply(obter_status_drive, axis=1)
        
        # Filtra conforme o toggle (True = Disponível, False = Ausente)
        if status_drive_toggle:
            df_filtrado = df_filtrado[df_filtrado['Status no Drive'] == "Disponível ✅"]
        else:
            df_filtrado = df_filtrado[df_filtrado['Status no Drive'] == "Ausente ❌"]

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
            'Selecionar', 'data', 'satelite', 'pixels_validos', 'Status no Drive'
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
                ),
                "Data do Produto": st.column_config.DateColumn("Data do Produto", format="YYYY-MM-DD", width="medium"),
                "Satélite": st.column_config.TextColumn("Satélite", width="small"),
                "Pixels Válidos": st.column_config.NumberColumn("Pixels Válidos", width="medium"),
                "Status no Drive": st.column_config.TextColumn("Status no Drive", width="medium")
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


        # Verifica se já existe uma tarefa ativa rodando no banco ao carregar a página
        if "tarefa_id_monitorada" not in st.session_state:
            tarefa_ativa = obter_tarefa_ativa()
            if tarefa_ativa and tarefa_ativa["tipo_tarefa"] == "GEE_EXPORT":
                if not st.session_state.get(f"tarefa_dismissed_{tarefa_ativa['id']}", False):
                    st.session_state["tarefa_id_monitorada"] = tarefa_ativa["id"]

        col_spacer, col_reset, col_process = st.columns([6, 3, 3])
        with col_reset:
            st.button("Reiniciar Página", type="secondary", use_container_width=True, on_click=reiniciar_pagina_callback)
        with col_process:
            btn_processar = st.button(
                f"Iniciar Processamento ({len(selected_rows)})", 
                type="primary", 
                use_container_width=True,
                disabled=selected_rows.empty or st.session_state.get("tarefa_id_monitorada") is not None
            )

        if btn_processar and not selected_rows.empty:
            # Prepara o payload para a fila
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
            
            # Cria a tarefa no banco de dados
            tarefa_id = criar_tarefa_background("GEE_EXPORT", payload, len(selected_rows_list))
            if tarefa_id:
                st.session_state["tarefa_id_monitorada"] = tarefa_id
                st.rerun()

        if st.session_state.get("tarefa_id_monitorada"):
            processar_gee_modal(st.session_state["tarefa_id_monitorada"])

