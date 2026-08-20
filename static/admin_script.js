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
        showToast("Sesión iniciada correctamente", "success");
    } else {
        localStorage.removeItem("admin_token");
        showToast("Acceso denegado: Privilegios insuficientes.", "error");
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
        } else {
            const detalle = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : data.mensaje;
            showToast("Error: " + detalle, "error");
        }
    } catch {
        showToast("Error de conexión al servidor.", "error");
    }
}

// --- ACCIONES CON MODAL PROPIO (Sustituye prompt) ---
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
}

const cerrarSesionAdmin = () => { localStorage.removeItem("admin_token"); location.reload(); }