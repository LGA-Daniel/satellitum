import streamlit as st
import extra_streamlit_components as stx

from modules.auth import (
    AVAILABLE_VIEWS,
    validate_token,
    init_db_and_admin_if_needed
)
from modules.login import render_login_view

# Configuração base da página
st.set_page_config(
    page_title="Satellitum",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Injeta CSS global da aplicação
st.html("""
    <style>
        /* Oculta as páginas de prévia e visualização rápida do menu lateral se presentes */
        a[href*="celmm_previa_dados"],
        a[href*="celmm_visualizacao_rapida"] {
            display: none !important;
        }
        
        /* Ajusta a largura global das janelas modais (st.dialog) */
        @media (min-width: 768px) {
            div[data-testid="stDialog"] div[role="dialog"],
            div[data-testid="stDialog"] div[aria-modal="true"],
            div[data-testid="stDialog"] > div:first-child {
                width: 60vw !important;
                max-width: 60vw !important;
            }
        }
        @media (max-width: 767px) {
            div[data-testid="stDialog"] div[role="dialog"],
            div[data-testid="stDialog"] div[aria-modal="true"],
            div[data-testid="stDialog"] > div:first-child {
                width: 92vw !important;
                max-width: 92vw !important;
            }
        }
        
        /* Estilização do Container de Login */
        .login-card {
            background-color: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 32px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
        }
    </style>
""")






# Garante inicialização do banco de dados e usuário admin padrão
@st.cache_resource(show_spinner=False)
def setup_database():
    init_db_and_admin_if_needed()
    return True

setup_database()

# Inicializa o gerenciador de cookies
cookie_manager = stx.CookieManager(key="satellitum_auth_cookie_manager")

# ==============================================================================
# 0. CAPTURA E PROCESSAMENTO AUTOMÁTICO DO RETORNO GOOGLE OAUTH
# ==============================================================================
if "code" in st.query_params:
    raw_code = st.query_params["code"]
    if isinstance(raw_code, list):
        raw_code = raw_code[0]
        
    last_processed = st.session_state.get("_last_processed_oauth_code")
    if raw_code and raw_code != last_processed:
        st.session_state["_last_processed_oauth_code"] = raw_code
        try:
            from modules.google_auth import get_tokens, processar_e_salvar_tokens
            tokens = get_tokens(raw_code)
            if "access_token" in tokens:
                processar_e_salvar_tokens(tokens)
                st.toast("🎉 Conta Google autenticada e credenciais salvas com sucesso!", icon="✅")
                st.query_params.clear()
                st.rerun()
            else:
                err_msg = tokens.get("error_description") or tokens.get("error") or "Falha ao obter tokens."
                st.toast(f"⚠️ Erro no Google OAuth: {err_msg}", icon="❌")
                st.query_params.clear()
        except Exception as e:
            st.toast(f"⚠️ Erro ao processar tokens: {e}", icon="❌")
            st.query_params.clear()

# ==============================================================================
# 1. VERIFICAÇÃO AUTOMÁTICA DE SESSÃO & COOKIE JWT
# ==============================================================================
if ("user" not in st.session_state or st.session_state.user is None) and not st.session_state.get("logged_out"):
    auth_token = cookie_manager.get(cookie="auth_token")
    if auth_token:
        user_instance = validate_token(auth_token)
        if user_instance:
            st.session_state["user"] = user_instance.to_dict()
            st.rerun()

# ==============================================================================
# 2. RENDERIZAÇÃO DA TELA DE LOGIN (SEM BARRA LATERAL)
# ==============================================================================
if "user" not in st.session_state or st.session_state.user is None:
    # Renderiza apenas a tela de login com a barra lateral totalmente oculta
    pg_login = st.navigation([st.Page(lambda: render_login_view(cookie_manager), title="Login", icon="🔒")], position="hidden")
    pg_login.run()
    st.stop()

# ==============================================================================
# 3. FLUXO: USUÁRIO AUTENTICADO (NAVEGAÇÃO DINÂMICA RBAC)
# ==============================================================================
logged_user = st.session_state.user
user_views = logged_user.get("views", [])

# Sidebar: Informações do Usuário e Botão de Logout
with st.sidebar:
    st.markdown(f"**Operador:** {logged_user.get('name') or logged_user.get('username')}")
    
    if st.button("🚪 Sair", use_container_width=True, key="btn_logout_sidebar"):
        st.session_state["logged_out"] = True
        st.session_state["user"] = None
        try:
            cookie_manager.delete("auth_token")
        except Exception:
            pass
        for k in list(st.session_state.keys()):
            if k not in ["satellitum_auth_cookie_manager", "logged_out"]:
                try:
                    del st.session_state[k]
                except Exception:
                    pass
        st.rerun()
        
    st.markdown("---")

# Montagem do Dicionário de Páginas Baseado em Permissões
pages_dict = {}

for category_data in AVAILABLE_VIEWS:
    cat_name = category_data["category"]
    cat_pages = []
    
    for v in category_data["views"]:
        v_path = v["path"]
        
        # Acesso definido diretamente pela presença da view na lista de permissões do usuário
        has_access = (v_path in user_views) or (logged_user.get("username") == "admin")
        
        if has_access:
            page_kwargs = {
                "page": v_path,
                "title": v["name"],
                "icon": v.get("icon")
            }
            if v.get("url_path"):
                page_kwargs["url_path"] = v["url_path"]
                
            cat_pages.append(st.Page(**page_kwargs))
            
    if cat_pages:
        pages_dict[cat_name] = cat_pages

# Se o usuário não tiver nenhuma view permitida, fornece tela de aviso amigável
if not pages_dict:
    st.warning("⚠️ Seu usuário não possui permissão para acessar nenhuma tela no momento. Entre em contato com um administrador.")
    st.stop()

# Inicializa e executa o sistema de navegação do Streamlit
pg = st.navigation(pages_dict, position="sidebar")
pg.run()