import ee
import psycopg2
import os
import streamlit as st

def get_db_connection():
    """Retorna a conexão com o banco de dados PostgreSQL."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "satellitum_db"),
        database=os.getenv("DB_NAME", "satellitum"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASS", "admin_password")
    )

def registrar_historico(nome_arquivo, script, status_execucao):
    """Grava o log de execução no banco."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = "INSERT INTO historico_execucoes (nome_arquivo, script, status) VALUES (%s, %s, %s);"
        cursor.execute(query, (nome_arquivo, script, status_execucao))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        st.error(f"Erro ao conectar ao banco de dados: {e}")

@st.cache_resource
def init_gee():
    """Inicializa o GEE apenas uma vez por sessão."""
    try:
        ee.Initialize()
        return True
    except Exception as e:
        st.error(f"Erro ao inicializar o Earth Engine: {e}. Verifique as credenciais.")
        return False