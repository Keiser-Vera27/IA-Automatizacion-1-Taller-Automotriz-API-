/* ==========================================================================
   LÓGICA DEL PANEL SAAS (SISTEMA DE MODALES Y TOASTS PERSONALIZADOS)
   ========================================================================== */

// --- SENSOR DE TOASTS (Reemplaza alert) ---
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const ICONOS_TOAST = {
        success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>',
        error: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
        info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="11" x2="12" y2="16"/><line x1="12" y1="7.5" x2="12.01" y2="7.5"/></svg>'
    };
    const icon = ICONOS_TOAST[type] || ICONOS_TOAST.info;
    toast.innerHTML = `<span style="display:inline-flex;vertical-align:middle;">${icon}</span> <span>${message}</span>`;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s reverse ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// --- MANEJO DE MODALES (Reemplaza prompt) ---
let accionModalCallback = null;

function abrirModal(titulo, htmlInputs, callbackConfirmar, ancho = false) {
    document.querySelector('#modal-overlay .modal-box').classList.toggle('modal-ancho', ancho);
    document.getElementById('modal-titulo').innerText = titulo;
    document.getElementById('modal-body').innerHTML = htmlInputs;
    document.getElementById('modal-overlay').classList.add('active');
    accionModalCallback = callbackConfirmar;
}

function cerrarModal() {
    document.getElementById('modal-overlay').classList.remove('active');
    accionModalCallback = null;
}

document.getElementById('modal-btn-confirmar').onclick = () => {
    if (accionModalCallback) accionModalCallback();
};

// --- AUTENTICACIÓN Y CARGA ---
async function loginAdmin() {
    const em = document.getElementById("admin_email").value;
    const pw = document.getElementById("admin_password").value;
    
    try {
        const res = await fetch("/login", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: em, password: pw })
        });
        const data = await res.json();
        
        if (data.status === "success" && data.token) {
            localStorage.setItem("admin_token", data.token);
            await verificarAcceso(data.token);
        } else {
            showToast("Credenciales inválidas.", "error");
        }
    } catch {
        showToast("Error de conexión al servidor.", "error");
    }
}

async function verificarAcceso(token) {
    const res = await fetch("/admin/talleres", { headers: { 'Authorization': `Bearer ${token}` } });
    if (res.ok) {
        document.getElementById("login-admin").style.display = "none";
        document.getElementById("panel-admin").style.display = "block";
        
        cargarPlanes().then(llenarSelectPlanes);
        cargarTalleres();
        cargarDashboard(); // Carga de métricas operacionales
        
        showToast("Sesión iniciada correctamente", "success");
    } else {
        localStorage.removeItem("admin_token");
        showToast("Acceso denegado: Privilegios insuficientes.", "error");
    }
}

// --- CARGAR DASHBOARD ---
async function cargarDashboard() {
    const token = localStorage.getItem("admin_token");
    try {
        const res = await fetch("/admin/dashboard-metrics", { 
            headers: { 'Authorization': `Bearer ${token}` } 
        });
        
        if (res.ok) {
            const data = await res.json();
            
            // Renderizar Talleres
            document.getElementById("dash-total-workshops").innerText = data.workshops.total;
            document.getElementById("dash-active-workshops").innerText = data.workshops.active;
            document.getElementById("dash-suspended-workshops").innerText = data.workshops.suspended;
            
            // Renderizar Suscripciones
            document.getElementById("dash-mrr").innerText = "$" + data.subscriptions.mrr;
            const porPlan = data.subscriptions.por_plan || {};
            document.getElementById("dash-por-plan").innerHTML =
                `<span class="pill-badge pill-plan">Activas: <b id="dash-active-subs">${data.subscriptions.active}</b></span>` +
                Object.entries(porPlan).map(([nombre, n]) => `<span class="pill-badge pill-plan">${esc(nombre)}: <b>${n}</b></span>`).join('');
            
            // Renderizar Sistema
            document.getElementById("dash-ai-today").innerHTML = `${data.system.ai_today} <span style="font-size: 14px; font-weight:normal; color: var(--text-muted);">usos IA hoy</span>`;
            document.getElementById("dash-errors").innerText = data.system.errors;
            
            // Renderizar Alertas Preventivas
            if (data.alertas && data.alertas.length > 0) {
                let htmlAlertas = "";
                data.alertas.forEach(alerta => {
                    let clase = "alerta-riesgo"; // Naranja por defecto
                    if (alerta.tipo === "critico") clase = "alerta-critico"; // Rojo
                    else if (alerta.tipo === "advertencia") clase = "alerta-advertencia"; // Amarillo
                    
                    htmlAlertas += `<div class="alerta-card ${clase}">${alerta.mensaje}</div>`;
                });
                document.getElementById("lista-alertas").innerHTML = htmlAlertas;
            } else {
                // Si no hay alertas, mostramos un mensaje verde tranquilizador
                document.getElementById("lista-alertas").innerHTML = `<div class="alerta-card alerta-ok">Todo en orden. Todos los talleres están al día y activos.</div>`;
            }
            document.getElementById("dashboard-alertas").style.display = "block";
            
            // Mostrar la sección del dashboard
            document.getElementById("dashboard-section").style.display = "block";
        }
    } catch (error) {
        showToast("Error al cargar las métricas del dashboard.", "error");
    }
}

