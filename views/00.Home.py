import streamlit as st

st.set_page_config(page_title="Satellitum | Home", page_icon="🛰️", layout="wide")

current_user = st.session_state.get("user")
if not current_user:
    st.error("⛔ Acesso não autorizado. Faça login para acessar o sistema.")
    st.stop()

st.title("Satellitum")

st.subheader("Sistema de Processamento e Armazenamento de Produtos Orbitais")

st.divider()

st.caption("FlowBR | PPGRHS | Centro de Tecnologia — Versão Beta 08.2026")