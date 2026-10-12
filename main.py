from fastapi import FastAPI, HTTPException
import pandas as pd
import numpy as np
import joblib

# Inicializamos la aplicación de FastAPI
app = FastAPI(
    title="API Comercial Cruzimex",
    description="Motor de recomendación y optimización para preventa en ruta",
    version="1.0.0"
)

# --- CARGA EN CALIENTE (Se ejecuta UNA SOLA VEZ al encender el servidor) ---
# Aquí cargamos los archivos .joblib directo a la memoria RAM reservada
try:
    df_ventas = joblib.load("df_ventas.joblib")
    df_clientes = joblib.load("df_clientes.joblib")
    stock_disponible = joblib.load("stock_disponible.joblib")
    df_coseno = joblib.load("df_coseno.joblib")
    print("¡Modelos y datos cargados exitosamente en la memoria RAM!")
except Exception as e:
    print(f"Error al cargar los archivos .joblib: {e}")

@app.get("/")
def home():
    return {
        "status": "Online", 
        "mensaje": "Servidor de Recomendaciones Cruzimex funcionando correctamente"
    }

@app.get("/recomendar/{codigo_cliente}")
def obtener_recomendacion_cliente(codigo_cliente: int, top_n: int = 5):
    """
    Este es el 'link' o endpoint que consumirá la app móvil en la calle.
    Recibe el código del cliente y devuelve las recomendaciones basadas en Coseno y Stock Real.
    """
    # 1. Buscar información del cliente en el DataFrame cargado en RAM
    cli_info = df_clientes[df_clientes['CODIGO'] == codigo_cliente]
    if cli_info.empty:
        raise HTTPException(status_code=404, detail=f"Cliente con código {codigo_cliente} no encontrado.")
    
    info_cli = cli_info.iloc[0]
    canal_cli = info_cli['CLASIFICACION']
    clase_pareto_cli = info_cli.get('CLASE_PARETO', 'C')

    # 2. Obtener historial del cliente
    historial = df_ventas[df_ventas['Cliente'] == codigo_cliente]
    subclases_compradas_raw = historial['Descripcion SubClase'].unique() if not historial.empty else []
    subclases_compradas = [s for s in subclases_compradas_raw if pd.notna(s) and s in df_coseno.columns]

    articulos_con_stock = set(stock_disponible['COD'])
    recomendaciones = []

    # 3. Lógica de recomendación por Similitud Coseno o Top Canal
    if len(subclases_compradas) > 0:
        similares = df_coseno[subclases_compradas].mean(axis=1).sort_values(ascending=False)
        similares = similares.drop(labels=subclases_compradas, errors='ignore')

        for subclase_sugerida, score in similares.items():
            if score <= 0: continue
            articulos_subclase = df_ventas[df_ventas['Descripcion SubClase'] == subclase_sugerida][['Articulo', 'Descripcion Articulo']].drop_duplicates()

            for _, row in articulos_subclase.iterrows():
                cod_art = str(row['Articulo']).strip()
                if cod_art in articulos_con_stock:
                    match_stock = stock_disponible[stock_disponible['COD'] == cod_art]
                    cant_stock = float(match_stock['CANT'].values[0]) if not match_stock.empty else 0.0

                    recomendaciones.append({
                        'codigo': cod_art,
                        'producto': row['Descripcion Articulo'],
                        'subclase': subclase_sugerida,
                        'stock_piso': cant_stock,
                        'afinidad': f"{round(score * 100, 1)}%",
                        'motivo': "Basado en similitud de consumo con su historial"
                    })
                if len(recomendaciones) >= top_n: break
            if len(recomendaciones) >= top_n: break
    else:
        # Fallback para cliente nuevo o sin historial (Top Ventas del Canal)
        clientes_canal = df_clientes[df_clientes['CLASIFICACION'] == canal_cli]['CODIGO']
        top_canal = df_ventas[df_ventas['Cliente'].isin(clientes_canal)]
        top_subclases = top_canal['Descripcion SubClase'].value_counts().index.tolist()
        
        for subclase_sugerida in top_subclases:
            articulos_subclase = df_ventas[df_ventas['Descripcion SubClase'] == subclase_sugerida][['Articulo', 'Descripcion Articulo']].drop_duplicates()
            for _, row in articulos_subclase.iterrows():
                cod_art = str(row['Articulo'].strip())
                if cod_art in articulos_con_stock:
                    match_stock = stock_disponible[stock_disponible['COD'] == cod_art]
                    cant_stock = float(match_stock['CANT'].values[0]) if not match_stock.empty else 0.0

                    recomendaciones.append({
                        'codigo': cod_art,
                        'producto': row['Descripcion Articulo'],
                        'subclase': subclase_sugerida,
                        'stock_piso': cant_stock,
                        'afinidad': "Top Canal",
                        'motivo': "Producto estrella del canal (Sugerencia para cliente nuevo)"
                    })
                if len(recomendaciones) >= top_n: break
            if len(recomendaciones) >= top_n: break

    return {
        "codigo_cliente": codigo_cliente,
        "razon_social": info_cli['NOMBRE COMPANIA'],
        "canal": canal_cli,
        "pareto": clase_pareto_cli,
        "total_recomendaciones": len(recomendaciones),
        "recomendaciones": recomendaciones
    }