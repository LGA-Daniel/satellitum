import io
import time
import datetime
import hashlib
import pandas as pd
import streamlit as st
from modules.db import obter_df_pixels_por_imagem_ids_generator

def preparar_arquivo_exportacao(ids_imagens: list, tipo_formato: str) -> dict:
    """Carregamento em lotes do banco de dados, limpeza de colunas e codificação
    em formato CSV ou XLSX com suporte a cache em session_state.
    
    Retorna dicionário contendo os dados do arquivo codificado, mime_type, file_ext, total_rows e tempo decorrido.
    """
    ids_hash = hashlib.md5(str(sorted(ids_imagens)).encode()).hexdigest()
    export_key = f"export_cache_{tipo_formato}_{ids_hash}"
    
    if export_key in st.session_state:
        return st.session_state[export_key]

    start_time = time.time()
    chunks = []
    total_rows = 0
    generator = obter_df_pixels_por_imagem_ids_generator(ids_imagens, chunksize=50000)
    
    for chunk in generator:
        chunks.append(chunk)
        total_rows += len(chunk)
        
    if not chunks:
        raise ValueError("Nenhum dado de pixel encontrado no banco de dados para as imagens selecionadas.")
        
    df_pixels = pd.concat(chunks, ignore_index=True)
    
    colunas_para_excluir = ['id', 'metadados_imagem_id', 'data_registro', 'system_index', 'geo']
    colunas_exportaveis = [col for col in df_pixels.columns if col not in colunas_para_excluir]
    df_export = df_pixels[colunas_exportaveis]
    
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
            raise RuntimeError("Suporte a Excel indisponível. Reconstrua a stack Docker (`docker compose up --build -d`).")
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        file_ext = "xlsx"
        
    elapsed = int(time.time() - start_time)
    
    resultado = {
        "file_data": file_data,
        "mime_type": mime_type,
        "file_ext": file_ext,
        "total_rows": total_rows,
        "elapsed": elapsed
    }
    
    st.session_state[export_key] = resultado
    return resultado
