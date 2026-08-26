import streamlit as st
import io
import pandas as pd
import datetime
from contextlib import redirect_stdout
from modules.db import (
    obter_historico_tarefas, 
    obter_status_tarefa, 
    cancelar_tarefa, 
    obter_tarefa_ativa
)

st.title("Configurações do Sistema")
st.divider()

# Cria as abas de configuração
tab_auth, tab_db, tab_batch = st.tabs([
    "🔑 Autenticação Google (Drive & GEE)", 
    "🗄️ Banco de Dados", 
    "⚙️ Operações em Lote"
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
    st.write(
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
    # Inicializa logs no session_state para que sobrevivam ao rerun
    if "logs_banco" not in st.session_state:
        st.session_state["logs_banco"] = ""

    st.subheader("Configurações do Banco de Dados")
    st.write("Verifique se as tabelas do banco de dados estão criadas e sincronizadas corretamente com a modelagem do sistema.")
    st.text("")

    if st.button("Verificar e Sincronizar Tabelas do Banco", type="primary"):
        with st.spinner("Executando verificação de tabelas no PostgreSQL..."):
            try:
                from modules.verificar_banco import run as verificar_db
                
                # Captura os prints do script
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    verificar_db()
                
                output = buffer.getvalue()
                
                # Salva no session_state para persistir após o rerun
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

with tab_batch:
    st.subheader("Histórico de Operações em Lote")
    st.write("Acompanhe o status e os logs detalhados de exportação do GEE e sincronização de CSVs.")
    st.text("")

    # Busca as tarefas registradas no banco
    tarefas = obter_historico_tarefas(limit=50)

    if not tarefas:
        st.info("Nenhuma operação em lote foi registrada no sistema.")
    else:
        # Prepara dados para exibição em tabela
        linhas = []
        status_map = {
            "pendente": "⏳ Pendente",
            "processando": "🔄 Processando",
            "concluido": "✅ Concluído",
            "falhou": "❌ Falhou",
            "cancelado": "🚫 Cancelado"
        }
        tipo_map = {
            "GEE_EXPORT": "Exportação GEE",
            "CSV_INGEST": "Sincronização de CSV"
        }

        for t in tarefas:
            criado_dt = datetime.datetime.fromisoformat(t["criado_em"]) if t["criado_em"] else None
            atualizado_dt = datetime.datetime.fromisoformat(t["atualizado_em"]) if t["atualizado_em"] else None
            
            linhas.append({
                "ID": t["id"],
                "Operação": tipo_map.get(t["tipo_tarefa"], t["tipo_tarefa"]),
                "Status": status_map.get(t["status"], t["status"]),
                "Progresso": f"{t['itens_processados']}/{t['total_itens']}",
                "Criado em": criado_dt.strftime("%d/%m/%Y %H:%M:%S") if criado_dt else "N/A",
                "Atualizado em": atualizado_dt.strftime("%d/%m/%Y %H:%M:%S") if atualizado_dt else "N/A",
            })

        df_tarefas = pd.DataFrame(linhas)

        # Exibe tabela das tarefas
        st.dataframe(
            df_tarefas,
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        # Detalhes e logs da tarefa selecionada
        st.subheader("Logs Detalhados da Tarefa")
        opcoes = df_tarefas["ID"].tolist()
        
        id_selecionado = st.selectbox(
            "Selecione uma tarefa para visualizar os detalhes:",
            options=opcoes,
            format_func=lambda x: f"Tarefa #{x} - {df_tarefas[df_tarefas['ID'] == x]['Operação'].values[0]} ({df_tarefas[df_tarefas['ID'] == x]['Status'].values[0]})"
        )

        if id_selecionado:
            t_detalhe = obter_status_tarefa(id_selecionado)
            if t_detalhe:
                col_info1, col_info2, col_info3 = st.columns(3)
                with col_info1:
                    st.metric("Status Atual", status_map.get(t_detalhe["status"], t_detalhe["status"]))
                with col_info2:
                    st.metric("Progresso", f"{t_detalhe['itens_processados']} / {t_detalhe['total_itens']}")
                with col_info3:
                    st.metric("Última Atualização", df_tarefas[df_tarefas['ID'] == id_selecionado]['Atualizado em'].values[0])

                # Se a tarefa está em execução, permite cancelar
                if t_detalhe["status"] in ["pendente", "processando"]:
                    if st.button("Cancelar Operação Selecionada", type="secondary"):
                        cancelar_tarefa(id_selecionado)
                        st.toast("Cancelamento solicitado.")
                        st.rerun()

                st.text("")
                st.markdown("**Logs de Execução:**")
                st.code(t_detalhe["logs"] or "Nenhum log registrado.")

                # Download do log
                st.download_button(
                    label="Baixar Logs desta Tarefa",
                    data=t_detalhe["logs"] or "",
                    file_name=f"log_tarefa_{id_selecionado}_{datetime.date.today()}.txt",
                    mime="text/plain"
                )

