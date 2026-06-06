import streamlit as st

paginas = st.navigation([
    st.Page("views/00.Home.py", title="Home"),
        
    st.Page("views/01.CELMM_PROCESSAR_METADADOS.py", title="CELMM - Processar Metadados"),
    st.Page("views/02.CELMM_VISUALIZAR_METADADOS.py", title="CELMM - Visualizar Metadados"),
    st.Page("views/03.CELMM_BAIXAR_IMAGENS.py", title="CELMM - Baixar Imagens"),
    st.Page("views/99.Manutencao.py", title="Configurações do Sistema"),

])

# Executa a página selecionada
paginas.run()