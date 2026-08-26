// ==============================================================================
// Script del Taller Automotriz - Autotronic Solutions IA
// ==============================================================================

// Modo claro/oscuro (persistido en localStorage, aplicado también al cargar en index.html)
function alternarTema() {
    const raiz = document.documentElement;
    const temaActual = raiz.getAttribute("data-theme") || "dark";
    const nuevoTema = temaActual === "light" ? "dark" : "light";
    raiz.setAttribute("data-theme", nuevoTema);
    localStorage.setItem("as_tema", nuevoTema);
    actualizarIconoTema(nuevoTema);
}

function actualizarIconoTema(tema) {
    const icono = document.getElementById("icono-tema");
    const texto = document.getElementById("texto-tema");
    if (!icono || !texto) return;
    icono.innerText = tema === "dark" ? "☾" : "☀";
    texto.innerText = tema === "dark" ? "Oscuro" : "Claro";
}

// Bienvenida personalizada con el nombre del taller (definido por el admin)
async function cargarBienvenidaTaller() {
    const token = localStorage.getItem("taller_token");
    const banner = document.getElementById('banner-bienvenida');
    if (!token || !banner) return;

    try {
        const res = await fetch('/mi-taller', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) return;

        const data = await res.json();
        
        // ¡NUEVA LÍNEA! Guardamos el nombre para usarlo en la factura
        localStorage.setItem("nombre_taller_actual", data.nombre_taller); 
        
        banner.innerHTML = `¡Bienvenido, <span class="nombre-taller-destacado">${data.nombre_taller}</span>! Empecemos a trabajar`;
    } catch (e) {
        console.error("No se pudo cargar el nombre del taller:", e);
    }
}

// Validar sesión activa al cargar
// Validar sesión activa al cargar
window.onload = function() {
    actualizarIconoTema(document.documentElement.getAttribute("data-theme") || "dark");

    const token = localStorage.getItem("taller_token");
    if (token) {
        document.getElementById("login-container").style.display = "none";
        document.getElementById("app-container").style.display = "block";
        cargarVehiculosPendientes();
        cargarBienvenidaTaller();
        
        // Carga segura del ranking para móviles
        setTimeout(() => {
            cargarRankingAnual();
        }, 300);
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
            cargarBienvenidaTaller();
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

    const panelCaja = document.getElementById('panel-cuadre-caja');
    if (panelCaja) {
        panelCaja.innerHTML = "";
    }

    const banner = document.getElementById('banner-bienvenida');
    if (banner) {
        banner.innerHTML = "";
    }

    document.getElementById("texto_reporte").value = "";
}

// Función unificada: Envía reportes o consultas analíticas
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

        // INTERCEPTAMOS LA SOLICITUD DE ORDEN DE TRABAJO
        if (data.status === "imprimir_orden") {
            inputTexto.value = ""; 
            mostrarNotificacion(data.mensaje_bd, "success"); 
            generarImagenFactura(data.datos_orden);
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

// Descarga de inventario
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
        mostrarNotificacion("Error de conexion al descargar el inventario.", "error");
    }
}

// Descarga reporte diario
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
        mostrarNotificacion("Error de conexion al descargar el reporte.", "error");
    }
}

// Cuadre de caja del día (dashboard en pantalla, no descarga)
async function verCuadreDeCaja() {
    const token = localStorage.getItem("taller_token");
    const panel = document.getElementById('panel-cuadre-caja');
    if (!panel) return;

    panel.innerHTML = `<p style="color: #a0a0a0; text-align: center; margin: 20px 0;">Calculando cuadre de caja...</p>`;

    try {
        const response = await fetch('/reporte-dia', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            panel.innerHTML = "";
            mostrarNotificacion(errData.detail || "Error al calcular el cuadre de caja.", "warning");
            return;
        }

        const data = await response.json();
        renderizarCuadreDeCaja(data);
    } catch (error) {
        panel.innerHTML = "";
        mostrarNotificacion("Error de conexión al calcular el cuadre de caja.", "error");
    }
}

