import streamlit as st
import io
import html
import pandas as pd
import datetime
from contextlib import redirect_stdout
from modules.db import (
    obter_historico_tarefas, 
    obter_status_tarefa, 
    cancelar_tarefa, 
    obter_tarefa_ativa,
    obter_metadados_salvos,
    obter_ids_imagens_com_pixels,
    excluir_pixels_por_imagem_ids,
    excluir_produtos_completos_por_imagem_ids
)
from modules.api_gdrive import listar_arquivos_pasta_drive

st.title("Administração do Sistema")
st.divider()

# Cria as abas administrativas do sistema
tab_auth, tab_db, tab_batch, tab_users, tab_data = st.tabs([
    "🔑 Autenticação Google (Drive & GEE)", 
    "🗄️ Métricas do Banco", 
    "⚙️ Operações em Lote",
    "👥 Gestão de Usuários",
    "💾 Gestão de Dados"
])

with tab_auth:
    from modules.google_auth import (
        obter_status_autenticacao,
        get_login_url,
        get_tokens,
        processar_e_salvar_tokens,
        limpar_credenciais,
        testar_conexao_gdrive,
        testar_conexao_gee
    )
    import os

    st.subheader("Autenticação Google")
    st.caption(
        "Conexão com a conta Google para acesso ao Google Drive e Google Earth Engine (GEE)."
    )
    st.text("")

    # --- 1. STATUS ATUAL DAS CREDENCIAIS ---
    status = obter_status_autenticacao()

    col_st1, col_st2 = st.columns(2)
    with col_st1:
        if status["valido"]:
            st.success("✅ **Status:** Autenticado")
        else:
            st.warning("⚠️ **Status:** Não Autenticado")
    with col_st2:
        st.info(f"**Tipo:** {status['tipo']}")

    st.divider()

    # --- 2. FLUXO DE LOGIN OFICIAL OAUTH WEB ---
    st.markdown("#### 1. Conectar / Renovar Conta Google")
    st.write(
        "Autenticação OAuth 2.0 unificada com o projeto Google Cloud configurado."
    )

    # Verifica se a URL atual contém o parâmetro 'code' retornado pelo Google
    query_params = st.query_params

    if "code" in query_params:
        raw_code = query_params["code"]
        if isinstance(raw_code, list):
            raw_code = raw_code[0]
            
        with st.spinner("Autenticando e gravando credenciais..."):
            tokens = get_tokens(raw_code)
            if "access_token" in tokens:
                st.query_params.clear()
                processar_e_salvar_tokens(tokens)
                st.success("🎉 Autenticado com sucesso na sua conta Google!")
                st.rerun()
            else:
                err_msg = tokens.get("error_description") or tokens.get("error") or "Falha ao obter tokens."
                st.error(f"Erro na autenticação: {err_msg}")
                st.query_params.clear()

    # Exibe o botão de login direto e opção de limpar credenciais
    try:
        login_url = get_login_url()
        col_btn_login, col_btn_clear, _ = st.columns([2.5, 2.5, 7])
        with col_btn_login:
            st.link_button(
                "🚀 Login com Google ↗",
                url=login_url,
                type="primary",
                use_container_width=True
            )
        with col_btn_clear:
            if status["valido"]:
                if st.button("🗑️ Desconectar Conta", use_container_width=True, help="Remove os arquivos de tokens e credenciais salvos"):
                    limpar_credenciais()
                    st.toast("Credenciais removidas com sucesso!", icon="🗑️")
                    st.rerun()
    except Exception as e:
        st.error(f"Erro ao gerar link de login: {e}")

    st.divider()

    # --- 3. TESTES DE CONEXÃO (MODAIS) ---
    @st.dialog("🔍 Teste de Conexão com Google Drive", width="medium")
    def modal_teste_drive():
        st.write("Executando validação de comunicação com a API do **Google Drive (v3)**...")
        with st.spinner("Consultando serviço..."):
            ok_drive, msg_drive = testar_conexao_gdrive()
        if ok_drive:
            st.success(msg_drive)
        else:
            st.error(msg_drive)

    @st.dialog("🌍 Teste de Conexão com Earth Engine (GEE)", width="medium")
    def modal_teste_gee():
        st.write("Executando inicialização e teste de computação com o **Google Earth Engine**...")
        with st.spinner("Consultando serviço..."):
            ok_gee, msg_gee = testar_conexao_gee()
        if ok_gee:
            st.success(msg_gee)
        else:
            st.error(msg_gee)

    st.markdown("#### 2. Testes de Conectividade")
    st.write("Valide se a aplicação consegue se comunicar com as APIs do Google Drive e do Earth Engine:")
    
    col_t1, col_t2, _ = st.columns([2.5, 2.5, 7])
    with col_t1:
        if st.button("🔍 Testar Google Drive", use_container_width=True):
            modal_teste_drive()

    with col_t2:
        if st.button("🌍 Testar Earth Engine", use_container_width=True):
            modal_teste_gee()

