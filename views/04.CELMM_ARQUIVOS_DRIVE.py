import streamlit as st
import pandas as pd
import datetime
import os
import shutil
import inspect
from modules.core import (
    obter_metadados_salvos, 
    listar_arquivos_pasta_drive, 
    baixar_arquivo_drive_para_disco, 
    salvar_pixels_bulk, 
    obter_ids_imagens_com_pixels,
    criar_tarefa_background,
    obter_tarefa_ativa,
    obter_status_tarefa,
    cancelar_tarefa
)

st.set_page_config(page_title="CELMM | Sincronizar Produtos", page_icon="🛰️", layout="wide")

st.title("CELMM - Sincronizar Produtos")
st.divider()

# Carregamento dos dados em paralelo com indicador visual
with st.spinner("Buscando Arquivos"):
    dados = obter_metadados_salvos()
    arquivos_drive = listar_arquivos_pasta_drive("CSV_Sentinel2")
    ids_com_pixels = obter_ids_imagens_com_pixels()

# Cria um set dos nomes dos arquivos no Drive para busca rápida O(1)
nomes_arquivos_drive = {arq.get('name') for arq in arquivos_drive if arq.get('name')}

# Define a pasta temporária para armazenar os arquivos CSV fisicamente no servidor
module_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(module_dir)
temp_dir = os.path.join(project_root, "temp_downloads")

def resetar_estado_processamento():
    """Reseta as flags de processamento no session_state para evitar que o modal abra automaticamente ao interagir com a página."""
    st.session_state["executar_processamento"] = False
    st.session_state["processamento_concluido"] = False
    st.session_state["confirmar_sobrescrever_pixels"] = False
    st.session_state["pixels_dados_conflito"] = []
    if "logs_processamento" in st.session_state:
        try:
            del st.session_state["logs_processamento"]
        except KeyError:
            pass

if 'reset_counter' not in st.session_state:
    st.session_state['reset_counter'] = 0

def limpar_filtros_callback():
    st.session_state['reset_counter'] += 1
    resetar_estado_processamento()

def on_dismiss_csv_callback():
    if "tarefa_id_monitorada" in st.session_state:
        tid = st.session_state["tarefa_id_monitorada"]
        st.session_state[f"tarefa_dismissed_{tid}"] = True
        del st.session_state["tarefa_id_monitorada"]

def limpar_pasta_temporaria():
    """Apaga e recria de forma limpa a pasta de downloads temporários."""
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
    os.makedirs(temp_dir, exist_ok=True)

