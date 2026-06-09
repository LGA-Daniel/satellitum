import ee
import os
import streamlit as st
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert
from modules.models import HistoricoExecucao, MetadadosImagens, CelmmPixels

# Configurações do Banco de Dados
DB_HOST = os.getenv("DB_HOST", "satellitum_db")
DB_NAME = os.getenv("DB_NAME", "satellitum")
DB_USER = os.getenv("DB_USER", "administrador")
DB_PASS = os.getenv("DB_PASS", "202606")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"

# Criação do Engine do SQLAlchemy
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Retorna uma nova sessão do banco de dados."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def registrar_historico(nome_arquivo: str, script: str, status_execucao: str):
    """Grava o log de execução no banco usando SQLAlchemy."""
    db = SessionLocal()
    try:
        log = HistoricoExecucao(
            nome_arquivo=nome_arquivo,
            script=script,
            status=status_execucao
        )
        db.add(log)
        db.commit()
    except Exception as e:
        db.rollback()
        st.error(f"Erro ao salvar histórico de execução: {e}")
    finally:
        db.close()

def salvar_metadados(lista_dados: list, tamanho_pixel: int) -> bool:
    """Salva ou atualiza a lista de metadados no banco usando PostgreSQL Upsert."""
    db = SessionLocal()
    try:
        for item in lista_dados:
            stmt = insert(MetadadosImagens).values(
                data=str(item.get('Data')),
                pixels_validos=int(item.get('Pixels_Validos', 0)),
                satelite=str(item.get('Satelite')),
                zenital=float(item.get('Zenital')) if item.get('Zenital') is not None else None,
                z_grade_mgrs=str(item.get('Z_Grade_MGRS')) if item.get('Z_Grade_MGRS') is not None else None,
                tamanho_pixel=int(tamanho_pixel)
            )
            stmt = stmt.on_conflict_do_update(
                constraint='uq_metadados_imagem',
                set_={
                    'pixels_validos': stmt.excluded.pixels_validos,
                    'zenital': stmt.excluded.zenital,
                    'data_registro': func.now()
                }
            )
            db.execute(stmt)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        st.error(f"Erro ao salvar metadados no banco: {e}")
        return False
    finally:
        db.close()

def obter_metadados_salvos() -> list:
    """Retorna todos os registros da tabela metadados_imagens ordenados por data decrescente."""
    db = SessionLocal()
    try:
        registros = db.query(MetadadosImagens).order_by(MetadadosImagens.data.desc()).all()
        return [r.to_dict() for r in registros]
    except Exception as e:
        st.error(f"Erro ao buscar metadados do banco: {e}")
        return []
    finally:
        db.close()

def obter_caminho_token() -> str:
    """Retorna o caminho rígido do arquivo JSON de credenciais na pasta .streamlit da raiz do projeto."""
    module_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(module_dir)
    streamlit_dir = os.path.join(project_root, ".streamlit")
    
    if not os.path.exists(streamlit_dir):
        raise FileNotFoundError(f"Diretório '.streamlit' não encontrado na raiz do projeto ({project_root}).")
        
    json_files = [f for f in os.listdir(streamlit_dir) if f.endswith('.json')]
    if not json_files:
        raise FileNotFoundError("Nenhum arquivo JSON de credenciais encontrado em '.streamlit'.")
        
    json_files.sort()
    return os.path.join(streamlit_dir, json_files[0])

@st.cache_resource
def init_gee():
    """Inicializa o GEE apenas uma vez por sessão."""
    try:
        project = os.getenv("EARTHENGINE_PROJECT", "ppgrhs")
        ee.Initialize(project=project)
        return True
    except Exception as e:
        st.error(f"Erro ao inicializar o Earth Engine: {e}. Verifique as credenciais.")
        return False