with tab_db:
    from modules.db import obter_estatisticas_tamanho_banco

    # Inicializa logs no session_state para que sobrevivam ao rerun
    if "logs_banco" not in st.session_state:
        st.session_state["logs_banco"] = ""

    st.subheader("Métricas de Ocupação do Banco de Dados")
    st.caption("Visão geral do espaço utilizado no disco pelo PostgreSQL e volumetria das tabelas principais.")
    st.text("")

    stats = obter_estatisticas_tamanho_banco()
    contagens = stats.get("contagens", {})
    df_tabelas = stats.get("tabelas_df", pd.DataFrame())

    # Função para renderizar cards padronizados
    def card_db(label, value, subtext=""):
        return f"""
            <div style="
                background-color: rgba(2, 132, 199, 0.08); 
                border: 1px solid rgba(2, 132, 199, 0.25); 
                border-radius: 8px; 
                padding: 14px 16px; 
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                text-align: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                margin-bottom: 15px;
                width: 100%;
            ">
                <p style="margin: 0; font-size: 0.85em; font-weight: 500; color: var(--text-color); opacity: 0.8; text-align: center; width: 100%;">{label}</p>
                <div style="margin: 4px 0 2px 0; font-size: 1.7em; color: var(--primary-color); font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; width: 100%;">{value}</div>
                <small style="color: var(--text-color); opacity: 0.65; font-size: 0.78em;">{subtext}</small>
            </div>
        """

    # 1. Cards de Métricas
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.markdown(card_db("Tamanho Total do Banco", stats.get("total_pretty", "0 MB"), f"Banco: {stats.get('db_name', 'satellitum')}"), unsafe_allow_html=True)
    with col_m2:
        qtd_pixels = contagens.get("celmm_pixels", 0)
        st.markdown(card_db("Total de Pixels", f"{qtd_pixels:,}".replace(",", "."), "Tabela: celmm_pixels"), unsafe_allow_html=True)
    with col_m3:
        qtd_meta = contagens.get("metadados_imagens", 0)
        st.markdown(card_db("Produtos / Metadados", f"{qtd_meta:,}".replace(",", "."), "Tabela: metadados_imagens"), unsafe_allow_html=True)

    st.text("")

    # 2. Detalhamento por Tabela
    if not df_tabelas.empty:
        with st.expander("📊 Detalhamento de Ocupação por Tabela e Índices", expanded=False):
            colunas_exibir = [c for c in df_tabelas.columns if c != "bytes_total"]
            st.dataframe(
                df_tabelas[colunas_exibir],
                use_container_width=True,
                hide_index=True
            )

    st.divider()

    # 3. Ferramenta de Verificação e Sincronização
    st.subheader("Verificação de Integridade das Tabelas")
    st.write("Valide se todas as colunas e tabelas necessárias pelo SQLAlchemy e migrações estão presentes no PostgreSQL.")
    st.text("")

    col_btn_v, _ = st.columns([4, 6])
    with col_btn_v:
        btn_verificar = st.button("Verificar e Sincronizar Tabelas do Banco", type="primary", use_container_width=True)

    if btn_verificar:
        with st.spinner("Executando verificação de tabelas no PostgreSQL..."):
            try:
                from modules.verificar_banco import run as verificar_db
                
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    verificar_db()
                
                output = buffer.getvalue()
                st.session_state["logs_banco"] = output
                st.rerun()
                
            except Exception as e:
                st.error(f"Erro ao executar o script de verificação: {e}")

    # Exibe o log se houver conteúdo no session_state
    if st.session_state["logs_banco"]:
        st.divider()
        st.subheader("Logs da Última Sincronização")
        st.text_area("Resultado / Logs do Banco", st.session_state["logs_banco"], height=300)
        
        col_clear, _ = st.columns([2, 10])
        with col_clear:
            if st.button("Limpar Logs", use_container_width=True):
                st.session_state["logs_banco"] = ""
                st.rerun()


