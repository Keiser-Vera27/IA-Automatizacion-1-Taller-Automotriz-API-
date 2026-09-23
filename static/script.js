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

const ICONO_LUNA = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const ICONO_SOL = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>';

function actualizarIconoTema(tema) {
    const icono = document.getElementById("icono-tema");
    const texto = document.getElementById("texto-tema");
    if (!icono || !texto) return;
    // Íconos SVG (luna/sol) en lugar de caracteres especiales
    icono.innerHTML = tema === "dark" ? ICONO_LUNA : ICONO_SOL;
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
        
        // ¡NUEVA VALIDACIÓN! Si el servidor responde 401 (No autorizado/Caducado)
        if (res.status === 401) {
            cerrarSesion();
            mostrarNotificacion("Tu sesión ha caducado por seguridad. Por favor, inicia sesión nuevamente.", "warning");
            return;
        }

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
window.onload = function() {
    actualizarIconoTema(document.documentElement.getAttribute("data-theme") || "dark");

    const token = localStorage.getItem("taller_token");
    if (token) {
        document.getElementById("login-container").style.display = "none";
        document.getElementById("app-container").style.display = "block";
        
        // Al ejecutarse estas funciones, si el token expiró, la app se cerrará sola
        cargarVehiculosPendientes();
        cargarBienvenidaTaller();
        iniciarActualizacionCuadre();   // cuadre de caja siempre visible y en vivo
        
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
            iniciarActualizacionCuadre();   // cuadre de caja siempre visible y en vivo
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

    detenerActualizacionCuadre();   // no seguir consultando sin sesión
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

// Maneja la respuesta de /procesar-mensaje (envío normal o confirmación del modal)
async function manejarRespuestaRegistro(res, data, desdeModal) {
    const inputTexto = document.getElementById('texto_reporte');

    if (!res.ok) {
        const mensajeError = data.detail || "Error al procesar la solicitud en el servidor.";
        if (desdeModal) {
            mostrarModal({ tipo: 'error', titulo: 'No se pudo registrar', mensaje: escaparHTML(mensajeError) });
        } else {
            inputTexto.value = "";
            mostrarNotificacion(mensajeError, "warning");
        }
        return;
    }

    // Faltan datos obligatorios: NO se guardó nada, se piden en el modal
    if (data.status === "faltan_datos") {
        mostrarNotificacion("Faltan datos obligatorios: complétalos en la ventana para registrar la orden.", "warning");
        mostrarFormularioFaltantes(data);
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
        if (data.garantia) {
            mostrarModal({ tipo: data.garantia.vigente ? 'warning' : 'info', titulo: 'Orden registrada',
                           mensaje: avisoGarantiaHTML(data.garantia) });
        } else if (desdeModal) {
            mostrarModal({ tipo: 'success', titulo: 'Orden registrada',
                           mensaje: 'Los datos están completos. La orden se está guardando.' });
        }
        mostrarNotificacion(`${data.mensaje_bd}`, data.validado === false ? "warning" : "success");
        cargarVehiculosPendientes();
        refrescarCuadrePronto();   // el registro se procesa en segundo plano
    }
    else if (data.status === "éxito_consulta") {
        inputTexto.value = "";
        mostrarNotificacion(`<b>Respuesta del Gerente IA:</b><br>${data.mensaje_bd}`, "info");
    }
    else {
        inputTexto.value = "";
        mostrarNotificacion(`Error del sistema: ${data.mensaje || "Desconocido"}`, "error");
    }
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

        const data = await res.json().catch(() => ({}));
        await manejarRespuestaRegistro(res, data, false);

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

// Descarga la plantilla oficial de inventario (encabezados correctos,
// validaciones y hoja de instrucciones) generada por el backend.
async function descargarPlantillaInventario() {
    const token = localStorage.getItem("taller_token");
    try {
        const response = await fetch('/plantilla-inventario', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            mostrarModal({
                tipo: 'error',
                titulo: 'No se pudo descargar la plantilla',
                mensaje: escaparHTML(errData.detail || `El servidor respondió con el código ${response.status}.`)
            });
            return;
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'Plantilla_Inventario.xlsx';
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    } catch (error) {
        mostrarModal({
            tipo: 'error',
            titulo: 'Error de conexión',
            mensaje: 'No se pudo descargar la plantilla. Revisa tu internet e inténtalo de nuevo.'
        });
    }
}

// Importación masiva de inventario (abre el selector de archivo)
function abrirSelectorInventario() {
    document.getElementById('input-excel-inventario').click();
}

// ==============================================================================
// MODAL DE AVISO REUTILIZABLE (centro de pantalla + botón OK)
// Uso: mostrarModal({ tipo: 'success'|'warning'|'error'|'info', titulo, mensaje, detalles: [] })
//      mostrarModal({ cargando: true, titulo, mensaje })  -> sin botón, con spinner
// ==============================================================================
const ICONOS_MODAL = {
    success: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>',
    warning: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="14"/><line x1="12" y1="19" x2="12.01" y2="19"/></svg>',
    error:   '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    info:    '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="11" x2="12" y2="16"/><line x1="12" y1="7.5" x2="12.01" y2="7.5"/></svg>'
};

function escaparHTML(texto) {
    const div = document.createElement('div');
    div.textContent = String(texto);
    return div.innerHTML;
}

function mostrarModal({ tipo = 'info', titulo = '', mensaje = '', detalles = [], cargando = false } = {}) {
    const overlay = document.getElementById('modal-aviso');
    if (!overlay) { mostrarNotificacion(mensaje, tipo); return; }  // respaldo

    const icono = document.getElementById('modal-icono');
    icono.className = `modal-icono ${cargando ? 'info cargando' : tipo}`;
    icono.innerHTML = cargando ? '' : (ICONOS_MODAL[tipo] || ICONOS_MODAL.info);

    document.getElementById('modal-titulo').textContent = titulo;
    document.getElementById('modal-mensaje').innerHTML = mensaje;  // mensaje ya viene escapado

    // Lista de detalles (ej. filas con error). Máximo 10 visibles.
    const lista = document.getElementById('modal-detalles');
    if (detalles.length > 0) {
        let items = detalles.slice(0, 10).map(d => `<li>${escaparHTML(d)}</li>`).join('');
        if (detalles.length > 10) items += `<li>... y ${detalles.length - 10} más</li>`;
        lista.innerHTML = items;
        lista.classList.add('visible');
    } else {
        lista.innerHTML = '';
        lista.classList.remove('visible');
    }

    // Modo aviso: sin formulario ni botón Cancelar, OK solo cierra
    const formulario = document.getElementById('modal-formulario');
    if (formulario) { formulario.hidden = true; formulario.innerHTML = ''; }
    const btnCancelar = document.getElementById('modal-btn-cancelar');
    if (btnCancelar) btnCancelar.hidden = true;
    overlay.dataset.modo = '';

    // Mientras carga no se puede cerrar (no hay botón OK)
    const btnOk = document.getElementById('modal-btn-ok');
    btnOk.textContent = 'OK';
    btnOk.disabled = false;
    btnOk.onclick = cerrarModal;
    btnOk.hidden = cargando;
    overlay.dataset.bloqueado = cargando ? '1' : '';

    overlay.classList.add('visible');
    overlay.setAttribute('aria-hidden', 'false');
    if (!cargando) btnOk.focus();
}

function cerrarModal() {
    const overlay = document.getElementById('modal-aviso');
    if (!overlay || overlay.dataset.bloqueado) return;
    overlay.classList.remove('visible');
    overlay.setAttribute('aria-hidden', 'true');
}

// Teclado: en modo aviso, Escape/Enter cierran. En modo formulario, Enter
// envía y Escape cancela (así no se cierra por accidente al escribir).
document.addEventListener('keydown', (e) => {
    const overlay = document.getElementById('modal-aviso');
    if (!overlay || !overlay.classList.contains('visible')) return;
    if (overlay.dataset.modo === 'formulario') {
        if (e.key === 'Escape') { e.preventDefault(); document.getElementById('modal-btn-cancelar').click(); }
        else if (e.key === 'Enter' && e.target.tagName !== 'SELECT' && e.target.tagName !== 'TEXTAREA') { e.preventDefault(); document.getElementById('modal-btn-ok').click(); }
        return;
    }
    if (e.key === 'Escape' || e.key === 'Enter') { e.preventDefault(); cerrarModal(); }
});

// ==============================================================================
// ORDEN DE TRABAJO CON DATOS FALTANTES: modal para completarlos
// El backend NO guarda nada hasta que estén todos los datos obligatorios.
// ==============================================================================
const BANCOS_SUGERIDOS = ['Pichincha', 'Guayaquil', 'Produbanco', 'Pacífico', 'Bolivariano',
                          'Internacional', 'Austro', 'Loja', 'Machala', 'JEP', 'Jardín Azuayo'];
const EJEMPLOS_CAMPO = {
    vehiculo: 'Ej. PXY9876', modelo: 'Ej. Chevrolet Sail', kilometraje: 'Ej. 85400', cliente: 'Ej. Juan Pérez',
    cedula: 'Ej. 0912345678', telefono: 'Ej. 0991234567', motivo: 'Ej. Ruido en la suspensión delantera',
    trabajo_realizado: 'Ej. Cambio de pastillas delanteras y rectificación de discos',
    banco: 'Ej. Pichincha'
};

// Arma el HTML de un campo según su tipo (técnico y método de pago son listas)
function campoFaltanteHTML(f, tecnicos) {
    const e = escaparHTML;
    const error = f.problema && f.problema !== 'falta'
        ? `<span class="campo-error">${e(f.problema)}</span>` : '';
    let control;
    if (f.campo === 'oficial') {
        control = tecnicos.length
            ? `<select name="oficial" required>
                   <option value="">Selecciona el técnico...</option>
                   ${tecnicos.map(t => `<option value="${e(t)}">${e(t)}</option>`).join('')}
               </select>`
            : `<div class="campo-error">No hay técnicos registrados en este taller. Pide al administrador que los registre para poder asignar órdenes.</div>`;
    } else if (f.campo === 'metodo_pago') {
        control = `<select name="metodo_pago" required onchange="alternarCampoBanco(this)">
                       <option value="">Selecciona...</option>
                       <option>Efectivo</option><option>Transferencia</option><option>Tarjeta</option>
                   </select>
                   <div class="campo-banco" hidden>
                       <input name="banco" list="lista-bancos" placeholder="Banco de la transferencia (ej. Pichincha)" autocomplete="off">
                   </div>`;
    } else {
        const extra = ['cedula', 'telefono', 'kilometraje'].includes(f.campo) ? 'inputmode="numeric"' : '';
        const lista = f.campo === 'banco' ? 'list="lista-bancos"' : '';
        control = `<input name="${e(f.campo)}" value="${e(f.valor || '')}" placeholder="${e(EJEMPLOS_CAMPO[f.campo] || '')}"
                          autocomplete="off" required ${extra} ${lista}>`;
    }
    return `<label class="campo-faltante">
                <span class="campo-etiqueta">${e(f.etiqueta)} ${error}</span>
                ${control}
                <span class="campo-aviso" hidden>Este dato es obligatorio</span>
            </label>`;
}

// Muestra el campo "banco" solo cuando el pago es por transferencia
function alternarCampoBanco(select) {
    const caja = select.parentElement.querySelector('.campo-banco');
    if (caja) caja.hidden = select.value !== 'Transferencia';
}

// Muestra el modal con SOLO los datos que faltan o son inválidos
function mostrarFormularioFaltantes(data) {
    const overlay = document.getElementById('modal-aviso');
    const e = escaparHTML;
    const ctx = data.contexto || {};
    const tecnicos = data.tecnicos || [];

    mostrarModal({ tipo: 'warning', titulo: 'Faltan datos obligatorios' });  // base visual
    overlay.dataset.modo = 'formulario';

    const tipoOrden = ctx.es_cierre ? 'Cierre de trabajo' : 'Ingreso al taller';
    const resumen = [ctx.placa && ctx.placa !== 'S/C' ? `<b>${e(ctx.placa)}</b>` : '',
                     ctx.modelo ? e(ctx.modelo) : '', ctx.cliente ? e(ctx.cliente) : '']
                    .filter(Boolean).join(' · ');
    document.getElementById('modal-mensaje').innerHTML =
        `<div class="resumen-orden">${tipoOrden}${resumen ? ': ' + resumen : ''}</div>
         ${avisoGarantiaHTML(ctx.garantia)}
         Completa estos datos para registrar la orden. <b>No se guardó nada todavía.</b>`;

    const formulario = document.getElementById('modal-formulario');
    formulario.innerHTML = (data.faltantes || []).map(f => campoFaltanteHTML(f, tecnicos)).join('')
        + `<datalist id="lista-bancos">${BANCOS_SUGERIDOS.map(b => `<option value="${e(b)}">`).join('')}</datalist>`;
    formulario.hidden = false;

    const btnCancelar = document.getElementById('modal-btn-cancelar');
    btnCancelar.hidden = false;
    btnCancelar.onclick = () => {
        overlay.dataset.modo = '';
        cerrarModal();
        mostrarNotificacion("Registro cancelado: no se guardó la orden. Tu mensaje sigue en el cuadro de texto.", "warning");
    };

    const btnOk = document.getElementById('modal-btn-ok');
    btnOk.textContent = 'Registrar orden';
    btnOk.disabled = (data.faltantes || []).some(f => f.campo === 'oficial') && !tecnicos.length;
    btnOk.onclick = () => confirmarDatosFaltantes(data.borrador);

    const primero = formulario.querySelector('input, select');
    if (primero) setTimeout(() => primero.focus(), 50);
}

// ==============================================================================
// CERRAR ORDEN SIN COBRO (botón "Cerrar orden" en la tarjeta del vehículo)
// ==============================================================================
let motivosCierreCache = null;

async function obtenerMotivosCierre() {
    if (motivosCierreCache) return motivosCierreCache;
    const res = await fetch('/motivos-cierre', { headers: { 'Authorization': `Bearer ${localStorage.getItem("taller_token")}` } });
    if (!res.ok) throw new Error('motivos');
    motivosCierreCache = (await res.json()).motivos || [];
    return motivosCierreCache;
}

// Abre el modal con la lista de motivos. 'boton' trae id, placa y cliente en data-*
async function abrirCerrarOrden(boton) {
    const { id, placa, cliente } = boton.dataset;
    const e = escaparHTML;
    let motivos;
    try {
        motivos = await obtenerMotivosCierre();
    } catch (err) {
        mostrarModal({ tipo: 'error', titulo: 'No se pudo abrir', mensaje: 'No se pudieron cargar los motivos de cierre. Revisa tu conexión.' });
        return;
    }

    const overlay = document.getElementById('modal-aviso');
    mostrarModal({ tipo: 'info', titulo: 'Cerrar orden sin cobro' });
    overlay.dataset.modo = 'formulario';

    document.getElementById('modal-mensaje').innerHTML =
        `<div class="resumen-orden"><b>${e(placa)}</b>${cliente ? ' · ' + e(cliente) : ''} · Orden N° ${e(id)}</div>
         El vehículo sale del taller <b>sin registrar ningún cobro</b>.
         <div class="nota-cierre">Si se cobró algo (aunque sea un diagnóstico), no uses esta opción: regístralo por el chat como un trabajo terminado.</div>`;

    const formulario = document.getElementById('modal-formulario');
    formulario.innerHTML = `
        <label class="campo-faltante">
            <span class="campo-etiqueta">Motivo del cierre</span>
            <select name="motivo" required onchange="ajustarDetalleCierre(this)">
                <option value="">Selecciona el motivo...</option>
                ${motivos.map(m => `<option value="${e(m.clave)}" data-obligatorio="${m.detalle_obligatorio ? 1 : 0}">${e(m.texto)}</option>`).join('')}
            </select>
            <span class="campo-aviso" hidden>Este dato es obligatorio</span>
        </label>
        <label class="campo-faltante">
            <span class="campo-etiqueta" id="etiqueta-detalle-cierre">Detalle (opcional)</span>
            <textarea name="detalle" placeholder="Ej. El cliente volverá cuando tenga el presupuesto"></textarea>
            <span class="campo-aviso" hidden>Este dato es obligatorio</span>
        </label>
        <div id="bloque-garantia-cierre" class="bloque-garantia-cierre" hidden data-orden="${e(id)}"></div>`;
    formulario.hidden = false;

    const btnCancelar = document.getElementById('modal-btn-cancelar');
    btnCancelar.hidden = false;
    btnCancelar.onclick = () => { overlay.dataset.modo = ''; cerrarModal(); };

    const btnOk = document.getElementById('modal-btn-ok');
    btnOk.textContent = 'Cerrar orden';
    btnOk.onclick = () => confirmarCerrarOrden(id, placa);
    setTimeout(() => formulario.querySelector('select').focus(), 50);
}

// Cambia la etiqueta/placeholder del detalle según el motivo elegido
function ajustarDetalleCierre(select) {
    const opcion = select.selectedOptions[0];
    const obligatorio = opcion && opcion.dataset.obligatorio === '1';
    const textarea = document.querySelector('#modal-formulario textarea[name="detalle"]');
    const etiqueta = document.getElementById('etiqueta-detalle-cierre');
    textarea.required = obligatorio;
    const bloque = document.getElementById('bloque-garantia-cierre');
    if (bloque) {
        bloque.hidden = select.value !== 'garantia';
        if (select.value === 'garantia' && !bloque.dataset.cargado) cargarBloqueGarantiaCierre(bloque);
    }
    if (select.value === 'garantia') {
        etiqueta.textContent = '¿Qué se hizo bajo garantía?';
        textarea.placeholder = 'Ej. Se reajustó el embrague cambiado en la orden N° 1520';
    } else if (select.value === 'otro') {
        etiqueta.textContent = 'Describe el motivo';
        textarea.placeholder = 'Ej. El cliente retiró el vehículo sin autorizar el trabajo';
    } else {
        etiqueta.textContent = 'Detalle (opcional)';
        textarea.placeholder = 'Ej. El cliente volverá cuando tenga el presupuesto';
    }
}

// ==============================================================================
// GARANTÍAS — ETAPA 2
// ==============================================================================

// Al cerrar por "Se cubre garantía": elegir la orden original, la causa y el costo
async function cargarBloqueGarantiaCierre(bloque) {
    const e = escaparHTML;
    bloque.innerHTML = `<p class="nota-cierre">Buscando trabajos anteriores del vehículo...</p>`;
    let ordenes = [];
    try {
        const res = await fetch(`/reparaciones/${encodeURIComponent(bloque.dataset.orden)}/ordenes-previas`, { headers: cabeceraAuth() });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
        ordenes = data.ordenes || [];
    } catch (err) {
        bloque.innerHTML = `<p class="campo-error">No se pudieron cargar los trabajos anteriores: ${e(err.message)}</p>`;
        return;
    }
    bloque.dataset.cargado = '1';
    bloque._ordenes = ordenes;

    if (!ordenes.length) {
        bloque.innerHTML = `<p class="campo-error">Este vehículo no tiene trabajos terminados anteriores en el taller, así que no hay una garantía que cubrir. Usa otro motivo de cierre.</p>`;
        return;
    }
    // Se preselecciona el trabajo con garantía vigente más reciente
    const sugerida = ordenes.find(o => o.garantia_vigente) || ordenes[0];
    const etiquetaOrden = o => {
        const estado = o.garantia_vigente ? 'garantía vigente'
            : (o.garantia_vence ? `garantía vencida ${o.garantia_motivo_vencida}` : 'sin garantía registrada');
        return `N° ${o.id} · ${o.fecha} · ${o.trabajo || 'trabajo'} (${o.tecnico || 'sin técnico'}) — ${estado}`;
    };
    bloque.innerHTML = `
        <label class="campo-faltante">
            <span class="campo-etiqueta">Trabajo original que cubre la garantía</span>
            <select name="orden_origen_id" required onchange="ajustarProveedorGarantia()">
                ${ordenes.map(o => `<option value="${e(String(o.id))}" ${o === sugerida ? 'selected' : ''}>${e(etiquetaOrden(o))}</option>`).join('')}
            </select>
            <span class="campo-aviso" hidden>Este dato es obligatorio</span>
        </label>
        <label class="campo-faltante">
            <span class="campo-etiqueta">¿Por qué falló?</span>
            <select name="causa" required onchange="ajustarProveedorGarantia()">
                <option value="">Selecciona la causa...</option>
                <option value="mano_obra">Falla de mano de obra</option>
                <option value="repuesto">Falla del repuesto</option>
                <option value="otra">Otra causa</option>
            </select>
            <span class="campo-aviso" hidden>Este dato es obligatorio</span>
        </label>
        <label class="campo-faltante" id="campo-proveedor-garantia" hidden>
            <span class="campo-etiqueta">Proveedor del repuesto (se registra un reclamo pendiente)</span>
            <input name="proveedor" list="lista-proveedores-garantia" placeholder="Ej. Importadora Andina" autocomplete="off">
            <datalist id="lista-proveedores-garantia"></datalist>
            <span class="campo-aviso" hidden>Este dato es obligatorio</span>
        </label>
        <label class="campo-faltante">
            <span class="campo-etiqueta">Costo para el taller ($) — repuestos y materiales usados</span>
            <input name="costo" type="number" min="0" step="0.01" inputmode="decimal" placeholder="0.00">
        </label>`;
    ajustarProveedorGarantia();
}

// Muestra/rellena el proveedor cuando la causa es "Falla del repuesto"
function ajustarProveedorGarantia() {
    const bloque = document.getElementById('bloque-garantia-cierre');
    if (!bloque || !bloque._ordenes) return;
    const causa = bloque.querySelector('[name=causa]').value;
    const campo = document.getElementById('campo-proveedor-garantia');
    const input = campo.querySelector('input');
    campo.hidden = causa !== 'repuesto';
    input.required = causa === 'repuesto';

    const orden = bloque._ordenes.find(o => String(o.id) === bloque.querySelector('[name=orden_origen_id]').value);
    const proveedores = [...new Set((orden?.repuestos || []).map(r => r.proveedor).filter(p => p && p !== 'General'))];
    document.getElementById('lista-proveedores-garantia').innerHTML = proveedores.map(p => `<option value="${escaparHTML(p)}">`).join('');
    if (!input.value && proveedores.length === 1) input.value = proveedores[0];
}

// ---------------------------- Vista "Garantías" ----------------------------
function iniciarVistaGarantias() {
    const hoy = new Date();
    const desde = new Date(hoy.getTime() - 90 * 86400000);
    const iso = d => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const inDesde = document.getElementById('garantias-desde');
    const inHasta = document.getElementById('garantias-hasta');
    if (!inDesde.value) inDesde.value = iso(desde);
    if (!inHasta.value) inHasta.value = iso(hoy);
    cargarReporteGarantias();
}

async function cargarReporteGarantias() {
    const cont = document.getElementById('resultado-garantias');
    const e = escaparHTML;
    const desde = document.getElementById('garantias-desde').value;
    const hasta = document.getElementById('garantias-hasta').value;
    cont.innerHTML = `<p class="caja-cargando">Cargando reporte de garantías...</p>`;
    let d;
    try {
        const res = await fetch(`/reporte-garantias?desde=${encodeURIComponent(desde)}&hasta=${encodeURIComponent(hasta)}`, { headers: cabeceraAuth() });
        d = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(d.detail || `Error ${res.status}`);
    } catch (err) {
        cont.innerHTML = `<p class="campo-error">No se pudo cargar el reporte: ${e(err.message)}</p>`;
        return;
    }
    const r = d.resumen;
    const pct = v => v === null || v === undefined ? '—' : `${v}%`;
    const tabla = (cabeceras, filas, vacio) => `
        <div class="tabla-scroll"><table class="tabla-caja">
            <thead><tr>${cabeceras.map(([t, al]) => `<th style="text-align:${al || 'left'}">${t}</th>`).join('')}</tr></thead>
            <tbody>${filas.length ? filas.join('') : `<tr><td colspan="${cabeceras.length}" class="vacio">${vacio}</td></tr>`}</tbody>
        </table></div>`;

    const filasTec = d.por_tecnico.map(t => `<tr>
        <td>${e(t.tecnico)}</td><td class="centro">${t.entregadas}</td><td class="centro">${t.reclamos}</td>
        <td class="num ${t.tasa >= 10 ? 'monto-negativo' : ''}">${pct(t.tasa)}</td><td class="num">${dinero(t.costo)}</td></tr>`);
    const filasSrv = d.por_servicio.map(s => `<tr>
        <td>${e(s.servicio)}</td><td class="centro">${s.entregadas}</td><td class="centro">${s.reclamos}</td>
        <td class="num">${pct(s.tasa)}</td><td class="num">${dinero(s.costo)}</td></tr>`);
    const filasCausa = d.por_causa.map(c => `<tr><td>${e(c.causa)}</td><td class="centro">${c.reclamos}</td><td class="num">${dinero(c.costo)}</td></tr>`);
    const filasRep = d.por_repuesto.map(p => `<tr><td>${e(p.codigo || '-')}</td><td>${e(p.nombre)}</td><td>${e(p.proveedor || '-')}</td><td class="centro">${p.reclamos}</td></tr>`);
    const filasProv = d.reclamos_proveedor.map(p => `<tr>
        <td>${e(p.fecha)}</td><td><b>${e(p.vehiculo)}</b><div class="sub">orden N° ${e(String(p.orden_origen))}</div></td>
        <td>${e(p.repuestos)}</td><td>${e(p.proveedor)}</td><td class="num">${dinero(p.costo)}</td>
        <td><span class="estado-reclamo ${e(p.estado.toLowerCase())}">${e(p.estado)}</span>${p.estado === 'Aprobado' ? `<div class="sub">recuperado ${dinero(p.recuperado)}</div>` : ''}</td>
        <td class="centro">${p.estado === 'Pendiente'
            ? `<button class="btn-link" onclick='resolverReclamoProveedor(${JSON.stringify(String(p.id))}, "Aprobado", ${p.costo})'>Aprobado</button>
               <button class="btn-link" onclick='resolverReclamoProveedor(${JSON.stringify(String(p.id))}, "Rechazado", 0)'>Rechazado</button>`
            : `<button class="btn-link" onclick='resolverReclamoProveedor(${JSON.stringify(String(p.id))}, "Pendiente", 0)'>Reabrir</button>`}</td></tr>`);
    const filasDet = d.detalle.map(x => `<tr>
        <td>${e(x.fecha)}</td><td><b>${e(x.vehiculo)}</b><div class="sub">${e(x.cliente)}</div></td>
        <td>${e(x.trabajo_original)}<div class="sub">orden N° ${e(String(x.orden_origen))}</div></td>
        <td>${e(x.tecnico)}</td><td>${e(x.causa)}</td><td class="celda-trabajo" title="${e(x.detalle)}">${e(x.detalle || '-')}</td>
        <td class="num">${dinero(x.costo)}</td></tr>`);

    cont.innerHTML = `
        <div class="tarjetas-resumen-caja">
            <div class="tarjeta-resumen-caja"><div class="etiqueta">Garantías entregadas</div><div class="monto monto-neutro">${r.entregadas}</div></div>
            <div class="tarjeta-resumen-caja"><div class="etiqueta">Reclamos atendidos</div><div class="monto ${r.reclamos ? 'monto-negativo' : 'monto-neutro'}">${r.reclamos}</div></div>
            <div class="tarjeta-resumen-caja"><div class="etiqueta">Tasa de retorno</div><div class="monto monto-neutro">${pct(r.tasa_retorno)}</div></div>
            <div class="tarjeta-resumen-caja"><div class="etiqueta">Costo neto para el taller</div><div class="monto monto-negativo">${dinero(r.costo_neto)}</div></div>
        </div>
        <div class="linea-detalle">Costo de reclamos <b>${dinero(r.costo_total)}</b> · Recuperado de proveedores <b>${dinero(r.recuperado_proveedores)}</b>
            ${r.reclamos_proveedor_pendientes ? ` · <b>${r.reclamos_proveedor_pendientes}</b> reclamo(s) a proveedores pendientes` : ''}</div>

        <h4>Por técnico</h4>
        <p class="nota-cierre">La tasa de retorno compara los reclamos con las garantías que ese técnico entregó en el mismo período.</p>
        ${tabla([['Técnico'], ['Entregadas', 'center'], ['Reclamos', 'center'], ['Tasa', 'right'], ['Costo', 'right']], filasTec, 'Sin trabajos con garantía en el período.')}

        <div class="grid-caja">
            <div><h4>Servicios con más reclamos</h4>
                ${tabla([['Servicio'], ['Entregadas', 'center'], ['Reclamos', 'center'], ['Tasa', 'right'], ['Costo', 'right']], filasSrv, 'Sin reclamos en el período.')}</div>
            <div><h4>Por causa</h4>
                ${tabla([['Causa'], ['Reclamos', 'center'], ['Costo', 'right']], filasCausa, '')}</div>
        </div>

        <h4>Repuestos que fallaron</h4>
        ${tabla([['Código'], ['Repuesto'], ['Proveedor'], ['Reclamos', 'center']], filasRep, 'Ningún reclamo por falla de repuesto en el período.')}

        <h4>Reclamos a proveedores</h4>
        <p class="nota-cierre">Se muestran los del período y todos los pendientes. Cuando el proveedor responda, márcalo aquí.</p>
        ${tabla([['Fecha'], ['Placa'], ['Repuestos'], ['Proveedor'], ['Costo', 'right'], ['Estado'], ['Acción', 'center']], filasProv, 'No hay reclamos a proveedores.')}

        <h4>Detalle de reclamos (${d.detalle.length})</h4>
        ${tabla([['Fecha'], ['Placa'], ['Trabajo original'], ['Técnico'], ['Causa'], ['Qué se hizo'], ['Costo', 'right']], filasDet, 'Sin reclamos de garantía en el período.')}`;
}

// Registra la respuesta del proveedor a un reclamo
function resolverReclamoProveedor(id, estado, montoSugerido) {
    const enviar = async (monto) => {
        const res = await fetch(`/reparaciones/${encodeURIComponent(id)}/reclamo-proveedor`, {
            method: 'PATCH', headers: cabeceraAuth(true), body: JSON.stringify({ estado, monto })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) { mostrarModal({ tipo: 'error', titulo: 'No se pudo actualizar', mensaje: escaparHTML(data.detail || `Error ${res.status}`) }); return; }
        const overlay = document.getElementById('modal-aviso'); overlay.dataset.modo = ''; cerrarModal();
        cargarReporteGarantias();
    };
    if (estado !== 'Aprobado') { enviar(0); return; }

    // Aprobado: preguntar cuánto devolvió o abonó el proveedor
    const overlay = document.getElementById('modal-aviso');
    mostrarModal({ tipo: 'success', titulo: 'Reclamo aprobado' });
    overlay.dataset.modo = 'formulario';
    document.getElementById('modal-mensaje').innerHTML = '¿Cuánto devolvió o abonó el proveedor? (reposición del repuesto o nota de crédito)';
    const formulario = document.getElementById('modal-formulario');
    formulario.innerHTML = `<label class="campo-faltante"><span class="campo-etiqueta">Monto recuperado ($)</span>
        <input name="monto" type="number" min="0" step="0.01" inputmode="decimal" value="${Number(montoSugerido || 0).toFixed(2)}"></label>`;
    formulario.hidden = false;
    const btnCancelar = document.getElementById('modal-btn-cancelar');
    btnCancelar.hidden = false;
    btnCancelar.onclick = () => { overlay.dataset.modo = ''; cerrarModal(); };
    const btnOk = document.getElementById('modal-btn-ok');
    btnOk.textContent = 'Guardar';
    btnOk.onclick = () => enviar(Math.max(0, parseFloat(formulario.querySelector('[name=monto]').value || '0') || 0));
}

async function confirmarCerrarOrden(id, placa) {
    const formulario = document.getElementById('modal-formulario');
    const motivo = formulario.querySelector('select[name="motivo"]');
    const detalle = formulario.querySelector('textarea[name="detalle"]');
    let completo = true;
    const extra = motivo.value === 'garantia'
        ? [...formulario.querySelectorAll('#bloque-garantia-cierre [name]')] : [];
    // Con motivo "garantía" debe existir una orden original para elegir
    if (motivo.value === 'garantia' && !formulario.querySelector('[name=orden_origen_id]')) return;
    [motivo, detalle, ...extra].forEach(ctrl => {
        if (!ctrl.closest('.campo-faltante')) return;
        const falta = ctrl.required && !ctrl.closest('[hidden]') && ctrl.value.trim().length < (ctrl.tagName === 'TEXTAREA' ? 3 : 1);
        ctrl.classList.toggle('invalido', falta);
        const aviso = ctrl.closest('.campo-faltante').querySelector('.campo-aviso');
        if (aviso) aviso.hidden = !falta;
        if (falta) completo = false;
    });
    if (!completo) return;

    const btnOk = document.getElementById('modal-btn-ok');
    btnOk.disabled = true;
    btnOk.textContent = 'Cerrando...';
    try {
        const res = await fetch(`/reparaciones/${encodeURIComponent(id)}/cerrar-sin-cobro`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem("taller_token")}` },
            body: JSON.stringify(Object.assign(
                { motivo: motivo.value, detalle: detalle.value.trim() },
                motivo.value === 'garantia' ? {
                    orden_origen_id: formulario.querySelector('[name=orden_origen_id]')?.value || null,
                    causa: formulario.querySelector('[name=causa]')?.value || null,
                    costo: parseFloat(formulario.querySelector('[name=costo]')?.value || '0') || 0,
                    proveedor: formulario.querySelector('[name=proveedor]')?.value.trim() || ''
                } : {}))
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            mostrarModal({ tipo: 'error', titulo: 'No se pudo cerrar la orden', mensaje: escaparHTML(data.detail || `Error ${res.status}`) });
            return;
        }
        mostrarModal({ tipo: 'success', titulo: 'Orden cerrada',
                       mensaje: `<b>${escaparHTML(placa)}</b> se cerró sin cobro. Motivo: ${escaparHTML(data.motivo || '')}.` });
        cargarVehiculosPendientes(typeof filtroEstadoActual !== 'undefined' ? filtroEstadoActual : 'Pendiente');
        cargarCuadreCaja(true);
    } catch (err) {
        btnOk.disabled = false;
        btnOk.textContent = 'Cerrar orden';
        mostrarNotificacion("Error de conexión al cerrar la orden. Inténtalo de nuevo.", "error");
    }
}

// Valida en pantalla y reenvía al backend junto con el borrador firmado
async function confirmarDatosFaltantes(borrador) {
    const formulario = document.getElementById('modal-formulario');
    const datos = {};
    let completo = true;

    formulario.querySelectorAll('input[name], select[name]').forEach(ctrl => {
        const visible = !ctrl.closest('[hidden]');
        const valor = ctrl.value.trim();
        const aviso = ctrl.closest('.campo-faltante').querySelector('.campo-aviso');
        const obligatorio = ctrl.required || (ctrl.name === 'banco' && visible);
        const falta = visible && obligatorio && !valor;
        ctrl.classList.toggle('invalido', falta);
        if (aviso) aviso.hidden = !falta;
        if (falta) completo = false;
        if (visible && valor) datos[ctrl.name] = valor;
    });
    if (!completo) return;

    const btnOk = document.getElementById('modal-btn-ok');
    btnOk.disabled = true;
    btnOk.textContent = 'Registrando...';
    try {
        const res = await fetch('/procesar-mensaje', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem("taller_token")}` },
            body: JSON.stringify({ borrador: borrador, datos_confirmados: datos })
        });
        const data = await res.json().catch(() => ({}));
        await manejarRespuestaRegistro(res, data, true);
    } catch (err) {
        btnOk.disabled = false;
        btnOk.textContent = 'Registrar orden';
        mostrarNotificacion("Error de conexión al registrar la orden. Inténtalo de nuevo.", "error");
    }
}

// Importación masiva de inventario (sube el Excel al backend)
async function subirInventarioExcel(event) {
    const input = event.target;
    const archivo = input.files[0];
    if (!archivo) return;

    const token = localStorage.getItem("taller_token");
    const formData = new FormData();
    formData.append("archivo", archivo);

    try {
        mostrarModal({
            cargando: true,
            titulo: 'Importando inventario',
            mensaje: `Procesando <b>${escaparHTML(archivo.name)}</b>, espera un momento...`
        });

        const response = await fetch('/importar-inventario', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });

        // Si el servidor responde algo que no es JSON (500, timeout del proxy),
        // no lo tratamos como "error de conexión": mostramos el código real.
        const data = await response.json().catch(() => ({}));
        document.getElementById('modal-aviso').dataset.bloqueado = '';

        if (!response.ok) {
            mostrarModal({
                tipo: 'error',
                titulo: 'No se pudo importar',
                mensaje: escaparHTML(data.detail || `El servidor respondió con el código ${response.status}.`)
            });
            return;
        }

        const errores = data.errores || [];
        const hojas = data.hojas || [];
        const procesados = (data.nuevos || 0) + (data.actualizados || 0);
        const omitidas = hojas.filter(h => h.omitida);

        let mensaje = `<b>${data.nuevos}</b> repuestos nuevos y <b>${data.actualizados}</b> actualizados`;
        if (data.total_filas !== undefined) mensaje += ` de ${data.total_filas} fila(s)`;
        mensaje += '.';

        // Resumen por hoja (cada hoja del Excel = una categoría)
        if (hojas.length > 1 || omitidas.length > 0) {
            const filas = hojas.map(h => h.omitida
                ? `<tr class="omitida"><td>${escaparHTML(h.hoja)}</td><td colspan="3">Omitida: ${escaparHTML(h.omitida)}</td></tr>`
                : `<tr><td>${escaparHTML(h.hoja)}</td><td>${h.nuevos}</td><td>${h.actualizados}</td><td>${h.errores || '-'}</td></tr>`
            ).join('');
            mensaje += `<table class="modal-tabla">
                <thead><tr><th>Hoja</th><th>Nuevos</th><th>Actualiz.</th><th>Errores</th></tr></thead>
                <tbody>${filas}</tbody></table>`;
        }
        if (errores.length > 0) mensaje += `${errores.length} fila(s) no se importaron:`;

        let tipo = 'success', titulo = 'Inventario importado';
        if (procesados === 0) { tipo = 'error'; titulo = 'No se importó ningún repuesto'; }
        else if (errores.length > 0 || omitidas.length > 0) { tipo = 'warning'; titulo = 'Importación con observaciones'; }

        mostrarModal({ tipo, titulo, mensaje, detalles: errores });
    } catch (error) {
        document.getElementById('modal-aviso').dataset.bloqueado = '';
        mostrarModal({
            tipo: 'error',
            titulo: 'Error de conexión',
            mensaje: 'No se pudo contactar al servidor. Revisa tu internet e inténtalo de nuevo.'
        });
    } finally {
        input.value = "";  // permite volver a elegir el mismo archivo
    }
}

// ==============================================================================
// CUADRE DE CAJA DEL DÍA: siempre visible y actualizado automáticamente
// ==============================================================================
const INTERVALO_CUADRE_MS = 30000;   // refresco periódico mientras la pestaña está visible
let temporizadorCuadre = null;
let cuadreCargando = false;          // evita peticiones superpuestas
let cuadreYaMostrado = false;        // tras la 1.ª carga, los refrescos son silenciosos

// Carga el cuadre. silencioso=true: no muestra "Calculando..." ni borra el
// panel si falla (solo marca el estado en la esquina), para que no parpadee.
async function cargarCuadreCaja(silencioso = false) {
    const token = localStorage.getItem("taller_token");
    const panel = document.getElementById('panel-cuadre-caja');
    if (!panel || !token || cuadreCargando) return;
    cuadreCargando = true;

    if (!silencioso || !cuadreYaMostrado) {
        panel.innerHTML = `<div class="panel-caja"><p class="caja-cargando">Calculando cuadre de caja...</p></div>`;
    }

    try {
        const response = await fetch('/reporte-dia', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        renderizarCuadreDeCaja(data);
        cuadreYaMostrado = true;
    } catch (error) {
        const estado = document.getElementById('estado-cuadre');
        if (cuadreYaMostrado && estado) {
            // Se conserva el último cuadre en pantalla y se avisa discretamente
            estado.textContent = "Sin conexión, reintentando...";
            estado.classList.add('estado-error');
        } else {
            panel.innerHTML = `<div class="panel-caja"><p class="caja-cargando">No se pudo cargar el cuadre de caja. Se reintentará automáticamente.</p></div>`;
        }
    } finally {
        cuadreCargando = false;
    }
}

// Arranca el refresco periódico (solo consulta si la pestaña está visible)
function iniciarActualizacionCuadre() {
    detenerActualizacionCuadre();
    cargarCuadreCaja();
    temporizadorCuadre = setInterval(() => {
        if (document.visibilityState === "visible") cargarCuadreCaja(true);
    }, INTERVALO_CUADRE_MS);
}

function detenerActualizacionCuadre() {
    if (temporizadorCuadre) clearInterval(temporizadorCuadre);
    temporizadorCuadre = null;
    cuadreYaMostrado = false;
}

// Los registros se procesan en segundo plano (cola de IA): refrescamos un par
// de veces en los segundos siguientes para que el cuadre refleje el cambio.
function refrescarCuadrePronto() {
    [4000, 12000].forEach(ms => setTimeout(() => cargarCuadreCaja(true), ms));
}

// Descarga el cuadre como imagen PNG (nítida para texto y tablas; JPG
// difumina las letras). Se genera siempre a ancho completo y fondo sólido,
// aunque se descargue desde un celular.
async function descargarCuadreCaja() {
    const tarjeta = document.querySelector('#panel-cuadre-caja .panel-caja');
    const boton = document.getElementById('btn-descargar-cuadre');
    if (!tarjeta || typeof html2canvas === 'undefined') {
        mostrarModal({ tipo: 'error', titulo: 'No se pudo descargar', mensaje: 'El cuadre aún no está listo o falta la librería de imágenes. Recarga la página e inténtalo otra vez.' });
        return;
    }

    const oscuro = (document.documentElement.getAttribute("data-theme") || "dark") === "dark";
    const nombreTaller = localStorage.getItem("nombre_taller_actual") || "";
    const fecha = tarjeta.dataset.fecha || new Date().toISOString().slice(0, 10);

    try {
        if (boton) boton.disabled = true;
        const canvas = await html2canvas(tarjeta, {
            scale: 2,                                     // doble resolución: se lee bien al hacer zoom
            backgroundColor: oscuro ? "#15112E" : "#FFFFFF",
            // Cambios SOLO en la copia que se fotografía (la pantalla no cambia):
            onclone: (doc) => {
                const copia = doc.querySelector('#panel-cuadre-caja .panel-caja');
                copia.style.width = '1000px';             // ancho fijo, también desde móvil
                copia.style.backdropFilter = 'none';
                copia.style.background = oscuro ? "#15112E" : "#FFFFFF";
                copia.querySelectorAll('.tabla-scroll').forEach(t => t.style.overflow = 'visible');
                if (nombreTaller) {
                    const titulo = copia.querySelector('.titulo-cuadre');
                    if (titulo) titulo.textContent = `${nombreTaller} · ${titulo.textContent}`;
                }
                // Pie con la hora exacta de generación (evita confundir cortes del mismo día)
                const pie = doc.createElement('p');
                pie.textContent = `Generado el ${new Date().toLocaleString('es-EC')}`;
                pie.style.cssText = 'margin:4px 0 0; font-size:12px; text-align:right; opacity:0.7;';
                copia.appendChild(pie);
            }
        });

        canvas.toBlob((blob) => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Cuadre_Caja_${fecha}.png`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        }, 'image/png');
    } catch (error) {
        mostrarModal({ tipo: 'error', titulo: 'No se pudo descargar', mensaje: 'Ocurrió un error al generar la imagen del cuadre de caja.' });
    } finally {
        if (boton) boton.disabled = false;
    }
}

// Formatea dinero: 1234.5 -> "$1,234.50"
function dinero(valor) {
    return '$' + Number(valor || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Colores fijos por método de pago (la barra y los puntos de la tabla coinciden)
const COLORES_METODO = {
    'Efectivo': '#16A34A', 'Transferencia': '#7030EF', 'Tarjeta': '#2563EB',
    'Otro': '#D97706', 'Sin especificar': '#9CA3AF'
};

function renderizarCuadreDeCaja(data) {
    const panel = document.getElementById('panel-cuadre-caja');
    if (!panel) return;
    const e = escaparHTML;  // todo texto que viene de la BD se escapa

    const claseNeto = data.neto > 0 ? 'monto-positivo' : (data.neto < 0 ? 'monto-negativo' : 'monto-neutro');
    const claseCaja = data.efectivo_en_caja < 0 ? 'monto-negativo' : 'monto-neutro';
    const v = data.vehiculos || {};

    // ---------- Alertas: datos incompletos que impiden cuadrar bien ----------
    const alertas = data.alertas || [];
    const bloqueAlertas = alertas.length ? `
        <div class="alertas-caja">
            <b>Revisar antes de cerrar caja (${alertas.length})</b>
            <ul>${alertas.map(a => `<li>${e(a)}</li>`).join('')}</ul>
        </div>` : '';

    // ---------- Ingresos por método de pago ----------
    const metodos = data.ingresos_por_metodo || [];
    const barra = metodos.length ? `
        <div class="barra-metodos">${metodos.map(m =>
            `<span style="width:${m.porcentaje}%; background:${COLORES_METODO[m.metodo]}" title="${e(m.metodo)} ${m.porcentaje}%"></span>`).join('')}
        </div>` : '';
    const filasMetodos = metodos.length ? metodos.map(m => `
            <tr class="fila-metodo">
                <td><span class="punto-metodo" style="background:${COLORES_METODO[m.metodo]}"></span>${e(m.metodo)}</td>
                <td class="centro">${m.ordenes}</td>
                <td class="num">${dinero(m.total)}</td>
                <td class="num">${m.porcentaje}%</td>
            </tr>
            ${(m.bancos || []).map(b => `
            <tr class="fila-banco">
                <td>${e(b.banco)}</td>
                <td class="centro">${b.ordenes}</td>
                <td class="num">${dinero(b.total)}</td>
                <td></td>
            </tr>`).join('')}`).join('')
        : `<tr><td colspan="4" class="vacio">Sin cobros registrados hoy.</td></tr>`;

    // ---------- Órdenes cerradas ----------
    const ordenes = data.ordenes_cerradas || [];
    const filasOrdenes = ordenes.length ? ordenes.map(o => `
            <tr>
                <td>${e(o.hora || '-')}</td>
                <td><b>${e(o.vehiculo)}</b>${o.modelo ? `<div class="sub">${e(o.modelo)}</div>` : ''}</td>
                <td>${e(o.cliente)}</td>
                <td class="celda-trabajo" title="${e(o.trabajo)}">${e(o.trabajo || '-')}</td>
                <td>${e(o.oficial)}</td>
                <td>${e(o.metodo_pago)}${o.banco ? `<div class="sub">${e(o.banco)}</div>` : ''}</td>
                <td class="num">${dinero(o.cobro)}${o.repuestos > 0 ? `<div class="sub">rep. ${dinero(o.repuestos)}</div>` : ''}</td>
            </tr>`).join('') + `
            <tr class="fila-total"><td colspan="6">Total cobrado</td><td class="num">${dinero(data.total_ingresos)}</td></tr>`
        : `<tr><td colspan="7" class="vacio">Sin órdenes cerradas hoy.</td></tr>`;

    // ---------- Cerrados sin cobro (garantías, sin presupuesto, etc.) ----------
    const sinCobro = data.cerrados_sin_cobro || [];
    const bloqueSinCobro = sinCobro.length ? `
            <h4>Cerrados sin cobro (${sinCobro.length})</h4>
            <div class="tabla-scroll">
                <table class="tabla-caja">
                    <thead><tr><th>Hora</th><th>Placa</th><th>Cliente</th><th>Técnico</th><th>Motivo</th><th>Detalle</th></tr></thead>
                    <tbody>${sinCobro.map(c => `
                        <tr>
                            <td>${e(c.hora || '-')}</td>
                            <td><b>${e(c.vehiculo)}</b>${c.modelo ? `<div class="sub">${e(c.modelo)}</div>` : ''}</td>
                            <td>${e(c.cliente)}</td>
                            <td>${e(c.oficial)}</td>
                            <td>${e(c.motivo)}</td>
                            <td class="celda-trabajo" title="${e(c.detalle)}">${e(c.detalle || '-')}</td>
                        </tr>`).join('')}
                    </tbody>
                </table>
            </div>` : '';

    // ---------- Egresos ----------
    const egresos = data.egresos || [];
    const filasEgresos = egresos.length ? egresos.map(g => `
            <tr>
                <td>${e(g.hora || '-')}</td>
                <td>${e(g.motivo)}</td>
                <td>${e(g.vehiculo || '-')}</td>
                <td>${e(g.responsable)}</td>
                <td class="num">${dinero(g.monto)}</td>
            </tr>`).join('') + `
            <tr class="fila-total"><td colspan="4">Total egresos</td><td class="num">${dinero(data.total_egresos)}</td></tr>`
        : `<tr><td colspan="5" class="vacio">Sin egresos registrados hoy.</td></tr>`;
    const porResponsable = (data.egresos_por_responsable || []);
    const bloqueResponsables = porResponsable.length > 1 ? `
        <div class="chips-responsables">${porResponsable.map(r =>
            `<span class="chip">${e(r.responsable)}: <b>${dinero(r.total)}</b> (${r.cantidad})</span>`).join('')}
        </div>` : '';

    // ---------- Técnicos ----------
    const tecnicos = data.rendimiento_tecnicos || [];
    const filasTecnicos = tecnicos.length ? tecnicos.map(t => `
            <tr>
                <td>${e(t.tecnico)}</td>
                <td class="centro">${t.trabajos}</td>
                <td class="num">${dinero(t.total_generado)}</td>
                <td class="num">${dinero(t.mano_de_obra)}</td>
                <td class="num comision">${dinero(t.comision_a_pagar)}</td>
            </tr>`).join('') + `
            <tr class="fila-total"><td colspan="4">Total comisiones a pagar</td><td class="num comision">${dinero(data.total_comisiones)}</td></tr>`
        : `<tr><td colspan="5" class="vacio">Sin datos de técnicos hoy.</td></tr>`;

    panel.innerHTML = `
        <div class="panel-caja" data-fecha="${e(data.fecha)}">
            <div class="cabecera-caja">
                <div class="titulo-caja-wrap">
                    <h3 class="titulo-cuadre">Cuadre de Caja — ${e(data.fecha)}</h3>
                    <span id="estado-cuadre" class="estado-cuadre" data-html2canvas-ignore="true">Actualizado ${new Date().toLocaleTimeString('es-EC', { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                <button id="btn-descargar-cuadre" class="btn-descargar-cuadre" onclick="descargarCuadreCaja()" data-html2canvas-ignore="true"
                        title="Descargar cuadre de caja (imagen PNG)" aria-label="Descargar cuadre de caja"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11"/><polyline points="7 10 12 15 17 10"/><path d="M5 20h14"/></svg></button>
            </div>

            <!-- Resumen principal -->
            <div class="tarjetas-resumen-caja">
                <div class="tarjeta-resumen-caja">
                    <div class="etiqueta">Ingresos</div>
                    <div class="monto monto-positivo">${dinero(data.total_ingresos)}</div>
                </div>
                <div class="tarjeta-resumen-caja">
                    <div class="etiqueta">Egresos</div>
                    <div class="monto monto-negativo">${dinero(data.total_egresos)}</div>
                </div>
                <div class="tarjeta-resumen-caja">
                    <div class="etiqueta">Neto del día</div>
                    <div class="monto ${claseNeto}">${dinero(data.neto)}</div>
                </div>
                <div class="tarjeta-resumen-caja tarjeta-efectivo">
                    <div class="etiqueta">Efectivo en caja</div>
                    <div class="monto ${claseCaja}">${dinero(data.efectivo_en_caja)}</div>
                </div>
            </div>
            <div class="linea-detalle">
                Mano de obra <b>${dinero(data.total_mano_obra)}</b> · Repuestos <b>${dinero(data.total_repuestos)}</b> · Comisiones <b>${dinero(data.total_comisiones)}</b>
                <span class="separador">|</span>
                Vehículos: <b>${v.ingresados_hoy || 0}</b> ingresaron · <b>${v.entregados_hoy || 0}</b> entregados${v.cerrados_sin_cobro ? ` · <b>${v.cerrados_sin_cobro}</b> sin cobro` : ''} · <b>${v.pendientes_en_taller || 0}</b> en taller
            </div>

            ${bloqueAlertas}

            <!-- Métodos de pago + cuadre de efectivo -->
            <div class="grid-caja">
                <div>
                    <h4>Ingresos por método de pago</h4>
                    ${barra}
                    <table class="tabla-caja tabla-compacta">
                        <thead><tr><th>Método</th><th style="text-align:center;">Órdenes</th><th style="text-align:right;">Total</th><th style="text-align:right;">%</th></tr></thead>
                        <tbody>${filasMetodos}</tbody>
                    </table>
                </div>
                <div class="cuadre-efectivo">
                    <h4>Cuadre de efectivo</h4>
                    <div class="linea-cuadre"><span>Efectivo cobrado</span><span class="monto-positivo">+ ${dinero(data.efectivo_cobrado)}</span></div>
                    <div class="linea-cuadre"><span>Egresos pagados de caja</span><span class="monto-negativo">− ${dinero(data.total_egresos)}</span></div>
                    <div class="linea-cuadre total"><span>Debe haber en caja</span><span class="${claseCaja}">${dinero(data.efectivo_en_caja)}</span></div>
                    <p class="nota-cuadre">Transferencias y tarjeta van directo al banco; no se cuentan en caja. Se asume que los egresos se pagan en efectivo.</p>
                </div>
            </div>

            <h4>Órdenes cerradas hoy (${ordenes.length})</h4>
            <div class="tabla-scroll">
                <table class="tabla-caja">
                    <thead><tr>
                        <th>Hora</th><th>Placa</th><th>Cliente</th><th>Trabajo</th><th>Técnico</th><th>Pago</th><th style="text-align:right;">Cobro</th>
                    </tr></thead>
                    <tbody>${filasOrdenes}</tbody>
                </table>
            </div>

            ${bloqueSinCobro}

            <h4>Egresos de hoy (${egresos.length})</h4>
            ${bloqueResponsables}
            <div class="tabla-scroll">
                <table class="tabla-caja">
                    <thead><tr>
                        <th>Hora</th><th>Motivo</th><th>Placa</th><th>Responsable</th><th style="text-align:right;">Monto</th>
                    </tr></thead>
                    <tbody>${filasEgresos}</tbody>
                </table>
            </div>

            <h4>Rendimiento y comisiones por técnico</h4>
            <div class="tabla-scroll">
                <table class="tabla-caja">
                    <thead><tr>
                        <th>Técnico</th><th style="text-align:center;">Trabajos</th><th style="text-align:right;">Generado</th><th style="text-align:right;">Mano de obra</th><th style="text-align:right;">Comisión</th>
                    </tr></thead>
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
        
        // ¡NUEVA VALIDACIÓN! Cierre automático si el token expiró
        if (response.status === 401) {
            cerrarSesion();
            mostrarNotificacion("Tu sesión ha caducado por seguridad. Por favor, inicia sesión nuevamente.", "warning");
            return;
        }
        
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
        // "Terminados hoy" también muestra los cerrados sin cobro del día
        const vehiculosFiltrados = listaVehiculos.filter(v => filtroEstadoActual === 'Terminado'
            ? (v.estado === 'Terminado' || v.estado === 'Cerrado sin cobro')
            : v.estado === filtroEstadoActual);

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
                let claseEstado = v.estado === 'Pendiente' ? 'estado-pendiente'
                                 : (v.estado === 'Cerrado sin cobro' ? 'estado-sin-cobro' : 'estado-terminado');

                let detalleExtra;
                if (v.estado === 'Terminado') {
                    detalleExtra = `<div class="info-cobro">Cobro: $${v.cobro || 0} (${v.metodo_pago || 'Efectivo'})</div>`;
                } else if (v.estado === 'Cerrado sin cobro') {
                    detalleExtra = `<div class="info-taller-item"><strong>Motivo de cierre:</strong> ${escaparHTML(v.motivo_cierre || '-')}</div>`
                        + (v.detalle_cierre ? `<div class="info-taller-item"><strong>Detalle:</strong> ${escaparHTML(v.detalle_cierre)}</div>` : '');
                } else {
                    detalleExtra = `<div class="info-taller-item"><strong>Falla / Motivo:</strong> ${v.motivo || 'No especificado'}</div>`;
                }

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
                            Descargar Orden
                        </button>
                    `;
                }

                // Botón corto "Cerrar orden" (sin cobro) solo en vehículos pendientes
                const botonCerrar = v.estado === 'Pendiente'
                    ? `<button class="btn-cerrar-orden" title="Cerrar la orden sin cobro (garantía, sin presupuesto...)"
                               data-id="${escaparHTML(String(v.id))}" data-placa="${escaparHTML(v.vehiculo || '')}"
                               data-cliente="${escaparHTML(v.cliente || '')}"
                               onclick="event.stopPropagation(); abrirCerrarOrden(this)">Cerrar orden</button>`
                    : '';

                // Extraer el ID de la base de datos para mostrarlo como Número de Orden
                let numOrden = v.id || v.id_orden || '---';

                html += `
                    <div class="tarjeta-vehiculo-pendiente" onclick="usarPlaca('${v.vehiculo}')" title="Haz clic para usar esta placa">
                        <div class="tarjeta-header">
                            <span class="placa-badge">${v.vehiculo}</span>
                            <span class="badge-orden-esquina">N° ${numOrden}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span class="badge-estado ${claseEstado}">${v.estado}</span>
                        </div>
                        <div class="info-taller-item"><strong>Cliente:</strong> ${v.cliente || 'N/A'}</div>
                        ${infoVehiculo}
                        ${infoTelefono}
                        ${detalleExtra}
                        ${marcaGarantia(v.garantia_previa)}
                        ${botonDescarga}
                        ${botonCerrar}
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

// Marca en la tarjeta si el vehículo tiene (o tuvo hace poco) garantía de otro trabajo
function marcaGarantia(g) {
    if (!g) return '';
    const vence = new Date(g.vence + 'T12:00:00').toLocaleDateString('es-EC');
    const texto = g.vigente
        ? `En garantía hasta ${vence} (orden N° ${g.orden_id})`
        : `Garantía vencida ${g.motivo_vencida} (orden N° ${g.orden_id})`;
    return `<div class="marca-garantia ${g.vigente ? 'vigente' : 'vencida'}" title="${escaparHTML(g.trabajo)}">${escaparHTML(texto)}</div>`;
}

// Texto del aviso de garantía (modal de ingreso / confirmación)
function avisoGarantiaHTML(g) {
    if (!g) return '';
    const e = escaparHTML;
    const vence = new Date(g.vence + 'T12:00:00').toLocaleDateString('es-EC');
    const km = g.km_limite ? ` o ${Number(g.km_limite).toLocaleString('es-EC')} km` : '';
    return g.vigente
        ? `<div class="aviso-garantia vigente"><b>Este vehículo tiene garantía vigente</b> por la orden N° ${e(g.orden_id)}:
             ${e(g.trabajo || 'trabajo anterior')}${g.tecnico ? ` (técnico: ${e(g.tecnico)})` : ''}. Válida hasta el ${vence}${km}.</div>`
        : `<div class="aviso-garantia vencida"><b>Garantía vencida ${e(g.motivo_vencida)}</b> de la orden N° ${e(g.orden_id)}:
             ${e(g.trabajo || 'trabajo anterior')}. Venció el ${vence}${km}. El taller decide si la cubre.</div>`;
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
/// ==============================================================================
// FUNCIÓN MAESTRA PARA LLENAR LA PLANTILLA (Evita código duplicado)
// ==============================================================================
function llenarPlantillaOrden(datos) {
    // 1. Taller y Número de Orden
    const nombreTaller = localStorage.getItem("nombre_taller_actual") || "Orden de Servicio";
    const elTitulo = document.getElementById('orden-nombre-taller');
    if (elTitulo) elTitulo.innerText = nombreTaller;
    document.getElementById('orden-id').innerText = datos.id || '---';

    // 2. Vehículo y Cliente
    document.getElementById('orden-placa').innerText = datos.vehiculo || '---';
    const modelo = datos.modelo || 'S/M';
    const color = datos.color || 'S/C';
    const anio = datos.anio || 'S/A';
    const cilindraje = datos.cilindraje ? datos.cilindraje + 'L' : 'S/C';
    document.getElementById('orden-detalles-vehiculo').innerText = `${modelo} | ${color} | ${anio} | ${cilindraje}`;
    
    document.getElementById('orden-cliente').innerText = datos.cliente || '---';
    
    // CORRECCIÓN CÉDULA: Conversión segura a String para evitar errores con trim()
    const rawCedula = datos.cedula || datos.cedula_cliente || datos.identificacion || '';
    const cedulaLimpia = String(rawCedula).trim();
    document.getElementById('orden-cedula').innerText = (cedulaLimpia !== '' && cedulaLimpia !== 'null' && cedulaLimpia !== 'undefined') ? cedulaLimpia : 'No registrada';
    
    document.getElementById('orden-telefono').innerText = datos.telefono || 'No registrado';
    const elKm = document.getElementById('orden-kilometraje');
    if (elKm) elKm.innerText = datos.kilometraje ? `${Number(datos.kilometraje).toLocaleString('es-EC')} km` : 'No registrado';

    // 3. Fechas y Equipo
    let fechaLimpia = datos.fecha_hora ? new Date(datos.fecha_hora).toLocaleDateString() : '---';
    document.getElementById('orden-fecha').innerText = fechaLimpia;
    document.getElementById('orden-tecnico').innerText = datos.oficial || 'No asignado';

    // 4. Trabajo Realizado
    document.getElementById('orden-motivo').innerText = datos.motivo || 'No especificado';
    document.getElementById('orden-trabajo').innerText = datos.trabajo_realizado || 'No especificado';

    // 5. Tabla de Repuestos
    const tbody = document.getElementById('orden-repuestos-body');
    tbody.innerHTML = '';
    let totalRepuestos = 0;

    if (datos.reparacion_detalles && datos.reparacion_detalles.length > 0) {
        datos.reparacion_detalles.forEach(detalle => {
            const subtotal = detalle.cantidad * (detalle.precio_unitario || 0);
            totalRepuestos += subtotal;
            
            tbody.innerHTML += `
                <tr>
                    <td style="border: 1px solid #ddd; padding: 8px;">${detalle.inventario?.codigo || 'N/A'}</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">${detalle.inventario?.nombre || 'Genérico'}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">${detalle.cantidad}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">$${(detalle.precio_unitario || 0).toFixed(2)}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">$${subtotal.toFixed(2)}</td>
                </tr>
            `;
        });
    } else {
        tbody.innerHTML = `<tr><td colspan="5" style="border: 1px solid #ddd; padding: 8px; text-align: center;">No se registraron repuestos (Solo mano de obra)</td></tr>`;
    }

    // 6. Lógica de Cobros y Total
    const estado = datos.estado || 'Pendiente';
    document.getElementById('orden-estado-texto').innerText = estado;
    
    const etiquetaTotal = document.getElementById('orden-etiqueta-total');
    if (etiquetaTotal) {
        etiquetaTotal.innerText = estado === 'Terminado' ? 'Valor Cancelado:' : 'Valor a Pagar:';
    }

    // El "cobro" registrado YA incluye los repuestos (así se calcula el cuadre y
    // la comisión: mano de obra = cobro - repuestos). Antes aquí se sumaban los
    // repuestos otra vez y el total salía inflado.
    const cobro = parseFloat(datos.cobro || 0);
    const totalFinal = cobro > 0 ? cobro : totalRepuestos;
    document.getElementById('orden-total').innerText = totalFinal.toFixed(2);

    // Garantía entregada con este trabajo
    const cajaGarantia = document.getElementById('orden-garantia');
    if (cajaGarantia) {
        if (estado === 'Terminado' && datos.garantia_vence) {
            const vence = new Date(datos.garantia_vence + 'T12:00:00').toLocaleDateString('es-EC');
            const km = datos.garantia_km ? ` o ${Number(datos.garantia_km).toLocaleString('es-EC')} km` : '';
            const kmLimite = datos.garantia_km_limite ? ` o hasta los ${Number(datos.garantia_km_limite).toLocaleString('es-EC')} km` : '';
            cajaGarantia.innerHTML = `<strong>Garantía: ${datos.garantia_dias} días${km}</strong> — válida hasta el ${vence}${kmLimite}, lo que ocurra primero.
                <br><span style="font-size: 11px;">Cubre el trabajo realizado en esta orden. No cubre mal uso, golpes ni manipulación por terceros. Presente esta orden para hacerla válida.</span>`;
            cajaGarantia.style.display = 'block';
        } else if (estado === 'Terminado' && datos.garantia_dias === 0) {
            cajaGarantia.innerHTML = '<strong>Este trabajo no incluye garantía.</strong>';
            cajaGarantia.style.display = 'block';
        } else {
            cajaGarantia.style.display = 'none';
            cajaGarantia.innerHTML = '';
        }
    }

    // 7. CORRECCIÓN BANCO Y MÉTODO DE PAGO
    const metodo = String(datos.metodo_pago || '').trim();
    const banco = String(datos.banco || '').trim();
    let textoMetodoPago = "Pendiente de pago";

    if (metodo !== '' && metodo !== 'null') {
        textoMetodoPago = metodo;
        if (banco !== '' && banco !== 'null' && !metodo.toLowerCase().includes(banco.toLowerCase())) {
            textoMetodoPago += ` (${banco})`;
        }
    } else if (banco !== '' && banco !== 'null') {
        textoMetodoPago = `Transferencia (${banco})`;
    } else if (estado === 'Terminado') {
        textoMetodoPago = "Efectivo";
    }

    document.getElementById('orden-metodo-pago').innerText = textoMetodoPago;
}

// ==========================================================================
// GENERADOR DE IMÁGENES (Chat IA)
// ==========================================================================
async function generarImagenFactura(orden) {
    llenarPlantillaOrden(orden); // <-- Llama a la función maestra

    const plantilla = document.getElementById('plantilla-orden');
    plantilla.style.display = 'block'; 
    plantilla.style.position = 'absolute';
    plantilla.style.top = '-9999px';
    plantilla.style.left = '-9999px';

    try {
        const canvas = await html2canvas(plantilla, { scale: 2, backgroundColor: "#ffffff" });
        const imgData = canvas.toDataURL('image/png');
        
        const enlaceDescarga = document.createElement('a');
        enlaceDescarga.href = imgData;
        enlaceDescarga.download = `Orden_Trabajo_${orden.vehiculo}.png`;
        enlaceDescarga.click();
        
    } catch (error) {
        console.error("Error al generar la imagen:", error);
        alert("Hubo un error al crear la imagen");
    } finally {
        plantilla.style.display = 'none';
    }
}

// ==============================================================================
// GENERADOR DE COMPROBANTES PNG (Botón en la Tarjeta)
// ==============================================================================
async function generarComprobantePNG(vehiculoJson) {
    try {
        const reparacion = typeof vehiculoJson === 'string' ? JSON.parse(vehiculoJson) : vehiculoJson;
        
        llenarPlantillaOrden(reparacion); // <-- Llama a la misma función maestra

        const plantilla = document.getElementById('plantilla-orden');
        plantilla.style.display = 'block';
        plantilla.style.position = 'absolute';
        plantilla.style.top = '-9999px'; 
        plantilla.style.left = '-9999px';

        const canvas = await html2canvas(plantilla, { scale: 2, backgroundColor: "#ffffff" });
        const imgData = canvas.toDataURL('image/png');

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
                <td>${escaparHTML(t.tecnico)}</td>
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
            const clasePuesto = t.posicion <= 3 ? `puesto-top puesto-${t.posicion}` : '';
            return `
                <tr>
                    <td style="font-weight: bold;"><span class="${clasePuesto}">#${t.posicion}</span></td>
                    <td>${escaparHTML(t.tecnico)}</td>
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
// ==============================================================================
// ACTUALIZACIÓN AUTOMÁTICA AL RETOMAR LA PESTAÑA (WAKE UP)
// ==============================================================================
document.addEventListener("visibilitychange", function() {
    // Si el usuario vuelve a poner la pestaña en primer plano (estado visible)
    if (document.visibilityState === "visible") {
        const token = localStorage.getItem("taller_token");
        
        // Si hay una sesión activa, refrescamos los datos críticos automáticamente
        if (token) {
            console.log("Pestaña reactivada: actualizando datos en vivo...");
            
            // 1. Refrescar vehículos pendientes/terminados
            if (typeof cargarVehiculosPendientes === "function") {
                cargarVehiculosPendientes(typeof filtroEstadoActual !== 'undefined' ? filtroEstadoActual : 'Pendiente');
            }
            
            // 2. Refrescar el ranking anual en vivo
            if (typeof cargarRankingAnual === "function") {
                cargarRankingAnual();
            }

            // 3. Refrescar el cuadre de caja
            cargarCuadreCaja(true);
        }
    }
});

// Respaldo adicional para dispositivos móviles (iOS/Android) al salir de la caché de navegación
window.addEventListener("pageshow", function(event) {
    if (event.persisted) {
        const token = localStorage.getItem("taller_token");
        if (token) {
            cargarVehiculosPendientes();
            if (typeof cargarRankingAnual === "function") cargarRankingAnual();
            cargarCuadreCaja(true);
        }
    }
});
// ==========================================================================
// NAVEGACIÓN Y MENÚ HAMBURGUESA
// ==========================================================================
function toggleMenu() {
    const menu = document.getElementById('menu-lateral');
    if (menu.style.left === '0px') {
        menu.style.left = '-250px';
    } else {
        menu.style.left = '0px';
    }
}

function cambiarVista(idVista) {
    // Ocultar todas las vistas
    const vistas = document.querySelectorAll('.vista-app');
    vistas.forEach(vista => vista.style.display = 'none');
    
    // Mostrar la vista seleccionada
    document.getElementById(idVista).style.display = 'block';
    
    // Cerrar el menú lateral
    toggleMenu();
    
    // Si entramos al dashboard, cargamos los gráficos (lo programaremos luego)
    if (idVista === 'vista-dashboard') {
        cargarDatosDashboard(); 
    } else if (idVista === 'vista-servicios') {
        cargarServicios();
    } else if (idVista === 'vista-garantias') {
        iniciarVistaGarantias();
    }
}
// ==========================================================================
// DASHBOARD ANALÍTICO (CHART.JS)
// ==========================================================================
let chartRepuestos = null;
let chartClientes = null;
let chartServicios = null;

async function cargarDatosDashboard() {
    const token = localStorage.getItem("taller_token"); // ¡Corregido!
    if (!token) return;

    try {
        // Llama a la URL de tu backend correctamente sin API_URL
        const response = await fetch("/dashboard-stats", {
            headers: { "Authorization": `Bearer ${token}` }
        });
        
        if (!response.ok) throw new Error("Error cargando el dashboard");
        
        const data = await response.json();

        renderChartRepuestos(data.top_repuestos);
        renderChartClientes(data.top_clientes);
        renderChartServicios(data.top_servicios);

    } catch (error) {
        console.error("Error en el Dashboard:", error);
    }
}

function renderChartRepuestos(datos) {
    const ctx = document.getElementById('graficoRepuestos').getContext('2d');
    if (chartRepuestos) chartRepuestos.destroy(); // Limpiar gráfico anterior

    chartRepuestos = new Chart(ctx, {
        type: 'doughnut', // Gráfico circular (donut)
        data: {
            labels: datos.map(d => d.nombre),
            datasets: [{
                label: 'Unidades Vendidas',
                data: datos.map(d => d.cantidad),
                backgroundColor: ['#DB1FFF', '#7030EF', '#00d2ff', '#3a7bd5', '#ff7b00'],
                borderWidth: 0
            }]
        },
        options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { color: '#888' } } } }
    });
}

function renderChartClientes(datos) {
    const ctx = document.getElementById('graficoClientes').getContext('2d');
    if (chartClientes) chartClientes.destroy();

    chartClientes = new Chart(ctx, {
        type: 'bar', // Gráfico de barras horizontales
        data: {
            labels: datos.map(d => d.nombre),
            datasets: [{
                label: 'Inversión Total ($)',
                data: datos.map(d => d.total),
                backgroundColor: '#28a745',
                borderRadius: 5
            }]
        },
        options: { 
            indexAxis: 'y', // Lo hace horizontal
            responsive: true, 
            plugins: { legend: { display: false } },
            scales: { x: { grid: { color: '#333' } }, y: { grid: { display: false } } }
        }
    });
}

function renderChartServicios(datos) {
    const ctx = document.getElementById('graficoServicios').getContext('2d');
    if (chartServicios) chartServicios.destroy();

    chartServicios = new Chart(ctx, {
        type: 'pie', // Gráfico tipo pastel
        data: {
            labels: datos.map(d => d.nombre),
            datasets: [{
                label: 'Veces Realizado',
                data: datos.map(d => d.cantidad),
                backgroundColor: ['#ff9900', '#ff5500', '#ff0055', '#9900ff', '#00ccff'],
                borderWidth: 0
            }]
        },
        options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { color: '#888' } } } }
    });
}
// ==========================================================================
// CATÁLOGO DE SERVICIOS
// ==========================================================================
// ==============================================================================
// CATÁLOGO DE SERVICIOS + GARANTÍAS (cada taller define las suyas)
// Nota: antes había dos copias de guardarServicio/eliminarServicio y las de
// abajo usaban una clave de token equivocada ('as_token'), así que agregar y
// eliminar servicios fallaba sin avisar. Queda una sola versión.
// ==============================================================================
let garantiaTallerActual = { dias: 30, km: 1000 };

function textoGarantia(dias, km) {
    if (dias === 0) return 'Sin garantía';
    const partes = [`${dias} días`];
    if (km) partes.push(`${Number(km).toLocaleString('es-EC')} km`);
    return partes.join(' o ');
}

function cabeceraAuth(json = false) {
    const h = { 'Authorization': `Bearer ${localStorage.getItem("taller_token")}` };
    if (json) h['Content-Type'] = 'application/json';
    return h;
}

async function cargarServicios() {
    if (!localStorage.getItem("taller_token")) return;
    const e = escaparHTML;
    try {
        const res = await fetch("/servicios", { headers: cabeceraAuth() });
        const data = await res.json();
        garantiaTallerActual = data.garantia_defecto || garantiaTallerActual;

        // Garantía por defecto del taller (la define el dueño)
        const nota = document.getElementById('nota-garantia-defecto');
        if (nota) {
            nota.innerHTML = `<b>Garantía por defecto de tu taller: ${textoGarantia(garantiaTallerActual.dias, garantiaTallerActual.km)}</b>
                <button class="btn-link" onclick="editarGarantiaTaller()">Cambiar</button><br>
                Se aplica a los servicios que no tienen garantía propia. En cada trabajo también puedes indicarla al cerrar
                (ej. "...se le dio garantía de 3 meses"), y esa tiene prioridad.`;
        }

        const tbody = document.getElementById('tabla-servicios');
        const servicios = data.servicios || [];
        if (!servicios.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="vacio">No hay servicios registrados.</td></tr>';
            return;
        }
        tbody.innerHTML = servicios.map(s => {
            const propia = s.garantia_dias !== null && s.garantia_dias !== undefined;
            const dias = propia ? s.garantia_dias : garantiaTallerActual.dias;
            const km = (s.garantia_km !== null && s.garantia_km !== undefined) ? s.garantia_km : garantiaTallerActual.km;
            return `
                <tr>
                    <td>${e(s.nombre_servicio)}</td>
                    <td class="num">$${Number(s.precio_base || 0).toFixed(2)}</td>
                    <td>${e(textoGarantia(dias, km))}${propia ? '' : ' <span class="sub">(del taller)</span>'}
                        <button class="btn-link" onclick='editarGarantiaServicio(${JSON.stringify(String(s.id))}, ${JSON.stringify(s.nombre_servicio)}, ${JSON.stringify(s.garantia_dias)}, ${JSON.stringify(s.garantia_km)})'>Editar</button>
                    </td>
                    <td class="centro">
                        <button onclick='eliminarServicio(${JSON.stringify(String(s.id))})' class="btn-icono-eliminar" title="Eliminar" aria-label="Eliminar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></button>
                    </td>
                </tr>`;
        }).join('');
    } catch (error) {
        console.error("Error cargando servicios:", error);
    }
}

// Lee un número entero opcional de un input (vacío -> null)
function enteroOpcional(id) {
    const v = document.getElementById(id).value.trim();
    return v === '' ? null : Math.max(0, parseInt(v, 10));
}

async function guardarServicio() {
    const nombre = document.getElementById('nuevo-servicio-nombre').value.trim();
    const precio = document.getElementById('nuevo-servicio-precio').value;
    if (!nombre || precio === '' || isNaN(parseFloat(precio))) {
        mostrarModal({ tipo: 'warning', titulo: 'Faltan datos', mensaje: 'Ingresa el nombre del servicio y un precio válido.' });
        return;
    }
    try {
        const res = await fetch("/servicios", {
            method: "POST",
            headers: cabeceraAuth(true),
            body: JSON.stringify({
                nombre_servicio: nombre,
                precio_base: parseFloat(precio),
                garantia_dias: enteroOpcional('nuevo-servicio-garantia-dias'),
                garantia_km: enteroOpcional('nuevo-servicio-garantia-km')
            })
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            mostrarModal({ tipo: 'error', titulo: 'No se pudo agregar', mensaje: escaparHTML(typeof err.detail === 'string' ? err.detail : `Error ${res.status}`) });
            return;
        }
        ['nuevo-servicio-nombre', 'nuevo-servicio-precio', 'nuevo-servicio-garantia-dias', 'nuevo-servicio-garantia-km']
            .forEach(id => document.getElementById(id).value = '');
        cargarServicios();
    } catch (error) {
        mostrarNotificacion("Error de conexión al guardar el servicio.", "error");
    }
}

async function eliminarServicio(id) {
    if (!confirm("¿Estás seguro de eliminar este servicio?")) return;
    try {
        const res = await fetch(`/servicios/${encodeURIComponent(id)}`, { method: "DELETE", headers: cabeceraAuth() });
        if (res.ok) cargarServicios();
        else mostrarModal({ tipo: 'error', titulo: 'No se pudo eliminar', mensaje: `Error ${res.status}` });
    } catch (error) {
        mostrarNotificacion("Error de conexión al eliminar el servicio.", "error");
    }
}

// Modal genérico para editar días/km de garantía
function abrirModalGarantia({ titulo, descripcion, dias, km, permitirVacio, alGuardar }) {
    const overlay = document.getElementById('modal-aviso');
    mostrarModal({ tipo: 'info', titulo });
    overlay.dataset.modo = 'formulario';
    document.getElementById('modal-mensaje').innerHTML = descripcion;

    const valor = v => (v === null || v === undefined) ? '' : v;
    const formulario = document.getElementById('modal-formulario');
    formulario.innerHTML = `
        <label class="campo-faltante">
            <span class="campo-etiqueta">Garantía en días (0 = sin garantía)</span>
            <input name="dias" type="number" min="0" inputmode="numeric" value="${valor(dias)}" placeholder="${permitirVacio ? 'Vacío = la del taller' : 'Ej. 30'}">
            <span class="campo-aviso" hidden>Ingresa un número de días</span>
        </label>
        <label class="campo-faltante">
            <span class="campo-etiqueta">Garantía en kilómetros (0 = sin límite de km)</span>
            <input name="km" type="number" min="0" inputmode="numeric" value="${valor(km)}" placeholder="${permitirVacio ? 'Vacío = la del taller' : 'Ej. 1000'}">
            <span class="campo-aviso" hidden>Ingresa un número de kilómetros</span>
        </label>`;
    formulario.hidden = false;

    const btnCancelar = document.getElementById('modal-btn-cancelar');
    btnCancelar.hidden = false;
    btnCancelar.onclick = () => { overlay.dataset.modo = ''; cerrarModal(); };

    const btnOk = document.getElementById('modal-btn-ok');
    btnOk.textContent = 'Guardar';
    btnOk.onclick = async () => {
        const campos = { dias: formulario.querySelector('[name=dias]'), km: formulario.querySelector('[name=km]') };
        const datos = {};
        let ok = true;
        for (const [k, input] of Object.entries(campos)) {
            const v = input.value.trim();
            const falta = !permitirVacio && v === '';
            input.classList.toggle('invalido', falta);
            input.closest('.campo-faltante').querySelector('.campo-aviso').hidden = !falta;
            if (falta) ok = false;
            datos[k] = v === '' ? null : Math.max(0, parseInt(v, 10));
        }
        if (!ok) return;
        btnOk.disabled = true;
        try {
            await alGuardar(datos);
        } finally {
            btnOk.disabled = false;
        }
    };
    setTimeout(() => formulario.querySelector('input').focus(), 50);
}

function editarGarantiaTaller() {
    abrirModalGarantia({
        titulo: 'Garantía por defecto del taller',
        descripcion: 'Se aplica a todos los servicios que no tienen una garantía propia. Solo afecta a los trabajos que se cierren desde ahora.',
        dias: garantiaTallerActual.dias, km: garantiaTallerActual.km, permitirVacio: false,
        alGuardar: async (d) => {
            const res = await fetch('/garantia-taller', { method: 'PUT', headers: cabeceraAuth(true), body: JSON.stringify(d) });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) { mostrarModal({ tipo: 'error', titulo: 'No se pudo guardar', mensaje: escaparHTML(typeof data.detail === 'string' ? data.detail : `Error ${res.status}`) }); return; }
            mostrarModal({ tipo: 'success', titulo: 'Garantía actualizada', mensaje: `Nueva garantía por defecto: <b>${textoGarantia(d.dias, d.km)}</b>.` });
            cargarServicios();
        }
    });
}

function editarGarantiaServicio(id, nombre, dias, km) {
    abrirModalGarantia({
        titulo: 'Garantía del servicio',
        descripcion: `<div class="resumen-orden">${escaparHTML(nombre)}</div>Déjalo vacío para usar la garantía por defecto del taller (${textoGarantia(garantiaTallerActual.dias, garantiaTallerActual.km)}).`,
        dias, km, permitirVacio: true,
        alGuardar: async (d) => {
            const res = await fetch(`/servicios/${encodeURIComponent(id)}/garantia`, {
                method: 'PATCH', headers: cabeceraAuth(true),
                body: JSON.stringify({ garantia_dias: d.dias, garantia_km: d.km })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) { mostrarModal({ tipo: 'error', titulo: 'No se pudo guardar', mensaje: escaparHTML(typeof data.detail === 'string' ? data.detail : `Error ${res.status}`) }); return; }
            const overlay = document.getElementById('modal-aviso'); overlay.dataset.modo = ''; cerrarModal();
            cargarServicios();
        }
    });
}
