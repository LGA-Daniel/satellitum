import streamlit as st
import pandas as pd
import datetime
import io
from modules.core import (
    obter_metadados_salvos,
    obter_ids_imagens_com_pixels,
    obter_df_pixels_por_imagem_ids,
    obter_df_pixels_por_imagem_ids_generator
)

def exportar_conteudo_modal(ids_imagens, tipo_formato):
    # Prepara uma chave única e estável para cachear o processamento do download
    import hashlib
    ids_hash = hashlib.md5(str(sorted(ids_imagens)).encode()).hexdigest()
    export_key = f"export_cache_{tipo_formato}_{ids_hash}"
    
    # Se o arquivo já foi processado nesta sessão, exibe o download diretamente
    if export_key in st.session_state:
        cache = st.session_state[export_key]
        st.write(f"Arquivo **{tipo_formato.upper()}** pronto!")
        progresso = st.progress(1.0, text="Concluído!")
        elapsed_placeholder = st.empty()
        elapsed_placeholder.markdown(f"**Tempo decorrido:** {cache['elapsed']}s | **Total carregado:** {cache['total_rows']:,} linhas")
        st.success(f"Arquivo com {cache['total_rows']:,} pixels recuperado do cache com sucesso!")
        st.download_button(
            label=f"Baixar {tipo_formato.upper()}",
            data=cache["file_data"],
            file_name=f"CELMM_Export_{datetime.date.today()}.{cache['file_ext']}",
            mime=cache["mime_type"],
            type="primary",
            use_container_width=True
        )
        return

    st.write(f"Iniciando a preparação do arquivo **{tipo_formato.upper()}**...")
    progresso = st.progress(0.0, text="Aguardando...")
    elapsed_placeholder = st.empty()
    
    import time
    start_time = time.time()
    
    elapsed_placeholder.markdown("**Tempo decorrido:** 0s | **Registros carregados:** 0")
    
    chunks = []
    total_rows = 0
    generator = obter_df_pixels_por_imagem_ids_generator(ids_imagens, chunksize=50000)
    
    progresso.progress(0.1, text="Consultando banco de dados...")
    
    for chunk in generator:
        chunks.append(chunk)
        total_rows += len(chunk)
        elapsed = int(time.time() - start_time)
        elapsed_placeholder.markdown(f"**Tempo decorrido:** {elapsed}s | **Registros carregados:** {total_rows:,}")
        # Progresso dinâmico simples limitado a 50% para a etapa de banco de dados
        progresso.progress(
            min(0.1 + (total_rows / 1000000) * 0.4, 0.5),
            text=f"Carregando dados do banco: {total_rows:,} registros..."
        )
        
    if not chunks:
        st.error("Erro: Nenhum dada de pixel encontrado para as imagens selecionadas.")
        st.stop()
        
    df_pixels = pd.concat(chunks, ignore_index=True)
    
    elapsed = int(time.time() - start_time)
    elapsed_placeholder.markdown(f"**Tempo decorrido:** {elapsed}s | **Total carregado:** {total_rows:,} linhas")
    progresso.progress(0.6, text="Formatando dados (removendo colunas de controle)...")
    
    # Passo 2: Limpar colunas
    colunas_para_excluir = ['id', 'metadados_imagem_id', 'data_registro']
    colunas_exportaveis = [col for col in df_pixels.columns if col not in colunas_para_excluir]
    df_export = df_pixels[colunas_exportaveis]
    
    elapsed = int(time.time() - start_time)
    elapsed_placeholder.markdown(f"**Tempo decorrido:** {elapsed}s | **Total carregado:** {total_rows:,} linhas")
    progresso.progress(0.8, text=f"Codificando arquivo em {tipo_formato.upper()}...")
    
    # Passo 3: Converter formato
    if tipo_formato == 'csv':
        file_data = df_export.to_csv(index=False).encode('utf-8')
        mime_type = "text/csv"
        file_ext = "csv"
    else:
        excel_buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name="Pixels_CELMM")
            excel_buffer.seek(0)
            file_data = excel_buffer.getvalue()
        except ImportError:
            st.error("Erro: Suporte a Excel indisponível. Reconstrua a stack Docker (`docker compose up --build -d`).")
            st.stop()
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        file_ext = "xlsx"
        
    elapsed = int(time.time() - start_time)
    elapsed_placeholder.markdown(f"**Tempo decorrido:** {elapsed}s | **Total carregado:** {total_rows:,} linhas")
    progresso.progress(1.0, text="Concluído!")
    st.success(f"Arquivo com {total_rows:,} pixels preparado com sucesso em {elapsed}s!")
    
    # Salva no cache do session_state
    st.session_state[export_key] = {
        "file_data": file_data,
        "mime_type": mime_type,
        "file_ext": file_ext,
        "total_rows": total_rows,
        "elapsed": elapsed
    }
    
    st.download_button(
        label=f"Clique aqui para Baixar {tipo_formato.upper()}",
        data=file_data,
        file_name=f"CELMM_Export_{datetime.date.today()}.{file_ext}",
        mime=mime_type,
        type="primary",
        use_container_width=True
    )