from modules.task_monitor import render_conteudo_monitoramento_tarefa, card_destacado, TIPO_MAP

def on_dismiss_logs_modal():
    st.session_state["modal_logs_tarefa_id"] = None

# --- MODAL DE VISUALIZAÇÃO DE LOGS DE OPERAÇÃO EM LOTE ---
def modal_visualizar_logs_tarefa(tarefa_id: int):
    t = obter_status_tarefa(tarefa_id)
    tipo_cod = t.get("tipo_tarefa") if t else ""
    nome_op = TIPO_MAP.get(tipo_cod, "Detalhes e Logs da Tarefa")
    
    import inspect
    sig_dialog = inspect.signature(st.dialog)
    if 'on_dismiss' in sig_dialog.parameters:
        @st.dialog(f"Logs: {nome_op}", width="large", on_dismiss=on_dismiss_logs_modal)
        def _inner(tid):
            render_conteudo_monitoramento_tarefa(tid, live_polling=True, show_download_log=True)
        _inner(tarefa_id)
    else:
        @st.dialog(f"Logs: {nome_op}", width="large", dismissible=True)
        def _inner(tid):
            render_conteudo_monitoramento_tarefa(tid, live_polling=True, show_download_log=True)
        _inner(tarefa_id)


with tab_batch:
    st.subheader("Histórico de Operações em Lote")
    st.caption("Acompanhe o status, cancele execuções ativas ou visualize os logs completos das tarefas em segundo plano.")
    st.text("")

    # Busca as tarefas registradas no banco
    tarefas = obter_historico_tarefas(limit=50)

    if not tarefas:
        st.info("Nenhuma operação em lote foi registrada no sistema.")
    else:
        status_map = {
            "pendente": "⏳ Pendente",
            "processando": "🔄 Processando",
            "concluido": "✅ Concluído",
            "falhou": "❌ Falhou",
            "cancelado": "🚫 Cancelado"
        }
        tipo_map = {
            "FULL_PIPELINE": "Processo Completo",
            "GEE_EXPORT": "Exportação GEE",
            "CSV_INGEST": "Sincronização de CSV"
        }

        linhas = []
        for t in tarefas:
            criado_dt = datetime.datetime.fromisoformat(t["criado_em"]) if t["criado_em"] else None
            atualizado_dt = datetime.datetime.fromisoformat(t["atualizado_em"]) if t["atualizado_em"] else None
            
            linhas.append({
                "ID": int(t["id"]),
                "Operação": tipo_map.get(t["tipo_tarefa"], t["tipo_tarefa"]),
                "Status": status_map.get(t["status"], t["status"]),
                "Progresso": f"{t['itens_processados']}/{t['total_itens']}",
                "Criado em": criado_dt.strftime("%d/%m/%Y %H:%M:%S") if criado_dt else "N/A",
                "Atualizado em": atualizado_dt.strftime("%d/%m/%Y %H:%M:%S") if atualizado_dt else "N/A",
                "status_raw": t["status"]
            })

        df_tarefas = pd.DataFrame(linhas)

        # Tabela com seleção estritamente unitária (single-row)
        event = st.dataframe(
            df_tarefas,
            key="tabela_tarefas_batch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "ID": st.column_config.NumberColumn("ID", width="small"),
                "Operação": st.column_config.TextColumn("Operação", width="medium"),
                "Status": st.column_config.TextColumn("Status", width="medium"),
                "Progresso": st.column_config.TextColumn("Progresso", width="small"),
                "Criado em": st.column_config.TextColumn("Criado em", width="medium"),
                "Atualizado em": st.column_config.TextColumn("Atualizado em", width="medium"),
                "status_raw": None
            },
            use_container_width=True
        )

        st.divider()

        # Identifica a tarefa selecionada
        selected_rows_idx = event.selection.rows if (event and hasattr(event, "selection")) else []
        tem_selecao = (len(selected_rows_idx) == 1)
        
        if tem_selecao:
            tarefa_sel = df_tarefas.iloc[selected_rows_idx[0]]
            id_sel = int(tarefa_sel["ID"])
            status_sel = tarefa_sel["status_raw"]
            pode_cancelar = status_sel in ["pendente", "processando"]
        else:
            id_sel = None
            status_sel = None
            pode_cancelar = False

        # Barra de Ações no Rodapé
        col_spacer, col_t_log, col_t_cancel = st.columns([6, 3, 3])

        with col_t_log:
            if st.button(
                "📄 Visualizar Logs",
                type="primary",
                use_container_width=True,
                disabled=not tem_selecao,
                help="Abre os logs detalhados da tarefa selecionada em uma janela modal."
            ):
                st.session_state["modal_logs_tarefa_id"] = id_sel
                st.rerun()

        with col_t_cancel:
            if st.button(
                "🚫 Cancelar Tarefa",
                type="secondary",
                use_container_width=True,
                disabled=not pode_cancelar,
                help="Interrompe e cancela a tarefa se estiver pendente ou em processamento."
            ):
                with st.spinner(f"Cancelando tarefa #{id_sel}..."):
                    cancelar_tarefa(id_sel)
                    st.toast(f"Tarefa #{id_sel} cancelada com sucesso!")
                    st.rerun()

    # Exibe a modal se houver ID configurado
    if st.session_state.get("modal_logs_tarefa_id"):
        modal_visualizar_logs_tarefa(int(st.session_state["modal_logs_tarefa_id"]))

