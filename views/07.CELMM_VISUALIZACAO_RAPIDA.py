import streamlit as st
import pandas as pd
from modules.db import (
    obter_metadados_salvos,
    obter_df_raster_cor_verdadeira_cached
)
from modules.raster import processar_matriz_cor_verdadeira
from PIL import Image
import io

st.set_page_config(page_title="CELMM | Visualização Rápida (RGB)", page_icon="🖼️", layout="wide")

st.title("Visualização em Cor Verdadeira")

st.markdown("<br>", unsafe_allow_html=True)

st.divider()

# Recupera IDs das imagens selecionadas no session_state
ids_selecionados = st.session_state.get("ids_pixels_carregados", [])

if not ids_selecionados:
    st.warning("⚠️ Nenhum conjunto de dados foi selecionado para visualização.")
    st.info("Por favor, selecione ao menos um produto na tabela da aplicação **CELMM - Visualizar e Exportar Dados** e clique no botão **Visualizar Cor Verdadeira**.")
    col_btn, _ = st.columns([3, 9])
    with col_btn:
        if st.button("Voltar para Exportador de Dados", type="primary", use_container_width=True):
            st.switch_page("views/05.CELMM_VISUALIZAR_DADOS.py")
    st.stop()

# Busca metadados cadastrados para popular as opções de seleção
todos_metadados = obter_metadados_salvos()
metadados_filtrados = [m for m in todos_metadados if m['id'] in ids_selecionados]

if not metadados_filtrados:
    st.error("Não foram encontrados os metadados correspondentes aos IDs selecionados.")
    st.stop()

# Como apenas 1 conjunto de dados pode ser selecionado por vez, pega o primeiro ID
id_imagem_ativa = ids_selecionados[0]
meta_ativo = next((m for m in metadados_filtrados if m['id'] == id_imagem_ativa), metadados_filtrados[0])

# Consulta com cache no banco
with st.spinner("Carregando coordenadas e bandas (B4, B3, B2) do Banco de Dados..."):
    df_pixels = obter_df_raster_cor_verdadeira_cached(id_imagem_ativa)

if df_pixels.empty:
    st.error("Nenhum dado de pixel encontrado no banco de dados para a imagem selecionada.")
    st.stop()

# Processamento da matriz raster utilizando o módulo dedicado
rgb_matriz, (altura_px, largura_px) = processar_matriz_cor_verdadeira(df_pixels)

# Função para renderizar cards padronizados do sistema (idênticos às views 2 e 5)
def card_destacado(label, value, title_tooltip=None):
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
            margin-bottom: 15px;
            width: 100%;
        " {tooltip_attr}>
            <p style="margin: 0; font-size: 0.85em; font-weight: 500; color: var(--text-color); opacity: 0.8; text-align: center; width: 100%;">{label}</p>
            <div style="margin: 4px 0 0 0; font-size: 1.6em; color: var(--primary-color); font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; width: 100%;">{value}</div>
        </div>
    """

# Métricas do Produto (Cards Padronizados)
col_c1, col_c2, col_c3 = st.columns(3)
with col_c1:
    st.markdown(card_destacado("Total de Pixels", f"{len(df_pixels):,}".replace(",", ".")), unsafe_allow_html=True)
with col_c2:
    st.markdown(card_destacado("Data do Produto", str(meta_ativo['data'])), unsafe_allow_html=True)
with col_c3:
    st.markdown(card_destacado("Satélite / MGRS", f"{meta_ativo['satelite']} ({meta_ativo.get('z_grade_mgrs', 'N/A')})", title_tooltip=f"{meta_ativo['satelite']} ({meta_ativo.get('z_grade_mgrs', 'N/A')})"), unsafe_allow_html=True)

st.divider()

# Exibição do Raster em Streamlit

col1, col_img, col_3 = st.columns([1, 10, 1])

with col_img:
    st.image(rgb_matriz, width=1024, output_format="PNG")

buf = io.BytesIO()
Image.fromarray((rgb_matriz * 255).astype('uint8')).save(buf, format="PNG")
# Cria o botão de download


st.divider()
col_nav1, col_nav2, col_nav3 = st.columns([6, 3, 3])
with col_nav2:
    st.download_button(
        "Baixar Imagem", 
        data=buf.getvalue(), 
        file_name=f"Raster_RGB_{meta_ativo['data']}.png", 
        mime="image/png", 
        type="secondary", 
        use_container_width=True
    )
with col_nav3:
    if st.button("Voltar", type="primary", use_container_width=True):
        st.switch_page("views/06.CELMM_PREVIA_DADOS.py")
