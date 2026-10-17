import os
import datetime as dt
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple
import ee
import streamlit as st

import logging
logger = logging.getLogger(__name__)

@st.cache_resource
def init_gee():
    """Inicializa a conexão com o Google Earth Engine apenas uma vez por sessão."""
    try:
        from modules.google_auth import carregar_credenciais_google
        project = os.getenv("EARTHENGINE_PROJECT") or os.getenv("GOOGLE_PROJECT_ID", "ppgrhs-satellitum")
        creds = carregar_credenciais_google()
        ee.Initialize(credentials=creds, project=project)
        return True
    except Exception as e:
        logger.error(f"Erro ao inicializar o Earth Engine: {e}", exc_info=True)
        try:
            st.error("Falha ao inicializar o Google Earth Engine. Verifique as credenciais na aba de Administração.")
        except Exception:
            pass
        return False

def preprocess_1(image):
    """Aplica a máscara de qualidade do sensor SCL (Sentinel-2 L2A)."""
    scl = image.select('SCL')
    mask = (scl.neq(1)
            .And(scl.neq(3))
            .And(scl.neq(8))
            .And(scl.neq(9))
            .And(scl.neq(10)))
    return image.updateMask(mask)

def preprocess_2(image, bands, CRS_original, pixel_size, ROI):
    """Executa a seleção de bandas, reamostragem espacial e contagem de pixels disponíveis."""
    select_image = image.select(bands)
    if pixel_size > 10:
        CRS_target = CRS_original.atScale(pixel_size)
        final_image = (select_image.setDefaultProjection(CRS_original)
                       .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=40000)
                       .reproject(crs=CRS_target)
                       .clip(ROI))
    else:
        final_image = select_image.clip(ROI)
    
    pixel_count = final_image.select('B4').reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=ROI.geometry(),
        crs=final_image.select('B4').projection(),
        maxPixels=800000
    )  
    return final_image.set({
        'date_formatted': image.date().format('YYYY-MM-dd'),
        'system:time_start': image.get('system:time_start'),
        'available_pixels': pixel_count.get('B4'),
        'cloud_cover': image.get('CLOUDY_PIXEL_PERCENTAGE'),
        'water_percent': image.get('WATER_PERCENTAGE'),
        'spacecraft': image.get('SPACECRAFT_NAME'),
        'solar_zenith': image.get('MEAN_SOLAR_ZENITH_ANGLE'),
        'mgrs_tile': image.get('MGRS_TILE')
    })

def buscar_metadados_gee(date_start, date_end, pixel_size: int) -> list:
    """Realiza a consulta da coleção Sentinel-2 L2A no Earth Engine e retorna a lista formatada de metadados extraídos."""
    if not init_gee():
        try:
            st.error("Erro ao inicializar o Earth Engine.")
        except Exception:
            pass
        return []

    # Geometria da ROI pré-definida no projeto
    table = ee.FeatureCollection("projects/ppgrhs/assets/CELMM_2025_AJUSTADO")
    ROI = table.geometry()
    
    bands = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B11', 'B12']
    
    S2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterBounds(ROI)
          .filterDate(str(date_start), str(date_end))
          .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 100))
          .map(preprocess_1))
    
    first_image = S2.first()
    if not first_image.getInfo():
        return []

    CRS_original = first_image.select('B4').projection()

    def process_func(img):
        return preprocess_2(img, bands, CRS_original, pixel_size, table)

    processed_collection = S2.map(process_func)
    
    def extract_info(image):
        return ee.Feature(None, {
            'Data': image.get('date_formatted'),
            'Pixels_Validos': image.get('available_pixels'),
            'Nuvens_Pct': image.get('cloud_cover'),
            'Agua_Pct': image.get('water_percent'),
            'Satelite': image.get('spacecraft'),
            'Zenital': image.get('solar_zenith'),
            'Z_Grade_MGRS': image.get('mgrs_tile')
        })

    info_collection = processed_collection.map(extract_info)
    results = info_collection.getInfo()
    
    lista_dados = []
    for feat in results.get('features', []):
        props = feat.get('properties', {})
        if props.get('Data') is not None:
            lista_dados.append(props)
            
    return lista_dados


