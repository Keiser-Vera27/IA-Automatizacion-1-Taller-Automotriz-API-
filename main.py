# ==============================================================================
# Proyecto: API del Taller Automotriz con IA, Supabase (Nube), y Proveedores
# Autor: Keiser Vera
# ==============================================================================

import os
import io
import re
import json
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, EmailStr
from dotenv import load_dotenv
from openai import OpenAI as ClienteOpenAICompatible
from supabase import create_client, Client
from postgrest.exceptions import APIError
from typing import Literal

def normalizar_placa(texto: str) -> str:
    """
    Deja la placa en un formato único: mayúsculas, sin espacios ni guiones.
    """
    if not texto:
        return texto
    return re.sub(r"[\s\-]", "", texto).upper().strip()


def normalizar_nombre_tecnico(nombre: str) -> str:
    """
    Normaliza el nombre de un técnico para poder cruzarlo entre tablas
    (reparaciones.oficial vs tecnicos.nombre) sin que un espacio extra,
    mayúscula distinta o tilde perdida haga que la comisión salga en 0.0
    aunque el técnico sí exista en la tabla.
    """
    return re.sub(r"\s+", " ", str(nombre or "")).strip().casefold()


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
        print(f"Groq falló, probando respaldo con DeepSeek: {e_groq}")
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

# Evita que el navegador siga usando versiones viejas de script.js/style.css
# después de un deploy. "no-cache" NO desactiva la caché: obliga a preguntar
# al servidor si el archivo cambió (ETag); si no cambió responde 304 y
# reutiliza la copia local, así que no hay costo de rendimiento.
@app.middleware("http")
async def no_cachear_frontend(request: Request, call_next):
    respuesta = await call_next(request)
    if request.url.path.startswith("/web"):
        respuesta.headers["Cache-Control"] = "no-cache"
    return respuesta

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
                alertas.append({"tipo": "riesgo", "mensaje": f"<b>{nombre}</b> lleva más de 3 días sin registrar actividad."})

            # B. Pagos vencidos o próximos a vencer
            if vencimiento_str:
                vencimiento_obj = datetime.strptime(vencimiento_str, "%Y-%m-%d").date()
                dias_restantes = (vencimiento_obj - hoy_obj).days

                if dias_restantes < 0:
                    alertas.append({"tipo": "critico", "mensaje": f"<b>{nombre}</b> tiene el pago vencido ({vencimiento_str})."})
                elif 0 <= dias_restantes <= 5:
                    alertas.append({"tipo": "advertencia", "mensaje": f"<b>{nombre}</b> vence en {dias_restantes} días ({vencimiento_str})."})

        # C. Alerta del sistema
        if errors > 0:
            alertas.insert(0, {"tipo": "critico", "mensaje": f"Hay <b>{errors} mensajes fallidos</b> en la cola de IA que requieren tu atención."})

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
    tipo: Literal["reparacion", "gasto", "inventario", "devolucion"] = Field(
        description="Clasifica estrictamente la acción. Las ventas de repuestos sin servicio mecánico son obligatoriamente 'reparacion'."
    )
    reparacion: TrabajoTaller | None = Field(default=None)
    gasto: GastoTaller | None = Field(default=None)
    inventario: RepuestoInventario | None = Field(default=None)
    devolucion: DevolucionInventario | None = Field(default=None)

class SolicitudUnificada(BaseModel):
    texto: str


class RouterIntencion(BaseModel):
    accion: Literal["registro", "consulta", "generar_orden"] = Field(
        description="Clasificación estricta de la intención del usuario."
    )
    placa: str = Field(
        default="", 
        description="Placa del vehículo SOLO si la acción es generar_orden."
    )
# ==============================================================================
# TRABAJADOR SILENCIOSO (CORREGIDO: CÉDULA Y BANCO)
# ==============================================================================

