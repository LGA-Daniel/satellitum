import os
import hashlib
import hmac
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple, Dict, Any
import streamlit as st

from modules.models import Base, User
from modules.db import engine, SessionLocal

# ==============================================================================
# CONFIGURAÇÃO DE SEGURANÇA E JWT
# ==============================================================================
def get_secret_key() -> str:
    """Obtém a chave secreta a partir do st.secrets ou variável de ambiente."""
    try:
        if hasattr(st, "secrets") and "SECRET_KEY" in st.secrets:
            return str(st.secrets["SECRET_KEY"])
    except Exception:
        pass
    return os.getenv("SECRET_KEY", "satellitum-secure-jwt-token-key-2026-production")

SECRET_KEY = get_secret_key()
JWT_ALGORITHM = "HS256"

# ==============================================================================
# 1. MATRIZ DE TELAS (AVAILABLE_VIEWS)
# ==============================================================================
AVAILABLE_VIEWS = [
    {
        "category": "Início",
        "views": [
            {
                "name": "Satellitum (Home)",
                "path": "views/00.Home.py",
                "icon": "🛰️",
                "url_path": None,
                "default": True
            }
        ]
    },
    {
        "category": "Processamento & Metadados",
        "views": [
            {
                "name": "CELMM | Gerenciamento de Produtos Orbitais",
                "path": "views/08.CELMM_GESTAO_PRODUTOS.py",
                "icon": "🛰️",
                "url_path": None,
                "default": True
            }
        ]
    },
    {
        "category": "Visualização & Análise",
        "views": [
            {
                "name": "CELMM - Prévia de Dados",
                "path": "views/06.CELMM_PREVIA_DADOS.py",
                "icon": "👁️",
                "url_path": "celmm_previa_dados",
                "default": True
            },
            {
                "name": "CELMM - Visualização Rápida",
                "path": "views/07.CELMM_VISUALIZACAO_RAPIDA.py",
                "icon": "🚀",
                "url_path": "celmm_visualizacao_rapida",
                "default": True
            }
        ]
    },
    {
        "category": "Administração do Sistema",
        "views": [
            {
                "name": "Administração do Sistema",
                "path": "views/99.Manutencao.py",
                "icon": "⚙️",
                "url_path": "administracao",
                "default": True
            }
        ]
    }
]

def get_all_view_paths() -> List[str]:
    """Retorna uma lista com todos os caminhos relativos das views disponíveis."""
    paths = []
    for cat in AVAILABLE_VIEWS:
        for v in cat["views"]:
            paths.append(v["path"])
    return paths

def get_view_metadata(path: str) -> Optional[Dict[str, Any]]:
    """Retorna os metadados de uma view dado o seu caminho relativo."""
    for cat in AVAILABLE_VIEWS:
        for v in cat["views"]:
            if v["path"] == path:
                return v
    return None

# ==============================================================================
# 2. CRIPTOGRAFIA DE SENHA
# ==============================================================================
def generate_salt() -> str:
    """Gera um salt criptográfico de 16 bytes em formato hexadecimal."""
    return os.urandom(16).hex()

def hash_password(password: str, salt: str) -> str:
    """Gera o hash PBKDF2-HMAC-SHA256 da senha com 100.000 iterações."""
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        bytes.fromhex(salt),
        100000
    ).hex()

def check_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verifica se a senha fornecida corresponde ao hash armazenado usando comparação constante."""
    try:
        calculated_hash = hash_password(password, salt)
        return hmac.compare_digest(calculated_hash, stored_hash)
    except Exception:
        return False

# ==============================================================================
# 3. GERENCIAMENTO DE SESSÃO & TOKENS (JWT)
# ==============================================================================
def create_token(username: str, expires_in_days: int = 7) -> str:
    """Gera um token JWT assinado para o usuário."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + timedelta(days=expires_in_days)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

