import streamlit as st
import pandas as pd
import datetime
from modules.core import obter_metadados_salvos

st.set_page_config(page_title="CELMM | Visualizar Metadados", page_icon="📊", layout="wide")

st.title("CELMM - Visualizar Metadados")
st.divider()

# Busca os dados no banco
dados = obter_metadados_salvos()

if not dados:
    st.info("Nenhum metadado foi encontrado no banco de dados.")
    st.markdown("""
    Para popular o banco:
    1. Vá para a página **CELMM - Analisar Metadados** no menu lateral.
    2. Realize uma busca no Google Earth Engine.
    3. Clique no botão **Salvar no Banco de Dados** que aparecerá abaixo dos resultados.
    """)
else:
    # Transforma em DataFrame
    df = pd.DataFrame(dados)
    
    # Conversões e ordenação
    df['data'] = pd.to_datetime(df['data']).dt.date
    df = df.sort_values(by='data', ascending=False)

    # 1. Filtros no Expander no topo da página
    with st.expander("Filtros", expanded=True):
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            # Filtro de Satélite
            satelites_disponiveis = df['satelite'].unique().tolist()
            satelites_selecionados = st.multiselect(
                "Satélite",
                options=satelites_disponiveis,
                default=satelites_disponiveis
            )

            # Filtro de Grade MGRS
            grades_disponiveis = df['z_grade_mgrs'].dropna().unique().tolist()
            grades_selecionadas = st.multiselect(
                "Grade MGRS",
                options=grades_disponiveis,
                default=grades_disponiveis
            )

        with col_f2:
            # Filtro de Tamanho de Pixel (Seleção Única)
            pixels_disponiveis = sorted(df['tamanho_pixel'].unique().tolist())
            opcoes_pixel = [int(p) for p in pixels_disponiveis]
            pixel_selecionado = st.selectbox(
                "Tamanho do Pixel (m)",
                options=opcoes_pixel,
                index=0
            )

            # Filtro de Período
            data_min = df['data'].min()
            data_max = df['data'].max()
            
            if data_min == data_max:
                data_inicio = data_min
                data_fim = data_max
                st.info(f"Período de datas disponível: {data_min}")
            else:
                periodo = st.date_input(
                    "Período",
                    value=(data_min, data_max),
                    min_value=data_min,
                    max_value=data_max
                )
                if isinstance(periodo, tuple) and len(periodo) == 2:
                    data_inicio, data_fim = periodo
                else:
                    data_inicio, data_fim = data_min, data_max

        # Filtro de Intervalo de Pixels Válidos (Slider de Intervalo)
        min_pixels_val = int(df['pixels_validos'].min())
        max_pixels_val = int(df['pixels_validos'].max())
        
        if min_pixels_val < max_pixels_val:
            pixels_range = st.slider(
                "Pixels Válidos",
                min_value=min_pixels_val,
                max_value=max_pixels_val,
                value=(min_pixels_val, max_pixels_val)
            )
        else:
            pixels_range = (min_pixels_val, max_pixels_val)

    # Filtro de tamanho de pixel
    filtro_pixel = df['tamanho_pixel'] == int(pixel_selecionado)

    # Aplicação dos filtros
    df_filtrado = df[
        (df['satelite'].isin(satelites_selecionados)) &
        (df['z_grade_mgrs'].isin(grades_selecionadas)) &
        filtro_pixel &
        (df['data'] >= data_inicio) &
        (df['data'] <= data_fim) &
        (df['pixels_validos'] >= pixels_range[0]) &
        (df['pixels_validos'] <= pixels_range[1])
    ]

    # 2. Seção de Indicadores Gerais
    if not df_filtrado.empty:
        total_imagens = len(df_filtrado)
        
        # Encontra o maior valor de pixels válidos
        max_pixels = int(df_filtrado['pixels_validos'].max())
        
        # Filtra todas as linhas que têm esse valor máximo e extrai as datas únicas ordenadas
        df_max = df_filtrado[df_filtrado['pixels_validos'] == max_pixels]
        datas_max = sorted(df_max['data'].unique())
        
        # Junta todas as datas formatadas separadas por vírgula
        data_max_pixels = ", ".join([d.strftime('%d/%m/%Y') for d in datas_max])
        
        # Contagem de zeros
        contagem_zeros = int((df_filtrado['pixels_validos'] == 0).sum())
        
        # Cálculo de aproveitamento baseando-se no maior valor do período
        if max_pixels > 0:
            aproveitamento = df_filtrado['pixels_validos'] / max_pixels
            contagem_50 = int((aproveitamento >= 0.50).sum())
            contagem_75 = int((aproveitamento >= 0.75).sum())
        else:
            contagem_50 = 0
            contagem_75 = 0
    else:
        total_imagens = 0
        max_pixels = 0
        data_max_pixels = "N/A"
        contagem_zeros = 0
        contagem_50 = 0
        contagem_75 = 0

    st.subheader("Estatística Básica")
    st.text("")
    col1, col2, col3 = st.columns(3)
    
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

    with col1:
        st.markdown(card_destacado("Total de Imagens", str(total_imagens)), unsafe_allow_html=True)
        st.markdown(card_destacado("Imagens Nulas", str(contagem_zeros)), unsafe_allow_html=True)
    with col2:
        st.markdown(card_destacado("Máximo Pixels", f"{max_pixels:,}"), unsafe_allow_html=True)
        st.markdown(card_destacado("Imagens com Aproveitamento ≥ 50%", str(contagem_50)), unsafe_allow_html=True)
    with col3:
        st.markdown(card_destacado("Melhor Imagem", data_max_pixels, title_tooltip=data_max_pixels), unsafe_allow_html=True)
        st.markdown(card_destacado("Imagens com Aproveitamento ≥ 75%", str(contagem_75)), unsafe_allow_html=True)

    st.divider()

    st.subheader("Metadados Salvos")
    st.text("")
    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
       
        # Renomeia as colunas para exibição amigável
        df_exibicao = df_filtrado[[
            'id', 'data', 'satelite', 'z_grade_mgrs', 'tamanho_pixel', 'pixels_validos', 'data_registro'
        ]].rename(columns={
            'id': 'ID',
            'data': 'Data da Imagem',
            'satelite': 'Satélite',
            'z_grade_mgrs': 'Grade MGRS',
            'tamanho_pixel': 'Tamanho Pixel (m)',
            'pixels_validos': 'Pixels Válidos',
            'data_registro': 'Data de Gravação'
        })
        
        # Exibe a tabela interativa
        st.dataframe(df_exibicao, use_container_width=True)