async function cargarTalleres() {
    const token = localStorage.getItem("admin_token");
    const res = await fetch("/admin/talleres", { headers: { 'Authorization': `Bearer ${token}` } });
    const data = await res.json();
    
    let html = "";
    data.talleres.forEach(t => {
        const esActivo = t.estado_pago === 'activo';
        const badgeEstado = esActivo 
            ? `<span class="pill-badge pill-activo">Activo</span>` 
            : `<span class="pill-badge pill-suspendido">Suspendido</span>`;
            
        const fechaMostrar = t.fecha_vencimiento ? t.fecha_vencimiento : 'Sin fecha asignada';
        
        // Plan (funciones) y periodo (pago). Sin la migración de planes solo hay periodo.
        const planTxt = t.plan_nombre ? `${esc(t.plan_nombre)} · ${esc(t.periodo || '')}` : esc(t.plan);
        const totalModulos = catalogoModulos.length || 6;
        const lineaModulos = Array.isArray(t.modulos)
            ? `<span>•</span><span><b>Módulos:</b> ${t.modulos.length} de ${totalModulos}${t.n_excepciones ? ` (${t.n_excepciones} excepción${t.n_excepciones > 1 ? 'es' : ''})` : ''}</span>`
            : '';
        html += `
        <div class="taller-card">
            <div class="taller-info">
                <div class="taller-header-row">
                    <h4 class="taller-nombre">${esc(t.nombre)}</h4>
                    <span class="pill-badge pill-plan">${planTxt}</span>
                    ${badgeEstado}
                </div>
                <div class="taller-meta">
                    <span><b>ID:</b> ${esc(t.id)}</span>
                    <span>•</span>
                    <span><b>Vence:</b> ${esc(fechaMostrar)}</span>
                    ${lineaModulos}
                </div>
            </div>

            <div class="card-actions">
                <!-- NUEVO BOTÓN 360 -->
                <button class="btn-action btn-view" onclick="abrirFicha360('${t.id}')">Ficha 360°</button>
                <button class="btn-action btn-user" onclick="modalModulos('${t.id}')">Módulos</button>
                
                <button class="btn-action btn-pay" onclick="modalActualizarPago('${t.id}')">Renovar Pago</button>
                <button class="btn-action btn-suspend" onclick="suspender('${t.id}')">Suspender</button>
                <button class="btn-action btn-user" onclick="modalAgregarUsuario('${t.id}')">+ Usuario</button>
            </div>
        </div>`;
    });
    document.getElementById("lista-talleres").innerHTML = html;
}

