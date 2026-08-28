import os
import datetime
from typing import Optional
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert
from modules.models import HistoricoExecucao, MetadadosImagens, CelmmPixels, BackgroundTask, User

# Configurações do Banco de Dados a partir do ambiente (.env)
DB_HOST = os.getenv("DB_HOST", "satellitum_db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME") or os.getenv("POSTGRES_DB", "satellitum")
DB_USER = os.getenv("DB_USER") or os.getenv("POSTGRES_USER", "postgres")
DB_PASS = os.getenv("DB_PASS") or os.getenv("POSTGRES_PASSWORD", "")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Criação do Engine do SQLAlchemy com gerenciamento robusto do pool de conexões
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    pool_pre_ping=True
)
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

def verificar_metadados_existentes(lista_dados: list, tamanho_pixel: int) -> list:
    """Verifica quais datas da lista de metadados já estão cadastradas no banco."""
    db = SessionLocal()
    try:
        datas_conflito = []
        for item in lista_dados:
            data_val = str(item.get('Data'))
            satelite_val = str(item.get('Satelite'))
            mgrs_val = str(item.get('Z_Grade_MGRS')) if item.get('Z_Grade_MGRS') is not None else None
            
            query = db.query(MetadadosImagens).filter(
                MetadadosImagens.data == data_val,
                MetadadosImagens.satelite == satelite_val,
                MetadadosImagens.tamanho_pixel == int(tamanho_pixel)
            )
            if mgrs_val is not None:
                query = query.filter(MetadadosImagens.z_grade_mgrs == mgrs_val)
            else:
                query = query.filter(MetadadosImagens.z_grade_mgrs.is_(None))
                
            if query.first() is not None:
                datas_conflito.append(data_val)
        return sorted(list(set(datas_conflito)))
    except Exception as e:
        st.error(f"Erro ao verificar metadados no banco: {e}")
        return []
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

def salvar_pixels_bulk(df_pixels) -> int:
    """Insere ou atualiza registros de pixels na tabela celmm_pixels usando PostgreSQL COPY via tabela temporária de estágio."""
    if df_pixels.empty:
        return 0
        
    import io
    db = SessionLocal()
    try:
        colunas = [
            'metadados_imagem_id', 'system_index', 'data', 'satelite', 
            'z_grade_mgrs', 'tamanho_pixel', 'zenital', 
            'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12', 
            'latitude', 'longitude', 'geo'
        ]
        
        csv_buffer = io.StringIO()
        df_pixels.to_csv(csv_buffer, index=False, header=True, columns=colunas, sep=',')
        csv_buffer.seek(0)
        
        connection = db.connection()
        dbapi_conn = getattr(connection, "dbapi_connection", getattr(connection, "connection", None))
        if dbapi_conn is None:
            raise RuntimeError("Não foi possível obter a conexão DBAPI bruta do SQLAlchemy.")
            
        cursor = dbapi_conn.cursor()
        cursor.execute("CREATE TEMP TABLE temp_celmm_pixels (LIKE celmm_pixels INCLUDING DEFAULTS) ON COMMIT DROP;")
        
        colunas_str = ", ".join([f'"{col}"' for col in colunas])
        copy_sql = f"COPY temp_celmm_pixels ({colunas_str}) FROM STDIN WITH CSV HEADER;"
        cursor.copy_expert(copy_sql, csv_buffer)
        
        insert_sql = f"""
            INSERT INTO celmm_pixels ({colunas_str})
            SELECT {colunas_str} FROM temp_celmm_pixels
            ON CONFLICT ON CONSTRAINT uq_celmm_pixel DO UPDATE SET
                "B1" = EXCLUDED."B1",
                "B2" = EXCLUDED."B2",
                "B3" = EXCLUDED."B3",
                "B4" = EXCLUDED."B4",
                "B5" = EXCLUDED."B5",
                "B6" = EXCLUDED."B6",
                "B7" = EXCLUDED."B7",
                "B8" = EXCLUDED."B8",
                "B8A" = EXCLUDED."B8A",
                "B9" = EXCLUDED."B9",
                "B11" = EXCLUDED."B11",
                "B12" = EXCLUDED."B12",
                "latitude" = EXCLUDED."latitude",
                "longitude" = EXCLUDED."longitude",
                "geo" = EXCLUDED."geo",
                "data" = EXCLUDED."data",
                "satelite" = EXCLUDED."satelite",
                "z_grade_mgrs" = EXCLUDED."z_grade_mgrs",
                "tamanho_pixel" = EXCLUDED."tamanho_pixel",
                "zenital" = EXCLUDED."zenital",
                "data_registro" = NOW();
        """
        cursor.execute(insert_sql)
        db.commit()
        return len(df_pixels)
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

