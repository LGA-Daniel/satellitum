import streamlit as st
import pandas as pd
import numpy as np
from PIL import Image
import io

from modules.db import (
    obter_metadados_salvos,
    obter_df_raster_multibandas_cached
)
from modules.raster import (
    COMBINACOES_ESPECTRAIS,
    processar_matriz_combinacao
)

st.set_page_config(page_title="CELMM | Visualização em Carrossel", page_icon="🖼️", layout="wide")

# ==============================================================================
# 1. VERIFICAÇÃO DE SESSÃO & DADOS
# ==============================================================================
ids_selecionados = st.session_state.get("ids_pixels_carregados", [])

if not ids_selecionados:
    st.warning("⚠️ Nenhum conjunto de dados foi selecionado para visualização.")
    st.info("Por favor, selecione ao menos um produto na **Central de Gerenciamento** e abra a prévia de dados.")
    col_btn, _ = st.columns([3, 9])
    with col_btn:
        if st.button("Voltar ao Gerenciamento", type="primary", use_container_width=True):
            st.switch_page("views/08.CELMM_GESTAO_PRODUTOS.py")
    st.stop()

# Busca metadados cadastrados para popular as opções de seleção
todos_metadados = obter_metadados_salvos()
metadados_filtrados = [m for m in todos_metadados if m['id'] in ids_selecionados]

if not metadados_filtrados:
    st.error("Não foram encontrados os metadados correspondentes aos produtos selecionados.")
    if st.button("Voltar para Prévia de Dados", type="primary"):
        st.switch_page("views/06.CELMM_PREVIA_DADOS.py")
    st.stop()

# Ordena metadados por data crescente
df_meta_sel = pd.DataFrame(metadados_filtrados).sort_values(by='data', ascending=True)

# Combinações espectrais selecionadas
combinacoes_ativas = st.session_state.get("combinacoes_renderizacao", ["RGB_TRUE_COLOR"])
if not combinacoes_ativas:
    combinacoes_ativas = ["RGB_TRUE_COLOR"]

# ==============================================================================
# 2. PROCESSAMENTO MULTIDATAS & MULTIBANDAS EM CARROSSEL (500x400 PADRONIZADO)
# ==============================================================================
slides = []

with st.spinner("Renderizando matrizes raster padronizadas (500x400 px) para todas as datas..."):
    # Pré-carrega e calcula centro de referência comum para alinhamento espacial perfeito
    data_cache_pixels = {}
    all_lats_min, all_lats_max = [], []
    all_lons_min, all_lons_max = [], []

    for _, meta_row in df_meta_sel.iterrows():
        p_id = int(meta_row['id'])
        df_px = obter_df_raster_multibandas_cached(p_id)
        if not df_px.empty and 'latitude' in df_px.columns and 'longitude' in df_px.columns:
            data_cache_pixels[p_id] = df_px
            all_lats_min.append(df_px['latitude'].min())
            all_lats_max.append(df_px['latitude'].max())
            all_lons_min.append(df_px['longitude'].min())
            all_lons_max.append(df_px['longitude'].max())

    if all_lats_min and all_lats_max:
        global_center = (
            (min(all_lats_min) + max(all_lats_max)) / 2.0,
            (min(all_lons_min) + max(all_lons_max)) / 2.0
        )
    else:
        global_center = None

    for _, meta_row in df_meta_sel.iterrows():
        p_id = int(meta_row['id'])
        d_str = str(meta_row['data'])
        d_fmt = pd.to_datetime(meta_row['data']).strftime('%d/%m/%Y') if meta_row.get('data') else d_str
        sat_str = str(meta_row.get('satelite', 'Sentinel-2'))
        mgrs_str = str(meta_row.get('z_grade_mgrs', 'N/A'))
        px_val = int(meta_row.get('pixels_validos') or 0)
        
        df_pixels_img = data_cache_pixels.get(p_id)
        if df_pixels_img is None or df_pixels_img.empty:
            continue
            
        for comb_key in combinacoes_ativas:
            comb_info = COMBINACOES_ESPECTRAIS.get(comb_key, COMBINACOES_ESPECTRAIS["RGB_TRUE_COLOR"])
            try:
                matriz_rgba, dims = processar_matriz_combinacao(
                    df_pixels_img,
                    bandas=comb_info["bandas"],
                    max_val=comb_info.get("max_val", 3000.0),
                    target_width=500,
                    target_height=400,
                    center_coords=None
                )
                
                buf = io.BytesIO()
                img_pil = Image.fromarray((matriz_rgba * 255).astype('uint8'))
                img_pil.save(buf, format="PNG")
                
                slides.append({
                    "id": p_id,
                    "data_str": d_str,
                    "data_fmt": d_fmt,
                    "satelite": sat_str,
                    "mgrs": mgrs_str,
                    "pixels_validos": px_val,
                    "key": comb_key,
                    "nome": comb_info["nome"],
                    "descricao": comb_info["descricao"],
                    "bandas": comb_info["bandas"],
                    "matriz": matriz_rgba,
                    "png_bytes": buf.getvalue(),
                    "dims": dims
                })
            except Exception as e:
                st.warning(f"Erro ao renderizar {comb_info['nome']} para a data {d_fmt}: {e}")

if not slides:
    st.error("Falha ao gerar imagens para os produtos e combinações selecionados.")
    if st.button("Voltar para Prévia de Dados", type="primary"):
        st.switch_page("views/06.CELMM_PREVIA_DADOS.py")
    st.stop()