// --- CREAR TALLER ---
async function crearTaller() {
    const token = localStorage.getItem("admin_token");
    const req = {
        nombre_taller: document.getElementById("nuevo_nombre").value, 
        email_jefe: document.getElementById("nuevo_email").value,
        password_jefe: document.getElementById("nuevo_pass").value,
        plan: document.getElementById("nuevo_plan").value,               // columna antigua (periodo)
        periodo_facturacion: document.getElementById("nuevo_plan").value
    };
    const planCodigo = document.getElementById("nuevo_plan_codigo").value;
    if (planCodigo) req.plan_codigo = planCodigo;   // vacío = migración de planes aún no ejecutada
    
    if(!req.nombre_taller || !req.email_jefe || !req.password_jefe) {
        showToast("Por favor complete todos los campos", "error");
        return;
    }
    
    try {
        const res = await fetch("/admin/talleres", {
            method: "POST", 
            headers: { "Content-Type": "application/json", 'Authorization': `Bearer ${token}` },
            body: JSON.stringify(req)
        });
        const data = await res.json();
        
        if (res.ok) {
            showToast(data.mensaje || "Taller registrado con éxito", "success");
            document.getElementById("nuevo_nombre").value = "";
            document.getElementById("nuevo_email").value = "";
            document.getElementById("nuevo_pass").value = "";
            cargarTalleres();
            cargarDashboard(); // Actualizar dashboard
        } else {
            const detalle = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : data.mensaje;
            showToast("Error: " + detalle, "error");
        }
    } catch {
        showToast("Error de conexión al servidor.", "error");
    }
}

// --- ACCIONES CON MODAL PROPIO ---
function modalActualizarPago(id) {
    const inputs = `<label style="font-size:13px; color:#aaa;">Nueva Fecha de Vencimiento:</label>
                    <input type="date" id="modal_fecha" style="width:100%;">`;
                    
    abrirModal("Actualizar Suscripción", inputs, async () => {
        const fecha = document.getElementById("modal_fecha").value;
        if(!fecha) {
            showToast("Seleccione una fecha válida", "error");
            return;
        }
        
        const token = localStorage.getItem("admin_token");
        await fetch(`/admin/talleres/${id}`, {
            method: "PATCH", 
            headers: { "Content-Type": "application/json", 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ estado_pago: 'activo', fecha_vencimiento: fecha })
        });
        
        cerrarModal();
        showToast("Suscripción renovada correctamente", "success");
        cargarTalleres();
        cargarDashboard(); // Actualizar dashboard
    });
}

function modalAgregarUsuario(id) {
    const inputs = `<input type="email" id="modal_user_email" placeholder="Correo del Usuario">
                    <input type="password" id="modal_user_pass" placeholder="Contraseña (mín 6 caracteres)">`;
                    
    abrirModal("Agregar Usuario Supervisor", inputs, async () => {
        const email = document.getElementById("modal_user_email").value;
        const pass = document.getElementById("modal_user_pass").value;
        
        if(!email || !pass) {
            showToast("Complete ambos campos", "error");
            return;
        }
        
        const token = localStorage.getItem("admin_token");
        const res = await fetch(`/admin/talleres/${id}/usuarios`, {
            method: "POST", 
            headers: { "Content-Type": "application/json", 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ email: email, password: pass, rol: "supervisor" }) 
        });
        
        if(res.ok) {
            cerrarModal();
            showToast("Usuario agregado al taller", "success");
        } else {
            const data = await res.json();
            showToast(data.detail || "Error al crear usuario", "error");
        }
    });
}

async function suspender(id) {
    const token = localStorage.getItem("admin_token");
    await fetch(`/admin/talleres/${id}`, {
        method: "PATCH", 
        headers: { "Content-Type": "application/json", 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ estado_pago: 'suspendido' })
    });
    showToast("Taller suspendido", "info");
    cargarTalleres();
    cargarDashboard(); // Actualizar dashboard
}