def marcar_imagem_sem_pixels_processada(metadados_imagem_id: int, data: str, satelite: str, z_grade_mgrs: str, tamanho_pixel: int, zenital: float = None):
    """Insere um registro marcador na tabela celmm_pixels para imagens com 0 pixels válidos que já passaram pelo pipeline de processamento."""
    db = SessionLocal()
    try:
        existe = db.query(CelmmPixels.id).filter(
            CelmmPixels.metadados_imagem_id == metadados_imagem_id
        ).first()
        if not existe:
            pixel_vazio = CelmmPixels(
                metadados_imagem_id=metadados_imagem_id,
                system_index="EMPTY_0_PIXELS",
                data=data,
                satelite=satelite,
                z_grade_mgrs=z_grade_mgrs,
                tamanho_pixel=tamanho_pixel,
                zenital=zenital
            )
            db.add(pixel_vazio)
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"Erro ao marcar imagem com 0 pixels no banco: {e}")
    finally:
        db.close()

def obter_ids_imagens_com_pixels() -> set:
    """Retorna um conjunto (set) de IDs de metadados_imagens que já possuem pixels associados na tabela celmm_pixels."""
    db = SessionLocal()
    try:
        resultado = db.query(CelmmPixels.metadados_imagem_id).distinct().all()
        return {r[0] for r in resultado}
    except Exception as e:
        st.error(f"Erro ao buscar IDs de imagens com pixels no banco: {e}")
        return set()
    finally:
        db.close()

def obter_df_pixels_por_imagem_ids(imagem_ids: list, limit: int = None) -> pd.DataFrame:
    """Busca registros da tabela celmm_pixels associados aos imagem_ids passados e retorna como DataFrame.
    Admite limit opcional para consultas de preview mais rápidas.
    """
    if not imagem_ids:
        return pd.DataFrame()
    db = SessionLocal()
    try:
        query = db.query(CelmmPixels).filter(
            CelmmPixels.metadados_imagem_id.in_(imagem_ids),
            CelmmPixels.system_index != "EMPTY_0_PIXELS"
        )
        if limit is not None:
            query = query.limit(limit)
        df = pd.read_sql(query.statement, db.bind)
        return df
    except Exception as e:
        st.error(f"Erro ao buscar pixels do banco de dados: {e}")
        return pd.DataFrame()
    finally:
        db.close()

def obter_amostra_pixels_por_imagem_ids(imagem_ids: list, limit_por_imagem: int = 50) -> pd.DataFrame:
    """Busca as N primeiras linhas de amostra para cada imagem_id informado usando Window Functions."""
    if not imagem_ids:
        return pd.DataFrame()
    try:
        from sqlalchemy import text, bindparam
        query = text("""
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY metadados_imagem_id ORDER BY id ASC) as row_num
                FROM celmm_pixels
                WHERE metadados_imagem_id IN :ids AND system_index != 'EMPTY_0_PIXELS'
            ) sub
            WHERE row_num <= :limit_val
            ORDER BY data ASC, id ASC;
        """).bindparams(bindparam('ids', expanding=True))
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"ids": list(imagem_ids), "limit_val": limit_por_imagem})
        if 'row_num' in df.columns:
            df = df.drop(columns=['row_num'])
        return df
    except Exception as e:
        st.error(f"Erro ao buscar amostra de pixels por produto: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def obter_df_raster_cor_verdadeira_cached(metadados_imagem_id: int) -> pd.DataFrame:
    """Busca com cache do Streamlit as colunas de coordenadas e bandas B4, B3, B2 para uma imagem raster."""
    if not metadados_imagem_id:
        return pd.DataFrame()
    try:
        from sqlalchemy import text
        query = text("""
            SELECT latitude, longitude, "B4", "B3", "B2"
            FROM celmm_pixels
            WHERE metadados_imagem_id = :img_id AND system_index != 'EMPTY_0_PIXELS'
        """)
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"img_id": metadados_imagem_id})
        return df
    except Exception as e:
        st.error(f"Erro ao buscar dados raster para a imagem ID {metadados_imagem_id}: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def obter_df_raster_multibandas_cached(metadados_imagem_id: int) -> pd.DataFrame:
    """Busca com cache do Streamlit coordenadas e bandas espectrais para geração de raster."""
    if not metadados_imagem_id:
        return pd.DataFrame()
    try:
        from sqlalchemy import text
        query = text("""
            SELECT latitude, longitude, "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B11", "B12"
            FROM celmm_pixels
            WHERE metadados_imagem_id = :img_id AND system_index != 'EMPTY_0_PIXELS'
        """)
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"img_id": metadados_imagem_id})
        return df
    except Exception as e:
        st.error(f"Erro ao buscar dados raster multibandas para a imagem ID {metadados_imagem_id}: {e}")
        return pd.DataFrame()

