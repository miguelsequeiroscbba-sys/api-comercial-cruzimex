import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import joblib

print("Iniciando proceso ETL y actualización de modelos...")

# 1. REGLA DE AGRUPACIÓN Y LIMPIEZA
def mapear_grupo(valor):
    if pd.isna(valor): return None
    val = str(valor).strip().upper()
    if "LAURA NATALIE" in val or "POMACLAURE" in val: return None
    if any(k in val for k in ["ALIMENTO", "NO PERECEDERO", "NO PERECEDEROS", "FRITO LAY", "ATUN", "CONSERVA", "FIDEO", "SNACK", "1 KILO"]): return "Alimentos"
    if any(k in val for k in ["REFRESCANTE", "MEZCLADOR", "SUPER FRUT", "JUGO", "GASEOSA"]): return "Bebidas Refrescantes"
    if any(k in val for k in ["ALCOHOLICA", "ALCOHOLICAS", "MADRILENA", "TEQUILA", "LICOR", "RON", "CERVEZA", "VINO", "750 ML", "980 ML", "200 ML"]): return "Bebidas Alcohólicas"
    if any(k in val for k in ["CUIDADO PERSONAL", "PAÑUELO", "DMUJER", "LOCION", "DESODORANTE", "SHAMPOO"]): return "Cuidado Personal"
    if any(k in val for k in ["HOGAR", "LIMPIEZA", "LAVAVAJILLA", "LAVANDINA", "DETERGENTE", "DESINFECTANTE"]): return "Hogar y Limpieza"
    return None

# 2. CARGA DE DATOS
ruta_clientes = r"C:\Users\katye\OneDrive\Escritorio\PROCEDIMIENTOS CRUZIMEX\EXCELS\Gestión clientes dual\Clientes_20260925.xls"
df_c_raw = pd.read_excel(ruta_clientes, header=None)
header_row = df_c_raw[df_c_raw.apply(lambda r: r.astype(str).str.contains('ACTIVO').any(), axis=1)].index[0]
df_clientes = pd.read_excel(ruta_clientes, header=header_row)
df_clientes.columns = df_clientes.columns.astype(str).str.strip()
df_clientes = df_clientes[df_clientes['ACTIVO'] == 'HABILITADO'].copy()
df_clientes['CLASIFICACION'] = df_clientes['CLASIFICACION'].fillna('Sin Clasificación').astype(str).str.strip()
df_clientes['ZONA'] = df_clientes['ZONA'].fillna('Sin Zona').astype(str).str.strip()
df_clientes['RUTA'] = df_clientes['RUTA'].fillna('Sin Ruta').astype(str).str.strip() if 'RUTA' in df_clientes.columns else 'Sin Ruta'
df_clientes = df_clientes.dropna(subset=['CODIGO'])
df_clientes['CODIGO'] = df_clientes['CODIGO'].astype(int)

FECHA_CORTE = pd.to_datetime('2026-10-02')
df_clientes['FECHA REGISTRO'] = pd.to_datetime(df_clientes['FECHA REGISTRO'], dayfirst=True, errors='coerce')
df_clientes['DIAS_REGISTRO'] = (FECHA_CORTE - df_clientes['FECHA REGISTRO']).dt.days.fillna(999)
df_clientes['ES_NUEVO'] = df_clientes['DIAS_REGISTRO'] <= 30

# Google Sheets Planificación
# Google Sheets Planificación (Seguro contra fallos)
sheet_id = "1looMoLTTKIb5LNh1t8VflFTY5JWbF5Lmn_mjUS9aJ20"
gid = "1957412713"
url_sheets = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

try:
    df_plan = pd.read_csv(url_sheets)
    df_plan.columns = df_plan.columns.astype(str).str.strip()
    df_plan['RUTA'] = df_plan['RUTA'].astype(str).str.strip()
    df_clientes = pd.merge(df_clientes, df_plan[['RUTA', 'DIA', 'VENDEDOR']], on='RUTA', how='left')
except Exception as e:
    print(f"Aviso: No se pudo leer Google Sheets o faltaba alguna columna: {e}")

# Blindaje: Si por algo no existe la columna, la creamos vacía para que no explote
if 'VENDEDOR' not in df_clientes.columns:
    df_clientes['VENDEDOR'] = 'Sin Vendedor'
