import streamlit as st
from modules.auth import (
    AVAILABLE_VIEWS,
    get_all_view_paths,
    get_all_users,
    get_user_by_username,
    create_user,
    update_user,
    reset_password,
    delete_user,
)

# ==============================================================================
# DIÁLOGOS ADMINISTRATIVOS (@st.dialog)
# ==============================================================================

@st.dialog("➕ Adicionar Novo Usuário", width="large")
def dialog_novo_usuario():
    st.markdown("Preencha as informações cadastrais e selecione as permissões de visualização do usuário.")
    
    col1, col2, col3 = st.columns([1.2, 1.5, 1.3])
    with col1:
        username = st.text_input("Usuário (Username) *", placeholder="ex: j_silva").strip().lower()
    with col2:
        name = st.text_input("Nome Completo", placeholder="ex: João Silva")
    with col3:
        password = st.text_input("Senha Inicial *", type="password", placeholder="Mínimo 4 caracteres")

    st.markdown("---")
    st.markdown("### 🔐 Permissões de Acesso por Tela")
    
    all_paths = get_all_view_paths()
    
    # Callback para marcar/desmarcar todos
    def toggle_all_new():
        val = st.session_state.get("toggle_all_new_chk", True)
        for p in all_paths:
            st.session_state[f"new_perm_{p}"] = val

    st.checkbox("Marcar / Desmarcar Todas as Telas", value=True, key="toggle_all_new_chk", on_change=toggle_all_new)
    
    selected_views = []
    # Renderiza colunas organizadas por categoria
    cols = st.columns(len(AVAILABLE_VIEWS))
    for idx, cat in enumerate(AVAILABLE_VIEWS):
        with cols[idx % len(cols)]:
            st.markdown(f"**{cat['category']}**")
            for v in cat["views"]:
                chk_key = f"new_perm_{v['path']}"
                if chk_key not in st.session_state:
                    st.session_state[chk_key] = True
                
                is_selected = st.checkbox(
                    f"{v.get('icon', '📄')} {v['name']}",
                    key=chk_key
                )
                if is_selected:
                    selected_views.append(v["path"])
                    
    st.markdown("---")
    c_btn1, c_btn2 = st.columns([1, 4])
    with c_btn1:
        if st.button("Salvar Usuário", type="primary", use_container_width=True):
            if not username:
                st.error("O campo Usuário (Username) é obrigatório.")
                return
            if not password:
                st.error("O campo Senha é obrigatório.")
                return
                
            success, msg = create_user(
                username=username,
                password=password,
                name=name,
                views=selected_views
            )
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


@st.dialog("✏️ Editar Usuário", width="large")
def dialog_editar_usuario(username: str):
    user = get_user_by_username(username)
    if not user:
        st.error("Usuário não encontrado.")
        return
        
    st.markdown(f"Editando informações de: **@{user.username}**")
    
    name = st.text_input("Nome Completo", value=user.name or "")
        
    st.markdown("---")
    st.markdown("### 🔐 Permissões de Acesso por Tela")
    
    all_paths = get_all_view_paths()
    curr_user_views = user.views if user.views is not None else []
    
    # Callback para marcar/desmarcar todos na edição
    def toggle_all_edit():
        val = st.session_state.get(f"toggle_all_edit_{username}", True)
        for p in all_paths:
            st.session_state[f"edit_perm_{username}_{p}"] = val

    all_initially_checked = len(curr_user_views) == len(all_paths)
    st.checkbox(
        "Marcar / Desmarcar Todas as Telas",
        value=all_initially_checked,
        key=f"toggle_all_edit_{username}",
        on_change=toggle_all_edit
    )
    
    selected_views = []
    cols = st.columns(len(AVAILABLE_VIEWS))
    for idx, cat in enumerate(AVAILABLE_VIEWS):
        with cols[idx % len(cols)]:
            st.markdown(f"**{cat['category']}**")
            for v in cat["views"]:
                chk_key = f"edit_perm_{username}_{v['path']}"
                if chk_key not in st.session_state:
                    st.session_state[chk_key] = (v["path"] in curr_user_views)
                
                is_selected = st.checkbox(
                    f"{v.get('icon', '📄')} {v['name']}",
                    key=chk_key
                )
                if is_selected:
                    selected_views.append(v["path"])
                    
    st.markdown("---")
    c_btn1, c_btn2 = st.columns([1, 4])
    with c_btn1:
        if st.button("Salvar Alterações", type="primary", use_container_width=True):
            success, msg = update_user(
                username=user.username,
                name=name,
                views=selected_views
            )
            if success:
                st.success(msg)
                current_user = st.session_state.get("user")
                if current_user and current_user.get("username") == user.username:
                    st.session_state.user["name"] = name
                    st.session_state.user["views"] = selected_views
                st.rerun()
            else:
                st.error(msg)