# Função contendo a lógica de download e compactação
def baixar_arquivos_conteudo(valid_selected, map_nome_id):
    st.write(f"Você selecionou **{len(valid_selected)}** arquivo(s) disponível(is) para download.")
    
    with st.spinner("Baixando arquivos do Drive diretamente para o disco do servidor..."):
        try:
            limpar_pasta_temporaria()
            files_downloaded = []
            
            for idx, row in valid_selected.iterrows():
                # Converte a data para string YYYY-MM-DD
                date_str = row["Data do Produto"].strftime('%Y-%m-%d') if isinstance(row["Data do Produto"], (datetime.date, datetime.datetime)) else str(row["Data do Produto"])
                nome_esperado = f"CELMM_Data_{date_str}_{int(row['Tamanho Pixel (m)'])}m.csv"
                fid = map_nome_id.get(nome_esperado)
                if fid:
                    dest_path = os.path.join(temp_dir, nome_esperado)
                    # Download streaming direto para disco
                    baixar_arquivo_drive_para_disco(fid, dest_path)
                    files_downloaded.append(dest_path)
            
            if not files_downloaded:
                st.warning("Nenhum arquivo correspondente encontrado no Drive.")
            elif len(files_downloaded) == 1:
                local_file_path = files_downloaded[0]
                filename = os.path.basename(local_file_path)
                
                with open(local_file_path, "rb") as f:
                    st.download_button(
                        label="Salvar Arquivo no Computador",
                        data=f,
                        file_name=filename,
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )
            else:
                # Cria arquivo ZIP no disco temporário
                import zipfile
                zip_filename = f"CELMM_CSVs_{datetime.date.today().strftime('%Y%m%d')}.zip"
                zip_path = os.path.join(temp_dir, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for filepath in files_downloaded:
                        zip_file.write(filepath, os.path.basename(filepath))
                        
                with open(zip_path, "rb") as f:
                    st.download_button(
                        label="Salvar Arquivo ZIP no Computador",
                        data=f,
                        file_name=zip_filename,
                        mime="application/zip",
                        type="primary",
                        use_container_width=True
                    )
        except Exception as e:
            st.error(f"Erro ao processar arquivos do Drive: {e}")

# Definição dinâmica do modal para suportar retrocompatibilidade do Streamlit
if hasattr(st, "dialog"):
    baixar_arquivos_modal = st.dialog("Baixar Arquivos do Google Drive")(baixar_arquivos_conteudo)
else:
    def baixar_arquivos_modal(valid_selected, map_nome_id):
        with st.expander("Preparação do Download", expanded=True):
            baixar_arquivos_conteudo(valid_selected, map_nome_id)

# Função contendo a lógica de processamento do CSV para o banco
# Função contendo a lógica de processamento do CSV para o banco (monitorada via fila)
def processar_csv_conteudo(tarefa_id):
    import time
    t = obter_status_tarefa(tarefa_id)
    if not t:
        st.error("Tarefa não encontrada.")
        if st.button("Fechar", type="primary", use_container_width=True, key=f"btn_close_not_found_csv_{tarefa_id}"):
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
        st.progress(pct, text=f"Processando CSVs: {processados}/{total} arquivos ({int(pct*100)}%)")
    elif status == "concluido":
        st.success("Sincronização concluída com sucesso!")
        st.progress(1.0)
    elif status == "cancelado":
        st.warning("Processamento cancelado pelo usuário.")
        st.progress(processados / total if total > 0 else 0.0)
    else:
        st.error("A sincronização falhou.")
        st.progress(processados / total if total > 0 else 0.0)

    st.subheader("Logs de Ingestão")
    st.code(logs)

    # Botões de ação baseados no status
    if status in ["pendente", "processando"]:
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("Cancelar Processamento", type="secondary", use_container_width=True, key=f"btn_cancel_csv_{tarefa_id}"):
                cancelar_tarefa(tarefa_id)
                st.toast("Cancelamento solicitado.")
                st.rerun()
        with col_btn2:
            if st.button("Esconder Progresso", type="primary", use_container_width=True, key=f"btn_hide_csv_{tarefa_id}"):
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
                file_name=f"log_ingestao_tarefa_{tarefa_id}_{datetime.date.today()}.txt",
                mime="text/plain",
                use_container_width=True,
                key=f"btn_download_logs_csv_{tarefa_id}"
            )
        with col_c2:
            if st.button("Fechar", type="primary", use_container_width=True, key=f"btn_close_csv_{tarefa_id}"):
                if "tarefa_id_monitorada" in st.session_state:
                    st.session_state[f"tarefa_dismissed_{st.session_state['tarefa_id_monitorada']}"] = True
                    del st.session_state["tarefa_id_monitorada"]
                st.rerun()

if hasattr(st, "dialog"):
    sig = inspect.signature(st.dialog)
    if 'on_dismiss' in sig.parameters:
        @st.dialog("Processar CSV para a Base de Dados", dismissible=False, on_dismiss=on_dismiss_csv_callback)
        def processar_csv_modal(tid):
            processar_csv_conteudo(tid)
    else:
        @st.dialog("Processar CSV para a Base de Dados", dismissible=False)
        def processar_csv_modal(tid):
            processar_csv_conteudo(tid)
