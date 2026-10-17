import streamlit as st
import datetime as dt
import pandas as pd
import html
import logging

logger = logging.getLogger(__name__)

from modules.api_gee import (
    init_gee,
    calcular_cronograma_passagens,
    gerar_relatorio_txt_cronograma,
    ASSET_CELMM_ROI
)

# Configuração da página
st.set_page_config(
    page_title="Satellitum | Órbitas CELMM",
    page_icon="🛰️",
    layout="wide"
)

current_user = st.session_state.get("user")
if not current_user:
    st.error("⛔ Acesso não autorizado. Faça login para acessar esta página.")
    st.stop()

# Estilização complementar
st.markdown("""
<style>
    .proxima-passagem-banner {
        background: linear-gradient(90deg, rgba(30, 58, 138, 0.35) 0%, rgba(15, 23, 42, 0.55) 100%);
        border-left: 4px solid #38bdf8;
        border-radius: 8px;
        padding: 12px 18px;
        margin-top: 10px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Cabeçalho da página
st.title("🛰️ Cronograma de Órbitas | CELMM")

# Botão de Ação e Carregamento
col_info, col_dl, col_btn = st.columns([4,2,2])

with col_btn:
    btn_atualizar = st.button("🔄 Atualizar", type="primary", use_container_width=True)

# Inicializa ou atualiza os dados na sessão
carregar_dados = btn_atualizar or ("cronograma_celmm_data" not in st.session_state)

if carregar_dados:
    with st.spinner("Consultando órbitas e projetando passagens para os próximos 90 dias..."):
        try:
            dados = calcular_cronograma_passagens(dias_a_frente=90)
            st.session_state["cronograma_celmm_data"] = dados
            st.session_state["cronograma_celmm_updated_at"] = dt.datetime.now()
            if btn_atualizar:
                st.toast("Cronograma orbital atualizado com sucesso!", icon="✅")
        except Exception as e:
            logger.error(f"Erro ao calcular cronograma orbital: {e}", exc_info=True)
            st.error("Não foi possível calcular o cronograma orbital no momento.")
            st.info("💡 Verifique se as credenciais do Google Earth Engine estão ativas na aba **Administração do Sistema > Autenticação Google**.")

dados = st.session_state.get("cronograma_celmm_data")

if dados and dados.get("cronograma"):
    cronograma = dados["cronograma"]
    data_ate = dados.get("data_ate", dt.date.today() + dt.timedelta(days=90))
    ultima_atualizacao = st.session_state.get("cronograma_celmm_updated_at")

    with col_info:
        data_ini_fmt = dt.date.today().strftime('%d/%m/%Y')
        data_fim_fmt = data_ate.strftime('%d/%m/%Y')
        hora_upd = ultima_atualizacao.strftime('%H:%M:%S') if ultima_atualizacao else ""
        st.markdown(f"**Janela de Projeção:** `{data_ini_fmt}` a `{data_fim_fmt}` (90 dias)")
        st.caption(f"*Última atualização: {hora_upd} | Horário médio de sobrevoo: 09h30 às 10h15 local.*")

    # Banner com a próxima passagem imediata
    proxima = cronograma[0]
    dias_prox = proxima["dias_restantes"]
    txt_tempo = "Hoje" if dias_prox == 0 else ("Amanhã" if dias_prox == 1 else f"Em {dias_prox} dias")

    dias_semana_nomes = {
        0: 'Segunda-feira', 1: 'Terça-feira', 2: 'Quarta-feira',
        3: 'Quinta-feira', 4: 'Sexta-feira', 5: 'Sábado', 6: 'Domingo'
    }
    dia_sem_prox = dias_semana_nomes.get(proxima["data"].weekday(), "")
    dupla_badge = " — ⭐ <b>S2 + Landsat no mesmo dia</b>" if proxima.get("dupla_passagem") else ""
    sat_nomes_prox = [x.get("satelite") or x.get("label", "").split(" (")[0] for x in proxima.get("satelites", [])]
    sat_nomes_prox = list(dict.fromkeys(sat_nomes_prox))
    sat_str_prox = ", ".join(sat_nomes_prox) if sat_nomes_prox else proxima.get("satelites_str", "")
    safe_sat_str_prox = html.escape(str(sat_str_prox))

    st.markdown(f"""
    <div class="proxima-passagem-banner">
        <strong>Próxima Passagem:</strong> {proxima['data'].strftime('%d/%m/%Y')} ({dia_sem_prox}) — <em>{txt_tempo}</em>
        <br><strong> Satélites:</strong> {safe_sat_str_prox}{dupla_badge}
    </div>
    """, unsafe_allow_html=True)

    # Montagem da Tabela com todos os registros dos 90 dias
    tabela_dados = []

    for item in cronograma:
        dia_obj = item["data"]
        sem_nome = dias_semana_nomes.get(dia_obj.weekday(), '')
        
        d_dias = item["dias_restantes"]
        if d_dias == 0:
            tempo_str = "Hoje"
        elif d_dias == 1:
            tempo_str = "Amanhã"
        else:
            tempo_str = f"Em {d_dias} dias"

        s2_list = [x.get("satelite") or x.get("label", "").split(" (")[0] for x in item.get("satelites", []) if x.get("tipo") == "Sentinel-2"]
        ls_list = [x.get("satelite") or x.get("label", "").split(" (")[0] for x in item.get("satelites", []) if x.get("tipo") == "Landsat"]
        s2_list = list(dict.fromkeys(s2_list))
        ls_list = list(dict.fromkeys(ls_list))

        tabela_dados.append({
            "Data": dia_obj.strftime('%d/%m/%Y'),
            "Dia da Semana": sem_nome,
            "Previsão": tempo_str,
            "Sentinel-2": f"✅ {', '.join(s2_list)}" if s2_list else "—",
            "Landsat": f"✅ {', '.join(ls_list)}" if ls_list else "—"
        })

    df_cronograma = pd.DataFrame(tabela_dados)

    # Exibição direta em formato de tabela
    st.dataframe(
        df_cronograma,
        use_container_width=True,
        hide_index=True,
        height=580,
        column_config={
            "Data": st.column_config.TextColumn("Data", width="small"),
            "Dia da Semana": st.column_config.TextColumn("Dia da Semana", width="medium"),
            "Previsão": st.column_config.TextColumn("Previsão", width="small"),
            "Sentinel-2": st.column_config.TextColumn("Sentinel-2", width="medium"),
            "Landsat": st.column_config.TextColumn("Landsat", width="medium"),
        }
    )

    # Exportações
    with col_dl:
        conteudo_txt = gerar_relatorio_txt_cronograma(
            cronograma=cronograma,
            data_ate=data_ate
        )
        st.download_button(
            label="📄 Baixar Relatório (.txt)",
            data=conteudo_txt,
            file_name=f"passagens_satelite_CELMM_90d_{dt.date.today().strftime('%Y%m%d')}.txt",
            mime="text/plain",
            use_container_width=True
        )

elif not dados:
    st.info("Nenhum cronograma disponível no momento. Clique em '🔄 Atualizar' para consultar.")