if 'DIA' not in df_clientes.columns:
    df_clientes['DIA'] = 'Sin Día'

df_clientes['VENDEDOR'] = df_clientes['VENDEDOR'].fillna('Sin Vendedor')
df_clientes['DIA'] = df_clientes['DIA'].fillna('Sin Día')

# Inventario
ruta_inv = r"C:\Users\katye\Downloads\INVENTARIO EN PISO 29.09.2026-CBBA..xls"
df_inv = pd.read_excel(ruta_inv)
stock_disponible = df_inv[df_inv['CANT'] > 0].copy()
stock_disponible['COD'] = stock_disponible['COD'].astype(str).str.strip()

# Ventas
ruta_vts = r"C:\Users\katye\OneDrive\Escritorio\PROCEDIMIENTOS CRUZIMEX\EXCELS\Gestión clientes dual\VENTAS-20-MAYO-AL-20-JUNIO.xlsx"
cols_vts = ['Cliente','Fecha', 'Descripcion Grupo', 'Descripcion SubClase', 'Articulo', 'Descripcion Articulo', 'Cantidad', 'Total']
df_ventas = pd.read_excel(ruta_vts, sheet_name='Anexar1', usecols=lambda c: c in cols_vts or c in ['Fecha', 'FECHA', 'FECHA_VENTA'])
df_ventas = df_ventas.dropna(subset=['Cliente', 'Descripcion SubClase', 'Articulo']).copy()
df_ventas['Articulo'] = df_ventas['Articulo'].astype(str).str.strip()
df_ventas['Descripcion SubClase'] = df_ventas['Descripcion SubClase'].astype(str).str.strip()
df_ventas['Cliente'] = df_ventas['Cliente'].astype(int)
df_ventas['Total'] = pd.to_numeric(df_ventas['Total'], errors='coerce').fillna(0)
df_ventas['Cantidad'] = pd.to_numeric(df_ventas['Cantidad'], errors='coerce').fillna(0)
df_ventas['CategoriaMacro'] = df_ventas['Descripcion SubClase'].apply(mapear_grupo)
df_ventas = df_ventas.dropna(subset=['CategoriaMacro']).copy()

# Pareto
ventas_cli = df_ventas.groupby('Cliente')['Total'].sum().reset_index().sort_values(by='Total', ascending=False)
ventas_cli['Monto_Acum'] = ventas_cli['Total'].cumsum()
total_gen = ventas_cli['Total'].sum()
ventas_cli['Pct_Acum'] = (ventas_cli['Monto_Acum'] / total_gen) * 100 if total_gen > 0 else 0
ventas_cli['CLASE_PARETO'] = ventas_cli['Pct_Acum'].apply(lambda p: 'A' if p <= 80 else ('B' if p <= 95 else 'C'))

df_clientes = df_clientes.merge(ventas_cli[['Cliente', 'CLASE_PARETO']], left_on='CODIGO', right_on='Cliente', how='left')
df_clientes['CLASE_PARETO'] = df_clientes.apply(lambda r: 'NUEVO' if r.get('ES_NUEVO', False) else (r['CLASE_PARETO'] if pd.notnull(r['CLASE_PARETO']) else 'C'), axis=1)
df_clientes.drop(columns=['Cliente'], inplace=True, errors='ignore')

# Matriz Coseno
df_ventas_canal = df_ventas.merge(df_clientes, left_on='Cliente', right_on='CODIGO', how='inner')
pivot_matrix = df_ventas_canal.pivot_table(index='Descripcion SubClase', columns='CLASIFICACION', values='Cantidad', aggfunc='sum', fill_value=0)
cos_sim = cosine_similarity(pivot_matrix)
df_coseno = pd.DataFrame(cos_sim, index=pivot_matrix.index, columns=pivot_matrix.index)

# Guardar Binarios
joblib.dump(df_ventas, "df_ventas.joblib")
joblib.dump(df_clientes, "df_clientes.joblib")
joblib.dump(stock_disponible, "stock_disponible.joblib")
joblib.dump(df_coseno, "df_coseno.joblib")

print("¡Proceso finalizado con éxito! Archivos .joblib generados.")