async def trabajador_silencioso():
    print("==================================================")
    print("EL TRABAJADOR SILENCIOSO SE HA DESPERTADO")
    
    try:
        response = supabase.rpc("reclamar_mensajes_pendientes", {"cantidad": 20, "max_intentos": 3}).execute()
        pendientes = response.data
        print(f"Mensajes atrapados en la BD: {len(pendientes) if pendientes else 0}")
    except Exception as e:
        print(f"ERROR AL HABLAR CON SUPABASE: {e}")
        return

    print("==================================================")

    if not pendientes:
        return

    for msj in pendientes:
        id_msj = msj["id"]
        texto_msj = msj["texto"]
        taller_id = msj["taller_id"]
        tiempo_actual = ahora_utc_str()

        # 1. Consultar técnicos válidos del taller
        tecnicos_res = supabase.table("tecnicos").select("nombre").eq("taller_id", taller_id).execute()
        nombres_tecnicos = [t["nombre"] for t in tecnicos_res.data] if tecnicos_res.data else []
        lista_tecnicos_str = ", ".join(nombres_tecnicos) if nombres_tecnicos else "Ninguno registrado"

        # Catálogo de servicios
        try:
            servicios_res = supabase.table("servicios").select("*").eq("taller_id", taller_id).execute()
            lista_servicios_str = "No hay servicios registrados aún."
            if servicios_res.data:
                lista_servicios_str = "\n".join([
                    f"- {s.get('nombre_servicio', s.get('nombre', 'Servicio'))}: ${s.get('precio_base', s.get('precio', 0.0))}" 
                    for s in servicios_res.data
                ])
        except Exception as e:
            print(f"Error interno leyendo el catálogo de servicios: {e}")
            lista_servicios_str = "Catálogo de servicios no disponible."

        # Catálogo de repuestos en inventario: sin esto, la IA no tiene forma de
        # saber qué "codigo" poner en repuestos_usados cuando el mensaje solo
        # menciona el nombre de la pieza (ej. "usé un filtro de aceite"), y
        # repuestos_usados queda vacío aunque sí se haya usado un repuesto real.
        try:
            inventario_res = supabase.table("inventario").select("codigo, nombre").eq("taller_id", taller_id).limit(500).execute()
            lista_inventario_str = "No hay repuestos registrados en el inventario aún."
            if inventario_res.data:
                lista_inventario_str = "\n".join([
                    f"- {i.get('codigo', 'S/C')}: {i.get('nombre', '')}"
                    for i in inventario_res.data
                ])
        except Exception as e:
            print(f"Error interno leyendo el inventario: {e}")
            lista_inventario_str = "Catálogo de inventario no disponible."

        # PROMPT CON EXTRACCIÓN MEJORADA DE CÉDULA Y BANCO
        prompt = f"""
        Eres un asistente contable inteligente de un taller mecánico.
        Analiza el siguiente mensaje y clasifícalo ESTRICTAMENTE en una de estas 4 categorías: 'reparacion', 'gasto', 'inventario' o 'devolucion'.

        REGLA DE VENTAS DIRECTAS AL MOSTRADOR:
        Si el mensaje describe la venta de un repuesto a un cliente que no ingresó su vehículo (ej. "se le vendió...", "compró...", "llevó un repuesto"), OBLIGATORIAMENTE es una 'reparacion'. 
        - Escribe "Venta de repuestos al mostrador" en el campo 'trabajo_realizado'.
        - En el campo 'motivo', escribe "Compra de repuesto".
        - Pon la placa del vehículo obligatoriamente como "S/C" (Sin Código).

        Catálogo oficial de servicios y precios base de este taller:
        {lista_servicios_str}

        Catálogo de repuestos en inventario (código: nombre):
        {lista_inventario_str}

        REGLA DE REPUESTOS USADOS:
        Si el mensaje menciona que se usó, cambió o vendió un repuesto (por nombre o por código), 
        BUSCA en el catálogo de inventario de arriba cuál coincide y pon su "codigo" EXACTO en 
        'repuestos_usados'. Si el repuesto mencionado no se parece a ninguno del catálogo, NO lo 
        inventes: omítelo de 'repuestos_usados' (mejor dejarlo fuera que inventar un código que no existe).

        REGLAS DE COBRO PARA REPARACIONES:
        1. Si el trabajo mencionado coincide con un servicio del catálogo, usa automáticamente su 'precio_base' en el campo 'cobro'.
        2. EXCEPCIÓN: Si en el mensaje se menciona explícitamente un precio cobrado distinto, un descuento o una rebaja, IGNORA el catálogo y respeta SIEMPRE el precio mencionado en el mensaje.
        3. Si el trabajo no está en el catálogo y no se menciona precio, pon el cobro en 0.0.

        Responde en JSON con esta estructura EXACTA:
        {{
          "tipo": "reparacion" | "gasto" | "inventario" | "devolucion",
          "reparacion": {{
              "vehiculo": "EXTRAE SOLO LA PLACA AQUÍ (sin guiones, ej. ABB3322). Si es venta directa, usa 'S/C'",
              "modelo": "Marca y modelo (ej. Chevrolet Sail)",
              "color": "Color del auto (ej. negro)",
              "anio": "Año (ej. 2023)",
              "cilindraje": "Cilindraje (ej. 1.4)",
              "cliente": "Nombre del cliente",
              "cedula": "Número de cédula, RUC o CI en texto plano (ej. 1205888769)",
              "telefono": "Número de teléfono (si se menciona)",
              "motivo": "Razón de ingreso o fallo reportado (ej. 'fallo de cilindro').",
              "trabajo_realizado": "Describe el trabajo hecho (usa el nombre del catálogo si coincide). Si recién ingresa, déjalo vacío.",
              "oficial": "DEBES elegir strictly uno de esta lista: [{lista_tecnicos_str}]. Si no coincide con ninguno, déjalo vacío.",
              "cobro": 0.0,
              "metodo_pago": "efectivo, transferencia, tarjeta, etc.",
              "banco": "Nombre exacto del banco si es transferencia (ej. Pichincha, Guayaquil, Produbanco, Pacifico)",
              "repuestos_usados": [
                  {{"codigo": "codigo_repuesto_EXACTO_del_catalogo", "cantidad": 1}}
              ]
          }} | null,
          "gasto": {{
              "monto": 0.0,
              "motivo": "",
              "vehiculo": "placa o N/A",
              "responsable": ""
          }} | null,
          "inventario": {{
              "codigo": "", "nombre": "", "marca": "", "cantidad": 0, "costo": 0.0, "precio_venta": 0.0, "proveedor": ""
          }} | null,
          "devolucion": {{
              "codigo": "", "cantidad": 0, "motivo": ""
          }} | null
        }}

        Mensaje: "{texto_msj}"
        """

        try:
            resultado, proveedor_usado = await asyncio.to_thread(generar_json_con_respaldo, prompt)
            resultado = ClasificacionMensaje.model_validate(resultado).model_dump()
            tipo = resultado.get("tipo")

        except Exception as e:
            tipo_error = str(type(e))
            if "ValidationError" in tipo_error:
                detalle_error = "Error de Formato. IA envió un dato incompleto o inválido."
            elif "JSONDecodeError" in tipo_error or "Expecting value" in str(e):
                detalle_error = "Error. La respuesta de la IA fue ilegible."
            else:
                detalle_error = "Error (IA no disponible o tiempo agotado)."

            print(f"Error procesando mensaje {id_msj}: {e}")

            intentos_usados = msj.get("intentos", 1)
            estado_final = "Error permanente (máx. reintentos alcanzado)" if intentos_usados >= 5 else "Error"

            supabase.table("cola_mensajes").update({
                "estado": estado_final,
                "ultimo_error": detalle_error
            }).eq("id", id_msj).execute()
            await asyncio.sleep(2)
            continue

        if tipo == "reparacion" and resultado.get("reparacion"):
            d = resultado["reparacion"]
            placa = str(d.get("vehiculo", "")).strip()

            ultima_orden = None
            if placa and placa != "S/C":
                res_rep = supabase.table("reparaciones").select("*").eq("vehiculo", placa).eq("taller_id", taller_id).order("id", desc=True).limit(1).execute()
                ultima_orden = res_rep.data[0] if res_rep.data else None

            if ultima_orden and ultima_orden["estado"] == 'Terminado' and (d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != ""):
                fecha_ultima = ultima_orden["fecha_hora"].split(" ")[0]
                hoy = tiempo_actual.split(" ")[0]
                if fecha_ultima == hoy:
                    supabase.table("cola_mensajes").update({"estado": "Bloqueado (Duplicado)"}).eq("id", id_msj).execute()
                    continue

            # Normalización estricta de Cédula y Banco a string plano
            cedula_extraida = str(d.get("cedula") or "").strip()
            banco_extraido = str(d.get("banco") or "").strip()

            # id real de la reparación ya guardada (se define en cualquiera de las
            # dos ramas de abajo). Lo necesitamos para poder dejar el detalle de
            # repuestos usados en reparacion_detalles, ligado a esta orden.
            reparacion_id_actual = None

            if ultima_orden and ultima_orden["estado"] == 'Pendiente':
                se_cierra = d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != ""

                motivo_bd = ultima_orden.get("motivo", "")
                motivo_ia = d.get("motivo", "")
                motivo_final = f"{motivo_bd} | {motivo_ia}".strip(" |") if motivo_bd and motivo_ia and motivo_ia not in motivo_bd else (motivo_ia or motivo_bd)

                trabajo_bd = ultima_orden.get("trabajo_realizado", "")
                trabajo_ia = d.get("trabajo_realizado", "")
                trabajo_final = f"{trabajo_bd} | {trabajo_ia}".strip(" |") if trabajo_bd and trabajo_ia and trabajo_ia not in trabajo_bd else (trabajo_ia or trabajo_bd)

                # FUNCIÓN DE HERENCIA MEJORADA (Prioriza dato nuevo válido)
                def _heredar_o_actualizar(campo, valor_nuevo):
                    val_str = str(valor_nuevo or "").strip()
                    val_antiguo = str(ultima_orden.get(campo) or "").strip()
                    return val_str if val_str and val_str.lower() != "none" else val_antiguo

                datos_actualizar = {
                    "motivo": motivo_final,
                    "trabajo_realizado": trabajo_final,
                    "cliente": _heredar_o_actualizar("cliente", d.get("cliente")),
                    "cedula": _heredar_o_actualizar("cedula", cedula_extraida),
                    "telefono": _heredar_o_actualizar("telefono", d.get("telefono")),
                    "oficial": _heredar_o_actualizar("oficial", d.get("oficial")),
                    "modelo": _heredar_o_actualizar("modelo", d.get("modelo")),
                    "color": _heredar_o_actualizar("color", d.get("color")),
                    "anio": _heredar_o_actualizar("anio", d.get("anio")),
                    "cilindraje": _heredar_o_actualizar("cilindraje", d.get("cilindraje")),
                    "cobro": d.get("cobro", 0.0) if d.get("cobro", 0) > 0 else ultima_orden.get("cobro", 0.0),
                    "metodo_pago": _heredar_o_actualizar("metodo_pago", d.get("metodo_pago")),
                    "banco": _heredar_o_actualizar("banco", banco_extraido)
                }

                if se_cierra:
                    datos_actualizar["estado"] = "Terminado"
                    datos_actualizar["fecha_salida"] = tiempo_actual
                else:
                    datos_actualizar["estado"] = "Pendiente"
                
                supabase.table("reparaciones").update(datos_actualizar).eq("id", ultima_orden["id"]).execute()
                reparacion_id_actual = ultima_orden["id"]
            else:
                estado_nuevo = 'Terminado' if (d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != "") else 'Pendiente'
                fecha_sal = tiempo_actual if estado_nuevo == 'Terminado' else None

                def _heredar(campo, valor_nuevo):
                    val_str = str(valor_nuevo or "").strip()
                    if val_str and val_str.lower() != "none":
                        return val_str
                    return str(ultima_orden.get(campo) or "").strip() if ultima_orden else ""

                try:
                    insertada = supabase.table("reparaciones").insert({
                        "taller_id": taller_id,
                        "vehiculo": placa if placa else "S/C",
                        "modelo": _heredar("modelo", d.get("modelo")),
                        "color": _heredar("color", d.get("color")),
                        "anio": _heredar("anio", d.get("anio")),
                        "cilindraje": _heredar("cilindraje", d.get("cilindraje")),
                        "cliente": _heredar("cliente", d.get("cliente")),
                        "cedula": _heredar("cedula", cedula_extraida),
                        "telefono": _heredar("telefono", d.get("telefono")),
                        "motivo": d.get("motivo", ""),
                        "trabajo_realizado": d.get("trabajo_realizado", ""),
                        "oficial": d.get("oficial", ""),
                        "cobro": d.get("cobro", 0.0),
                        "metodo_pago": d.get("metodo_pago", ""),
                        "banco": banco_extraido,
                        "fecha_hora": tiempo_actual,
                        "fecha_salida": fecha_sal,
                        "estado": estado_nuevo,
                        "mensaje_id": id_msj
                    }).execute()
                    if insertada.data:
                        reparacion_id_actual = insertada.data[0]["id"]
                except APIError as e:
                    if e.code == "23505":
                        print(f"Mensaje {id_msj} ya había creado esta reparación antes, no se duplica.")
                    else:
                        raise

            # Descuento de inventario + detalle de repuestos usados en esta orden.
            # Se hace aquí (no antes) porque recién ahora tenemos el id real de la
            # reparación para poder dejar el detalle en reparacion_detalles, con
            # el precio de venta de cada repuesto al momento de usarlo. Ese detalle
            # es lo que alimenta el PNG de la orden y el descuento de repuestos al
            # calcular comisión (antes de esto, reparacion_detalles nunca se llenaba).
            if reparacion_id_actual and (d.get("cobro", 0) > 0 or d.get("trabajo_realizado", "") != "") and d.get("repuestos_usados"):
                for repuesto in d.get("repuestos_usados", []):
                    try:
                        inv_res = supabase.table("inventario").select("id, cantidad, precio_venta").eq("codigo", repuesto.get("codigo")).eq("taller_id", taller_id).execute()
                        if inv_res.data:
                            inv_item = inv_res.data[0]
                            cantidad_usada = repuesto.get("cantidad", 0)
                            nueva_cant = max(0, inv_item["cantidad"] - cantidad_usada)
                            supabase.table("inventario").update({"cantidad": nueva_cant}).eq("id", inv_item["id"]).execute()
                            supabase.table("reparacion_detalles").insert({
                                "reparacion_id": reparacion_id_actual,
                                "inventario_id": inv_item["id"],
                                "cantidad": cantidad_usada,
                                "precio_unitario": inv_item.get("precio_venta", 0) or 0
                            }).execute()
                    except Exception as e_repuesto:
                        # No dejamos que un repuesto con problema tumbe el resto del mensaje
                        # (cierre de la orden, cédula, banco, etc. ya se guardaron arriba).
                        print(f"No se pudo registrar el repuesto {repuesto.get('codigo')} de la orden {reparacion_id_actual}: {e_repuesto}")


        elif tipo == "gasto" and resultado.get("gasto"):
            d = resultado["gasto"]
            try:
                supabase.table("gastos").insert({
                    "taller_id": taller_id,
                    "monto": d.get("monto", 0.0),
                    "motivo": d.get("motivo", ""),
                    "vehiculo": d.get("vehiculo", "N/A"),
                    "responsable": d.get("responsable", ""),
                    "fecha_hora": tiempo_actual,
                    "mensaje_id": id_msj
                }).execute()
            except APIError as e:
                if e.code == "23505":
                    print(f"Mensaje {id_msj} ya había creado este gasto antes, no se duplica.")
                else:
                    raise

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
                try:
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
                        "fecha_actualizacion": tiempo_actual,
                        "mensaje_id": id_msj
                    }).execute()
                except APIError as e:
                    if e.code == "23505":
                        print(f"Mensaje {id_msj} ya había creado este repuesto antes, no se duplica.")
                    else:
                        raise

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
            .eq("taller_id", args.get("_taller_id"))
            .ilike("vehiculo", f"%{placa}%")
            .order("fecha_hora", desc=True)
            .limit(10)
            .execute()
        ).data
        return {"resultados": data}

    if nombre_funcion == "cliente_top_visitas":
        anio = args.get("anio")
        data = cliente_seguro.rpc("cliente_top_visitas", {"p_taller_id": args.get("_taller_id"), "p_anio": anio}).execute().data
        return {"resultado": data[0] if data else None}

    if nombre_funcion == "cliente_top_gasto":
        params = {"p_taller_id": args.get("_taller_id")}
        if args.get("fecha_inicio"):
            params["p_fecha_inicio"] = args["fecha_inicio"]
        if args.get("fecha_fin"):
            params["p_fecha_fin"] = args["fecha_fin"]
        data = cliente_seguro.rpc("cliente_top_gasto", params).execute().data
        return {"resultado": data[0] if data else None}

    if nombre_funcion == "rendimiento_tecnico":
        params = {"p_taller_id": args.get("_taller_id"), "p_mes": args.get("mes"), "p_anio": args.get("anio")}
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
        print(f"Groq falló decidiendo la consulta analítica: {e_groq}")
        if not deepseek_client:
            return "El asistente de IA no está disponible en este momento. Intenta de nuevo en unos minutos."
        try:
            resp = _decidir_funcion(deepseek_client, MODELO_DEEPSEEK)
        except Exception as e_ds:
            print(f"DeepSeek también falló decidiendo la consulta analítica: {e_ds}")
            return "El asistente de IA no está disponible en este momento (ni el proveedor principal ni el de respaldo). Intenta de nuevo en unos minutos."

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
        print(f"Groq falló redactando la respuesta final: {e}")

    if deepseek_client:
        try:
            resp_final = deepseek_client.chat.completions.create(model=MODELO_DEEPSEEK, messages=mensajes_redaccion)
            return resp_final.choices[0].message.content
        except Exception as e:
            print(f"DeepSeek también falló redactando la respuesta final: {e}")

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

    # PROMPT BLINDADO CON REGLAS Y FEW-SHOT (Ejemplos)
    prompt_router = f"""
    Eres el enrutador principal de un sistema de gestión de taller automotriz. 
    Tu única tarea es clasificar la intención del texto en una de estas tres categorías: 'registro', 'consulta' o 'generar_orden'.

    REGLAS CRÍTICAS DE CLASIFICACIÓN:
    1. REGISTRO (Por defecto para ingresos): El usuario proporciona información que debe guardarse. 
       - IMPORTANTE: La sola presencia de un vehículo, cliente, placa o diagnóstico implica un REGISTRO de entrada. 
       - NUNCA clasifiques como 'generar_orden' o 'consulta' a menos que el usuario pida explícitamente buscar, imprimir o descargar.
    2. CONSULTA: El usuario pregunta por datos históricos o estadísticas (ej. ¿cuándo vino?, ¿cuánto gastó?).
    3. GENERAR_ORDEN: El usuario pide EXPLÍCITAMENTE imprimir, descargar, generar factura u orden de un vehículo que YA existe.

    EJEMPLOS DE CLASIFICACIÓN:
    - "Ingresa el Spark GSC8797 por falla de freno" -> {{"accion": "registro", "placa": ""}}
    - "Chevrolet Spark blanco Placa GSC8797, Jeferson Laje quiere escaneo" -> {{"accion": "registro", "placa": ""}}
    - "¿Cuándo vino el carro placa GSC8797?" -> {{"accion": "consulta", "placa": ""}}
    - "Genera la orden de trabajo para GSC8797" -> {{"accion": "generar_orden", "placa": "GSC8797"}}
    - "Imprime la ficha del cliente" -> {{"accion": "generar_orden", "placa": ""}}

    Responde ESTRICTAMENTE en formato JSON válido con las claves "accion" y "placa".
    Texto: "{texto_usuario}"
    """

    try:
        # 1. Obtenemos el JSON de Groq o DeepSeek
        resultado_bruto, proveedor_usado = generar_json_con_respaldo(prompt_router)
        
        # 2. Forzamos la validación estricta con Pydantic para evitar alucinaciones
        resultado_validado = RouterIntencion.model_validate(resultado_bruto)
        
        accion = resultado_validado.accion
        placa_extraida = resultado_validado.placa
    except Exception as e:
        # Fallback de seguridad (Se mantiene igual que antes)
        print(f"Router de IA falló en ambos proveedores o falló validación Pydantic. Error: {e}")
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
        
        # Buscamos la reparación más reciente de esa placa, trayendo también sus repuestos anidados.
        # Cliente admin (no cliente_seguro): el JOIN anidado a reparacion_detalles/inventario
        # requiere que esas tablas también tengan política RLS de SELECT, y no la tienen.
        orden = (
            supabase.table("reparaciones")
            .select("*, reparacion_detalles(*, inventario(codigo, nombre))")
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
            print(f"Falló la consulta analítica: {e}")
            respuesta_analitica = (
                "El asistente de IA no está disponible en este momento. "
                "Intenta de nuevo en unos segundos."
            )

        # Si la IA no está disponible (cuota agotada, saturación, o cualquier
        # falla), NO descartamos el mensaje. Lo guardamos en la cola para que
        # se reintente solo cuando la IA vuelva a responder. Si en verdad era
        # una pregunta (no una acción), el trabajador de la cola simplemente
        # la marcará como "Error (No clasificable)" sin efecto — inofensivo.
        señales_no_disponible = ("no está disponible", "temporalmente saturado")
        if any(s in respuesta_analitica for s in señales_no_disponible):
            cliente_seguro.table("cola_mensajes").insert({
                "taller_id": taller_id,
                "texto": texto_usuario,
                "fecha_hora": tiempo_actual,
                "estado": "Pendiente"
            }).execute()
            respuesta_analitica += "\n\nTu mensaje quedó guardado y se procesará automáticamente en cuanto la IA esté disponible."

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
        "mensaje_bd": "¡Recibido en la nube! Procesando registro en segundo plano.",
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
        # Cliente admin: el JOIN a reparacion_detalles requiere política RLS de
        # SELECT en esa tabla, y no la tiene. Sigue aislado por .eq("taller_id",...).
        supabase.table("reparaciones")
        # 1. Añadimos reparacion_detalles para poder restar los repuestos después
        .select("vehiculo, cliente, modelo, oficial, trabajo_realizado, cobro, metodo_pago, fecha_hora, fecha_salida, reparacion_detalles(cantidad, precio_unitario)")
        .eq("taller_id", taller_id)
        .eq("estado", "Terminado")
        .gte("fecha_salida", inicio_utc)
        .lte("fecha_salida", fin_utc)
        .order("fecha_salida", desc=True)
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

    # Descargar los porcentajes de comisión de la base de datos
    tecnicos_bd = supabase.table("tecnicos").select("nombre, porcentaje_comision").eq("taller_id", taller_id).execute().data  # cliente admin: la tabla tecnicos no tiene politica RLS de SELECT
    mapa_comisiones = {normalizar_nombre_tecnico(t["nombre"]): float(t.get("porcentaje_comision") or 0) for t in tecnicos_bd}

    total_ingresos = sum(o.get("cobro", 0) or 0 for o in ordenes_cerradas)
    total_egresos = sum(g.get("monto", 0) or 0 for g in egresos)

    rendimiento: dict[str, dict] = {}
    for o in ordenes_cerradas:
        tecnico = o.get("oficial") or "Sin asignar"
        registro = rendimiento.setdefault(tecnico, {"trabajos": 0, "total_generado": 0.0, "comision_a_pagar": 0.0})
        
        cobro = o.get("cobro", 0) or 0
        registro["trabajos"] += 1
        registro["total_generado"] += cobro
        
        # 2. Calcular el total de repuestos usados en esta orden para excluirlos de la comisión
        detalles_repuestos = o.get("reparacion_detalles", [])
        total_repuestos = sum((r.get("cantidad", 0) * r.get("precio_unitario", 0)) for r in detalles_repuestos)
        
        # 3. La mano de obra real es el cobro total menos los repuestos
        mano_de_obra = max(0.0, cobro - total_repuestos)
        
        # 4. Calcular la comisión exclusivamente sobre la mano de obra
        porcentaje = mapa_comisiones.get(normalizar_nombre_tecnico(tecnico), 0)
        registro["comision_a_pagar"] += mano_de_obra * (porcentaje / 100.0)

    ranking_tecnicos = [
        {
            "tecnico": nombre, 
            "trabajos": datos["trabajos"],
            "total_generado": round(datos["total_generado"], 2),
            "comision_a_pagar": round(datos["comision_a_pagar"], 2)
        }
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
# RANKING ANUAL Y LEADERBOARD DE TÉCNICOS 
# ==============================================================================

@app.get("/ranking-anual")
def ranking_anual(request: Request, anio: int | None = None):
    """
    Devuelve el acumulado histórico de todo el año (restando repuestos) 
    para mostrar un dashboard de posiciones en vivo ordenado del que más genera.
    """
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    
    if not anio:
        anio = datetime.now(ZONA_ECUADOR).year

    inicio_ano = f"{anio}-01-01 00:00:00"
    fin_ano = f"{anio}-12-31 23:59:59"

    # Consultamos las órdenes terminadas del año trayendo los repuestos
    # (cliente admin: reparacion_detalles no tiene política RLS de SELECT)
    ordenes = (
        supabase.table("reparaciones")
        .select("oficial, cobro, reparacion_detalles(cantidad, precio_unitario)")
        .eq("taller_id", taller_id)
        .eq("estado", "Terminado")
        .gte("fecha_salida", inicio_ano)
        .lte("fecha_salida", fin_ano)
        .execute()
    ).data

    tecnicos_bd = supabase.table("tecnicos").select("nombre, porcentaje_comision").eq("taller_id", taller_id).execute().data  # cliente admin: la tabla tecnicos no tiene politica RLS de SELECT
    mapa_comisiones = {normalizar_nombre_tecnico(t["nombre"]): float(t.get("porcentaje_comision") or 0) for t in tecnicos_bd}

    acumulado: dict[str, dict] = {}
    for o in ordenes:
        tecnico = o.get("oficial") or "Sin asignar"
        reg = acumulado.setdefault(tecnico, {"trabajos": 0, "total_generado": 0.0, "mano_de_obra_total": 0.0, "comision_acumulada": 0.0})
        
        cobro = o.get("cobro", 0) or 0
        detalles = o.get("reparacion_detalles", [])
        total_repuestos = sum((r.get("cantidad", 0) * r.get("precio_unitario", 0)) for r in detalles)
        
        # Restamos los repuestos para calcular la mano de obra real
        mano_de_obra = max(0.0, cobro - total_repuestos)

        reg["trabajos"] += 1
        reg["total_generado"] += cobro
        reg["mano_de_obra_total"] += mano_de_obra
        
        porcentaje = mapa_comisiones.get(normalizar_nombre_tecnico(tecnico), 0)
        reg["comision_acumulada"] += mano_de_obra * (porcentaje / 100.0)

    ranking = [
        {
            "posicion": i + 1,
            "tecnico": nombre,
            "trabajos_totales": datos["trabajos"],
            "facturacion_anual": round(datos["total_generado"], 2),
            "mano_de_obra_acumulada": round(datos["mano_de_obra_total"], 2),
            "comision_acumulada": round(datos["comision_acumulada"], 2)
        }
        for i, (nombre, datos) in enumerate(sorted(
            acumulado.items(), key=lambda x: x[1]["mano_de_obra_total"], reverse=True
        ))
    ]

    return {
        "anio": anio,
        "leaderboard": ranking
    }

# ==============================================================================
# REPORTE DE LIQUIDACIÓN / QUINCENA POR RANGO DE FECHAS PERSONALIZADO
# ==============================================================================

@app.get("/reporte-liquidacion")
def reporte_liquidacion(request: Request, fecha_inicio: str, fecha_fin: str):
    """
    Calcula el consolidado de trabajos, mano de obra y comisiones por técnico 
    en un rango de fechas totalmente personalizado (ej. cortes quincenales por feriados).
    Formato esperado de fechas: YYYY-MM-DD
    """
    cliente_seguro, taller_id = obtener_cliente_seguro(request)

    # Usar los límites del día en Ecuador para asegurar precisión exacta de horario
    inicio_utc, _ = limites_dia_ecuador(fecha_inicio)
    _, fin_utc = limites_dia_ecuador(fecha_fin)

    # Consultar las órdenes terminadas dentro del rango de corte seleccionado
    # (cliente admin: reparacion_detalles no tiene política RLS de SELECT)
    ordenes = (
        supabase.table("reparaciones")
        .select("vehiculo, cliente, modelo, oficial, trabajo_realizado, cobro, fecha_salida, reparacion_detalles(cantidad, precio_unitario)")
        .eq("taller_id", taller_id)
        .eq("estado", "Terminado")
        .gte("fecha_salida", inicio_utc)
        .lte("fecha_salida", fin_utc)
        .execute()
    ).data

    # Descargar los porcentajes actuales de comisión de los técnicos
    tecnicos_bd = supabase.table("tecnicos").select("nombre, porcentaje_comision").eq("taller_id", taller_id).execute().data  # cliente admin: la tabla tecnicos no tiene politica RLS de SELECT
    mapa_comisiones = {normalizar_nombre_tecnico(t["nombre"]): float(t.get("porcentaje_comision") or 0) for t in tecnicos_bd}

    liquidacion: dict[str, dict] = {}
    for o in ordenes:
        tecnico = o.get("oficial") or "Sin asignar"
        reg = liquidacion.setdefault(tecnico, {"trabajos": 0, "total_generado": 0.0, "mano_de_obra_total": 0.0, "comision_total": 0.0})
        
        cobro = o.get("cobro", 0) or 0
        detalles = o.get("reparacion_detalles", [])
        total_repuestos = sum((r.get("cantidad", 0) * r.get("precio_unitario", 0)) for r in detalles)
        
        # Restamos los repuestos para calcular la mano de obra real del periodo
        mano_de_obra = max(0.0, cobro - total_repuestos)

        reg["trabajos"] += 1
        reg["total_generado"] += cobro
        reg["mano_de_obra_total"] += mano_de_obra
        
        porcentaje = mapa_comisiones.get(normalizar_nombre_tecnico(tecnico), 0)
        reg["comision_total"] += mano_de_obra * (porcentaje / 100.0)

    resultado = [
        {
            "tecnico": nombre,
            "trabajos_realizados": datos["trabajos"],
            "facturacion_total": round(datos["total_generado"], 2),
            "mano_de_obra_acumulada": round(datos["mano_de_obra_total"], 2),
            "comision_a_pagar": round(datos["comision_total"], 2)
        }
        for nombre, datos in sorted(liquidacion.items(), key=lambda x: x[1]["comision_total"], reverse=True)
    ]

    return {
        "periodo": f"Desde {fecha_inicio} hasta {fecha_fin}",
        "liquidacion_tecnicos": resultado
    }
# ==============================================================================
# EXPORTACIONES E INVENTARIOS
# ==============================================================================

@app.get("/exportar-excel")
def exportar_excel(request: Request):
    try:
        cliente_seguro, taller_id = obtener_cliente_seguro(request)

        reps = cliente_seguro.table("reparaciones").select("*").eq("taller_id", taller_id).execute().data
        gasts = cliente_seguro.table("gastos").select("*").eq("taller_id", taller_id).execute().data
        inv = cliente_seguro.table("inventario").select("*").eq("taller_id", taller_id).execute().data

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
        # Cliente admin: el JOIN a reparacion_detalles/inventario no tiene política RLS de SELECT
        supabase.table("reparaciones")
        .select("id, vehiculo, cliente, cedula, telefono, modelo, color, anio, cilindraje, motivo, trabajo_realizado, cobro, metodo_pago, banco, fecha_hora, estado, fecha_salida, oficial, reparacion_detalles(cantidad, precio_unitario, inventario(codigo, nombre))")
        .eq("taller_id", taller_id)
        .eq("estado", "Pendiente")
        .execute()
    ).data

    terminados_hoy = (
        supabase.table("reparaciones")
        .select("id, vehiculo, cliente, cedula, telefono, modelo, color, anio, cilindraje, motivo, trabajo_realizado, cobro, metodo_pago, banco, fecha_hora, estado, fecha_salida, oficial, reparacion_detalles(cantidad, precio_unitario, inventario(codigo, nombre))")
        .eq("taller_id", taller_id)
        .eq("estado", "Terminado")
        .gte("fecha_salida", hoy_inicio)
        .lte("fecha_salida", hoy_fin)
        .execute()
    ).data

    return {"vehiculos": pendientes + terminados_hoy}
# --- IMPORTAR INVENTARIO (carga masiva desde Excel) ---------------------
# Regla de negocio: si el código YA existe, SUMA la cantidad nueva al stock
# y SOBREESCRIBE costo/precio_venta con los del archivo (igual criterio que
# el registro individual por IA). Si no existe, lo crea.

def _normalizar_encabezado(col) -> str:
    """Lleva cualquier encabezado a una forma comparable:
    'Código*' -> 'codigo', 'Costo ($)' -> 'costo', 'Descripción / Repuesto' -> 'descripcion_repuesto'."""
    import unicodedata
    texto = unicodedata.normalize("NFKD", str(col)).encode("ascii", "ignore").decode().lower()
    texto = re.sub(r"\(.*?\)", " ", texto)          # quita '($)', '(opcional)', etc.
    texto = re.sub(r"[^a-z0-9]+", "_", texto)        # espacios, '/', '*', '-' -> '_'
    return texto.strip("_")

# Nombres alternativos que la gente suele usar en sus Excel. Si el archivo
# trae uno de estos (y no trae ya el nombre oficial), se toma como equivalente.
# Así no hace falta acertar el encabezado exacto a prueba y error.
ALIAS_COLUMNAS_INVENTARIO = {
    "codigo":       ["cod", "codigo_repuesto", "codigo_producto", "sku", "referencia", "ref", "numero_parte", "no_parte",
                     "code", "part_number", "part_no"],
    "nombre":       ["descripcion", "descripcion_repuesto", "nombre_descripcion", "repuesto", "nombre_repuesto",
                     "producto", "articulo", "detalle", "item",
                     "name", "description", "product"],
    "cantidad":     ["cant", "stock", "unidades", "existencia", "existencias", "cantidad_ingreso",
                     "qty", "quantity"],
    "costo":        ["costo_unitario", "precio_costo", "precio_compra", "costo_compra", "valor_compra", "cost", "unit_cost"],
    "precio_venta": ["precio", "pvp", "venta", "precio_de_venta", "precio_publico", "valor_venta", "price", "sale_price"],
    "aplicacion":   ["vehiculo_compatible", "vehiculos_compatibles", "compatibilidad", "compatible_con",
                     "vehiculo", "aplica_a", "modelo_compatible", "application", "fits"],
    "marca":        ["marca_repuesto", "fabricante", "brand"],
    "proveedor":    ["distribuidor", "proveedor_repuesto", "supplier", "vendor"],
    "categoria":    ["tipo", "familia", "grupo", "linea", "categoria_repuesto", "tipo_repuesto", "category"],
}

def _mapear_columnas_inventario(columnas: list[str]) -> list[str]:
    """Normaliza encabezados y traduce alias al nombre oficial de la columna."""
    normalizadas = [_normalizar_encabezado(c) for c in columnas]
    presentes = set(normalizadas)
    alias_a_oficial = {alias: oficial for oficial, alias_lista in ALIAS_COLUMNAS_INVENTARIO.items()
                       for alias in alias_lista}
    resultado = []
    for col in normalizadas:
        oficial = alias_a_oficial.get(col)
        if oficial and oficial not in presentes:
            presentes.add(oficial)       # solo el primer alias cuenta
            resultado.append(oficial)
        else:
            resultado.append(col)
    return resultado

def _celda_vacia(valor) -> bool:
    """True si la celda viene vacía (NaN de pandas, None o texto en blanco)."""
    return valor is None or (not isinstance(valor, str) and pd.isna(valor)) or str(valor).strip() == ""

def _a_numero(valor, entero: bool = False, campo: str = "valor"):
    """Convierte una celda a número. Vacío -> 0. Acepta '$12,50' o '1.234,5'.
    Antes: una celda vacía llegaba como NaN -> int(NaN) reventaba o se enviaba
    NaN a Supabase (JSON inválido) y la fila se descartaba en silencio."""
    if _celda_vacia(valor):
        return 0
    if isinstance(valor, str):
        limpio = valor.strip().replace("$", "").replace(" ", "")
        if "," in limpio and "." in limpio:
            limpio = limpio.replace(".", "").replace(",", ".")  # formato 1.234,50
        else:
            limpio = limpio.replace(",", ".")                   # formato 12,50
        try:
            valor = float(limpio)
        except ValueError:
            raise ValueError(f"'{campo}' no es un número válido: '{valor}'")
    try:
        return int(round(float(valor))) if entero else round(float(valor), 2)
    except (TypeError, ValueError):
        raise ValueError(f"'{campo}' no es un número válido: '{valor}'")

def _a_texto(valor, por_defecto: str = "") -> str:
    """Texto limpio; evita guardar la palabra 'nan' en la base."""
    if _celda_vacia(valor):
        return por_defecto
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)  # códigos numéricos: 12345.0 -> '12345'
    return str(valor).strip()