const cerrarSesionAdmin = () => { localStorage.removeItem("admin_token"); location.reload(); }
// --- LÓGICA FICHA 360° ---
async function abrirFicha360(id) {
    const token = localStorage.getItem("admin_token");
    try {
        // Transición de vistas
        document.getElementById("vista-principal").style.display = "none";
        document.getElementById("vista-360-taller").style.display = "block";
        document.getElementById("contenido-360").innerHTML = "<p style='padding:30px; color:#aaa;'>Cargando radiografía del taller...</p>";
        
        const res = await fetch(`/admin/talleres/${id}/ficha-360`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!res.ok) throw new Error("Error al obtener datos");
        const data = await res.json();
        
        renderizarFicha360(data);
    } catch (error) {
        showToast("Error al cargar la ficha 360°", "error");
        cerrarVista360();
    }
}

function cerrarVista360() {
    document.getElementById("vista-360-taller").style.display = "none";
    document.getElementById("vista-principal").style.display = "block";
}

function renderizarFicha360(data) {
    const t = data.taller;
    const u = data.uso;
    const a = data.actividad;
    
    const esActivo = t.estado_pago === 'activo';
    const badgeEstado = esActivo 
        ? `<span class="pill-badge pill-activo">Activo</span>` 
        : `<span class="pill-badge pill-suspendido">Suspendido</span>`;

    const html = `
    <div class="ficha-360-container">
        <div class="ficha-360-header">
            <h2>${t.nombre}</h2>
            <div class="ficha-360-badges">
                ${badgeEstado}
                <span class="pill-badge pill-plan">${t.plan_codigo ? `Plan ${esc(nombrePlan(t.plan_codigo))} · ${esc(t.periodo || '')}` : `Plan ${esc(t.plan)}`}</span>
                <span style="color:var(--text-muted); font-size:13px; margin-left:10px;">Cliente desde: ${t.created_at}</span>
                <span style="color:var(--text-muted); font-size:13px; margin-left:10px;">| ID: ${t.id}</span>
            </div>
        </div>
        
        <div class="ficha-360-body">
            <!-- Bloque Uso -->
            <div class="ficha-seccion">
                <h4>Volúmen de Uso</h4>
                <ul class="ficha-lista-datos">
                    <li><span>Clientes Registrados</span> <span>${u.clientes}</span></li>
                    <li><span>Vehículos Atendidos</span> <span>${u.vehiculos}</span></li>
                    <li><span>Total Reparaciones</span> <span>${u.reparaciones}</span></li>
                    <li><span>Usuarios Admin</span> <span>${u.usuarios_admin}</span></li>
                </ul>
            </div>
            
            <!-- Bloque Suscripción -->
            <div class="ficha-seccion">
                <h4>Suscripción</h4>
                <ul class="ficha-lista-datos">
                    <li><span>Próximo Pago</span> <span>${t.fecha_vencimiento}</span></li>
                    <li><span>Estado Actual</span> <span>${t.estado_pago.toUpperCase()}</span></li>
                    <li><span>Email Contacto</span> <span style="font-size:12px;">${esc(t.email)}</span></li>
                </ul>
            </div>

            <!-- Bloque Módulos -->
            <div class="ficha-seccion">
                <h4>Módulos activos</h4>
                <ul class="ficha-lista-datos">
                    ${(t.modulos || []).map(m => `<li><span>${esc(m)}</span></li>`).join('') || '<li><span>Solo funciones básicas</span></li>'}
                </ul>
            </div>
            
            <!-- Bloque Actividad -->
            <div class="ficha-seccion">
                <h4>Actividad Reciente</h4>
                <ul class="ficha-lista-datos">
                    <li><span>Último acceso/registro</span> <span>${a.ultima_actividad}</span></li>
                    <li><span>Peticiones IA (Hoy)</span> <span>${a.ia_hoy}</span></li>
                </ul>
            </div>
        </div>
        
        <div class="ficha-360-footer">
            <button class="btn-primary" onclick="modalActualizarPago('${t.id}')">Renovar Suscripción</button>
            <button class="btn-ghost" onclick="modalAgregarUsuario('${t.id}')">Agregar Usuario</button>
            <button class="btn-ghost" onclick="modalModulos('${t.id}')">Módulos</button>
            <button class="btn-action btn-suspend" onclick="suspender('${t.id}')">Suspender Servicio</button>
            
            <!-- Preparado para la futura función 'Impersonar' -->
            <button class="btn-action btn-user" style="margin-left:auto;" onclick="showToast('Función Entrar como Taller en desarrollo', 'info')">Entrar como este Taller</button>
        </div>
    </div>`;
    
    document.getElementById("contenido-360").innerHTML = html;
}
// ==========================================================================
//   LÓGICA DEL MONITOR DE IA
// ==========================================================================