function renderizarCuadreDeCaja(data) {
    const panel = document.getElementById('panel-cuadre-caja');
    if (!panel) return;

    const claseNeto = data.neto > 0 ? 'monto-positivo' : (data.neto < 0 ? 'monto-negativo' : 'monto-neutro');

    let filasOrdenes = data.ordenes_cerradas.length > 0
        ? data.ordenes_cerradas.map(o => `
            <tr>
                <td>${o.vehiculo || '-'}</td>
                <td>${o.cliente || '-'}</td>
                <td>${o.oficial || 'Sin asignar'}</td>
                <td class="num">$${(o.cobro || 0).toFixed(2)}</td>
            </tr>`).join('')
        : `<tr><td colspan="4" class="vacio">Sin órdenes cerradas hoy.</td></tr>`;

    let filasEgresos = data.egresos.length > 0
        ? data.egresos.map(g => `
            <tr>
                <td>${g.motivo || '-'}</td>
                <td>${g.responsable || '-'}</td>
                <td class="num">$${(g.monto || 0).toFixed(2)}</td>
            </tr>`).join('')
        : `<tr><td colspan="3" class="vacio">Sin egresos registrados hoy.</td></tr>`;

   let filasTecnicos = data.rendimiento_tecnicos.length > 0
        ? data.rendimiento_tecnicos.map(t => `
            <tr>
                <td>${t.tecnico}</td>
                <td class="centro">${t.trabajos}</td>
                <td class="num">$${t.total_generado.toFixed(2)}</td>
                <td class="num" style="color: #4CAF50; font-weight: bold;">$${(t.comision_a_pagar || 0).toFixed(2)}</td>
            </tr>`).join('')
        : `<tr><td colspan="4" class="vacio">Sin datos de técnicos hoy.</td></tr>`;

    panel.innerHTML = `
        <div class="panel-caja">
            <h3>Cuadre de Caja — ${data.fecha}</h3>

            <div class="tarjetas-resumen-caja">
                <div class="tarjeta-resumen-caja">
                    <div class="etiqueta">Ingresos</div>
                    <div class="monto monto-positivo">$${data.total_ingresos.toFixed(2)}</div>
                </div>
                <div class="tarjeta-resumen-caja">
                    <div class="etiqueta">Egresos</div>
                    <div class="monto monto-negativo">$${data.total_egresos.toFixed(2)}</div>
                </div>
                <div class="tarjeta-resumen-caja">
                    <div class="etiqueta">Neto</div>
                    <div class="monto ${claseNeto}">$${data.neto.toFixed(2)}</div>
                </div>
            </div>

            <h4>Órdenes cerradas hoy (${data.ordenes_cerradas.length})</h4>
            <div class="tabla-scroll">
                <table class="tabla-caja">
                    <thead>
                        <tr>
                            <th>Placa</th>
                            <th>Cliente</th>
                            <th>Técnico</th>
                            <th style="text-align: right;">Cobro</th>
                        </tr>
                    </thead>
                    <tbody>${filasOrdenes}</tbody>
                </table>
            </div>

            <h4>Egresos de hoy (${data.egresos.length})</h4>
            <div class="tabla-scroll">
                <table class="tabla-caja">
                    <thead>
                        <tr>
                            <th>Motivo</th>
                            <th>Responsable</th>
                            <th style="text-align: right;">Monto</th>
                        </tr>
                    </thead>
                    <tbody>${filasEgresos}</tbody>
                </table>
            </div>

            <h4>Rendimiento por técnico</h4>
            <div class="tabla-scroll">
                <table class="tabla-caja">
                    <thead>
                        <tr>
                            <th>Técnico</th>
                            <th style="text-align: center;">Trabajos</th>
                            <th style="text-align: right;">Generado</th>
                            <th style="text-align: right;">Comisión</th>
                        </tr>
                    </thead>
                    <tbody>${filasTecnicos}</tbody>
                </table>
            </div>
        </div>
    `;
}