# Hojas que nunca son de datos (se ignoran sin reportar error)
HOJAS_IGNORADAS = {"instrucciones", "instruccion", "leeme", "readme", "ayuda", "notas", "indice"}
# Nombres de hoja "genéricos": no se usan como categoría (se conserva la actual
# del repuesto, o 'General' si es nuevo)
HOJAS_SIN_CATEGORIA = {"inventario", "hoja1", "hoja_1", "sheet1", "sheet_1", "datos", "general", "repuestos"}
TAMANO_LOTE = 1000  # repuestos por llamada a la función SQL

@app.post("/importar-inventario")
def importar_inventario(request: Request, archivo: UploadFile = File(...)):
    """Importa TODAS las hojas del Excel en una sola operación.

    - Cada hoja válida es una categoría (Sensores, Filtros, Frenos...) que se
      asigna a los repuestos NUEVOS. Los repuestos que ya existen conservan su
      categoría, salvo que la fila traiga una columna 'Categoría' con valor
      (así una hoja tipo "Pedido de la semana" no desordena el inventario).
    - Hojas sin las columnas obligatorias se omiten y se reportan.
    - Códigos repetidos (en la misma hoja o entre hojas) se agrupan: se suman
      las cantidades, gana el último costo/precio con valor y la categoría es
      la de la primera hoja donde aparece (o la de una columna explícita).
    - La escritura va por lotes a la función SQL importar_inventario_lote
      (una transacción por lote), no fila por fila.
    """
    # 'def' (no 'async def'): las llamadas a Supabase son bloqueantes; así FastAPI
    # usa el threadpool y no congela el servidor mientras se importa.
    cliente_seguro, taller_id = obtener_cliente_seguro(request)

    try:
        contenido = archivo.file.read()
        # sheet_name=None -> diccionario {nombre_hoja: DataFrame} con TODAS las hojas.
        # dtype=object: no convertir códigos como '0012' en 12.
        hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None, dtype=object)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el Excel: {e}")

    columnas_requeridas = {"codigo", "nombre", "cantidad"}
    resumen_hojas = []   # lo que se muestra al usuario, hoja por hoja
    errores = []         # errores de fila, con el nombre de la hoja
    items = {}           # codigo -> datos agrupados listos para la BD
    hoja_de_codigo = {}  # codigo -> nombre de hoja (para el resumen)
    total_filas = 0

    for nombre_hoja, df in hojas.items():
        clave_hoja = _normalizar_encabezado(nombre_hoja)
        if clave_hoja in HOJAS_IGNORADAS:
            continue

        info = {"hoja": str(nombre_hoja), "filas": 0, "nuevos": 0, "actualizados": 0, "errores": 0, "omitida": None}
        resumen_hojas.append(info)

        df.columns = _mapear_columnas_inventario(list(df.columns))
        df = df.dropna(how="all")
        if df.empty:
            info["omitida"] = "hoja vacía"
            continue
        faltantes = columnas_requeridas - set(df.columns)
        if faltantes:
            info["omitida"] = f"faltan columnas: {', '.join(sorted(faltantes))}"
            continue

        categoria_hoja = None if clave_hoja in HOJAS_SIN_CATEGORIA else str(nombre_hoja).strip()
        info["categoria"] = categoria_hoja or "(sin cambio)"

        for idx, fila in df.iterrows():
            num_fila = idx + 2  # +1 por encabezado, +1 porque Excel cuenta desde 1
            info["filas"] += 1
            total_filas += 1
            try:
                codigo = _a_texto(fila.get("codigo"))
                if not codigo:
                    raise ValueError("sin código, omitida")

                cantidad = _a_numero(fila.get("cantidad"), entero=True, campo="cantidad")
                # None = celda vacía -> la BD conserva el valor actual del repuesto
                costo = None if _celda_vacia(fila.get("costo")) else _a_numero(fila.get("costo"), campo="costo")
                precio = None if _celda_vacia(fila.get("precio_venta")) else _a_numero(fila.get("precio_venta"), campo="precio_venta")
                # Categoría explícita (columna) vs. implícita (nombre de la hoja).
                # Solo la explícita puede cambiar la categoría de un repuesto existente.
                categoria_columna = _a_texto(fila.get("categoria"))
                categoria = categoria_columna or categoria_hoja
                forzar = bool(categoria_columna)

                if codigo in items:
                    # Código repetido en el archivo: sumar cantidad, último valor gana
                    previo = items[codigo]
                    previo["cantidad"] += cantidad
                    for campo, valor in (("costo", costo), ("precio_venta", precio)):
                        if valor is not None:
                            previo[campo] = valor
                    # Categoría: una columna explícita siempre gana; si no, se
                    # mantiene la de la primera hoja donde apareció el código.
                    if forzar:
                        previo["categoria"], previo["forzar_categoria"] = categoria, True
                        hoja_de_codigo[codigo] = info
                    elif not previo["categoria"]:
                        previo["categoria"] = categoria
                    for campo in ("nombre", "marca", "proveedor", "aplicacion"):
                        previo[campo] = previo[campo] or _a_texto(fila.get(campo)) or None
                else:
                    items[codigo] = {
                        "codigo": codigo,
                        "nombre": _a_texto(fila.get("nombre")) or None,
                        "marca": _a_texto(fila.get("marca")) or None,
                        "proveedor": _a_texto(fila.get("proveedor")) or None,
                        "aplicacion": _a_texto(fila.get("aplicacion")) or None,
                        "categoria": categoria,
                        "forzar_categoria": forzar,  # lo interpreta la función SQL
                        "cantidad": cantidad,
                        "costo": costo,
                        "precio_venta": precio,
                    }
                    hoja_de_codigo[codigo] = info  # el resumen lo cuenta en su primera hoja
            except Exception as e_fila:
                info["errores"] += 1
                errores.append(f"{nombre_hoja}, fila {num_fila}: {e_fila}")

    hojas_validas = [h for h in resumen_hojas if not h["omitida"]]
    if not hojas_validas:
        detalle = "; ".join(f"{h['hoja']}: {h['omitida']}" for h in resumen_hojas) or "el archivo no tiene hojas con datos"
        raise HTTPException(
            status_code=400,
            detail=(f"Ninguna hoja se pudo importar ({detalle}). Cada hoja necesita las columnas "
                    f"Código, Descripción y Cantidad. Descarga la plantilla oficial con el botón "
                    f"'Descargar Plantilla de Inventario'.")
        )

    # ---- Escritura por lotes (una transacción por lote) ----
    # Cliente admin: la función solo la puede ejecutar service_role, y el
    # taller_id viene del JWT, nunca del navegador.
    tiempo_actual = ahora_utc_str()
    lista = list(items.values())
    for inicio in range(0, len(lista), TAMANO_LOTE):
        lote = lista[inicio:inicio + TAMANO_LOTE]
        try:
            resultado = supabase.rpc("importar_inventario_lote", {
                "p_taller_id": taller_id,
                "p_items": lote,
                "p_fecha": tiempo_actual,
            }).execute().data or []
        except Exception as e_lote:
            print(f"[importar-inventario] fallo de lote taller={taller_id}: {e_lote}")
            ya_guardados = sum(h["nuevos"] + h["actualizados"] for h in resumen_hojas)
            raise HTTPException(
                status_code=500,
                detail=(f"Error guardando el inventario en la base de datos ({e_lote}). "
                        f"Se guardaron {ya_guardados} repuestos antes del error; "
                        f"puedes volver a importar el archivo sin riesgo de duplicar códigos, "
                        f"pero las cantidades de los ya guardados se sumarían de nuevo.")
                if ya_guardados else
                f"Error guardando el inventario en la base de datos: {e_lote}. No se guardó ningún repuesto."
            )
        for r in resultado:
            info = hoja_de_codigo.get(r.get("codigo"))
            if info is not None:
                info["nuevos" if r.get("accion") == "nuevo" else "actualizados"] += 1

    nuevos = sum(h["nuevos"] for h in resumen_hojas)
    actualizados = sum(h["actualizados"] for h in resumen_hojas)
    print(f"[importar-inventario] taller={taller_id} hojas={len(hojas_validas)} filas={total_filas} "
          f"nuevos={nuevos} actualizados={actualizados} errores={len(errores)}")

    return {"status": "ok", "nuevos": nuevos, "actualizados": actualizados,
            "total_filas": total_filas, "errores": errores, "hojas": resumen_hojas}


