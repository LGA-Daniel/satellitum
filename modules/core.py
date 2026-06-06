import ee
import os
import streamlit as st
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert
from modules.models import HistoricoExecucao, MetadadosImagens

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