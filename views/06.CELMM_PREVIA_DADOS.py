import datetime
import streamlit as st
import pandas as pd
import inspect
from modules.db import (
    obter_metadados_salvos,
    obter_amostra_pixels_por_imagem_ids
)
from modules.data_export import preparar_arquivo_exportacao, limpar_arquivos_exportacao_disco
from modules.raster import COMBINACOES_ESPECTRAIS

st.set_page_config(page_title="CELMM | Prévia de Dados", page_icon="🛰️", layout="wide")

# Função auxiliar para cards de métricas no padrão visual do sistema
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
            <div style="margin: 4px 0 0 0; font-size: 1.5em; color: var(--primary-color); font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; width: 100%;">{value}</div>
        </div>
    """

# ==============================================================================
# 1. CABEÇALHO DA TELA
# ==============================================================================
col_title, col_btn_top = st.columns([8.5, 3.5], vertical_alignment="center")
with col_title:
    st.title("Visualização de Produtos")
with col_btn_top:
    if st.button("⬅️ Voltar ao Gerenciamento", type="secondary", use_container_width=True, key="btn_top_voltar"):
        st.switch_page("views/08.CELMM_GESTAO_PRODUTOS.py")

st.warning("⚠️ **Nota:** Os dados das bandas espectrais (B1 a B12) são mantidos e exibidos em valores brutos de **Número Digital (DN)**.")
st.markdown("")

ids_carregados = st.session_state.get("ids_pixels_carregados", [])

# ==============================================================================
# 2. VALIDAÇÃO DE DADOS CARREGADOS
# ==============================================================================
if not ids_carregados:
    st.warning("⚠️ Nenhum conjunto de dados carregado na sessão para visualização.")
    st.info("Por favor, selecione ao menos um produto na tela de **Gerenciamento de Produtos Orbitais** e acesse a visualização.")
    if st.button("Voltar ao Gerenciamento de Produtos", type="primary", use_container_width=True, key="btn_voltar_no_data"):
        st.switch_page("views/08.CELMM_GESTAO_PRODUTOS.py")
    st.stop()

# Busca metadados dos produtos carregados
todos_metadados = obter_metadados_salvos()
metadados_selecionados = [m for m in todos_metadados if m['id'] in ids_carregados]

if not metadados_selecionados:
    st.error("Metadados não encontrados para os produtos selecionados.")
    st.stop()

# Ordena metadados por data crescente
df_meta_sel = pd.DataFrame(metadados_selecionados).sort_values(by='data', ascending=True)
meta_mais_antigo = df_meta_sel.iloc[0].to_dict()

# Busca as 50 primeiras linhas de cada imagem selecionada
if "df_pixels_carregados" not in st.session_state or st.session_state.get("df_pixels_carregados") is None:
    with st.spinner("Carregando amostra de 50 linhas por produto..."):
        df_pixels = obter_amostra_pixels_por_imagem_ids(ids_carregados, limit_por_imagem=50)
        st.session_state["df_pixels_carregados"] = df_pixels
else:
    df_pixels = st.session_state["df_pixels_carregados"]

# ==============================================================================
# 3. CARDS DE IDENTIFICAÇÃO DOS PRODUTOS
# ==============================================================================
total_produtos_sel = len(metadados_selecionados)
data_mais_antiga_fmt = pd.to_datetime(meta_mais_antigo['data']).strftime('%d/%m/%Y')
total_pixels_acumulado = sum([int(m.get('pixels_validos') or 0) for m in metadados_selecionados])

col_c1, col_c2, col_c3, col_c4 = st.columns(4)

if total_produtos_sel == 1:
    sat_mgrs = f"{meta_mais_antigo.get('satelite', 'N/A')} ({meta_mais_antigo.get('z_grade_mgrs', 'N/A')})"
    res_pixel = f"{int(meta_mais_antigo.get('tamanho_pixel', 10))} m"
    with col_c1:
        st.markdown(card_destacado("Data do Produto", data_mais_antiga_fmt), unsafe_allow_html=True)
    with col_c2:
        st.markdown(card_destacado("Satélite / Grade MGRS", sat_mgrs, title_tooltip=sat_mgrs), unsafe_allow_html=True)
    with col_c3:
        st.markdown(card_destacado("Tamanho do Pixel", res_pixel), unsafe_allow_html=True)
    with col_c4:
        st.markdown(card_destacado("Pixels Válidos", f"{total_pixels_acumulado:,}".replace(",", ".")), unsafe_allow_html=True)
else:
    data_mais_recente_fmt = pd.to_datetime(df_meta_sel.iloc[-1]['data']).strftime('%d/%m/%Y')
    periodo_str = f"{data_mais_antiga_fmt} a {data_mais_recente_fmt}"
    with col_c1:
        st.markdown(card_destacado("Produtos Selecionados", f"{total_produtos_sel} produtos"), unsafe_allow_html=True)
    with col_c2:
        st.markdown(card_destacado("Data Mais Antiga", data_mais_antiga_fmt), unsafe_allow_html=True)
    with col_c3:
        st.markdown(card_destacado("Período Coberto", periodo_str, title_tooltip=periodo_str), unsafe_allow_html=True)
    with col_c4:
        st.markdown(card_destacado("Total de Pixels (Conjunto)", f"{total_pixels_acumulado:,}".replace(",", ".")), unsafe_allow_html=True)

st.divider()

# ==============================================================================
# 4. TABELA DE AMOSTRA DOS PIXELS (50 LINHAS POR ARQUIVO)
# ==============================================================================
colunas_para_excluir = ['id', 'metadados_imagem_id', 'data_registro', 'system_index', 'geo']
colunas_visualizacao = [col for col in df_pixels.columns if col not in colunas_para_excluir]
df_export = df_pixels[colunas_visualizacao]

if total_produtos_sel == 1:
    st.markdown(f"#### 📋 Amostra de Dados")
    st.caption("50 primeiras linhas")
else:
    st.markdown(f"#### 📋 Amostra de Dados")
    st.caption(f"50 primeiras linhas de cada um dos {total_produtos_sel} arquivos")

st.dataframe(df_export, use_container_width=True)

st.divider()

# ==============================================================================
# 5. DIÁLOGO MODAL: SELEÇÃO DE RENDERIZAÇÃO DE IMAGENS
# ==============================================================================
def dialog_selecionar_renderizacao_impl():
    st.markdown(f"Configuração para renderização de imagens orbitais para **{total_produtos_sel} produto(s)** selecionado(s):")
    
    opcoes_comb = list(COMBINACOES_ESPECTRAIS.keys())
    
    selecionados = st.multiselect(
        "Combinações Espectrais para Renderizar",
        options=opcoes_comb,
        format_func=lambda k: COMBINACOES_ESPECTRAIS[k]["nome"],
        default=["RGB_TRUE_COLOR"],
        help="Cada produto selecionado será processado para cada combinação escolhida e disponibilizado no carrossel."
    )
    
    for k in selecionados:
        st.caption(f"🔹 **{COMBINACOES_ESPECTRAIS[k]['nome']}**: {COMBINACOES_ESPECTRAIS[k]['descricao']}")
        
    total_imagens_geradas = len(selecionados) * total_produtos_sel
    st.info(f"📊 Total de imagens no carrossel: **{total_imagens_geradas}** ({total_produtos_sel} data(s) × {len(selecionados)} combinação(ões)).")
    
    st.markdown("---")
    col_dlg_btn1, col_dlg_btn2 = st.columns([6, 4])
    with col_dlg_btn2:
        if st.button("🖼️ Processar e Visualizar", type="primary", use_container_width=True, disabled=len(selecionados) == 0):
            st.session_state["combinacoes_renderizacao"] = selecionados
            st.session_state["show_render_modal"] = False
            st.session_state["carousel_index"] = 0
            st.switch_page("views/07.CELMM_VISUALIZACAO_RAPIDA.py")

sig_dialog = inspect.signature(st.dialog)
dialog_kwargs = {"width": "large"} if "width" in sig_dialog.parameters else {}

if 'on_dismiss' in sig_dialog.parameters:
    @st.dialog("🖼️ Configurar Visualização de Imagens", on_dismiss=lambda: st.session_state.update({'show_render_modal': False}), **dialog_kwargs)
    def render_config_dialog():
        dialog_selecionar_renderizacao_impl()
else:
    @st.dialog("🖼️ Configurar Visualização de Imagens", dismissible=True, **dialog_kwargs)
    def render_config_dialog():
        dialog_selecionar_renderizacao_impl()

if st.session_state.get('show_render_modal', False):
    render_config_dialog()

# ==============================================================================
# 6. SEÇÕES DE AÇÃO INFERIORES: EXPORTAÇÃO (IDÊNTICA À CENTRAL) E IMAGENS
# ==============================================================================
col_act1, col_act2 = st.columns(2)

with col_act1:
    # AÇÃO: Renderização de Imagens
    with st.container(border=True):
        st.markdown(f"""
            <div style="min-height: 80px; margin-bottom: 8px;">
                <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">🖼️ Visualização em Imagem</h4>
                <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Renderizar imagens combinando bandas dos produtos.</p>
            </div>
        """, unsafe_allow_html=True)
        if st.button("Configurar e Visualizar Imagens", type="primary", use_container_width=True, key="btn_abrir_render_modal"):
            st.session_state['show_render_modal'] = True
            st.rerun()

with col_act2:
    # AÇÃO: Exportar Dados (Idêntico à Central de Ações)
    formato_in_place = st.session_state.get('previa_export_in_place_formato')
    with st.container(border=True):
        st.markdown(f"""
            <div style="min-height: 80px; margin-bottom: 8px;">
                <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">📊 Exportar Dados ({total_produtos_sel} Produtos)</h4>
                <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Exportar todos os pixels dos {total_produtos_sel} produtos selecionados em arquivo único CSV ou planilha Excel.</p>
            </div>
        """, unsafe_allow_html=True)
        
        if formato_in_place:
            with st.spinner(f"Processando e gravando {formato_in_place.upper()}..."):
                try:
                    cache = preparar_arquivo_exportacao(ids_carregados, formato_in_place)
                    col_dl, col_reset = st.columns([5, 5])
                    with col_dl:
                        with open(cache["file_path"], "rb") as f_exp:
                            st.download_button(
                                label=f"⬇️ Baixar {formato_in_place.upper()} ({cache['file_size_mb']} MB)",
                                data=f_exp,
                                file_name=cache["file_name"],
                                mime=cache["mime_type"],
                                type="primary",
                                use_container_width=True,
                                key="btn_download_previa_inplace"
                            )
                    with col_reset:
                        if st.button("🔄 Alternar formato", help="Alternar formato de exportação", use_container_width=True, key="btn_reset_previa_export"):
                            del st.session_state['previa_export_in_place_formato']
                            limpar_arquivos_exportacao_disco()
                            st.rerun()
                except Exception as e:
                    st.error(f"Erro na exportação: {e}")
        else:
            col_btn_csv, col_btn_xlsx = st.columns(2)
            with col_btn_csv:
                if st.button("📄 Gerar CSV", type="secondary", use_container_width=True, key="btn_previa_export_csv"):
                    st.session_state['previa_export_in_place_formato'] = 'csv'
                    st.rerun()
            with col_btn_xlsx:
                if st.button("📊 Gerar Excel", type="secondary", use_container_width=True, key="btn_previa_export_xlsx"):
                    st.session_state['previa_export_in_place_formato'] = 'xlsx'
                    st.rerun()
