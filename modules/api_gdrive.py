import os
import time
import io
import streamlit as st

def obter_caminho_token() -> str:
    """Retorna o caminho do arquivo JSON de credenciais da Service Account para o Google Drive."""
    env_path = os.getenv("GDRIVE_SERVICE_ACCOUNT_KEY_FILE") or os.getenv("GEE_SERVICE_ACCOUNT_KEY_FILE")
    if env_path and os.path.exists(env_path):
        return os.path.abspath(env_path)

    module_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(module_dir)
    streamlit_dir = os.path.join(project_root, ".streamlit")
    
    candidatos = [
        os.path.join(streamlit_dir, "token.json"),
        os.path.join(streamlit_dir, "credentials"),
        os.path.join(streamlit_dir, "SA.json"),
        os.path.join(".streamlit", "token.json"),
        os.path.join(".streamlit", "credentials"),
        os.path.join(".streamlit", "SA.json"),
        "/app/.streamlit/token.json",
        "/app/.streamlit/credentials",
        "/app/.streamlit/SA.json"
    ]
    for c in candidatos:
        if os.path.exists(c):
            return os.path.abspath(c)
            
    if os.path.exists(streamlit_dir):
        json_files = [f for f in os.listdir(streamlit_dir) if f.endswith('.json')]
        if json_files:
            json_files.sort()
            return os.path.join(streamlit_dir, json_files[0])
            
    raise FileNotFoundError("Nenhum arquivo JSON de credenciais encontrado em '.streamlit'.")

@st.cache_resource
def obter_servico_gdrive():
    """Retorna uma instância de cliente do Google Drive API (v3) autenticada com o token JSON."""
    try:
        from googleapiclient.discovery import build
        from modules.google_auth import carregar_credenciais_google
        
        credentials = carregar_credenciais_google()
        service = build('drive', 'v3', credentials=credentials)
        return service
    except Exception as e:
        st.error(f"Erro ao inicializar o cliente do Google Drive: {e}")
        return None

@st.cache_data(ttl=30)
def listar_arquivos_pasta_drive(folder_name: str = 'CSV_Sentinel2') -> list:
    """Lista todos os arquivos dentro de uma pasta específica no Google Drive com lógica de retentativas."""
    retries = 3
    delay = 1
    
    for attempt in range(retries):
        service = obter_servico_gdrive()
        if not service:
            if attempt == retries - 1:
                return []
            time.sleep(delay)
            delay *= 2
            continue
            
        try:
            query_folder = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            response_folder = service.files().list(q=query_folder, fields="files(id, name)").execute()
            folders = response_folder.get('files', [])
            
            if not folders:
                return []
                
            folder_ids = [f['id'] for f in folders]
            all_files = []
            for fid in folder_ids:
                query_files = f"'{fid}' in parents and trashed = false"
                page_token = None
                while True:
                    response_files = service.files().list(
                        q=query_files,
                        fields="nextPageToken, files(id, name, mimeType, size, createdTime)",
                        pageToken=page_token
                    ).execute()
                    all_files.extend(response_files.get('files', []))
                    page_token = response_files.get('nextPageToken')
                    if not page_token:
                        break
                        
            return all_files
        except Exception as e:
            if attempt == retries - 1:
                st.error(f"Erro ao listar arquivos da pasta '{folder_name}' no Google Drive após {retries} tentativas: {e}")
                return []
            else:
                time.sleep(delay)
                delay *= 2

def baixar_conteudo_arquivo_drive(file_id: str) -> bytes:
    """Retorna o conteúdo binário (bytes) de um arquivo no Google Drive com lógica de retentativas."""
    from googleapiclient.http import MediaIoBaseDownload
    
    retries = 3
    delay = 1
    
    for attempt in range(retries):
        service = obter_servico_gdrive()
        if not service:
            if attempt == retries - 1:
                raise ConnectionError("Não foi possível inicializar o serviço do Google Drive.")
            time.sleep(delay)
            delay *= 2
            continue
            
        try:
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                
            return fh.getvalue()
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"Erro ao baixar conteúdo do arquivo do Drive após {retries} tentativas: {e}")
            else:
                time.sleep(delay)
                delay *= 2

def baixar_arquivo_drive_para_disco(file_id: str, dest_path: str):
    """Baixa um arquivo do Google Drive diretamente para o disco para economizar RAM com lógica de retentativas."""
    from googleapiclient.http import MediaIoBaseDownload
    
    retries = 3
    delay = 1
    
    for attempt in range(retries):
        service = obter_servico_gdrive()
        if not service:
            if attempt == retries - 1:
                raise ConnectionError("Não foi possível inicializar o serviço do Google Drive.")
            time.sleep(delay)
            delay *= 2
            continue
            
        try:
            request = service.files().get_media(fileId=file_id)
            with open(dest_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            return
        except Exception as e:
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except:
                    pass
            if attempt == retries - 1:
                raise RuntimeError(f"Erro ao baixar arquivo do Drive para o disco após {retries} tentativas: {e}")
            else:
                time.sleep(delay)
                delay *= 2