ASSET_CELMM_ROI = "projects/ppgrhs/assets/CELMM_2025_AJUSTADO"


@st.cache_data(ttl=86400, show_spinner=False)
def calcular_cronograma_passagens(
    asset_roi: str = ASSET_CELMM_ROI,
    dias_a_frente: int = 90,
    data_ate: Optional[dt.date] = None,
    data_ini_hist: Optional[dt.date] = None,
    data_fim_hist: Optional[dt.date] = None,
    incluir_s2: bool = True,
    incluir_l8: bool = True,
    incluir_l9: bool = True,
    incluir_hoje: bool = True
) -> Dict[str, Any]:
    """
    Projeta o cronograma de passagens futuras de satélites (Sentinel-2 e Landsat 8/9)
    sobre o asset orbital do CELMM ("projects/ppgrhs/assets/CELMM_2025_AJUSTADO"),
    extrapolando os ciclos orbitais para os próximos 90 dias a partir
    das últimas passagens registradas no Google Earth Engine.
    Resultados cacheados globalmente por 24 horas (@st.cache_data).
    """
    if not init_gee():
        raise RuntimeError("Não foi possível inicializar a conexão com o Google Earth Engine.")

    hoje = dt.date.today()
    if data_ate is None:
        data_ate = hoje + dt.timedelta(days=dias_a_frente)

    if data_fim_hist is None:
        data_fim_hist = hoje
    if data_ini_hist is None:
        # Padrão: 60 dias de histórico para cobrir ao menos 3 órbitas completas dos sensores
        data_ini_hist = data_fim_hist - dt.timedelta(days=60)

    # Utiliza o asset do CELMM como ROI
    roi = ee.FeatureCollection(asset_roi)

    ini_str = data_ini_hist.strftime('%Y-%m-%d')
    fim_str = (data_fim_hist + dt.timedelta(days=1)).strftime('%Y-%m-%d')
    ate_dt = dt.datetime.combine(data_ate, dt.time.max)

    fontes = []
    if incluir_s2:
        fontes.append(('COPERNICUS/S2_SR_HARMONIZED', 'SPACECRAFT_NAME', 'SENSING_ORBIT_NUMBER', 10))
    if incluir_l8:
        fontes.append(('LANDSAT/LC08/C02/T1_L2', 'SPACECRAFT_ID', 'WRS_PATH', 16))
    if incluir_l9:
        fontes.append(('LANDSAT/LC09/C02/T1_L2', 'SPACECRAFT_ID', 'WRS_PATH', 16))

    passagens = defaultdict(list)
    detalhes_satelites = []

    for colid, p_sat, p_orb, ciclo in fontes:
        try:
            col = ee.ImageCollection(colid).filterBounds(roi).filterDate(ini_str, fim_str)
            col_list = col.reduceColumns(
                ee.Reducer.toList(3),
                ['system:time_start', p_sat, p_orb]
            ).get('list').getInfo()
            
            lst = col_list or []
            ultimo = {}
            for item in lst:
                if not item or len(item) < 3:
                    continue
                t, sat, orb = item[0], item[1], item[2]
                if t is None:
                    continue
                d = dt.datetime.fromtimestamp(t / 1000, tz=dt.timezone.utc).replace(tzinfo=None)
                sat_label = str(sat) if sat else "Desconhecido"
                orb_label = str(orb) if orb is not None else "-"
                chave = (sat_label, orb_label)
                if chave not in ultimo or d > ultimo[chave]:
                    ultimo[chave] = d

            for (sat_label, orb_label), d_pass in ultimo.items():
                detalhes_satelites.append({
                    "satelite": sat_label,
                    "orbita": orb_label,
                    "colecao": colid,
                    "ultima_passagem": d_pass,
                    "ciclo_dias": ciclo
                })
                d = d_pass
                while d <= ate_dt:
                    d += dt.timedelta(days=ciclo)
                    dia_pass = d.date()
                    valido = (dia_pass >= hoje) if incluir_hoje else (dia_pass > hoje)
                    if valido and d <= ate_dt:
                        passagens[dia_pass].append({
                            "satelite": sat_label,
                            "orbita": orb_label,
                            "tipo": "Sentinel-2" if "Sentinel" in sat_label else "Landsat",
                            "label": f"{sat_label} (órb {orb_label})"
                        })
        except Exception as e:
            st.warning(f"Aviso ao consultar coleção '{colid}': {e}")

    # Monta estrutura cronológica ordenada
    cronograma = []
    for dia in sorted(passagens.keys()):
        items = passagens[dia]
        sat_labels = [x["label"] for x in items]
        s2 = any(x["tipo"] == "Sentinel-2" for x in items)
        ls = any(x["tipo"] == "Landsat" for x in items)
        coincidencia = s2 and ls
        
        cronograma.append({
            "data": dia,
            "satelites": items,
            "satelites_str": ", ".join(sat_labels),
            "tem_sentinel": s2,
            "tem_landsat": ls,
            "dupla_passagem": coincidencia,
            "dias_restantes": (dia - hoje).days
        })

    return {
        "asset_roi": asset_roi,
        "data_ate": data_ate,
        "dias_projetados": (data_ate - hoje).days,
        "cronograma": cronograma,
        "detalhes_satelites": detalhes_satelites,
        "gerado_em": dt.datetime.now()
    }

