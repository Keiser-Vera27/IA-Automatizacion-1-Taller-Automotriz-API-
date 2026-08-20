# ==============================================================================
# Proyecto: API del Taller Automotriz con IA, Supabase (Nube), y Proveedores
# Autor: Keiser Vera
# ==============================================================================

import os
import re
import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware # <--- NUEVA IMPORTACIÓN
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, EmailStr
from dotenv import load_dotenv
from google import genai
from google.genai import types, errors
import pandas as pd
from supabase import create_client, Client


def normalizar_placa(texto: str) -> str:
    """
    Deja la placa en un formato único: mayúsculas, sin espacios ni guiones.
    Así "abb777", "ABB 777" y "ABB-777" quedan todas como "ABB777",
    en vez de crear vehículos duplicados en la base de datos.
    """
    if not texto:
        return texto
    return re.sub(r"[\s\-]", "", texto).upper().strip()

# ==============================================================================
# CONFIGURACIÓN DE SUPABASE Y CLIENTE DE IA
# ==============================================================================

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # Llave maestra para el trabajador en segundo plano
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")     # Llave pública para crear clientes seguros

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

app = FastAPI(title="API del Taller Automotriz - Cloud Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # En el futuro, aquí pondrás el dominio exacto de tu web
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ------------------------------------------------

app.mount("/web", StaticFiles(directory="static", html=True), name="static")

# ==============================================================================
# DEPENDENCIA DE SEGURIDAD (ESCUDO MULTI-TENANT)
# ==============================================================================

def obtener_cliente_seguro(request: Request):
    """
    Atrapa el Token de la petición, extrae el taller_id y crea una
    conexión a la base de datos blindada por las políticas RLS.
    También verifica que la suscripción del taller esté vigente.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        print("🔴 401: la petición llegó SIN header Authorization (el frontend no mandó el token)")
        raise HTTPException(status_code=401, detail="Falta el Pase VIP (Token)")

    token = auth_header.split(" ")[1]

    try:
        user_data = supabase.auth.get_user(token)
        usuario = user_data.user
        # Intentamos obtener el taller_id de los app_metadata
        taller_id = usuario.app_metadata.get("taller_id") if usuario.app_metadata else None
        
        # --- AUTOCORRECCIÓN SI FALTA EN METADATA ---
        if not taller_id and usuario.email:
            # Buscamos en la tabla de talleres si este correo es el jefe del taller
            taller_por_email = supabase.table("talleres").select("id").eq("email", usuario.email).execute().data
            if taller_por_email:
                taller_id = taller_por_email[0]["id"]
    except Exception as e:
        print(f"🔴 401: Supabase rechazó el token → {e}")
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    if not taller_id:
        print("🟠 403: token válido pero el usuario no tiene taller_id asignado")
        raise HTTPException(status_code=403, detail="Usuario sin taller asignado")

    # Verificar que el taller tenga acceso vigente
    try:
        taller_info = supabase.table("talleres").select("estado_pago, fecha_vencimiento").eq("id", taller_id).execute().data
    except Exception as e:
        print(f"🔴 500: fallo al verificar suscripción del taller {taller_id} → {e}")
        print("   ¿Ya corriste migracion_panel_admin.sql? Verifica que 'talleres' tenga las columnas estado_pago y fecha_vencimiento.")
        raise HTTPException(status_code=500, detail="Error interno verificando la suscripción del taller")

    if taller_info:
        estado_pago = taller_info[0].get("estado_pago")
        fecha_vencimiento = taller_info[0].get("fecha_vencimiento")
        
        # Mensaje personalizado y profesional
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
    """
    Protege los endpoints del panel de administración global (/admin/*).
    Solo pasa si el token pertenece a un usuario con "rol": "superadmin"
    en su app_metadata (asignado a mano desde el Dashboard de Supabase,
    nunca por API — ver migracion_panel_admin.sql).
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta el Pase VIP (Token)")

    token = auth_header.split(" ")[1]

    try:
        user_data = supabase.auth.get_user(token)
        rol = user_data.user.app_metadata.get("rol")
    except Exception as e:
        print(f"🔴 401 (admin): Supabase rechazó el token → {e}")
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

    if rol != "superadmin":
        print(f"🟠 403 (admin): usuario sin rol superadmin intentó acceder al panel")
        raise HTTPException(status_code=403, detail="No tienes permisos de administrador")

    return token

# ==============================================================================
# SISTEMA DE AUTENTICACIÓN (LOGIN)
# ==============================================================================
# ==============================================================================
# SISTEMA DE AUTENTICACIÓN (LOGIN) AISLADO
# ==============================================================================
class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/login")
def login(credenciales: LoginRequest):
    # IMPORTANTE: Creamos un cliente temporal solo para autenticar.
    # Así no contaminamos el cliente 'supabase' global que tiene la llave maestra.
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
# PANEL DE ADMINISTRACIÓN GLOBAL (SOLO SUPERADMIN)
#
# Todos los endpoints aquí usan el cliente `supabase` (llave de servicio),
# NO `cliente_seguro`, porque el superadmin necesita ver/crear datos de
# TODOS los talleres — RLS filtraría por taller_id, que el superadmin no tiene.
# La protección aquí es obtener_superadmin(), no RLS.
# ==============================================================================

class NuevoTallerRequest(BaseModel):
    nombre_taller: str
    email_jefe: EmailStr
    password_jefe: str = Field(min_length=6, description="Mínimo 6 caracteres (requisito de Supabase Auth)")
    plan: str = "mensual"  # 'mensual', 'trimestral' o 'anual'

class ActualizarTallerRequest(BaseModel):
    plan: str | None = None
    estado_pago: str | None = None       # 'activo' o 'suspendido'
    fecha_vencimiento: str | None = None  # formato YYYY-MM-DD

class NuevoUsuarioTallerRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    rol: str = "supervisor"  # 'jefe' o 'supervisor', solo informativo


@app.post("/admin/talleres")
def crear_taller(datos: NuevoTallerRequest, request: Request):
    # Aislar al superadmin...
    obtener_superadmin(request)

    # 1) Crear el registro del taller (¡AQUÍ AGREGAMOS EL EMAIL!)
    resultado_taller = supabase.table("talleres").insert({
        "nombre": datos.nombre_taller,
        "email": datos.email_jefe,     # <--- LÍNEA NUEVA
        "plan": datos.plan,
        "estado_pago": "activo",
    }).execute()
    
    # ... (el resto queda igual)

    if not resultado_taller.data:
        raise HTTPException(status_code=500, detail="No se pudo crear el registro del taller")

    taller_id = resultado_taller.data[0]["id"]

    # 2) Crear el usuario "jefe" en Supabase Auth, ya vinculado a ese taller_id.
    #    Esto es lo que le da acceso: sin este app_metadata, el login
    #    funcionaría pero obtener_cliente_seguro lo rechazaría con 403.
    try:
        supabase.auth.admin.create_user({
            "email": datos.email_jefe,
            "password": datos.password_jefe,
            "email_confirm": True,
            "app_metadata": {"taller_id": taller_id, "rol": "jefe"}
        })
    except Exception as e:
        # El taller ya se creó pero el usuario falló (ej: correo duplicado).
        # No revertimos el insert del taller para no perder el registro;
        # el superadmin puede agregar el usuario después con el otro endpoint.
        return {
            "status": "parcial",
            "taller_id": taller_id,
            "mensaje": f"Taller creado, pero el usuario jefe falló: {e}. Usa /admin/talleres/{taller_id}/usuarios para reintentar."
        }

    return {
        "status": "éxito",
        "taller_id": taller_id,
        "mensaje": f"Taller '{datos.nombre_taller}' creado con su usuario jefe ({datos.email_jefe})."
    }


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

    # Confirmar que el taller exista antes de crear el usuario
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

    return {"status": "éxito", "mensaje": f"Usuario {datos.email} agregado al taller {taller_id} como {datos.rol}"}

# ==============================================================================
# ESTRUCTURAS DE DATOS (PYDANTIC) — sin cambios
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
# TRABAJADOR SILENCIOSO — sin cambios respecto a tu versión
# ==============================================================================

async def trabajador_silencioso():
    response = supabase.table("cola_mensajes").select("id, texto, taller_id").eq("estado", "Pendiente").order("id").execute()
    pendientes = response.data

    if not pendientes:
        return

    for msj in pendientes:
        id_msj = msj["id"]
        texto_msj = msj["texto"]
        taller_id = msj["taller_id"]
        tiempo_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        prompt = f"""
        Eres un asistente contable inteligente de un taller mecánico.
        Analiza el siguiente mensaje y determina si se trata de un trabajo de reparación (ingreso), un gasto operativo (salida de dinero), un registro de INVENTARIO (ingreso de repuestos, extrayendo el proveedor si se menciona), o una DEVOLUCION.

        Clasificalo correctamente y extrae los datos correspondientes. Si faltan datos en el mensaje, déjalos vacíos o en 0 según corresponda.

        Mensaje: "{texto_msj}"
        """

        try:
            respuesta = await client.aio.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=ClasificacionMensaje,
                ),
            )
            resultado = json.loads(respuesta.text)
            tipo = resultado.get("tipo")

        except Exception as e:
            print(f"⚠️ Google saturado. Pausando la cola por 30 segundos... Error: {e}")
            await asyncio.sleep(30)
            break

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

                # Si el mensaje nuevo no trae modelo/color/año/cilindraje, se heredan
                # del último registro de esta misma placa (el mecánico no suele
                # repetir esos datos en visitas posteriores del mismo carro).
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
# GERENTE ANALÍTICO — NUEVO: function calling en vez de volcar tablas completas
#
# Idea central: Gemini NUNCA ve tus datos crudos. Solo decide qué función
# ejecutar y con qué parámetros (según la pregunta), tu backend ejecuta una
# consulta puntual y ya agregada en Postgres, y solo el resultado pequeño
# (una fila o pocas) se le devuelve a Gemini para redactar la respuesta.
# Esto es rápido y exacto sin importar si tienes 100 o 100,000 registros.
# ==============================================================================

# --- Declaración de las funciones que Gemini puede "pedir" ejecutar ---
HERRAMIENTAS_REPORTES = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="historial_vehiculo",
        description=(
            "Busca el historial de reparaciones de un vehículo por su placa. "
            "Úsala cuando pregunten quién trabajó un vehículo, cuándo vino la última vez, "
            "qué se le hizo, cuánto se cobró, método de pago o técnico responsable."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "placa": types.Schema(type="STRING", description="Placa del vehículo, ej: ABB777")
            },
            required=["placa"],
        ),
    ),
    types.FunctionDeclaration(
        name="cliente_top_visitas",
        description="Devuelve el cliente que más veces ha visitado el taller en un año específico.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "anio": types.Schema(type="INTEGER", description="Año a consultar, ej: 2026")
            },
            required=["anio"],
        ),
    ),
    types.FunctionDeclaration(
        name="cliente_top_gasto",
        description="Devuelve el cliente que más dinero ha gastado en el taller y el monto total.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "fecha_inicio": types.Schema(type="STRING", description="Fecha inicio YYYY-MM-DD, opcional (si no se menciona un rango, omitir)"),
                "fecha_fin": types.Schema(type="STRING", description="Fecha fin YYYY-MM-DD, opcional (si no se menciona un rango, omitir)"),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="rendimiento_tecnico",
        description=(
            "Calcula cuánto dinero ha generado un técnico específico, o el ranking de todos "
            "los técnicos, en un mes y año dado. Úsala para 'cuánto generó Fulano' o "
            "'quién es el técnico que más generó este mes'."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "mes": types.Schema(type="INTEGER", description="Mes numérico, 1 a 12"),
                "anio": types.Schema(type="INTEGER", description="Año, ej: 2026"),
                "tecnico": types.Schema(type="STRING", description="Nombre del técnico/oficial, opcional. Si preguntan 'quién generó más', omitir para traer el ranking completo."),
            },
            required=["mes", "anio"],
        ),
    ),
    types.FunctionDeclaration(
        name="info_repuesto",
        description="Busca precio de venta, costo y proveedor de un repuesto por nombre o código.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "nombre_o_codigo": types.Schema(type="STRING", description="Nombre o código del repuesto, ej: 'pastillas' o 'vss005'")
            },
            required=["nombre_o_codigo"],
        ),
    ),
])


def ejecutar_funcion_reporte(cliente_seguro, nombre_funcion: str, args: dict) -> dict:
    """
    Ejecuta la consulta puntual correspondiente contra Supabase.
    cliente_seguro ya trae el token del taller, así que RLS filtra
    automáticamente por taller_id — no hace falta pasarlo a mano aquí.
    """
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
    """
    Arma una respuesta legible en Markdown directo desde el resultado de Supabase,
    sin pasar por Gemini. Se usa como respaldo cuando la IA falla o está saturada,
    para que el usuario siempre reciba el dato aunque Google esté teniendo problemas.
    """
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

    if nombre_funcion == "repuestos_bajo_stock":
        items = resultado.get("resultados", [])
        if not items:
            return "No hay repuestos por debajo del umbral consultado."
        lineas = ["**Repuestos con stock bajo:**"]
        for r in items:
            lineas.append(f"- {r.get('nombre', '?')} ({r.get('codigo', 'S/C')}): {r.get('cantidad', 0)} unidades")
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
    Flujo de 2 llamadas, ambas livianas (nunca se manda la base de datos completa):
      1) Gemini decide qué función llamar y con qué parámetros.
      2) Le devolvemos el resultado (pequeño, ya calculado por SQL) y redacta la respuesta.
    Si Gemini falla o está saturado, se usa formatear_resultado_sin_ia como respaldo
    en vez de perder la respuesta o tumbar el endpoint.
    """
    import time
    t0 = time.time()
    contents = [types.Content(role="user", parts=[types.Part(text=texto_usuario)])]

    try:
        primera_respuesta = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                tools=[HERRAMIENTAS_REPORTES],
                system_instruction=(
                    "Eres el gerente analítico de un taller mecánico. Para responder preguntas "
                    "sobre historial de vehículos, clientes, técnicos o repuestos, SIEMPRE debes "
                    "llamar a la función correspondiente en vez de inventar una respuesta. "
                    "Si la pregunta no menciona mes/año explícito para técnicos, usa el mes y año actuales."
                ),
            ),
        )
    except (errors.ClientError, errors.ServerError) as e:
        codigo = getattr(e, "code", None)
        if codigo == 429:
            return (
                "⏳ Se agotó la cuota de consultas a la IA por ahora. "
                "Intenta de nuevo en unos minutos, o si esto se repite seguido, "
                "hay que revisar el plan de facturación de Gemini."
            )
        if codigo == 503:
            return (
                "⚠️ El modelo de IA está temporalmente saturado del lado de Google. "
                "Intenta de nuevo en un momento."
            )
        raise

    t1 = time.time()
    print(f"⏱️ Llamada 1 (elegir función): {t1 - t0:.2f}s")

    parte = primera_respuesta.candidates[0].content.parts[0]
    llamada = getattr(parte, "function_call", None)

    if not llamada:
        # La IA no encontró una función aplicable; devolvemos su texto tal cual
        # (puede pasar si la pregunta no es realmente una consulta de reportes).
        return primera_respuesta.text or "No pude interpretar esa pregunta como una consulta de reportes."

    args = dict(llamada.args) if llamada.args else {}
    resultado_funcion = ejecutar_funcion_reporte(cliente_seguro, llamada.name, args)

    t2 = time.time()
    print(f"⏱️ Consulta a Supabase ({llamada.name}): {t2 - t1:.2f}s")

    # Segunda llamada: solo con el resultado pequeño, no con las tablas completas
    contents.append(primera_respuesta.candidates[0].content)
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_function_response(
            name=llamada.name,
            response=resultado_funcion,
        )],
    ))

    try:
        segunda_respuesta = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                tools=[HERRAMIENTAS_REPORTES],
                system_instruction=(
                    "Redacta la respuesta final en español, clara y con formato Markdown "
                    "(viñetas/negritas para montos y fechas). Si el resultado viene vacío, "
                    "dilo explícitamente en vez de inventar datos."
                ),
            ),
        )
    except (errors.ClientError, errors.ServerError) as e:
        # Gemini falló al redactar, pero el dato YA está calculado y correcto
        # (viene de Supabase, no de la IA) — lo formateamos nosotros mismos
        # en vez de perder la respuesta o dejar que el endpoint truene.
        print(f"⚠️ Gemini falló en la redacción final ({e}); usando formateador de respaldo")
        return formatear_resultado_sin_ia(llamada.name, resultado_funcion)

    t3 = time.time()
    print(f"⏱️ Llamada 2 (redactar respuesta): {t3 - t2:.2f}s")
    print(f"⏱️ TOTAL: {t3 - t0:.2f}s")

    return segunda_respuesta.text


# ==============================================================================
# RECEPCIÓN WEB UNIFICADA (ENRUTADOR INTELIGENTE: REGISTRO O CONSULTA IA)
# ==============================================================================

@app.post("/procesar-mensaje")
async def procesar_mensaje_unificado(solicitud: SolicitudUnificada, background_tasks: BackgroundTasks, request: Request):
    cliente_seguro, taller_id = obtener_cliente_seguro(request)
    texto_usuario = solicitud.texto
    tiempo_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    prompt_router = f"""
    Analiza el siguiente texto de un usuario de taller mecánico y clasifícalo estrictamente en una de estas dos categorías:
    - "registro": Si el usuario está reportando un ingreso de vehículo, un trabajo hecho, un gasto, compra de repuestos o devolución.
    - "consulta": Si el usuario está haciendo una pregunta sobre reportes, estadísticas, historial de vehículos, precios, proveedores, técnicos o clientes.

    Texto: "{texto_usuario}"
    Responde únicamente con la palabra: "registro" o "consulta".
    """

    try:
        clasificacion = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt_router,
        ).text.strip().lower()
    except Exception:
        clasificacion = "registro"

    # --- CONSULTA ANALÍTICA: ahora vía function calling, no volcado de tablas ---
    if "consulta" in clasificacion:
        respuesta_ia = responder_consulta_analitica(cliente_seguro, texto_usuario)
        return {
            "status": "éxito_consulta",
            "tipo_detectado": "consulta",
            "mensaje_bd": respuesta_ia,
            "registrado_a_las": tiempo_actual
        }

    # --- REGISTRO NORMAL: sin cambios ---
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

# ==============================================================================
# EXPORTACIÓN CON SEGURIDAD RLS APLICADA — sin cambios
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

        hoy_str = datetime.now().strftime("%Y-%m-%d")
        hoy_archivo = datetime.now().strftime("%d-%m-%Y")

        if not df_reparaciones.empty and 'fecha_hora' in df_reparaciones.columns:
            df_reparaciones = df_reparaciones[df_reparaciones['fecha_hora'].str.startswith(hoy_str)]

        if not df_gastos.empty and 'fecha_hora' in df_gastos.columns:
            df_gastos = df_gastos[df_gastos['fecha_hora'].str.startswith(hoy_str)]

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
    hoy_inicio = datetime.now().strftime("%Y-%m-%d") + " 00:00:00"
    
    # Consultamos los pendientes del taller
    pendientes = (
        cliente_seguro.table("reparaciones")
        .select("vehiculo, cliente, telefono, modelo, color, anio, cilindraje, motivo, trabajo_realizado, cobro, metodo_pago, fecha_hora, estado")
        .eq("taller_id", taller_id)
        .eq("estado", "Pendiente")
        .execute()
    ).data

    # Consultamos los terminados que hayan sido registrados hoy
    terminados_hoy = (
        cliente_seguro.table("reparaciones")
        .select("vehiculo, cliente, telefono, modelo, color, anio, cilindraje, motivo, trabajo_realizado, cobro, metodo_pago, fecha_hora, estado")
        .eq("taller_id", taller_id)
        .eq("estado", "Terminado")
        .gte("fecha_hora", hoy_inicio)
        .execute()
    ).data

    # Unimos ambas listas para enviarlas juntas al frontend
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

        hoy_archivo = datetime.now().strftime("%d-%m-%Y")
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
    # En la nube, el proveedor (Railway/Render) asigna el puerto dinámicamente
    puerto = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=puerto, reload=False)
    # Forzar actualización de ruta