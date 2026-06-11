import streamlit as st
import pandas as pd
import datetime
import os
import shutil
from modules.core import obter_metadados_salvos, listar_arquivos_pasta_drive, baixar_arquivo_drive_para_disco, salvar_pixels_bulk, obter_ids_imagens_com_pixels

st.set_page_config(page_title="CELMM | Sincronizar Produtos", page_icon="🛰️", layout="wide")

st.title("CELMM - Sincronizar Produtos")
st.divider()

# Carregamento dos dados em paralelo com indicador visual
with st.spinner("Buscando Arquivos"):
    dados = obter_metadados_salvos()
    arquivos_drive = listar_arquivos_pasta_drive("CSV_Sentinel2")
    ids_com_pixels = obter_ids_imagens_com_pixels()

# Cria um set dos nomes dos arquivos no Drive para busca rápida O(1)
nomes_arquivos_drive = {arq.get('name') for arq in arquivos_drive if arq.get('name')}

# Define a pasta temporária para armazenar os arquivos CSV fisicamente no servidor
module_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(module_dir)
temp_dir = os.path.join(project_root, "temp_downloads")

def resetar_estado_processamento():
    """Reseta as flags de processamento no session_state para evitar que o modal abra automaticamente ao interagir com a página."""
    st.session_state["executar_processamento"] = False
    st.session_state["processamento_concluido"] = False
    if "logs_processamento" in st.session_state:
        try:
            del st.session_state["logs_processamento"]
        except KeyError:
            pass

def limpar_pasta_temporaria():
    """Apaga e recria de forma limpa a pasta de downloads temporários."""
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
    os.makedirs(temp_dir, exist_ok=True)

