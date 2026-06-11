import threading
import time
import datetime
import json
import os
import ee
import pandas as pd
from modules.core import (
    SessionLocal, 
    init_gee, 
    baixar_arquivo_drive_para_disco, 
    salvar_pixels_bulk,
    obter_metadados_salvos,
    obter_servico_gdrive
)
from modules.models import BackgroundTask

# Variáveis globais para gerenciar a Thread do Worker
_worker_thread = None
_worker_lock = threading.Lock()
_stop_event = threading.Event()

def inicializar_worker():
    """Inicializa a thread única do worker em segundo plano, se ainda não estiver ativa."""
    global _worker_thread
    with _worker_lock:
        # Verifica se já existe uma thread ativa e saudável do worker
        thread_ativa = False
        for t in threading.enumerate():
            if t.name == "SatellitumWorkerThread" and t.is_alive() and not getattr(t, 'stop_requested', False):
                thread_ativa = True
                break
        
        if thread_ativa:
            # Já está rodando e saudável, não faz nada
            return

        # Sinaliza todas as threads antigas com o mesmo nome para pararem
        for t in threading.enumerate():
            if t.name == "SatellitumWorkerThread" and t.is_alive():
                t.stop_requested = True
                
        _stop_event.clear()
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="SatellitumWorkerThread")
        _worker_thread.stop_requested = False
        _worker_thread.start()

def parar_worker():
    """Sinaliza para a thread do worker parar."""
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.stop_requested = True

def _adicionar_log_db(tarefa_id: int, mensagem: str, incremental: bool = True):
    """Auxiliar para adicionar logs da execução no registro da tarefa no PostgreSQL."""
    # Envia para o stdout para que o Docker logs capture em tempo real
    print(f"[TAREFA #{tarefa_id}] {mensagem}", flush=True)
    
    db = SessionLocal()
    try:
        tarefa = db.query(BackgroundTask).filter(BackgroundTask.id == tarefa_id).first()
        if tarefa:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            nova_linha = f"[{timestamp}] {mensagem}\n"
            if incremental:
                tarefa.logs = (tarefa.logs or "") + nova_linha
            else:
                tarefa.logs = nova_linha
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"Erro ao salvar logs no banco: {e}", flush=True)
    finally:
        db.close()

def _atualizar_progresso_db(tarefa_id: int, processados: int, status: str = None):
    """Atualiza o número de itens processados e opcionalmente o status no banco."""
    db = SessionLocal()
    try:
        tarefa = db.query(BackgroundTask).filter(BackgroundTask.id == tarefa_id).first()
        if tarefa:
            tarefa.itens_processados = processados
            if status:
                tarefa.status = status
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"Erro ao salvar progresso no banco: {e}")
    finally:
        db.close()

def _verificar_cancelamento(tarefa_id: int) -> bool:
    """Verifica se o status da tarefa foi alterado para 'cancelado' pela interface."""
    db = SessionLocal()
    try:
        tarefa = db.query(BackgroundTask).filter(BackgroundTask.id == tarefa_id).first()
        if tarefa and tarefa.status == "cancelado":
            return True
        return False
    except Exception:
        return False
    finally:
        db.close()

