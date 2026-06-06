import streamlit as st
import pandas as pd
import datetime
from modules.core import obter_metadados_salvos

st.set_page_config(page_title="CELMM | Visualizar Metadados", page_icon="📊", layout="wide")

st.title("CELMM - Visualização de Metadados")
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
    with st.expander("Filtros", expanded=False):
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
    col1, col2, col3 = st.columns(3)
    
    if not df_filtrado.empty:
        total_imagens = len(df_filtrado)
        
        # Encontra o maior valor de pixels válidos
        max_pixels = int(df_filtrado['pixels_validos'].max())
        
        # Filtra todas as linhas que têm esse valor máximo e extrai as datas únicas ordenadas
        df_max = df_filtrado[df_filtrado['pixels_validos'] == max_pixels]
        datas_max = sorted(df_max['data'].unique())
        
        # Junta todas as datas formatadas separadas por vírgula
        data_max_pixels = ", ".join([d.strftime('%d/%m/%Y') for d in datas_max])
    else:
        total_imagens = 0
        max_pixels = 0
        data_max_pixels = "N/A"

    with col1:
        st.metric(label="Total de Imagens", value=total_imagens)
    with col2:
        st.metric(label="Máximo de Pixels Válidos", value=f"{max_pixels:,}")
    with col3:
        st.metric(label="Data do Máximo", value=data_max_pixels)

    st.divider()

    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
        # 3. Gráfico de Evolução Temporal
        try:
            # Agrupa por data obtendo o valor máximo de pixels válidos por dia
            df_grafico = df_filtrado.groupby('data')['pixels_validos'].max().sort_index()
            st.line_chart(df_grafico)
        except Exception as e:
            st.warning(f"Não foi possível gerar o gráfico temporal: {e}")

        st.divider()

        # 4. Histograma de Pixels Válidos
        st.subheader("Distribuição do Número de Imagens por Pixels Válidos")
        try:
            if len(df_filtrado) > 1 and df_filtrado['pixels_validos'].nunique() > 1:
                min_val = int(df_filtrado['pixels_validos'].min())
                max_val = int(df_filtrado['pixels_validos'].max())
                
                # Define os limites das 10 classes antes de gerar o histograma
                bin_edges = [min_val + i * (max_val - min_val) / 10 for i in range(11)]
                bin_edges = [int(edge) for edge in bin_edges]
                bin_edges = sorted(list(set(bin_edges))) # Remove duplicatas em intervalos estreitos
                
                if len(bin_edges) > 1:
                    # Agrupa os dados nas classes pré-definidas
                    binned_data = pd.cut(df_filtrado['pixels_validos'], bins=bin_edges, include_lowest=True).value_counts().sort_index()
                    
                    # Cria rótulos ordenados no eixo X (adicionando prefixo numérico para garantir a ordenação correta)
                    labels_hist = []
                    for i, idx in enumerate(binned_data.index):
                        left = int(idx.left)
                        right = int(idx.right)
                        labels_hist.append(f"{i+1:02d}) {left:,} a {right:,}")
                    
                    df_hist = pd.DataFrame({
                        "Número de Imagens": binned_data.values
                    }, index=labels_hist)
                    
                    st.bar_chart(df_hist)
                else:
                    st.info("Intervalo de pixels válidos muito estreito para criar classes.")
            else:
                # Fallback simples caso não haja variação nos valores
                valores_unicos = df_filtrado['pixels_validos'].value_counts()
                df_hist = pd.DataFrame({
                    "Número de Imagens": valores_unicos.values
                }, index=[f"{int(v):,} pixels" for v in valores_unicos.index])
                
                st.bar_chart(df_hist)
        except Exception as e:
            st.warning(f"Não foi possível gerar o histograma: {e}")

        st.divider()

        # 5. Tabela de Dados e Exportação
        
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

        # Botão de exportação para CSV
        csv = df_filtrado.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar Dados Filtrados (CSV)",
            data=csv,
            file_name=f"metadados_satellitum_{datetime.date.today()}.csv",
            mime="text/csv",
            type="secondary"
        )