@st.dialog("🔑 Resetar Senha do Usuário", width="small")
def dialog_resetar_senha(username: str):
    st.markdown(f"Defina uma nova senha para o usuário **@{username}**:")
    new_pass = st.text_input("Nova Senha", type="password", key="reset_pass_input")
    confirm_pass = st.text_input("Confirme a Nova Senha", type="password", key="reset_pass_confirm")
    
    if st.button("Confirmar Redefinição", type="primary", use_container_width=True):
        if not new_pass or len(new_pass) < 4:
            st.error("A senha deve conter no mínimo 4 caracteres.")
            return
        if new_pass != confirm_pass:
            st.error("As senhas informadas não conferem.")
            return
            
        success, msg = reset_password(username, new_pass)
        if success:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)


@st.dialog("🗑️ Confirmar Exclusão de Usuário", width="small")
def dialog_confirmar_exclusao(username: str):
    st.warning(f"⚠️ Tem certeza que deseja excluir permanentemente o usuário **@{username}**?")
    st.markdown("Esta ação não poderá ser desfeita e revogará todos os acessos deste usuário imediatamente.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Sim, Excluir", type="primary", use_container_width=True):
            success, msg = delete_user(username)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    with col2:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()


# ==============================================================================
# RENDERIZADOR DA ABA DE GESTÃO DE USUÁRIOS
# ==============================================================================
def render_admin_users_tab():
    """Renderiza a interface completa de gestão de usuários e permissões."""
    current_user = st.session_state.get("user")
    
    c_sub, c_action = st.columns([4, 1.2], vertical_alignment="center")
    with c_sub:
        st.subheader("Gestão de Usuários & Permissões (RBAC)")
        st.caption("Cadastre usuários e controle o acesso granular às telas da aplicação.")
    with c_action:
        if st.button("➕ Novo Usuário", type="primary", use_container_width=True):
            dialog_novo_usuario()

    st.text("")

    users = get_all_users()
    all_paths = get_all_view_paths()
    total_views_count = len(all_paths)

    if not users:
        st.info("Nenhum usuário cadastrado no momento.")
        return

    # Cabeçalho da Tabela
    header_cols = st.columns([0.6, 1.8, 2.4, 2.0, 1.8, 1.8])
    with header_cols[0]:
        st.markdown("**ID**")
    with header_cols[1]:
        st.markdown("**Usuário**")
    with header_cols[2]:
        st.markdown("**Nome Completo**")
    with header_cols[3]:
        st.markdown("**Permissões**")
    with header_cols[4]:
        st.markdown("**Criado em**")
    with header_cols[5]:
        st.markdown("**Ações**")

    st.markdown("---")

    for u in users:
        cols = st.columns([0.6, 1.8, 2.4, 2.0, 1.8, 1.8])
        
        # ID
        with cols[0]:
            st.write(f"#{u.id}")
            
        # Username
        with cols[1]:
            st.markdown(f"**@{u.username}**")
            
        # Nome
        with cols[2]:
            st.write(u.name or "—")
            
        # Permissões
        with cols[3]:
            user_perm_views = u.views if u.views is not None else []
            count = len(user_perm_views)
            if count >= total_views_count:
                st.markdown("🟢 **Todas as Telas**")
            elif count == 0:
                st.markdown("🔴 *Nenhuma tela*")
            else:
                st.markdown(f"🟡 **{count}/{total_views_count} telas**")
                
        # Criado em
        with cols[4]:
            dt_str = u.created_at.strftime("%d/%m/%Y %H:%M") if u.created_at else "—"
            st.caption(dt_str)
            
        # Ações
        with cols[5]:
            act_c1, act_c2, act_c3 = st.columns(3)
            with act_c1:
                if st.button("✏️", key=f"btn_edit_{u.id}", help=f"Editar usuário @{u.username}"):
                    dialog_editar_usuario(u.username)
            with act_c2:
                if st.button("🔑", key=f"btn_reset_{u.id}", help=f"Resetar senha de @{u.username}"):
                    dialog_resetar_senha(u.username)
            with act_c3:
                # Regra de Segurança: Não permitir exclusão do admin padrão ou do usuário atualmente logado
                is_disabled = (u.username == "admin") or (current_user and u.username == current_user.get("username"))
                if st.button("🗑️", key=f"btn_del_{u.id}", help=f"Excluir @{u.username}", disabled=is_disabled):
                    dialog_confirmar_exclusao(u.username)
                    
        st.markdown("<hr style='margin: 4px 0; border-color: rgba(255,255,255,0.1);'>", unsafe_allow_html=True)