with tab_users:
    from modules.admin_users_view import render_admin_users_tab
    render_admin_users_tab()

# --- DIÁLOGO DE CONFIRMAÇÃO DE EXCLUSÃO DE PIXELS ---
@st.dialog("🗑️ Confirmar Exclusão de Pixels", width="medium")
def dialog_confirmar_exclusao_pixels(ids_sel: list, datas_txt: list):
    st.warning(f"⚠️ Deseja excluir os dados de pixels de **{len(ids_sel)}** produto(s)?")
    st.markdown(f"**Datas afetadas:** {', '.join(datas_txt[:10])}{' e mais...' if len(datas_txt) > 10 else ''}")
    st.caption("Esta ação liberará espaço no disco apagando os registros da tabela `celmm_pixels`. Os metadados continuarão catalogados no sistema.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Sim, Excluir Pixels", type="primary", use_container_width=True, key="btn_conf_del_pixels"):
            with st.spinner("Excluindo registros de pixels no PostgreSQL..."):
                qtd = excluir_pixels_por_imagem_ids(ids_sel)
                st.toast(f"{qtd:,} pixels excluídos com sucesso!", icon="🗑️")
                st.session_state["show_dialog_del_pixels"] = False
                st.session_state["del_pixels_ids"] = []
                st.session_state["del_pixels_datas"] = []
                st.rerun()
    with col2:
        if st.button("Cancelar", use_container_width=True, key="btn_cancel_del_pixels"):
            st.session_state["show_dialog_del_pixels"] = False
            st.rerun()


