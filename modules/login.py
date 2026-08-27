import datetime
import streamlit as st
import extra_streamlit_components as stx
from modules.auth import login_user, create_token


def render_login_view(cookie_manager=None):
    """Renderiza o formulário de login centralizado da aplicação."""
    if cookie_manager is None:
        cookie_manager = stx.CookieManager(key="satellitum_standalone_cookie_manager")

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
            st.caption("Insira suas credenciais para acessar o sistema.")
            
            with st.form("login_form", clear_on_submit=False):
                username_input = st.text_input("Usuário:", placeholder="Digite seu nome de usuário").strip().lower()
                password_input = st.text_input("Senha:", type="password", placeholder="Digite sua senha")
                
                st.write("")
                submit_button = st.form_submit_button("Entrar", type="primary", use_container_width=True)
                
                if submit_button:
                    if not username_input or not password_input:
                        st.error("Por favor, preencha todos os campos.")
                    else:
                        user = login_user(username_input, password_input)
                        if user:
                            # Salva os dados na sessão e remove flag de logout
                            st.session_state["logged_out"] = False
                            st.session_state["user"] = user.to_dict()
                            
                            # Gera o token JWT e salva no cookie (7 dias de expiração)
                            token = create_token(user.username, expires_in_days=7)
                            expires_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
                            try:
                                cookie_manager.set("auth_token", token, expires_at=expires_date, key="set_login_token")
                            except Exception:
                                pass
                            
                            st.success(f"Bem-vindo(a), {user.name or user.username}!")
                            st.rerun()
                        else:
                            st.error("Credenciais inválidas. Verifique seu usuário e senha.")
                            
        st.caption("FlowBR | PPGRHS | Centro de Tecnologia — Versão Dev.26.08.2026")


if __name__ == "__main__":
    render_login_view()