# --- PLANTILLA OFICIAL DE INVENTARIO (Excel listo para llenar) -----------
# Mismos encabezados que entiende /importar-inventario. Cada hoja de datos es
# una categoría; la hoja "Instrucciones" va primero y el importador la ignora.
COLUMNAS_PLANTILLA_INVENTARIO = [
    # (encabezado visible, obligatoria, ancho, formato numérico, ayuda, ejemplo)
    ("Código",               True,  16, "@",           "Código único del repuesto. Si ya existe en el sistema, se suma la cantidad.", "FA-0112"),
    ("Descripción",          True,  38, "@",           "Nombre o descripción del repuesto.",                                            "Filtro de aceite"),
    ("Marca",                False, 16, "@",           "Marca del repuesto (opcional).",                                               "Bosch"),
    ("Vehículo compatible",  False, 30, "@",           "Vehículos donde se usa. Ayuda a la búsqueda por descripción (opcional).",       "Chevrolet Sail 1.4 2013-2020"),
    ("Cantidad",             True,  12, "0",           "Unidades que ingresan. Número entero, 0 o mayor.",                             12),
    ("Costo",                False, 14, '"$"#,##0.00', "Costo unitario de compra en dólares. Vacío = conserva el costo actual.",        3.5),
    ("Precio venta",         False, 14, '"$"#,##0.00', "Precio unitario de venta en dólares. Vacío = conserva el precio actual.",       6.0),
    ("Proveedor",            False, 20, "@",           "Proveedor o distribuidor (opcional). Si se deja vacío se guarda 'General'.",   "Importadora XYZ"),
]