# Função contendo a lógica de download e compactação
def baixar_arquivos_conteudo(valid_selected, map_nome_id):
    st.write(f"Você selecionou **{len(valid_selected)}** arquivo(s) disponível(is) para download.")
    
    with st.spinner("Baixando arquivos do Drive diretamente para o disco do servidor..."):
        try:
            limpar_pasta_temporaria()
            files_downloaded = []
            
            for idx, row in valid_selected.iterrows():
                # Converte a data para string YYYY-MM-DD
                date_str = row["Data do Produto"].strftime('%Y-%m-%d') if isinstance(row["Data do Produto"], (datetime.date, datetime.datetime)) else str(row["Data do Produto"])
                nome_esperado = f"CELMM_Data_{date_str}_{int(row['Tamanho Pixel (m)'])}m.csv"
                fid = map_nome_id.get(nome_esperado)
                if fid:
                    dest_path = os.path.join(temp_dir, nome_esperado)
                    # Download streaming direto para disco
                    baixar_arquivo_drive_para_disco(fid, dest_path)
                    files_downloaded.append(dest_path)
            
            if not files_downloaded:
                st.warning("Nenhum arquivo correspondente encontrado no Drive.")
            elif len(files_downloaded) == 1:
                local_file_path = files_downloaded[0]
                filename = os.path.basename(local_file_path)
                
                with open(local_file_path, "rb") as f:
                    st.download_button(
                        label="Salvar Arquivo no Computador",
                        data=f,
                        file_name=filename,
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )
            else:
                # Cria arquivo ZIP no disco temporário
                import zipfile
                zip_filename = f"CELMM_CSVs_{datetime.date.today().strftime('%Y%m%d')}.zip"
                zip_path = os.path.join(temp_dir, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for filepath in files_downloaded:
                        zip_file.write(filepath, os.path.basename(filepath))
                        
                with open(zip_path, "rb") as f:
                    st.download_button(
                        label="Salvar Arquivo ZIP no Computador",
                        data=f,
                        file_name=zip_filename,
                        mime="application/zip",
                        type="primary",
                        use_container_width=True
                    )
        except Exception as e:
            st.error(f"Erro ao processar arquivos do Drive: {e}")

# Definição dinâmica do modal para suportar retrocompatibilidade do Streamlit
if hasattr(st, "dialog"):
    baixar_arquivos_modal = st.dialog("Baixar Arquivos do Google Drive 📥")(baixar_arquivos_conteudo)
else:
    def baixar_arquivos_modal(valid_selected, map_nome_id):
        with st.expander("Preparação do Download 📥", expanded=True):
            baixar_arquivos_conteudo(valid_selected, map_nome_id)

# Função contendo a lógica de processamento do CSV para o banco
def processar_csv_conteudo(valid_selected, map_nome_id):
    if st.session_state.get("executar_processamento"):
        # Impede reexecuções em reruns subsequentes
        st.session_state["executar_processamento"] = False
        
        import time
        logs = []
        st.write(f"Iniciando o processamento de **{len(valid_selected)}** arquivo(s) disponível(is).")
        progresso_geral = st.progress(0.0, text="Progresso Geral: 0%")
        status_geral = st.empty()
        
        for i, (idx, row) in enumerate(valid_selected.iterrows()):
            img_id = int(row['id'])
            date_str = row["Data do Produto"].strftime('%Y-%m-%d') if isinstance(row["Data do Produto"], (datetime.date, datetime.datetime)) else str(row["Data do Produto"])
            pixel_size = int(row['Tamanho Pixel (m)'])
            satelite = str(row['Satélite'])
            grade = str(row['Grade MGRS']) if pd.notna(row['Grade MGRS']) else None
            zenital = float(row['zenital']) if pd.notna(row['zenital']) else None
            
            nome_esperado = f"CELMM_Data_{date_str}_{pixel_size}m.csv"
            dest_path = os.path.join(temp_dir, nome_esperado)
            
            status_geral.info(f"**Produto {i+1} de {len(valid_selected)}:** `{nome_esperado}`")
            
            # Progress bar para as etapas deste produto
            barra_etapas = st.progress(0.0, text="Iniciando processamento do produto...")
            
            # 1. Download se necessário
            if not os.path.exists(dest_path):
                fid = map_nome_id.get(nome_esperado)
                if not fid:
                    logs.append(f"❌ Produto {date_str} ({pixel_size}m): Arquivo não encontrado no Google Drive.")
                    barra_etapas.empty()
                    continue
                barra_etapas.progress(0.1, text="Etapa 1/5: Baixando arquivo do Google Drive...")
                try:
                    baixar_arquivo_drive_para_disco(fid, dest_path)
                except Exception as e:
                    logs.append(f"❌ Produto {date_str} ({pixel_size}m): Erro ao baixar: {e}")
                    barra_etapas.empty()
                    continue
            
            # 2. Leitura e Ingestão via COPY
            if os.path.exists(dest_path):
                try:
                    # Passo A: Ler CSV completo
                    barra_etapas.progress(0.3, text="Etapa 2/5: Carregando arquivo CSV na memória...")
                    df = pd.read_csv(dest_path)
                    
                    # Passo B: Limpeza e formatação de colunas
                    barra_etapas.progress(0.5, text="Etapa 3/5: Realizando limpeza de dados e injeção de metadados...")
                    rename_dict = {
                        'system:index': 'system_index',
                        '.geo': 'geo'
                    }
                    df = df.rename(columns=rename_dict)
                    
                    df['metadados_imagem_id'] = img_id
                    df['data'] = date_str
                    df['satelite'] = satelite
                    df['z_grade_mgrs'] = grade
                    df['tamanho_pixel'] = pixel_size
                    df['zenital'] = zenital
                    
                    # Converte system_index de forma segura para string sem .0
                    def converter_system_index(val):
                        if pd.isna(val):
                            return ""
                        if isinstance(val, float):
                            if val.is_integer():
                                return str(int(val))
                            return str(val)
                        return str(val)
                    df['system_index'] = df['system_index'].apply(converter_system_index)
                    
                    # Passo C: Executar o COPY via core.py
                    barra_etapas.progress(0.7, text="Etapa 4/5: Transmitindo dados via COPY e resolvendo conflitos...")
                    inseridos = salvar_pixels_bulk(df)
                    logs.append(f"✅ Produto {date_str} ({pixel_size}m): {inseridos:,} pixels importados com sucesso.")
                    
                    # Passo D: Limpeza local
                    barra_etapas.progress(1.0, text="Etapa 5/5: Finalizando e limpando arquivos temporários locais...")
                    try:
                        os.remove(dest_path)
                    except Exception:
                        pass
                        
                    st.success(f"Sucesso: {inseridos:,} pixels importados/atualizados para `{nome_esperado}`!")
                    
                except Exception as e:
                    logs.append(f"❌ Produto {date_str} ({pixel_size}m): Erro no processamento: {e}")
                
                # Aguarda meio segundo para exibição visual do estado de conclusão da etapa antes de limpar
                time.sleep(0.5)
                barra_etapas.empty()
                    
            progresso_geral.progress((i + 1) / len(valid_selected), text=f"Progresso Geral: {int((i + 1) / len(valid_selected) * 100)}%")
            
        st.session_state["logs_processamento"] = logs
        st.session_state["processamento_concluido"] = True
        st.rerun()

    # Tela final pós-processamento (estável e sem reexecução)
    if st.session_state.get("processamento_concluido"):
        st.subheader("Processamento Concluído! 📋")
        for log in st.session_state.get("logs_processamento", []):
            if "✅" in log:
                st.success(log)
            else:
                st.error(log)
                


# Definição dinâmica do modal de processamento para suportar retrocompatibilidade do Streamlit
if hasattr(st, "dialog"):
    processar_csv_modal = st.dialog("Processar CSV para a Base de Dados ⚙️")(processar_csv_conteudo)
else:
    def processar_csv_modal(valid_selected, map_nome_id):
        with st.expander("Processamento de CSV ⚙️", expanded=True):
            processar_csv_conteudo(valid_selected, map_nome_id)


if not dados:
    st.info("Nenhum metadado foi encontrado no banco de dados.")
    st.markdown("""
    Para popular o banco:
    1. Vá para a página **CELMM - Processar Metadados** no menu lateral.
    2. Realize uma busca no Google Earth Engine.
    3. Clique no botão **Salvar no Banco de Dados** que aparecerá abaixo dos resultados.
    """)
else:
    # Transforma em DataFrame
    df = pd.DataFrame(dados)
    
    # Conversões e ordenação
    df['data'] = pd.to_datetime(df['data']).dt.date
    df = df.sort_values(by='data', ascending=False)

    # Adiciona a coluna de status correlacionando os registros com o set do Drive previamente
    def verificar_disponibilidade(row):
        nome_esperado = f"CELMM_Data_{row['data'].strftime('%Y-%m-%d')}_{int(row['tamanho_pixel'])}m.csv"
        return "Disponível ✅" if nome_esperado in nomes_arquivos_drive else "Não Encontrado ❌"
        
    df['Status no Drive'] = df.apply(verificar_disponibilidade, axis=1)
    df['Importado para o Banco'] = df['id'].apply(lambda x: "Salvo ✅" if x in ids_com_pixels else "Pendente ⏳")

    # 1. Filtros no Expander (Cópia exata do layout da página de baixar imagens)
    with st.expander("Filtros", expanded=True):
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            # Filtro de Satélite
            satelites_disponiveis = df['satelite'].unique().tolist()
            satelites_selecionados = st.multiselect(
                "Satélite",
                options=satelites_disponiveis,
                default=satelites_disponiveis,
                on_change=resetar_estado_processamento
            )

            # Filtro de Grade MGRS
            grades_disponiveis = df['z_grade_mgrs'].dropna().unique().tolist()
            grades_selecionadas = st.multiselect(
                "Grade MGRS",
                options=grades_disponiveis,
                default=grades_disponiveis,
                on_change=resetar_estado_processamento
            )

        with col_f2:
            # Filtro de Tamanho de Pixel (Seleção Única)
            pixels_disponiveis = sorted(df['tamanho_pixel'].unique().tolist())
            opcoes_pixel = [int(p) for p in pixels_disponiveis]
            pixel_selecionado = st.selectbox(
                "Tamanho do Pixel (m)",
                options=opcoes_pixel,
                index=0,
                on_change=resetar_estado_processamento
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
                    max_value=data_max,
                    on_change=resetar_estado_processamento
                )
                if isinstance(periodo, tuple) and len(periodo) == 2:
                    data_inicio, data_fim = periodo
                else:
                    data_inicio, data_fim = data_min, data_max

        # Filtro: Somente disponíveis no Drive (toggle)
        apenas_disponiveis = st.toggle("Somente disponíveis no Drive", value=False, on_change=resetar_estado_processamento)

        # Filtro de Intervalo de Pixels Válidos (Slider de Intervalo)
        min_pixels_val = int(df['pixels_validos'].min()) if not df.empty else 0
        max_pixels_val = int(df['pixels_validos'].max()) if not df.empty else 0
        
        if min_pixels_val < max_pixels_val:
            pixels_range = st.slider(
                "Pixels Válidos",
                min_value=min_pixels_val,
                max_value=max_pixels_val,
                value=(min_pixels_val, max_pixels_val),
                on_change=resetar_estado_processamento
            )
        else:
            pixels_range = (min_pixels_val, max_pixels_val)

    # Aplicação final dos filtros
    df_filtrado = df[
        (df['satelite'].isin(satelites_selecionados)) &
        (df['z_grade_mgrs'].isin(grades_selecionadas)) &
        (df['tamanho_pixel'] == int(pixel_selecionado)) &
        (df['data'] >= data_inicio) &
        (df['data'] <= data_fim) &
        (df['pixels_validos'] >= pixels_range[0]) &
        (df['pixels_validos'] <= pixels_range[1])
    ]

    # Aplica o filtro do toggle (Somente disponíveis no Drive)
    if apenas_disponiveis:
        df_filtrado = df_filtrado[df_filtrado['Status no Drive'] == "Disponível ✅"]

    st.text("")

    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
        # Adiciona caixa para controle rápido de marcação
        selecionar_padrao = st.checkbox("Marcar todas", value=False, on_change=resetar_estado_processamento)
        
        df_display = df_filtrado.copy()
        df_display.insert(0, "Selecionar", selecionar_padrao)
        
        # Seleciona e renomeia as colunas para exibição amigável
        df_to_edit = df_display[[
            'Selecionar', 'id', 'data', 'satelite', 'z_grade_mgrs', 'tamanho_pixel', 'pixels_validos', 'zenital', 'Status no Drive', 'Importado para o Banco'
        ]].rename(columns={
            'data': 'Data do Produto',
            'satelite': 'Satélite',
            'z_grade_mgrs': 'Grade MGRS',
            'tamanho_pixel': 'Tamanho Pixel (m)',
            'pixels_validos': 'Pixels Válidos'
        })
        
        # Mapeamento de nome de arquivo para ID do Drive
        map_nome_id = {arq.get('name'): arq.get('id') for arq in arquivos_drive if arq.get('name') and arq.get('id')}
        
        # Gera uma chave estável e única baseada nos filtros ativos
        filtro_str = f"{sorted(satelites_selecionados)}_{sorted(grades_selecionadas)}_{pixel_selecionado}_{data_inicio}_{data_fim}_{pixels_range}_{apenas_disponiveis}"
        editor_key = f"editor_drive_{hash(filtro_str)}"
        
        # Exibe a lista interativa com caixa de seleção (checkbox) por linha
        edited_df = st.data_editor(
            df_to_edit,
            key=editor_key,
            on_change=resetar_estado_processamento,
            hide_index=True,
            column_config={
                "Selecionar": st.column_config.CheckboxColumn(
                    "Selecionar",
                    help="Selecione os produtos para download ou processamento",
                    default=selecionar_padrao,
                ),
                "id": None,  # Oculta a coluna id
                "zenital": None,  # Oculta a coluna zenital
                "Data do Produto": st.column_config.DateColumn("Data do Produto", format="YYYY-MM-DD", width="medium"),
                "Satélite": st.column_config.TextColumn("Satélite", width="small"),
                "Grade MGRS": st.column_config.TextColumn("Grade MGRS", width="small"),
                "Tamanho Pixel (m)": st.column_config.NumberColumn("Tamanho Pixel (m)", width="small"),
                "Pixels Válidos": st.column_config.NumberColumn("Pixels Válidos", width="medium"),
                "Status no Drive": st.column_config.TextColumn("Status no Drive", width="medium"),
                "Importado para o Banco": st.column_config.TextColumn("Status no Banco", width="medium")
            },
            disabled=[c for c in df_to_edit.columns if c != "Selecionar"],
            use_container_width=True
        )

        st.divider()

        # Seleciona os registros marcados
        selected_rows = edited_df[edited_df["Selecionar"] == True]
        
        # Filtra apenas os selecionados que estão disponíveis no Drive
        valid_selected = selected_rows[selected_rows["Status no Drive"] == "Disponível ✅"]
        
        col_spacer, col_process_db, col_download = st.columns([6, 3, 3])
        
        with col_process_db:
            if not valid_selected.empty:
                if st.button("Sincronizar com o Banco de Dados", type="secondary", use_container_width=True, key="btn_sincronizar_ativos"):
                    st.session_state["executar_processamento"] = True
                    st.session_state["processamento_concluido"] = False
                    st.session_state["logs_processamento"] = []
                    st.rerun()
            else:
                st.button(
                    "Sincronizar com o Banco de Dados", 
                    type="secondary", 
                    use_container_width=True, 
                    disabled=True, 
                    help="Marque pelo menos um produto com status 'Disponível ✅'.",
                    key="btn_sincronizar_inativos"
                )
                
        with col_download:
            if not valid_selected.empty:
                if st.button("Baixar Arquivos", type="primary", use_container_width=True, key="btn_baixar_ativos"):
                    baixar_arquivos_modal(valid_selected, map_nome_id)
            else:
                st.button(
                    "Baixar Arquivos", 
                    type="primary", 
                    use_container_width=True, 
                    disabled=True, 
                    help="Marque pelo menos um produto com status 'Disponível ✅'.",
                    key="btn_baixar_inativos"
                )
                
        # Renderiza o modal condicionalmente de acordo com o estado do session_state
        if st.session_state.get("executar_processamento") or st.session_state.get("processamento_concluido"):
            processar_csv_modal(valid_selected, map_nome_id)
