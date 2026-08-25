# ==============================================================================
# Proyecto: API del Taller Automotriz con IA, Supabase (Nube), y Proveedores
# Autor: Keiser Vera
# ==============================================================================

import os
import re
import json
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, EmailStr
from dotenv import load_dotenv
from openai import OpenAI as ClienteOpenAICompatible
import pandas as pd
from supabase import create_client, Client
import re # Asegúrate de que esto esté al inicio de tu archivo main.py


def normalizar_placa(texto: str) -> str:
    """
    Deja la placa en un formato único: mayúsculas, sin espacios ni guiones.
    """
    if not texto:
        return texto
    return re.sub(r"[\s\-]", "", texto).upper().strip()


# ==============================================================================
# MANEJO DE ZONA HORARIA (ECUADOR)
# ==============================================================================
# IMPORTANTE: todo fecha_hora que guardamos en Supabase se genera con
# ahora_utc_str(), es decir, es UTC explícito (no depende de en qué
# timezone esté corriendo el servidor/contenedor). Para calcular "el día
# de hoy" para un taller en Ecuador, convertimos el día calendario de
# Ecuador a su rango equivalente en UTC antes de filtrar en la base.

ZONA_ECUADOR = ZoneInfo("America/Guayaquil")


def ahora_utc_str() -> str:
    """Timestamp actual en UTC explícito, en el formato que usamos para guardar fecha_hora."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def limites_dia_ecuador(fecha_str: str | None = None) -> tuple[str, str]:
    """
    Devuelve (inicio_utc, fin_utc) del día calendario en Ecuador (00:00:00 a 23:59:59
    hora de Guayaquil), convertidos a UTC, en el mismo formato de texto usado al
    guardar fecha_hora. Si no se pasa fecha_str, usa el día actual en Ecuador.
    """
    if fecha_str:
        dia_base = datetime.strptime(fecha_str, "%Y-%m-%d").replace(tzinfo=ZONA_ECUADOR)
    else:
        dia_base = datetime.now(ZONA_ECUADOR)

    inicio_local = dia_base.replace(hour=0, minute=0, second=0, microsecond=0)
    fin_local = dia_base.replace(hour=23, minute=59, second=59, microsecond=0)

    inicio_utc = inicio_local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    fin_utc = fin_local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return inicio_utc, fin_utc


# ==============================================================================
# CONFIGURACIÓN DE SUPABASE Y CLIENTE DE IA
# ==============================================================================

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") 
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")     

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==============================================================================
# PROVEEDORES DE IA — Groq (principal) + DeepSeek (respaldo)
# ==============================================================================
# Ambos hablan el mismo formato compatible con OpenAI, así que comparten
# el mismo código de llamada — solo cambia la URL base, la key y el modelo.
# Si DEEPSEEK_API_KEY no está configurada, el sistema sigue funcionando
# solo con Groq (respaldo desactivado, no roto).
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

groq_client = ClienteOpenAICompatible(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
deepseek_client = ClienteOpenAICompatible(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com") if DEEPSEEK_API_KEY else None

MODELO_GROQ = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile fue descontinuado por Groq el 16-ago-2026
MODELO_DEEPSEEK = "deepseek-v4-flash"  # deepseek-chat quedó retirado el 24-jul-2026


def generar_json_con_respaldo(prompt: str, temperature: float = 0.0) -> tuple[dict, str]:
    """
    Pide una respuesta JSON. Intenta primero con Groq; si falla por
    cualquier motivo, reintenta con DeepSeek (si está configurado) antes
    de lanzar la excepción. Devuelve (json_parseado, "groq" o "deepseek").
    """
    prompt_json = prompt + "\n\nResponde ÚNICAMENTE con JSON válido, sin explicación."
    try:
        resp = groq_client.chat.completions.create(
            model=MODELO_GROQ,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt_json}],
        )
        return json.loads(resp.choices[0].message.content), "groq"
    except Exception as e_groq:
        print(f"⚠️ Groq falló, probando respaldo con DeepSeek: {e_groq}")
        if not deepseek_client:
            raise
        resp = deepseek_client.chat.completions.create(
            model=MODELO_DEEPSEEK,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt_json}],
        )
        return json.loads(resp.choices[0].message.content), "deepseek"

app = FastAPI(title="API del Taller Automotriz - Cloud Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/web", StaticFiles(directory="static", html=True), name="static")

# ==============================================================================
# DEPENDENCIA DE SEGURIDAD (ESCUDO MULTI-TENANT)
# ==============================================================================

def obtener_cliente_seguro(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta el Pase VIP (Token)")

    token = auth_header.split(" ")[1]

    try:
        user_data = supabase.auth.get_user(token)
        usuario = user_data.user
        taller_id = usuario.app_metadata.get("taller_id") if usuario.app_metadata else None
        
        if not taller_id and usuario.email:
            taller_por_email = supabase.table("talleres").select("id").eq("email", usuario.email).execute().data
            if taller_por_email:
                taller_id = taller_por_email[0]["id"]
    except Exception as e:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    if not taller_id:
        raise HTTPException(status_code=403, detail="Usuario sin taller asignado")

    try:
        taller_info = supabase.table("talleres").select("estado_pago, fecha_vencimiento").eq("id", taller_id).execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno verificando la suscripción del taller")

    if taller_info:
        estado_pago = taller_info[0].get("estado_pago")
        fecha_vencimiento = taller_info[0].get("fecha_vencimiento")
        
        mensaje_amable = (
            "Tu acceso está suspendido actualmente por falta de pago."
            "Por favor, comunícate con Keiser para gestionar la reactivación de tu cuenta"
        )

        if estado_pago == "suspendido" or (fecha_vencimiento and datetime.now().strftime("%Y-%m-%d") > fecha_vencimiento):
            raise HTTPException(status_code=402, detail=mensaje_amable)

    cliente_seguro = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    cliente_seguro.postgrest.auth(token)

    return cliente_seguro, taller_id


def obtener_superadmin(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta el Pase VIP (Token)")

    token = auth_header.split(" ")[1]

    try:
        user_data = supabase.auth.get_user(token)
        rol = user_data.user.app_metadata.get("rol")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    if rol != "superadmin":
        raise HTTPException(status_code=403, detail="No tienes permisos de administrador")

    return token

# ==============================================================================
# SISTEMA DE AUTENTICACIÓN (LOGIN)
# ==============================================================================
class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/login")
def login(credenciales: LoginRequest):
    cliente_auth = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    try:
        respuesta = cliente_auth.auth.sign_in_with_password({
            "email": credenciales.email,
            "password": credenciales.password
        })
        token = respuesta.session.access_token
        return {"status": "success", "mensaje": "Inicio de sesión exitoso", "token": token}
    except Exception:
        return {"status": "error", "mensaje": "Credenciales inválidas o error de red."}

# ==============================================================================
# PANEL DE ADMINISTRACIÓN GLOBAL
# ==============================================================================

class NuevoTallerRequest(BaseModel):
    nombre_taller: str
    email_jefe: EmailStr
    password_jefe: str = Field(min_length=6)
    plan: str = "mensual"

class ActualizarTallerRequest(BaseModel):
    plan: str | None = None
    estado_pago: str | None = None
    fecha_vencimiento: str | None = None

class NuevoUsuarioTallerRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    rol: str = "supervisor"


@app.post("/admin/talleres")
def crear_taller(datos: NuevoTallerRequest, request: Request):
    obtener_superadmin(request)

    resultado_taller = supabase.table("talleres").insert({
        "nombre": datos.nombre_taller,
        "email": datos.email_jefe,
        "plan": datos.plan,
        "estado_pago": "activo",
    }).execute()

    if not resultado_taller.data:
        raise HTTPException(status_code=500, detail="No se pudo crear el registro del taller")

    taller_id = resultado_taller.data[0]["id"]

    try:
        supabase.auth.admin.create_user({
            "email": datos.email_jefe,
            "password": datos.password_jefe,
            "email_confirm": True,
            "app_metadata": {"taller_id": taller_id, "rol": "jefe"}
        })
    except Exception as e:
        return {
            "status": "parcial",
            "taller_id": taller_id,
            "mensaje": f"Taller creado, pero el usuario jefe falló: {e}."
        }

    return {"status": "éxito", "taller_id": taller_id, "mensaje": f"Taller '{datos.nombre_taller}' creado."}


@app.get("/admin/talleres")
def listar_talleres(request: Request):
    obtener_superadmin(request)
    data = supabase.table("talleres").select("*").order("id").execute().data
    return {"talleres": data}


@app.patch("/admin/talleres/{taller_id}")
def actualizar_taller(taller_id: str, datos: ActualizarTallerRequest, request: Request):
    obtener_superadmin(request)
    cambios = {k: v for k, v in datos.model_dump().items() if v is not None}
    if not cambios:
        raise HTTPException(status_code=400, detail="No enviaste ningún campo para actualizar")

    supabase.table("talleres").update(cambios).eq("id", taller_id).execute()
    return {"status": "éxito", "mensaje": "Taller actualizado", "cambios": cambios}


@app.post("/admin/talleres/{taller_id}/usuarios")
def agregar_usuario_taller(taller_id: str, datos: NuevoUsuarioTallerRequest, request: Request):
    obtener_superadmin(request)
    taller = supabase.table("talleres").select("id").eq("id", taller_id).execute().data
    if not taller:
        raise HTTPException(status_code=404, detail="Ese taller no existe")

    try:
        supabase.auth.admin.create_user({
            "email": datos.email,
            "password": datos.password,
            "email_confirm": True,
            "app_metadata": {"taller_id": taller_id, "rol": datos.rol}
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo crear el usuario: {e}")

    return {"status": "éxito", "mensaje": f"Usuario agregado."}
from datetime import timedelta

@app.get("/admin/dashboard-metrics")
def get_dashboard_metrics(request: Request):
    obtener_superadmin(request)
    
    try:
        # 1. Consultar talleres
        talleres = supabase.table("talleres").select("id, nombre, estado_pago, plan, fecha_vencimiento").execute().data
        
        total = len(talleres)
        activos_lista = [t for t in talleres if t.get("estado_pago") == "activo"]
        activos = len(activos_lista)
        suspendidos = sum(1 for t in talleres if t.get("estado_pago") == "suspendido")

        # 2. Consultar MRR
        precios_planes = {"mensual": 29.99, "trimestral": 79.99, "anual": 299.99}
        mrr = sum(precios_planes.get(t.get("plan", "mensual"), 0) for t in activos_lista)
        
        # 3. Consultar uso de sistema de hoy
        hoy_inicio, hoy_fin = limites_dia_ecuador() 
        cola_hoy = supabase.table("cola_mensajes").select("id, estado").gte("fecha_hora", hoy_inicio).lte("fecha_hora", hoy_fin).execute().data
        ai_today = len(cola_hoy)
        errors = sum(1 for msj in cola_hoy if str(msj.get("estado")).startswith("Error"))

        # =========================================================
        # 4. LÓGICA DE ALERTAS PREVENTIVAS
        # =========================================================
        hoy_obj = datetime.now(ZONA_ECUADOR).date()
        limite_inactividad_obj = hoy_obj - timedelta(days=3) # 3 días sin uso = Riesgo
        limite_inactividad_str = limite_inactividad_obj.strftime("%Y-%m-%d 00:00:00")

        # Buscar talleres con actividad reciente
        reparaciones_recientes = supabase.table("reparaciones").select("taller_id").gte("fecha_hora", limite_inactividad_str).execute().data
        talleres_con_actividad = set(r["taller_id"] for r in reparaciones_recientes)

        alertas = []
        
        for t in activos_lista:
            nombre = t.get("nombre", "Taller Desconocido")
            vencimiento_str = t.get("fecha_vencimiento")

            # A. Riesgo de abandono (Churn)
            if t["id"] not in talleres_con_actividad:
                alertas.append({"tipo": "riesgo", "mensaje": f"⚠️ <b>{nombre}</b> lleva más de 3 días sin registrar actividad."})

            # B. Pagos vencidos o próximos a vencer
            if vencimiento_str:
                vencimiento_obj = datetime.strptime(vencimiento_str, "%Y-%m-%d").date()
                dias_restantes = (vencimiento_obj - hoy_obj).days

                if dias_restantes < 0:
                    alertas.append({"tipo": "critico", "mensaje": f"🔴 <b>{nombre}</b> tiene el pago vencido ({vencimiento_str})."})
                elif 0 <= dias_restantes <= 5:
                    alertas.append({"tipo": "advertencia", "mensaje": f"🟡 <b>{nombre}</b> vence en {dias_restantes} días ({vencimiento_str})."})

        # C. Alerta del sistema
        if errors > 0:
            alertas.insert(0, {"tipo": "critico", "mensaje": f"🔴 Hay <b>{errors} mensajes fallidos</b> en la cola de IA que requieren tu atención."})

        return {
            "workshops": {
                "total": total,
                "active": activos,
                "suspended": suspendidos
            },
            "subscriptions": {
                "mrr": round(mrr, 2),
                "active": activos
            },
            "system": {
                "ai_today": ai_today,
                "errors": errors
            },
            "alertas": alertas # Nuevo nodo enviado al panel
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# ---------------------------------------------------
@app.get("/admin/talleres/{taller_id}/ficha-360")
def obtener_ficha_360(taller_id: str, request: Request):
    obtener_superadmin(request)
    
    try:
        # 1. Info básica
        taller_res = supabase.table("talleres").select("*").eq("id", taller_id).execute().data
        if not taller_res:
            raise HTTPException(status_code=404, detail="Taller no encontrado")
        taller = taller_res[0]
        
        # 2. Métricas de uso cruzando la tabla 'reparaciones'
        reparaciones = supabase.table("reparaciones").select("vehiculo, cliente, fecha_hora").eq("taller_id", taller_id).execute().data
        
        total_reparaciones = len(reparaciones)
        # Usamos set() para contar cuántos vehículos y clientes únicos hay
        vehiculos_unicos = len(set(r.get("vehiculo") for r in reparaciones if r.get("vehiculo")))
        clientes_unicos = len(set(r.get("cliente") for r in reparaciones if r.get("cliente")))
        
        # Última actividad registrada
        ultima_actividad = "Sin actividad"
        if reparaciones:
            fechas = [r.get("fecha_hora") for r in reparaciones if r.get("fecha_hora")]
            if fechas:
                ultima_actividad = max(fechas)
                
        # 3. Uso de IA (Mensajes) hoy
        hoy_inicio, hoy_fin = limites_dia_ecuador()
        mensajes_hoy = supabase.table("cola_mensajes").select("id").eq("taller_id", taller_id).gte("fecha_hora", hoy_inicio).lte("fecha_hora", hoy_fin).execute().data
        ia_hoy = len(mensajes_hoy)

        return {
            "taller": {
                "id": taller.get("id"),
                "nombre": taller.get("nombre"),
                "email": taller.get("email"),
                "plan": taller.get("plan", "N/A"),
                "estado_pago": taller.get("estado_pago", "N/A"),
                "fecha_vencimiento": taller.get("fecha_vencimiento") or "No definida",
                "created_at": taller.get("created_at", "").split("T")[0] if taller.get("created_at") else "Desconocida"
            },
            "uso": {
                "reparaciones": total_reparaciones,
                "vehiculos": vehiculos_unicos,
                "clientes": clientes_unicos,
                "usuarios_admin": 1 # Por defecto mínimo el jefe
            },
            "actividad": {
                "ultima_actividad": ultima_actividad,
                "ia_hoy": ia_hoy
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # ==============================================================================
# MONITOR DE IA Y COLA DE PROCESAMIENTO
# ==============================================================================
@app.get("/admin/cola")
def obtener_cola_ia(request: Request, limite: int = 50):
    obtener_superadmin(request)
    try:
        # Obtenemos los últimos mensajes, trayendo también el nombre del taller
        res = supabase.table("cola_mensajes") \
            .select("id, texto, estado, fecha_hora, talleres(nombre)") \
            .order("id", desc=True) \
            .limit(limite) \
            .execute()
        
        return {"mensajes": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer la cola: {str(e)}")

@app.post("/admin/cola/{mensaje_id}/reprocesar")
def reprocesar_mensaje(mensaje_id: str, background_tasks: BackgroundTasks, request: Request):
    obtener_superadmin(request)
    try:
        # 1. Regresamos el estado a "Pendiente"
        supabase.table("cola_mensajes").update({"estado": "Pendiente"}).eq("id", mensaje_id).execute()
        
        # 2. ¡Despertamos al trabajador silencioso inmediatamente!
        background_tasks.add_task(trabajador_silencioso)
        
        return {"status": "éxito", "mensaje": "Mensaje enviado a reprocesamiento"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# ESTRUCTURAS DE DATOS (PYDANTIC)
# ==============================================================================

class RepuestoUsado(BaseModel):
    codigo: str = Field(description="Código exacto del repuesto usado (ej: vss005)")
    cantidad: int = Field(description="Cantidad de unidades utilizadas")



class TrabajoTaller(BaseModel):
    vehiculo: str = Field(description="OBLIGATORIO: Extrae ÚNICAMENTE la placa del vehículo (ej: PXY9876, GPU340). NUNCA incluyas la marca o color aquí.")
    modelo: str = Field(default="", description="Marca y modelo del vehículo, ej: 'Toyota Corolla'. Vacío si no se menciona.")
    color: str = Field(default="", description="Color, ej: 'blanco'. Vacío si no se menciona.")
    anio: str = Field(default="")
    cilindraje: str = Field(default="")
    cliente: str = ""
    cedula: str = ""
    telefono: str = ""
    motivo: str = ""
    trabajo_realizado: str = ""
    oficial: str = ""
    cobro: float = 0.0
    metodo_pago: str = ""
    banco: str = ""
    repuestos_usados: list[RepuestoUsado] = Field(default=[])

    @field_validator("vehiculo", mode="before")
    @classmethod
    def _limpiar_placa_inteligente(cls, v):
        if not v or str(v).lower() in ["s/c", "n/a", "no especificado", "ninguna", "---"]:
            return ""
        
        # 1. Buscar patrón exacto de placa Ecuatoriana (ej: ABC-1234, GPU340, AB-123)
        patron = re.search(r'[a-zA-Z]{2,3}[-\s]?\d{3,4}[a-zA-Z]?', str(v))
        if patron:
            return normalizar_placa(patron.group(0))
            
        # 2. Si no es una placa estándar pero es corto (menos de 9 caracteres), lo aceptamos
        if len(str(v)) <= 9:
            return normalizar_placa(str(v))
            
        # 3. Si la IA mandó un texto gigante y no hay placa visible, se descarta para no corromper la BD
        return ""

    @field_validator("cobro", mode="before")
    @classmethod
    def _asegurar_numero(cls, v):
        if not v or v == "": 
            return 0.0
        # Limpiar símbolos de dólar o comas si la IA los envía por error
        if isinstance(v, str):
            v = v.replace("$", "").replace(",", ".").strip()
            # Extraer solo los números
            numeros = re.findall(r"[-+]?\d*\.\d+|\d+", v)
            if numeros:
                return float(numeros[0])
        try:
            return float(v)
        except:
            return 0.0

class GastoTaller(BaseModel):
    monto: float = Field(description="Cantidad de dinero gastada en números decimales")
    motivo: str = Field(description="Motivo o concepto del gasto (ej: compra de repuesto, gasolina, almuerzo, etc.)")
    vehiculo: str = Field(description="Vehículo o placa relacionada al gasto, o 'N/A' si no aplica a un carro específico")
    responsable: str = Field(description="Nombre de la persona que realizó el gasto")

class RepuestoInventario(BaseModel):
    codigo: str = Field(description="Código del repuesto (ej: vss005). Si no tiene, pon 'S/C'")
    nombre: str = Field(description="Nombre de la pieza (ej: sensor vss, pastillas)")
    marca: str = Field(description="Marca del repuesto (ej: besuto)")
    proveedor: str = Field(description="Nombre del proveedor o distribuidor que vendió o dejó el repuesto", default="General")
    aplicacion: str = Field(description="Para qué vehículo/marca es (ej: kia)", default="General")
    cantidad: int = Field(description="Cantidad de unidades que ingresan")
    costo: float = Field(description="Precio que le costó al taller comprarlo")
    precio_venta: float = Field(description="Precio sugerido de venta al cliente")

class DevolucionInventario(BaseModel):
    codigo: str = Field(description="Código exacto del repuesto devuelto (ej: vss005)")
    cantidad: int = Field(description="Cantidad de unidades que reingresan al stock.")
    motivo: str = Field(default="Devolución de cliente", description="Motivo de la devolución")

class ClasificacionMensaje(BaseModel):
    tipo: str = Field(description="Debe ser estrictamente 'reparacion', 'gasto', 'inventario' o 'devolucion'")
    reparacion: TrabajoTaller | None = Field(default=None)
    gasto: GastoTaller | None = Field(default=None)
    inventario: RepuestoInventario | None = Field(default=None)
    devolucion: DevolucionInventario | None = Field(default=None)

class SolicitudUnificada(BaseModel):
    texto: str
# ==============================================================================
# TRABAJADOR SILENCIOSO
# ==============================================================================

async def trabajador_silencioso():
    # Reclama mensajes de forma ATÓMICA vía la función SQL reclamar_mensajes_pendientes
    response = supabase.rpc("reclamar_mensajes_pendientes", {"cantidad": 20}).execute()
    pendientes = response.data

    if not pendientes:
        return

    for msj in pendientes:
        id_msj = msj["id"]
        texto_msj = msj["texto"]
        taller_id = msj["taller_id"]
        tiempo_actual = ahora_utc_str()

        prompt = f"""
        Eres un asistente contable inteligente de un taller mecánico.
        Analiza el siguiente mensaje y determina si se trata de un trabajo de reparación (ingreso), un gasto operativo (salida de dinero), un registro de INVENTARIO (ingreso de repuestos, extrayendo el proveedor si se menciona), o una DEVOLUCION.

        Clasificalo correctamente y extrae los datos correspondientes. Si faltan datos en el mensaje, déjalos vacíos o en 0 según corresponda.

        Responde en JSON con esta estructura EXACTA. Separa las características del vehículo en sus campos correspondientes:
        {{
          "tipo": "reparacion" | "gasto" | "inventario" | "devolucion",
          "reparacion": {{
              "vehiculo": "EXTRAE SOLO LA PLACA AQUÍ (sin guiones, ej. ABB3322)",
              "modelo": "Marca y modelo (ej. Chevrolet Sail)",
              "color": "Color del auto (ej. negro)",
              "anio": "Año (ej. 2023)",
              "cilindraje": "Cilindraje (ej. 1.4)",
              "cliente": "Nombre del cliente",
              "cobro": 0.0,
              "motivo": "Síntoma o razón de ingreso (ej. 'le falla un cilindro').",
              "trabajo_realizado": "SOLO llénalo si se reporta una reparación, cambio o arreglo realizado. Si el auto RECIÉN ENTRA o solo se reporta un fallo, déjalo estrictamente VACÍO (\"\").",
              "repuestos_usados": [
                  {{"codigo": "codigo_repuesto", "cantidad": 1}}
              ]
          }}

        Mensaje: "{texto_msj}"
        """
        try:
            resultado, proveedor_usado = await asyncio.to_thread(generar_json_con_respaldo, prompt)
            resultado = ClasificacionMensaje.model_validate(resultado).model_dump()
            tipo = resultado.get("tipo")

        except Exception as e:
            # NUEVO BLOQUE: Clasificación inteligente de errores
            tipo_error = str(type(e))
            
            if "ValidationError" in tipo_error:
                estado_error = "Error de Formato. IA envió un dato incompleto o inválido."
            elif "JSONDecodeError" in tipo_error or "Expecting value" in str(e):
                estado_error = "Error. La respuesta de la IA fue ilegible."
            else:
                estado_error = "Error (IA no disponible o tiempo agotado)."
                
            print(f" Error procesando mensaje {id_msj}: {e}")
            supabase.table("cola_mensajes").update({"estado": estado_error}).eq("id", id_msj).execute()
            await asyncio.sleep(2)
            continue

        if tipo == "reparacion" and resultado.get("reparacion"):
            d = resultado["reparacion"]
            res_rep = supabase.table("reparaciones").select("id, estado, fecha_hora, modelo, color, anio, cilindraje").eq("vehiculo", d.get("vehiculo", "S/C")).eq("taller_id", taller_id).order("id", desc=True).limit(1).execute()
            ultima_orden = res_rep.data[0] if res_rep.data else None

            if ultima_orden and ultima_orden["estado"] == 'Terminado' and (d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != ""):
                fecha_ultima = ultima_orden["fecha_hora"].split(" ")[0]
                hoy = tiempo_actual.split(" ")[0]
                if fecha_ultima == hoy:
                    supabase.table("cola_mensajes").update({"estado": "Bloqueado (Duplicado)"}).eq("id", id_msj).execute()
                    continue

            if (d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != "") and d.get("repuestos_usados"):
                for repuesto in d.get("repuestos_usados", []):
                    inv_res = supabase.table("inventario").select("id, cantidad").eq("codigo", repuesto.get("codigo")).eq("taller_id", taller_id).execute()
                    if inv_res.data:
                        inv_item = inv_res.data[0]
                        nueva_cant = max(0, inv_item["cantidad"] - repuesto.get("cantidad", 0))
                        supabase.table("inventario").update({"cantidad": nueva_cant}).eq("id", inv_item["id"]).execute()

            if ultima_orden and ultima_orden["estado"] == 'Pendiente':
                if d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != "":
                    supabase.table("reparaciones").update({
                        "trabajo_realizado": d.get("trabajo_realizado", ""),
                        "cobro": d.get("cobro", 0.0),
                        "metodo_pago": d.get("metodo_pago", ""),
                        "banco": d.get("banco", ""),
                        "estado": "Terminado"
                    }).eq("id", ultima_orden["id"]).execute()
                else:
                    supabase.table("cola_mensajes").update({"estado": "Bloqueado (Ya pendiente)"}).eq("id", id_msj).execute()
                    continue
            else:
                estado_nuevo = 'Terminado' if (d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != "") else 'Pendiente'

                def _heredar(campo):
                    valor_nuevo = d.get(campo, "")
                    if valor_nuevo:
                        return valor_nuevo
                    return ultima_orden.get(campo, "") if ultima_orden else ""

                supabase.table("reparaciones").insert({
                    "taller_id": taller_id,
                    "vehiculo": d.get("vehiculo", "S/C"),
                    "modelo": _heredar("modelo"),
                    "color": _heredar("color"),
                    "anio": _heredar("anio"),
                    "cilindraje": _heredar("cilindraje"),
                    "cliente": d.get("cliente", ""),
                    "cedula": d.get("cedula", ""),
                    "telefono": d.get("telefono", ""),
                    "motivo": d.get("motivo", ""),
                    "trabajo_realizado": d.get("trabajo_realizado", ""),
                    "oficial": d.get("oficial", ""),
                    "cobro": d.get("cobro", 0.0),
                    "metodo_pago": d.get("metodo_pago", ""),
                    "banco": d.get("banco", ""),
                    "fecha_hora": tiempo_actual,
                    "estado": estado_nuevo
                }).execute()

        elif tipo == "gasto" and resultado.get("gasto"):
            d = resultado["gasto"]
            supabase.table("gastos").insert({
                "taller_id": taller_id,
                "monto": d.get("monto", 0.0),
                "motivo": d.get("motivo", ""),
                "vehiculo": d.get("vehiculo", "N/A"),
                "responsable": d.get("responsable", ""),
                "fecha_hora": tiempo_actual
            }).execute()

        elif tipo == "inventario" and resultado.get("inventario"):
            d = resultado["inventario"]
            inv_res = supabase.table("inventario").select("id, cantidad").eq("codigo", d.get("codigo", "S/C")).eq("taller_id", taller_id).execute()

            if inv_res.data:
                rep_existente = inv_res.data[0]
                nueva_cantidad = rep_existente["cantidad"] + d.get("cantidad", 0)
                supabase.table("inventario").update({
                    "cantidad": nueva_cantidad,
                    "costo": d.get("costo", 0.0),
                    "precio_venta": d.get("precio_venta", 0.0),
                    "proveedor": d.get("proveedor", "General"),
                    "fecha_actualizacion": tiempo_actual
                }).eq("id", rep_existente["id"]).execute()
            else:
                supabase.table("inventario").insert({
                    "taller_id": taller_id,
                    "codigo": d.get("codigo", "S/C"),
                    "nombre": d.get("nombre", ""),
                    "marca": d.get("marca", ""),
                    "proveedor": d.get("proveedor", "General"),
                    "aplicacion": d.get("aplicacion", "General"),
                    "cantidad": d.get("cantidad", 0),
                    "costo": d.get("costo", 0.0),
                    "precio_venta": d.get("precio_venta", 0.0),
                    "fecha_actualizacion": tiempo_actual
                }).execute()

        elif tipo == "devolucion" and resultado.get("devolucion"):
            d = resultado["devolucion"]
            inv_res = supabase.table("inventario").select("id, cantidad").eq("codigo", d.get("codigo", "S/C")).eq("taller_id", taller_id).execute()
            if inv_res.data:
                rep = inv_res.data[0]
                nueva_cantidad = rep["cantidad"] + d.get("cantidad", 0)
                supabase.table("inventario").update({
                    "cantidad": nueva_cantidad,
                    "fecha_actualizacion": tiempo_actual
                }).eq("id", rep["id"]).execute()
            else:
                supabase.table("cola_mensajes").update({"estado": "Error (Repuesto no encontrado)"}).eq("id", id_msj).execute()
                continue
        else:
            supabase.table("cola_mensajes").update({"estado": "Error (No clasificable)"}).eq("id", id_msj).execute()
            continue

        supabase.table("cola_mensajes").update({"estado": "Procesado"}).eq("id", id_msj).execute()
        await asyncio.sleep(3)

# ==============================================================================
# AUTO-RECUPERACIÓN DE LA COLA (sin depender de que llegue un mensaje nuevo)
# ==============================================================================
# Antes, si la cola se quedaba a medias (ej: cuota de Gemini agotada), se
# congelaba hasta que alguien enviara otro mensaje nuevo desde la app —
# de ahí los retrasos de horas. Este ciclo revisa la cola cada 3 minutos
# por su cuenta, para que se recupere sola en cuanto la IA vuelva a responder.

@app.on_event("startup")
async def iniciar_vigilancia_de_cola():
    async def ciclo_de_vigilancia():
        while True:
            await asyncio.sleep(180)  # cada 3 minutos
            try:
                await trabajador_silencioso()
            except Exception as e:
                print(f" Error en el ciclo de auto-recuperación de la cola: {e}")

    asyncio.create_task(ciclo_de_vigilancia())

# ==============================================================================
# GERENTE ANALÍTICO 
# ==============================================================================

HERRAMIENTAS_REPORTES = [
    {
        "type": "function",
        "function": {
            "name": "historial_vehiculo",
            "description": (
                "Busca el historial de reparaciones de un vehículo por su placa. "
                "cuándo vino la última vez,"
                "por qué motivo o daño llegó,  "
                "qué se le hizo, cuánto se cobró, método de pago o técnico responsable."
            ),
            "parameters": {
                "type": "object",
                "properties": {"placa": {"type": "string", "description": "Placa del vehículo, ej: ABB777"}},
                "required": ["placa"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cliente_top_visitas",
            "description": "Devuelve el cliente que más veces ha visitado el taller en un año específico.",
            "parameters": {
                "type": "object",
                "properties": {"anio": {"type": "integer", "description": "Año a consultar, ej: 2026"}},
                "required": ["anio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cliente_top_gasto",
            "description": "Devuelve el cliente que más dinero ha gastado en el taller y el monto total.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fecha_inicio": {"type": "string", "description": "Fecha inicio YYYY-MM-DD, opcional"},
                    "fecha_fin": {"type": "string", "description": "Fecha fin YYYY-MM-DD, opcional"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rendimiento_tecnico",
            "description": (
                "Calcula cuánto dinero ha generado un técnico específico, o el ranking de todos "
                "los técnicos, en un mes y año dado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mes": {"type": "integer", "description": "Mes numérico, 1 a 12"},
                    "anio": {"type": "integer", "description": "Año, ej: 2026"},
                    "tecnico": {"type": "string", "description": "Nombre del técnico/oficial, opcional"},
                },
                "required": ["mes", "anio"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "info_repuesto",
            "description": (
                "Busca repuestos en el inventario por nombre, código, marca o descripción libre "
                "de compatibilidad (ej: 'sensor CKP Sail 1.4 2013'). No hace falta el código exacto: "
                "la búsqueda es flexible y puede devolver varios resultados de distintas marcas."
            ),
            "parameters": {
                "type": "object",
                "properties": {"nombre_o_codigo": {"type": "string", "description": "Descripción, nombre, marca o código del repuesto, tal como lo dijo el usuario"}},
                "required": ["nombre_o_codigo"],
            },
        },
    },
]

def ejecutar_funcion_reporte(cliente_seguro, nombre_funcion: str, args: dict) -> dict:
    if nombre_funcion == "historial_vehiculo":
        placa = normalizar_placa(args.get("placa", ""))
        data = (
            cliente_seguro.table("reparaciones")
            .select("*")
            .ilike("vehiculo", f"%{placa}%")
            .order("fecha_hora", desc=True)
            .limit(10)
            .execute()
        ).data
        return {"resultados": data}

    if nombre_funcion == "cliente_top_visitas":
        anio = args.get("anio")
        data = cliente_seguro.rpc("cliente_top_visitas", {"p_anio": anio}).execute().data
        return {"resultado": data[0] if data else None}

    if nombre_funcion == "cliente_top_gasto":
        params = {}
        if args.get("fecha_inicio"):
            params["p_fecha_inicio"] = args["fecha_inicio"]
        if args.get("fecha_fin"):
            params["p_fecha_fin"] = args["fecha_fin"]
        data = cliente_seguro.rpc("cliente_top_gasto", params).execute().data
        return {"resultado": data[0] if data else None}

    if nombre_funcion == "rendimiento_tecnico":
        params = {"p_mes": args.get("mes"), "p_anio": args.get("anio")}
        if args.get("tecnico"):
            params["p_tecnico"] = args["tecnico"]
        data = cliente_seguro.rpc("rendimiento_tecnico", params).execute().data
        return {"resultados": data}

    if nombre_funcion == "info_repuesto":
        termino = args.get("nombre_o_codigo", "")
        # Búsqueda de texto completo (no ILIKE literal): encuentra coincidencias
        # aunque el usuario no sepa el código exacto ni el orden de las palabras
        # ("sensor CKP Sail 1.4 2013" en vez de "CKP001"). El campo "aplicacion"
        # es el que guarda la compatibilidad de vehículo — nunca lo infiere la IA.
        taller_id = args.get("_taller_id")
        data = cliente_seguro.rpc(
            "buscar_repuestos_flexible",
            {"p_taller_id": taller_id, "p_termino": termino, "p_limite": 15},
        ).execute().data
        return {"resultados": data}

    return {"error": f"Función '{nombre_funcion}' no reconocida"}

def formatear_resultado_sin_ia(nombre_funcion: str, resultado: dict) -> str:
    if nombre_funcion == "info_repuesto":
        items = resultado.get("resultados", [])
        if not items:
            return "No encontré ningún repuesto que coincida con esa descripción."
        lineas = [f"**Encontrado{'s' if len(items) > 1 else ''} ({len(items)}):**"]
        for r in items:
            lineas.append(
                f"- **{r.get('nombre', '?')}** — Marca: {r.get('marca', 'N/A')} · "
                f"Código: {r.get('codigo', 'S/C')} · Aplicación: {r.get('aplicacion', 'N/A')} · "
                f"Precio: ${r.get('precio_venta', 0)} · Stock: {r.get('cantidad', 0)} · "
                f"Proveedor: {r.get('proveedor', 'N/A')}"
            )
        return "\n".join(lineas)

    if nombre_funcion == "historial_vehiculo":
        items = resultado.get("resultados", [])
        if not items:
            return "No encontré registros para esa placa."
        lineas = ["**Historial del vehículo:**"]
        for r in items:
            lineas.append(
                f"- {r.get('fecha_hora', '?')}: {r.get('trabajo_realizado', 'N/A')} — "
                f"${r.get('cobro', 0)} ({r.get('metodo_pago', 'N/A')}) por {r.get('oficial', 'N/A')}"
            )
        return "\n".join(lineas)

    if nombre_funcion in ("cliente_top_visitas", "cliente_top_gasto"):
        r = resultado.get("resultado")
        if not r:
            return "No hay datos suficientes para calcular esto todavía."
        return f"**Resultado:** {r}"

    if nombre_funcion == "rendimiento_tecnico":
        items = resultado.get("resultados", [])
        if not items:
            return "No hay registros de técnicos para ese periodo."
        lineas = ["**Rendimiento por técnico:**"]
        for r in items:
            lineas.append(f"- {r.get('oficial', '?')}: ${r.get('total_generado', 0)} ({r.get('trabajos', 0)} trabajos)")
        return "\n".join(lineas)

    return f"Resultado: {resultado}"

def responder_consulta_analitica(cliente_seguro, texto_usuario: str, taller_id) -> str:
    """
    Motor analítico de dos turnos: el modelo decide qué función llamar,
    nosotros la ejecutamos contra Supabase, y el modelo redacta la
    respuesta final en español con el resultado real. Groq es el
    proveedor principal; DeepSeek es el respaldo si Groq falla.
    """
    instruccion_sistema = (
        "Eres el gerente analítico de un taller mecánico. Para responder preguntas "
        "sobre historial de vehículos, clientes, técnicos o repuestos, SIEMPRE debes "
        "llamar a la función correspondiente en vez de inventar una respuesta. "
        "Si la pregunta no menciona mes/año explícito para técnicos, usa el mes y año actuales."
    )

    def _decidir_funcion(cliente_ia, modelo):
        return cliente_ia.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": instruccion_sistema},
                {"role": "user", "content": texto_usuario},
            ],
            tools=HERRAMIENTAS_REPORTES,
            tool_choice="auto",
        )

    llamada_nombre = None
    args = {}
    texto_directo = None

    try:
        resp = _decidir_funcion(groq_client, MODELO_GROQ)
    except Exception as e_groq:
        print(f"⚠️ Groq falló decidiendo la consulta analítica: {e_groq}")
        if not deepseek_client:
            return "⏳ El asistente de IA no está disponible en este momento. Intenta de nuevo en unos minutos."
        try:
            resp = _decidir_funcion(deepseek_client, MODELO_DEEPSEEK)
        except Exception as e_ds:
            print(f"⚠️ DeepSeek también falló decidiendo la consulta analítica: {e_ds}")
            return "⚠️ El asistente de IA no está disponible en este momento (ni el proveedor principal ni el de respaldo). Intenta de nuevo en unos minutos."

    msj = resp.choices[0].message
    if msj.tool_calls:
        llamada_nombre = msj.tool_calls[0].function.name
        args = json.loads(msj.tool_calls[0].function.arguments or "{}")
    else:
        texto_directo = msj.content or "No pude interpretar esa pregunta como una consulta de reportes."

    if texto_directo is not None:
        return texto_directo

    resultado_funcion = ejecutar_funcion_reporte(cliente_seguro, llamada_nombre, {**args, "_taller_id": taller_id})

    # --- Segundo turno: redactar la respuesta final con el resultado real ---
    instruccion_redaccion = (
        "Redacta la respuesta final en español, clara y con formato Markdown. "
        "Si el resultado viene vacío, dilo explícitamente en vez de inventar datos. "
        "Si el resultado trae varios repuestos (distintas marcas, códigos o aplicaciones), "
        "MUÉSTRALOS TODOS por separado con su marca, precio y stock — nunca elijas uno solo "
        "ni afirmes cuál es el correcto para el vehículo del cliente; esa decisión es del taller, "
        "no tuya. Nunca afirmes que un repuesto es compatible con un vehículo salvo que el campo "
        "'aplicación' del resultado lo confirme explícitamente."
    )
    mensajes_redaccion = [
        {"role": "system", "content": instruccion_redaccion},
        {"role": "user", "content": texto_usuario},
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call_1", "type": "function",
            "function": {"name": llamada_nombre, "arguments": json.dumps(args)},
        }]},
        {"role": "tool", "tool_call_id": "call_1", "content": json.dumps(resultado_funcion)},
    ]

    try:
        resp_final = groq_client.chat.completions.create(model=MODELO_GROQ, messages=mensajes_redaccion)
        return resp_final.choices[0].message.content
    except Exception as e:
        print(f"⚠️ Groq falló redactando la respuesta final: {e}")

    if deepseek_client:
        try:
            resp_final = deepseek_client.chat.completions.create(model=MODELO_DEEPSEEK, messages=mensajes_redaccion)
            return resp_final.choices[0].message.content
        except Exception as e:
            print(f"⚠️ DeepSeek también falló redactando la respuesta final: {e}")

    # Última red de seguridad: mostrar el dato crudo sin redacción de IA.
    return formatear_resultado_sin_ia(llamada_nombre, resultado_funcion)


# ==============================================================================
# RECEPCIÓN WEB UNIFICADA (ENRUTADOR INTELIGENTE MODIFICADO)
# ==============================================================================

@app.post("/procesar-mensaje")
async def procesar_mensaje_unificado(solicitud: SolicitudUnificada, background_tasks: BackgroundTasks, request: Request):
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    texto_usuario = solicitud.texto
    tiempo_actual = ahora_utc_str()

    # MODIFICACIÓN: El router ahora devuelve JSON para saber si debe imprimir la orden
    prompt_router = f"""
    Analiza el siguiente texto de un usuario de taller mecánico y determina la intención.
    Responde ESTRICTAMENTE en formato JSON con las siguientes claves:
    - "accion": Debe ser "generar_orden" (si pide imprimir, descargar, ficha, factura u orden de trabajo de un vehículo), "consulta" (si hace preguntas de estadísticas, historiales o repuestos), o "registro" (si reporta trabajos, ingresos o gastos).
    - "placa": Extrae la placa del vehículo SOLO si la acción es "generar_orden" (sin espacios ni guiones). De lo contrario, déjalo vacío.

    Texto: "{texto_usuario}"
    """

    try:
        resultado_json, proveedor_usado = generar_json_con_respaldo(prompt_router)
        accion = resultado_json.get("accion", "registro")
        placa_extraida = resultado_json.get("placa", "")
    except Exception as e:
        # Ni Gemini ni Groq respondieron. NO asumimos "registro" a ciegas: eso
        # mete preguntas analíticas a la cola de trabajo y el usuario nunca ve
        # respuesta. Usamos un respaldo por palabras clave como último recurso.
        print(f"⚠️ Router de IA falló en ambos proveedores, usando respaldo por palabras clave. Error: {e}")
        texto_min = texto_usuario.lower()
        palabras_consulta = (
            "cuánt", "cuant", "cuál", "cual", "quién", "quien", "qué", "que ",
            "cómo", "como ", "dame", "dime", "muéstrame", "muestrame",
            "cuando fue", "última vez", "ultima vez", "?"
        )
        if any(p in texto_min for p in palabras_consulta):
            accion = "consulta"
        else:
            accion = "registro"
        placa_extraida = ""

    # --- NUEVA LÓGICA: GENERAR ORDEN DE TRABAJO ---
    if accion == "generar_orden":
        placa = normalizar_placa(placa_extraida)
        
        # Buscamos la reparación más reciente de esa placa, trayendo también sus repuestos anidados
        orden = (
            cliente_seguro.table("reparaciones")
            .select("*, reparacion_detalles(*, repuestos(codigo_producto, nombre_repuesto))")
            .eq("vehiculo", placa)
            .eq("taller_id", taller_id)
            .order("fecha_hora", desc=True)
            .limit(1)
            .execute()
        )
        
        # Lanzamos un HTTPException (Error 400) para que tu frontend salte al bloque 'if (!res.ok)'
        if not orden.data:
            raise HTTPException(status_code=400, detail=f"No se encontraron registros para la placa {placa} en este taller.")
            
        # Enviamos el paquete de datos puros al frontend
        return {
            "status": "imprimir_orden",
            "datos_orden": orden.data[0],
            "mensaje_bd": f"Preparando la orden de trabajo para el vehículo {placa}."
        }

    # --- CONSULTA ANALÍTICA ---
    if accion == "consulta":
        try:
            respuesta_analitica = responder_consulta_analitica(cliente_seguro, texto_usuario, taller_id)
        except Exception as e:
            print(f"⚠️ Falló la consulta analítica: {e}")
            respuesta_analitica = (
                "⚠️ El asistente de IA no está disponible en este momento. "
                "Intenta de nuevo en unos segundos."
            )

        # Si la IA no está disponible (cuota agotada, saturación, o cualquier
        # falla), NO descartamos el mensaje. Lo guardamos en la cola para que
        # se reintente solo cuando la IA vuelva a responder. Si en verdad era
        # una pregunta (no una acción), el trabajador de la cola simplemente
        # la marcará como "Error (No clasificable)" sin efecto — inofensivo.
        señales_no_disponible = ("⏳", "no está disponible", "temporalmente saturado")
        if any(s in respuesta_analitica for s in señales_no_disponible):
            cliente_seguro.table("cola_mensajes").insert({
                "taller_id": taller_id,
                "texto": texto_usuario,
                "fecha_hora": tiempo_actual,
                "estado": "Pendiente"
            }).execute()
            respuesta_analitica += "\n\n📥 Tu mensaje quedó guardado y se procesará automáticamente en cuanto la IA esté disponible."

        return {
            "status": "éxito_consulta",
            "tipo_detectado": "consulta",
            "mensaje_bd": respuesta_analitica,
            "registrado_a_las": tiempo_actual
        }

    # --- REGISTRO NORMAL (En segundo plano) ---
    cliente_seguro.table("cola_mensajes").insert({
        "taller_id": taller_id,
        "texto": texto_usuario,
        "fecha_hora": tiempo_actual,
        "estado": "Pendiente"
    }).execute()

    background_tasks.add_task(trabajador_silencioso)

    return {
        "status": "éxito",
        "tipo_detectado": "registro",
        "mensaje_bd": "✅ ¡Recibido en la nube! Procesando registro en segundo plano.",
        "registrado_a_las": tiempo_actual
    }

@app.get("/mi-taller")
def mi_taller(request: Request):
    """
    Devuelve el nombre del taller del usuario autenticado, tal como lo
    ingresó el admin al crearlo, para mostrarlo en el saludo de bienvenida.
    """
    _, taller_id = obtener_cliente_seguro(request)
    data = supabase.table("talleres").select("nombre").eq("id", taller_id).execute().data
    nombre = data[0]["nombre"] if data and data[0].get("nombre") else "tu taller"
    return {"nombre_taller": nombre}

# ==============================================================================
# CUADRE DE CAJA DIARIO
# ==============================================================================

@app.get("/reporte-dia")
def reporte_del_dia(request: Request, fecha: str | None = None):
    """
    Cuadre de caja del día: órdenes cerradas, egresos, ingresos vs egresos
    y rendimiento por técnico. 'fecha' es opcional en formato YYYY-MM-DD
    (día calendario de Ecuador); si se omite, usa el día actual en Ecuador.
    """
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    inicio_utc, fin_utc = limites_dia_ecuador(fecha)

    ordenes_cerradas = (
        cliente_seguro.table("reparaciones")
        .select("vehiculo, cliente, modelo, oficial, trabajo_realizado, cobro, metodo_pago, fecha_hora")
        .eq("taller_id", taller_id)
        .eq("estado", "Terminado")
        .gte("fecha_hora", inicio_utc)
        .lte("fecha_hora", fin_utc)
        .order("fecha_hora", desc=True)
        .execute()
    ).data

    egresos = (
        cliente_seguro.table("gastos")
        .select("monto, motivo, vehiculo, responsable, fecha_hora")
        .eq("taller_id", taller_id)
        .gte("fecha_hora", inicio_utc)
        .lte("fecha_hora", fin_utc)
        .order("fecha_hora", desc=True)
        .execute()
    ).data

    total_ingresos = sum(o.get("cobro", 0) or 0 for o in ordenes_cerradas)
    total_egresos = sum(g.get("monto", 0) or 0 for g in egresos)

    rendimiento: dict[str, dict] = {}
    for o in ordenes_cerradas:
        tecnico = o.get("oficial") or "Sin asignar"
        registro = rendimiento.setdefault(tecnico, {"trabajos": 0, "total_generado": 0.0})
        registro["trabajos"] += 1
        registro["total_generado"] += o.get("cobro", 0) or 0

    ranking_tecnicos = [
        {"tecnico": nombre, **datos}
        for nombre, datos in sorted(
            rendimiento.items(), key=lambda item: item[1]["total_generado"], reverse=True
        )
    ]

    return {
        "fecha": fecha or datetime.now(ZONA_ECUADOR).strftime("%Y-%m-%d"),
        "ordenes_cerradas": ordenes_cerradas,
        "egresos": egresos,
        "total_ingresos": round(total_ingresos, 2),
        "total_egresos": round(total_egresos, 2),
        "neto": round(total_ingresos - total_egresos, 2),
        "rendimiento_tecnicos": ranking_tecnicos,
    }

# ==============================================================================
# EXPORTACIONES E INVENTARIOS
# ==============================================================================

@app.get("/exportar-excel")
def exportar_excel(request: Request):
    try:
        cliente_seguro, _ = obtener_cliente_seguro(request)

        reps = cliente_seguro.table("reparaciones").select("*").execute().data
        gasts = cliente_seguro.table("gastos").select("*").execute().data
        inv = cliente_seguro.table("inventario").select("*").execute().data

        df_reparaciones = pd.DataFrame(reps)
        df_gastos = pd.DataFrame(gasts)
        df_inventario = pd.DataFrame(inv)

        hoy_archivo = datetime.now(ZONA_ECUADOR).strftime("%d-%m-%Y")
        inicio_utc, fin_utc = limites_dia_ecuador()

        if not df_reparaciones.empty and 'fecha_hora' in df_reparaciones.columns:
            df_reparaciones = df_reparaciones[
                (df_reparaciones['fecha_hora'] >= inicio_utc) & (df_reparaciones['fecha_hora'] <= fin_utc)
            ]

        if not df_gastos.empty and 'fecha_hora' in df_gastos.columns:
            df_gastos = df_gastos[
                (df_gastos['fecha_hora'] >= inicio_utc) & (df_gastos['fecha_hora'] <= fin_utc)
            ]

        carpeta_respaldos = "respaldos_excel"
        os.makedirs(carpeta_respaldos, exist_ok=True)

        nombre_archivo = f"Reporte Cloud AS {hoy_archivo}.xlsx"
        ruta_completa = os.path.join(carpeta_respaldos, nombre_archivo)

        with pd.ExcelWriter(ruta_completa, engine='openpyxl') as writer:
            df_reparaciones.to_excel(writer, sheet_name='Reparaciones', index=False)
            df_gastos.to_excel(writer, sheet_name='Gastos', index=False)
            df_inventario.to_excel(writer, sheet_name='Inventario', index=False)

        return FileResponse(
            ruta_completa,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=nombre_archivo
        )

    except Exception as error_principal:
        return {"status": "error_critico", "motivo_exacto": str(error_principal)}

@app.get("/vehiculos-pendientes")
def listar_pendientes(request: Request):
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    hoy_inicio, hoy_fin = limites_dia_ecuador()

    pendientes = (
        cliente_seguro.table("reparaciones")
        .select("vehiculo, cliente, telefono, modelo, color, anio, cilindraje, motivo, trabajo_realizado, cobro, metodo_pago, fecha_hora, estado")
        .eq("taller_id", taller_id)
        .eq("estado", "Pendiente")
        .execute()
    ).data

    terminados_hoy = (
        cliente_seguro.table("reparaciones")
        .select("vehiculo, cliente, telefono, modelo, color, anio, cilindraje, motivo, trabajo_realizado, cobro, metodo_pago, fecha_hora, estado")
        .eq("taller_id", taller_id)
        .eq("estado", "Terminado")
        .gte("fecha_hora", hoy_inicio)
        .lte("fecha_hora", hoy_fin)
        .execute()
    ).data

    return {"vehiculos": pendientes + terminados_hoy}

@app.get("/exportar-inventario")
def exportar_inventario(request: Request):
    try:
        cliente_seguro, _ = obtener_cliente_seguro(request)

        inv = cliente_seguro.table("inventario").select("*").execute().data
        df_inventario = pd.DataFrame(inv)

        if df_inventario.empty:
            df_inventario = pd.DataFrame(columns=[
                "id", "codigo", "nombre", "marca", "proveedor", "aplicacion",
                "cantidad", "costo", "precio_venta", "fecha_actualizacion"
            ])

        carpeta_respaldos = "respaldos_excel"
        os.makedirs(carpeta_respaldos, exist_ok=True)

        hoy_archivo = datetime.now(ZONA_ECUADOR).strftime("%d-%m-%Y")
        nombre_archivo = f"Auditoria_Inventario_{hoy_archivo}.xlsx"
        ruta_completa = os.path.join(carpeta_respaldos, nombre_archivo)

        with pd.ExcelWriter(ruta_completa, engine='openpyxl') as writer:
            df_inventario.to_excel(writer, sheet_name='Inventario', index=False)

        return FileResponse(
            ruta_completa,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            filename=nombre_archivo
        )

    except Exception as e:
        return {"status": "error_critico", "motivo_exacto": str(e)}

# ==============================================================================
# CONFIGURACIÓN DE ARRANQUE PARA LA NUBE
# ==============================================================================
if __name__ == "__main__":
    import uvicorn
    puerto = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=puerto, reload=False)