def _worker_loop():
    """Loop principal do worker executado em segundo plano."""
    print("[WORKER] Thread do Worker Satellitum iniciada com sucesso.")
    
    current_thread = threading.current_thread()
    
    # Ao iniciar, recupera tarefas presas em status 'processando' (ex: após restart de container)
    # apenas se esta for a única thread de worker ativa (evita resetar tarefas de outras threads ativas)
    outros_workers = [t for t in threading.enumerate() if t.name == "SatellitumWorkerThread" and t != current_thread and t.is_alive()]
    if not outros_workers:
        db = SessionLocal()
        try:
            tarefas_presas = db.query(BackgroundTask).filter(BackgroundTask.status == "processando").all()
            for t in tarefas_presas:
                t.status = "pendente"
                t.logs = (t.logs or "") + "[SISTEMA] Reinício detectado. Tarefa resetada para pendente.\n"
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[WORKER] Erro ao resetar tarefas presas no startup: {e}")
        finally:
            db.close()

    while not _stop_event.is_set() and not getattr(current_thread, 'stop_requested', False):
        db = SessionLocal()
        tarefa = None
        try:
            # Busca a tarefa pendente mais antiga
            tarefa = db.query(BackgroundTask).filter(BackgroundTask.status == "pendente").order_by(BackgroundTask.id.asc()).first()
            if tarefa:
                # Altera status para 'processando'
                tarefa.status = "processando"
                tarefa.logs = (tarefa.logs or "") + "[WORKER] Iniciando execução da tarefa.\n"
                db.commit()
                
                # Armazena o ID e payload para trabalhar fora da sessão aberta do SQLAlchemy
                tarefa_id = tarefa.id
                tipo = tarefa.tipo_tarefa
                payload = json.loads(tarefa.payload) if tarefa.payload else {}
                
                print(f"[WORKER] Executando tarefa #{tarefa_id} (Tipo: {tipo})")
                
                # Executa a tarefa
                if tipo == "GEE_EXPORT":
                    _executar_gee_export(tarefa_id, payload)
                elif tipo == "CSV_INGEST":
                    _executar_csv_ingest(tarefa_id, payload)
                else:
                    _adicionar_log_db(tarefa_id, f"[ERRO] Tipo de tarefa desconhecido: {tipo}")
                    _atualizar_progresso_db(tarefa_id, 0, "falhou")
            
        except Exception as e:
            print(f"[WORKER] Erro no loop: {e}")
            if tarefa:
                try:
                    db.rollback()
                    tarefa.status = "falhou"
                    tarefa.logs = (tarefa.logs or "") + f"[ERRO GRAVE] Erro fatal no worker: {e}\n"
                    db.commit()
                except:
                    pass
        finally:
            db.close()
            
        # Espera 5 segundos antes de buscar novas tarefas
        time.sleep(5)

