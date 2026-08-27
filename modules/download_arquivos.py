import streamlit as st
import datetime
import os
import shutil
import zipfile
import inspect
from modules.api_gdrive import baixar_arquivo_drive_para_disco

temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "temp_downloads")

def limpar_pasta_temporaria():
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
    os.makedirs(temp_dir, exist_ok=True)

def on_dismiss_download_callback():
    st.session_state['show_download_modal'] = False
    limpar_pasta_temporaria()

def _baixar_arquivos_dialog_impl(valid_selected, map_nome_id, map_nome_id_lower):
    st.write(f"Você selecionou **{len(valid_selected)}** arquivo(s) disponível(is) para download.")
    
    with st.spinner("Baixando arquivos do Drive diretamente para o servidor..."):
        try:
            limpar_pasta_temporaria()
            files_downloaded = []
            
            for idx, row in valid_selected.iterrows():
                date_str = row["Data do Produto"].strftime('%Y-%m-%d') if isinstance(row["Data do Produto"], (datetime.date, datetime.datetime)) else str(row["Data do Produto"])
                nome_esperado = f"CELMM_Data_{date_str}_{int(row['Tamanho Pixel (m)'])}m.csv"
                fid = map_nome_id.get(nome_esperado) or map_nome_id_lower.get(nome_esperado.lower())
                if fid:
                    dest_path = os.path.join(temp_dir, nome_esperado)
                    baixar_arquivo_drive_para_disco(fid, dest_path)
                    files_downloaded.append(dest_path)
            
            if not files_downloaded:
                st.warning("Nenhum arquivo correspondente encontrado no Google Drive.")
            elif len(files_downloaded) == 1:
                local_file_path = files_downloaded[0]
                filename = os.path.basename(local_file_path)
                
                with open(local_file_path, "rb") as f:
                    st.download_button(
                        label="Salvar Arquivo CSV no Computador",
                        data=f,
                        file_name=filename,
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )
            else:
                zip_filename = f"CELMM_CSVs_{datetime.date.today().strftime('%Y%m%d')}.zip"
                zip_path = os.path.join(temp_dir, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for filepath in files_downloaded:
                        zip_file.write(filepath, os.path.basename(filepath))
                        
                with open(zip_path, "rb") as f:
                    st.download_button(
                        label="Salvar Pacote ZIP no Computador",
                        data=f,
                        file_name=zip_filename,
                        mime="application/zip",
                        type="primary",
                        use_container_width=True
                    )
        except Exception as e:
            st.error(f"Erro ao processar arquivos do Drive: {e}")

def baixar_arquivos_dialog(valid_selected, map_nome_id, map_nome_id_lower):
    sig_dialog = inspect.signature(st.dialog)
    dialog_kwargs = {"width": "large"} if "width" in sig_dialog.parameters else {}
    
    if 'on_dismiss' in sig_dialog.parameters:
        @st.dialog("Baixar Arquivos do Google Drive", on_dismiss=on_dismiss_download_callback, **dialog_kwargs)
        def _inner(v_sel, m_id, m_id_lower):
            _baixar_arquivos_dialog_impl(v_sel, m_id, m_id_lower)
        _inner(valid_selected, map_nome_id, map_nome_id_lower)
    else:
        @st.dialog("Baixar Arquivos do Google Drive", dismissible=True, **dialog_kwargs)
        def _inner(v_sel, m_id, m_id_lower):
            _baixar_arquivos_dialog_impl(v_sel, m_id, m_id_lower)
        _inner(valid_selected, map_nome_id, map_nome_id_lower)