# ==============================================================================
# 3. CONTROLE DO ÍNDICE DO CARROSSEL
# ==============================================================================
if "carousel_index" not in st.session_state:
    st.session_state["carousel_index"] = 0

total_slides = len(slides)
if st.session_state["carousel_index"] >= total_slides:
    st.session_state["carousel_index"] = 0

idx_ativo = st.session_state["carousel_index"]
slide_ativo = slides[idx_ativo]

# ==============================================================================
# 4. CABEÇALHO & CARDS DE INFORMAÇÃO DA IMAGEM ATIVA
# ==============================================================================
col_title, col_btn_top = st.columns([8, 4], vertical_alignment="center")
with col_title:
    st.title("Visualização de Imagens")
with col_btn_top:
    if st.button("⬅️ Voltar para Prévia de Dados", type="secondary", use_container_width=True, key="btn_top_voltar_previa"):
        st.switch_page("views/06.CELMM_PREVIA_DADOS.py")

st.divider()

def card_destacado(label, value, title_tooltip=None):
    tooltip_attr = f'title="{title_tooltip}"' if title_tooltip else ""
    return f"""
        <div style="
            background-color: rgba(2, 132, 199, 0.08); 
            border: 1px solid rgba(2, 132, 199, 0.25); 
            border-radius: 8px; 
            padding: 10px 14px; 
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            margin-bottom: 12px;
            width: 100%;
        " {tooltip_attr}>
            <p style="margin: 0; font-size: 0.82em; font-weight: 500; color: var(--text-color); opacity: 0.8; text-align: center; width: 100%;">{label}</p>
            <div style="margin: 3px 0 0 0; font-size: 1.4em; color: var(--primary-color); font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; width: 100%;">{value}</div>
        </div>
    """

col_c1, col_c2, col_c3 = st.columns(3)
with col_c1:
    st.markdown(card_destacado("Data do Produto", slide_ativo['data_fmt']), unsafe_allow_html=True)
with col_c2:
    st.markdown(card_destacado("Satélite / Grade MGRS", f"{slide_ativo['satelite']} ({slide_ativo['mgrs']})", title_tooltip=f"{slide_ativo['satelite']} ({slide_ativo['mgrs']})"), unsafe_allow_html=True)
with col_c3:
    st.markdown(card_destacado("Total de Pixels Válidos", f"{slide_ativo['pixels_validos']:,}".replace(",", ".")), unsafe_allow_html=True)

# ==============================================================================
# 5. CONTROLES DO CARROSSEL
# ==============================================================================
col_prev, col_info_carrossel, col_next = st.columns([3, 6, 3], vertical_alignment="center")

with col_prev:
    if st.button("⬅️ Imagem Anterior", use_container_width=True, disabled=total_slides <= 1, key="btn_carousel_prev"):
        st.session_state["carousel_index"] = (idx_ativo - 1) % total_slides
        st.rerun()

with col_info_carrossel:
    st.markdown(f"""
        <div style="text-align: center; background-color: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 6px 12px;">
            <div style="font-size: 1.05em; font-weight: 600; color: var(--primary-color);">
                📅 {slide_ativo['data_fmt']} &nbsp;•&nbsp; 🎨 {slide_ativo['nome']}
            </div>
            <div style="font-size: 0.82em; opacity: 0.70; margin-top: 2px;">
                Slide {idx_ativo + 1} de {total_slides} &nbsp;|&nbsp; {slide_ativo['descricao']}
            </div>
        </div>
    """, unsafe_allow_html=True)

with col_next:
    if st.button("Próxima Imagem ➡️", use_container_width=True, disabled=total_slides <= 1, key="btn_carousel_next"):
        st.session_state["carousel_index"] = (idx_ativo + 1) % total_slides
        st.rerun()

st.text("")

# ==============================================================================
# 6. EXIBIÇÃO DA IMAGEM ATIVA (OTIMIZADA PARA TELAS 1080P)
# ==============================================================================
col_left_space, col_img_center, col_right_space = st.columns([3, 6, 3])

with col_img_center:
    st.image(
        slide_ativo["matriz"], 
        use_container_width=True, 
        output_format="PNG",
        caption=f"{slide_ativo['nome']} ({slide_ativo['data_fmt']}) — {slide_ativo['dims'][1]} x {slide_ativo['dims'][0]} px"
    )

st.divider()

# ==============================================================================
# 7. BARRA INFERIOR DE AÇÕES: DOWNLOAD E NAVEGAÇÃO
# ==============================================================================
col_foot_sp1, col_dl, col_voltar, col_foot_sp2 = st.columns([3, 3, 3, 3])

nome_arquivo_png = f"Raster_{slide_ativo['key']}_{slide_ativo['data_str']}.png"

with col_dl:
    st.download_button(
        label=f"⬇️ Baixar Imagem Ativa ({slide_ativo['data_fmt']})",
        data=slide_ativo["png_bytes"],
        file_name=nome_arquivo_png,
        mime="image/png",
        type="primary",
        use_container_width=True,
        key=f"btn_dl_active_img_{idx_ativo}"
    )

with col_voltar:
    if st.button("⬅️ Voltar para Prévia de Dados", type="secondary", use_container_width=True, key="btn_bottom_voltar"):
        st.switch_page("views/06.CELMM_PREVIA_DADOS.py")