def _executar_gee_export(tarefa_id: int, payload: dict):
    """Executa o processamento do Earth Engine e exportação assíncrona para o Drive."""
    current_thread = threading.current_thread()
    _adicionar_log_db(tarefa_id, "Inicializando o Google Earth Engine...")
    if not init_gee():
        _adicionar_log_db(tarefa_id, "[ERRO] Falha ao inicializar o Earth Engine. Abortando tarefa.")
        _atualizar_progresso_db(tarefa_id, 0, "falhou")
        return
        
    try:
        ROI = ee.FeatureCollection("projects/ppgrhs/assets/CELMM_2025_AJUSTADO")
    except Exception as e:
        _adicionar_log_db(tarefa_id, f"[ERRO] Falha ao carregar a ROI CELMM no GEE: {e}")
        _atualizar_progresso_db(tarefa_id, 0, "falhou")
        return

    # Lógicas de processamento auxiliares do Earth Engine
    def preprocess_1(image):
        scl = image.select('SCL')
        mask = (scl.neq(1)
                .And(scl.neq(3))
                .And(scl.neq(8))
                .And(scl.neq(9))
                .And(scl.neq(10)))
        return image.updateMask(mask)

    def preprocess_2(image, bands, CRS_original, pixel_size, ROI):
        select_image = image.select(bands)
        if pixel_size > 10:
            CRS_target = CRS_original.atScale(pixel_size)
            final_image = (select_image.setDefaultProjection(CRS_original)
                           .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=40000)
                           .reproject(crs=CRS_target)
                           .clip(ROI))
        else:
            final_image = select_image.clip(ROI)
        return final_image

    selected_rows = payload.get("selected_rows", [])
    df_filtrado_data = payload.get("df_filtrado_data", [])
    
    total = len(selected_rows)
    success_count = 0
    fail_count = 0
    
    _adicionar_log_db(tarefa_id, f"Iniciando processamento sequencial de {total} produtos no GEE.")
    
    for index, rdata in enumerate(selected_rows):
        # 1. Verifica cancelamento
        if _verificar_cancelamento(tarefa_id):
            _adicionar_log_db(tarefa_id, "[CANCELADO] Processamento cancelado pelo usuário.")
            return

        # 1b. Verifica se a thread do worker foi solicitada a parar
        if _stop_event.is_set() or getattr(current_thread, 'stop_requested', False):
            _adicionar_log_db(tarefa_id, "[SISTEMA] Execução suspensa devido ao reinício da thread. A tarefa será retomada.")
            _atualizar_progresso_db(tarefa_id, success_count, "pendente")
            return

        date_str = rdata.get('Data do Produto')
        sat = rdata.get('Satélite')
        
        # Encontra nos metadados correspondentes
        match = None
        for m in df_filtrado_data:
            if m.get('data') == date_str and m.get('satelite') == sat:
                match = m
                break
                
        if not match:
            _adicionar_log_db(tarefa_id, f"[ERRO] [{index + 1}/{total}] Metadados não encontrados para a data {date_str}.")
            fail_count += 1
            _atualizar_progresso_db(tarefa_id, success_count)
            continue
            
        date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        grade = match.get('z_grade_mgrs')
        pixel_sz = int(match.get('tamanho_pixel'))
        
        _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Processando data: {date_str} | Satélite: {sat} | Grade: {grade} | Pixel: {pixel_sz}m")
        
        try:
            str_start = date_str
            str_end = (date_obj + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            
            collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                          .filterBounds(ROI)
                          .filterDate(str_start, str_end)
                          .filter(ee.Filter.eq('MGRS_TILE', grade))
                          .filter(ee.Filter.eq('SPACECRAFT_NAME', sat)))
            
            size = collection.size().getInfo()
            if size == 0:
                _adicionar_log_db(tarefa_id, f"[ERRO] [{index + 1}/{total}] Nenhum produto correspondente no Earth Engine.")
                fail_count += 1
                _atualizar_progresso_db(tarefa_id, success_count)
                continue
                
            image = collection.first()
            CRS_base = image.select('B4').projection()
            
            img_with_SCL = preprocess_1(image)
            bands = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12']
            final_img = preprocess_2(img_with_SCL, bands, CRS_base, pixel_sz, ROI)
            
            image_for_extraction = final_img.addBands(ee.Image.pixelLonLat())
            final_CRS = CRS_base.atScale(pixel_sz) if pixel_sz > 10 else CRS_base
            
            extracted_points = image_for_extraction.sample(
                region=ROI,
                scale=pixel_sz,
                projection=final_CRS,
                geometries=False,
                tileScale=4
            )
            
            task_desc = f"Exportar_CSV_{date_str}_{pixel_sz}m"
            file_prefix = f"CELMM_Data_{date_str}_{pixel_sz}m"
            
            task = ee.batch.Export.table.toDrive(
                collection=extracted_points,
                description=task_desc,
                folder='CSV_Sentinel2',
                fileNamePrefix=file_prefix,
                fileFormat='CSV'
            )
            
            _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Submetendo tarefa de exportação ao GEE...")
            task.start()
            task_id = task.status().get('id')
            _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Tarefa iniciada no GEE. ID: {task_id}")
            
            start_time = time.time()
            last_state = None
            
            # Loop de monitoramento da tarefa individual no Earth Engine
            while True:
                # Verifica se houve solicitação de cancelamento da tarefa principal
                if _verificar_cancelamento(tarefa_id):
                    _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Cancelamento detectado. Cancelando tarefa no GEE...")
                    try:
                        task.cancel()
                    except:
                        pass
                    _adicionar_log_db(tarefa_id, "[CANCELADO] Processamento cancelado pelo usuário.")
                    return
                
                # Verifica se a thread do worker foi solicitada a parar
                if _stop_event.is_set() or getattr(current_thread, 'stop_requested', False):
                    _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Desligamento da thread detectado. Retornando tarefa ao status pendente...")
                    _atualizar_progresso_db(tarefa_id, success_count, "pendente")
                    return
                    
                status = task.status()
                state = status.get('state')
                elapsed = int(time.time() - start_time)
                
                if state != last_state:
                    _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Status GEE: {state} ({elapsed}s decorridos)")
                    last_state = state
                    
                if state in ['COMPLETED', 'FAILED', 'CANCELLED']:
                    if state == 'COMPLETED':
                        _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Sucesso! Exportação GEE concluída em {elapsed}s.")
                        success_count += 1
                    else:
                        err_msg = status.get('error_message', 'Sem detalhes de erro.')
                        _adicionar_log_db(tarefa_id, f"[ERRO] [{index + 1}/{total}] Tarefa no GEE falhou/cancelou. Erro: {err_msg}")
                        fail_count += 1
                    break
                    
                time.sleep(5)
                
        except Exception as e:
            _adicionar_log_db(tarefa_id, f"[ERRO] [{index + 1}/{total}] Erro durante o processamento da data {date_str}: {e}")
            fail_count += 1
            
        _atualizar_progresso_db(tarefa_id, success_count)
        
    _adicionar_log_db(tarefa_id, "--------------------------------------------------")
    _adicionar_log_db(tarefa_id, f"Fim da fila. Sucesso: {success_count} | Falhas: {fail_count}")
    
    final_status = "concluido" if fail_count == 0 else "falhou"
    _atualizar_progresso_db(tarefa_id, success_count, final_status)

