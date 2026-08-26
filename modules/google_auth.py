import os
import json
import logging
from typing import Tuple, Dict, Any, Optional
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/earthengine",
    "https://www.googleapis.com/auth/cloud-platform"
]

def obter_diretorios_credenciais() -> Tuple[str, str, str]:
    """Retorna os caminhos base do projeto, pasta .streamlit, token.json e credentials."""
    module_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(module_dir)
    streamlit_dir = os.path.join(project_root, ".streamlit")
    os.makedirs(streamlit_dir, exist_ok=True)
    
    token_path = os.path.join(streamlit_dir, "token.json")
    gee_cred_path = os.path.join(streamlit_dir, "credentials")
    return streamlit_dir, token_path, gee_cred_path

def _obter_var_ambiente(nome: str, default: str = None) -> Optional[str]:
    """Obtém variável lendo primeiramente do arquivo .env em disco ou de os.getenv."""
    module_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(module_dir)
    candidatos_env = [
        os.path.join(project_root, ".env"),
        os.path.join(project_root, ".streamlit", ".env"),
        ".env",
        os.path.join(".streamlit", ".env")
    ]
    for caminho in candidatos_env:
        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            if k.strip() == nome:
                                val = v.strip().strip("'\"")
                                if val:
                                    return val
            except Exception:
                pass
                
    valor = os.getenv(nome)
    if valor:
        return valor
    return default

def obter_client_config() -> Optional[Dict[str, Any]]:
    """Obtém as credenciais de cliente OAuth exclusivamente a partir das variáveis de ambiente do .env."""
    client_id = _obter_var_ambiente("GOOGLE_CLIENT_ID")
    client_secret = _obter_var_ambiente("GOOGLE_CLIENT_SECRET")
    project_id = _obter_var_ambiente("GOOGLE_PROJECT_ID") or _obter_var_ambiente("EARTHENGINE_PROJECT", "ppgrhs-satellitum")
    app_url = _obter_var_ambiente("APP_URL", "http://localhost:8502").rstrip("/")

    if client_id and client_secret:
        client_id = client_id.strip()
        client_secret = client_secret.strip()
        if "seu_google_client_id" not in client_id and "seu_google_client_secret" not in client_secret:
            return {
                "web": {
                    "client_id": client_id,
                    "project_id": project_id,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_secret": client_secret,
                    "redirect_uris": [app_url, "http://localhost:8502", "http://localhost"]
                }
            }

    return None

def obter_redirect_uri_padrao(redirect_uri: Optional[str] = None) -> str:
    """Determina o redirect_uri para redirecionar diretamente de volta ao Satellitum (sem barra final)."""
    if redirect_uri:
        return redirect_uri.rstrip("/")
    app_url = _obter_var_ambiente("APP_URL", "http://localhost:8502").rstrip("/")
    return app_url

def criar_flow(redirect_uri: Optional[str] = None) -> Flow:
    """Cria e retorna uma instância do Google OAuth Flow."""
    client_config = obter_client_config()
    if not client_config:
        raise ValueError(
            "Credenciais GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET não estão configuradas no .env"
        )
    
    uri = obter_redirect_uri_padrao(redirect_uri)
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=uri
    )
    return flow

def get_login_url() -> str:
    """Gera a URL de login do Google com os escopos necessários de forma direta e limpa."""
    import urllib.parse
    client_id = _obter_var_ambiente("GOOGLE_CLIENT_ID")
    redirect_uri = _obter_var_ambiente("APP_URL", "http://localhost:8502").rstrip("/")
    scopes = "https://www.googleapis.com/auth/earthengine https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/cloud-platform"
    
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "access_type": "offline",
        "prompt": "consent",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

def extrair_codigo_limpo(code_or_url: str) -> str:
    """Extrai e decodifica o código de autorização mesmo se colado com URL ou codificado em URL."""
    import urllib.parse
    texto = code_or_url.strip().strip("'\"")
    
    if "code=" in texto:
        parsed = urllib.parse.urlparse(texto)
        qs = urllib.parse.parse_qs(parsed.query)
        if "code" in qs and qs["code"]:
            return qs["code"][0].strip()
        part = texto.split("code=")[1]
        part = part.split("&")[0].split("#")[0].strip()
        return urllib.parse.unquote(part)
    
    return urllib.parse.unquote(texto)

def get_tokens(code: str) -> dict:
    """Troca o código de autorização pelos tokens de acesso e refresh via requisição direta."""
    import requests
    code_clean = extrair_codigo_limpo(code)
    client_id = _obter_var_ambiente("GOOGLE_CLIENT_ID")
    client_secret = _obter_var_ambiente("GOOGLE_CLIENT_SECRET")
    redirect_uri = _obter_var_ambiente("APP_URL", "http://localhost:8502").rstrip("/")
    
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code_clean,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        response = requests.post(token_url, data=data, timeout=10)
        return response.json()
    except Exception as e:
        return {"error": "request_failed", "error_description": str(e)}