# Alias para compatibilidade
calcular_schedule_passagens = calcular_cronograma_passagens


def gerar_relatorio_txt_cronograma(
    cronograma: List[Dict[str, Any]],
    data_ate: dt.date,
    asset_roi: str = ASSET_CELMM_ROI
) -> str:
    """Gera o arquivo de texto formatado com o cronograma de passagens sobre o CELMM."""
    linhas = []
    linhas.append("Passagens previstas - Sentinel-2 e Landsat 8/9")
    linhas.append(f"Região de Interesse (ROI): {asset_roi}  |  Projetado até {data_ate.strftime('%d/%m/%Y')}")
    linhas.append(f"Gerado em {dt.datetime.now().strftime('%d/%m/%Y %H:%M')}")
    linhas.append("Horário aproximado da passagem: 9h30-10h (local)")
    linhas.append("-" * 70)
    
    dias_semana_abrev = {
        0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex', 5: 'Sáb', 6: 'Dom'
    }
    
    for item in cronograma:
        dia = item["data"]
        abrev = dias_semana_abrev.get(dia.weekday(), "")
        dia_str = f"{abrev} {dia.strftime('%d/%m/%Y')}"
        marca = "   <-- S2 + Landsat no mesmo dia" if item["dupla_passagem"] else ""
        linhas.append(f"{dia_str} | {item['satelites_str']}{marca}")
        
    return "\n".join(linhas) + "\n"

# Alias para compatibilidade
gerar_relatorio_txt_schedule = gerar_relatorio_txt_cronograma


