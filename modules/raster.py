import pandas as pd
import numpy as np
import streamlit as st
from modules.db import obter_df_raster_cor_verdadeira_cached

def processar_matriz_cor_verdadeira(df: pd.DataFrame):
    """Processa o DataFrame de pixels de uma imagem e gera a matriz RGBA 4D normalizada
    em Cor Verdadeira (B4-B3-B2) com fundo transparente/branco onde não houver dados.
    
    Retorna:
        rgba_4d (np.ndarray): Matriz 3D (n_rows, n_cols, 4) com valores entre 0.0 e 1.0.
        shape (tuple): Tupla (n_rows, n_cols) com a dimensão em pixels da grade.
    """
    df_proc = df.copy()
    df_proc['latitude'] = pd.to_numeric(df_proc['latitude'], errors='coerce')
    df_proc['longitude'] = pd.to_numeric(df_proc['longitude'], errors='coerce')
    
    ordem_bandas = ['B4', 'B3', 'B2'] # Red, Green, Blue
    for b in ordem_bandas:
        if b in df_proc.columns:
            df_proc[b] = pd.to_numeric(df_proc[b], errors='coerce').fillna(0.0)
        else:
            df_proc[b] = 0.0
            
    df_proc = df_proc.dropna(subset=['latitude', 'longitude'])
    
    if df_proc.empty:
        raise ValueError("Dados de coordenadas inválidos ou vazios.")

    min_lat = df_proc['latitude'].min()
    max_lat = df_proc['latitude'].max()
    min_lon = df_proc['longitude'].min()
    max_lon = df_proc['longitude'].max()
    
    range_lat = max_lat - min_lat
    range_lon = max_lon - min_lon
    n_points = len(df_proc)

    # 1. Calcula o passo espacial esperado com base na área de cobertura e quantidade de pontos
    if range_lat > 0 and range_lon > 0 and n_points > 0:
        area_por_pixel = (range_lat * range_lon) / n_points
        step_estimado = np.sqrt(area_por_pixel)
        step_lat = step_estimado
        step_lon = step_estimado
    else:
        step_lat = 0.0001
        step_lon = 0.0001

    # Trava de segurança para impedir matrizes gigantes (máximo de 2000x2000 px)
    if range_lat > 0 and (range_lat / step_lat) > 2000:
        step_lat = range_lat / 2000.0
    if range_lon > 0 and (range_lon / step_lon) > 2000:
        step_lon = range_lon / 2000.0

    # 2. Calcula índices inteiros de linha (Norte no topo) e coluna (Oeste à esquerda)
    rows = np.round((max_lat - df_proc['latitude'].values) / step_lat).astype(int)
    cols = np.round((df_proc['longitude'].values - min_lon) / step_lon).astype(int)
    
    rows = np.clip(rows, 0, 2000)
    cols = np.clip(cols, 0, 2000)
    
    n_rows = int(rows.max() + 1)
    n_cols = int(cols.max() + 1)
    
    # Preenche grades das bandas
    grids = {}
    for b in ordem_bandas:
        g = np.zeros((n_rows, n_cols), dtype=np.float32)
        g[rows, cols] = df_proc[b].values.astype(np.float32)
        grids[b] = g

    # Máscara booleana de presença de dados válidos de pixel
    data_mask = (grids['B4'] > 0) | (grids['B3'] > 0) | (grids['B2'] > 0)
    
    canais_norm = []
    
    for b in ordem_bandas:
        grid_band = grids[b]
        valid_vals = grid_band[data_mask]
        
        if len(valid_vals) > 0:
            p2 = np.percentile(valid_vals, 2.0)
            p98 = np.percentile(valid_vals, 98.0)
            if p98 <= p2:
                p98 = p2 + 1e-6
            norm = (grid_band - p2) / (p98 - p2)
        else:
            norm = grid_band
            
        norm = np.clip(norm, 0.0, 1.0)
        # Onde não houver dados, preenche o canal com 1.0 (branco)
        norm[~data_mask] = 1.0
        canais_norm.append(norm)
        
    # Adiciona o canal Alpha (transparência: 1.0 para dados, 0.0 para ausência de dados)
    alpha_channel = np.where(data_mask, 1.0, 0.0).astype(np.float32)
    canais_norm.append(alpha_channel)
    
    rgba_4d = np.dstack(canais_norm)
    return rgba_4d, (n_rows, n_cols)
