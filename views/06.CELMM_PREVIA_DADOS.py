import streamlit as st
import pandas as pd
from modules.core import obter_df_pixels_por_imagem_ids, obter_df_pixels_por_imagem_ids_generator

def exportar_conteudo_modal(ids_imagens, tipo_formato):
    # Prepara uma chave única e estável para cachear o processamento do download
    import hashlib
    import datetime
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
            label=f"Clique aqui para Baixar {tipo_formato.upper()}",
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
        st.error("Erro: Nenhum dado de pixel encontrado para as imagens selecionadas.")
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
    import io
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
        with st.expander("Preparação do Download", expanded=True):
            exportar_conteudo_modal(ids_imagens, tipo_formato)

st.set_page_config(page_title="CELMM | Prévia de Dados", page_icon="🛰️", layout="wide")

st.title("CELMM - Prévia de Dados")
st.caption("Visualização rápida das primeiras 500 linhas dos dados de pixels carregados da base de dados PostgreSQL.")
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
    
    col_csv, col_xlsx = st.columns(2)
    
    with col_csv:
        if st.button("Baixar em CSV", type="secondary", use_container_width=True):
            modal_exportar(st.session_state["ids_pixels_carregados"], 'csv')
            
    with col_xlsx:
        if st.button("Baixar em XLSX", type="secondary", use_container_width=True):
            modal_exportar(st.session_state["ids_pixels_carregados"], 'xlsx')
                