@app.get("/plantilla-inventario")
def plantilla_inventario(request: Request):
    obtener_cliente_seguro(request)  # solo usuarios autenticados

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.utils import get_column_letter
    from fastapi.responses import Response

    FILAS_PREPARADAS = 1000  # filas con formato y validación listas para llenar
    morado, lila, tinta = "7030EF", "EDE7FB", "14102B"
    borde = Border(bottom=Side(style="thin", color="C9BEF2"))

    wb = Workbook()

    def armar_hoja_categoria(ws):
        """Encabezados, formatos, validaciones y ayudas de una hoja de categoría."""
        for i, (titulo, obligatoria, ancho, formato, ayuda, _) in enumerate(COLUMNAS_PLANTILLA_INVENTARIO, start=1):
            letra = get_column_letter(i)
            celda = ws.cell(row=1, column=i, value=titulo)
            # Obligatorias: morado con texto blanco. Opcionales: lila con texto oscuro.
            celda.fill = PatternFill("solid", fgColor=morado if obligatoria else lila)
            celda.font = Font(bold=True, color="FFFFFF" if obligatoria else tinta, size=11)
            celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.column_dimensions[letra].width = ancho

            # Formato de las filas de datos (texto para códigos: conserva ceros a la izquierda)
            for fila in range(2, FILAS_PREPARADAS + 2):
                c = ws.cell(row=fila, column=i)
                c.number_format = formato
                c.border = borde

            # Mensaje de ayuda al seleccionar la columna + validación de números
            rango = f"{letra}2:{letra}{FILAS_PREPARADAS + 1}"
            if titulo == "Cantidad":
                dv = DataValidation(type="whole", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
                dv.error = "La cantidad debe ser un número entero (0 o mayor)."
            elif formato.startswith('"$"'):
                dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
                dv.error = "Ingresa un valor en dólares (0 o mayor), sin letras."
            else:
                dv = DataValidation(allow_blank=True)
            dv.errorTitle = "Valor no válido"
            dv.promptTitle = titulo + (" (obligatorio)" if obligatoria else " (opcional)")
            dv.prompt = ayuda
            dv.showInputMessage = True
            dv.showErrorMessage = dv.type is not None
            ws.add_data_validation(dv)
            dv.add(rango)

        ws.row_dimensions[1].height = 30
        ws.freeze_panes = "A2"  # encabezado siempre visible
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNAS_PLANTILLA_INVENTARIO))}1"

    # ------------- Hojas de categoría (cada hoja = una categoría) -------------
    # Ejemplos; el taller puede renombrarlas o duplicarlas (Sensores, Sockets...).
    CATEGORIAS_EJEMPLO = ["Filtros", "Frenos", "Sensores"]
    ws = wb.active
    ws.title = CATEGORIAS_EJEMPLO[0]
    armar_hoja_categoria(ws)
    hojas_datos = [ws]
    for nombre in CATEGORIAS_EJEMPLO[1:]:
        nueva = wb.create_sheet(nombre)
        armar_hoja_categoria(nueva)
        hojas_datos.append(nueva)

    # ---------------- Hoja de Instrucciones ----------------
    ins = wb.create_sheet("Instrucciones")
    ins.sheet_view.showGridLines = False
    ins.column_dimensions["A"].width = 24
    ins.column_dimensions["B"].width = 14
    ins.column_dimensions["C"].width = 70
    ins.column_dimensions["D"].width = 30

    ins["A1"] = "Plantilla de carga de inventario"
    ins["A1"].font = Font(bold=True, size=16, color=morado)
    ins["A2"] = ("Cada hoja es una categoría (Filtros, Frenos, Sensores...). Llénalas con una fila por repuesto "
                 "y sube el archivo completo con el botón \"Importar Inventario (Excel)\": se cargan todas las hojas a la vez.")
    ins["A2"].font = Font(color="574F7A")

    encabezados = ["Columna", "¿Obligatoria?", "Qué poner", "Ejemplo"]
    for j, texto in enumerate(encabezados, start=1):
        c = ins.cell(row=4, column=j, value=texto)
        c.fill = PatternFill("solid", fgColor=morado)
        c.font = Font(bold=True, color="FFFFFF")
        c.alignment = Alignment(vertical="center")
    for k, (titulo, obligatoria, _, _, ayuda, ejemplo) in enumerate(COLUMNAS_PLANTILLA_INVENTARIO, start=5):
        # El ejemplo se muestra como texto (alineado a la izquierda, con $ si aplica)
        ejemplo_txt = f"${ejemplo:.2f}" if isinstance(ejemplo, float) else str(ejemplo)
        valores = [titulo, "Sí" if obligatoria else "No", ayuda, ejemplo_txt]
        for j, v in enumerate(valores, start=1):
            c = ins.cell(row=k, column=j, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.border = borde
            if j == 2 and obligatoria:
                c.font = Font(bold=True, color=morado)

    fila = 5 + len(COLUMNAS_PLANTILLA_INVENTARIO) + 1
    ins.cell(row=fila, column=1, value="Reglas importantes").font = Font(bold=True, size=12, color=morado)
    reglas = [
        "El NOMBRE DE LA HOJA es la categoría de los repuestos NUEVOS. Para una categoría nueva: clic derecho en una pestaña > Mover o copiar > Crear una copia, y renómbrala (ej. Sockets, Actuadores).",
        "Los repuestos que YA EXISTEN conservan su categoría aunque estén en otra hoja (ej. una hoja 'Pedido de la semana'). Para cambiarla, agrega una columna 'Categoría' con el nuevo valor.",
        "Puedes borrar las hojas que no uses. Las hojas vacías y esta hoja de Instrucciones se ignoran al importar.",
        "No cambies los nombres de los encabezados de las columnas.",
        "Si el código ya existe, la cantidad se SUMA al stock actual; costo y precio se actualizan solo si vienen llenos.",
        "Si un mismo código aparece en varias filas u hojas, las cantidades se suman antes de guardar.",
        "Las filas sin código se omiten. Al terminar, el sistema muestra un resumen por hoja y qué filas tuvieron problemas.",
        "Los precios van sin el símbolo $ (la plantilla ya les da formato de dólares).",
    ]
    for r in reglas:
        fila += 1
        c = ins.cell(row=fila, column=1, value="•  " + r)
        ins.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=4)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ins.row_dimensions[fila].height = 30

    # Instrucciones como primera pestaña (es lo primero que se ve al abrir)
    wb.move_sheet(ins, offset=-len(hojas_datos))
    wb.active = 0

    # Impresión: horizontal y ajustada al ancho de una página
    for hoja in hojas_datos + [ins]:
        hoja.page_setup.orientation = "landscape"
        hoja.sheet_properties.pageSetUpPr.fitToPage = True
        hoja.page_setup.fitToWidth = 1
        hoja.page_setup.fitToHeight = 0

    buffer = io.BytesIO()
    wb.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Plantilla_Inventario.xlsx"'},
    )
