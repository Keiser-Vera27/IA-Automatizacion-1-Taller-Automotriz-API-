# ==============================================================================
# Proyecto: API del Taller Automotriz con IA, SQLite, Fecha/Hora y Gastos
# Autor: Keiser Vera
# ==============================================================================

import os
import json
import sqlite3
from datetime import datetime
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from google import genai
from google.genai import types
import pandas as pd

# ==============================================================================
# CONFIGURACIÓN DE LA BASE DE DATOS (REPARACIONES Y GASTOS)
# ==============================================================================

def inicializar_base_datos():
    conexion = sqlite3.connect("taller.db")
    cursor = conexion.cursor()
    
    # 1. Tabla de Reparaciones (Ingresos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reparaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehiculo TEXT,
            cliente TEXT,
            cedula TEXT,
            telefono TEXT,
            motivo TEXT,
            trabajo_realizado TEXT,
            oficial TEXT,
            cobro REAL,
            metodo_pago TEXT,
            banco TEXT,
            fecha_hora TEXT
        )
    """)
    
    # 2. Tabla de Gastos (Salidas de dinero)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monto REAL,
            motivo TEXT,
            vehiculo TEXT,
            responsable TEXT,
            fecha_hora TEXT
        )
    """)
    
    conexion.commit()
    conexion.close()

inicializar_base_datos()

# ==============================================================================
# CONFIGURACIÓN API, IA Y ARCHIVOS WEB
# ==============================================================================

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
app = FastAPI(title="API del Taller Automotriz - Control Total")

app.mount("/web", StaticFiles(directory="static", html=True), name="static")

# ==============================================================================
# ESTRUCTURAS DE DATOS (PYDANTIC)
# ==============================================================================

# Estructura para reparaciones (Ingresos)
class TrabajoTaller(BaseModel):
    vehiculo: str
    cliente: str
    cedula: str
    telefono: str
    motivo: str
    trabajo_realizado: str
    oficial: str
    cobro: float
    metodo_pago: str
    banco: str

# Estructura para Gastos
class GastoTaller(BaseModel):
    monto: float = Field(description="Cantidad de dinero gastada en números decimales")
    motivo: str = Field(description="Motivo o concepto del gasto (ej: compra de repuesto, gasolina, almuerzo, etc.)")
    vehiculo: str = Field(description="Vehículo o placa relacionada al gasto, o 'N/A' si no aplica a un carro específico")
    responsable: str = Field(description="Nombre de la persona que realizó el gasto")

# Estructura maestra que decide si el mensaje es una Reparación o un Gasto
class ClasificacionMensaje(BaseModel):
    tipo: str = Field(description="Debe ser estrictamente 'reparacion' o 'gasto' según el mensaje del usuario")
    reparacion: TrabajoTaller | None = Field(default=None, description="Llenar solo si el tipo es reparacion")
    gasto: GastoTaller | None = Field(default=None, description="Llenar solo si el tipo es gasto")

class MensajeEntrante(BaseModel):
    texto: str

# ==============================================================================
# SERVIDOR WEB (FASTAPI)
# ==============================================================================

@app.get("/")
def leer_raiz():
    return {"mensaje": "Servidor activo con gestión de reparaciones y gastos."}

@app.post("/procesar-mensaje")
def procesar_mensaje_con_ia(mensaje: MensajeEntrante):
    prompt = f"""
    Eres un asistente contable inteligente de un taller mecánico. 
    Analiza el siguiente mensaje y determina si se trata de un trabajo de reparación (ingreso) o de un gasto operativo (salida de dinero).
    
    Clasificalo correctamente y extrae los datos correspondientes.
    
    Mensaje: "{mensaje.texto}"
    """
    
    respuesta = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ClasificacionMensaje,
        ),
    )
    
    # Convertimos la respuesta de texto de la IA a diccionario
    resultado = json.loads(respuesta.text)
    tipo = resultado.get("tipo")
    tiempo_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conexion = sqlite3.connect("taller.db")
    cursor = conexion.cursor()
    
    if tipo == "reparacion" and resultado.get("reparacion"):
        d = resultado["reparacion"]
        cursor.execute("""
            INSERT INTO reparaciones 
            (vehiculo, cliente, cedula, telefono, motivo, trabajo_realizado, oficial, cobro, metodo_pago, banco, fecha_hora)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            d["vehiculo"], d["cliente"], d["cedula"], d["telefono"],
            d["motivo"], d["trabajo_realizado"], d["oficial"],
            d["cobro"], d["metodo_pago"], d["banco"], tiempo_actual
        ))
        mensaje_bd = "Reparación guardada exitosamente"
        
    elif tipo == "gasto" and resultado.get("gasto"):
        d = resultado["gasto"]
        cursor.execute("""
            INSERT INTO gastos 
            (monto, motivo, vehiculo, responsable, fecha_hora)
            VALUES (?, ?, ?, ?, ?)
        """, (
            d["monto"], d["motivo"], d["vehiculo"], d["responsable"], tiempo_actual
        ))
        mensaje_bd = "Gasto registrado exitosamente"
    else:
        conexion.close()
        return {"status": "error", "mensaje": "No se pudo clasificar el mensaje correctamente."}
        
    conexion.commit()
    conexion.close()
    
    return {
        "status": "éxito",
        "tipo_detectado": tipo,
        "mensaje_bd": mensaje_bd,
        "datos_procesados": resultado,
        "registrado_a_las": tiempo_actual
    }

# ==============================================================================
# EXPORTAR EXCEL CON DOS PESTAÑAS (INGRESOS Y GASTOS DEL DÍA)
# ==============================================================================

@app.get("/exportar-excel")
def exportar_excel():
    conexion = sqlite3.connect("taller.db")
    
    # Leemos ambas tablas en DataFrames independientes
    df_reparaciones = pd.read_sql_query("SELECT * FROM reparaciones", conexion)
    df_gastos = pd.read_sql_query("SELECT * FROM gastos", conexion)
    conexion.close()
    
    hoy_str = datetime.now().strftime("%Y-%m-%d")
    hoy_archivo = datetime.now().strftime("%d-%m-%Y")
    
    # Filtramos únicamente los registros del día actual
    if not df_reparaciones.empty and 'fecha_hora' in df_reparaciones.columns:
        df_reparaciones = df_reparaciones[df_reparaciones['fecha_hora'].str.startswith(hoy_str)]
        
    if not df_gastos.empty and 'fecha_hora' in df_gastos.columns:
        df_gastos = df_gastos[df_gastos['fecha_hora'].str.startswith(hoy_str)]
    
    carpeta_respaldos = "respaldos_excel"
    os.makedirs(carpeta_respaldos, exist_ok=True)
    
    nombre_archivo = f"Reporte AS {hoy_archivo}.xlsx"
    ruta_completa = os.path.join(carpeta_respaldos, nombre_archivo)
    
    # Guardamos el Excel usando ExcelWriter para crear múltiples pestañas (hojas)
    with pd.ExcelWriter(ruta_completa, engine='openpyxl') as writer:
        df_reparaciones.to_excel(writer, sheet_name='Reparaciones', index=False)
        df_gastos.to_excel(writer, sheet_name='Gastos', index=False)
        
    return FileResponse(
        ruta_completa, 
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
        filename=nombre_archivo
    )