# --- ABA DE GESTÃO DE DADOS (ÚLTIMA ABA) ---
with tab_data:
    st.subheader("Gestão de Dados do Banco")
    st.caption("Filtre e selecione os produtos salvos no PostgreSQL para excluir registros de pixels e liberar espaço em disco.")
    st.text("")

    dados_mgmt = obter_metadados_salvos()
    arquivos_drive_mgmt = listar_arquivos_pasta_drive("CSV_Sentinel2")
    ids_com_pixels_mgmt = obter_ids_imagens_com_pixels()

    map_drive_mgmt = {arq.get('name', '').strip(): arq.get('id') for arq in arquivos_drive_mgmt if arq.get('name')}
    map_drive_mgmt_lower = {arq.get('name', '').strip().lower(): arq.get('id') for arq in arquivos_drive_mgmt if arq.get('name')}
    nomes_drive_set = set(map_drive_mgmt.keys())
    nomes_drive_lower_set = set(map_drive_mgmt_lower.keys())

    # Popula SOMENTE com dados que estiverem salvos no banco
    if not dados_mgmt or not ids_com_pixels_mgmt:
        st.info("Nenhum dado de pixel está salvo no banco de dados no momento.")
    else:
        df_del = pd.DataFrame(dados_mgmt)
        df_del = df_del[df_del['id'].isin(ids_com_pixels_mgmt)]

        if df_del.empty:
            st.info("Nenhum dado de pixel está salvo no banco de dados no momento.")
        else:
            df_del['data'] = pd.to_datetime(df_del['data']).dt.date
            df_del = df_del.sort_values(by='data', ascending=False)

            def verificar_drive_del(row):
                nome_esp = f"CELMM_Data_{row['data'].strftime('%Y-%m-%d')}_{int(row['tamanho_pixel'])}m.csv"
                if nome_esp in nomes_drive_set or nome_esp.lower() in nomes_drive_lower_set:
                    return "Disponível ✅"
                return "Não Encontrado ❌"

            df_del['Status no Drive'] = df_del.apply(verificar_drive_del, axis=1)

            # Filtros
            with st.expander("Filtros de Produtos", expanded=False):
                col_df1, col_df2 = st.columns(2)
                with col_df1:
                    sats_del = df_del['satelite'].unique().tolist()
                    sats_sel = st.multiselect("Satélite", options=sats_del, default=sats_del, key="del_filtro_sat")
                    
                    grades_del = df_del['z_grade_mgrs'].dropna().unique().tolist()
                    grades_sel = st.multiselect("Grade MGRS", options=grades_del, default=grades_del, key="del_filtro_grade")
                    
                with col_df2:
                    px_del = sorted(df_del['tamanho_pixel'].unique().tolist())
                    px_sel = st.selectbox("Tamanho do Pixel (m)", options=[int(p) for p in px_del], index=0, key="del_filtro_px")
                    
                    d_min_del = df_del['data'].min()
                    d_max_del = df_del['data'].max()
                    if d_min_del == d_max_del:
                        p_inicio, p_fim = d_min_del, d_max_del
                    else:
                        periodo_del = st.date_input("Período", value=(d_min_del, d_max_del), min_value=d_min_del, max_value=d_max_del, key="del_filtro_periodo")
                        if isinstance(periodo_del, tuple) and len(periodo_del) == 2:
                            p_inicio, p_fim = periodo_del
                        else:
                            p_inicio, p_fim = d_min_del, d_max_del

                col_sl_del, col_t_drive = st.columns([8, 4])
                with col_sl_del:
                    min_p = int(df_del['pixels_validos'].min())
                    max_p = int(df_del['pixels_validos'].max())
                    if min_p < max_p:
                        range_px = st.slider("Pixels Válidos", min_value=min_p, max_value=max_p, value=(min_p, max_p), key="del_filtro_px_range")
                    else:
                        range_px = (min_p, max_p)
                with col_t_drive:
                    toggle_drive_del = st.toggle("Somente com CSV no Drive", value=False, key="del_filtro_toggle_drive")

            # Aplicação dos Filtros
            df_del_filtrado = df_del[
                (df_del['satelite'].isin(sats_sel)) &
                (df_del['z_grade_mgrs'].isin(grades_sel)) &
                (df_del['tamanho_pixel'] == int(px_sel)) &
                (df_del['data'] >= p_inicio) &
                (df_del['data'] <= p_fim) &
                (df_del['pixels_validos'] >= range_px[0]) &
                (df_del['pixels_validos'] <= range_px[1])
            ]
            if toggle_drive_del:
                df_del_filtrado = df_del_filtrado[df_del_filtrado['Status no Drive'] == "Disponível ✅"]

            if df_del_filtrado.empty:
                st.warning("Nenhum produto salvo corresponde aos filtros selecionados.")
            else:
                col_chk_del, _ = st.columns([3, 9])
                with col_chk_del:
                    marcar_todos_del = st.checkbox("Marcar todos", value=False, key="del_chk_marcar_todos")

                df_del_display = df_del_filtrado.copy()
                df_del_display.insert(0, "Selecionar", marcar_todos_del)

                df_del_to_edit = df_del_display[[
                    'Selecionar', 'id', 'data', 'satelite', 'z_grade_mgrs', 'tamanho_pixel', 'pixels_validos', 'Status no Drive'
                ]].rename(columns={
                    'data': 'Data do Produto',
                    'satelite': 'Satélite',
                    'z_grade_mgrs': 'Grade MGRS',
                    'tamanho_pixel': 'Tamanho Pixel (m)',
                    'pixels_validos': 'Pixels Válidos'
                })

                edited_del_df = st.data_editor(
                    df_del_to_edit,
                    key=f"editor_del_produtos_{marcar_todos_del}",
                    hide_index=True,
                    column_config={
                        "Selecionar": st.column_config.CheckboxColumn("Selecionar", default=marcar_todos_del),
                        "id": None,
                        "Data do Produto": st.column_config.DateColumn("Data do Produto", format="YYYY-MM-DD", width="medium"),
                        "Satélite": st.column_config.TextColumn("Satélite", width="small"),
                        "Grade MGRS": st.column_config.TextColumn("Grade MGRS", width="small"),
                        "Tamanho Pixel (m)": st.column_config.NumberColumn("Tamanho Pixel (m)", width="small"),
                        "Pixels Válidos": st.column_config.NumberColumn("Pixels Válidos", width="medium"),
                        "Status no Drive": st.column_config.TextColumn("Arquivo CSV", width="medium")
                    },
                    disabled=[c for c in df_del_to_edit.columns if c != "Selecionar"],
                    use_container_width=True
                )

                st.divider()

                # Produtos selecionados
                rows_del_sel = edited_del_df[edited_del_df["Selecionar"] == True]
                tot_del_sel = len(rows_del_sel)

                # Barra de Ações: Exclusão Exclusiva de Pixels
                col_sp_del, col_b_del_pix = st.columns([8, 4])

                with col_b_del_pix:
                    label_btn_pix = f"🗑️ Excluir Pixels ({tot_del_sel})" if tot_del_sel > 0 else "🗑️ Excluir Pixels"
                    if st.button(
                        label_btn_pix,
                        type="primary",
                        use_container_width=True,
                        disabled=tot_del_sel == 0,
                        help="Exclui os registros de pixels (tabela celmm_pixels) dos produtos selecionados no PostgreSQL. Os metadados serão preservados."
                    ):
                        ids_pixels = [int(i) for i in rows_del_sel['id'].tolist()]
                        datas_pixels = [str(d) for d in rows_del_sel['Data do Produto'].tolist()]
                        st.session_state["del_pixels_ids"] = ids_pixels
                        st.session_state["del_pixels_datas"] = datas_pixels
                        st.session_state["show_dialog_del_pixels"] = True
                        st.rerun()

    # Disparo do diálogo condicional
    if st.session_state.get("show_dialog_del_pixels", False):
        dialog_confirmar_exclusao_pixels(
            st.session_state.get("del_pixels_ids", []),
            st.session_state.get("del_pixels_datas", [])
        )
