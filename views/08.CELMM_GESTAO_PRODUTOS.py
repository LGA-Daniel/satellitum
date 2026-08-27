import streamlit as st
import pandas as pd
import datetime
import inspect

from modules.db import (
    obter_metadados_salvos,
    obter_ids_imagens_com_pixels,
    obter_tarefa_ativa,
    obter_status_tarefa
)
from modules.api_gee import init_gee
from modules.api_gdrive import listar_arquivos_pasta_drive
from modules.task_monitor import card_destacado, monitorar_tarefa_dialog
from modules.busca_produtos import buscar_produtos_dialog
from modules.central_acoes import central_acoes_dialog
from modules.download_arquivos import baixar_arquivos_dialog

# Configuração da página
st.set_page_config(page_title="CELMM | Gerenciamento de Produtos Orbitais", page_icon="🛰️", layout="wide")

# Controle de estado e reset de filtros
if 'reset_counter' not in st.session_state:
    st.session_state['reset_counter'] = 0

if 'show_buscar_modal' not in st.session_state:
    st.session_state['show_buscar_modal'] = False

if 'show_acoes_modal' not in st.session_state:
    st.session_state['show_acoes_modal'] = False

if 'show_download_modal' not in st.session_state:
    st.session_state['show_download_modal'] = False

def limpar_filtros_callback():
    st.session_state['reset_counter'] += 1
    listar_arquivos_pasta_drive.clear()
    resetar_estado_processamento()

def resetar_estado_processamento():
    st.session_state["confirmar_sobrescrever_pixels"] = False
    st.session_state["pixels_dados_conflito"] = []

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
        buscar_produtos_dialog()
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
# 10. MÓDULOS DE DIÁLOGO CONDICIONAIS
# ==============================================================================
if st.session_state.get('show_buscar_modal', False):
    buscar_produtos_dialog()

if st.session_state.get('show_acoes_modal', False):
    central_acoes_dialog(
        selected_rows, 
        valid_drive_selected, 
        valid_db_selected, 
        df_filtrado, 
        map_nome_id, 
        map_nome_id_lower
    )

if st.session_state.get('show_download_modal', False):
    baixar_arquivos_dialog(valid_drive_selected, map_nome_id, map_nome_id_lower)

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
    monitorar_tarefa_dialog(tid, tipo_desc)
