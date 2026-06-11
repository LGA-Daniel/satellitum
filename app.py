import streamlit as st


# Injeta CSS global da aplicação
st.html("""
    <style>
        /* Oculta a página de prévia de dados do menu lateral */
        a[href*="celmm_previa_dados"] {
            display: none !important;
        }
        
        /* Ajusta a largura global das janelas modais (st.dialog) */
        @media (min-width: 768px) {
            div[data-testid="stDialog"] div[role="dialog"],
            div[data-testid="stDialog"] div[aria-modal="true"] {
                width: 60vw !important;
                max-width: 60vw !important;
            }
        }
        @media (max-width: 767px) {
            div[data-testid="stDialog"] div[role="dialog"],
            div[data-testid="stDialog"] div[aria-modal="true"] {
                width: 90vw !important;
                max-width: 90vw !important;
            }
        }
    </style>
""")

paginas = st.navigation([
    st.Page("views/00.Home.py", title="Satellitum"),
        
    st.Page("views/02.CELMM_VISUALIZAR_METADADOS.py", title="CELMM - Explorar Metadados"),
    st.Page("views/03.CELMM_BAIXAR_IMAGENS.py", title="CELMM - Processar Produtos (CSV | GDRIVE)"),
    st.Page("views/04.CELMM_ARQUIVOS_DRIVE.py", title="CELMM - Sincronizar Produtos"),
    st.Page("views/05.CELMM_VISUALIZAR_DADOS.py", title="CELMM - Visualizar e Exportar Dados", url_path="celmm_visualizar_dados"),
    st.Page("views/06.CELMM_PREVIA_DADOS.py", title="CELMM - Prévia de Dados", url_path="celmm_previa_dados"),
    st.Page("views/99.Manutencao.py", title="Configurações do Sistema"),

])

# Executa a página selecionada
paginas.run()