else:
    def processar_csv_modal(tid):
        with st.expander("Processamento de CSV", expanded=True):
            processar_csv_conteudo(tid)



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

    # Adiciona a coluna de status correlacionando os registros com o set do Drive previamente
    def verificar_disponibilidade(row):
        nome_esperado = f"CELMM_Data_{row['data'].strftime('%Y-%m-%d')}_{int(row['tamanho_pixel'])}m.csv"
        return "Disponível ✅" if nome_esperado in nomes_arquivos_drive else "Não Encontrado ❌"
        
    df['Status no Drive'] = df.apply(verificar_disponibilidade, axis=1)
    df['Importado para o Banco'] = df.apply(
        lambda r: "Salvo ✅" if (r['id'] in ids_com_pixels or (r['pixels_validos'] == 0 and r['Status no Drive'] == "Disponível ✅")) else "Pendente ⏳",
        axis=1
    )

    # 1. Filtros no Expander (Cópia exata do layout da página de baixar imagens)
    with st.expander("Filtros", expanded=True):
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            # Filtro de Satélite
            satelites_disponiveis = df['satelite'].unique().tolist()
            satelites_selecionados = st.multiselect(
                "Satélite",
                options=satelites_disponiveis,
                default=satelites_disponiveis,
                on_change=resetar_estado_processamento,
                key=f"filtro_satelite_{st.session_state['reset_counter']}"
            )

            # Filtro de Grade MGRS
            grades_disponiveis = df['z_grade_mgrs'].dropna().unique().tolist()
            grades_selecionadas = st.multiselect(
                "Grade MGRS",
                options=grades_disponiveis,
                default=grades_disponiveis,
                on_change=resetar_estado_processamento,
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
                on_change=resetar_estado_processamento,
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
                    on_change=resetar_estado_processamento,
                    key=f"filtro_periodo_{st.session_state['reset_counter']}"
                )
                if isinstance(periodo, tuple) and len(periodo) == 2:
                    data_inicio, data_fim = periodo
                else:
                    data_inicio, data_fim = data_min, data_max

        # Filtro de Intervalo de Pixels Válidos, Toggles de Status e Botão de Limpar Filtro
        has_valign = 'vertical_alignment' in inspect.signature(st.columns).parameters
        if has_valign:
            col_slider, col_t1, col_t2, col_clear = st.columns([6, 2, 2, 2.5], vertical_alignment="bottom")
        else:
            col_slider, col_t1, col_t2, col_clear = st.columns([6, 2, 2, 2.5])
        with col_slider:
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
        with col_t1:
            if not has_valign:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            status_drive_toggle = st.toggle(
                "Somente Disponíveis", 
                value=False, 
                on_change=resetar_estado_processamento, 
                key=f"filtro_status_drive_{st.session_state['reset_counter']}"
            )
        with col_t2:
            if not has_valign:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            status_banco_toggle = st.toggle(
                "Somente Pendentes", 
                value=False, 
                on_change=resetar_estado_processamento, 
                key=f"filtro_status_banco_{st.session_state['reset_counter']}"
            )
        with col_clear:
            if not has_valign:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            st.button("Limpar Filtro", type="secondary", use_container_width=True, on_click=limpar_filtros_callback)

    # Aplicação final dos filtros
    df_filtrado = df[
        (df['satelite'].isin(satelites_selecionados)) &
        (df['z_grade_mgrs'].isin(grades_selecionadas)) &
        (df['tamanho_pixel'] == int(pixel_selecionado)) &
        (df['data'] >= data_inicio) &
        (df['data'] <= data_fim) &
        (df['pixels_validos'] >= pixels_range[0]) &
        (df['pixels_validos'] <= pixels_range[1])
    ]

    # Aplica o filtro de status do Drive conforme o toggle (Apenas se ativado)
    if not df_filtrado.empty:
        if status_drive_toggle:
            df_filtrado = df_filtrado[df_filtrado['Status no Drive'] == "Disponível ✅"]

    # Aplica o filtro de status do banco conforme o toggle (Apenas se ativado)
    if not df_filtrado.empty:
        if status_banco_toggle:
            df_filtrado = df_filtrado[df_filtrado['Importado para o Banco'] == "Pendente ⏳"]

    st.text("")

    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
        # Adiciona caixa para controle rápido de marcação
        selecionar_padrao = st.checkbox("Marcar todas", value=False, on_change=resetar_estado_processamento)
        
        df_display = df_filtrado.copy()
        df_display.insert(0, "Selecionar", selecionar_padrao)
        
        # Seleciona e renomeia as colunas para exibição amigável
        df_to_edit = df_display[[
            'Selecionar', 'id', 'data', 'satelite', 'z_grade_mgrs', 'tamanho_pixel', 'pixels_validos', 'zenital', 'Status no Drive', 'Importado para o Banco'
        ]].rename(columns={
            'data': 'Data do Produto',
            'satelite': 'Satélite',
            'z_grade_mgrs': 'Grade MGRS',
            'tamanho_pixel': 'Tamanho Pixel (m)',
            'pixels_validos': 'Pixels Válidos'
        })
        
        # Mapeamento de nome de arquivo para ID do Drive
        map_nome_id = {arq.get('name'): arq.get('id') for arq in arquivos_drive if arq.get('name') and arq.get('id')}
        
        # Gera uma chave estável e única baseada nos filtros ativos
        filtro_str = f"{sorted(satelites_selecionados)}_{sorted(grades_selecionadas)}_{pixel_selecionado}_{data_inicio}_{data_fim}_{pixels_range}_{status_drive_toggle}_{status_banco_toggle}"
        editor_key = f"editor_drive_{hash(filtro_str)}"
        
        # Exibe a lista interativa com caixa de seleção (checkbox) por linha
        edited_df = st.data_editor(
            df_to_edit,
            key=editor_key,
            on_change=resetar_estado_processamento,
            hide_index=True,
            column_config={
                "Selecionar": st.column_config.CheckboxColumn(
                    "Selecionar",
                    help="Selecione os produtos para download ou processamento",
                    default=selecionar_padrao,
                ),
                "id": None,  # Oculta a coluna id
                "zenital": None,  # Oculta a coluna zenital
                "Data do Produto": st.column_config.DateColumn("Data do Produto", format="YYYY-MM-DD", width="medium"),
                "Satélite": st.column_config.TextColumn("Satélite", width="small"),
                "Grade MGRS": st.column_config.TextColumn("Grade MGRS", width="small"),
                "Tamanho Pixel (m)": st.column_config.NumberColumn("Tamanho Pixel (m)", width="small"),
                "Pixels Válidos": st.column_config.NumberColumn("Pixels Válidos", width="medium"),
                "Status no Drive": st.column_config.TextColumn("Arquivo CSV", width="medium"),
                "Importado para o Banco": st.column_config.TextColumn("Banco de Dados", width="medium")
            },
            disabled=[c for c in df_to_edit.columns if c != "Selecionar"],
            use_container_width=True
        )

        st.divider()

        # Verifica se já existe uma tarefa ativa rodando no banco ao carregar a página
        if "tarefa_id_monitorada" not in st.session_state:
            tarefa_ativa = obter_tarefa_ativa()
            if tarefa_ativa and tarefa_ativa["tipo_tarefa"] == "CSV_INGEST":
                if not st.session_state.get(f"tarefa_dismissed_{tarefa_ativa['id']}", False):
                    st.session_state["tarefa_id_monitorada"] = tarefa_ativa["id"]

        # Seleciona os registros marcados
        selected_rows = edited_df[edited_df["Selecionar"] == True]
        
        # Filtra apenas os selecionados que estão disponíveis no Drive
        valid_selected = selected_rows[selected_rows["Status no Drive"] == "Disponível ✅"]
        
        col_spacer, col_process_db, col_download = st.columns([6, 3, 3])
        
        with col_process_db:
            if not valid_selected.empty:
                btn_sinc = st.button(
                    "Sincronizar com o Banco de Dados", 
                    type="secondary", 
                    use_container_width=True, 
                    key="btn_sincronizar_ativos",
                    disabled=st.session_state.get("tarefa_id_monitorada") is not None
                )
            else:
                btn_sinc = False
                st.button(
                    "Sincronizar com o Banco de Dados", 
                    type="secondary", 
                    use_container_width=True, 
                    disabled=True, 
                    help="Marque pelo menos um produto com status 'Disponível ✅'.",
                    key="btn_sincronizar_inativos"
                )
                
        with col_download:
            if not valid_selected.empty:
                if st.button("Baixar Arquivos", type="primary", use_container_width=True, key="btn_baixar_ativos"):
                    baixar_arquivos_modal(valid_selected, map_nome_id)
            else:
                st.button(
                    "Baixar Arquivos", 
                    type="primary", 
                    use_container_width=True, 
                    disabled=True, 
                    help="Marque pelo menos um produto com status 'Disponível ✅'.",
                    key="btn_baixar_inativos"
                )

        # Inicializa o estado de confirmação se não existir
        if 'confirmar_sobrescrever_pixels' not in st.session_state:
            st.session_state['confirmar_sobrescrever_pixels'] = False
            st.session_state['pixels_dados_conflito'] = []

        if st.session_state['confirmar_sobrescrever_pixels']:
            st.warning(f"Os produtos das seguintes datas já possuem pixels cadastrados no banco: {', '.join(st.session_state['pixels_dados_conflito'])}. Deseja sobrescrever os registros existentes?")
            col_conf_spacer, col_conf_reset, col_conf_save = st.columns([6, 3, 3])
            with col_conf_reset:
                if st.button("Não, Cancelar Ingestão", type="secondary", use_container_width=True, key="btn_cancel_conf_pixels"):
                    st.session_state['confirmar_sobrescrever_pixels'] = False
                    st.session_state['pixels_dados_conflito'] = []
                    st.rerun()
            with col_conf_save:
                if st.button("Sim, Sobrescrever Pixels", type="primary", use_container_width=True, key="btn_save_conf_pixels"):
                    selected_rows_list = []
                    for _, r in valid_selected.iterrows():
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
                    
                    # Cria a tarefa no banco
                    tarefa_id = criar_tarefa_background("CSV_INGEST", payload, len(selected_rows_list))
                    if tarefa_id:
                        st.session_state["tarefa_id_monitorada"] = tarefa_id
                        st.session_state['confirmar_sobrescrever_pixels'] = False
                        st.session_state['pixels_dados_conflito'] = []
                        st.rerun()
        else:
            if btn_sinc and not valid_selected.empty:
                # Verifica se há conflito (registros já importados no banco)
                conflitos = valid_selected[valid_selected['Importado para o Banco'] == 'Salvo ✅']
                if not conflitos.empty:
                    conflito_dates = [c.strftime('%Y-%m-%d') if isinstance(c, (datetime.date, datetime.datetime)) else str(c) for c in conflitos['Data do Produto'].tolist()]
                    st.session_state['confirmar_sobrescrever_pixels'] = True
                    st.session_state['pixels_dados_conflito'] = conflito_dates
                    st.rerun()
                else:
                    selected_rows_list = []
                    for _, r in valid_selected.iterrows():
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
                    
                    # Cria a tarefa no banco
                    tarefa_id = criar_tarefa_background("CSV_INGEST", payload, len(selected_rows_list))
                    if tarefa_id:
                        st.session_state["tarefa_id_monitorada"] = tarefa_id
                        st.rerun()

        if st.session_state.get("tarefa_id_monitorada"):
            processar_csv_modal(st.session_state["tarefa_id_monitorada"])