// ==============================================================================
// GESTIÓN DEL PANEL VISUAL DE VEHÍCULOS
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
        
        if (!response.ok) return;
        const data = await response.json();
        
        let container = document.getElementById('panel-vehiculos-pendientes-container') || document.getElementById('panel-vehiculos-pendientes');
        
        if (!container || container.id === 'panel-vehiculos-pendientes') {
            container = document.createElement('div');
            container.id = 'panel-vehiculos-pendientes';
            container.className = 'panel-pendientes';
            
            // Lo insertamos en el espacio dedicado entre las líneas divisorias
            const contenedorDestino = document.getElementById('panel-vehiculos-pendientes-container');
            if (contenedorDestino) {
                contenedorDestino.appendChild(container);
            } else {
                const app = document.getElementById('app-container');
                if (app) app.appendChild(container);
            }
        }

        const listaVehiculos = data.vehiculos || [];
        const vehiculosFiltrados = listaVehiculos.filter(v => v.estado === filtroEstadoActual);

        // NUEVA ESTRUCTURA HTML: Usando las clases limpias de CSS
        let html = `
            <div class="cabecera-panel-vehiculos">
                <h3>Control de Vehículos</h3>
                <div class="grupo-filtros">
                    <button class="btn-filtro ${filtroEstadoActual === 'Pendiente' ? 'activo' : ''}" onclick="cargarVehiculosPendientes('Pendiente')">Pendientes</button>
                    <button class="btn-filtro ${filtroEstadoActual === 'Terminado' ? 'activo' : ''}" onclick="cargarVehiculosPendientes('Terminado')">Terminados Hoy</button>
                </div>
            </div>
            <div class="grid-vehiculos">
        `;

        if (vehiculosFiltrados.length > 0) {
            vehiculosFiltrados.forEach(v => {
                // Detecta qué colores aplicar
                let claseEstado = v.estado === 'Pendiente' ? 'estado-pendiente' : 'estado-terminado';
                
                let detalleExtra = v.estado === 'Terminado' 
                    ? `<div class="info-cobro">✅ Cobro: $${v.cobro || 0} (${v.metodo_pago || 'Efectivo'})</div>` 
                    : `<div class="info-taller-item"><strong>Falla / Motivo:</strong> ${v.motivo || 'No especificado'}</div>`;

                const partesVehiculo = [v.modelo, v.color, v.anio, v.cilindraje ? `${v.cilindraje}cc` : ''].filter(Boolean);
                const infoVehiculo = partesVehiculo.length > 0
                    ? `<div class="info-taller-item"><strong>Vehículo:</strong> ${partesVehiculo.join(' · ')}</div>`
                    : '';

                const infoTelefono = v.telefono
                    ? `<div class="info-taller-item"><strong>Tel:</strong> <a href="tel:${v.telefono}" class="link-telefono" onclick="event.stopPropagation()">${v.telefono}</a></div>`
                    : '';

                // INYECCIÓN DEL BOTÓN DE DESCARGA PARA ORDENES TERMINADAS
                let botonDescarga = "";
                if (v.estado === "Terminado") {
                    const datosVehiculoStr = JSON.stringify(v).replace(/'/g, "&apos;").replace(/"/g, "&quot;");
                    botonDescarga = `
                        <button class="btn-filtro activo" style="margin-top: 15px; width: 100%; border:none; padding: 8px; border-radius: 8px; font-weight: 600; cursor: pointer;" 
                        onclick="event.stopPropagation(); generarComprobantePNG('${datosVehiculoStr}')">
                            📥 Descargar Orden
                        </button>
                    `;
                }

                html += `
                    <div class="tarjeta-vehiculo-pendiente" onclick="usarPlaca('${v.vehiculo}')" title="Haz clic para usar esta placa">
                        <div class="tarjeta-header">
                            <span class="placa-badge">${v.vehiculo}</span>
                            <span class="badge-estado ${claseEstado}">${v.estado}</span>
                        </div>
                        <div class="info-taller-item"><strong>Cliente:</strong> ${v.cliente || 'N/A'}</div>
                        ${infoVehiculo}
                        ${infoTelefono}
                        ${detalleExtra}
                        ${botonDescarga}
                    </div>
                `;
            });
            html += `</div>`; // Cierra el grid
            container.innerHTML = html;
        } else {
            container.innerHTML = html + `</div><p style="color: var(--texto-tenue); font-size: 0.9rem; text-align: center; margin: 20px 0; width: 100%;">No hay vehículos en la categoría '${filtroEstadoActual}'.</p>`;
        }
    } catch (e) {
        console.error("Error al cargar vehículos:", e);
    }
}

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
        cajaNotificacion.style.fontFamily = 'var(--fuente-datos)';
        cajaNotificacion.style.fontSize = '14px';
        cajaNotificacion.style.lineHeight = '1.6';
        cajaNotificacion.style.transition = 'all 0.3s ease';
        cajaNotificacion.style.display = 'block';
        cajaNotificacion.style.width = '100%';
        cajaNotificacion.style.boxSizing = 'border-box';

        const inputTexto = document.getElementById('texto_reporte');
        inputTexto.parentNode.insertBefore(cajaNotificacion, inputTexto.nextSibling);
    }

    cajaNotificacion.className = `mensaje-procesando-ia ${tipo}`;
    cajaNotificacion.style.opacity = '1';
    cajaNotificacion.style.padding = '15px 20px';
    cajaNotificacion.style.borderRadius = '10px';

    if (tipo === "info" && mensaje.includes("Respuesta del Gerente IA")) {
        if (typeof marked !== 'undefined') cajaNotificacion.innerHTML = marked.parse(mensaje);
        else cajaNotificacion.innerHTML = mensaje;
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

// ==========================================================================
// GENERADOR DE IMÁGENES (FICHAS DE SERVICIO)
// ==========================================================================
async function generarImagenFactura(orden) {
    // Inyectar el nombre del taller en el título
    const nombreTaller = localStorage.getItem("nombre_taller_actual") || "Orden de Servicio";
    const elTitulo = document.getElementById('orden-nombre-taller');
    if (elTitulo) elTitulo.innerText = nombreTaller;

    document.getElementById('orden-placa').innerText = orden.vehiculo || '---';
    document.getElementById('orden-cliente').innerText = orden.cliente || '---';
    
    const fecha = new Date(orden.fecha_hora);
    document.getElementById('orden-fecha').innerText = fecha.toLocaleDateString();
    
    document.getElementById('orden-tecnico').innerText = orden.oficial || 'No asignado';
    document.getElementById('orden-motivo').innerText = orden.motivo || '---';
    document.getElementById('orden-trabajo').innerText = orden.trabajo_realizado || '---';

    const tbody = document.getElementById('orden-repuestos-body');
    tbody.innerHTML = '';
    let totalRepuestos = 0;

    if (orden.reparacion_detalles && orden.reparacion_detalles.length > 0) {
        orden.reparacion_detalles.forEach(detalle => {
            const subtotal = detalle.cantidad * detalle.precio_unitario;
            totalRepuestos += subtotal;
            
            tbody.innerHTML += `
                <tr>
                    <td style="border: 1px solid #ddd; padding: 8px;">${detalle.repuestos?.codigo_producto || 'N/A'}</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">${detalle.repuestos?.nombre_repuesto || 'Genérico'}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">${detalle.cantidad}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">$${detalle.precio_unitario.toFixed(2)}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">$${subtotal.toFixed(2)}</td>
                </tr>
            `;
        });
    } else {
        tbody.innerHTML = `<tr><td colspan="5" style="border: 1px solid #ddd; padding: 8px; text-align: center;">No se registraron repuestos (Solo mano de obra)</td></tr>`;
    }

    const cobroManoObra = parseFloat(orden.cobro || 0);
    const totalFinal = totalRepuestos + cobroManoObra;
    document.getElementById('orden-total').innerText = totalFinal.toFixed(2);

    const plantilla = document.getElementById('plantilla-orden');
    plantilla.style.display = 'block'; 
    plantilla.style.position = 'absolute';
    plantilla.style.left = '-9999px';

    try {
        const canvas = await html2canvas(plantilla, { scale: 2 });
        const imgData = canvas.toDataURL('image/png');
        
        const enlaceDescarga = document.createElement('a');
        enlaceDescarga.href = imgData;
        enlaceDescarga.download = `Orden_Trabajo_${orden.vehiculo}.png`;
        enlaceDescarga.click();
        
        alert("Ficha de servicio descargada con éxito");
    } catch (error) {
        console.error("Error al generar la imagen:", error);
        alert("Hubo un error al crear la imagen");
    } finally {
        plantilla.style.display = 'none';
        plantilla.style.position = 'static';
    }
}

// ==============================================================================
// GENERADOR DE COMPROBANTES PNG
// ==============================================================================
async function generarComprobantePNG(vehiculoJson) {
    try {
        // Parsear si viene como string
        const reparacion = typeof vehiculoJson === 'string' ? JSON.parse(vehiculoJson) : vehiculoJson;

        // Inyectar el nombre del taller en el título
        const nombreTaller = localStorage.getItem("nombre_taller_actual") || "Orden de Servicio";
        const elTitulo = document.getElementById('orden-nombre-taller');
        if (elTitulo) elTitulo.innerText = nombreTaller;

        // 1. Llenar los datos en la plantilla HTML
        document.getElementById('orden-placa').innerText = reparacion.vehiculo || '---';
        document.getElementById('orden-cliente').innerText = reparacion.cliente || '---';
        
        // Formatear la fecha para que se vea limpia
        let fechaLimpia = reparacion.fecha_hora ? reparacion.fecha_hora.split('.')[0] : '---';
        document.getElementById('orden-fecha').innerText = fechaLimpia;
        
        document.getElementById('orden-tecnico').innerText = reparacion.oficial || 'No asignado';
        document.getElementById('orden-motivo').innerText = reparacion.motivo || 'No especificado';
        document.getElementById('orden-trabajo').innerText = reparacion.trabajo_realizado || 'No especificado';
        document.getElementById('orden-total').innerText = reparacion.cobro || '0.00';

        // 2. Preparar el contenedor para la foto (debe estar visible pero fuera de pantalla)
        const plantilla = document.getElementById('plantilla-orden');
        plantilla.style.display = 'block';
        plantilla.style.position = 'absolute';
        plantilla.style.top = '-9999px'; 
        plantilla.style.left = '-9999px';

        // 3. Tomar la "foto" con html2canvas
        const canvas = await html2canvas(plantilla, { 
            scale: 2, // Escala 2x para que el texto se vea nítido al hacer zoom
            backgroundColor: "#ffffff"
        });
        
        const imgData = canvas.toDataURL('image/png');

        // 4. Forzar la descarga
        const enlace = document.createElement('a');
        enlace.href = imgData;
        enlace.download = `Orden_Trabajo_${reparacion.vehiculo}.png`;
        document.body.appendChild(enlace);
        enlace.click();
        document.body.removeChild(enlace);

    } catch (error) {
        console.error("Error generando la orden:", error);
        alert("Hubo un error al generar la imagen del comprobante.");
    } finally {
        // 5. Volver a ocultar la plantilla para no dañar el diseño
        document.getElementById('plantilla-orden').style.display = 'none';
    }
}
// ==============================================================================
// REPORTE DE LIQUIDACIÓN QUINCENAL / PERSONALIZADA
// ==============================================================================
async function cargarLiquidacionFechas() {
    const token = localStorage.getItem("taller_token");
    const fechaInicio = document.getElementById('fechaInicioLiq').value;
    const fechaFin = document.getElementById('fechaFinLiq').value;
    const contenedorResultado = document.getElementById('resultado-liquidacion');

    if (!fechaInicio || !fechaFin) {
        mostrarNotificacion("Por favor selecciona ambas fechas para el corte de liquidación.", "warning");
        return;
    }

    if (fechaInicio > fechaFin) {
        mostrarNotificacion("La fecha de inicio no puede ser posterior a la fecha final.", "warning");
        return;
    }

    contenedorResultado.innerHTML = `<p style="color: #a0a0a0; text-align: center; margin: 20px 0;">Calculando liquidación del periodo...</p>`;

    try {
        const response = await fetch(`/reporte-liquidacion?fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            contenedorResultado.innerHTML = "";
            mostrarNotificacion(errData.detail || "Error al calcular la liquidación.", "warning");
            return;
        }

        const data = await response.json();
        renderizarLiquidacion(data);

    } catch (error) {
        contenedorResultado.innerHTML = "";
        mostrarNotificacion("Error de conexión al generar la liquidación.", "error");
    }
}

function renderizarLiquidacion(data) {
    const contenedor = document.getElementById('resultado-liquidacion');
    if (!contenedor) return;

    let filas = data.liquidacion_tecnicos.length > 0
        ? data.liquidacion_tecnicos.map(t => `
            <tr>
                <td>${t.tecnico}</td>
                <td class="centro">${t.trabajos_realizados}</td>
                <td class="num">$${t.facturacion_total.toFixed(2)}</td>
                <td class="num">$${t.mano_de_obra_acumulada.toFixed(2)}</td>
                <td class="num" style="color: #4CAF50; font-weight: bold;">$${t.comision_a_pagar.toFixed(2)}</td>
            </tr>`).join('')
        : `<tr><td colspan="5" class="vacio">No hay registros en este periodo.</td></tr>`;

    contenedor.innerHTML = `
        <h4 style="margin-top: 15px; margin-bottom: 10px;">Resultado: ${data.periodo}</h4>
        <div class="tabla-scroll">
            <table class="tabla-caja">
                <thead>
                    <tr>
                        <th>Técnico</th>
                        <th style="text-align: center;">Trabajos</th>
                        <th style="text-align: right;">Facturación Total</th>
                        <th style="text-align: right;">Mano de Obra (Neto)</th>
                        <th style="text-align: right;">Comisión a Pagar</th>
                    </tr>
                </thead>
                <tbody>${filas}</tbody>
            </table>
        </div>
    `;
}
// ==============================================================================
// LEADERBOARD / RANKING ANUAL EN VIVO
// ==============================================================================
async function cargarRankingAnual() {
    const token = localStorage.getItem("taller_token");
    const contenedor = document.getElementById('resultado-ranking-anual');
    if (!contenedor) return;

    contenedor.innerHTML = `<p style="color: var(--texto-tenue); text-align: center; font-size: 0.9rem; margin: 15px 0;">Cargando posiciones del año...</p>`;

    try {
        const response = await fetch('/ranking-anual', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) {
            contenedor.innerHTML = `<p style="color: #E0397A; text-align: center; font-size: 0.9rem;">Error al cargar el ranking anual.</p>`;
            return;
        }

        const data = await response.json();
        renderizarRankingAnual(data);

    } catch (error) {
        console.error("Error:", error);
        contenedor.innerHTML = `<p style="color: #E0397A; text-align: center; font-size: 0.9rem;">Error de conexión con el servidor.</p>`;
    }
}

function renderizarRankingAnual(data) {
    const contenedor = document.getElementById('resultado-ranking-anual');
    if (!contenedor) return;

    let filas = data.leaderboard && data.leaderboard.length > 0
        ? data.leaderboard.map(t => {
            let medalla = t.posicion === 1 ? '🥇 ' : (t.posicion === 2 ? '🥈 ' : (t.posicion === 3 ? '🥉 ' : ''));
            return `
                <tr>
                    <td style="font-weight: bold;">${medalla}#${t.posicion}</td>
                    <td>${t.tecnico}</td>
                    <td class="centro">${t.trabajos_totales}</td>
                    <td class="num">$${t.facturacion_anual.toFixed(2)}</td>
                    <td class="num">$${t.mano_de_obra_acumulada.toFixed(2)}</td>
                    <td class="num" style="color: var(--magenta); font-weight: bold;">$${t.comision_acumulada.toFixed(2)}</td>
                </tr>`;
        }).join('')
        : `<tr><td colspan="6" class="vacio">Aún no hay registros de técnicos este año.</td></tr>`;

    contenedor.innerHTML = `
        <div class="tabla-scroll">
            <table class="tabla-caja">
                <thead>
                    <tr>
                        <th>Pos</th>
                        <th>Técnico</th>
                        <th style="text-align: center;">Trabajos</th>
                        <th style="text-align: right;">Facturado (Total)</th>
                        <th style="text-align: right;">Mano de Obra (Neto)</th>
                        <th style="text-align: right;">Comisión Acumulada</th>
                    </tr>
                </thead>
                <tbody>${filas}</tbody>
            </table>
        </div>
    `;
}