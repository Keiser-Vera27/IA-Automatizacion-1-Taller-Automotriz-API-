// ==============================================================================
// Script del Taller Automotriz - Autotronic Solutions IA
// ==============================================================================

// Validar sesión activa al cargar
window.onload = function() {
    const token = localStorage.getItem("taller_token");
    if (token) {
        document.getElementById("login-container").style.display = "none";
        document.getElementById("app-container").style.display = "block";
        cargarVehiculosPendientes(); 
    }

    const emailInput = document.getElementById("email_login");
    const passwordInput = document.getElementById("password_login");

    emailInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            iniciarSesion();
        }
    });

    passwordInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            iniciarSesion();
        }
    });

    const textoReporte = document.getElementById("texto_reporte");
    textoReporte.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            enviarReporte();
        }
    });
};

// Función de Login
async function iniciarSesion() {
    const email = document.getElementById("email_login").value;
    const password = document.getElementById("password_login").value;
    const msgError = document.getElementById("login_error");
    msgError.style.display = "none";

    if (!email || !password) {
        msgError.innerText = "Por favor completa ambos campos.";
        msgError.style.display = "block";
        return;
    }

    try {
        const response = await fetch("/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, password: password })
        });

        const data = await response.json();

        if (data.status === "success") {
            localStorage.setItem("taller_token", data.token);
            document.getElementById("login-container").style.display = "none";
            document.getElementById("app-container").style.display = "block";
            cargarVehiculosPendientes(); 
        } else {
            msgError.innerText = data.mensaje;
            msgError.style.display = "block";
        }
    } catch (error) {
        msgError.innerText = "Error de conexión con el servidor.";
        msgError.style.display = "block";
    }
}

// Función Logout
function cerrarSesion() {
    localStorage.removeItem("taller_token");
    document.getElementById("app-container").style.display = "none";
    document.getElementById("login-container").style.display = "block";
    document.getElementById("password_login").value = "";

    const cajaNotificacion = document.getElementById('caja-notificacion-ia');
    if (cajaNotificacion) {
        cajaNotificacion.innerHTML = "";
        cajaNotificacion.style.padding = "0";
    }
    
    const panelPendientes = document.getElementById('panel-vehiculos-pendientes');
    if (panelPendientes) {
        panelPendientes.remove();
    }

    document.getElementById("texto_reporte").value = "";
}

// Función unificada: Envía reportes de registro o consultas analíticas al enrutador
async function enviarReporte() {
    const inputTexto = document.getElementById('texto_reporte');
    const texto = inputTexto.value;
    const token = localStorage.getItem("taller_token");

    if (texto.trim() === "") {
        mostrarNotificacion("Por favor, escriba un reporte o una pregunta antes de enviar.", "warning");
        return;
    }

    if (!token) {
        mostrarNotificacion("Sesión expirada. Por favor, inicia sesión nuevamente.", "error");
        cerrarSesion();
        return;
    }

    try {
        mostrarNotificacion("Analizando mensaje con inteligencia artificial...", "info");

        const res = await fetch('/procesar-mensaje', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ texto: texto })
        });

        const data = await res.json();

        if (!res.ok) {
            inputTexto.value = "";
            const mensajeError = data.detail || "Error al procesar la solicitud en el servidor.";
            mostrarNotificacion(mensajeError, "warning");
            return;
        }

        if (data.status === "éxito") {
            inputTexto.value = "";
            mostrarNotificacion(`${data.mensaje_bd}`, "success");
            cargarVehiculosPendientes(); 
        }
        else if (data.status === "éxito_consulta") {
            inputTexto.value = "";
            mostrarNotificacion(`<b>Respuesta del Gerente IA:</b><br>${data.mensaje_bd}`, "info");
        }
        else {
            inputTexto.value = "";
            mostrarNotificacion(`Error del sistema: ${data.mensaje || "Desconocido"}`, "error");
        }

    } catch (e) {
        console.error("Error:", e);
        mostrarNotificacion("Error al conectar con el servidor.", "error");
    }
}