def _executar_csv_ingest(tarefa_id: int, payload: dict):
    """Executa o download de arquivos CSV do Drive e ingestão em massa no PostgreSQL."""
    _adicionar_log_db(tarefa_id, "Inicializando conexão com o Google Drive...")
    service = obter_servico_gdrive()
    if not service:
        _adicionar_log_db(tarefa_id, "[ERRO] Não foi possível autenticar no Google Drive. Abortando tarefa.")
        _atualizar_progresso_db(tarefa_id, 0, "falhou")
        return

    selected_rows = payload.get("selected_rows", [])
    map_nome_id = payload.get("map_nome_id", {})
    
    total = len(selected_rows)
    success_count = 0
    fail_count = 0
    
    temp_dir = "/tmp/satellitum_temp"
    # Limpa a pasta temporária de arquivos parciais de execuções anteriores abortadas
    try:
        if os.path.exists(temp_dir):
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
    except Exception as e:
        print(f"Erro ao limpar pasta temporária no início da ingestão: {e}")
        
    os.makedirs(temp_dir, exist_ok=True)
    
    _adicionar_log_db(tarefa_id, f"Iniciando ingestão de {total} arquivo(s) CSV no PostgreSQL.")
    
    for index, rdata in enumerate(selected_rows):
        # 1. Verifica cancelamento
        if _verificar_cancelamento(tarefa_id):
            _adicionar_log_db(tarefa_id, "[CANCELADO] Processamento cancelado pelo usuário.")
            return

        # 1b. Verifica se a thread do worker foi solicitada a parar
        if _stop_event.is_set() or getattr(threading.current_thread(), 'stop_requested', False):
            _adicionar_log_db(tarefa_id, "[SISTEMA] Execução suspensa devido ao reinício da thread. A tarefa será retomada.")
            _atualizar_progresso_db(tarefa_id, success_count, "pendente")
            return

        img_id = int(rdata.get('id'))
        date_str = rdata.get('Data do Produto')
        pixel_size = int(rdata.get('Tamanho Pixel (m)'))
        satelite = str(rdata.get('Satélite'))
        grade = rdata.get('Grade MGRS')
        zenital = rdata.get('zenital')
        nome_esperado = f"CELMM_Data_{date_str}_{pixel_size}m.csv"
        dest_path = os.path.join(temp_dir, nome_esperado)
        
        # Verifica se o produto tem 0 pixels válidos no banco de dados
        pixels_validos_meta = None
        db_sess = SessionLocal()
        try:
            from modules.models import MetadadosImagens
            meta = db_sess.query(MetadadosImagens).filter(MetadadosImagens.id == img_id).first()
            if meta:
                pixels_validos_meta = meta.pixels_validos
        except Exception as e:
            print(f"Erro ao verificar pixels_validos_meta: {e}")
        finally:
            db_sess.close()

        if pixels_validos_meta == 0:
            _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Produto com 0 pixels válidos. Ingestão vazia considerada sucesso.")
            success_count += 1
            _atualizar_progresso_db(tarefa_id, success_count)
            try:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
            except:
                pass
            continue
            
        _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Preparando arquivo: `{nome_esperado}`")
        
        # A. Realiza download do GDrive se não estiver em disco local
        if not os.path.exists(dest_path):
            fid = map_nome_id.get(nome_esperado)
            if not fid:
                _adicionar_log_db(tarefa_id, f"[ERRO] [{index + 1}/{total}] Arquivo `{nome_esperado}` não foi encontrado na pasta do Google Drive.")
                fail_count += 1
                _atualizar_progresso_db(tarefa_id, success_count)
                continue
            
            _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Baixando arquivo do Google Drive...")
            try:
                baixar_arquivo_drive_para_disco(fid, dest_path)
            except Exception as e:
                _adicionar_log_db(tarefa_id, f"[ERRO] [{index + 1}/{total}] Falha no download do Drive: {e}")
                fail_count += 1
                _atualizar_progresso_db(tarefa_id, success_count)
                continue
                
        # B. Leitura e ingestão rápida (COPY)
        if os.path.exists(dest_path):
            _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Lendo CSV e estruturando metadados na memória...")
            try:
                try:
                    df = pd.read_csv(dest_path)
                except pd.errors.EmptyDataError:
                    _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Arquivo CSV vazio encontrado (0 pixels válidos). Ingestão concluída com sucesso.")
                    try:
                        os.remove(dest_path)
                    except:
                        pass
                    success_count += 1
                    _atualizar_progresso_db(tarefa_id, success_count)
                    continue

                rename_dict = {
                    'system:index': 'system_index',
                    '.geo': 'geo'
                }
                df = df.rename(columns=rename_dict)
                
                df['metadados_imagem_id'] = img_id
                df['data'] = date_str
                df['satelite'] = satelite
                df['z_grade_mgrs'] = grade
                df['tamanho_pixel'] = pixel_size
                df['zenital'] = zenital
                
                # Converte system_index de forma segura para string sem .0
                def converter_system_index(val):
                    if pd.isna(val):
                        return ""
                    if isinstance(val, float):
                        if val.is_integer():
                            return str(int(val))
                        return str(val)
                    return str(val)
                df['system_index'] = df['system_index'].apply(converter_system_index)
                
                _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Iniciando inserção em massa (COPY) no banco...")
                inseridos = salvar_pixels_bulk(df)
                _adicionar_log_db(tarefa_id, f"[{index + 1}/{total}] Sucesso! {inseridos:,} pixels importados com sucesso.")
                
                # C. Remove arquivo temporário do disco
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
                
                success_count += 1
                
            except Exception as e:
                _adicionar_log_db(tarefa_id, f"[ERRO] [{index + 1}/{total}] Ingestão no banco falhou: {e}")
                fail_count += 1
                
        _atualizar_progresso_db(tarefa_id, success_count)
        
    _adicionar_log_db(tarefa_id, "--------------------------------------------------")
    _adicionar_log_db(tarefa_id, f"Fim do processamento de CSVs. Sucesso: {success_count} | Falhas: {fail_count}")
    
    final_status = "concluido" if fail_count == 0 else "falhou"
    _atualizar_progresso_db(tarefa_id, success_count, final_status)


if __name__ == "__main__":
    print("[WORKER] Iniciando worker em modo standalone...")
    try:
        _worker_loop()
    except KeyboardInterrupt:
        print("[WORKER] Interrupção detectada. Encerrando worker...")
        parar_worker()
