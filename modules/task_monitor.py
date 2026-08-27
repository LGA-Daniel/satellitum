import time
import datetime
import html
import streamlit as st
from modules.db import obter_status_tarefa, cancelar_tarefa

STATUS_MAP = {
    "pendente": "⏳ Pendente",
    "processando": "🔄 Processando",
    "concluido": "✅ Concluído",
    "falhou": "❌ Falhou",
    "cancelado": "🚫 Cancelado"
}

TIPO_MAP = {
    "FULL_PIPELINE": "Processamento Automático",
    "GEE_EXPORT": "Processamento no GEE",
    "CSV_INGEST": "Sincronização de Produtos"
}

def card_destacado(label: str, value: str, title_tooltip: str = None) -> str:
    """Retorna o HTML formatado de um card de métrica padrão do sistema."""
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
            margin-bottom: 12px;
            width: 100%;
        " {tooltip_attr}>
            <p style="margin: 0; font-size: 0.85em; font-weight: 500; color: var(--text-color); opacity: 0.8; text-align: center; width: 100%;">{label}</p>
            <div style="margin: 4px 0 0 0; font-size: 1.3em; color: var(--primary-color); font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; width: 100%;">{value}</div>
        </div>
    """

def render_conteudo_monitoramento_tarefa(tarefa_id: int, live_polling: bool = True, show_download_log: bool = False):
    """Renderiza o conteúdo completo e padronizado da modal 'Detalhes e Logs da Tarefa'."""
    t = obter_status_tarefa(tarefa_id)
    if not t:
        st.error("Tarefa não encontrada no banco de dados.")
        return

    status = t["status"]
    st_proc = t["itens_processados"]
    st_tot = t["total_itens"]
    st_logs = t["logs"] or ""
    tipo_tarefa_code = t.get("tipo_tarefa", "")
    nome_op = TIPO_MAP.get(tipo_tarefa_code, tipo_tarefa_code)
    label_status = STATUS_MAP.get(status, status.capitalize())
    pct = st_proc / st_tot if st_tot > 0 else (1.0 if status == "concluido" else 0.0)

    # 1. Cards de Métricas Padronizados
    col_i1, col_i2, col_i3 = st.columns(3)
    with col_i1:
        st.markdown(card_destacado("Operação", nome_op), unsafe_allow_html=True)
    with col_i2:
        st.markdown(card_destacado("Status", label_status), unsafe_allow_html=True)
    with col_i3:
        st.markdown(card_destacado("Progresso", f"{st_proc} / {st_tot}"), unsafe_allow_html=True)

    # 2. Barra de Progresso
    st.markdown("")
    st.progress(pct, text=f"{nome_op}: {st_proc}/{st_tot} itens ({int(pct*100)}%)")

    # 3. Terminal Escuro de Logs
    st.markdown("#### Log de Execução:")
    log_text = st_logs if st_logs else "Aguardando logs..."
    escaped_logs = html.escape(log_text)
    st.markdown(f"""
        <div style="
            background-color: #0d1117; 
            border: 1px solid rgba(255, 255, 255, 0.12); 
            border-radius: 8px; 
            padding: 12px 16px; 
            height: 360px; 
            overflow-y: auto; 
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; 
            font-size: 0.82rem; 
            line-height: 1.5; 
            color: #58a6ff; 
            white-space: pre-wrap;
            word-break: break-word;
        ">{escaped_logs}</div>
    """, unsafe_allow_html=True)
    st.markdown("")

    # 4. Ações inferiores
    if status in ["pendente", "processando"]:
        if st.button("❌ Cancelar Execução", type="secondary", use_container_width=True, key=f"btn_cancel_task_{tarefa_id}"):
            cancelar_tarefa(tarefa_id)
            st.toast("Cancelamento solicitado.")
            st.rerun()

        if live_polling:
            time.sleep(1.5)
            st.rerun()
    elif show_download_log and status not in ["pendente", "processando"]:
        st.download_button(
            label="⬇️ Baixar Logs (.txt)",
            data=st_logs,
            file_name=f"log_tarefa_{tarefa_id}_{datetime.date.today()}.txt",
            mime="text/plain",
            use_container_width=True,
            key=f"btn_download_log_shared_{tarefa_id}"
        )