// Descarga de inventario, envía el Token JWT
async function descargarInventario() {
    const token = localStorage.getItem("taller_token");
    try {
        mostrarNotificacion("Generando formato de auditoria de inventario...", "info");

        const response = await fetch('/exportar-inventario', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Auditoria Inventario ${new Date().toLocaleDateString()}.xlsx`;
            document.body.appendChild(a);
            a.click();
            a.remove();

            mostrarNotificacion("Auditoria de inventario descargada correctamente.", "success");
        } else {
            const errData = await response.json().catch(() => ({}));
            mostrarNotificacion(errData.detail || "Error al generar el archivo de inventario.", "warning");
        }
    } catch (error) {
        console.error("Error:", error);
        mostrarNotificacion("Error de conexion al descargar el inventario.", "error");
    }
}

// Descarga reporte diario, envía el Token JWT
async function descargarReporteDiario() {
    const token = localStorage.getItem("taller_token");
    try {
        mostrarNotificacion("Generando reporte diario...", "info");

        const response = await fetch('/exportar-excel', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Reporte Cloud AS ${new Date().toLocaleDateString()}.xlsx`;
            document.body.appendChild(a);
            a.click();
            a.remove();

            mostrarNotificacion("Reporte diario descargado correctamente.", "success");
        } else {
            const errData = await response.json().catch(() => ({}));
            mostrarNotificacion(errData.detail || "Error al generar el reporte diario.", "warning");
        }
    } catch (error) {
        console.error("Error:", error);
        mostrarNotificacion("Error de conexion al descargar el reporte.", "error");
    }
}

// ==============================================================================
// GESTIÓN DEL PANEL VISUAL DE VEHÍCULOS (Glassmorphism)
// ==============================================================================

let filtroEstadoActual = 'Pendiente'; 

async function cargarVehiculosPendientes(estadoFiltro = 'Pendiente') {
    filtroEstadoActual = estadoFiltro;
    const token = localStorage.getItem("taller_token");
    if (!token) return;

    try {
        const response = await fetch('/vehiculos-pendientes', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            console.error(`Error al cargar vehículos pendientes (${response.status}):`, errData.detail || errData);
            return;
        }
        const data = await response.json();
        
        let container = document.getElementById('panel-vehiculos-pendientes');
        
        if (!container) {
            container = document.createElement('div');
            container.id = 'panel-vehiculos-pendientes';
            container.className = 'panel-pendientes';
            const app = document.getElementById('app-container');
            if (app) app.appendChild(container);
        }

        // Se usa data.vehiculos que mapea correctamente con la respuesta del backend
        const listaVehiculos = data.vehiculos || [];
        const vehiculosFiltrados = listaVehiculos.filter(v => v.estado === filtroEstadoActual);

        let html = `
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom: 10px; margin-bottom: 15px;">
                <h3 style="margin: 0; border: none; padding: 0;">Control de Vehículos</h3>
                <div style="display: flex; gap: 5px; background: rgba(0,0,0,0.3); padding: 3px; border-radius: 8px;">
                    <button onclick="cargarVehiculosPendientes('Pendiente')" style="background: ${filtroEstadoActual === 'Pendiente' ? 'rgba(0, 210, 255, 0.3)' : 'transparent'}; color: #fff; border: none; padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 0.85rem;">Pendientes</button>
                    <button onclick="cargarVehiculosPendientes('Terminado')" style="background: ${filtroEstadoActual === 'Terminado' ? 'rgba(46, 133, 64, 0.4)' : 'transparent'}; color: #fff; border: none; padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 0.85rem;">Terminados Hoy</button>
                </div>
            </div>
        `;

        if (vehiculosFiltrados.length > 0) {
            vehiculosFiltrados.forEach(v => {
                let detalleExtra = v.estado === 'Terminado' 
                    ? `<div style="color: #a8f5b6; font-size: 0.85rem; margin-top: 4px;">✅ Cobro: $${v.cobro || 0} (${v.metodo_pago || 'Efectivo'})</div>` 
                    : `<div class="info-taller-item"><strong>Falla / Motivo:</strong> ${v.motivo || 'No especificado'}</div>`;

                // Arma la línea de datos del vehículo solo con lo que sí venga informado
                const partesVehiculo = [v.modelo, v.color, v.anio, v.cilindraje ? `${v.cilindraje}cc` : ''].filter(Boolean);
                const infoVehiculo = partesVehiculo.length > 0
                    ? `<div class="info-taller-item"><strong>Vehículo:</strong> ${partesVehiculo.join(' · ')}</div>`
                    : '';

                // Teléfono con enlace "tel:" para llamar directo; stopPropagation
                // evita que el clic también dispare usarPlaca() de la tarjeta.
                const infoTelefono = v.telefono
                    ? `<div class="info-taller-item"><strong>Tel:</strong> <a href="tel:${v.telefono}" onclick="event.stopPropagation()" style="color: #00d2ff; text-decoration: none;">${v.telefono}</a></div>`
                    : '';

                html += `
                    <div class="tarjeta-vehiculo-pendiente" onclick="usarPlaca('${v.vehiculo}')" title="Haz clic para usar esta placa">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span class="placa-badge">${v.vehiculo}</span>
                            <span style="font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; background: ${v.estado === 'Pendiente' ? 'rgba(240, 173, 78, 0.2)' : 'rgba(46, 133, 64, 0.2)'}; color: ${v.estado === 'Pendiente' ? '#ffe066' : '#a8f5b6'};">${v.estado}</span>
                        </div>
                        <div class="info-taller-item" style="margin-top: 6px;"><strong>Cliente:</strong> ${v.cliente || 'N/A'}</div>
                        ${infoVehiculo}
                        ${infoTelefono}
                        ${detalleExtra}
                    </div>
                `;
            });
            container.innerHTML = html;
        } else {
            container.innerHTML = html + `<p style="color: #a0a0a0; font-size: 0.9rem; text-align: center; margin: 20px 0;">No hay vehículos en la categoría '${filtroEstadoActual}'.</p>`;
        }
    } catch (e) {
        console.error("Error al cargar vehículos:", e);
    }
}