def obter_df_pixels_por_imagem_ids_generator(imagem_ids: list, chunksize: int = 50000):
    """Retorna um gerador (generator) que busca os pixels da tabela celmm_pixels
    associados aos imagem_ids informados em lotes (chunks).
    """
    if not imagem_ids:
        return
    db = SessionLocal()
    try:
        query = db.query(CelmmPixels).filter(
            CelmmPixels.metadados_imagem_id.in_(imagem_ids),
            CelmmPixels.system_index != "EMPTY_0_PIXELS"
        )
        for chunk in pd.read_sql(query.statement, db.bind, chunksize=chunksize):
            yield chunk
    except Exception as e:
        st.error(f"Erro ao buscar pixels do banco de dados em lotes: {e}")
    finally:
        db.close()

def criar_tarefa_background(tipo_tarefa: str, payload_dict: dict, total_itens: int) -> int:
    """Cria uma nova tarefa de background e a insere no banco com status 'pendente'."""
    import json
    db = SessionLocal()
    try:
        nome_op = {
            "FULL_PIPELINE": "Processamento Automático",
            "GEE_EXPORT": "Processamento no GEE",
            "CSV_INGEST": "Sincronização de Produtos"
        }.get(tipo_tarefa, tipo_tarefa)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tarefa = BackgroundTask(
            tipo_tarefa=tipo_tarefa,
            status="pendente",
            total_itens=total_itens,
            itens_processados=0,
            payload=json.dumps(payload_dict),
            logs=f"[{timestamp}] [INÍCIO] Tarefa criada: {nome_op} | Total de produto(s): {total_itens}\n"
        )
        db.add(tarefa)
        db.commit()
        db.refresh(tarefa)
        return tarefa.id
    except Exception as e:
        db.rollback()
        st.error(f"Erro ao criar tarefa de background: {e}")
        return None
    finally:
        db.close()

def obter_tarefa_ativa() -> Optional[dict]:
    """Retorna a tarefa de background ativa (em andamento ou pendente), se houver."""
    db = SessionLocal()
    try:
        tarefa = db.query(BackgroundTask).filter(BackgroundTask.status == "processando").first()
        if not tarefa:
            tarefa = db.query(BackgroundTask).filter(BackgroundTask.status == "pendente").order_by(BackgroundTask.id.asc()).first()
        
        return tarefa.to_dict() if tarefa else None
    except Exception as e:
        st.error(f"Erro ao buscar tarefa ativa: {e}")
        return None
    finally:
        db.close()

def cancelar_tarefa(tarefa_id: int):
    """Marca uma tarefa específica como cancelada no banco de dados."""
    db = SessionLocal()
    try:
        tarefa = db.query(BackgroundTask).filter(BackgroundTask.id == tarefa_id).first()
        if tarefa:
            tarefa.status = "cancelado"
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tarefa.logs = (tarefa.logs or "") + f"[{timestamp}] [SISTEMA] Solicitação de cancelamento registrada pelo usuário.\n"
            db.commit()
    except Exception as e:
        db.rollback()
        st.error(f"Erro ao cancelar tarefa: {e}")
    finally:
        db.close()

def obter_status_tarefa(tarefa_id: int) -> Optional[dict]:
    """Retorna o status atual de uma tarefa específica."""
    db = SessionLocal()
    try:
        tarefa = db.query(BackgroundTask).filter(BackgroundTask.id == tarefa_id).first()
        return tarefa.to_dict() if tarefa else None
    except Exception as e:
        st.error(f"Erro ao obter status da tarefa: {e}")
        return None
    finally:
        db.close()

