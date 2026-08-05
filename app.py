import streamlit as st


# Injeta CSS global da aplicação
st.html("""
    <style>
        /* Oculta as páginas de prévia e visualização rápida do menu lateral */
        a[href*="celmm_previa_dados"],
        a[href*="celmm_visualizacao_rapida"] {
            display: none !important;
        }
        
        /* Ajusta a largura global das janelas modais (st.dialog) para 50% da largura da tela */
        @media (min-width: 768px) {
            div[data-testid="stDialog"] div[role="dialog"],
            div[data-testid="stDialog"] div[aria-modal="true"],
            div[data-testid="stDialog"] > div:first-child {
                width: 50vw !important;
                max-width: 50vw !important;
            }
        }
        @media (max-width: 767px) {
            div[data-testid="stDialog"] div[role="dialog"],
            div[data-testid="stDialog"] div[aria-modal="true"],
            div[data-testid="stDialog"] > div:first-child {
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
    st.Page("views/07.CELMM_VISUALIZACAO_RAPIDA.py", title="CELMM - Visualização Rápida", url_path="celmm_visualizacao_rapida"),
    st.Page("views/99.Manutencao.py", title="Configurações do Sistema"),

])

# Executa a página selecionada
paginas.run()