// Función auxiliar para copiar la placa al campo de texto del chat
function usarPlaca(placa) {
    const inputTexto = document.getElementById('texto_reporte');
    if (inputTexto) {
        inputTexto.value = placa + " "; 
        inputTexto.focus();
    }
}

function mostrarNotificacion(mensaje, tipo) {
    let cajaNotificacion = document.getElementById('caja-notificacion-ia');
    if (!cajaNotificacion) {
        cajaNotificacion = document.createElement('div');
        cajaNotificacion.id = 'caja-notificacion-ia';
        cajaNotificacion.style.marginTop = '20px';
        cajaNotificacion.style.padding = '15px 20px';
        cajaNotificacion.style.borderRadius = '10px';
        cajaNotificacion.style.fontFamily = 'sans-serif';
        cajaNotificacion.style.fontSize = '14px';
        cajaNotificacion.style.lineHeight = '1.6';
        cajaNotificacion.style.transition = 'all 0.3s ease';
        cajaNotificacion.style.display = 'block';
        cajaNotificacion.style.width = '100%';
        cajaNotificacion.style.boxSizing = 'border-box';

        const inputTexto = document.getElementById('texto_reporte');
        inputTexto.parentNode.insertBefore(cajaNotificacion, inputTexto.nextSibling);
    }

    if (tipo === "success") {
        cajaNotificacion.style.backgroundColor = 'rgba(46, 133, 64, 0.15)';
        cajaNotificacion.style.color = '#a8f5b6';
        cajaNotificacion.style.border = '1px solid rgba(46, 133, 64, 0.4)';
    } else if (tipo === "error") {
        cajaNotificacion.style.backgroundColor = 'rgba(217, 83, 79, 0.15)';
        cajaNotificacion.style.color = '#ff9999';
        cajaNotificacion.style.border = '1px solid rgba(217, 83, 79, 0.4)';
    } else if (tipo === "warning") {
        cajaNotificacion.style.backgroundColor = 'rgba(240, 173, 78, 0.15)';
        cajaNotificacion.style.color = '#ffe066';
        cajaNotificacion.style.border = '1px solid rgba(240, 173, 78, 0.4)';
    } else if (tipo === "info") {
        cajaNotificacion.style.backgroundColor = 'rgba(0, 191, 255, 0.1)';
        cajaNotificacion.style.color = '#e0f7ff';
        cajaNotificacion.style.border = '1px solid rgba(0, 191, 255, 0.3)';
        cajaNotificacion.style.boxShadow = '0 0 10px rgba(0, 191, 255, 0.1)';
    }

    cajaNotificacion.style.opacity = '1';

    if (tipo === "info" && mensaje.includes("Respuesta del Gerente IA")) {
        cajaNotificacion.innerHTML = marked.parse(mensaje);
    } else {
        cajaNotificacion.innerHTML = mensaje;
    }

    if (tipo === "success") {
        setTimeout(() => {
            cajaNotificacion.style.opacity = '0';
            setTimeout(() => { cajaNotificacion.innerHTML = ""; cajaNotificacion.style.padding = "0"; }, 300);
        }, 5000);
    }
}