import datetime
import streamlit as st
import pandas as pd
from modules.db import obter_df_pixels_por_imagem_ids
from modules.data_export import preparar_arquivo_exportacao

def exportar_conteudo_modal(ids_imagens, tipo_formato):
    st.write(f"Iniciando a preparação do arquivo **{tipo_formato.upper()}**...")
    with st.spinner("Processando dados e codificando arquivo..."):
        try:
            cache = preparar_arquivo_exportacao(ids_imagens, tipo_formato)
            st.success(f"Arquivo **{tipo_formato.upper()}** preparado com sucesso ({cache['total_rows']:,} linhas em {cache['elapsed']}s)!")
            st.download_button(
                label=f"Clique aqui para Baixar {tipo_formato.upper()}",
                data=cache["file_data"],
                file_name=f"CELMM_Export_{datetime.date.today()}.{cache['file_ext']}",
                mime=cache["mime_type"],
                type="primary",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Erro na preparação do download: {e}")

if hasattr(st, "dialog"):
    import inspect
    sig = inspect.signature(st.dialog)
    dialog_kwargs = {"width": "large"} if "width" in sig.parameters else {}
    modal_exportar = st.dialog("Preparando Exportação de Dados", **dialog_kwargs)(exportar_conteudo_modal)
else:
    def modal_exportar(ids_imagens, tipo_formato):
        with st.expander("Preparação do Download", expanded=True):
            exportar_conteudo_modal(ids_imagens, tipo_formato)

st.set_page_config(page_title="CELMM | Prévia de Dados", page_icon="🛰️", layout="wide")

st.title("CELMM - Prévia de Dados")
st.caption("Visualização rápida das primeiras 500 linhas dos dados de pixels carregados da base de dados PostgreSQL.")
st.warning("⚠️ **Nota:** Os dados das bandas espectrais (B1 a B12) são mantidos e exibidos em valores brutos de **Número Digital (DN)**.")
st.divider()

if "df_pixels_carregados" not in st.session_state or st.session_state["df_pixels_carregados"] is None:
    st.warning("Nenhum dado carregado na sessão para visualização.")
    if st.button("Voltar para Exportador", type="primary", use_container_width=True, key="btn_voltar_no_data"):
        st.switch_page("views/05.CELMM_VISUALIZAR_DADOS.py")
else:
    df_pixels = st.session_state["df_pixels_carregados"]
    total_pixels = len(df_pixels)
    
    # Exclusão de colunas internas de banco e de controle de visualização
    colunas_para_excluir = ['id', 'metadados_imagem_id', 'data_registro', 'system_index', 'geo']
    colunas_visualizacao = [col for col in df_pixels.columns if col not in colunas_para_excluir]
    df_export = df_pixels[colunas_visualizacao]
    
    # Alinhamento do texto explicativo e botão de voltar à direita
    col_text, col_btn = st.columns([8.5, 3.5])
    with col_text:
        # Se carregamos parcial, o total real pode ser maior que o len do dataframe
        if st.session_state.get("carregado_parcial", True):
            st.write("Exibindo uma amostra rápida das primeiras **500** linhas dos dados (Modo Preview):")
        else:
            st.write(f"Exibindo uma amostra das primeiras **500** linhas de um total de **{total_pixels:,}** pixels carregados do banco:")
    with col_btn:
        if st.button("Voltar para Exportador", type="primary", use_container_width=True, key="btn_voltar_with_data"):
            st.switch_page("views/05.CELMM_VISUALIZAR_DADOS.py")
        
    st.dataframe(df_export.head(500), use_container_width=True)
    
    col_rgb, col_csv, col_xlsx = st.columns(3)
    
    with col_rgb:
        ids_carregados = st.session_state.get("ids_pixels_carregados", [])
        if len(ids_carregados) == 1:
            if st.button("Visualizar Cor Verdadeira", type="primary", use_container_width=True):
                st.switch_page("views/07.CELMM_VISUALIZACAO_RAPIDA.py")
        else:
            st.button("Visualizar Cor Verdadeira", type="primary", disabled=True, use_container_width=True, help="Selecione apenas 1 produto por vez para visualizar em Cor Verdadeira.")

    with col_csv:
        if st.button("Baixar em CSV", type="secondary", use_container_width=True):
            modal_exportar(st.session_state["ids_pixels_carregados"], 'csv')
            
    with col_xlsx:
        if st.button("Baixar em XLSX", type="secondary", use_container_width=True):
            modal_exportar(st.session_state["ids_pixels_carregados"], 'xlsx')
                

