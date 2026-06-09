import streamlit as st
import io
from contextlib import redirect_stdout
from modules.core import engine
from sqlalchemy import inspect

st.set_page_config(page_title="Satellitum | Manutenção", page_icon="⚙️", layout="wide")

st.title("Manutenção do Sistema")
st.divider()

# Inicializa logs no session_state para que sobrevivam ao rerun
if "logs_banco" not in st.session_state:
    st.session_state["logs_banco"] = ""

st.subheader("Banco de Dados")
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
            
            # Recarrega a página para atualizar o status do alerta (Ativa ✅ / Ausente ❌)
            st.rerun()
            
        except Exception as e:
            st.error(f"Erro ao executar o script de verificação: {e}")

# Exibe o log se houver conteúdo no session_state
if st.session_state["logs_banco"]:
    st.divider()
    st.subheader("Logs da Última Sincronização")
    st.text_area("Resultado / Logs do Banco", st.session_state["logs_banco"], height=400)
    
    col_clear, _ = st.columns([2, 10])
    with col_clear:
        if st.button("Limpar Logs 🗑️", use_container_width=True):
            st.session_state["logs_banco"] = ""
            st.rerun()
