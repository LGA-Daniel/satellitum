import os
import gc
import io
import time
import datetime
import hashlib
import pandas as pd
import streamlit as st
from modules.db import obter_df_pixels_por_imagem_ids_generator

module_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(module_dir)
temp_dir = os.path.join(project_root, "temp_downloads")

def limpar_arquivos_exportacao_disco():
    """Remove todos os arquivos gerados de exportação no disco e aciona garbage collection."""
    if os.path.exists(temp_dir):
        try:
            for filename in os.listdir(temp_dir):
                if filename.startswith("CELMM_Export_"):
                    fpath = os.path.join(temp_dir, filename)
                    if os.path.isfile(fpath):
                        os.remove(fpath)
        except Exception:
            pass
    gc.collect()

def preparar_arquivo_exportacao(ids_imagens: list, tipo_formato: str) -> dict:
    """Streaming em lotes diretamente do PostgreSQL para arquivo em disco com Garbage Collection.
    
    Evita sobrecarga de memória RAM mesmo para exportações massivas de centenas de megabytes (800MB+).
    Retorna dicionário contendo caminho do arquivo em disco, nome, mime_type, tamanho em MB, total de linhas e tempo.
    """
    os.makedirs(temp_dir, exist_ok=True)
    
    ids_hash = hashlib.md5(str(sorted(ids_imagens)).encode()).hexdigest()
    file_ext = "csv" if tipo_formato == 'csv' else "xlsx"
    target_filename = f"CELMM_Export_{datetime.date.today().strftime('%Y%m%d')}_{ids_hash[:8]}.{file_ext}"
    target_filepath = os.path.join(temp_dir, target_filename)
    
    export_key = f"export_cache_meta_{tipo_formato}_{ids_hash}"
    if export_key in st.session_state and os.path.exists(target_filepath):
        return st.session_state[export_key]

    # Remove arquivos de exportação anteriores para manter o disco limpo
    limpar_arquivos_exportacao_disco()

    start_time = time.time()
    total_rows = 0
    colunas_para_excluir = {'id', 'metadados_imagem_id', 'data_registro', 'system_index', 'geo'}
    
    generator = obter_df_pixels_por_imagem_ids_generator(ids_imagens, chunksize=50000)
    
    if tipo_formato == 'csv':
        mime_type = "text/csv"
        with open(target_filepath, 'w', encoding='utf-8', newline='') as f_out:
            for chunk in generator:
                colunas_exportaveis = [col for col in chunk.columns if col not in colunas_para_excluir]
                df_export = chunk[colunas_exportaveis]
                
                # Escreve cabeçalho apenas no primeiro chunk
                df_export.to_csv(f_out, index=False, header=(total_rows == 0))
                total_rows += len(chunk)
                
                del df_export
                del chunk
                gc.collect()
    else:
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        chunks = []
        for chunk in generator:
            colunas_exportaveis = [col for col in chunk.columns if col not in colunas_para_excluir]
            chunks.append(chunk[colunas_exportaveis])
            total_rows += len(chunk)
            del chunk
            gc.collect()
            
            if total_rows > 1048500:
                del chunks
                gc.collect()
                raise ValueError(
                    f"A seleção contém mais de {total_rows:,} linhas, excedendo o limite máximo do Excel (1.048.576 linhas). "
                    "Por favor, utilize o formato CSV para exportações deste volume de dados."
                )
                
        if not chunks:
            raise ValueError("Nenhum dado de pixel encontrado no banco de dados para os produtos selecionados.")
            
        df_completo = pd.concat(chunks, ignore_index=True)
        del chunks
        gc.collect()
        
        try:
            with pd.ExcelWriter(target_filepath, engine='openpyxl') as writer:
                df_completo.to_excel(writer, index=False, sheet_name="Pixels_CELMM")
        except ImportError:
            raise RuntimeError("Suporte a Excel indisponível no ambiente.")
        finally:
            del df_completo
            gc.collect()

    if total_rows == 0:
        if os.path.exists(target_filepath):
            os.remove(target_filepath)
        raise ValueError("Nenhum dado de pixel encontrado no banco de dados para os produtos selecionados.")

    elapsed = int(time.time() - start_time)
    file_size_bytes = os.path.getsize(target_filepath)
    file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

    resultado = {
        "file_path": target_filepath,
        "file_name": target_filename,
        "file_ext": file_ext,
        "mime_type": mime_type,
        "total_rows": total_rows,
        "file_size_mb": file_size_mb,
        "elapsed": elapsed
    }
    
    st.session_state[export_key] = resultado
    gc.collect()
    return resultado
