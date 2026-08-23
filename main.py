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

# ==============================================================================
# ESTRUCTURAS DE DATOS (PYDANTIC)
# ==============================================================================

class RepuestoUsado(BaseModel):
    codigo: str = Field(description="Código exacto del repuesto usado (ej: vss005)")
    cantidad: int = Field(description="Cantidad de unidades utilizadas")

class TrabajoTaller(BaseModel):
    vehiculo: str = Field(description="OBLIGATORIO: Extrae ÚNICAMENTE la placa del vehículo (letras y números sin espacios, ej: PXY9876, ABB777). No incluyas marca ni color. Si no hay placa, extrae solo el modelo principal.")
    modelo: str = Field(default="", description="Marca y modelo del vehículo si se menciona, ej: 'Toyota Corolla', 'Kia Sportage'. Vacío si no se menciona.")
    color: str = Field(default="", description="Color del vehículo si se menciona, ej: 'blanco', 'gris plata'. Vacío si no se menciona.")
    anio: str = Field(default="", description="Año del vehículo si se menciona, ej: '2019'. Vacío si no se menciona.")
    cilindraje: str = Field(default="", description="Cilindraje del motor si se menciona, ej: '1.6', '2000cc'. Vacío si no se menciona.")
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

    @field_validator("vehiculo")
    @classmethod
    def _normalizar_placa_capturada(cls, v):
        return normalizar_placa(v)

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
    # Reclama mensajes de forma ATÓMICA vía la función SQL reclamar_mensajes_pendientes:
    # marca cada mensaje como "Procesando" en el mismo paso en que lo selecciona
    # (SELECT ... FOR UPDATE SKIP LOCKED). Esto evita que, si en el futuro corres
    # más de una instancia del servidor, dos procesos agarren y procesen el
    # mismo mensaje dos veces. También rescata mensajes que quedaron
    # "Procesando" por más de 10 minutos (servidor caído a medias).
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

        Responde en JSON con esta forma exacta:
        {{
          "tipo": "reparacion" | "gasto" | "inventario" | "devolucion",
          "reparacion": {{...}} | null,
          "gasto": {{...}} | null,
          "inventario": {{...}} | null,
          "devolucion": {{...}} | null
        }}
        Solo llena el objeto que corresponda a "tipo"; los demás van en null.

        Mensaje: "{texto_msj}"
        """

        try:
            resultado, proveedor_usado = await asyncio.to_thread(generar_json_con_respaldo, prompt)
            resultado = ClasificacionMensaje.model_validate(resultado).model_dump()
            tipo = resultado.get("tipo")

        except Exception as e:
            # Antes esto detenía TODA la cola con un 'break', dejando mensajes
            # sanos sin procesar hasta que llegara un mensaje nuevo que la
            # reactivara (de ahí los retrasos de horas). Ahora marcamos SOLO
            # este mensaje como error y seguimos con el resto de la cola.
            # Y ahora también intentamos Groq antes de rendirnos del todo.
            print(f"⚠️ Error de IA (Gemini y Groq) procesando mensaje {id_msj}: {e}")
            supabase.table("cola_mensajes").update({"estado": "Error (IA no disponible, se reintentará)"}).eq("id", id_msj).execute()
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
                print(f"⚠️ Error en el ciclo de auto-recuperación de la cola: {e}")

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
                "Úsala cuando pregunten quién trabajó un vehículo, cuándo vino la última vez, "
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
            "description": "Busca precio de venta, costo y proveedor de un repuesto por nombre o código.",
            "parameters": {
                "type": "object",
                "properties": {"nombre_o_codigo": {"type": "string", "description": "Nombre o código del repuesto"}},
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
            .select("vehiculo, cliente, fecha_hora, oficial, trabajo_realizado, cobro, metodo_pago, banco, estado")
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
        data = (
            cliente_seguro.table("inventario")
            .select("codigo, nombre, marca, proveedor, aplicacion, cantidad, costo, precio_venta")
            .or_(f"nombre.ilike.%{termino}%,codigo.ilike.%{termino}%")
            .limit(5)
            .execute()
        ).data
        return {"resultados": data}

    return {"error": f"Función '{nombre_funcion}' no reconocida"}

def formatear_resultado_sin_ia(nombre_funcion: str, resultado: dict) -> str:
    if nombre_funcion == "info_repuesto":
        items = resultado.get("resultados", [])
        if not items:
            return "No encontré ningún repuesto con ese nombre o código."
        lineas = ["**Repuestos encontrados:**"]
        for r in items:
            lineas.append(
                f"- **{r.get('nombre', '?')}** ({r.get('codigo', 'S/C')}) — "
                f"Precio venta: ${r.get('precio_venta', 0)} · Stock: {r.get('cantidad', 0)} · "
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

def responder_consulta_analitica(cliente_seguro, texto_usuario: str) -> str:
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

    resultado_funcion = ejecutar_funcion_reporte(cliente_seguro, llamada_nombre, args)

    # --- Segundo turno: redactar la respuesta final con el resultado real ---
    instruccion_redaccion = (
        "Redacta la respuesta final en español, clara y con formato Markdown. "
        "Si el resultado viene vacío, dilo explícitamente en vez de inventar datos."
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
            respuesta_analitica = responder_consulta_analitica(cliente_seguro, texto_usuario)
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