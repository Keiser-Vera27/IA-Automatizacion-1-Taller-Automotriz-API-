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
# CONFIGURACIÓN DE LA BASE DE DATOS (REPARACIONES, GASTOS E INVENTARIO)
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
            fecha_hora TEXT,
            estado TEXT
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
    
    # 3. Tabla de Inventario (Repuestos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            nombre TEXT,
            marca TEXT,
            aplicacion TEXT,
            cantidad INTEGER,
            costo REAL,
            precio_venta REAL,
            fecha_actualizacion TEXT
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

# Sub-estructura para descontar inventario en una reparación
class RepuestoUsado(BaseModel):
    codigo: str = Field(description="Código exacto del repuesto usado (ej: vss005)")
    cantidad: int = Field(description="Cantidad de unidades utilizadas")

# Estructura para reparaciones (Ingresos)
class TrabajoTaller(BaseModel):
    vehiculo: str
    cliente: str = ""
    cedula: str = ""
    telefono: str = ""
    motivo: str = ""
    trabajo_realizado: str = ""
    oficial: str = ""
    cobro: float = 0.0
    metodo_pago: str = ""
    banco: str = ""
    repuestos_usados: list[RepuestoUsado] = Field(default=[], description="Lista de repuestos del inventario usados en esta reparación")

# Estructura para Gastos
class GastoTaller(BaseModel):
    monto: float = Field(description="Cantidad de dinero gastada en números decimales")
    motivo: str = Field(description="Motivo o concepto del gasto (ej: compra de repuesto, gasolina, almuerzo, etc.)")
    vehiculo: str = Field(description="Vehículo o placa relacionada al gasto, o 'N/A' si no aplica a un carro específico")
    responsable: str = Field(description="Nombre de la persona que realizó el gasto")

# Estructura para Inventario (Nuevos repuestos)
class RepuestoInventario(BaseModel):
    codigo: str = Field(description="Código del repuesto (ej: vss005). Si no tiene, pon 'S/C'")
    nombre: str = Field(description="Nombre de la pieza (ej: sensor vss, pastillas)")
    marca: str = Field(description="Marca del repuesto (ej: besuto)")
    aplicacion: str = Field(description="Para qué vehículo/marca es (ej: kia)", default="General")
    cantidad: int = Field(description="Cantidad de unidades que ingresan")
    costo: float = Field(description="Precio que le costó al taller comprarlo")
    precio_venta: float = Field(description="Precio sugerido de venta al cliente")

# Estructura para Devoluciones (Reingreso al stock)
class DevolucionInventario(BaseModel):
    codigo: str = Field(description="Código exacto del repuesto devuelto (ej: vss005)")
    cantidad: int = Field(description="Cantidad de unidades que reingresan al stock. Si el usuario dice 'todas' o 'el repuesto completo', pon el número total que correspondía.")
    motivo: str = Field(default="Devolución de cliente", description="Motivo de la devolución")

# Estructura maestra ACTUALIZADA (con 4 opciones)
class ClasificacionMensaje(BaseModel):
    tipo: str = Field(description="Debe ser estrictamente 'reparacion', 'gasto', 'inventario' o 'devolucion'")
    reparacion: TrabajoTaller | None = Field(default=None)
    gasto: GastoTaller | None = Field(default=None)
    inventario: RepuestoInventario | None = Field(default=None)
    devolucion: DevolucionInventario | None = Field(default=None)

class MensajeEntrante(BaseModel):
    texto: str

# ==============================================================================
# SERVIDOR WEB (FASTAPI)
# ==============================================================================

