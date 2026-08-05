import streamlit as st
import pandas as pd
from modules.db import (
    obter_metadados_salvos,
    obter_df_raster_cor_verdadeira_cached
)
from modules.raster import processar_matriz_cor_verdadeira

st.set_page_config(page_title="CELMM | Visualização Rápida (RGB)", page_icon="🖼️", layout="wide")

st.title("Visualização de Dados")
st.divider()

# Botões de Navegação no Topo
col_nav1, col_nav2 = st.columns(2)
with col_nav1:
    if st.button("⬅️ Voltar para Exportador de Dados", type="secondary", use_container_width=True):
        st.switch_page("views/05.CELMM_VISUALIZAR_DADOS.py")
with col_nav2:
    if st.button("📋 Voltar para Prévia de Dados", type="secondary", use_container_width=True):
        st.switch_page("views/06.CELMM_PREVIA_DADOS.py")

st.markdown("<br>", unsafe_allow_html=True)

# Recupera IDs das imagens selecionadas no session_state
ids_selecionados = st.session_state.get("ids_pixels_carregados", [])

if not ids_selecionados:
    st.warning("⚠️ Nenhum conjunto de dados foi selecionado para visualização.")
    st.info("Por favor, selecione ao menos um produto na tabela da aplicação **CELMM - Visualizar e Exportar Dados** e clique no botão **Visualizar Cor Verdadeira**.")
    if st.button("Ir para o Exportador de Dados", type="primary", use_container_width=True):
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
with st.spinner("Carregando coordenadas e bandas (B4, B3, B2) do PostgreSQL..."):
    df_pixels = obter_df_raster_cor_verdadeira_cached(id_imagem_ativa)

if df_pixels.empty:
    st.error("Nenhum dado de pixel encontrado no banco de dados para a imagem selecionada.")
    st.stop()

# Processamento da matriz raster utilizando o módulo dedicado
rgb_matriz, (altura_px, largura_px) = processar_matriz_cor_verdadeira(df_pixels)

# Métricas do Produto
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric("Dimensão do Raster", f"{largura_px} × {altura_px} px")
with col_m2:
    st.metric("Total de Pixels", f"{len(df_pixels):,}".replace(",", "."))
with col_m3:
    st.metric("Data do Produto", str(meta_ativo['data']))
with col_m4:
    st.metric("Satélite / MGRS", f"{meta_ativo['satelite']} ({meta_ativo.get('z_grade_mgrs', 'N/A')})")

st.divider()

# Exibição do Raster em Streamlit
st.subheader("Visualização em Cor Verdadeira (B4-B3-B2)")
st.image(rgb_matriz, caption=f"Raster Cor Verdadeira - {meta_ativo['data']} ({largura_px}x{altura_px}px)", use_container_width=True)
