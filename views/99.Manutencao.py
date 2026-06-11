import streamlit as st
import io
import pandas as pd
import datetime
from contextlib import redirect_stdout
from modules.core import (
    obter_historico_tarefas, 
    obter_status_tarefa, 
    cancelar_tarefa, 
    obter_tarefa_ativa
)

st.set_page_config(page_title="Satellitum | Configurações do Sistema", page_icon="🛰️", layout="wide")

st.title("Configurações do Sistema")
st.divider()

# Cria as abas de configuração
tab_db, tab_batch = st.tabs(["Banco de Dados", "Operações em Lote"])

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
                from src.verificar_banco import run as verificar_db
                
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
