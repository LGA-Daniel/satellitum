import datetime
import streamlit as st
import extra_streamlit_components as stx

from modules.auth import (
    AVAILABLE_VIEWS,
    get_all_view_paths,
    login_user,
    create_token,
    validate_token,
    init_db_and_admin_if_needed
)

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
# 1. VERIFICAÇÃO AUTOMÁTICA DE SESSÃO & COOKIE JWT
# ==============================================================================
if "user" not in st.session_state or st.session_state.user is None:
    auth_token = cookie_manager.get(cookie="auth_token")
    if auth_token:
        user_instance = validate_token(auth_token)
        if user_instance:
            st.session_state["user"] = user_instance.to_dict()
            st.rerun()

# ==============================================================================
# 2. FLUXO: USUÁRIO NÃO AUTENTICADO (TELA DE LOGIN)
# ==============================================================================
if "user" not in st.session_state or st.session_state.user is None:
    col_l, col_center, col_r = st.columns([1, 1.8, 1])
    with col_center:
        st.write("")
        st.write("")
        st.markdown(
            """
            <div style="text-align: center; margin-bottom: 24px;">
                <h1 style="margin-bottom: 4px; font-size: 2.4rem;">🛰️ Satellitum</h1>
                <p style="color: #888888; font-size: 1.05rem;">Sistema de Processamento e Armazenamento de Produtos Orbitais</p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        with st.container(border=True):
            st.markdown("### 🔐 Autenticação de Usuário")
            st.caption("Insira suas credenciais para acessar o painel.")
            
            with st.form("login_form", clear_on_submit=False):
                username_input = st.text_input("Usuário", placeholder="Digite seu nome de usuário").strip().lower()
                password_input = st.text_input("Senha", type="password", placeholder="Digite sua senha")
                
                st.write("")
                submit_button = st.form_submit_button("Entrar no Sistema", type="primary", use_container_width=True)
                
                if submit_button:
                    if not username_input or not password_input:
                        st.error("Por favor, preencha todos os campos.")
                    else:
                        user = login_user(username_input, password_input)
                        if user:
                            # Salva os dados na sessão
                            st.session_state["user"] = user.to_dict()
                            
                            # Gera o token JWT e salva no cookie (7 dias de expiração)
                            token = create_token(user.username, expires_in_days=7)
                            expires_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
                            cookie_manager.set("auth_token", token, expires_at=expires_date, key="set_login_token")
                            
                            st.success(f"Bem-vindo(a), {user.name or user.username}!")
                            st.rerun()
                        else:
                            st.error("Credenciais inválidas. Verifique seu usuário e senha.")
                            
        st.caption("PPGRHS | Centro de Tecnologia — Versão Dev.02.06-2026")
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
        cookie_manager.delete("auth_token", key="logout_token_del")
        st.session_state.clear()
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
pg = st.navigation(pages_dict)
pg.run()