def obter_historico_tarefas(limit: int = 10) -> list:
    """Retorna o histórico de tarefas recentes executadas ou em execução."""
    db = SessionLocal()
    try:
        tarefas = db.query(BackgroundTask).order_by(BackgroundTask.id.desc()).limit(limit).all()
        return [t.to_dict() for t in tarefas]
    except Exception as e:
        st.error(f"Erro ao buscar histórico de tarefas: {e}")
        return []
    finally:
        db.close()

def obter_total_pixels() -> int:
    """Retorna o número total de registros na tabela celmm_pixels."""
    db = SessionLocal()
    try:
        return db.query(func.count(CelmmPixels.id)).scalar() or 0
    except Exception as e:
        st.error(f"Erro ao contar pixels no banco: {e}")
        return 0
    finally:
        db.close()


def obter_estatisticas_tamanho_banco() -> dict:
    """Consulta métricas de tamanho total do banco de dados, detalhamento por tabela e contagem de registros."""
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            # Tamanho geral do banco
            db_size_res = conn.execute(text("""
                SELECT 
                    current_database() AS db_name,
                    pg_size_pretty(pg_database_size(current_database())) AS total_pretty,
                    pg_database_size(current_database()) AS total_bytes;
            """)).fetchone()
            
            # Detalhamento por tabela
            tables_query = text("""
                SELECT
                    relname AS "Tabela",
                    pg_size_pretty(pg_total_relation_size(c.oid)) AS "Tamanho Total",
                    pg_size_pretty(pg_relation_size(c.oid)) AS "Tamanho Dados",
                    pg_size_pretty(pg_indexes_size(c.oid)) AS "Tamanho Índices",
                    reltuples::bigint AS "Linhas Estimadas",
                    pg_total_relation_size(c.oid) AS bytes_total
                FROM pg_class c
                LEFT JOIN pg_namespace n ON (n.oid = c.relnamespace)
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                  AND c.relkind = 'r'
                ORDER BY pg_total_relation_size(c.oid) DESC;
            """)
            df_tables = pd.read_sql(tables_query, conn)

            # Contagens exatas de linhas
            contagens = {}
            for t in ["celmm_pixels", "metadados_imagens", "background_tasks", "users", "historico_execucao"]:
                try:
                    cnt = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                    contagens[t] = int(cnt) if cnt is not None else 0
                except Exception:
                    contagens[t] = 0

            return {
                "db_name": db_size_res[0] if db_size_res else "satellitum",
                "total_pretty": db_size_res[1] if db_size_res else "0 MB",
                "total_bytes": db_size_res[2] if db_size_res else 0,
                "tabelas_df": df_tables,
                "contagens": contagens
            }
    except Exception as e:
        print(f"Erro ao obter estatísticas de tamanho do banco: {e}")
        return {
            "db_name": "satellitum",
            "total_pretty": "Indisponível",
            "total_bytes": 0,
            "tabelas_df": pd.DataFrame(),
            "contagens": {}
        }


def excluir_pixels_por_imagem_ids(imagem_ids: list) -> int:
    """Exclui os registros de pixels na tabela celmm_pixels correspondentes aos IDs de metadados informados."""
    if not imagem_ids:
        return 0
    db = SessionLocal()
    try:
        qtd = db.query(CelmmPixels).filter(CelmmPixels.metadados_imagem_id.in_(imagem_ids)).delete(synchronize_session=False)
        db.commit()
        return qtd
    except Exception as e:
        db.rollback()
        st.error(f"Erro ao excluir pixels no banco: {e}")
        return 0
    finally:
        db.close()


def excluir_produtos_completos_por_imagem_ids(imagem_ids: list) -> tuple:
    """Exclui tanto os registros de pixels quanto os metadados das imagens no banco de dados."""
    if not imagem_ids:
        return (0, 0)
    db = SessionLocal()
    try:
        qtd_pixels = db.query(CelmmPixels).filter(CelmmPixels.metadados_imagem_id.in_(imagem_ids)).delete(synchronize_session=False)
        qtd_meta = db.query(MetadadosImagens).filter(MetadadosImagens.id.in_(imagem_ids)).delete(synchronize_session=False)
        db.commit()
        return (qtd_pixels, qtd_meta)
    except Exception as e:
        db.rollback()
        st.error(f"Erro ao excluir produtos no banco: {e}")
        return (0, 0)
    finally:
        db.close()