def validar_metodo_historico(
    asset_roi: str = ASSET_CELMM_ROI,
    dias_teste: int = 60
) -> Dict[str, Any]:
    """
    Executa a validação retroativa do método (Backtesting cego):
    1. Define um ponto no passado (T_corte = hoje - dias_teste).
    2. Calibra as órbitas usando apenas imagens ANTERIORES a T_corte.
    3. Projeta as passagens entre T_corte e hoje com base no ciclo orbital.
    4. Consulta as imagens REAIS catalogadas no Earth Engine entre T_corte e hoje.
    5. Compara a previsão com o registro real e calcula a taxa de concordância.
    """
    if not init_gee():
        raise RuntimeError("Não foi possível inicializar a conexão com o Google Earth Engine.")

    hoje = dt.date.today()
    t_corte = hoje - dt.timedelta(days=dias_teste)
    t_inicio_calib = t_corte - dt.timedelta(days=60)

    roi = ee.FeatureCollection(asset_roi)
    fontes = [
        ('COPERNICUS/S2_SR_HARMONIZED', 'SPACECRAFT_NAME', 'SENSING_ORBIT_NUMBER', 10, 'Sentinel-2'),
        ('LANDSAT/LC08/C02/T1_L2', 'SPACECRAFT_ID', 'WRS_PATH', 16, 'Landsat'),
        ('LANDSAT/LC09/C02/T1_L2', 'SPACECRAFT_ID', 'WRS_PATH', 16, 'Landsat'),
    ]

    # 1. Obter a última data de calibração anterior a t_corte
    ultimas_calib = {}
    for colid, p_sat, p_orb, ciclo, tipo in fontes:
        try:
            col = ee.ImageCollection(colid).filterBounds(roi).filterDate(
                t_inicio_calib.strftime('%Y-%m-%d'),
                t_corte.strftime('%Y-%m-%d')
            )
            col_list = col.reduceColumns(
                ee.Reducer.toList(3),
                ['system:time_start', p_sat, p_orb]
            ).get('list').getInfo() or []

            for item in col_list:
                if not item or len(item) < 3 or item[0] is None:
                    continue
                t, sat, orb = item[0], item[1], item[2]
                d = dt.datetime.fromtimestamp(t / 1000, tz=dt.timezone.utc).replace(tzinfo=None)
                chave = (str(sat), str(orb), ciclo, tipo)
                if chave not in ultimas_calib or d > ultimas_calib[chave]:
                    ultimas_calib[chave] = d
        except Exception:
            pass

    # 2. Projetar passagens no período de teste [t_corte, hoje]
    passagens_previstas = defaultdict(list)
    ate_dt = dt.datetime.combine(hoje, dt.time.max)
    for (sat, orb, ciclo, tipo), d_pass in ultimas_calib.items():
        d = d_pass
        while d <= ate_dt:
            d += dt.timedelta(days=ciclo)
            dia = d.date()
            if t_corte <= dia <= hoje:
                passagens_previstas[dia].append(sat)

    # 3. Buscar dados REAIS ocorridos no período de teste [t_corte, hoje]
    passagens_reais = defaultdict(list)
    for colid, p_sat, p_orb, ciclo, tipo in fontes:
        try:
            col = ee.ImageCollection(colid).filterBounds(roi).filterDate(
                t_corte.strftime('%Y-%m-%d'),
                (hoje + dt.timedelta(days=1)).strftime('%Y-%m-%d')
            )
            col_list = col.reduceColumns(
                ee.Reducer.toList(2),
                ['system:time_start', p_sat]
            ).get('list').getInfo() or []

            for item in col_list:
                if not item or len(item) < 2 or item[0] is None:
                    continue
                t, sat = item[0], item[1]
                dia = dt.datetime.fromtimestamp(t / 1000, tz=dt.timezone.utc).date()
                if t_corte <= dia <= hoje:
                    passagens_reais[dia].append(str(sat))
        except Exception:
            pass

    # 4. Comparar previsões vs realidade
    todas_datas = sorted(set(list(passagens_previstas.keys()) + list(passagens_reais.keys())))
    comparativo = []
    acertos = 0
    total = len(todas_datas)

    for dia in todas_datas:
        prev = sorted(list(set(passagens_previstas.get(dia, []))))
        real = sorted(list(set(passagens_reais.get(dia, []))))
        
        concorda = (set(prev) == set(real))
        if concorda:
            acertos += 1
            status = "✅ 100% Confirmado"
        elif set(prev).issubset(set(real)):
            acertos += 0.8
            status = "ℹ️ Passagem real adicional catalogada"
        elif set(real).issubset(set(prev)):
            # Pode ocorrer se a imagem ainda não tiver sido ingerida no GEE (latência)
            status = "⏳ Imagem ainda em processamento no GEE"
        else:
            status = "⚠️ Divergência"

        comparativo.append({
            "Data": dia.strftime('%d/%m/%Y'),
            "Previsto pelo Algoritmo": ", ".join(prev) if prev else "—",
            "Realmente Catalogado no GEE": ", ".join(real) if real else "—",
            "Status": status
        })

    taxa_acuracia = round((acertos / total * 100), 1) if total > 0 else 0.0

    return {
        "periodo_teste": f"{t_corte.strftime('%d/%m/%Y')} a {hoje.strftime('%d/%m/%Y')}",
        "total_eventos": total,
        "taxa_acuracia": taxa_acuracia,
        "comparativo": comparativo
    }