def validate_token(token: str) -> Optional[User]:
    """Valida um token JWT e retorna a instância User correspondente do banco."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if not username:
            return None
        return get_user_by_username(username)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception):
        return None

# ==============================================================================
# 4. OPERAÇÕES DE USUÁRIO (CRUD)
# ==============================================================================
def get_user_by_username(username: str) -> Optional[User]:
    """Busca um usuário no banco pelo username."""
    if not username:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter(User.username == username.strip().lower()).first()
    except Exception as e:
        st.error(f"Erro ao buscar usuário: {e}")
        return None
    finally:
        db.close()

def get_all_users() -> List[User]:
    """Retorna todos os usuários cadastrados ordenados pelo ID."""
    db = SessionLocal()
    try:
        return db.query(User).order_by(User.id.asc()).all()
    except Exception as e:
        st.error(f"Erro ao listar usuários: {e}")
        return []
    finally:
        db.close()

def create_user(
    username: str,
    password: str,
    name: Optional[str] = None,
    views: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """Valida duplicidade, gera salt/hash e cria um novo usuário no banco."""
    username_clean = username.strip().lower() if username else ""
    if not username_clean:
        return False, "O nome de usuário (username) é obrigatório."
    
    if not password or len(password) < 4:
        return False, "A senha deve ter no mínimo 4 caracteres."
        
    if views is None:
        views = get_all_view_paths()
        
    db = SessionLocal()
    try:
        user_exist = db.query(User).filter(User.username == username_clean).first()
        if user_exist:
            return False, f"O usuário '{username_clean}' já está cadastrado."
            
        salt = generate_salt()
        data_hash = hash_password(password, salt)
        
        new_user = User(
            username=username_clean,
            name=name.strip() if name else None,
            data_hash=data_hash,
            salt=salt,
            views=views
        )
        db.add(new_user)
        db.commit()
        return True, f"Usuário '{username_clean}' criado com sucesso!"
    except Exception as e:
        db.rollback()
        return False, f"Erro ao criar usuário no banco de dados: {e}"
    finally:
        db.close()

def login_user(username: str, password: str) -> Optional[User]:
    """Verifica credenciais e retorna o usuário autenticado ou None."""
    username_clean = username.strip().lower() if username else ""
    if not username_clean or not password:
        return None
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username_clean).first()
        if not user:
            return None
            
        if check_password(password, user.data_hash, user.salt):
            return user
        return None
    except Exception as e:
        st.error(f"Erro ao processar login: {e}")
        return None
    finally:
        db.close()

def update_user(
    username: str,
    name: Optional[str] = None,
    views: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """Atualiza as informações cadastrais e permissões de views do usuário."""
    username_clean = username.strip().lower() if username else ""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username_clean).first()
        if not user:
            return False, "Usuário não encontrado."
            
        if name is not None:
            user.name = name.strip()
        if views is not None:
            user.views = views
            
        db.commit()
        return True, "Usuário atualizado com sucesso!"
    except Exception as e:
        db.rollback()
        return False, f"Erro ao atualizar usuário: {e}"
    finally:
        db.close()

def reset_password(username: str, new_password: str) -> Tuple[bool, str]:
    """Gera novo salt e hash para redefinir a senha do usuário."""
    username_clean = username.strip().lower() if username else ""
    if not new_password or len(new_password) < 4:
        return False, "A nova senha deve ter no mínimo 4 caracteres."
        
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username_clean).first()
        if not user:
            return False, "Usuário não encontrado."
            
        new_salt = generate_salt()
        new_hash = hash_password(new_password, new_salt)
        
        user.salt = new_salt
        user.data_hash = new_hash
        
        db.commit()
        return True, f"Senha do usuário '{username_clean}' redefinida com sucesso!"
    except Exception as e:
        db.rollback()
        return False, f"Erro ao redefinir senha: {e}"
    finally:
        db.close()

def delete_user(username: str) -> Tuple[bool, str]:
    """Remove um usuário do banco de dados (impede exclusão do admin padrão)."""
    username_clean = username.strip().lower() if username else ""
    if username_clean == "admin":
        return False, "Não é permitido excluir o usuário 'admin' padrão do sistema."
        
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username_clean).first()
        if not user:
            return False, "Usuário não encontrado."
            
        db.delete(user)
        db.commit()
        return True, f"Usuário '{username_clean}' removido com sucesso!"
    except Exception as e:
        db.rollback()
        return False, f"Erro ao excluir usuário: {e}"
    finally:
        db.close()

def init_db_and_admin_if_needed():
    """Garante que as tabelas existem no banco e cria o usuário 'admin' inicial caso a tabela users esteja vazia."""
    try:
        # Garante a criação de todas as tabelas mapeadas no SQLAlchemy
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        st.error(f"Erro ao inicializar tabelas do banco de dados: {e}")
        return

    db = SessionLocal()
    try:
        admin_exists = db.query(User).filter(User.username == "admin").first()
        if not admin_exists:
            initial_pass = os.getenv("ADMIN_INITIAL_PASSWORD", "admin123")
            salt = generate_salt()
            data_hash = hash_password(initial_pass, salt)
            admin_user = User(
                username="admin",
                name="Administrador do Sistema",
                data_hash=data_hash,
                salt=salt,
                views=get_all_view_paths()
            )
            db.add(admin_user)
            db.commit()
    except Exception as e:
        db.rollback()
        st.error(f"Erro ao inicializar usuário admin: {e}")
    finally:
        db.close()