@app.post("/procesar-mensaje")
def procesar_mensaje_con_ia(mensaje: MensajeEntrante):
    prompt = f"""
    Eres un asistente contable inteligente de un taller mecánico. 
    Analiza el siguiente mensaje y clasifícalo estrictamente en UNA de estas 4 categorías:
    1. 'reparacion': Ingreso de vehículo o cobro de trabajo terminado.
    2. 'gasto': Salida de dinero operativo del taller.
    3. 'inventario': Compra de repuestos NUEVOS para abastecer el taller.
    4. 'devolucion': Reingreso al stock de una pieza que un cliente no usó o devolvió.

    Extrae los datos correspondientes. Si faltan datos déjalos vacíos o en 0.
    IMPORTANTE: Si en una reparación se usaron piezas y se mencionan sus códigos, extráelas obligatoriamente en la lista 'repuestos_usados'.

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
    
    resultado = json.loads(respuesta.text)
    tipo = resultado.get("tipo")
    tiempo_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conexion = sqlite3.connect("taller.db")
    cursor = conexion.cursor()
    
    if tipo == "reparacion" and resultado.get("reparacion"):
        d = resultado["reparacion"]
        
        # 1. Buscar la ÚLTIMA orden de este vehículo
        cursor.execute("""
            SELECT id, estado, fecha_hora FROM reparaciones 
            WHERE vehiculo = ? 
            ORDER BY id DESC LIMIT 1
        """, (d["vehiculo"],))
        
        ultima_orden = cursor.fetchone()
        
        # --- FILTRO ANTI-DUPLICADOS ---
        if ultima_orden and ultima_orden[1] == 'Terminado' and (d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != ""):
            fecha_ultima = ultima_orden[2].split(" ")[0]
            hoy = tiempo_actual.split(" ")[0]
            
            if fecha_ultima == hoy:
                conexion.close()
                return {
                    "status": "éxito", 
                    "tipo_detectado": tipo,
                    "mensaje_bd": f"Bloqueado: El vehículo {d['vehiculo']} ya fue cerrado y cobrado el día de hoy.",
                    "datos_procesados": resultado,
                    "registrado_a_las": tiempo_actual
                }
        
        # Variables para mensaje
        mensaje_bd = ""
        aviso_inventario = ""
        
        # --- DESCUENTO DE INVENTARIO (Solo si se está cobrando/cerrando) ---
        if (d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != "") and d.get("repuestos_usados"):
            for repuesto in d.get("repuestos_usados", []):
                cursor.execute("""
                    UPDATE inventario 
                    SET cantidad = cantidad - ? 
                    WHERE codigo = ? AND codigo != 'S/C'
                """, (repuesto["cantidad"], repuesto["codigo"]))
                aviso_inventario += f" | -{repuesto['cantidad']} unid. de {repuesto['codigo']} descontadas."
        
        # --- FLUJO NORMAL DE GUARDADO ---
        if ultima_orden and ultima_orden[1] == 'Pendiente':
            if d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != "":
                # CASO A: Actualizamos y cerramos la orden
                id_orden = ultima_orden[0]
                cursor.execute("""
                    UPDATE reparaciones 
                    SET trabajo_realizado = ?, cobro = ?, metodo_pago = ?, banco = ?, estado = 'Terminado'
                    WHERE id = ?
                """, (d["trabajo_realizado"], d["cobro"], d["metodo_pago"], d["banco"], id_orden))
                
                mensaje_bd = f"Orden de {d['vehiculo']} marcada como Terminada" + aviso_inventario
            else:
                conexion.close()
                return {
                    "status": "éxito", 
                    "tipo_detectado": tipo,
                    "mensaje_bd": f"El vehículo {d['vehiculo']} ya está registrado como Pendiente.",
                    "datos_procesados": resultado,
                    "registrado_a_las": tiempo_actual
                }
                
        else:
            # CASO B: Registro nuevo
            estado_nuevo = 'Pendiente'
            if d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != "":
                estado_nuevo = 'Terminado'
                
            cursor.execute("""
                INSERT INTO reparaciones 
                (vehiculo, cliente, cedula, telefono, motivo, trabajo_realizado, oficial, cobro, metodo_pago, banco, fecha_hora, estado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                d["vehiculo"], d["cliente"], d["cedula"], d["telefono"],
                d["motivo"], d["trabajo_realizado"], d["oficial"],
                d["cobro"], d["metodo_pago"], d["banco"], tiempo_actual, estado_nuevo
            ))
            
            mensaje_bd = f"Nuevo registro {d['vehiculo']} guardado como {estado_nuevo}" + aviso_inventario
            
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
        
    elif tipo == "inventario" and resultado.get("inventario"):
        d = resultado["inventario"]
        cursor.execute("SELECT id, cantidad FROM inventario WHERE codigo = ? AND codigo != 'S/C'", (d["codigo"],))
        repuesto_existente = cursor.fetchone()
        
        if repuesto_existente:
            id_repuesto = repuesto_existente[0]
            nueva_cantidad = repuesto_existente[1] + d["cantidad"]
            cursor.execute("""
                UPDATE inventario 
                SET cantidad = ?, costo = ?, precio_venta = ?, fecha_actualizacion = ?
                WHERE id = ?
            """, (nueva_cantidad, d["costo"], d["precio_venta"], tiempo_actual, id_repuesto))
            mensaje_bd = f"Stock actualizado: {d['nombre']} ahora tiene {nueva_cantidad} unidades"
        else:
            cursor.execute("""
                INSERT INTO inventario 
                (codigo, nombre, marca, aplicacion, cantidad, costo, precio_venta, fecha_actualizacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (d["codigo"], d["nombre"], d["marca"], d["aplicacion"], d["cantidad"], d["costo"], d["precio_venta"], tiempo_actual))
            mensaje_bd = f"Nuevo repuesto agregado al inventario: {d['nombre']}"

    elif tipo == "devolucion" and resultado.get("devolucion"):
        d = resultado["devolucion"]
        cursor.execute("SELECT id, cantidad, nombre FROM inventario WHERE codigo = ?", (d["codigo"],))
        repuesto = cursor.fetchone()
        
        if repuesto:
            id_repuesto = repuesto[0]
            nueva_cantidad = repuesto[1] + d["cantidad"]
            nombre_rep = repuesto[2]
            
            cursor.execute("""
                UPDATE inventario 
                SET cantidad = ?, fecha_actualizacion = ?
                WHERE id = ?
            """, (nueva_cantidad, tiempo_actual, id_repuesto))
            mensaje_bd = f"Devolución: Se sumaron {d['cantidad']} unid. de {nombre_rep} al stock."
        else:
            conexion.close()
            return {"status": "error", "mensaje": f"No se encontró el repuesto código '{d['codigo']}' en el sistema."}
            
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
# 1. REPORTE DIARIO (Solo reparaciones y gastos del día)
# ==============================================================================

@app.get("/exportar-excel")
def exportar_excel():
    conexion = sqlite3.connect("taller.db")
    
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
    
    nombre_archivo = f"Reporte Diario AS {hoy_archivo}.xlsx"
    ruta_completa = os.path.join(carpeta_respaldos, nombre_archivo)
    
    # Guardamos el Excel únicamente con las dos pestañas operativas del día
    with pd.ExcelWriter(ruta_completa, engine='openpyxl') as writer:
        df_reparaciones.to_excel(writer, sheet_name='Reparaciones', index=False)
        df_gastos.to_excel(writer, sheet_name='Gastos', index=False)
        
    return FileResponse(
        ruta_completa, 
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
        filename=nombre_archivo
    )

# ==============================================================================
# 2. REPORTE DE INVENTARIO / AUDITORÍA (Aparte y bajo demanda)
# ==============================================================================

@app.get("/exportar-inventario")
def exportar_inventario():
    conexion = sqlite3.connect("taller.db")
    
    # Seleccionamos exclusivamente lo necesario para auditar el stock físico
    # Nota: Asegúrate de tener la columna 'proveedor' en tu tabla o cámbiala si usas otra.
    df_inventario = pd.read_sql_query("SELECT codigo, nombre, marca, proveedor, cantidad FROM inventario", conexion)
    conexion.close()
    
    # Renombramos las columnas para que el reporte impreso se vea profesional
    df_inventario.columns = ['Código', 'Repuesto', 'Marca', 'Proveedor', 'Stock en Sistema']
    
    # Añadimos columnas vacías para que el mecánico anote el conteo manual a mano
    df_inventario['Conteo Físico Real'] = ""
    df_inventario['Diferencia'] = ""
    
    hoy_archivo = datetime.now().strftime("%d-%m-%Y")
    
    carpeta_respaldos = "respaldos_excel"
    os.makedirs(carpeta_respaldos, exist_ok=True)
    
    nombre_archivo = f"Auditoria Inventario {hoy_archivo}.xlsx"
    ruta_completa = os.path.join(carpeta_respaldos, nombre_archivo)
    
    # Guardamos el archivo independiente para auditoría
    with pd.ExcelWriter(ruta_completa, engine='openpyxl') as writer:
        df_inventario.to_excel(writer, sheet_name='Inventario Físico', index=False)
        
    return FileResponse(
        ruta_completa, 
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
        filename=nombre_archivo
    )