def processar_e_salvar_tokens(tokens: dict) -> bool:
    """Grava as credenciais nos arquivos credentials e token.json."""
    if not tokens or "access_token" not in tokens:
        return False
        
    client_id = _obter_var_ambiente("GOOGLE_CLIENT_ID")
    client_secret = _obter_var_ambiente("GOOGLE_CLIENT_SECRET")
    _, token_path, gee_cred_path = obter_diretorios_credenciais()
    
    refresh_token = tokens.get("refresh_token")
    if not refresh_token and os.path.exists(gee_cred_path):
        try:
            with open(gee_cred_path, "r", encoding="utf-8") as f:
                prev = json.load(f)
                refresh_token = prev.get("refresh_token")
        except Exception:
            pass
            
    # Salva credentials (formato nativo do Earth Engine)
    gee_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "type": "authorized_user"
    }
    with open(gee_cred_path, "w", encoding="utf-8") as f:
        json.dump(gee_data, f, indent=2)
        
    # Salva token.json (para uso pelo Google Drive)
    token_data = {
        "token": tokens["access_token"],
        "refresh_token": refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": SCOPES
    }
    with open(token_path, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)
        
    return True

def limpar_credenciais() -> bool:
    """Exclui os arquivos token.json e credentials salvos."""
    _, token_path, gee_cred_path = obter_diretorios_credenciais()
    removido = False
    for path in [token_path, gee_cred_path]:
        if os.path.exists(path):
            try:
                os.remove(path)
                removido = True
            except Exception as e:
                logger.error(f"Erro ao remover {path}: {e}")
    return removido

def obter_status_autenticacao() -> Dict[str, Any]:
    """Analisa o status atual dos arquivos de credenciais."""
    _, token_path, gee_cred_path = obter_diretorios_credenciais()
    status = {
        "token_existe": os.path.exists(token_path),
        "gee_cred_existe": os.path.exists(gee_cred_path),
        "tipo": "Ausente",
        "email_ou_client": "N/A",
        "valido": False,
        "detalhes": ""
    }
    
    # Lê token.json ou credentials
    target_path = token_path if os.path.exists(token_path) else gee_cred_path
    if not os.path.exists(target_path):
        status["detalhes"] = "Nenhum arquivo de credenciais encontrado em .streamlit."
        return status
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if data.get("type") == "service_account":
            status["tipo"] = "Service Account (Conta de Serviço)"
            status["email_ou_client"] = data.get("client_email", "N/A")
            status["valido"] = True
            status["detalhes"] = "Conta de serviço carregada com sucesso."
        elif (data.get("refresh_token") and data.get("refresh_token") != "") or data.get("token"):
            status["tipo"] = "OAuth 2.0 (Conta de Usuário Google)"
            status["email_ou_client"] = data.get("client_id", "Autenticado via Earth Engine")
            status["valido"] = True
            status["detalhes"] = "Token OAuth de usuário ativo."
        else:
            status["tipo"] = "Ausente / Vazio"
            status["detalhes"] = "O arquivo de credenciais existe mas não contém refresh_token ativo."
    except Exception as e:
        status["detalhes"] = f"Erro ao ler arquivo de credenciais: {e}"
        
    return status

def carregar_credenciais_google():
    """Carrega as credenciais apropriadas (Service Account ou OAuth User) com auto-refresh."""
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from modules.api_gdrive import obter_caminho_token
    
    json_path = obter_caminho_token()
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if data.get("type") == "service_account":
        return service_account.Credentials.from_service_account_file(
            json_path,
            scopes=SCOPES
        )
    else:
        creds = Credentials.from_authorized_user_file(json_path, scopes=SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Atualiza o arquivo salvo com o novo access_token
            with open(json_path, "w", encoding="utf-8") as f_out:
                token_dict = {
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": creds.scopes,
                    "expiry": creds.expiry.isoformat() if creds.expiry else None
                }
                json.dump(token_dict, f_out, indent=2)
        return creds

def testar_conexao_gdrive() -> Tuple[bool, str]:
    """Testa a chamada à API do Google Drive."""
    try:
        from googleapiclient.discovery import build
        creds = carregar_credenciais_google()
        service = build("drive", "v3", credentials=creds)
        # Teste rápido: obtém informações sobre o usuário autenticado ou sobre o drive
        about = service.about().get(fields="user(displayName, emailAddress)").execute()
        user_info = about.get("user", {})
        display = user_info.get("displayName", "Usuário")
        email = user_info.get("emailAddress", "")
        return True, f"Conexão com Google Drive estabelecida com sucesso! ({display} <{email}>)"
    except Exception as e:
        return False, f"Falha na comunicação com Google Drive: {str(e)}"

def testar_conexao_gee() -> Tuple[bool, str]:
    """Testa a inicialização do Earth Engine usando as credenciais salvas."""
    try:
        import ee
        project = os.getenv("EARTHENGINE_PROJECT") or os.getenv("GOOGLE_PROJECT_ID", "ppgrhs-satellitum")
        creds = carregar_credenciais_google()
        ee.Initialize(credentials=creds, project=project)
        # Executa operação simples no GEE para validar
        res = ee.Number(1).add(1).getInfo()
        if res == 2:
            return True, f"Google Earth Engine inicializado com sucesso no projeto '{project}'!"
        return False, f"Resposta inesperada do Earth Engine: {res}"
    except Exception as e:
        return False, f"Falha ao conectar com Earth Engine: {str(e)}"
