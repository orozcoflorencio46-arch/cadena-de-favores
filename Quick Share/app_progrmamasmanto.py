import io
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(_file_).resolve().parent
DB_PATH = APP_DIR / "mantenimiento.db"

st.set_page_config(page_title="Sistema Total de Mantenimiento", page_icon="🛠️", layout="wide")

# ---------- Base de datos ----------
def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS equipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL, nombre TEXT NOT NULL, area TEXT,
            marca TEXT, modelo TEXT, serie TEXT, criticidad TEXT,
            estado TEXT, fecha_alta TEXT, observaciones TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS ordenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE NOT NULL, fecha_solicitud TEXT, equipo_codigo TEXT,
            tipo TEXT, prioridad TEXT, descripcion TEXT, responsable TEXT,
            estado TEXT, fecha_inicio TEXT, fecha_cierre TEXT,
            horas_paro REAL DEFAULT 0, costo REAL DEFAULT 0, observaciones TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS preventivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_codigo TEXT, actividad TEXT, frecuencia TEXT,
            ultima_fecha TEXT, proxima_fecha TEXT, responsable TEXT,
            estado TEXT, observaciones TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS repuestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL, descripcion TEXT NOT NULL,
            existencia REAL DEFAULT 0, stock_minimo REAL DEFAULT 0,
            unidad TEXT, ubicacion TEXT, costo_unitario REAL DEFAULT 0,
            proveedor TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT, codigo_repuesto TEXT, tipo TEXT,
            cantidad REAL, referencia TEXT, responsable TEXT, observaciones TEXT)""")

def read_table(table):
    with db() as con:
        return pd.read_sql_query(f"SELECT * FROM {table}", con)

def save_record(table, data, record_id=None):
    cols = list(data.keys())
    vals = [data[c] for c in cols]
    with db() as con:
        if record_id:
            assignments = ", ".join([f"{c}=?" for c in cols])
            con.execute(f"UPDATE {table} SET {assignments} WHERE id=?", vals + [record_id])
        else:
            marks = ", ".join(["?"] * len(cols))
            con.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({marks})", vals)

def delete_record(table, record_id):
    with db() as con:
        con.execute(f"DELETE FROM {table} WHERE id=?", (int(record_id),))

init_db()

# ---------- Encabezado y navegación ----------
st.title("🛠️ Sistema Total de Mantenimiento")
st.caption("Control de equipos, órdenes de trabajo, mantenimiento preventivo, repuestos, costos e indicadores. Los datos se guardan localmente en una base SQLite.")
menu = st.sidebar.radio("MÓDULOS", ["Dashboard", "Equipos", "Órdenes de trabajo", "Mantenimiento preventivo", "Repuestos e inventario", "Movimientos de almacén", "Excel: importar / exportar"])
st.sidebar.info("Consejo: realiza copias de seguridad periódicas del archivo mantenimiento.db.")

equipos = read_table("equipos")
ordenes = read_table("ordenes")
preventivos = read_table("preventivos")
repuestos = read_table("repuestos")
movimientos = read_table("movimientos")

# ---------- Dashboard ----------
if menu == "Dashboard":
    st.subheader("Panel general")
    hoy = date.today()
    abiertas = int((ordenes["estado"].fillna("").str.lower() != "cerrada").sum()) if not ordenes.empty else 0
    cerradas = int((ordenes["estado"].fillna("").str.lower() == "cerrada").sum()) if not ordenes.empty else 0
    costo_total = float(pd.to_numeric(ordenes.get("costo", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    horas_paro = float(pd.to_numeric(ordenes.get("horas_paro", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    vencidos = 0
    if not preventivos.empty:
        fechas = pd.to_datetime(preventivos["proxima_fecha"], errors="coerce")
        vencidos = int((fechas.dt.date < hoy).sum())
    bajo_stock = 0
    if not repuestos.empty:
        bajo_stock = int((pd.to_numeric(repuestos["existencia"], errors="coerce").fillna(0) <=
                          pd.to_numeric(repuestos["stock_minimo"], errors="coerce").fillna(0)).sum())
    c1,c2,c3,c4,c5 = st.columns(5)