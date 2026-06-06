import streamlit as st

paginas = st.navigation([
    st.Page("views/00.Home.py", title="Home"),
        
    st.Page("views/01.GEE001.py", title="CELMM - Analisar Metadados"),
    st.Page("views/02.GEE002.py", title="CELMM - Processar Imagens"),
    st.Page("views/03.VisualizarMetadados.py", title="CELMM - Visualizar Metadados"),
    st.Page("views/99.Manutencao.py", title="Manutenção"),

])

# Executa a página selecionada
paginas.run()