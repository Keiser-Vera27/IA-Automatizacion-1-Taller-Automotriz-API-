# ==============================================================================
# Proyecto: API del Taller Automotriz con IA, Supabase (Nube), y Proveedores
# Autor: Keiser Vera
# ==============================================================================

import os
import io
import re
import json
import asyncio
import base64
import hashlib
import hmac
import time
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



class TrabajoLinea(BaseModel):
    """Un trabajo/servicio dentro de una orden (se van agregando mientras está abierta)."""
    descripcion: str = ""
    precio: float = 0.0

    @field_validator("precio", mode="before")
    @classmethod
    def _precio_numero(cls, v):
        try:
            return max(0.0, float(str(v).replace("$", "").replace(",", ".").strip() or 0))
        except (TypeError, ValueError):
            return 0.0


class TrabajoTaller(BaseModel):
    vehiculo: str = Field(description="OBLIGATORIO: Extrae ÚNICAMENTE la placa del vehículo (ej: PXY9876, GPU340). NUNCA incluyas la marca o color aquí.")
    modelo: str = Field(default="", description="Marca y modelo del vehículo, ej: 'Toyota Corolla'. Vacío si no se menciona.")
    color: str = Field(default="", description="Color, ej: 'blanco'. Vacío si no se menciona.")
    anio: str = Field(default="")
    cilindraje: str = Field(default="")
    kilometraje: str = Field(default="", description="Kilometraje del vehículo, solo números")
    # Garantía indicada EXPLÍCITAMENTE en el mensaje (tiene prioridad sobre catálogo y taller)
    garantia_dias: str = Field(default="")
    garantia_km: str = Field(default="")
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
    # Etapa del mensaje: "ingreso" (llega el vehículo), "avance" (se agrega un
    # trabajo/hallazgo a la orden abierta) o "cierre" (trabajo terminado/cobrado).
    etapa: str = ""
    # Trabajos NUEVOS que este mensaje agrega a la orden (con su precio)
    trabajos_nuevos: list[TrabajoLinea] = Field(default=[])
    # Decisión final de cierre: la fija el backend (nunca la IA) después de la
    # doble verificación y la confirmación del usuario. None = no decidido.
    cierra: bool | None = None

    @field_validator("etapa", mode="before")
    @classmethod
    def _etapa_valida(cls, v):
        v = str(v or "").strip().lower()
        return v if v in ("ingreso", "avance", "cierre") else ""

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
    texto: str = ""
    # Segundo paso del modal "faltan datos": borrador firmado + datos completados
    borrador: str | None = None
    datos_confirmados: dict[str, str] | None = None
    # Respuesta a la ventana "¿Cerrar la orden?": "cerrar" o "abierta"
    decision_cierre: Literal["cerrar", "abierta"] | None = None


class RouterIntencion(BaseModel):
    accion: Literal["registro", "consulta", "generar_orden"] = Field(
        description="Clasificación estricta de la intención del usuario."
    )
    placa: str = Field(
        default="", 
        description="Placa del vehículo SOLO si la acción es generar_orden."
    )