# ==============================================================================
# CATÁLOGO DE SERVICIOS
# ==============================================================================
class NuevoServicio(BaseModel):
    nombre_servicio: str
    precio_base: float

@app.get("/servicios")
def listar_servicios(request: Request):
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    data = cliente_seguro.table("servicios").select("*").eq("taller_id", taller_id).order("nombre_servicio").execute().data
    return {"servicios": data}

@app.post("/servicios")
def agregar_servicio(datos: NuevoServicio, request: Request):
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    cliente_seguro.table("servicios").insert({
        "taller_id": taller_id,
        "nombre_servicio": datos.nombre_servicio.strip(),
        "precio_base": datos.precio_base
    }).execute()
    return {"status": "ok", "mensaje": "Servicio agregado exitosamente"}

@app.delete("/servicios/{servicio_id}")
def eliminar_servicio(servicio_id: str, request: Request):
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    cliente_seguro.table("servicios").delete().eq("id", servicio_id).eq("taller_id", taller_id).execute()
    return {"status": "ok", "mensaje": "Servicio eliminado"}
# ==============================================================================
# DASHBOARD ANALÍTICO (CHART.JS)
# ==============================================================================
@app.get("/dashboard-stats")
def dashboard_stats(request: Request):
    """
    Calcula los Top 5 para el Dashboard Analítico.
    """
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    
    try:
        # 1. Traer todas las órdenes terminadas con sus detalles
        # (cliente admin: reparacion_detalles/inventario no tienen política RLS de SELECT)
        res = (
            supabase.table("reparaciones")
            .select("cliente, cobro, trabajo_realizado, reparacion_detalles(cantidad, inventario(nombre))")
            .eq("taller_id", taller_id)
            .eq("estado", "Terminado")
            .execute()
        )
        ordenes = res.data

        dicc_clientes = {}
        dicc_servicios = {}
        dicc_repuestos = {}

        for o in ordenes:
            # --- Top Clientes ---
            cli = str(o.get("cliente") or "Cliente Final").strip()
            dicc_clientes[cli] = dicc_clientes.get(cli, 0.0) + float(o.get("cobro") or 0.0)

            # --- Top Servicios ---
            trabajo = str(o.get("trabajo_realizado") or "").strip()
            if trabajo:
                para_servicios = [t.strip() for t in trabajo.split("|") if t.strip()]
                for s in para_servicios:
                    dicc_servicios[s] = dicc_servicios.get(s, 0) + 1

            # --- Top Repuestos ---
            detalles = o.get("reparacion_detalles") or []
            for d in detalles:
                cant = int(d.get("cantidad") or 0)
                rep_info = d.get("inventario") or {}
                # Buscamos el nombre correcto del repuesto
                nombre_rep = str(rep_info.get("nombre") or "Repuesto Genérico").strip()
                dicc_repuestos[nombre_rep] = dicc_repuestos.get(nombre_rep, 0) + cant

        # 2. Ordenar de mayor a menor y sacar solo el Top 5
        top_clientes = [{"nombre": k, "total": round(v, 2)} for k, v in sorted(dicc_clientes.items(), key=lambda x: x[1], reverse=True)[:5]]
        top_servicios = [{"nombre": k, "cantidad": v} for k, v in sorted(dicc_servicios.items(), key=lambda x: x[1], reverse=True)[:5]]
        top_repuestos = [{"nombre": k, "cantidad": v} for k, v in sorted(dicc_repuestos.items(), key=lambda x: x[1], reverse=True)[:5]]

        return {
            "top_clientes": top_clientes,
            "top_servicios": top_servicios,
            "top_repuestos": top_repuestos
        }
    except Exception as e:
        print(f"Error en dashboard_stats: {e}")
        # En caso de error, devolvemos listas vacías para que no se rompa la página
        return {"top_clientes": [], "top_servicios": [], "top_repuestos": []}
    
@app.get("/exportar-inventario")
def exportar_inventario(request: Request):
    try:
        cliente_seguro, taller_id = obtener_cliente_seguro(request)

        inv = cliente_seguro.table("inventario").select("*").eq("taller_id", taller_id).execute().data
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