@st.cache_resource
def obter_servico_gdrive():
    """Retorna uma instância de cliente do Google Drive API (v3) autenticada com o token JSON."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        json_path = obter_caminho_token()
        
        # Escopo padrão para acesso ao Drive
        scopes = ['https://www.googleapis.com/auth/drive']
        
        credentials = service_account.Credentials.from_service_account_file(
            json_path,
            scopes=scopes
        )
        
        service = build('drive', 'v3', credentials=credentials)
        return service
    except Exception as e:
        st.error(f"Erro ao inicializar o cliente do Google Drive: {e}")
        return None

@st.cache_data(ttl=30)
def listar_arquivos_pasta_drive(folder_name: str = 'CSV_Sentinel2') -> list:
    """Lista todos os arquivos dentro de uma pasta específica no Google Drive da conta de serviço."""
    service = obter_servico_gdrive()
    if not service:
        return []
        
    try:
        # 1. Busca pela pasta do Drive pelo nome e tipo mime
        query_folder = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        response_folder = service.files().list(q=query_folder, fields="files(id, name)").execute()
        folders = response_folder.get('files', [])
        
        if not folders:
            return []
            
        # Coleta os IDs das pastas encontradas
        folder_ids = [f['id'] for f in folders]
        
        # 2. Lista os arquivos contidos nessas pastas
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
        st.error(f"Erro ao listar arquivos da pasta '{folder_name}' no Google Drive: {e}")
        return []

def baixar_conteudo_arquivo_drive(file_id: str) -> bytes:
    """Retorna o conteúdo binário (bytes) de um arquivo no Google Drive."""
    service = obter_servico_gdrive()
    if not service:
        raise ConnectionError("Não foi possível inicializar o serviço do Google Drive.")
        
    try:
        import io
        from googleapiclient.http import MediaIoBaseDownload
        
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            
        return fh.getvalue()
    except Exception as e:
        raise RuntimeError(f"Erro ao baixar arquivo do Drive: {e}")

def baixar_arquivo_drive_para_disco(file_id: str, dest_path: str):
    """Baixa um arquivo do Google Drive diretamente para o disco para economizar RAM."""
    service = obter_servico_gdrive()
    if not service:
        raise ConnectionError("Não foi possível inicializar o serviço do Google Drive.")
        
    try:
        from googleapiclient.http import MediaIoBaseDownload
        
        request = service.files().get_media(fileId=file_id)
        with open(dest_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
    except Exception as e:
        import os
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except:
                pass
        raise RuntimeError(f"Erro ao baixar arquivo do Drive para o disco: {e}")

def salvar_pixels_bulk(df_pixels) -> int:
    """Insere ou atualiza registros de pixels na tabela celmm_pixels usando PostgreSQL COPY via tabela temporária de estágio."""
    if df_pixels.empty:
        return 0
        
    import io
    db = SessionLocal()
    try:
        # Colunas na ordem que serão exportadas/importadas pelo COPY
        colunas = [
            'metadados_imagem_id', 'system_index', 'data', 'satelite', 
            'z_grade_mgrs', 'tamanho_pixel', 'zenital', 
            'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12', 
            'latitude', 'longitude', 'geo'
        ]
        
        # Cria um buffer CSV em memória com o DataFrame contendo apenas as colunas especificadas
        csv_buffer = io.StringIO()
        df_pixels.to_csv(csv_buffer, index=False, header=True, columns=colunas, sep=',')
        csv_buffer.seek(0)
        
        # Acessa a conexão e o cursor DBAPI bruto (psycopg2)
        connection = db.connection()
        dbapi_conn = getattr(connection, "dbapi_connection", getattr(connection, "connection", None))
        if dbapi_conn is None:
            raise RuntimeError("Não foi possível obter a conexão DBAPI bruta do SQLAlchemy.")
            
        cursor = dbapi_conn.cursor()
        
        # 1. Cria a tabela temporária (sem chaves ou constraints para velocidade máxima)
        cursor.execute("CREATE TEMP TABLE temp_celmm_pixels (LIKE celmm_pixels INCLUDING DEFAULTS) ON COMMIT DROP;")
        
        # 2. Executa o COPY rápido
        # Adiciona aspas duplas ao redor dos nomes das colunas para manter a diferenciação de maiúsculas/minúsculas no PostgreSQL (ex: "B1")
        colunas_str = ", ".join([f'"{col}"' for col in colunas])
        copy_sql = f"COPY temp_celmm_pixels ({colunas_str}) FROM STDIN WITH CSV HEADER;"
        cursor.copy_expert(copy_sql, csv_buffer)
        
        # 3. Executa o INSERT com resolução de conflito (ON CONFLICT DO UPDATE)
        insert_sql = f"""
            INSERT INTO celmm_pixels ({colunas_str})
            SELECT {colunas_str} FROM temp_celmm_pixels
            ON CONFLICT ON CONSTRAINT uq_celmm_pixel DO UPDATE SET
                "B1" = EXCLUDED."B1",
                "B2" = EXCLUDED."B2",
                "B3" = EXCLUDED."B3",
                "B4" = EXCLUDED."B4",
                "B5" = EXCLUDED."B5",
                "B6" = EXCLUDED."B6",
                "B7" = EXCLUDED."B7",
                "B8" = EXCLUDED."B8",
                "B8A" = EXCLUDED."B8A",
                "B9" = EXCLUDED."B9",
                "B11" = EXCLUDED."B11",
                "B12" = EXCLUDED."B12",
                "latitude" = EXCLUDED."latitude",
                "longitude" = EXCLUDED."longitude",
                "geo" = EXCLUDED."geo",
                "data" = EXCLUDED."data",
                "satelite" = EXCLUDED."satelite",
                "z_grade_mgrs" = EXCLUDED."z_grade_mgrs",
                "tamanho_pixel" = EXCLUDED."tamanho_pixel",
                "zenital" = EXCLUDED."zenital",
                "data_registro" = NOW();
        """
        cursor.execute(insert_sql)
        db.commit()
        return len(df_pixels)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()