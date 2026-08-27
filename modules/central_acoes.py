import streamlit as st
import pandas as pd
import datetime
import inspect
from modules.db import criar_tarefa_background, obter_df_pixels_por_imagem_ids
from modules.data_export import preparar_arquivo_exportacao, limpar_arquivos_exportacao_disco

def on_dismiss_acoes_callback():
    st.session_state['show_acoes_modal'] = False
    if 'export_in_place_formato' in st.session_state:
        del st.session_state['export_in_place_formato']
    limpar_arquivos_exportacao_disco()

def _acoes_produtos_dialog_impl(selected_rows, valid_drive_selected, valid_db_selected, df_filtrado, map_nome_id, map_nome_id_lower):
    total_sel = len(selected_rows)
    total_drive = len(valid_drive_selected)
    total_db = len(valid_db_selected)
    
    st.markdown(f"""
        <div style="background-color: rgba(2, 132, 199, 0.08); border: 1px solid rgba(2, 132, 199, 0.25); border-radius: 8px; padding: 10px 16px; margin-bottom: 18px; display: flex; justify-content: space-around; text-align: center;">
            <div><strong>Selecionados:</strong> <span style="color: var(--primary-color);">{total_sel}</span></div>
            <div><strong>Processados:</strong> <span style="color: #22c55e;">{total_drive}</span></div>
            <div><strong>Sincronizados:</strong> <span style="color: #3b82f6;">{total_db}</span></div>
        </div>
    """, unsafe_allow_html=True)
    
    col_g1, col_g2 = st.columns(2)
    
    # ------------------ COLUNA 1 ------------------
    with col_g1:
        # AÇÃO 1: Processo Completo
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">⚙️ Processamento Automático</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Executa toda a série de processamento: GEE + Banco de Dados.</p>
                </div>
            """, unsafe_allow_html=True)
            if st.button("Executar Processamento Automático", type="primary", use_container_width=True, disabled=total_sel == 0, key="modal_btn_full"):
                st.session_state['show_acoes_modal'] = False
                selected_rows_list = []
                for _, r in selected_rows.iterrows():
                    d_str = r['Data do Produto'].strftime('%Y-%m-%d') if isinstance(r['Data do Produto'], (datetime.date, datetime.datetime)) else str(r['Data do Produto'])
                    selected_rows_list.append({
                        "id": int(r['id']),
                        "Data do Produto": d_str,
                        "Tamanho Pixel (m)": int(r['Tamanho Pixel (m)']),
                        "Satélite": str(r['Satélite']),
                        "Grade MGRS": str(r['Grade MGRS']) if pd.notna(r['Grade MGRS']) else None,
                        "Pixels Válidos": int(r['Pixels Válidos']),
                        "zenital": float(r['zenital']) if pd.notna(r['zenital']) else None
                    })
                
                df_filtrado_list = []
                for _, r in df_filtrado.iterrows():
                    d_str = r['data'].strftime('%Y-%m-%d') if isinstance(r['data'], (datetime.date, datetime.datetime)) else str(r['data'])
                    df_filtrado_list.append({
                        "id": int(r['id']),
                        "data": d_str,
                        "satelite": str(r['satelite']),
                        "z_grade_mgrs": str(r['z_grade_mgrs']) if pd.notna(r['z_grade_mgrs']) else None,
                        "tamanho_pixel": int(r['tamanho_pixel']),
                        "zenital": float(r['zenital']) if pd.notna(r['zenital']) else None
                    })

                payload = {
                    "selected_rows": selected_rows_list,
                    "df_filtrado_data": df_filtrado_list,
                    "map_nome_id": map_nome_id
                }
                
                tarefa_id = criar_tarefa_background("FULL_PIPELINE", payload, len(selected_rows_list))
                if tarefa_id:
                    st.session_state[f"tarefa_dismissed_{tarefa_id}"] = False
                    st.session_state["tarefa_id_monitorada"] = tarefa_id
                    st.rerun()

        # AÇÃO 2: Sincronizar com o Banco
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">🔄 Sincronizar Produtos</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Realiza a leitura de produtos previamente processados e sincroniza com a a base de dados.</p>
                </div>
            """, unsafe_allow_html=True)
            if st.button("Sincronizar com o Banco de Dados", type="secondary", use_container_width=True, disabled=total_drive == 0, key="modal_btn_sinc"):
                st.session_state['show_acoes_modal'] = False
                selected_rows_list = []
                for _, r in valid_drive_selected.iterrows():
                    d_str = r['Data do Produto'].strftime('%Y-%m-%d') if isinstance(r['Data do Produto'], (datetime.date, datetime.datetime)) else str(r['Data do Produto'])
                    selected_rows_list.append({
                        "id": int(r['id']),
                        "Data do Produto": d_str,
                        "Tamanho Pixel (m)": int(r['Tamanho Pixel (m)']),
                        "Satélite": str(r['Satélite']),
                        "Grade MGRS": str(r['Grade MGRS']) if pd.notna(r['Grade MGRS']) else None,
                        "zenital": float(r['zenital']) if pd.notna(r['zenital']) else None
                    })
                
                payload = {
                    "selected_rows": selected_rows_list,
                    "map_nome_id": map_nome_id
                }
                
                tarefa_id = criar_tarefa_background("CSV_INGEST", payload, len(selected_rows_list))
                if tarefa_id:
                    st.session_state[f"tarefa_dismissed_{tarefa_id}"] = False
                    st.session_state["tarefa_id_monitorada"] = tarefa_id
                    st.rerun()

    # ------------------ COLUNA 2 ------------------
    with col_g2:
        # AÇÃO 3: Processar no GEE
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">🌍 Processar no GEE</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Submete o Processamento da cena no Google Earth Engine e disponibiliza o produto para sincronização futura.</p>
                </div>
            """, unsafe_allow_html=True)
            if st.button("Processar no GEE", type="secondary", use_container_width=True, disabled=total_sel == 0, key="modal_btn_gee"):
                st.session_state['show_acoes_modal'] = False
                selected_rows_list = []
                for _, r in selected_rows.iterrows():
                    d_str = r['Data do Produto'].strftime('%Y-%m-%d') if isinstance(r['Data do Produto'], (datetime.date, datetime.datetime)) else str(r['Data do Produto'])
                    selected_rows_list.append({
                        "Data do Produto": d_str,
                        "Satélite": str(r['Satélite']),
                        "Pixels Válidos": int(r['Pixels Válidos'])
                    })
                
                df_filtrado_list = []
                for _, r in df_filtrado.iterrows():
                    d_str = r['data'].strftime('%Y-%m-%d') if isinstance(r['data'], (datetime.date, datetime.datetime)) else str(r['data'])
                    df_filtrado_list.append({
                        "data": d_str,
                        "satelite": str(r['satelite']),
                        "z_grade_mgrs": str(r['z_grade_mgrs']) if pd.notna(r['z_grade_mgrs']) else None,
                        "tamanho_pixel": int(r['tamanho_pixel'])
                    })

                payload = {
                    "selected_rows": selected_rows_list,
                    "df_filtrado_data": df_filtrado_list
                }
                
                tarefa_id = criar_tarefa_background("GEE_EXPORT", payload, len(selected_rows_list))
                if tarefa_id:
                    st.session_state[f"tarefa_dismissed_{tarefa_id}"] = False
                    st.session_state["tarefa_id_monitorada"] = tarefa_id
                    st.rerun()

        # AÇÃO 4: Baixar CSVs
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">📥 Baixar Produtos</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Baixa os produtos processados em formato CSV diretamente para o seu computador.</p>
                </div>
            """, unsafe_allow_html=True)
            if st.button("Baixar Arquivos CSV", type="secondary", use_container_width=True, disabled=total_drive == 0, key="modal_btn_download"):
                st.session_state['show_acoes_modal'] = False
                st.session_state['show_download_modal'] = True
                st.rerun()

    # ------------------ LINHA INFERIOR ------------------
    col_inf1, col_inf2 = st.columns(2)
    
    with col_inf1:
        # AÇÃO 5: Visualizar Dados
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">🗺️ Visualizar Dados</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Visualizar prévia dos dados/pixels brutos e imagens reconstituídas.</p>
                </div>
            """, unsafe_allow_html=True)
            pode_ver = (total_db == 1 and total_sel == 1)
            
            if pode_ver:
                help_vis = "Abre a prévia de dados e composição RGB para o produto selecionado."
            elif total_sel == 0:
                help_vis = "Selecione exatamente 1 produto na tabela para visualizar seus dados."
            elif total_sel > 1:
                help_vis = f"A visualização de dados suporta apenas 1 produto por vez. Você selecionou {total_sel} produtos."
            else:
                help_vis = "O produto selecionado ainda não foi sincronizado com o banco de dados. Sincronize-o antes de visualizar."

            if st.button(
                "Abrir Visualização de Dados", 
                type="secondary", 
                use_container_width=True, 
                disabled=not pode_ver, 
                help=help_vis,
                key="modal_btn_vis"
            ):
                st.session_state['show_acoes_modal'] = False
                id_img = int(valid_db_selected.iloc[0]['id'])
                with st.spinner("Carregando amostra de dados para visualização..."):
                    df_pixels = obter_df_pixels_por_imagem_ids([id_img], limit=500)
                    st.session_state["df_pixels_carregados"] = df_pixels
                    st.session_state["ids_pixels_carregados"] = [id_img]
                    st.session_state["carregado_parcial"] = True
                    st.switch_page("views/06.CELMM_PREVIA_DADOS.py")

    with col_inf2:
        # AÇÃO 6: Exportar Dados (CSV / Excel)
        formato_in_place = st.session_state.get('export_in_place_formato')
        with st.container(border=True, height=175):
            st.markdown("""
                <div style="min-height: 90px; margin-bottom: 8px;">
                    <h4 style="margin: 0 0 4px 0; font-size: 1.15em; font-weight: 600;">📊 Exportar Dados</h4>
                    <p style="margin: 0; font-size: 0.85em; opacity: 0.75; line-height: 1.35;">Exportar o conjunto de dados dos produtos selecionados em um arquivo único. </p>
                </div>
            """, unsafe_allow_html=True)
            pode_exportar = total_db >= 1
            
            if pode_exportar:
                help_csv = f"Gera arquivo CSV para os {total_db} produto(s) sincronizado(s)."
                help_xlsx = f"Gera planilha Excel (.xlsx) para os {total_db} produto(s) sincronizado(s)."
            elif total_sel == 0:
                help_csv = help_xlsx = "Selecione ao menos 1 produto na tabela para exportar."
            else:
                help_csv = help_xlsx = "Nenhum dos produtos selecionados possui dados salvos no banco. Sincronize antes de exportar."

            if formato_in_place and pode_exportar:
                ids_exp = [int(x) for x in valid_db_selected['id'].tolist()]
                with st.spinner(f"Processando e gravando {formato_in_place.upper()}..."):
                    try:
                        cache = preparar_arquivo_exportacao(ids_exp, formato_in_place)
                        col_dl, col_reset = st.columns([5, 5])
                        with col_dl:
                            with open(cache["file_path"], "rb") as f_exp:
                                st.download_button(
                                    label=f"⬇️ Baixar {formato_in_place.upper()} ({cache['file_size_mb']} MB)",
                                    data=f_exp,
                                    file_name=cache["file_name"],
                                    mime=cache["mime_type"],
                                    type="primary",
                                    use_container_width=True,
                                    key="btn_download_direct_inplace"
                                )
                        with col_reset:
                            if st.button("🔄 Alternar formato", help="Alternar formato", use_container_width=True, key="btn_reset_export_fmt"):
                                del st.session_state['export_in_place_formato']
                                limpar_arquivos_exportacao_disco()
                                st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
            else:
                col_btn_csv, col_btn_xlsx = st.columns(2)
                with col_btn_csv:
                    if st.button(
                        "📄 Gerar CSV", 
                        type="secondary", 
                        use_container_width=True, 
                        disabled=not pode_exportar, 
                        help=help_csv, 
                        key="modal_btn_export_csv"
                    ):
                        st.session_state['export_in_place_formato'] = 'csv'
                        st.rerun()

                with col_btn_xlsx:
                    if st.button(
                        "📊 Gerar Excel", 
                        type="secondary", 
                        use_container_width=True, 
                        disabled=not pode_exportar, 
                        help=help_xlsx, 
                        key="modal_btn_export_xlsx"
                    ):
                        st.session_state['export_in_place_formato'] = 'xlsx'
                        st.rerun()

def central_acoes_dialog(selected_rows, valid_drive_selected, valid_db_selected, df_filtrado, map_nome_id, map_nome_id_lower):
    sig_dialog = inspect.signature(st.dialog)
    dialog_kwargs = {"width": "large"} if "width" in sig_dialog.parameters else {}

    if 'on_dismiss' in sig_dialog.parameters:
        @st.dialog("Central de Processamento", on_dismiss=on_dismiss_acoes_callback, **dialog_kwargs)
        def _inner(s_rows, v_drive, v_db, df_f, m_id, m_id_lower):
            _acoes_produtos_dialog_impl(s_rows, v_drive, v_db, df_f, m_id, m_id_lower)
        _inner(selected_rows, valid_drive_selected, valid_db_selected, df_filtrado, map_nome_id, map_nome_id_lower)
    else:
        @st.dialog("Central de Processamento", dismissible=True, **dialog_kwargs)
        def _inner(s_rows, v_drive, v_db, df_f, m_id, m_id_lower):
            _acoes_produtos_dialog_impl(s_rows, v_drive, v_db, df_f, m_id, m_id_lower)
        _inner(selected_rows, valid_drive_selected, valid_db_selected, df_filtrado, map_nome_id, map_nome_id_lower)