if hasattr(st, "dialog"):
    modal_exportar = st.dialog("Preparando Exportação de Dados")(exportar_conteudo_modal)
else:
    def modal_exportar(ids_imagens, tipo_formato):
        with st.expander("Preparando Exportação de Dados", expanded=True):
            exportar_conteudo_modal(ids_imagens, tipo_formato)

st.set_page_config(page_title="CELMM | Visualizar e Exportar Dados", page_icon="🛰️", layout="wide")

st.title("CELMM - Visualizar e Exportar Dados")
st.caption("Visualização, análise e exportação de conjuntos de dados.")
st.divider()

# Busca os dados salvos no banco
with st.spinner("Buscando metadados no banco de dados..."):
    dados = obter_metadados_salvos()
    ids_com_pixels = obter_ids_imagens_com_pixels()

if not dados:
    st.info("Nenhum metadado de produto foi encontrado no banco de dados.")
    st.markdown("""
    Para popular o banco:
    1. Vá para a página **CELMM - Buscar Produtos** no menu lateral.
    2. Realize uma busca no Google Earth Engine.
    3. Clique no botão **Salvar no Banco de Dados** que aparecerá abaixo dos resultados.
    """)
else:
    # Transforma em DataFrame e filtra apenas imagens com pixels salvos no banco
    df = pd.DataFrame(dados)
    df = df[df['id'].isin(ids_com_pixels)]
    
    # Conversões e ordenação
    df['data'] = pd.to_datetime(df['data']).dt.date
    df = df.sort_values(by='data', ascending=False)

    # 1. Filtros no Expander
    with st.expander("Filtros de Produtos", expanded=True):
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

    # Aplicação dos filtros
    df_filtrado = df[
        (df['satelite'].isin(satelites_selecionados)) &
        (df['z_grade_mgrs'].isin(grades_selecionadas)) &
        (df['tamanho_pixel'] == int(pixel_selecionado)) &
        (df['data'] >= data_inicio) &
        (df['data'] <= data_fim)
    ]

    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
        # Seção de Estatísticas (Cards)
        total_importados = len(df)
        filtrados_count = len(df_filtrado)
        total_pixels_est = int(df_filtrado['pixels_validos'].sum())
        
        st.text("")
        col_c1, col_c2, col_c3 = st.columns(3)
        
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
            
        with col_c1:
            st.markdown(card_destacado("Produtos Disponíveis", f"{total_importados:,}".replace(",", ".")), unsafe_allow_html=True)
        with col_c2:
            st.markdown(card_destacado("Total de Pixels", f"{total_pixels_est:,}".replace(",", ".")), unsafe_allow_html=True)
        with col_c3:
            st.markdown(card_destacado("&nbsp;", "&nbsp;"), unsafe_allow_html=True)
        st.text("")

        # Checkbox para marcar todas por padrão
        selecionar_padrao = st.checkbox("Marcar todos", value=False)
        
        df_display = df_filtrado.copy()
        df_display.insert(0, "Selecionar", selecionar_padrao)
        
        # Prepara exibição amigável
        df_to_edit = df_display[[
            'Selecionar', 'id', 'data', 'satelite', 'z_grade_mgrs', 'tamanho_pixel', 'pixels_validos'
        ]].rename(columns={
            'data': 'Data do Produto',
            'satelite': 'Satélite',
            'z_grade_mgrs': 'Grade MGRS',
            'tamanho_pixel': 'Tamanho Pixel (m)',
            'pixels_validos': 'Pixels Válidos (Metadata)'
        })
        
        # Tabela interativa
        edited_df = st.data_editor(
            df_to_edit,
            hide_index=True,
            column_config={
                "Selecionar": st.column_config.CheckboxColumn(
                    "Selecionar",
                    help="Selecione para visualizar/exportar os pixels desta data",
                    default=selecionar_padrao
                ),
                "id": None, # Oculta coluna ID
                "Data do Produto": st.column_config.DateColumn("Data do Produto", format="YYYY-MM-DD", width="medium"),
                "Satélite": st.column_config.TextColumn("Satélite", width="small"),
                "Grade MGRS": st.column_config.TextColumn("Grade MGRS", width="small"),
                "Tamanho Pixel (m)": st.column_config.NumberColumn("Tamanho Pixel (m)", width="small"),
                "Pixels Válidos (Metadata)": st.column_config.NumberColumn("Pixels Válidos", width="medium")
            },
            disabled=[c for c in df_to_edit.columns if c != "Selecionar"],
            use_container_width=True
        )
        
        selected_rows = edited_df[edited_df["Selecionar"] == True]
        
        # Três colunas de botões de controle abaixo da tabela de seleção (Sempre visíveis no mesmo local)
        col_vis, col_csv, col_xlsx = st.columns(3)
        
        if selected_rows.empty:
            # Caso não haja nenhuma imagem válida selecionada, renderiza os botões desabilitados
            with col_vis:
                st.button("Visualizar Dados", type="primary", disabled=True, use_container_width=True, help="Selecione pelo menos uma data.", key="btn_vis_disabled")
            with col_csv:
                st.button("Baixar em CSV", type="secondary", disabled=True, use_container_width=True, help="Selecione pelo menos uma data.", key="btn_csv_disabled")
            with col_xlsx:
                st.button("Baixar em XLSX", type="secondary", disabled=True, use_container_width=True, help="Selecione pelo menos uma data.", key="btn_xlsx_disabled")
        else:
            # Pega a lista de IDs das imagens válidas selecionadas
            chaves_selecionadas = set()
            for idx, r in selected_rows.iterrows():
                chaves_selecionadas.add((
                    r['Data do Produto'],
                    r['Satélite'],
                    r['Grade MGRS'],
                    r['Tamanho Pixel (m)']
                ))
            
            # Filtra do df_filtrado original para obter os IDs corretos
            ids_imagens = df_filtrado[
                df_filtrado.apply(lambda row: (row['data'], row['satelite'], row['z_grade_mgrs'], row['tamanho_pixel']) in chaves_selecionadas, axis=1)
            ]['id'].tolist()
            
            # Inicialização de estado para os dados de pixels carregados
            if "df_pixels_carregados" not in st.session_state:
                st.session_state["df_pixels_carregados"] = None
            if "ids_pixels_carregados" not in st.session_state:
                st.session_state["ids_pixels_carregados"] = []
            if "mostrar_tabela" not in st.session_state:
                st.session_state["mostrar_tabela"] = False
            if "carregado_parcial" not in st.session_state:
                st.session_state["carregado_parcial"] = True
                
            # Se a seleção mudar, limpa os dados salvos anteriormente no estado
            if set(ids_imagens) != set(st.session_state["ids_pixels_carregados"]):
                st.session_state["df_pixels_carregados"] = None
                st.session_state["ids_pixels_carregados"] = []
                st.session_state["mostrar_tabela"] = False
                st.session_state["carregado_parcial"] = True
                
                # Limpa chaves do cache de exportação para evitar vazamento de memória
                chaves_cache = [k for k in st.session_state.keys() if k.startswith("export_cache_")]
                for k in chaves_cache:
                    del st.session_state[k]
            
            # Usamos os mesmos containers de colunas criados anteriormente
            
            with col_vis:
                if st.button("Visualizar Dados", type="primary", use_container_width=True, key="btn_vis_enabled"):
                    # Se não carregou o preview, carrega agora
                    if st.session_state["df_pixels_carregados"] is None:
                        with st.spinner("Buscando pixels (preview) na base de dados..."):
                            df_pixels = obter_df_pixels_por_imagem_ids(ids_imagens, limit=500)
                            st.session_state["df_pixels_carregados"] = df_pixels
                            st.session_state["ids_pixels_carregados"] = ids_imagens
                            st.session_state["carregado_parcial"] = True
                    st.switch_page("views/06.CELMM_PREVIA_DADOS.py")
                    
            with col_csv:
                if st.button("Baixar em CSV", type="secondary", use_container_width=True, key="btn_csv_enabled"):
                    modal_exportar(ids_imagens, 'csv')
                    
            with col_xlsx:
                if st.button("Baixar em XLSX", type="secondary", use_container_width=True, key="btn_xlsx_enabled"):
                    modal_exportar(ids_imagens, 'xlsx')
