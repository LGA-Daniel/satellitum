import pandas as pd
import numpy as np
import streamlit as st
from modules.db import obter_df_raster_cor_verdadeira_cached, obter_df_raster_multibandas_cached

COMBINACOES_ESPECTRAIS = {
    "RGB_TRUE_COLOR": {
        "nome": "Cor Verdadeira (RGB: B4, B3, B2)",
        "bandas": ['B4', 'B3', 'B2'],
        "descricao": "B4 (Vermelho), B3 (Verde), B2 (Azul) — Visualização em cores naturais reais",
        "max_val": 3000.0
    },
    "FALSE_COLOR_NIR": {
        "nome": "Falsa Cor Vegetação (NIR: B8, B4, B3)",
        "bandas": ['B8', 'B4', 'B3'],
        "descricao": "B8 (Infravermelho Próximo), B4 (Vermelho), B3 (Verde) — Destaque de vigor vegetal e biomassa",
        "max_val": 4000.0
    },
    "SWIR_AGRICULTURE": {
        "nome": "Agricultura / Umidade (SWIR: B11, B8, B2)",
        "bandas": ['B11', 'B8', 'B2'],
        "descricao": "B11 (SWIR), B8 (NIR), B2 (Azul) — Sensibilidade à umidade do solo e estresse hídrico",
        "max_val": 4000.0
    },
    "GEOLOGY_SWIR": {
        "nome": "Urbano / Geologia (SWIR: B12, B11, B4)",
        "bandas": ['B12', 'B11', 'B4'],
        "descricao": "B12 (SWIR-2), B11 (SWIR-1), B4 (Vermelho) — Destaque de áreas urbanas e solo exposto",
        "max_val": 4000.0
    }
}

def processar_matriz_combinacao(
    df: pd.DataFrame, 
    bandas: list = None, 
    max_val: float = 3000.0,
    target_width: int = 500,
    target_height: int = 400,
    center_coords: tuple = None
):
    """Processa o DataFrame de pixels de uma imagem e gera a matriz RGBA 4D normalizada
    em resolução padronizada (500x400 px), centralizada geograficamente, com pixels inexistentes transparentes.
    
    Retorna:
        rgba_4d (np.ndarray): Matriz 3D (target_height, target_width, 4) com valores entre 0.0 e 1.0.
        shape (tuple): Tupla (target_height, target_width) com a dimensão padronizada da grade.
    """
    if bandas is None or len(bandas) != 3:
        bandas = ['B4', 'B3', 'B2']
        
    df_proc = df.copy()
    df_proc['latitude'] = pd.to_numeric(df_proc['latitude'], errors='coerce')
    df_proc['longitude'] = pd.to_numeric(df_proc['longitude'], errors='coerce')
    
    for b in bandas:
        if b in df_proc.columns:
            df_proc[b] = pd.to_numeric(df_proc[b], errors='coerce').fillna(0.0)
        else:
            df_proc[b] = 0.0
            
    df_proc = df_proc.dropna(subset=['latitude', 'longitude'])
    
    if df_proc.empty:
        raise ValueError("Dados de coordenadas inválidos ou vazios.")

    min_lat = float(df_proc['latitude'].min())
    max_lat = float(df_proc['latitude'].max())
    min_lon = float(df_proc['longitude'].min())
    max_lon = float(df_proc['longitude'].max())

    range_lat = max_lat - min_lat
    range_lon = max_lon - min_lon
    n_points = len(df_proc)

    # 1. Determina o centro de georreferenciamento
    if center_coords and len(center_coords) == 2 and center_coords[0] is not None:
        center_lat, center_lon = center_coords
    else:
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0

    # 2. Calcula o passo espacial esperado com base na área de cobertura e quantidade de pontos
    if range_lat > 0 and range_lon > 0 and n_points > 0:
        area_por_pixel = (range_lat * range_lon) / n_points
        step_estimado = np.sqrt(area_por_pixel)
        step_lat = step_estimado
        step_lon = step_estimado
    else:
        step_lat = 0.0001
        step_lon = 0.0001

    if step_lat <= 0:
        step_lat = 0.0001
    if step_lon <= 0:
        step_lon = 0.0001

    # 3. Mapeamento de coordenadas (lat, lon) para a grade fixa centralizada (target_height x target_width)
    center_row = (target_height - 1) / 2.0
    center_col = (target_width - 1) / 2.0

    rows = np.round(center_row - (df_proc['latitude'].values - center_lat) / step_lat).astype(int)
    cols = np.round(center_col + (df_proc['longitude'].values - center_lon) / step_lon).astype(int)

    # Máscara dos pixels que se encontram dentro da área útil do canvas
    valid_canvas = (rows >= 0) & (rows < target_height) & (cols >= 0) & (cols < target_width)
    rows_valid = rows[valid_canvas]
    cols_valid = cols[valid_canvas]

    # 4. Preenche as matrizes das bandas espectrais no canvas padronizado
    grids = {}
    for b in bandas:
        g = np.zeros((target_height, target_width), dtype=np.float32)
        if len(rows_valid) > 0:
            g[rows_valid, cols_valid] = df_proc[b].values[valid_canvas].astype(np.float32)
        grids[b] = g

    # 5. Máscara de presença de dados válidos
    data_presence = (grids[bandas[0]] > 0) | (grids[bandas[1]] > 0) | (grids[bandas[2]] > 0)

    canais_norm = []
    for b in bandas:
        grid_band = grids[b]
        norm = np.clip(grid_band / float(max_val), 0.0, 1.0)
        norm[~data_presence] = 1.0
        canais_norm.append(norm)

    # 6. Canal Alpha (1.0 para dados válidos, 0.0 para transparência total fora do dado)
    alpha_channel = np.where(data_presence, 1.0, 0.0).astype(np.float32)
    canais_norm.append(alpha_channel)

    rgba_4d = np.dstack(canais_norm)
    return rgba_4d, (target_height, target_width)

def processar_matriz_cor_verdadeira(df: pd.DataFrame, target_width: int = 500, target_height: int = 400):
    """Função de compatibilidade para Cor Verdadeira B4-B3-B2 padronizada."""
    return processar_matriz_combinacao(
        df, 
        bandas=['B4', 'B3', 'B2'], 
        max_val=3000.0,
        target_width=target_width,
        target_height=target_height
    )