function abrirMonitorIA() {
    document.getElementById("vista-principal").style.display = "none";
    document.getElementById("vista-360-taller").style.display = "none";
    document.getElementById("vista-monitor-ia").style.display = "block";
    cargarColaIA();
}

function cerrarMonitorIA() {
    document.getElementById("vista-monitor-ia").style.display = "none";
    document.getElementById("vista-principal").style.display = "block";
    cargarDashboard(); // Actualizar el conteo de errores por si reprocesamos
}

async function cargarColaIA() {
    const token = localStorage.getItem("admin_token");
    const contenedor = document.getElementById("lista-cola-ia");
    contenedor.innerHTML = "<p style='color:#aaa;'>Cargando cola...</p>";
    
    try {
        const res = await fetch("/admin/cola", {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!res.ok) throw new Error("Error al obtener la cola");
        const data = await res.json();
        
        if (data.mensajes.length === 0) {
            contenedor.innerHTML = "<p style='color:var(--accent-green);'>La cola está limpia. No hay mensajes recientes.</p>";
            return;
        }

        let html = "";
        data.mensajes.forEach(m => {
            // Determinar color del badge según estado
            let badgeClass = "pill-plan"; // gris
            let mostrarBoton = false;
            
            if (m.estado === "Pendiente" || m.estado === "Procesando") {
                badgeClass = "pill-plan"; 
            } else if (m.estado === "Procesado") {
                badgeClass = "pill-activo"; // verde
                mostrarBoton = true;
            } else {
                badgeClass = "pill-suspendido"; // rojo para errores o bloqueos
                mostrarBoton = true; // Solo reprocesamos si hubo error/bloqueo
            }
            
            const nombreTaller = m.talleres ? m.talleres.nombre : 'Taller Desconocido';
            
            html += `
            <div class="cola-card">
                <div class="cola-info">
                    <div style="display: flex; gap: 10px; align-items: center;">
                        <span class="pill-badge ${badgeClass}">${m.estado}</span>
                        <span class="cola-meta"><b>${nombreTaller}</b> • ${m.fecha_hora}</span>
                    </div>
                    <div class="cola-texto">"${m.texto}"</div>
                </div>
                ${mostrarBoton ? `<button class="btn-action btn-pay" onclick="reprocesarMensaje('${m.id}')">Reprocesar</button>` : ''}
            </div>`;
        });
        
        contenedor.innerHTML = html;
        
    } catch (error) {
        showToast("Error al cargar la cola de IA", "error");
        contenedor.innerHTML = "<p style='color:var(--accent-red);'>Error cargando datos.</p>";
    }
}

async function reprocesarMensaje(id) {
    const token = localStorage.getItem("admin_token");
    try {
        showToast("Enviando a reprocesar...", "info");
        
        const res = await fetch(`/admin/cola/${id}/reprocesar`, {
            method: "POST",
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!res.ok) throw new Error("Error al reprocesar");
        
        showToast("¡Mensaje reencolado con éxito!", "success");
        cargarColaIA(); // Refrescar la lista al instante
    } catch (error) {
        showToast("Error al intentar reprocesar", "error");
    }
}

// ==========================================================================
//   PLANES Y MÓDULOS
//   Plan = qué funciones tiene un taller. Excepción = un módulo activado o
//   quitado solo a ese taller (con fecha de fin opcional, ej. prueba gratis).
//   El backend valida todo (dependencias, fechas); aquí solo se ayuda.
// ==========================================================================
let planesCache = [];
let catalogoModulos = [];

// Escapa texto para meterlo en HTML (nombres de talleres, notas, etc.)
function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function cabeceraAdmin(json = false) {
    const h = { 'Authorization': `Bearer ${localStorage.getItem("admin_token")}` };
    if (json) h['Content-Type'] = 'application/json';
    return h;
}

function nombrePlan(codigo) {
    const p = planesCache.find(x => x.codigo === codigo);
    return p ? p.nombre : codigo;
}

function nombreModulo(clave) {
    const m = catalogoModulos.find(x => x.clave === clave);
    return m ? m.nombre : clave;
}

async function cargarPlanes() {
    try {
        const res = await fetch("/admin/planes", { headers: cabeceraAdmin() });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
        planesCache = data.planes || [];
        catalogoModulos = data.modulos || [];
        return true;
    } catch (e) {
        planesCache = [];
        return e.message;     // texto del error (ej. falta ejecutar el SQL)
    }
}

function llenarSelectPlanes() {
    const sel = document.getElementById("nuevo_plan_codigo");
    if (!sel) return;
    if (!planesCache.length) {
        sel.innerHTML = '<option value="">Sin planes (ejecuta el SQL de planes)</option>';
        return;
    }
    sel.innerHTML = planesCache.map(p => `<option value="${esc(p.codigo)}">Plan ${esc(p.nombre)}</option>`).join('');
    // Por defecto el plan más completo (el último)
    sel.value = planesCache[planesCache.length - 1].codigo;
}

// --- Ventana "Módulos" de un taller ---
const TEXTO_ACCION = {
    activado: 'Activó', desactivado: 'Quitó', segun_plan: 'Volvió a lo del plan',
    cambio_plan: 'Cambió de plan', plan_editado: 'Editó el plan'
};

async function modalModulos(tallerId) {
    let data;
    try {
        const res = await fetch(`/admin/talleres/${encodeURIComponent(tallerId)}/modulos`, { headers: cabeceraAdmin() });
        data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
    } catch (e) {
        showToast(esc(e.message), "error");
        return;
    }
    catalogoModulos = data.modulos.map(m => ({ clave: m.clave, nombre: m.nombre }));
    const planes = data.planes;

    const filas = data.modulos.map(m => {
        let estadoPill;
        if (m.activo) estadoPill = '<span class="pill-badge pill-activo">Activo</span>';
        else if (m.bloqueado) estadoPill = `<span class="pill-badge pill-aviso">Falta ${esc(m.requiere_nombres.join(', '))}</span>`;
        else estadoPill = '<span class="pill-badge pill-plan">Inactivo</span>';
        const vencida = m.vencida ? '<span class="pill-badge pill-aviso">Excepción vencida</span>' : '';
        return `
        <div class="modulo-fila" data-clave="${esc(m.clave)}">
            <div class="modulo-info">
                <div class="modulo-titulo"><b>${esc(m.nombre)}</b> ${estadoPill} ${vencida}</div>
                <div class="texto-ayuda">${esc(m.descripcion)}${m.requiere_nombres.length ? ` Requiere: ${esc(m.requiere_nombres.join(', '))}.` : ''}</div>
            </div>
            <div class="modulo-controles">
                <select class="sel-estado" onchange="ajustarFilaModulo(this)">
                    <option value="plan" ${m.estado === 'plan' ? 'selected' : ''}>${m.en_plan ? 'Según plan (incluido)' : 'Según plan (no incluido)'}</option>
                    <option value="activado" ${m.estado === 'activado' ? 'selected' : ''}>Activar para este taller</option>
                    <option value="desactivado" ${m.estado === 'desactivado' ? 'selected' : ''}>Quitar a este taller</option>
                </select>
                <input type="date" class="inp-hasta" value="${esc(m.hasta || '')}" title="Hasta (vacío = sin fecha de fin)">
                <input type="text" class="inp-nota" maxlength="300" value="${esc(m.nota)}" placeholder="Nota (ej. prueba gratis)">
            </div>
        </div>`;
    }).join('');

    const historial = (data.historial || []).map(h => `
        <li><span class="hist-fecha">${esc(formatearFecha(h.fecha))}</span>
            <span><b>${esc(TEXTO_ACCION[h.accion] || h.accion)}</b>${h.modulo ? ' ' + esc(nombreModulo(h.modulo)) : ''}${h.detalle ? ': ' + esc(h.detalle) : ''}
            <span class="hist-quien">· ${esc(h.admin_email || '')}</span></span></li>`).join('');

    const html = `
        <div class="modulos-cabecera">
            <label>Plan del taller
                <select id="sel-plan-taller" onchange="refrescarEtiquetasPlan()">
                    ${planes.map(p => `<option value="${esc(p.codigo)}" ${p.codigo === data.taller.plan_codigo ? 'selected' : ''}>${esc(p.nombre)}</option>`).join('')}
                </select>
            </label>
            <p class="texto-ayuda">"Según plan" sigue al plan. "Activar" o "Quitar" es una excepción solo para este taller;
                con fecha, vuelve sola a lo del plan cuando vence. Quitar un módulo no borra datos: solo los oculta.</p>
        </div>
        <div class="lista-modulos">${filas}</div>
        <h4 class="subtitulo-modal">Últimos cambios</h4>
        <ul class="historial-modulos">${historial || '<li><span class="texto-ayuda">Sin cambios registrados.</span></li>'}</ul>`;

    abrirModal(`Módulos · ${data.taller.nombre}`, html, () => guardarModulos(tallerId), true);
    window._planesModal = planes;
    document.querySelectorAll('#modal-body .modulo-fila .sel-estado').forEach(ajustarFilaModulo);
}

// Fecha/nota solo tienen sentido en una excepción
function ajustarFilaModulo(sel) {
    const fila = sel.closest('.modulo-fila');
    const excepcion = sel.value !== 'plan';
    fila.querySelectorAll('.inp-hasta, .inp-nota').forEach(i => i.disabled = !excepcion);
    fila.classList.toggle('con-excepcion', excepcion);
}

// Al cambiar de plan, "Según plan (incluido / no incluido)" se actualiza
function refrescarEtiquetasPlan() {
    const codigo = document.getElementById('sel-plan-taller').value;
    const plan = (window._planesModal || []).find(p => p.codigo === codigo) || { modulos: [] };
    document.querySelectorAll('#modal-body .modulo-fila').forEach(f => {
        const opt = f.querySelector('.sel-estado option[value="plan"]');
        opt.textContent = plan.modulos.includes(f.dataset.clave) ? 'Según plan (incluido)' : 'Según plan (no incluido)';
    });
}

async function guardarModulos(tallerId) {
    const ajustes = [...document.querySelectorAll('#modal-body .modulo-fila')].map(f => ({
        modulo: f.dataset.clave,
        estado: f.querySelector('.sel-estado').value,
        hasta: f.querySelector('.inp-hasta').value || null,
        nota: f.querySelector('.inp-nota').value.trim()
    }));
    const btn = document.getElementById('modal-btn-confirmar');
    btn.disabled = true;
    try {
        const res = await fetch(`/admin/talleres/${encodeURIComponent(tallerId)}/modulos`, {
            method: "PUT", headers: cabeceraAdmin(true),
            body: JSON.stringify({ plan_codigo: document.getElementById('sel-plan-taller').value, ajustes })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            showToast(esc(typeof data.detail === 'string' ? data.detail : `Error ${res.status}`), "error");
            return;
        }
        cerrarModal();
        showToast(data.cambios ? `Módulos actualizados (${data.cambios} cambio${data.cambios > 1 ? 's' : ''})` : "No había cambios", "success");
        cargarTalleres();
        cargarDashboard();
    } catch {
        showToast("Error de conexión al servidor.", "error");
    } finally {
        btn.disabled = false;
    }
}

function formatearFecha(valor) {
    const d = new Date(String(valor || '').replace(' ', 'T'));
    return isNaN(d) ? String(valor || '') : d.toLocaleString('es-EC', { dateStyle: 'short', timeStyle: 'short' });
}

// --- Vista "Planes y módulos" ---
async function abrirPlanes() {
    document.getElementById("vista-principal").style.display = "none";
    document.getElementById("vista-360-taller").style.display = "none";
    document.getElementById("vista-monitor-ia").style.display = "none";
    document.getElementById("vista-planes").style.display = "block";
    const cont = document.getElementById("lista-planes");
    cont.innerHTML = "<p style='color:#aaa;'>Cargando planes...</p>";
    const ok = await cargarPlanes();
    if (ok !== true) {
        cont.innerHTML = `<p style='color:var(--accent-red);'>${esc(ok)}</p>`;
        return;
    }
    cont.innerHTML = planesCache.map(p => `
        <div class="plan-card" data-codigo="${esc(p.codigo)}">
            <label class="campo-plan">Nombre del plan
                <input type="text" class="inp-nombre" value="${esc(p.nombre)}" maxlength="40"></label>
            <div class="precios-plan">
                <label class="campo-plan">Mensual ($)<input type="number" min="0" step="0.01" class="inp-precio" data-periodo="mensual" value="${Number(p.precio_mensual)}"></label>
                <label class="campo-plan">Trimestral ($)<input type="number" min="0" step="0.01" class="inp-precio" data-periodo="trimestral" value="${Number(p.precio_trimestral)}"></label>
                <label class="campo-plan">Anual ($)<input type="number" min="0" step="0.01" class="inp-precio" data-periodo="anual" value="${Number(p.precio_anual)}"></label>
            </div>
            <div class="checks-modulos">
                ${catalogoModulos.map(m => `
                <label class="check-modulo" title="${esc(m.descripcion)}">
                    <input type="checkbox" value="${esc(m.clave)}" ${p.modulos.includes(m.clave) ? 'checked' : ''} onchange="ajustarDependencias(this)">
                    <span><b>${esc(m.nombre)}</b><br><span class="texto-ayuda">${esc(m.descripcion)}${m.requiere_nombres.length ? ` Requiere: ${esc(m.requiere_nombres.join(', '))}.` : ''}</span></span>
                </label>`).join('')}
            </div>
            <button class="btn-primary" onclick="guardarPlan('${esc(p.codigo)}', this)">Guardar plan</button>
        </div>`).join('');
}

function cerrarPlanes() {
    document.getElementById("vista-planes").style.display = "none";
    document.getElementById("vista-principal").style.display = "block";
    cargarTalleres();
    cargarDashboard();
}

// Marcar un módulo marca sus requisitos; desmarcar un requisito desmarca a quien lo necesita
function ajustarDependencias(check) {
    const card = check.closest('.plan-card');
    const marcar = (clave, v) => { const c = card.querySelector(`input[type=checkbox][value="${clave}"]`); if (c) c.checked = v; };
    const mod = catalogoModulos.find(m => m.clave === check.value);
    if (check.checked) (mod.requiere || []).forEach(r => marcar(r, true));
    else catalogoModulos.filter(m => (m.requiere || []).includes(check.value)).forEach(m => marcar(m.clave, false));
}

async function guardarPlan(codigo, btn) {
    const card = btn.closest('.plan-card');
    const precio = p => parseFloat(card.querySelector(`.inp-precio[data-periodo="${p}"]`).value || '0');
    const cuerpo = {
        nombre: card.querySelector('.inp-nombre').value.trim(),
        precio_mensual: precio('mensual'), precio_trimestral: precio('trimestral'), precio_anual: precio('anual'),
        modulos: [...card.querySelectorAll('input[type=checkbox]:checked')].map(c => c.value)
    };
    btn.disabled = true;
    try {
        const res = await fetch(`/admin/planes/${encodeURIComponent(codigo)}`, {
            method: "PUT", headers: cabeceraAdmin(true), body: JSON.stringify(cuerpo)
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const d = data.detail;
            showToast(esc(typeof d === 'string' ? d : (Array.isArray(d) ? 'Revisa el nombre y los precios' : `Error ${res.status}`)), "error");
            return;
        }
        planesCache = data.planes || planesCache;
        llenarSelectPlanes();
        showToast(`Plan ${esc(cuerpo.nombre)} guardado. Ya se aplica a sus talleres.`, "success");
    } catch {
        showToast("Error de conexión al servidor.", "error");
    } finally {
        btn.disabled = false;
    }
}
