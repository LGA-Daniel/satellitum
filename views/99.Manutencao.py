import streamlit as st
import io
from contextlib import redirect_stdout

st.set_page_config(page_title="Satellitum | Manutenção", page_icon="⚙️", layout="wide")

st.title("Manutenção do Sistema")
st.divider()

st.subheader("Banco de Dados")
st.write("Verifique se as tabelas do banco de dados estão criadas e sincronizadas corretamente com a modelagem do sistema.")

if st.button("Verificar e Sincronizar Tabelas do Banco", type="primary"):
    with st.spinner("Executando verificação de tabelas no PostgreSQL..."):
        try:
            from src.verificar_banco import run as verificar_db
            
            # Captura os prints do script
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                verificar_db()
            
            output = buffer.getvalue()
            
            st.success("Verificação concluída!")
            st.text_area("Resultado / Logs do Banco", output, height=400)
            
        except Exception as e:
            st.error(f"Erro ao executar o script de verificação: {e}")
