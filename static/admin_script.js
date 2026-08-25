/* ==========================================================================
   LÓGICA DEL PANEL SAAS (SISTEMA DE MODALES Y TOASTS PERSONALIZADOS)
   ========================================================================== */

// --- SENSOR DE TOASTS (Reemplaza alert) ---
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';
    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s reverse ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// --- MANEJO DE MODALES (Reemplaza prompt) ---
let accionModalCallback = null;

function abrirModal(titulo, htmlInputs, callbackConfirmar) {
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
            document.getElementById("dash-active-subs").innerText = data.subscriptions.active;
            
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
                document.getElementById("lista-alertas").innerHTML = `<div class="alerta-card alerta-ok">🟢 Todo en orden. Todos los talleres están al día y activos.</div>`;
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
        
        html += `
        <div class="taller-card">
            <div class="taller-info">
                <div class="taller-header-row">
                    <h4 class="taller-nombre">${t.nombre}</h4>
                    <span class="pill-badge pill-plan">${t.plan}</span>
                    ${badgeEstado}
                </div>
                <div class="taller-meta">
                    <span><b>ID:</b> ${t.id}</span>
                    <span>•</span>
                    <span><b>Vence:</b> ${fechaMostrar}</span>
                </div>
            </div>

            <div class="card-actions">
                <!-- NUEVO BOTÓN 360 -->
                <button class="btn-action btn-view" onclick="abrirFicha360('${t.id}')">👁️ Ficha 360°</button>
                
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
        plan: document.getElementById("nuevo_plan").value
    };
    
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
        ? `<span class="pill-badge pill-activo">🟢 Activo</span>` 
        : `<span class="pill-badge pill-suspendido">🔴 Suspendido</span>`;

    const html = `
    <div class="ficha-360-container">
        <div class="ficha-360-header">
            <h2>${t.nombre}</h2>
            <div class="ficha-360-badges">
                ${badgeEstado}
                <span class="pill-badge pill-plan">Plan ${t.plan}</span>
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
                    <li><span>Email Contacto</span> <span style="font-size:12px;">${t.email}</span></li>
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
            <button class="btn-action btn-suspend" onclick="suspender('${t.id}')">Suspender Servicio</button>
            
            <!-- Preparado para la futura función 'Impersonar' -->
            <button class="btn-action btn-user" style="margin-left:auto;" onclick="showToast('Función Entrar como Taller en desarrollo', 'info')">👤 Entrar como este Taller</button>
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
                ${mostrarBoton ? `<button class="btn-action btn-pay" onclick="reprocesarMensaje('${m.id}')">🔄 Reprocesar</button>` : ''}
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