def construir_prompt_extraccion(taller_id, texto: str, nombres_tecnicos: list[str]) -> str:
    """Prompt de extracción de registros (reparación/gasto/inventario/devolución).
    Se usa en dos lugares: la pre-validación síncrona de /procesar-mensaje y el
    trabajador de la cola (cuando el mensaje llegó sin datos pre-extraídos)."""
    lista_tecnicos_str = ", ".join(nombres_tecnicos) if nombres_tecnicos else "(no hay técnicos registrados)"

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
    Si el mensaje describe la venta de un repuesto a un cliente que no ingresó su vehículo (ej. "se le vendió...", "compró...", "llevó un repuesto"), OBLIGATORIAMENTE es una 'reparacion' con etapa "cierre".
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

    ETAPA DE LA ORDEN (campo "etapa", OBLIGATORIO en reparaciones). Es la regla MÁS IMPORTANTE:
    - "ingreso": el vehículo LLEGA al taller. Lo que el cliente PIDE o el problema que reporta
      (ej. "quiere mantenimiento a inyectores", "llega por ruido en frenos") va SOLO en 'motivo'.
      En un ingreso: trabajos_nuevos = [], trabajo_realizado = "", cobro = 0. Aunque lo pedido
      coincida con un servicio del catálogo, SIGUE SIENDO el motivo, NO un trabajo hecho.
    - "avance": el vehículo YA está en el taller y se reporta un trabajo adicional, un hallazgo
      o un repuesto a cambiar (ej. "se encontró la bobina 2 dañada, se cambia", "también se le
      hace ABC"). Cada trabajo va como un elemento de trabajos_nuevos. cobro = 0.
    - "cierre": SOLO si el mensaje dice EXPLÍCITAMENTE que se terminó, está listo, se entregó,
      se cobró o el cliente pagó / retiró el vehículo. Si hay duda, NO es cierre.
    - Un mismo mensaje puede traer ingreso y cierre juntos (ej. "llegó Juan con el Spark, se le
      cambió el aceite y se cobraron 35") -> etapa "cierre", con motivo y trabajos_nuevos.

    PRECIOS DE LOS TRABAJOS (trabajos_nuevos):
    1. Si el mensaje menciona el precio de ese trabajo, usa ese precio.
    2. Si no, y el trabajo coincide con un servicio del catálogo, usa su 'precio_base'.
    3. Si no, precio 0.0.

    COBRO: SOLO en etapa "cierre" y SOLO si el mensaje menciona el monto total cobrado o pagado
    (respeta descuentos o rebajas). Si no se menciona, cobro = 0.0 (el sistema sumará los trabajos).

    Responde en JSON con esta estructura EXACTA:
    {{
      "tipo": "reparacion" | "gasto" | "inventario" | "devolucion",
      "reparacion": {{
          "vehiculo": "EXTRAE SOLO LA PLACA AQUÍ (sin guiones, ej. ABB3322). Si es venta directa, usa 'S/C'",
          "modelo": "Marca y modelo (ej. Chevrolet Sail)",
          "color": "Color del auto (ej. negro)",
          "anio": "Año (ej. 2023)",
          "cilindraje": "Cilindraje (ej. 1.4)",
          "kilometraje": "Kilometraje del odómetro SOLO en números, sin puntos ni 'km' (ej. 'ingresa con 85.400 km' -> 85400). Vacío si no se menciona.",
          "garantia_dias": "SOLO si el mensaje indica la garantía entregada: en DÍAS (ej. '3 meses de garantía' -> 90, '1 año' -> 365, 'sin garantía' -> 0). Vacío si no se menciona.",
          "garantia_km": "SOLO si el mensaje indica garantía en kilómetros (ej. 'o 5.000 km' -> 5000). Vacío si no se menciona.",
          "cliente": "Nombre del cliente",
          "cedula": "Número de cédula, RUC o CI en texto plano (ej. 1205888769)",
          "telefono": "Número de teléfono (si se menciona)",
          "motivo": "Razón de ingreso o fallo reportado (ej. 'fallo de cilindro').",
          "etapa": "ingreso" | "avance" | "cierre",
          "trabajos_nuevos": [
              {{"descripcion": "Trabajo hecho o por hacer en ESTE mensaje (nombre del catálogo si coincide). Vacío [] en un ingreso.", "precio": 0.0}}
          ],
          "trabajo_realizado": "Resumen de los trabajos hechos SOLO en avance o cierre. En un ingreso, SIEMPRE vacío.",
          "oficial": "DEBES elegir estrictamente uno de esta lista: [{lista_tecnicos_str}]. Si el mensaje no menciona un técnico o no coincide con ninguno, déjalo vacío (\"\"). NUNCA inventes un nombre.",
          "cobro": "0.0 salvo en un cierre que mencione el monto cobrado",
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

    Mensaje: "{texto}"
    """
    return prompt


# ==============================================================================
# TÉCNICOS REGISTRADOS Y VALIDACIÓN DE ÓRDENES DE TRABAJO
# ==============================================================================

def obtener_tecnicos_registrados(taller_id) -> dict[str, str]:
    """{nombre_normalizado: nombre_oficial} de los técnicos del taller.
    Cliente admin: la tabla tecnicos no tiene política RLS de SELECT (filtrado por taller_id)."""
    filas = supabase.table("tecnicos").select("nombre").eq("taller_id", taller_id).execute().data or []
    return {normalizar_nombre_tecnico(t["nombre"]): t["nombre"].strip() for t in filas if t.get("nombre")}

def canonizar_tecnico(nombre, mapa_tecnicos: dict[str, str]) -> str:
    """Devuelve el nombre oficial si coincide con un técnico registrado; si no, ''."""
    return mapa_tecnicos.get(normalizar_nombre_tecnico(nombre), "") if nombre else ""

def normalizar_telefono_ec(telefono) -> tuple[str, bool]:
    """Celular ecuatoriano: '+593 99 123 4567' / '0991234567' -> ('0991234567', True).
    También acepta convencional de 9 dígitos (02xxxxxxx). Devuelve (valor, es_valido)."""
    digitos = re.sub(r"\D", "", str(telefono or ""))
    if digitos.startswith("593"):
        digitos = "0" + digitos[3:]
    if re.fullmatch(r"09\d{8}", digitos) or re.fullmatch(r"0[2-7]\d{7}", digitos):
        return digitos, True
    return str(telefono or "").strip(), False

def validar_identificacion_ec(valor) -> tuple[str, str]:
    """Cédula (10 dígitos, con dígito verificador) o RUC (13 dígitos).
    Pasaportes de extranjeros (letras y números) se aceptan tal cual.
    Devuelve (valor_limpio, mensaje_error) — mensaje vacío si es válido."""
    texto = re.sub(r"[\s.\-]", "", str(valor or ""))
    if not texto:
        return "", "falta"
    if not texto.isdigit():
        return texto, "" if re.fullmatch(r"[A-Za-z0-9]{5,15}", texto) else "formato no válido"
    if len(texto) == 13:
        return texto, ""
    if len(texto) != 10:
        return texto, "debe tener 10 dígitos (cédula) o 13 (RUC)"
    provincia, tercero = int(texto[:2]), int(texto[2])
    if not (1 <= provincia <= 24 or provincia == 30) or tercero >= 6:
        return texto, "cédula no válida"
    suma = 0
    for i, coef in enumerate([2, 1, 2, 1, 2, 1, 2, 1, 2]):
        prod = int(texto[i]) * coef
        suma += prod - 9 if prod > 9 else prod
    verificador = (10 - suma % 10) % 10
    return (texto, "") if verificador == int(texto[9]) else (texto, "cédula no válida (revisa los dígitos)")

def normalizar_kilometraje(valor) -> int | None:
    """'85.400 km' / '85,400' / '85400' -> 85400. None si no es un kilometraje válido."""
    digitos = re.sub(r"[^\d]", "", str(valor or ""))
    if not digitos:
        return None
    km = int(digitos)
    return km if 0 < km < 2_000_000 else None

# --- Garantías (etapa 1) ---
GARANTIA_DIAS_DEFECTO = 30      # respaldo si el taller aún no configuró la suya
GARANTIA_KM_DEFECTO = 1000

def obtener_garantia_taller(taller_id) -> tuple[int, int]:
    """Garantía por defecto que definió el dueño del taller (días, km)."""
    try:
        fila = (supabase.table("talleres").select("garantia_dias_defecto, garantia_km_defecto")
                .eq("id", taller_id).limit(1).execute()).data
        if fila:
            dias = fila[0].get("garantia_dias_defecto")
            km = fila[0].get("garantia_km_defecto")
            return (GARANTIA_DIAS_DEFECTO if dias is None else int(dias),
                    GARANTIA_KM_DEFECTO if km is None else int(km))
    except Exception:
        pass   # migración aún no ejecutada
    return GARANTIA_DIAS_DEFECTO, GARANTIA_KM_DEFECTO

def _entero_o_none(valor) -> int | None:
    digitos = re.sub(r"[^\d]", "", str(valor if valor is not None else ""))
    return int(digitos) if digitos else None

def _sin_tildes(texto) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()

def calcular_garantia(taller_id, trabajo_realizado: str, kilometraje,
                      dias_mensaje=None, km_mensaje=None) -> dict:
    """Garantía que se entrega al TERMINAR una orden. Prioridad:
      1. Lo que diga el mensaje de cierre ("garantía de 3 meses o 5000 km").
      2. La garantía del servicio en el catálogo (si hay varios, la más amplia).
      3. La garantía por defecto que definió el dueño del taller.
    0 días = sin garantía."""
    dias_taller, km_taller = obtener_garantia_taller(taller_id)
    dias_msj, km_msj = _entero_o_none(dias_mensaje), _entero_o_none(km_mensaje)

    trabajo = _sin_tildes(trabajo_realizado)
    coincidencias = []
    try:
        servicios = (supabase.table("servicios").select("*").eq("taller_id", taller_id).execute().data) or []
        coincidencias = [sv for sv in servicios
                         if _sin_tildes(sv.get("nombre_servicio")) and _sin_tildes(sv.get("nombre_servicio")) in trabajo]
    except Exception as e:
        print(f"No se pudo leer el catálogo para la garantía: {e}")

    if coincidencias:
        dias = max((sv.get("garantia_dias") if sv.get("garantia_dias") is not None else dias_taller) for sv in coincidencias)
        km = max((sv.get("garantia_km") if sv.get("garantia_km") is not None else km_taller) for sv in coincidencias)
        origen = ", ".join(sv.get("nombre_servicio", "") for sv in coincidencias)
    else:
        dias, km, origen = dias_taller, km_taller, "Garantía general del taller"

    if dias_msj is not None or km_msj is not None:
        # Garantía indicada en el cierre para ESTE trabajo
        dias = dias_msj if dias_msj is not None else dias
        km = km_msj if km_msj is not None else (0 if dias_msj == 0 else km)
        origen = "Indicada al cerrar el trabajo"

    if not dias:
        return {"garantia_dias": 0, "garantia_km": 0, "garantia_vence": None,
                "garantia_km_limite": None, "garantia_servicio": f"Sin garantía ({origen})"}

    from datetime import timedelta
    vence = (datetime.now(ZONA_ECUADOR).date() + timedelta(days=int(dias))).isoformat()
    km_actual = normalizar_kilometraje(kilometraje)
    return {
        "garantia_dias": int(dias),
        "garantia_km": int(km or 0),
        "garantia_vence": vence,
        "garantia_km_limite": (km_actual + int(km)) if (km_actual and km) else None,
        "garantia_servicio": origen,
    }

_COLS_GARANTIA_SELECT = "id, vehiculo, trabajo_realizado, oficial, fecha_salida, garantia_vence, garantia_km_limite"

def _evaluar_garantia(o: dict, km_actual: int | None) -> dict | None:
    """Estado de la garantía de una orden terminada. None si no tiene, o si
    venció hace más de 60 días (ya no es relevante avisar)."""
    if not o or not o.get("garantia_vence"):
        return None
    hoy = datetime.now(ZONA_ECUADOR).date()
    vence = datetime.strptime(str(o["garantia_vence"])[:10], "%Y-%m-%d").date()
    if (hoy - vence).days > 60:
        return None
    km_limite = o.get("garantia_km_limite")
    vencida_fecha = hoy > vence
    vencida_km = bool(km_actual and km_limite and km_actual > km_limite)
    return {
        "orden_id": o.get("id"),
        "trabajo": o.get("trabajo_realizado") or "",
        "tecnico": o.get("oficial") or "",
        "entregado": str(o.get("fecha_salida") or "")[:10],
        "vence": vence.isoformat(),
        "km_limite": km_limite,
        "vigente": not (vencida_fecha or vencida_km),
        "motivo_vencida": "por fecha" if vencida_fecha else ("por kilometraje" if vencida_km else ""),
    }

def buscar_garantia(taller_id, placa: str, km_actual: int | None) -> dict | None:
    """Garantía de la última orden terminada de esta placa en ESTE taller."""
    try:
        filas = (supabase.table("reparaciones").select(_COLS_GARANTIA_SELECT)
                 .eq("taller_id", taller_id).eq("vehiculo", placa).eq("estado", "Terminado")
                 .order("fecha_salida", desc=True).limit(1).execute()).data
    except Exception:
        return None   # migración de garantías aún no ejecutada
    return _evaluar_garantia(filas[0] if filas else None, km_actual)

def buscar_garantias_lote(taller_id, placas: list[str]) -> dict[str, dict]:
    """Última orden terminada CON garantía de cada placa, en UNA sola consulta
    (la lista de pendientes no hace una consulta por vehículo)."""
    placas = sorted({p for p in placas if p and p != "S/C"})
    if not placas:
        return {}
    from datetime import timedelta
    desde = (datetime.now(ZONA_ECUADOR).date() - timedelta(days=60)).isoformat()
    try:
        filas = (supabase.table("reparaciones").select(_COLS_GARANTIA_SELECT)
                 .eq("taller_id", taller_id).eq("estado", "Terminado")
                 .in_("vehiculo", placas).gte("garantia_vence", desde)
                 .order("fecha_salida", desc=True).execute()).data or []
    except Exception:
        return {}
    ultima: dict[str, dict] = {}
    for f in filas:                       # ordenadas de la más reciente a la más antigua
        ultima.setdefault(f.get("vehiculo"), f)
    return ultima

# Columnas nuevas de garantía/kilometraje: si la migración aún no se ejecutó,
# se guarda la orden sin ellas en lugar de fallar.
COLUMNAS_GARANTIA = ("kilometraje", "garantia_dias", "garantia_km", "garantia_vence",
                     "garantia_km_limite", "garantia_servicio", "trabajos")

def guardar_reparacion(operacion: str, datos: dict, id_orden=None):
    def ejecutar(payload):
        tabla = supabase.table("reparaciones")
        if operacion == "insert":
            return tabla.insert(payload).execute()
        return tabla.update(payload).eq("id", id_orden).execute()
    try:
        return ejecutar(datos)
    except APIError as e:
        if any(c in str(e) for c in COLUMNAS_GARANTIA):
            print("Aviso: faltan columnas de garantía/kilometraje (ejecuta la migración 2026-09-23e). Se guarda sin ellas.")
            return ejecutar({k: v for k, v in datos.items() if k not in COLUMNAS_GARANTIA})
        raise

# ------------------------------------------------------------------------------
# Campos obligatorios de una orden de trabajo (en este orden se muestran en el modal)
# ------------------------------------------------------------------------------
# INGRESO del vehículo: solo lo mínimo para abrir la orden sin frenar la recepción.
CAMPOS_OBLIGATORIOS_INGRESO = [
    ("vehiculo", "Placa del vehículo"),
    ("modelo",   "Marca y modelo"),
    ("cliente",  "Nombre y apellido del cliente"),
    ("motivo",   "Motivo de ingreso al taller"),
]
# Se pueden dejar pendientes al ingresar, pero son OBLIGATORIOS para cerrar la
# orden (trabajo terminado): sin ellos la orden no pasa a "Terminado".
CAMPOS_OBLIGATORIOS_AL_CIERRE = [
    ("kilometraje", "Kilometraje actual"),
    ("cedula",   "Cédula o RUC del cliente"),
    ("telefono", "Número de celular"),
    ("oficial",  "Técnico asignado"),
]
CAMPOS_OBLIGATORIOS_ORDEN = CAMPOS_OBLIGATORIOS_INGRESO + CAMPOS_OBLIGATORIOS_AL_CIERRE
CAMPOS_SOLO_INGRESO = {c for c, _ in CAMPOS_OBLIGATORIOS_INGRESO}
# Campos que el usuario puede dejar vacíos en el modal de ingreso (dato opcional mal escrito)
CAMPOS_VACIABLES_ORDEN = {c for c, _ in CAMPOS_OBLIGATORIOS_AL_CIERRE}
# Datos que el usuario puede completar desde el modal
CAMPOS_EDITABLES_ORDEN = {c for c, _ in CAMPOS_OBLIGATORIOS_ORDEN} | {"trabajo_realizado", "cobro", "metodo_pago", "banco"}

# ------------------------------------------------------------------------------
# CIERRE DE ÓRDENES: doble candado + lista de trabajos
# ------------------------------------------------------------------------------
# Candado 2 (determinístico): además de que la IA diga "cierre", el TEXTO debe
# contener una señal clara de trabajo terminado o cobrado. Si falta, la orden
# NO se cierra (queda abierta y se agregan los trabajos como avance).
_SENALES_CIERRE = re.compile(
    r"\b(termin\w*|finaliz\w*|conclu\w*|listo|lista|entreg\w*|cobr\w*|pag[oóa]\w*|cancel[oóa]\w*|"
    r"retir\w*|se\s+(fue|llev\w*)|despach\w*|factur\w*|vend\w*|abon\w*)\b",
    re.IGNORECASE,
)

def hay_senal_cierre(texto: str) -> bool:
    return bool(_SENALES_CIERRE.search(_sin_tildes(texto or "")))

def trabajos_de_orden(orden: dict | None) -> list[dict]:
    """Trabajos ya registrados en una orden (lista jsonb). Órdenes antiguas sin
    lista: su texto de trabajo_realizado cuenta como un solo trabajo."""
    if not orden:
        return []
    lista = orden.get("trabajos")
    if isinstance(lista, list) and lista:
        return [t for t in lista if isinstance(t, dict) and str(t.get("descripcion") or "").strip()]
    texto = str(orden.get("trabajo_realizado") or "").strip()
    return [{"descripcion": texto, "precio": 0.0}] if texto else []

def normalizar_trabajos_nuevos(d: dict, taller_id) -> list[dict]:
    """Trabajos que agrega este mensaje, con precio del catálogo si no se dijo.
    Si la IA solo llenó 'trabajo_realizado' (avance/cierre), se usa como un trabajo."""
    nuevos = [t for t in (d.get("trabajos_nuevos") or []) if str((t or {}).get("descripcion") or "").strip()]
    if not nuevos and d.get("etapa") in ("avance", "cierre") and str(d.get("trabajo_realizado") or "").strip():
        nuevos = [{"descripcion": str(d["trabajo_realizado"]).strip(), "precio": 0.0}]
    if not nuevos:
        return []
    try:
        catalogo = (supabase.table("servicios").select("nombre_servicio, precio_base")
                    .eq("taller_id", taller_id).execute().data) or []
    except Exception:
        catalogo = []
    resultado = []
    for t in nuevos:
        desc = re.sub(r"\s+", " ", str(t.get("descripcion"))).strip()[:200]
        precio = float(t.get("precio") or 0)
        if precio <= 0:
            desc_n = _sin_tildes(desc)
            coincidencias = [c for c in catalogo if _sin_tildes(c.get("nombre_servicio")) and _sin_tildes(c.get("nombre_servicio")) in desc_n]
            if coincidencias:
                # el nombre más largo es la coincidencia más específica
                precio = float(max(coincidencias, key=lambda c: len(c["nombre_servicio"])).get("precio_base") or 0)
        resultado.append({"descripcion": desc, "precio": round(precio, 2)})
    return resultado

def unir_trabajos(existentes: list[dict], nuevos: list[dict]) -> list[dict]:
    """Agrega los nuevos sin repetir (misma descripción = mismo trabajo)."""
    vistos = {_sin_tildes(t["descripcion"]).strip() for t in existentes}
    lista = list(existentes)
    for t in nuevos:
        clave = _sin_tildes(t["descripcion"]).strip()
        if clave and clave not in vistos:
            vistos.add(clave)
            lista.append(t)
    return lista

def texto_trabajos(lista: list[dict]) -> str:
    return " | ".join(t["descripcion"] for t in lista)

def total_trabajos(lista: list[dict]) -> float:
    return round(sum(float(t.get("precio") or 0) for t in lista), 2)

def validar_orden_trabajo(d: dict, taller_id, mapa_tecnicos: dict[str, str], texto: str = "") -> tuple[dict, list[dict], dict]:
    """Revisa una orden (ingreso o cierre) ANTES de guardarla.
    - INGRESO: solo exige placa, marca/modelo, nombre y apellido del cliente y
      motivo. Los demás datos pueden quedar pendientes; si se escribieron pero
      con formato inválido se avisa como OPCIONAL (se corrige o se deja vacío).
    - CIERRE (trabajo terminado / cobro): exige TODOS los datos, incluidos los
      que no se escribieron al ingresar. Sin ellos la orden no se cierra.
    - Considera lo que el vehículo ya tiene en su última orden (el trabajador
      hereda esos datos), así al cerrar no se vuelve a pedir lo ya registrado.
    - CIERRE solo con doble candado: la IA dice etapa "cierre" Y el texto tiene
      una señal clara (terminó, listo, cobró, pagó...). O bien, el usuario ya
      decidió en la ventana de confirmación (d["cierra"] True/False).
    - Devuelve (orden_normalizada, faltantes, contexto)."""
    d = dict(d)
    placa = str(d.get("vehiculo") or "").strip()
    texto_trabajo = f"{d.get('trabajo_realizado', '')} {d.get('motivo', '')}".lower()
    es_mostrador = placa in ("", "S/C") and ("mostrador" in texto_trabajo or "compra de repuesto" in texto_trabajo)


    ultima = None
    if placa and placa != "S/C":
        res = (supabase.table("reparaciones").select("*").eq("vehiculo", placa)
               .eq("taller_id", taller_id).order("id", desc=True).limit(1).execute())
        ultima = res.data[0] if res.data else None
    pendiente = bool(ultima and ultima.get("estado") == "Pendiente")

    # ¿Este mensaje cierra la orden? (candado 1: la IA dice "cierre";
    # candado 2: el texto tiene una señal clara de terminado/cobrado)
    propone_cierre = d.get("etapa") == "cierre" and hay_senal_cierre(texto)
    cierre_descartado = d.get("etapa") == "cierre" and not propone_cierre
    se_cierra = d["cierra"] if isinstance(d.get("cierra"), bool) else propone_cierre
    if cierre_descartado:
        # La IA dijo "cierre" pero el texto no lo confirma. Sin orden abierta el
        # vehículo recién LLEGA (ingreso: lo pedido es el motivo, no un trabajo);
        # con orden abierta es un avance.
        d["etapa"] = "avance" if pendiente else "ingreso"
    # En un ingreso/avance el cobro nunca se toma (evita el precio del catálogo como cobro)
    if not se_cierra:
        d["cobro"] = 0.0
    if d.get("etapa") == "ingreso" and not se_cierra:
        d["trabajos_nuevos"], d["trabajo_realizado"] = [], ""
    else:
        d["trabajos_nuevos"] = normalizar_trabajos_nuevos(d, taller_id)

    # Trabajos que tendrá la orden (los ya registrados + los de este mensaje) y su total
    trabajos_orden = unir_trabajos(trabajos_de_orden(ultima) if pendiente else [], d["trabajos_nuevos"])
    total_orden = float(d.get("cobro") or 0) or total_trabajos(trabajos_orden)

    def efectivo(campo):
        """Valor que quedará guardado: el nuevo o, si no viene, el heredado."""
        nuevo = str(d.get(campo) or "").strip()
        if nuevo and nuevo.lower() != "none":
            return nuevo
        # Motivo, técnico y kilometraje solo se heredan de una orden abierta
        # (en cada visita nueva el vehículo llega con otro kilometraje)
        if campo in ("motivo", "oficial", "kilometraje") and not pendiente:
            return ""
        return str((ultima or {}).get(campo) or "").strip()

    faltantes = []
    def falta(campo, etiqueta, problema="falta", valor="", opcional=False):
        faltantes.append({"campo": campo, "etiqueta": etiqueta, "problema": problema,
                          "valor": valor, "opcional": opcional})

    if not es_mostrador:
        # Se guarda el técnico tal como vino para poder mostrar el error
        oficial_escrito = str(d.get("oficial") or "").strip()
        d["oficial"] = canonizar_tecnico(oficial_escrito, mapa_tecnicos) or ""
        for campo, etiqueta in CAMPOS_OBLIGATORIOS_ORDEN:
            obligatorio = se_cierra or campo in CAMPOS_SOLO_INGRESO
            if obligatorio:
                valor = efectivo(campo)
            else:
                # Ingreso: el dato es opcional. Solo se revisa si se escribió
                # en ESTE mensaje (no se vuelve a reclamar un dato heredado).
                valor = oficial_escrito if campo == "oficial" else str(d.get(campo) or "").strip()
                if not valor or valor.lower() == "none":
                    continue
            opcional = not obligatorio

            if campo == "vehiculo":
                if not placa or placa == "S/C":
                    falta(campo, etiqueta)
            elif campo == "cliente":
                if not valor:
                    falta(campo, etiqueta)
                elif len(valor.split()) < 2:
                    falta(campo, etiqueta, "escribe nombre y apellido", valor)
            elif campo == "oficial":
                if not canonizar_tecnico(valor, mapa_tecnicos):
                    escrito = oficial_escrito or valor
                    falta(campo, etiqueta, f"'{escrito}' no es un técnico registrado" if escrito else "falta",
                          escrito, opcional)
            elif campo == "telefono":
                tel, ok = normalizar_telefono_ec(valor)
                if not valor:
                    falta(campo, etiqueta)
                elif not ok:
                    falta(campo, etiqueta, "número no válido (ej. 0991234567)", valor, opcional)
                elif d.get("telefono"):
                    d["telefono"] = tel
            elif campo == "kilometraje":
                km = normalizar_kilometraje(valor)
                if not valor:
                    falta(campo, etiqueta)
                elif km is None:
                    falta(campo, etiqueta, "número no válido (ej. 85400)", valor, opcional)
                elif d.get("kilometraje"):
                    d["kilometraje"] = str(km)
            elif campo == "cedula":
                ced, error = validar_identificacion_ec(valor)
                if error:
                    falta(campo, etiqueta, error, "" if error == "falta" else valor, opcional)
                elif d.get("cedula"):
                    d["cedula"] = ced
            elif not valor:
                falta(campo, etiqueta)

    # Al cerrar, es obligatorio que la orden tenga al menos un trabajo realizado
    if se_cierra and not es_mostrador and not trabajos_orden:
        falta("trabajo_realizado", "Servicio realizado o solución brindada")

    # Al cerrar, debe haber un valor cobrado (el dicho o la suma de los trabajos).
    # Si no se cobró nada, se usa el botón "Cerrar orden" (sin cobro).
    if se_cierra and total_orden <= 0:
        falta("cobro", "Valor total cobrado ($)")

    # Al cobrar, el método de pago es obligatorio para poder cuadrar caja
    if se_cierra and total_orden > 0:
        categoria, banco = normalizar_metodo_pago(efectivo("metodo_pago"), efectivo("banco"))
        if categoria in ("Sin especificar", "Otro"):
            falta("metodo_pago", "Método de pago", "falta" if categoria == "Sin especificar" else "no reconocido",
                  efectivo("metodo_pago"))
        elif categoria == "Transferencia" and not banco:
            falta("banco", "Banco de la transferencia")

    # Aviso de garantía: solo al INGRESAR un vehículo (no al cerrar su orden)
    garantia = None
    if not pendiente and not es_mostrador and placa and placa != "S/C":
        garantia = buscar_garantia(taller_id, placa, normalizar_kilometraje(efectivo("kilometraje")))

    contexto = {
        "placa": placa, "es_cierre": se_cierra, "es_mostrador": es_mostrador,
        "orden_abierta": pendiente, "garantia": garantia,
        "cliente": efectivo("cliente"), "modelo": efectivo("modelo"),
        "trabajo": texto_trabajos(trabajos_orden), "cobro": d.get("cobro") or 0,
        "trabajos": trabajos_orden, "total": round(total_orden, 2),
        "cobro_indicado": float(d.get("cobro") or 0) > 0,
        "cierre_descartado": cierre_descartado,
        "tecnico": canonizar_tecnico(efectivo("oficial"), mapa_tecnicos) or "",
        "metodo_pago": efectivo("metodo_pago"), "banco": efectivo("banco"),
        # Datos que quedan pendientes y se exigirán al cerrar la orden
        "pendientes_cierre": [] if (se_cierra or es_mostrador) else
            [etq for c, etq in CAMPOS_OBLIGATORIOS_AL_CIERRE
             if not efectivo(c) or (c == "oficial" and not canonizar_tecnico(efectivo(c), mapa_tecnicos))],
    }
    return d, faltantes, contexto

# --- Borrador firmado: el backend devuelve lo que extrajo la IA junto con una
# firma HMAC. Al completar los datos en el modal, el navegador lo reenvía y el
# backend verifica la firma: así no se vuelve a llamar a la IA y nadie puede
# alterar los datos extraídos ni usarlos en otro taller.
_CLAVE_BORRADOR = hashlib.sha256(f"borrador-orden:{os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')}".encode()).digest()
VIGENCIA_BORRADOR_SEG = 30 * 60

def firmar_borrador(taller_id, texto: str, resultado: dict) -> str:
    cuerpo = json.dumps({"t": str(taller_id), "ts": int(time.time()), "texto": texto, "resultado": resultado},
                        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    firma = hmac.new(_CLAVE_BORRADOR, cuerpo, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(cuerpo).decode() + "." + firma

def verificar_borrador(token: str, taller_id) -> dict:
    try:
        cuerpo_b64, firma = token.rsplit(".", 1)
        cuerpo = base64.urlsafe_b64decode(cuerpo_b64.encode())
        esperada = hmac.new(_CLAVE_BORRADOR, cuerpo, hashlib.sha256).hexdigest()
        datos = json.loads(cuerpo)
    except Exception:
        raise HTTPException(status_code=400, detail="El borrador de la orden no es válido. Vuelve a escribir el registro.")
    if not hmac.compare_digest(firma, esperada) or datos.get("t") != str(taller_id):
        raise HTTPException(status_code=400, detail="El borrador de la orden no es válido. Vuelve a escribir el registro.")
    if time.time() - datos.get("ts", 0) > VIGENCIA_BORRADOR_SEG:
        raise HTTPException(status_code=400, detail="El borrador expiró (más de 30 minutos). Vuelve a escribir el registro.")
    return datos

def encolar_registro(cliente, taller_id, texto: str, tiempo: str, resultado: dict | None):
    """Guarda el mensaje en la cola. Si ya viene validado, se guarda también lo
    extraído (el trabajador no vuelve a llamar a la IA). Si la columna
    datos_extraidos aún no existe (migración sin ejecutar), se guarda sin ella."""
    fila = {"taller_id": taller_id, "texto": texto, "fecha_hora": tiempo, "estado": "Pendiente"}
    if resultado is not None:
        try:
            cliente.table("cola_mensajes").insert({**fila, "datos_extraidos": resultado}).execute()
            return
        except APIError as e:
            if "datos_extraidos" not in str(e):
                raise
            print("Aviso: falta la columna cola_mensajes.datos_extraidos; se encola sin datos pre-extraídos.")
    cliente.table("cola_mensajes").insert(fila).execute()

def obtener_datos_pre_extraidos(msj: dict) -> dict | None:
    """Datos ya validados que vienen con el mensaje de la cola (o None)."""
    if "datos_extraidos" in msj:
        return msj.get("datos_extraidos") or None
    try:  # la función RPC de la cola puede no devolver esta columna
        fila = supabase.table("cola_mensajes").select("datos_extraidos").eq("id", msj["id"]).limit(1).execute().data
        return (fila[0].get("datos_extraidos") if fila else None) or None
    except Exception:
        return None

# Estado de la cola para un cierre rechazado por datos faltantes (no se reintenta:
# el usuario debe reenviar el mensaje con los datos completos)
ESTADO_COLA_INCOMPLETO = "Incompleto (faltan datos para cerrar)"

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

        # Técnicos registrados del taller (normalizado -> nombre oficial)
        mapa_tecnicos = obtener_tecnicos_registrados(taller_id)

        # Si el mensaje ya viene validado desde /procesar-mensaje, se usan esos
        # datos tal cual (no se vuelve a llamar a la IA). Si no, se extrae aquí.
        resultado = obtener_datos_pre_extraidos(msj)
        # Si ya pasó por el modal de validación, no se vuelve a revisar aquí
        venia_validado = resultado is not None
        if resultado is None:
            prompt = construir_prompt_extraccion(taller_id, texto_msj, list(mapa_tecnicos.values()))

        try:
            if resultado is None:
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

        # Estado final del mensaje en la cola (puede cambiar si queda algo pendiente)
        estado_cola_final, nota_cola = "Procesado", None

        if tipo == "reparacion" and resultado.get("reparacion"):
            d = resultado["reparacion"]
            placa = str(d.get("vehiculo", "")).strip()
            es_venta_mostrador = not placa or placa == "S/C"

            # ¿Se cierra la orden? SOLO si el usuario lo confirmó en la ventana
            # de cierre (d["cierra"] True). Un mensaje que no pasó por la
            # validación previa (la IA no respondía al enviarlo) NUNCA cierra:
            # se aplica como avance y queda marcado para confirmar el cierre.
            cierra = d.get("cierra") is True
            if not venia_validado:
                _, _, ctx_msj = validar_orden_trabajo(d, taller_id, mapa_tecnicos, texto_msj)
                if ctx_msj.get("es_cierre"):
                    estado_cola_final = ESTADO_COLA_INCOMPLETO
                    nota_cola = "El mensaje pedía cerrar la orden, pero llegó sin confirmar: se registró como avance. Vuelve a enviar el cierre."
                d = {**d, "trabajos_nuevos": normalizar_trabajos_nuevos(d, taller_id)}
                if d.get("etapa") == "ingreso":
                    d["trabajos_nuevos"], d["trabajo_realizado"] = [], ""
                cierra = False
            if not cierra:
                d["cobro"] = 0.0     # un ingreso/avance nunca registra cobro

            # Solo se guarda un técnico REGISTRADO, con su nombre oficial
            # (evita "Ninguno registrado", "jordy" vs "Jordy", nombres inventados)
            d["oficial"] = canonizar_tecnico(d.get("oficial"), mapa_tecnicos)
            nuevos = [{"descripcion": t["descripcion"], "precio": float(t.get("precio") or 0),
                       "mensaje_id": str(id_msj), "fecha": tiempo_actual}
                      for t in (d.get("trabajos_nuevos") or []) if str(t.get("descripcion") or "").strip()]

            ultima_orden = None
            if placa and placa != "S/C":
                res_rep = supabase.table("reparaciones").select("*").eq("vehiculo", placa).eq("taller_id", taller_id).order("id", desc=True).limit(1).execute()
                ultima_orden = res_rep.data[0] if res_rep.data else None

            # Cierre duplicado: el mismo vehículo ya se cerró hoy y no hay orden abierta
            if cierra and ultima_orden and ultima_orden["estado"] == 'Terminado':
                if str(ultima_orden.get("fecha_salida") or "")[:10] == tiempo_actual[:10]:
                    supabase.table("cola_mensajes").update({"estado": "Bloqueado (Duplicado)"}).eq("id", id_msj).execute()
                    continue

            # Normalización estricta de Cédula y Banco a string plano
            cedula_extraida = str(d.get("cedula") or "").strip()
            banco_extraido = str(d.get("banco") or "").strip()

            # id real de la reparación ya guardada (para ligar los repuestos usados)
            reparacion_id_actual = None

            if ultima_orden and ultima_orden["estado"] == 'Pendiente':
                # ---- Orden ABIERTA: se agregan trabajos (y se cierra solo si se confirmó) ----
                # Idempotencia: si este mensaje ya se aplicó (reintento), no se duplican trabajos
                existentes = trabajos_de_orden(ultima_orden)
                ya_aplicado = any(str(t.get("mensaje_id")) == str(id_msj) for t in existentes)
                lista_trabajos = existentes if ya_aplicado else unir_trabajos(existentes, nuevos)
                trabajo_final = texto_trabajos(lista_trabajos)

                motivo_bd = ultima_orden.get("motivo", "") or ""
                motivo_ia = d.get("motivo", "") or ""
                motivo_final = f"{motivo_bd} | {motivo_ia}".strip(" |") if motivo_bd and motivo_ia and motivo_ia not in motivo_bd else (motivo_ia or motivo_bd)

                # FUNCIÓN DE HERENCIA (prioriza el dato nuevo válido)
                def _heredar_o_actualizar(campo, valor_nuevo):
                    val_str = str(valor_nuevo or "").strip()
                    val_antiguo = str(ultima_orden.get(campo) or "").strip()
                    return val_str if val_str and val_str.lower() != "none" else val_antiguo

                datos_actualizar = {
                    "motivo": motivo_final,
                    "trabajos": lista_trabajos,
                    "trabajo_realizado": trabajo_final,
                    "cliente": _heredar_o_actualizar("cliente", d.get("cliente")),
                    "cedula": _heredar_o_actualizar("cedula", cedula_extraida),
                    "telefono": _heredar_o_actualizar("telefono", d.get("telefono")),
                    "oficial": _heredar_o_actualizar("oficial", d.get("oficial")),
                    "modelo": _heredar_o_actualizar("modelo", d.get("modelo")),
                    "color": _heredar_o_actualizar("color", d.get("color")),
                    "anio": _heredar_o_actualizar("anio", d.get("anio")),
                    "cilindraje": _heredar_o_actualizar("cilindraje", d.get("cilindraje")),
                    "kilometraje": normalizar_kilometraje(d.get("kilometraje")) or ultima_orden.get("kilometraje"),
                    "metodo_pago": _heredar_o_actualizar("metodo_pago", d.get("metodo_pago")),
                    "banco": _heredar_o_actualizar("banco", banco_extraido),
                }

                if cierra:
                    datos_actualizar["estado"] = "Terminado"
                    datos_actualizar["fecha_salida"] = tiempo_actual
                    # Cobro: el dicho en el cierre o, si no, la suma de los trabajos
                    datos_actualizar["cobro"] = float(d.get("cobro") or 0) or total_trabajos(lista_trabajos)
                    # Garantía que se entrega con este trabajo
                    datos_actualizar.update(calcular_garantia(taller_id, trabajo_final, datos_actualizar["kilometraje"],
                                                              d.get("garantia_dias"), d.get("garantia_km")))
                else:
                    datos_actualizar["estado"] = "Pendiente"

                guardar_reparacion("update", datos_actualizar, ultima_orden["id"])
                reparacion_id_actual = ultima_orden["id"]
            else:
                # ---- No hay orden abierta: se crea una nueva ----
                estado_nuevo = 'Terminado' if cierra else 'Pendiente'
                fecha_sal = tiempo_actual if cierra else None
                trabajo_final = texto_trabajos(nuevos) or (str(d.get("trabajo_realizado") or "") if cierra else "")
                cobro_final = (float(d.get("cobro") or 0) or total_trabajos(nuevos)) if cierra else 0.0

                def _heredar(campo, valor_nuevo):
                    val_str = str(valor_nuevo or "").strip()
                    if val_str and val_str.lower() != "none":
                        return val_str
                    return str(ultima_orden.get(campo) or "").strip() if ultima_orden else ""

                garantia_nueva = (calcular_garantia(taller_id, trabajo_final, d.get("kilometraje"),
                                                    d.get("garantia_dias"), d.get("garantia_km"))
                                  if cierra and not es_venta_mostrador else {})
                try:
                    insertada = guardar_reparacion("insert", {
                        "taller_id": taller_id,
                        "vehiculo": placa if placa else "S/C",
                        "modelo": _heredar("modelo", d.get("modelo")),
                        "color": _heredar("color", d.get("color")),
                        "anio": _heredar("anio", d.get("anio")),
                        "cilindraje": _heredar("cilindraje", d.get("cilindraje")),
                        "kilometraje": normalizar_kilometraje(d.get("kilometraje")),
                        "cliente": _heredar("cliente", d.get("cliente")),
                        "cedula": _heredar("cedula", cedula_extraida),
                        "telefono": _heredar("telefono", d.get("telefono")),
                        "motivo": d.get("motivo", ""),
                        "trabajos": nuevos,
                        "trabajo_realizado": trabajo_final,
                        "oficial": d.get("oficial", ""),
                        "cobro": cobro_final,
                        "metodo_pago": d.get("metodo_pago", "") if cierra else "",
                        "banco": banco_extraido if cierra else "",
                        "fecha_hora": tiempo_actual,
                        "fecha_salida": fecha_sal,
                        "estado": estado_nuevo,
                        "mensaje_id": id_msj,
                        **garantia_nueva
                    })
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
            # Repuestos: se descuentan en cualquier etapa (un avance también puede
            # usar repuestos, ej. "se cambia la bobina"), ligados a esta orden.
            if reparacion_id_actual and d.get("repuestos_usados"):
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

        cambios_cola = {"estado": estado_cola_final}
        if nota_cola:
            cambios_cola["ultimo_error"] = nota_cola
        supabase.table("cola_mensajes").update(cambios_cola).eq("id", id_msj).execute()
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

    if solicitud.borrador:
        # Confirmación desde el modal "faltan datos": ya sabemos que es un registro
        accion, placa_extraida = "registro", ""
    else:
        try:
            # 1. Obtenemos el JSON de Groq o DeepSeek
            resultado_bruto, proveedor_usado = await asyncio.to_thread(generar_json_con_respaldo, prompt_router)
        
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

    # --- REGISTRO: validación previa + cola en segundo plano ---
    mapa_tecnicos = obtener_tecnicos_registrados(taller_id)
    resultado = None

    if solicitud.borrador:
        # Paso 2: el usuario completó los datos faltantes en el modal
        borrador = verificar_borrador(solicitud.borrador, taller_id)
        texto_usuario, resultado = borrador["texto"], borrador["resultado"]
        if resultado.get("tipo") == "reparacion" and resultado.get("reparacion"):
            # Un campo opcional del ingreso puede llegar vacío a propósito
            # (el usuario borró un dato mal escrito para completarlo al cierre)
            completados = {}
            for k, v in (solicitud.datos_confirmados or {}).items():
                valor = str(v or "").strip()
                if k in CAMPOS_EDITABLES_ORDEN and (valor or k in CAMPOS_VACIABLES_ORDEN):
                    completados[k] = valor
            # Se revalida con el modelo (normaliza la placa, etc.)
            resultado["reparacion"] = TrabajoTaller.model_validate({**resultado["reparacion"], **completados}).model_dump()
            # Decisión del usuario en la ventana de confirmación de cierre
            if solicitud.decision_cierre:
                resultado["reparacion"]["cierra"] = solicitud.decision_cierre == "cerrar"
    else:
        # Paso 1: la IA extrae los datos AHORA para poder revisarlos antes de guardar
        try:
            prompt = construir_prompt_extraccion(taller_id, texto_usuario, list(mapa_tecnicos.values()))
            bruto, _ = await asyncio.to_thread(generar_json_con_respaldo, prompt)
            resultado = ClasificacionMensaje.model_validate(bruto).model_dump()
        except Exception as e:
            # IA no disponible: no se bloquea el trabajo del taller. El mensaje se
            # encola igual y el trabajador lo procesará cuando la IA responda.
            print(f"Pre-validación no disponible, se encola sin validar: {e}")
            resultado = None

    garantia_aviso = None
    pendientes_cierre = []
    cierre_descartado = False
    if resultado and resultado.get("tipo") == "reparacion" and resultado.get("reparacion"):
        orden, faltantes, contexto = await asyncio.to_thread(
            validar_orden_trabajo, resultado["reparacion"], taller_id, mapa_tecnicos, texto_usuario)
        resultado["reparacion"] = orden
        garantia_aviso = contexto.get("garantia")
        pendientes_cierre = contexto.get("pendientes_cierre") or []
        if faltantes:
            # NO se guarda nada: el frontend muestra el modal para completar
            return {
                "status": "faltan_datos",
                "faltantes": faltantes,
                "tecnicos": sorted(mapa_tecnicos.values()),
                "contexto": contexto,
                "borrador": firmar_borrador(taller_id, texto_usuario, resultado),
                "mensaje_bd": ("Faltan datos obligatorios para cerrar la orden de trabajo."
                               if contexto.get("es_cierre") else
                               "Faltan datos obligatorios para registrar el ingreso del vehículo."),
            }

        # Punto 4: NINGUNA orden se cierra sin que el usuario vea el resumen y
        # lo confirme. Mientras no confirme, no se guarda nada.
        if contexto.get("es_cierre") and not isinstance(orden.get("cierra"), bool):
            return {
                "status": "confirmar_cierre",
                "contexto": contexto,
                "borrador": firmar_borrador(taller_id, texto_usuario, resultado),
                "mensaje_bd": "Confirma el cierre de la orden.",
            }
        # Decisión final explícita para el trabajador de la cola
        orden["cierra"] = bool(contexto.get("es_cierre"))
        cierre_descartado = contexto.get("cierre_descartado", False)

    encolar_registro(cliente_seguro, taller_id, texto_usuario, tiempo_actual, resultado)
    background_tasks.add_task(trabajador_silencioso)

    return {
        "status": "éxito",
        "tipo_detectado": "registro",
        "validado": resultado is not None,
        "garantia": garantia_aviso,
        "pendientes_cierre": pendientes_cierre,
        # La IA creyó que era un cierre pero el mensaje no dice que se terminó/cobró
        "cierre_descartado": cierre_descartado,
        "mensaje_bd": "¡Recibido en la nube! Procesando registro en segundo plano."
                      if resultado is not None else
                      "Recibido. La IA no está disponible en este momento: el registro se procesará automáticamente cuando vuelva.",
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

# --- Normalización de métodos de pago y bancos (texto libre escrito por la IA) ---
# La IA guarda lo que el empleado escribió ("efectivo", "Transf.", "tarjeta de
# crédito", "deuna"...). Para cuadrar caja hay que agruparlo en categorías fijas.
_CLAVES_METODO_PAGO = [
    ("Transferencia", ("transf", "deposito", "depósito", "deuna", "payphone", "banco")),
    ("Tarjeta",       ("tarjeta", "credito", "crédito", "debito", "débito", "datafast", "visa", "mastercard")),
    ("Efectivo",      ("efectivo", "cash", "contado", "billete")),
]
_BANCOS_CONOCIDOS = {
    "pichincha": "Pichincha", "guayaquil": "Guayaquil", "produbanco": "Produbanco",
    "pacifico": "Pacífico", "pacífico": "Pacífico", "bolivariano": "Bolivariano",
    "internacional": "Internacional", "austro": "Austro", "loja": "Loja", "machala": "Machala",
    "jep": "JEP", "jardin azuayo": "Jardín Azuayo", "jardín azuayo": "Jardín Azuayo",
    "bgr": "BGR", "general ruminahui": "BGR", "rumiñahui": "BGR", "solidario": "Solidario",
    "procredit": "ProCredit", "citibank": "Citibank", "deuna": "Pichincha",  # DeUna deposita en cuentas Pichincha: así cuadra con el estado de cuenta
}

def normalizar_metodo_pago(metodo: str | None, banco: str | None) -> tuple[str, str]:
    """Devuelve (categoría, banco). Categoría: Efectivo | Transferencia | Tarjeta |
    Otro | Sin especificar. Si hay banco pero no método, se asume Transferencia."""
    texto = str(metodo or "").strip().lower()
    banco_txt = str(banco or "").strip()
    categoria = "Sin especificar"
    if texto:
        categoria = "Otro"
        for nombre, claves in _CLAVES_METODO_PAGO:
            if any(c in texto for c in claves):
                categoria = nombre
                break
    elif banco_txt:
        categoria = "Transferencia"

    banco_norm = ""
    if categoria in ("Transferencia", "Tarjeta"):
        base = (banco_txt or texto).lower()
        for clave, nombre in _BANCOS_CONOCIDOS.items():
            if clave in base:
                banco_norm = nombre
                break
        if not banco_norm and banco_txt:
            # Banco no reconocido: se muestra tal cual, sin la palabra "banco"
            banco_norm = re.sub(r"(?i)^banco\s+(del?\s+)?", "", banco_txt).strip().title()
    return categoria, banco_norm

def hora_ecuador(fecha_utc) -> str:
    """'2026-09-23 19:32:05' (UTC) -> '14:32' (hora de Ecuador)."""
    if not fecha_utc:
        return ""
    try:
        texto = str(fecha_utc).replace("T", " ").replace("Z", "")[:19]
        dt = datetime.strptime(texto, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(ZONA_ECUADOR).strftime("%H:%M")
    except ValueError:
        return ""


@app.get("/reporte-dia")
def reporte_del_dia(request: Request, fecha: str | None = None):
    """
    Cuadre de caja del día (día calendario de Ecuador; 'fecha' opcional YYYY-MM-DD).
    Incluye todo lo necesario para cerrar caja:
      - Totales: ingresos, egresos, neto, mano de obra vs repuestos.
      - Ingresos por método de pago (efectivo / transferencia por banco / tarjeta).
      - Efectivo esperado en caja (efectivo cobrado - egresos).
      - Detalle de órdenes cerradas (hora, placa, cliente, trabajo, técnico, pago).
      - Egresos con detalle y total por responsable.
      - Rendimiento y comisiones por técnico.
      - Movimiento de vehículos del día y alertas de datos incompletos.
    """
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    inicio_utc, fin_utc = limites_dia_ecuador(fecha)

    ordenes_cerradas = (
        # Cliente admin: el JOIN a reparacion_detalles no tiene política RLS de
        # SELECT. Sigue aislado por .eq("taller_id", ...).
        supabase.table("reparaciones")
        .select("vehiculo, cliente, modelo, oficial, trabajo_realizado, cobro, metodo_pago, banco, "
                "fecha_hora, fecha_salida, reparacion_detalles(cantidad, precio_unitario)")
        .eq("taller_id", taller_id)
        .eq("estado", "Terminado")
        .gte("fecha_salida", inicio_utc)
        .lte("fecha_salida", fin_utc)
        .order("fecha_salida")   # cronológico: de la mañana a la noche
        .execute()
    ).data or []

    egresos = (
        cliente_seguro.table("gastos")
        .select("monto, motivo, vehiculo, responsable, fecha_hora")
        .eq("taller_id", taller_id)
        .gte("fecha_hora", inicio_utc)
        .lte("fecha_hora", fin_utc)
        .order("fecha_hora")
        .execute()
    ).data or []

    # Movimiento de vehículos: cuántos ingresaron hoy y cuántos siguen en el taller
    ingresados_hoy = (
        supabase.table("reparaciones").select("id", count="exact")
        .eq("taller_id", taller_id).gte("fecha_hora", inicio_utc).lte("fecha_hora", fin_utc)
        .limit(1).execute()
    ).count or 0
    pendientes_taller = (
        supabase.table("reparaciones").select("id", count="exact")
        .eq("taller_id", taller_id).eq("estado", "Pendiente")
        .limit(1).execute()
    ).count or 0

    # Vehículos cerrados SIN COBRO hoy (garantías, sin presupuesto, etc.).
    # No suman a ingresos ni comisiones, pero se muestran para el control.
    try:
        cerrados_sin_cobro = (
            supabase.table("reparaciones")
            .select("vehiculo, cliente, modelo, oficial, fecha_salida, motivo_cierre, detalle_cierre")
            .eq("taller_id", taller_id).eq("estado", ESTADO_CERRADO_SIN_COBRO)
            .gte("fecha_salida", inicio_utc).lte("fecha_salida", fin_utc)
            .order("fecha_salida")
            .execute()
        ).data or []
    except Exception:
        cerrados_sin_cobro = []   # migración aún no ejecutada

    # Porcentajes de comisión (cliente admin: tecnicos no tiene política RLS de SELECT)
    tecnicos_bd = supabase.table("tecnicos").select("nombre, porcentaje_comision").eq("taller_id", taller_id).execute().data
    mapa_comisiones = {normalizar_nombre_tecnico(t["nombre"]): float(t.get("porcentaje_comision") or 0) for t in tecnicos_bd}
    nombres_oficiales = {normalizar_nombre_tecnico(t["nombre"]): t["nombre"].strip() for t in tecnicos_bd if t.get("nombre")}

    # ---------------- Ingresos: por orden, por método de pago y por técnico ----------------
    total_ingresos = total_repuestos = 0.0
    por_metodo: dict[str, dict] = {}
    rendimiento: dict[str, dict] = {}
    alertas: list[str] = []
    detalle_ordenes = []

    for o in ordenes_cerradas:
        cobro = float(o.get("cobro") or 0)
        repuestos = sum(float(r.get("cantidad") or 0) * float(r.get("precio_unitario") or 0)
                        for r in (o.get("reparacion_detalles") or []))
        mano_de_obra = max(0.0, cobro - repuestos)
        categoria, banco = normalizar_metodo_pago(o.get("metodo_pago"), o.get("banco"))
        # Solo cuenta un técnico REGISTRADO (con su nombre oficial)
        tecnico = canonizar_tecnico(o.get("oficial"), nombres_oficiales)
        placa = o.get("vehiculo") or "-"

        total_ingresos += cobro
        total_repuestos += min(repuestos, cobro)

        # Agrupación por método de pago (y por banco dentro de transferencias/tarjeta)
        grupo = por_metodo.setdefault(categoria, {"metodo": categoria, "ordenes": 0, "total": 0.0, "bancos": {}})
        grupo["ordenes"] += 1
        grupo["total"] += cobro
        # Desglose por banco: siempre en transferencias; en tarjeta solo si se indicó
        if categoria == "Transferencia" or (categoria == "Tarjeta" and banco):
            b = grupo["bancos"].setdefault(banco or "Banco no indicado", {"banco": banco or "Banco no indicado", "ordenes": 0, "total": 0.0})
            b["ordenes"] += 1
            b["total"] += cobro

        # Comisión solo sobre mano de obra (se excluyen repuestos) y solo para técnicos registrados
        if tecnico:
            reg = rendimiento.setdefault(tecnico, {"trabajos": 0, "total_generado": 0.0, "mano_de_obra": 0.0, "comision_a_pagar": 0.0})
            reg["trabajos"] += 1
            reg["total_generado"] += cobro
            reg["mano_de_obra"] += mano_de_obra
            reg["comision_a_pagar"] += mano_de_obra * (mapa_comisiones.get(normalizar_nombre_tecnico(tecnico), 0) / 100.0)

        # Alertas: datos que impiden un cuadre correcto
        if categoria == "Sin especificar":
            alertas.append(f"{placa}: cobro de ${cobro:.2f} sin método de pago.")
        elif categoria == "Otro":
            alertas.append(f"{placa}: método de pago no reconocido ('{o.get('metodo_pago')}').")
        elif categoria == "Transferencia" and not banco:
            alertas.append(f"{placa}: transferencia de ${cobro:.2f} sin banco indicado.")
        if cobro <= 0:
            alertas.append(f"{placa}: orden cerrada con cobro $0.00.")
        if not tecnico:
            original = str(o.get("oficial") or "").strip()
            alertas.append(f"{placa}: técnico '{original}' no está registrado (no genera comisión)."
                           if original else f"{placa}: orden sin técnico asignado (no genera comisión).")

        detalle_ordenes.append({
            "hora": hora_ecuador(o.get("fecha_salida")),
            "vehiculo": placa,
            "modelo": o.get("modelo") or "",
            "cliente": o.get("cliente") or "-",
            "trabajo": o.get("trabajo_realizado") or "",
            "oficial": tecnico or "Sin técnico",
            "metodo_pago": categoria,
            "banco": banco,
            "repuestos": round(min(repuestos, cobro), 2),
            "cobro": round(cobro, 2),
        })

    orden_metodos = ["Efectivo", "Transferencia", "Tarjeta", "Otro", "Sin especificar"]
    ingresos_por_metodo = []
    for nombre in orden_metodos:
        if nombre in por_metodo:
            g = por_metodo[nombre]
            ingresos_por_metodo.append({
                "metodo": nombre,
                "ordenes": g["ordenes"],
                "total": round(g["total"], 2),
                "porcentaje": round(100 * g["total"] / total_ingresos, 1) if total_ingresos else 0.0,
                "bancos": sorted(({**b, "total": round(b["total"], 2)} for b in g["bancos"].values()),
                                 key=lambda x: x["total"], reverse=True),
            })

    # ---------------- Egresos: detalle y total por responsable ----------------
    total_egresos = 0.0
    por_responsable: dict[str, dict] = {}
    detalle_egresos = []
    for g in egresos:
        monto = float(g.get("monto") or 0)
        responsable = (g.get("responsable") or "").strip() or "Sin responsable"
        total_egresos += monto
        r = por_responsable.setdefault(responsable, {"responsable": responsable, "cantidad": 0, "total": 0.0})
        r["cantidad"] += 1
        r["total"] += monto
        vehiculo = g.get("vehiculo") or ""
        detalle_egresos.append({
            "hora": hora_ecuador(g.get("fecha_hora")),
            "motivo": g.get("motivo") or "-",
            "vehiculo": "" if vehiculo.upper() in ("N/A", "NA", "") else vehiculo,
            "responsable": responsable,
            "monto": round(monto, 2),
        })
        if responsable == "Sin responsable":
            alertas.append(f"Egreso '{g.get('motivo') or '-'}' de ${monto:.2f} sin responsable.")

    egresos_por_responsable = sorted(({**r, "total": round(r["total"], 2)} for r in por_responsable.values()),
                                     key=lambda x: x["total"], reverse=True)

    # Efectivo esperado en caja: los egresos del taller se pagan de caja (efectivo)
    efectivo_cobrado = por_metodo.get("Efectivo", {}).get("total", 0.0)
    efectivo_en_caja = efectivo_cobrado - total_egresos

    ranking_tecnicos = [
        {
            "tecnico": nombre,
            "trabajos": d["trabajos"],
            "total_generado": round(d["total_generado"], 2),
            "mano_de_obra": round(d["mano_de_obra"], 2),
            "comision_a_pagar": round(d["comision_a_pagar"], 2),
        }
        for nombre, d in sorted(rendimiento.items(), key=lambda item: item[1]["total_generado"], reverse=True)
    ]

    return {
        "fecha": fecha or datetime.now(ZONA_ECUADOR).strftime("%Y-%m-%d"),
        # Totales
        "total_ingresos": round(total_ingresos, 2),
        "total_egresos": round(total_egresos, 2),
        "neto": round(total_ingresos - total_egresos, 2),
        "total_mano_obra": round(total_ingresos - total_repuestos, 2),
        "total_repuestos": round(total_repuestos, 2),
        "efectivo_cobrado": round(efectivo_cobrado, 2),
        "efectivo_en_caja": round(efectivo_en_caja, 2),
        "total_comisiones": round(sum(t["comision_a_pagar"] for t in ranking_tecnicos), 2),
        # Desgloses
        "ingresos_por_metodo": ingresos_por_metodo,
        "ordenes_cerradas": detalle_ordenes,
        "egresos": detalle_egresos,
        "egresos_por_responsable": egresos_por_responsable,
        "rendimiento_tecnicos": ranking_tecnicos,
        "vehiculos": {"ingresados_hoy": ingresados_hoy, "entregados_hoy": len(ordenes_cerradas),
                      "cerrados_sin_cobro": len(cerrados_sin_cobro), "pendientes_en_taller": pendientes_taller},
        "cerrados_sin_cobro": [
            {"hora": hora_ecuador(c.get("fecha_salida")), "vehiculo": c.get("vehiculo") or "-",
             "modelo": c.get("modelo") or "", "cliente": c.get("cliente") or "-",
             "oficial": canonizar_tecnico(c.get("oficial"), nombres_oficiales) or "-",
             "motivo": c.get("motivo_cierre") or "-", "detalle": c.get("detalle_cierre") or ""}
            for c in cerrados_sin_cobro
        ],
        "alertas": alertas,
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

    # SOLO técnicos registrados. Los nombres se cruzan normalizados ("jordy" =
    # "Jordy") y se muestran con el nombre oficial. Los registrados sin trabajos
    # aparecen con 0. Lo que no tiene técnico válido no entra al ranking.
    nombres_oficiales = {normalizar_nombre_tecnico(t["nombre"]): t["nombre"].strip() for t in tecnicos_bd if t.get("nombre")}
    acumulado: dict[str, dict] = {
        nombre: {"trabajos": 0, "total_generado": 0.0, "mano_de_obra_total": 0.0, "comision_acumulada": 0.0}
        for nombre in nombres_oficiales.values()
    }
    excluidos = {"trabajos": 0, "monto": 0.0}
    for o in ordenes:
        cobro = o.get("cobro", 0) or 0
        tecnico = canonizar_tecnico(o.get("oficial"), nombres_oficiales)
        if not tecnico:
            excluidos["trabajos"] += 1
            excluidos["monto"] += cobro
            continue
        reg = acumulado[tecnico]
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
            acumulado.items(), key=lambda x: (x[1]["mano_de_obra_total"], x[1]["trabajos"]), reverse=True
        ))
    ]

    return {
        "anio": anio,
        "leaderboard": ranking,
        # Informativo: trabajos del año sin técnico registrado (no cuentan en el ranking)
        "excluidos": {"trabajos": excluidos["trabajos"], "monto": round(excluidos["monto"], 2)}
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

    # SOLO técnicos registrados (con su nombre oficial); los demás no se liquidan
    nombres_oficiales = {normalizar_nombre_tecnico(t["nombre"]): t["nombre"].strip() for t in tecnicos_bd if t.get("nombre")}
    liquidacion: dict[str, dict] = {
        nombre: {"trabajos": 0, "total_generado": 0.0, "mano_de_obra_total": 0.0, "comision_total": 0.0}
        for nombre in nombres_oficiales.values()
    }
    for o in ordenes:
        tecnico = canonizar_tecnico(o.get("oficial"), nombres_oficiales)
        if not tecnico:
            continue
        reg = liquidacion[tecnico]

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

# ==============================================================================
# CERRAR ORDEN SIN COBRO (botón "Cerrar orden" en la tarjeta del vehículo)
# ==============================================================================
# Para vehículos que se van sin que se cobre nada. Si hubo cobro (aunque sea
# un diagnóstico) NO se usa esto: se registra como un cierre normal por el chat.
MOTIVOS_CIERRE_SIN_COBRO = {
    "garantia":        "Se cubre garantía",
    "sin_presupuesto": "Cliente sin presupuesto para la reparación",
    "sin_tiempo":      "Cliente no dispone de tiempo para la reparación",
    "fuera_capacidad": "Falla sobrepasa las capacidades del taller",
    "otro":            "Otro",
}
# En estos motivos el detalle es obligatorio (qué se hizo / cuál fue el motivo)
MOTIVOS_CON_DETALLE_OBLIGATORIO = {"garantia", "otro"}
ESTADO_CERRADO_SIN_COBRO = "Cerrado sin cobro"

class CierreSinCobro(BaseModel):
    motivo: str
    detalle: str = ""
    # Solo para motivo "garantia" (etapa 2): de qué orden es la garantía,
    # por qué falló y cuánto le costó al taller atenderla.
    orden_origen_id: str | None = None
    causa: str | None = None                      # mano_obra | repuesto | otra
    costo: float = Field(default=0, ge=0, le=100000)
    proveedor: str = ""

CAUSAS_GARANTIA = {"mano_obra": "Falla de mano de obra", "repuesto": "Falla del repuesto", "otra": "Otra causa"}

@app.get("/motivos-cierre")
def listar_motivos_cierre(request: Request):
    obtener_cliente_seguro(request)
    return {"motivos": [{"clave": k, "texto": v, "detalle_obligatorio": k in MOTIVOS_CON_DETALLE_OBLIGATORIO}
                        for k, v in MOTIVOS_CIERRE_SIN_COBRO.items()]}

@app.post("/reparaciones/{reparacion_id}/cerrar-sin-cobro")
def cerrar_orden_sin_cobro(reparacion_id: str, datos: CierreSinCobro, request: Request):
    cliente_seguro, taller_id = obtener_cliente_seguro(request)

    if datos.motivo not in MOTIVOS_CIERRE_SIN_COBRO:
        raise HTTPException(status_code=400, detail="Selecciona un motivo de cierre válido.")
    detalle = datos.detalle.strip()
    if datos.motivo in MOTIVOS_CON_DETALLE_OBLIGATORIO and len(detalle) < 3:
        raise HTTPException(status_code=400, detail="Para este motivo es obligatorio escribir el detalle.")

    # La orden debe ser de ESTE taller y seguir abierta (cliente admin + filtro taller_id)
    orden = (supabase.table("reparaciones").select("id, vehiculo, estado")
             .eq("id", reparacion_id).eq("taller_id", taller_id).limit(1).execute()).data
    if not orden:
        raise HTTPException(status_code=404, detail="No se encontró la orden en este taller.")
    if orden[0].get("estado") != "Pendiente":
        raise HTTPException(status_code=409, detail=f"La orden ya estaba cerrada ({orden[0].get('estado')}).")

    # Reclamo de garantía: se liga a la orden original del MISMO vehículo y taller
    datos_reclamo = {}
    if datos.motivo == "garantia":
        if not datos.orden_origen_id:
            raise HTTPException(status_code=400, detail="Selecciona la orden original que cubre esta garantía.")
        if datos.causa not in CAUSAS_GARANTIA:
            raise HTTPException(status_code=400, detail="Selecciona la causa de la falla.")
        origen = (supabase.table("reparaciones").select("id, vehiculo, estado")
                  .eq("id", datos.orden_origen_id).eq("taller_id", taller_id).limit(1).execute()).data
        if (not origen or origen[0].get("estado") != "Terminado"
                or origen[0].get("vehiculo") != orden[0].get("vehiculo")
                or str(origen[0].get("id")) == str(orden[0].get("id"))):
            raise HTTPException(status_code=400, detail="La orden original debe ser un trabajo terminado del mismo vehículo en este taller.")
        datos_reclamo = {
            "garantia_orden_origen": origen[0]["id"],
            "garantia_causa": datos.causa,
            "garantia_costo": round(float(datos.costo or 0), 2),
        }
        if datos.causa == "repuesto":
            # Queda un reclamo pendiente al proveedor del repuesto que falló
            datos_reclamo["reclamo_proveedor_estado"] = "Pendiente"
            datos_reclamo["reclamo_proveedor_nombre"] = datos.proveedor.strip()[:120] or "Proveedor no indicado"

    try:
        actualizada = (
            supabase.table("reparaciones").update({
                "estado": ESTADO_CERRADO_SIN_COBRO,
                "motivo_cierre": MOTIVOS_CIERRE_SIN_COBRO[datos.motivo],
                "detalle_cierre": detalle,
                "cobro": 0,
                "fecha_salida": ahora_utc_str(),
                **datos_reclamo,
            })
            .eq("id", reparacion_id).eq("taller_id", taller_id)
            .eq("estado", "Pendiente")          # evita cerrar dos veces si hay dos clics a la vez
            .execute()
        ).data
    except APIError as e:
        if "motivo_cierre" in str(e) or "detalle_cierre" in str(e) or "estado_check" in str(e):
            raise HTTPException(status_code=500, detail="Falta ejecutar en Supabase la migración sql/2026-09-23d_cierre_sin_cobro.sql.")
        if "garantia_" in str(e) or "reclamo_proveedor" in str(e):
            raise HTTPException(status_code=500, detail="Falta ejecutar en Supabase la migración sql/2026-09-23f_garantias_reclamos.sql.")
        raise
    if not actualizada:
        raise HTTPException(status_code=409, detail="La orden ya fue cerrada por otra persona.")

    return {"status": "ok", "vehiculo": orden[0].get("vehiculo"), "motivo": MOTIVOS_CIERRE_SIN_COBRO[datos.motivo]}


# ==============================================================================
# REABRIR ORDEN (corrige un cierre por error, solo órdenes cerradas HOY)
# ==============================================================================
@app.post("/reparaciones/{reparacion_id}/reabrir")
def reabrir_orden(reparacion_id: str, request: Request):
    """Vuelve a poner en Pendiente una orden cerrada hoy (con o sin cobro).
    - Se conserva la lista de trabajos y los repuestos ya usados (sí se usaron).
    - Se borra lo que corresponde al cierre: cobro, pago, garantía entregada,
      motivo de cierre y el reclamo de garantía, que se volverán a registrar
      al cerrarla de nuevo."""
    _, taller_id = obtener_cliente_seguro(request)
    orden = (supabase.table("reparaciones").select("id, vehiculo, estado, fecha_salida")
             .eq("id", reparacion_id).eq("taller_id", taller_id).limit(1).execute()).data
    if not orden:
        raise HTTPException(status_code=404, detail="No se encontró la orden en este taller.")
    o = orden[0]
    if o.get("estado") not in ("Terminado", ESTADO_CERRADO_SIN_COBRO):
        raise HTTPException(status_code=409, detail="La orden ya está abierta.")
    hoy_inicio, hoy_fin = limites_dia_ecuador()
    salida = str(o.get("fecha_salida") or "").replace("T", " ")[:19]
    if not (hoy_inicio <= salida <= hoy_fin):
        raise HTTPException(status_code=409, detail="Solo se pueden reabrir órdenes cerradas hoy.")
    # No puede haber dos órdenes abiertas del mismo vehículo
    abierta = (supabase.table("reparaciones").select("id")
               .eq("taller_id", taller_id).eq("vehiculo", o.get("vehiculo")).eq("estado", "Pendiente")
               .limit(1).execute()).data
    if abierta and o.get("vehiculo") not in ("", "S/C"):
        raise HTTPException(status_code=409, detail=f"El vehículo ya tiene otra orden abierta (N° {abierta[0]['id']}).")

    cambios = {"estado": "Pendiente", "fecha_salida": None, "cobro": 0, "metodo_pago": "", "banco": ""}
    # Columnas de migraciones posteriores: se limpian solo si existen
    opcionales = {
        "garantia_dias": None, "garantia_km": None, "garantia_vence": None, "garantia_km_limite": None,
        "garantia_servicio": None, "motivo_cierre": None, "detalle_cierre": None,
        "garantia_orden_origen": None, "garantia_causa": None, "garantia_costo": 0,
        "reclamo_proveedor_estado": None, "reclamo_proveedor_nombre": None, "reclamo_proveedor_monto": 0,
    }
    try:
        res = (supabase.table("reparaciones").update({**cambios, **opcionales})
               .eq("id", reparacion_id).eq("taller_id", taller_id).eq("estado", o["estado"]).execute()).data
    except APIError:
        res = (supabase.table("reparaciones").update(cambios)
               .eq("id", reparacion_id).eq("taller_id", taller_id).eq("estado", o["estado"]).execute()).data
    if not res:
        raise HTTPException(status_code=409, detail="La orden cambió mientras se reabría. Actualiza la página.")
    return {"status": "ok", "vehiculo": o.get("vehiculo")}


# ==============================================================================
# GARANTÍAS — ETAPA 2: reclamos ligados, reporte y reclamos a proveedores
# ==============================================================================
@app.get("/reparaciones/{reparacion_id}/ordenes-previas")
def ordenes_previas_vehiculo(reparacion_id: str, request: Request):
    """Trabajos terminados anteriores del mismo vehículo (para elegir cuál cubre
    la garantía). Incluye el estado de su garantía y los repuestos con proveedor."""
    _, taller_id = obtener_cliente_seguro(request)
    actual = (supabase.table("reparaciones").select("id, vehiculo, kilometraje")
              .eq("id", reparacion_id).eq("taller_id", taller_id).limit(1).execute()).data
    if not actual:
        raise HTTPException(status_code=404, detail="No se encontró la orden en este taller.")
    previas = (supabase.table("reparaciones")
               .select("*, reparacion_detalles(cantidad, precio_unitario, inventario(codigo, nombre, proveedor))")
               .eq("taller_id", taller_id).eq("vehiculo", actual[0]["vehiculo"]).eq("estado", "Terminado")
               .order("fecha_salida", desc=True).limit(10).execute()).data or []
    km_actual = normalizar_kilometraje(actual[0].get("kilometraje"))
    resultado = []
    for o in previas:
        estado = _evaluar_garantia(o, km_actual) if o.get("garantia_vence") else None
        repuestos = [{"codigo": (d.get("inventario") or {}).get("codigo", ""),
                      "nombre": (d.get("inventario") or {}).get("nombre", ""),
                      "proveedor": (d.get("inventario") or {}).get("proveedor", "") or ""}
                     for d in (o.get("reparacion_detalles") or [])]
        resultado.append({
            "id": o.get("id"),
            "fecha": str(o.get("fecha_salida") or "")[:10],
            "trabajo": o.get("trabajo_realizado") or "",
            "tecnico": o.get("oficial") or "",
            "garantia_vence": o.get("garantia_vence"),
            "garantia_vigente": bool(estado and estado["vigente"]),
            "garantia_motivo_vencida": (estado or {}).get("motivo_vencida", "") if o.get("garantia_vence") else "sin garantía",
            "repuestos": repuestos,
        })
    return {"ordenes": resultado}


@app.get("/reporte-garantias")
def reporte_garantias(request: Request, desde: str | None = None, hasta: str | None = None):
    """Control de garantías del taller en un período (por defecto, últimos 90 días):
    garantías entregadas, reclamos, tasa de retorno y costo, por técnico, por
    servicio, por causa y por repuesto; más los reclamos a proveedores."""
    _, taller_id = obtener_cliente_seguro(request)
    from datetime import timedelta
    hoy = datetime.now(ZONA_ECUADOR).date()
    try:
        desde_d = datetime.strptime(desde, "%Y-%m-%d").date() if desde else hoy - timedelta(days=90)
        hasta_d = datetime.strptime(hasta, "%Y-%m-%d").date() if hasta else hoy
    except ValueError:
        raise HTTPException(status_code=400, detail="Fechas inválidas (formato AAAA-MM-DD).")
    if desde_d > hasta_d:
        raise HTTPException(status_code=400, detail="La fecha 'desde' no puede ser mayor que 'hasta'.")
    inicio_utc, _ = limites_dia_ecuador(desde_d.isoformat())
    _, fin_utc = limites_dia_ecuador(hasta_d.isoformat())

    tecnicos_bd = supabase.table("tecnicos").select("nombre").eq("taller_id", taller_id).execute().data or []
    nombres_oficiales = {normalizar_nombre_tecnico(t["nombre"]): t["nombre"].strip() for t in tecnicos_bd if t.get("nombre")}
    tecnico_de = lambda o: canonizar_tecnico(o.get("oficial"), nombres_oficiales) or "Sin técnico registrado"

    try:
        # Garantías ENTREGADAS en el período (trabajos terminados con garantía)
        entregadas = (supabase.table("reparaciones")
                      .select("id, oficial, trabajo_realizado, garantia_servicio")
                      .eq("taller_id", taller_id).eq("estado", "Terminado").gt("garantia_dias", 0)
                      .gte("fecha_salida", inicio_utc).lte("fecha_salida", fin_utc)
                      .execute()).data or []
        # RECLAMOS atendidos en el período
        reclamos = (supabase.table("reparaciones")
                    .select("id, vehiculo, cliente, fecha_salida, detalle_cierre, garantia_orden_origen, garantia_causa, "
                            "garantia_costo, reclamo_proveedor_estado, reclamo_proveedor_nombre, reclamo_proveedor_monto")
                    .eq("taller_id", taller_id).not_.is_("garantia_orden_origen", "null")
                    .gte("fecha_salida", inicio_utc).lte("fecha_salida", fin_utc)
                    .order("fecha_salida", desc=True)
                    .execute()).data or []
        # Reclamos a proveedores aún PENDIENTES (de cualquier fecha: no se deben olvidar)
        pendientes_prov = (supabase.table("reparaciones")
                           .select("id, vehiculo, cliente, fecha_salida, detalle_cierre, garantia_orden_origen, garantia_causa, "
                                   "garantia_costo, reclamo_proveedor_estado, reclamo_proveedor_nombre, reclamo_proveedor_monto")
                           .eq("taller_id", taller_id).eq("reclamo_proveedor_estado", "Pendiente")
                           .execute()).data or []
    except APIError as e:
        if "garantia" in str(e) or "reclamo_proveedor" in str(e):
            raise HTTPException(status_code=500, detail="Falta ejecutar en Supabase las migraciones de garantías (2026-09-23e y 2026-09-23f).")
        raise

    # Órdenes originales de los reclamos (una sola consulta), con sus repuestos
    ids_origen = sorted({r["garantia_orden_origen"] for r in reclamos + pendientes_prov if r.get("garantia_orden_origen")}, key=str)
    origenes = {}
    if ids_origen:
        filas = (supabase.table("reparaciones")
                 .select("id, oficial, trabajo_realizado, garantia_servicio, fecha_salida, "
                         "reparacion_detalles(cantidad, inventario(codigo, nombre, proveedor))")
                 .eq("taller_id", taller_id).in_("id", ids_origen).execute()).data or []
        origenes = {str(f["id"]): f for f in filas}

    def servicio_de(o):
        s = (o or {}).get("garantia_servicio") or ""
        if not s or s.startswith("Garantía general") or s.startswith("Indicada") or s.startswith("Sin garantía"):
            s = (o or {}).get("trabajo_realizado") or "Sin detalle"
        return s[:80]

    # --- Agregados ---
    por_tecnico: dict[str, dict] = {}
    por_servicio: dict[str, dict] = {}
    for e in entregadas:
        t = por_tecnico.setdefault(tecnico_de(e), {"tecnico": tecnico_de(e), "entregadas": 0, "reclamos": 0, "costo": 0.0})
        t["entregadas"] += 1
        sv = servicio_de(e)
        por_servicio.setdefault(sv, {"servicio": sv, "entregadas": 0, "reclamos": 0, "costo": 0.0})["entregadas"] += 1

    por_causa = {k: {"causa": v, "reclamos": 0, "costo": 0.0} for k, v in CAUSAS_GARANTIA.items()}
    por_repuesto: dict[str, dict] = {}
    detalle = []
    costo_total = 0.0
    for r in reclamos:
        o = origenes.get(str(r.get("garantia_orden_origen")))
        costo = float(r.get("garantia_costo") or 0)
        costo_total += costo
        tec = tecnico_de(o or {})
        t = por_tecnico.setdefault(tec, {"tecnico": tec, "entregadas": 0, "reclamos": 0, "costo": 0.0})
        t["reclamos"] += 1; t["costo"] += costo
        sv = servicio_de(o)
        s_ = por_servicio.setdefault(sv, {"servicio": sv, "entregadas": 0, "reclamos": 0, "costo": 0.0})
        s_["reclamos"] += 1; s_["costo"] += costo
        causa = r.get("garantia_causa") or "otra"
        if causa in por_causa:
            por_causa[causa]["reclamos"] += 1; por_causa[causa]["costo"] += costo
        if causa == "repuesto" and o:
            for dd in (o.get("reparacion_detalles") or []):
                inv = dd.get("inventario") or {}
                clave = inv.get("codigo") or inv.get("nombre") or "?"
                rp = por_repuesto.setdefault(clave, {"codigo": inv.get("codigo", ""), "nombre": inv.get("nombre", ""),
                                                     "proveedor": inv.get("proveedor", "") or "", "reclamos": 0})
                rp["reclamos"] += 1
        detalle.append({
            "id": r.get("id"), "fecha": str(r.get("fecha_salida") or "")[:10], "vehiculo": r.get("vehiculo") or "-",
            "cliente": r.get("cliente") or "-", "orden_origen": r.get("garantia_orden_origen"),
            "trabajo_original": (o or {}).get("trabajo_realizado") or "-", "tecnico": tec,
            "causa": CAUSAS_GARANTIA.get(causa, causa), "detalle": r.get("detalle_cierre") or "", "costo": round(costo, 2),
        })

    def tasa(reclamos_n, entregadas_n):
        return round(100 * reclamos_n / entregadas_n, 1) if entregadas_n else None

    lista_tecnicos = sorted(({**t, "costo": round(t["costo"], 2), "tasa": tasa(t["reclamos"], t["entregadas"])}
                             for t in por_tecnico.values()), key=lambda x: (-x["reclamos"], x["tecnico"]))
    lista_servicios = sorted(({**s_, "costo": round(s_["costo"], 2), "tasa": tasa(s_["reclamos"], s_["entregadas"])}
                              for s_ in por_servicio.values() if s_["reclamos"]), key=lambda x: -x["reclamos"])

    # Reclamos a proveedores: los del período + TODOS los pendientes
    vistos, reclamos_prov = set(), []
    for r in reclamos + pendientes_prov:
        if not r.get("reclamo_proveedor_estado") or str(r["id"]) in vistos:
            continue
        vistos.add(str(r["id"]))
        o = origenes.get(str(r.get("garantia_orden_origen"))) or {}
        repuestos = ", ".join(((d.get("inventario") or {}).get("nombre") or "") for d in (o.get("reparacion_detalles") or [])) or "-"
        reclamos_prov.append({
            "id": r["id"], "fecha": str(r.get("fecha_salida") or "")[:10], "vehiculo": r.get("vehiculo") or "-",
            "orden_origen": r.get("garantia_orden_origen"), "repuestos": repuestos,
            "proveedor": r.get("reclamo_proveedor_nombre") or "-", "estado": r.get("reclamo_proveedor_estado"),
            "costo": round(float(r.get("garantia_costo") or 0), 2),
            "recuperado": round(float(r.get("reclamo_proveedor_monto") or 0), 2),
        })
    reclamos_prov.sort(key=lambda x: (x["estado"] != "Pendiente", x["fecha"]), reverse=False)

    recuperado = sum(x["recuperado"] for x in reclamos_prov if x["estado"] == "Aprobado")
    total_entregadas = len(entregadas)
    return {
        "desde": desde_d.isoformat(), "hasta": hasta_d.isoformat(),
        "resumen": {
            "entregadas": total_entregadas, "reclamos": len(reclamos),
            "tasa_retorno": tasa(len(reclamos), total_entregadas),
            "costo_total": round(costo_total, 2), "recuperado_proveedores": round(recuperado, 2),
            "costo_neto": round(costo_total - recuperado, 2),
            "reclamos_proveedor_pendientes": sum(1 for x in reclamos_prov if x["estado"] == "Pendiente"),
        },
        "por_tecnico": lista_tecnicos,
        "por_servicio": lista_servicios,
        "por_causa": [{**c, "costo": round(c["costo"], 2)} for c in por_causa.values()],
        "por_repuesto": sorted(por_repuesto.values(), key=lambda x: -x["reclamos"]),
        "reclamos_proveedor": reclamos_prov,
        "detalle": detalle,
    }


class ActualizacionReclamoProveedor(BaseModel):
    estado: Literal["Pendiente", "Aprobado", "Rechazado"]
    monto: float = Field(default=0, ge=0, le=100000)   # lo que devolvió/abonó el proveedor

@app.patch("/reparaciones/{reparacion_id}/reclamo-proveedor")
def actualizar_reclamo_proveedor(reparacion_id: str, datos: ActualizacionReclamoProveedor, request: Request):
    _, taller_id = obtener_cliente_seguro(request)
    res = (supabase.table("reparaciones")
           .update({"reclamo_proveedor_estado": datos.estado,
                    "reclamo_proveedor_monto": round(datos.monto, 2) if datos.estado == "Aprobado" else 0})
           .eq("id", reparacion_id).eq("taller_id", taller_id)
           .not_.is_("reclamo_proveedor_estado", "null")
           .execute()).data
    if not res:
        raise HTTPException(status_code=404, detail="No se encontró el reclamo en este taller.")
    return {"status": "ok"}


@app.get("/vehiculos-pendientes")
def listar_pendientes(request: Request):
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    hoy_inicio, hoy_fin = limites_dia_ecuador()

    pendientes = (
        # Cliente admin: el JOIN a reparacion_detalles/inventario no tiene política RLS de SELECT
        supabase.table("reparaciones")
        .select("*, reparacion_detalles(cantidad, precio_unitario, inventario(codigo, nombre))")
        .eq("taller_id", taller_id)
        .eq("estado", "Pendiente")
        .execute()
    ).data

    terminados_hoy = (
        supabase.table("reparaciones")
        .select("*, reparacion_detalles(cantidad, precio_unitario, inventario(codigo, nombre))")
        .eq("taller_id", taller_id)
        .eq("estado", "Terminado")
        .gte("fecha_salida", hoy_inicio)
        .lte("fecha_salida", hoy_fin)
        .execute()
    ).data

    # Cerrados sin cobro hoy (se muestran en la pestaña "Terminados hoy").
    # Consulta aparte: si la migración aún no se ejecutó, simplemente no hay.
    try:
        sin_cobro_hoy = (
            supabase.table("reparaciones")
            .select("id, vehiculo, cliente, modelo, color, anio, cilindraje, telefono, motivo, oficial, "
                    "estado, fecha_hora, fecha_salida, motivo_cierre, detalle_cierre")
            .eq("taller_id", taller_id)
            .eq("estado", ESTADO_CERRADO_SIN_COBRO)
            .gte("fecha_salida", hoy_inicio)
            .lte("fecha_salida", hoy_fin)
            .execute()
        ).data or []
    except Exception:
        sin_cobro_hoy = []

    # Pendientes con garantía de un trabajo anterior (se marca en la tarjeta).
    # Una sola consulta para todos los vehículos del taller.
    previas = buscar_garantias_lote(taller_id, [v.get("vehiculo") for v in pendientes])
    for v in pendientes:
        g = _evaluar_garantia(previas.get(v.get("vehiculo")), normalizar_kilometraje(v.get("kilometraje")))
        if g and g["orden_id"] != v.get("id"):
            v["garantia_previa"] = g

    return {"vehiculos": pendientes + terminados_hoy + sin_cobro_hoy}
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
    # None = usar la garantía por defecto del taller; 0 días = sin garantía
    garantia_dias: int | None = Field(default=None, ge=0, le=3650)
    garantia_km: int | None = Field(default=None, ge=0, le=500000)

class GarantiaServicio(BaseModel):
    garantia_dias: int | None = Field(default=None, ge=0, le=3650)
    garantia_km: int | None = Field(default=None, ge=0, le=500000)

@app.get("/servicios")
def listar_servicios(request: Request):
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    data = cliente_seguro.table("servicios").select("*").eq("taller_id", taller_id).order("nombre_servicio").execute().data
    dias, km = obtener_garantia_taller(taller_id)
    return {"servicios": data, "garantia_defecto": {"dias": dias, "km": km}}

@app.post("/servicios")
def agregar_servicio(datos: NuevoServicio, request: Request):
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    fila = {"taller_id": taller_id, "nombre_servicio": datos.nombre_servicio.strip(), "precio_base": datos.precio_base}
    if datos.garantia_dias is not None:
        fila["garantia_dias"] = datos.garantia_dias
    if datos.garantia_km is not None:
        fila["garantia_km"] = datos.garantia_km
    cliente_seguro.table("servicios").insert(fila).execute()
    return {"status": "ok", "mensaje": "Servicio agregado exitosamente"}

class GarantiaTaller(BaseModel):
    dias: int = Field(ge=0, le=3650)
    km: int = Field(ge=0, le=500000)

@app.put("/garantia-taller")
def actualizar_garantia_taller(datos: GarantiaTaller, request: Request):
    """El dueño define la garantía por defecto de SU taller."""
    _, taller_id = obtener_cliente_seguro(request)
    try:
        # Cliente admin filtrado por el taller del JWT (talleres puede no tener política de UPDATE)
        supabase.table("talleres").update({"garantia_dias_defecto": datos.dias, "garantia_km_defecto": datos.km}).eq("id", taller_id).execute()
    except APIError as e:
        if "garantia" in str(e):
            raise HTTPException(status_code=500, detail="Falta ejecutar en Supabase la migración sql/2026-09-23e_garantias_kilometraje.sql.")
        raise
    return {"status": "ok"}

@app.patch("/servicios/{servicio_id}/garantia")
def actualizar_garantia_servicio(servicio_id: str, datos: GarantiaServicio, request: Request):
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    res = (cliente_seguro.table("servicios")
           .update({"garantia_dias": datos.garantia_dias, "garantia_km": datos.garantia_km})
           .eq("id", servicio_id).eq("taller_id", taller_id).execute())
    if not res.data:
        raise HTTPException(status_code=404, detail="No se encontró el servicio en este taller.")
    return {"status": "ok"}

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