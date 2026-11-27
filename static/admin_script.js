/* ==========================================================================
   PANEL DE ADMINISTRACIÓN DE LA PLATAFORMA
   Usa el mismo sistema de diseño que la app del taller (style.css):
   barra lateral, modo claro/oscuro y un modal centrado para todo resultado.
   ========================================================================== */

// ==========================================================================
// MODAL ÚNICO
//   - mostrarAviso(): resultado de una acción, con ícono y botón OK.
//   - abrirModal(): formulario con Cancelar / Guardar (renovar pago, módulos...).
//   - confirmarAccion(): pregunta antes de algo delicado (suspender un taller).
// ==========================================================================
const ICONOS_MODAL = {
    success: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>',
    warning: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="14"/><line x1="12" y1="19" x2="12.01" y2="19"/></svg>',
    error:   '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    info:    '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="11" x2="12" y2="16"/><line x1="12" y1="7.5" x2="12.01" y2="7.5"/></svg>'
};
const TITULOS_AVISO = { success: 'Listo', error: 'No se pudo completar', warning: 'Atención', info: 'Aviso' };

let accionModalCallback = null;   // lo que hace el botón principal en modo formulario

const elModal = id => document.getElementById(id);

// Deja el modal en un estado limpio antes de cada uso
function prepararModal({ modo, titulo, ancho = false }) {
    const overlay = elModal('modal-aviso');
    const caja = overlay.querySelector('.modal-caja');
    caja.classList.toggle('adm-modal-ancho', ancho);
    caja.classList.toggle('adm-modal-formulario', modo !== 'aviso');
    overlay.dataset.modo = modo;
    elModal('modal-titulo').textContent = titulo;
    elModal('modal-mensaje').innerHTML = '';
    elModal('modal-body').innerHTML = '';
    elModal('modal-body').hidden = true;
    elModal('modal-error').hidden = true;
    elModal('modal-icono').className = 'modal-icono';
    elModal('modal-icono').innerHTML = '';
    const ok = elModal('modal-btn-confirmar');
    ok.disabled = false;
    ok.classList.remove('adm-peligro');
    const cancelar = elModal('modal-btn-cancelar');
    cancelar.hidden = modo === 'aviso';
    cancelar.onclick = cerrarModal;
    return { overlay, ok };
}

let focoAntesDelModal = null;   // para devolver el foco al cerrar

function mostrarModalPreparado(overlay, enfocar) {
    if (!overlay.classList.contains('visible')) focoAntesDelModal = document.activeElement;
    overlay.classList.add('visible');
    overlay.setAttribute('aria-hidden', 'false');
    setTimeout(() => enfocar && enfocar.focus(), 60);
}

// Resultado de una acción: ícono, título, mensaje (texto plano) y OK
function mostrarAviso(mensaje, tipo = 'info', titulo) {
    const { overlay, ok } = prepararModal({ modo: 'aviso', titulo: titulo || TITULOS_AVISO[tipo] || 'Aviso' });
    const icono = elModal('modal-icono');
    icono.className = `modal-icono ${tipo}`;
    icono.innerHTML = ICONOS_MODAL[tipo] || ICONOS_MODAL.info;
    elModal('modal-mensaje').textContent = mensaje;
    ok.textContent = 'OK';
    ok.onclick = cerrarModal;
    accionModalCallback = null;
    mostrarModalPreparado(overlay, ok);
}

// Compatibilidad: el resto del panel sigue llamando a showToast().
// Si hay un formulario abierto, el error se muestra dentro de él (no se pierde lo escrito).
function showToast(message, type = 'info') {
    const overlay = elModal('modal-aviso');
    const enFormulario = overlay.classList.contains('visible') && overlay.dataset.modo !== 'aviso';
    if (enFormulario && type === 'error') {
        const error = elModal('modal-error');
        error.textContent = message;
        error.hidden = false;
        return;
    }
    mostrarAviso(message, type);
}

// Formulario: htmlInputs ya viene escapado por quien lo arma
function abrirModal(titulo, htmlInputs, callbackConfirmar, ancho = false, textoBoton = 'Guardar') {
    const { overlay, ok } = prepararModal({ modo: 'formulario', titulo, ancho });
    const cuerpo = elModal('modal-body');
    cuerpo.innerHTML = htmlInputs;
    cuerpo.hidden = false;
    ok.textContent = textoBoton;
    accionModalCallback = callbackConfirmar;
    ok.onclick = () => { if (accionModalCallback) accionModalCallback(); };
    mostrarModalPreparado(overlay, cuerpo.querySelector('input, select') || ok);
}

// Confirmación antes de una acción delicada. El botón de peligro va en rojo.
function confirmarAccion({ titulo, mensaje, textoBoton = 'Confirmar', peligro = false, alConfirmar }) {
    const { overlay, ok } = prepararModal({ modo: 'confirmacion', titulo });
    const icono = elModal('modal-icono');
    icono.className = `modal-icono ${peligro ? 'error' : 'warning'}`;
    icono.innerHTML = ICONOS_MODAL.warning;
    elModal('modal-mensaje').textContent = mensaje;
    ok.textContent = textoBoton;
    ok.classList.toggle('adm-peligro', peligro);
    accionModalCallback = alConfirmar;
    ok.onclick = async () => {
        ok.disabled = true;
        try { await alConfirmar(); } finally { ok.disabled = false; }
    };
    mostrarModalPreparado(overlay, elModal('modal-btn-cancelar'));   // el foco inicial nunca en el botón peligroso
}

function cerrarModal() {
    const overlay = elModal('modal-aviso');
    overlay.classList.remove('visible');
    overlay.setAttribute('aria-hidden', 'true');
    accionModalCallback = null;
    // El foco vuelve al botón que abrió el modal (si sigue en la página)
    if (focoAntesDelModal && document.contains(focoAntesDelModal)) focoAntesDelModal.focus({ preventScroll: true });
    focoAntesDelModal = null;
}

// Con el modal abierto, Tab recorre solo sus controles
function retenerFocoEnModal(e) {
    const caja = document.querySelector('#modal-aviso .modal-caja');
    const enfocables = [...caja.querySelectorAll('button, input, select, textarea, summary, [tabindex]:not([tabindex="-1"])')]
        .filter(el => !el.disabled && !el.hidden && el.offsetParent !== null);
    if (!enfocables.length) return;
    const primero = enfocables[0], ultimo = enfocables[enfocables.length - 1];
    if (!caja.contains(document.activeElement)) { e.preventDefault(); primero.focus(); }
    else if (e.shiftKey && document.activeElement === primero) { e.preventDefault(); ultimo.focus(); }
    else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primero.focus(); }
}

// Teclado: Escape siempre cancela. Enter solo acepta en un aviso (en un
// formulario o una confirmación hay que pulsar el botón a propósito).
document.addEventListener('keydown', e => {
    const overlay = elModal('modal-aviso');
    if (!overlay.classList.contains('visible')) {
        if (e.key === 'Escape') toggleMenu(false);
        return;
    }
    if (e.key === 'Escape') { e.preventDefault(); cerrarModal(); }
    else if (e.key === 'Tab') retenerFocoEnModal(e);
    else if (e.key === 'Enter' && overlay.dataset.modo === 'aviso') { e.preventDefault(); cerrarModal(); }
});
// Clic fuera de la caja: cierra solo los avisos
elModal('modal-aviso').addEventListener('click', e => {
    if (e.target.id === 'modal-aviso' && e.currentTarget.dataset.modo === 'aviso') cerrarModal();
});

// ==========================================================================
// TEMA CLARO / OSCURO (misma preferencia que la app del taller)
// ==========================================================================
const ICONO_LUNA = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const ICONO_SOL = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>';

function prefiereMenosMovimiento() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function alternarTema() {
    const cambiar = () => {
        const nuevo = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', nuevo);
        localStorage.setItem('as_tema', nuevo);
        actualizarIconoTema(nuevo);
    };
    // Fundido suave entre temas donde el navegador lo permite
    if (document.startViewTransition && !prefiereMenosMovimiento()) document.startViewTransition(cambiar);
    else cambiar();
}

function actualizarIconoTema(tema) {
    elModal('icono-tema').innerHTML = tema === 'dark' ? ICONO_LUNA : ICONO_SOL;
    elModal('texto-tema').textContent = tema === 'dark' ? 'Oscuro' : 'Claro';
}

// ==========================================================================
// NAVEGACIÓN ENTRE SECCIONES
// ==========================================================================
function toggleMenu(forzarAbierto) {
    // En escritorio la navegación siempre está visible; en el celular es un cajón
    const menu = elModal('menu-lateral');
    const abrir = typeof forzarAbierto === 'boolean' ? forzarAbierto : !menu.classList.contains('abierto');
    menu.classList.toggle('abierto', abrir);
    document.querySelector('.nav-fondo').classList.toggle('visible', abrir);
}

// Vuelve a disparar la animación de entrada de la sección
function reanimar(el) {
    if (!el || prefiereMenosMovimiento()) return;
    el.classList.remove('vista-entra');
    void el.offsetWidth;
    el.classList.add('vista-entra');
}

function cambiarSeccion(id) {
    document.querySelectorAll('.adm-seccion').forEach(s => s.hidden = s.id !== id);
    document.querySelectorAll('[data-seccion]').forEach(b => {
        if (b.dataset.seccion === id) b.setAttribute('aria-current', 'page');
        else b.removeAttribute('aria-current');
    });
    sessionStorage.setItem('adm_seccion', id);   // al recargar se vuelve a la misma sección
    reanimar(elModal(id));
    toggleMenu(false);
    window.scrollTo(0, 0);
    // Cada sección carga sus datos al abrirse
    if (id === 'sec-resumen') cargarResumen();
    else if (id === 'sec-talleres') {
        cerrarVista360();
        cargarTalleres();
        if (fichaPendiente) { const f = fichaPendiente; fichaPendiente = null; abrirFicha360(f); }
        else if (tallerAbierto) abrirFicha360(tallerAbierto, { desdeLista: true, mostrar: false });
    }
    else if (id === 'sec-planes') cargarVistaPlanes();
    else if (id === 'sec-monitor') cargarColaIA();
}

// ==========================================================================
// SESIÓN
// ==========================================================================
function alternarVerClave(forzarOculta = false) {
    const input = elModal('admin_password');
    const boton = elModal('ver-clave');
    const mostrar = forzarOculta ? false : input.type === 'password';
    input.type = mostrar ? 'text' : 'password';
    boton.setAttribute('aria-pressed', String(mostrar));
    boton.setAttribute('aria-label', mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña');
}

async function loginAdmin() {
    const em = elModal("admin_email").value.trim();
    const pw = elModal("admin_password").value;
    const error = elModal("login_error");
    const boton = document.querySelector('#login-container .btn-login');
    error.textContent = '';
    if (!em || !pw) { error.textContent = 'Escribe tu correo y tu contraseña.'; return; }
    if (boton.classList.contains('enviando')) return;

    // Estado "Ingresando..." mientras responde el servidor
    const ponerEnviando = activo => {
        boton.classList.toggle('enviando', activo);
        boton.disabled = activo;
        boton.setAttribute('aria-busy', String(activo));
        boton.textContent = activo ? 'Ingresando...' : 'Ingresar';
    };
    ponerEnviando(true);
    try {
        const res = await fetch("/login", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: em, password: pw })
        });
        const data = await res.json();
        if (data.status === "success" && data.token) {
            localStorage.setItem("admin_token", data.token);
            localStorage.setItem("admin_email", em);
            const ok = await verificarAcceso(data.token);
            if (!ok) error.textContent = 'Esta cuenta no tiene permisos de administrador.';
        } else {
            error.textContent = 'Correo o contraseña incorrectos.';
        }
    } catch {
        error.textContent = 'No se pudo conectar con el servidor. Intenta de nuevo.';
    } finally {
        ponerEnviando(false);
    }
}

// Comprueba que el token sea de superadmin y abre el panel. Devuelve true/false.
async function verificarAcceso(token) {
    try {
        const res = await fetch("/admin/talleres", { headers: { 'Authorization': `Bearer ${token}` } });
        if (!res.ok) throw new Error();
    } catch {
        localStorage.removeItem("admin_token");
        return false;
    }
    elModal("login-container").hidden = true;
    elModal("panel-admin").hidden = false;
    elModal("adm-correo").textContent = localStorage.getItem("admin_email") || 'Administrador';
    actualizarIconoTema(document.documentElement.getAttribute('data-theme') || 'dark');
    alternarVerClave(true);
    await cargarPlanes().then(llenarSelectPlanes);
    const seccion = sessionStorage.getItem('adm_seccion') || 'sec-resumen';
    if (seccion !== 'sec-resumen') cargarDashboard();   // contador de errores del menú
    cambiarSeccion(seccion);
    return true;
}

const cerrarSesionAdmin = () => {
    localStorage.removeItem("admin_token");
    sessionStorage.removeItem('adm_seccion');
    location.reload();
};

// Al abrir la página: si hay una sesión guardada, entra directo
(async () => {
    const token = localStorage.getItem("admin_token");
    if (token) await verificarAcceso(token);
})();

// ==========================================================================
// RESUMEN
//   Ingresos reales por mes y plan (como entró el dinero), próximos cobros,
//   salud de cada taller y alertas. Datos: /admin/resumen + /admin/dashboard-metrics.
// ==========================================================================
let periodoIngresos = 6;          // 6, 12 o 0 (todo)
let ultimoResumen = null;         // última respuesta de /admin/resumen
const MIGRACION_PAGOS = 'sql/2026-11-27_pagos_talleres.sql';

// Colores de los planes en el gráfico: el de más ingreso, lima brillante
const COLORES_PLAN = ['#B8F35B', '#5E8F2A', '#8FCB45', '#3F6B1C', '#D7F99E'];
let colorPorPlan = {};

const dinero = v => '$' + Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
// "2026-11-29" -> "29 nov 2026" (sin desfase de zona horaria)
function fechaCorta(iso) {
    if (!iso) return 'Sin fecha';
    const [a, m, d] = String(iso).slice(0, 10).split('-').map(Number);
    return a && m && d ? `${d} ${MESES_CORTOS[m - 1]} ${a}` : String(iso);
}
// Iniciales sin artículos ni preposiciones: "Lubricadora El Pana" -> "LP"
const PALABRAS_VACIAS = new Set(['el', 'la', 'los', 'las', 'de', 'del', 'y', 'e']);
const iniciales = nombre => {
    const palabras = String(nombre || '?').split(/\s+/).filter(Boolean);
    const utiles = palabras.filter(p => !PALABRAS_VACIAS.has(p.toLowerCase()));
    return (utiles.length ? utiles : palabras).slice(0, 2).map(p => p[0]).join('').toUpperCase();
};
const hoyISO = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

// "hace 4 min", "hace 3 días"... a partir de un timestamp UTC
function haceCuanto(ts) {
    if (!ts) return 'Sin actividad';
    const t = new Date(String(ts).replace(' ', 'T') + (/[zZ]|[+-]\d\d:?\d\d$/.test(ts) ? '' : 'Z'));
    const min = Math.max(0, Math.round((Date.now() - t) / 60000));
    if (min < 60) return `Hace ${min} min`;
    const h = Math.round(min / 60);
    if (h < 24) return `Hace ${h} h`;
    const d = Math.round(h / 24);
    return `Hace ${d} día${d === 1 ? '' : 's'}`;
}

async function cargarResumen() {
    const fecha = new Date().toLocaleDateString('es-EC', { weekday: 'long', day: 'numeric', month: 'long' });
    elModal('res-fecha').textContent = `${fecha.charAt(0).toUpperCase() + fecha.slice(1)}. Cómo va la plataforma hoy.`;
    cargarDashboard();   // estado del sistema y alertas (en paralelo)
    try {
        const res = await fetch(`/admin/resumen?meses=${periodoIngresos}`, { headers: cabeceraAdmin() });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
        ultimoResumen = data;
        pintarResumen(data);
    } catch (e) {
        elModal('res-barras').innerHTML = `<p class="res-vacio">No se pudo cargar el resumen: ${esc(e.message)}</p>`;
    }
}

function elegirPeriodoIngresos(meses) {
    periodoIngresos = meses;
    document.querySelectorAll('.res-segmentos button').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.meses) === meses)));
    cargarResumen();
}

function pintarResumen(r) {
    // Colores fijos por plan: primero los que generan más ingreso
    colorPorPlan = {};
    [...r.planes.map(p => p.codigo), ...Object.keys(r.nombres_planes || {})]
        .forEach(c => { if (!(c in colorPorPlan)) colorPorPlan[c] = COLORES_PLAN[Object.keys(colorPorPlan).length % COLORES_PLAN.length]; });
    const nombrePlanRes = c => (r.nombres_planes || {})[c] || (c === 'sin_plan' ? 'Sin plan' : c);

    // Aviso si falta la migración de pagos
    const aviso = elModal('res-aviso-migracion');
    aviso.hidden = !r.falta_migracion;
    if (r.falta_migracion) aviso.textContent = `Los ingresos aparecerán cuando ejecutes en Supabase la migración ${r.falta_migracion}. Mientras tanto se muestran el MRR esperado y los próximos cobros.`;

    // ---- Cifras de ingresos ----
    const ing = r.ingresos;
    elModal('res-total').textContent = dinero(ing.total);
    elModal('res-total-texto').textContent = periodoIngresos ? `en los últimos ${periodoIngresos} meses` : 'desde el primer pago';
    elModal('res-cobrado-mes').textContent = dinero(ing.cobrado_mes_actual);
    elModal('res-mrr').textContent = dinero(ing.mrr);
    elModal('res-por-cobrar').textContent = dinero(ing.por_cobrar_mes);
    const comp = elModal('res-comparacion');
    if (periodoIngresos && (ing.total || ing.total_anterior)) {
        const dif = ing.total - ing.total_anterior;
        comp.className = `res-comparacion ${dif < 0 ? 'baja' : ''}`;
        comp.textContent = `${dif >= 0 ? '+' : '-'}${dinero(Math.abs(dif))} frente a los ${periodoIngresos} meses anteriores`;
    } else {
        comp.textContent = '';
    }

    // ---- Leyenda y barras apiladas por plan ----
    const planesEnSerie = [...new Set(ing.meses.flatMap(m => Object.keys(m.por_plan)))]
        .sort((a, b) => Object.keys(colorPorPlan).indexOf(a) - Object.keys(colorPorPlan).indexOf(b));
    elModal('res-leyenda').innerHTML = planesEnSerie.map(c =>
        `<span><i style="background:${colorPorPlan[c] || '#8D9A95'}"></i>${esc(nombrePlanRes(c))}</span>`).join('');

    const barras = elModal('res-barras');
    if (!ing.meses.some(m => m.total > 0)) {
        barras.innerHTML = `<div class="res-vacio">
            <b>Aún no hay pagos registrados en este periodo.</b>
            <span>Cada vez que un taller te pague, regístralo con "Registrar un pago" y aparecerá aquí.</span></div>`;
    } else {
        const max = Math.max(...ing.meses.map(m => m.total));
        const muchos = ing.meses.length > 12;
        barras.classList.toggle('compactas', muchos);
        barras.innerHTML = ing.meses.map((m, i) => {
            const actual = i === ing.meses.length - 1;
            const segmentos = planesEnSerie.filter(c => m.por_plan[c]).map(c =>
                `<i style="height:${(m.por_plan[c] / max * 100).toFixed(2)}%;background:${colorPorPlan[c]}"
                    title="${esc(nombrePlanRes(c))}: ${dinero(m.por_plan[c])}"></i>`).join('');
            const etiqueta = m.etiqueta + (ing.meses.length > 12 || m.mes.slice(5) === '01' ? ` ${String(m.anio).slice(2)}` : '');
            return `<div class="res-col ${actual ? 'actual' : ''}">
                <span class="res-val">${m.total ? dinero(m.total) : ''}</span>
                <div class="res-pila" aria-label="${esc(etiqueta)}: ${dinero(m.total)}">${segmentos}</div>
                <span class="res-mes">${esc(etiqueta)}</span></div>`;
        }).join('');
    }

    // ---- Próximos cobros ----
    elModal('res-proximos').innerHTML = r.proximos_cobros.length ? r.proximos_cobros.slice(0, 4).map(p => {
        let chip = '';
        if (p.dias < 0) chip = `<span class="res-chip rojo">Vencido</span>`;
        else if (p.dias <= 7) chip = `<span class="res-chip amarillo">${p.dias === 0 ? 'Hoy' : `${p.dias} día${p.dias === 1 ? '' : 's'}`}</span>`;
        return `<button type="button" class="res-cobro" onclick="modalRegistrarPago('${esc(p.taller_id)}')" title="Registrar el pago de ${esc(p.nombre)}">
            <span class="res-av">${esc(iniciales(p.nombre))}</span>
            <span class="res-cobro-txt"><b>${esc(p.nombre)}</b><span>${fechaCorta(p.vence)}${chip}</span></span>
            <span class="res-monto">${dinero(p.monto)}</span></button>`;
    }).join('') : '<p class="res-vacio-chico">No hay talleres activos con fecha de vencimiento.</p>';

    // ---- Tabla de talleres ----
    const SALUD = { activo: ['Activo', 'ok'], bajando: ['Bajando', 'baja'], inactivo: ['Sin uso', 'inactivo'], suspendido: ['Suspendido', 'suspendido'] };
    elModal('res-talleres').innerHTML = r.talleres.map(t => {
        const [textoSalud, claseSalud] = SALUD[t.salud] || SALUD.activo;
        return `<tr data-id="${esc(t.id)}">
            <td data-etiqueta="Taller"><button type="button" class="res-taller" onclick="abrirFicha360('${esc(t.id)}')">
                <span class="res-av">${esc(iniciales(t.nombre))}</span><span>${esc(t.nombre)}</span></button></td>
            <td data-etiqueta="Plan"><span class="res-plan">${esc(t.plan)}</span> <span class="res-tenue">${esc(t.periodo)}</span></td>
            <td data-etiqueta="Te ha pagado"><b class="res-num">${dinero(t.pagado_total)}</b>
                <span class="res-tenue res-bloque">${t.n_pagos} pago${t.n_pagos === 1 ? '' : 's'}</span></td>
            <td data-etiqueta="Vence">${fechaCorta(t.vence)}</td>
            <td data-etiqueta="Uso">${minigrafico(t.uso_semanal, claseSalud)}
                <span class="res-tenue res-bloque">${esc(haceCuanto(t.ultima_actividad))}</span></td>
            <td data-etiqueta="Salud"><span class="res-salud ${claseSalud}"><i></i>${textoSalud}</span></td>
            <td class="res-acc"><button type="button" class="res-btn-menu" aria-haspopup="menu" aria-label="Acciones de ${esc(t.nombre)}"
                onclick="abrirMenuTaller(event, '${esc(t.id)}')"><svg viewBox="0 0 24 24"><circle cx="12" cy="5" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="12" cy="19" r="1.4"/></svg></button></td>
        </tr>`;
    }).join('') || '<tr><td colspan="7" class="res-vacio-chico">Todavía no hay talleres registrados.</td></tr>';

    // ---- Ingreso mensual por plan (anillos concéntricos) ----
    pintarAnillos(r.planes, ing.mrr);
    pintarAlertas();
}

// Mini curva de uso semanal (órdenes registradas) dentro de la tabla
function minigrafico(valores, clase) {
    const W = 104, H = 28, max = Math.max(...valores, 1);
    const pts = valores.map((v, i) => `${(i * W / (valores.length - 1)).toFixed(1)},${(H - 3 - v / max * (H - 6)).toFixed(1)}`).join(' ');
    const total = valores.reduce((a, b) => a + b, 0);
    return `<svg class="res-spark ${clase}" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img"
        aria-label="${total} órdenes en 8 semanas"><polyline points="${pts}"/></svg>`;
}

function pintarAnillos(planes, mrr) {
    const cont = elModal('res-anillos');
    if (!planes.length) { cont.innerHTML = '<p class="res-vacio-chico">Sin talleres activos.</p>'; return; }
    const radios = [80, 60, 40, 20];
    const anillos = planes.slice(0, 4).map((p, i) => {
        const r = radios[i], largo = 2 * Math.PI * r, parte = mrr ? p.mrr / mrr : 0;
        return `<circle cx="95" cy="95" r="${r}" class="res-anillo-fondo"/>
            <circle cx="95" cy="95" r="${r}" fill="none" stroke="${colorPorPlan[p.codigo]}" stroke-width="13" stroke-linecap="round"
                stroke-dasharray="${(largo * parte).toFixed(1)} ${largo.toFixed(1)}" transform="rotate(-90 95 95)"/>`;
    }).join('');
    cont.innerHTML = `
        <svg viewBox="0 0 190 190" class="res-anillos-svg" role="img" aria-label="Ingreso mensual por plan">${anillos}</svg>
        <div class="res-anillos-leyenda">
            <div class="res-anillos-total"><b>${dinero(mrr)}</b><span>MRR esperado al mes</span></div>
            ${planes.map(p => `<div class="res-anillos-fila"><i style="background:${colorPorPlan[p.codigo]}"></i>
                <span>${esc(p.nombre)}<small>${p.talleres} taller${p.talleres === 1 ? '' : 'es'}</small></span><b>${dinero(p.mrr)}</b></div>`).join('')}
        </div>`;
}

// ---- Estado del sistema y alertas (endpoint anterior, se mantiene) ----
let alertasSistema = [];
async function cargarDashboard() {
    try {
        const res = await fetch("/admin/dashboard-metrics", { headers: cabeceraAdmin() });
        if (!res.ok) throw new Error();
        const data = await res.json();
        elModal("dash-ai-today").textContent = data.system.ai_today;
        const errores = elModal("dash-errors");
        errores.textContent = data.system.errors;
        errores.classList.toggle('rojo', data.system.errors > 0);
        const navErr = elModal("nav-errores");
        navErr.textContent = data.system.errors;
        navErr.hidden = !data.system.errors;
        alertasSistema = data.alertas || [];
        pintarAlertas();
    } catch {
        // El Resumen sigue funcionando sin estas cifras
    }
}

// Une las alertas del sistema (pagos, cola de IA) con las de uso de cada taller
function pintarAlertas() {
    const cont = elModal('lista-alertas');
    if (!cont) return;
    const NIVEL = { critico: 'rojo', advertencia: 'amarillo', riesgo: 'azul' };
    // Las de "sin actividad" del sistema se reemplazan por las de salud (más precisas)
    const items = alertasSistema.filter(a => a.tipo !== 'riesgo')
        // Las fechas del servidor vienen como "(2026-11-29)": se muestran como "el 29 nov 2026"
        .map(a => ({ nivel: NIVEL[a.tipo] || 'azul',
                     html: String(a.mensaje || '').replace(/\s*\((\d{4}-\d{2}-\d{2})\)/g, (_, f) => `, el ${fechaCorta(f)}`) }));
    (ultimoResumen?.talleres || []).forEach(t => {
        const u = t.uso_semanal || [];
        if (t.salud === 'bajando') {
            const antes = Math.round(u.slice(0, -2).reduce((a, b) => a + b, 0) / Math.max(1, u.length - 2));
            const ahora = Math.round(u.slice(-2).reduce((a, b) => a + b, 0) / 2);
            items.push({ nivel: 'rojo', html: `<b>${esc(t.nombre)}</b> bajó su uso: de ${antes} a ${ahora} órdenes por semana. Conviene llamarlo.` });
        } else if (t.salud === 'inactivo') {
            items.push({ nivel: 'amarillo', html: `<b>${esc(t.nombre)}</b> no registró órdenes en las últimas 2 semanas.` });
        }
    });
    cont.innerHTML = items.length
        ? items.map(a => `<div class="res-alerta"><span class="res-punto ${a.nivel}" aria-hidden="true">!</span><p>${a.html}</p></div>`).join('')
        : '<div class="res-alerta"><span class="res-punto ok" aria-hidden="true"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span><p>Todo en orden. Los talleres están al día y usando el sistema.</p></div>';
}

// ---- Menú de acciones de una fila ----
function abrirMenuTaller(evento, id) {
    evento.stopPropagation();
    const menu = elModal('res-menu');
    const boton = evento.currentTarget;
    if (!menu.hidden && menu.dataset.id === id) { cerrarMenuTaller(); return; }
    menu.dataset.id = id;
    menu.innerHTML = `
        <button type="button" role="menuitem" onclick="cerrarMenuTaller(); modalRegistrarPago('${esc(id)}')">Registrar pago</button>
        <button type="button" role="menuitem" onclick="cerrarMenuTaller(); abrirFicha360('${esc(id)}')">Ver ficha 360°</button>
        <button type="button" role="menuitem" onclick="cerrarMenuTaller(); modalModulos('${esc(id)}')">Módulos</button>`;
    menu.hidden = false;
    const caja = boton.getBoundingClientRect();
    menu.style.top = `${Math.min(caja.bottom + 6, window.innerHeight - menu.offsetHeight - 10)}px`;
    menu.style.left = `${Math.max(10, caja.right - menu.offsetWidth)}px`;
    menu.dataset.abierto = String(Date.now());
    menu.querySelector('button').focus({ preventScroll: true });
}
function cerrarMenuTaller() { elModal('res-menu').hidden = true; }
document.addEventListener('click', e => { if (!e.target.closest('#res-menu')) cerrarMenuTaller(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrarMenuTaller(); });
// Al desplazarse la página el menú queda fuera de lugar: se cierra
// (salvo el desplazamiento que el propio clic pueda provocar al abrirlo)
window.addEventListener('scroll', () => {
    const menu = elModal('res-menu');
    if (!menu.hidden && Date.now() - Number(menu.dataset.abierto || 0) > 250) cerrarMenuTaller();
}, { passive: true });

function irARegistrarTaller() { modalNuevoTaller(); }

// ==========================================================================
// REGISTRAR PAGO
//   Guarda el cobro y renueva al taller hasta la fecha que cubre el pago.
//   Reemplaza al antiguo "Renovar pago", que solo cambiaba la fecha.
// ==========================================================================
const METODOS_PAGO = [['transferencia', 'Transferencia'], ['efectivo', 'Efectivo'], ['deposito', 'Depósito'], ['tarjeta', 'Tarjeta'], ['otro', 'Otro']];
const MESES_PERIODO = { mensual: 1, trimestral: 3, anual: 12 };
let talleresParaPago = [];

// Misma regla que el servidor: desde el vencimiento vigente (o desde hoy) + meses del periodo
function calcularCubreHasta(venceISO, periodo) {
    const hoy = hoyISO();
    const base = venceISO && venceISO > hoy ? venceISO : hoy;
    const [a, m, d] = base.split('-').map(Number);
    const total = m - 1 + MESES_PERIODO[periodo];
    const anio = a + Math.floor(total / 12), mes = total % 12;
    const ultimo = new Date(anio, mes + 1, 0).getDate();
    return `${anio}-${String(mes + 1).padStart(2, '0')}-${String(Math.min(d, ultimo)).padStart(2, '0')}`;
}

// Datos de cada taller para el formulario (del Resumen si ya cargó; si no, del listado)
async function obtenerTalleresParaPago() {
    if (ultimoResumen?.talleres?.length) return ultimoResumen.talleres;
    const res = await fetch('/admin/talleres', { headers: cabeceraAdmin() });
    const data = await res.json();
    return (data.talleres || []).map(t => {
        const periodo = t.periodo || t.plan || 'mensual';
        const plan = planesCache.find(p => p.codigo === t.plan_codigo);
        return { id: t.id, nombre: t.nombre, plan_codigo: t.plan_codigo, plan: t.plan_nombre || '', periodo,
                 vence: t.fecha_vencimiento, precio: plan ? Number(plan[`precio_${periodo}`]) : 0 };
    });
}

function precioDe(taller, periodo) {
    const plan = planesCache.find(p => p.codigo === taller.plan_codigo);
    return plan ? Number(plan[`precio_${periodo}`] || 0) : (periodo === taller.periodo ? taller.precio : 0);
}

async function modalRegistrarPago(tallerId = null) {
    try { talleresParaPago = await obtenerTalleresParaPago(); }
    catch { mostrarAviso('No se pudo cargar la lista de talleres.', 'error'); return; }
    if (!talleresParaPago.length) { mostrarAviso('Primero registra un taller.', 'info'); return; }
    // Sin taller elegido: el que vence primero
    const ordenados = [...talleresParaPago].sort((a, b) => String(a.vence || '9').localeCompare(String(b.vence || '9')));
    const elegido = talleresParaPago.find(t => String(t.id) === String(tallerId)) || ordenados[0];

    const html = `
        <label class="adm-campo-ancho">Taller
            <select id="pago-taller" onchange="actualizarFormularioPago(true)" ${tallerId ? 'disabled' : ''}>
                ${ordenados.map(t => `<option value="${esc(t.id)}" ${t.id === elegido.id ? 'selected' : ''}>${esc(t.nombre)}</option>`).join('')}
            </select></label>
        <p class="adm-modal-sub" id="pago-detalle"></p>
        <div class="adm-rejilla-2">
            <label>Monto recibido
                <input type="number" id="pago-monto" min="0" step="0.01" inputmode="decimal">
                <span class="adm-ayuda" id="pago-sugerido"></span></label>
            <label>Método
                <select id="pago-metodo">${METODOS_PAGO.map(([v, t]) => `<option value="${v}">${t}</option>`).join('')}</select></label>
            <label>Fecha del pago
                <input type="date" id="pago-fecha" value="${hoyISO()}" max="${hoyISO()}"></label>
            <label>Periodo que paga
                <select id="pago-periodo" onchange="actualizarFormularioPago(false)">
                    <option value="mensual">Mensual</option><option value="trimestral">Trimestral</option><option value="anual">Anual</option>
                </select></label>
            <label class="adm-campo-ancho">Nota (opcional)
                <input type="text" id="pago-nota" maxlength="300" placeholder="Ej. Banco Pichincha, comprobante 4821"></label>
            <label class="adm-campo-ancho">Queda activo hasta
                <input type="date" id="pago-hasta" oninput="this.dataset.editado = '1'">
                <span class="adm-ayuda">Se calcula con el periodo desde su vencimiento actual. Puedes cambiarla.</span></label>
        </div>`;
    abrirModal('Registrar pago', html, guardarPago, false, 'Registrar pago');
    actualizarFormularioPago(true);
    setTimeout(() => elModal('pago-monto').focus(), 80);
}

// Rellena monto sugerido, periodo y fecha de cobertura según el taller elegido
function actualizarFormularioPago(cambioTaller) {
    const t = talleresParaPago.find(x => String(x.id) === elModal('pago-taller').value);
    if (!t) return;
    const selPeriodo = elModal('pago-periodo');
    if (cambioTaller) selPeriodo.value = t.periodo || 'mensual';
    const periodo = selPeriodo.value;
    const precio = precioDe(t, periodo);
    elModal('pago-detalle').textContent = `Plan ${t.plan || 'sin plan'}, pago ${t.periodo || 'mensual'}. Vence el ${fechaCorta(t.vence)}.`;
    elModal('pago-monto').value = precio ? precio.toFixed(2) : '';
    elModal('pago-sugerido').textContent = precio ? `Sugerido según su plan: ${dinero(precio)}` : 'Escribe el monto que recibiste';
    const hasta = elModal('pago-hasta');
    if (cambioTaller) delete hasta.dataset.editado;
    if (!hasta.dataset.editado) hasta.value = calcularCubreHasta(t.vence, periodo);
}

async function guardarPago() {
    const id = elModal('pago-taller').value;
    const monto = parseFloat(elModal('pago-monto').value);
    const fecha = elModal('pago-fecha').value;
    if (!(monto >= 0) || elModal('pago-monto').value === '') { showToast('Escribe el monto que recibiste.', 'error'); return; }
    if (!fecha || fecha > hoyISO()) { showToast('La fecha del pago no puede ser futura.', 'error'); return; }
    const btn = elModal('modal-btn-confirmar');
    btn.disabled = true;
    try {
        const res = await fetch(`/admin/talleres/${encodeURIComponent(id)}/pagos`, {
            method: 'POST', headers: cabeceraAdmin(true),
            body: JSON.stringify({
                monto, fecha_pago: fecha, periodo: elModal('pago-periodo').value, metodo: elModal('pago-metodo').value,
                nota: elModal('pago-nota').value.trim(), cubre_hasta: elModal('pago-hasta').value || null
            })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            showToast(typeof data.detail === 'string' ? data.detail : 'Revisa los datos del pago.', 'error');
            return;
        }
        mostrarAviso(data.mensaje || 'Pago registrado.', 'success', 'Pago registrado');
        if (!elModal('sec-resumen').hidden) cargarResumen();
        if (!elModal('sec-talleres').hidden) cargarTalleres();
    } catch {
        showToast('Error de conexión al servidor.', 'error');
    } finally {
        btn.disabled = false;
    }
}

// Compatibilidad: los botones "Renovar pago" existentes abren el nuevo formulario
function modalActualizarPago(id) { modalRegistrarPago(id); }

// ==========================================================================
// TALLERES
//   Lista (con búsqueda y filtros) + ficha 360° del taller elegido.
//   Datos: /admin/talleres (plan, módulos, estado) unidos con /admin/resumen
//   (lo pagado, el uso y la salud) cuando está disponible.
// ==========================================================================
let talleresCache = [];         // filas de la lista ya unidas
let filtroTalleres = 'todos';
let tallerAbierto = null;       // id del taller con la ficha abierta
let fichaPendiente = null;      // ficha pedida desde otra sección (se abre al entrar)
const DIAS_POR_VENCER = 7;

const diasHasta = iso => {
    if (!iso) return null;
    const [a, m, d] = String(iso).slice(0, 10).split('-').map(Number);
    const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
    return Math.round((new Date(a, m - 1, d) - hoy) / 86400000);
};

async function cargarTalleres() {
    const cont = elModal('lista-talleres');
    if (!talleresCache.length) cont.innerHTML = '<p class="res-vacio-chico">Cargando talleres...</p>';
    try {
        const [resT, resR] = await Promise.all([
            fetch('/admin/talleres', { headers: cabeceraAdmin() }),
            fetch('/admin/resumen?meses=6', { headers: cabeceraAdmin() }).catch(() => null)
        ]);
        const data = await resT.json();
        if (!resT.ok) throw new Error(data.detail || `Error ${resT.status}`);
        const resumen = resR && resR.ok ? await resR.json() : null;
        if (resumen) ultimoResumen = resumen;
        const extra = Object.fromEntries((resumen?.talleres || []).map(t => [String(t.id), t]));
        talleresCache = (data.talleres || []).map(t => ({
            ...t,
            periodo: t.periodo || t.periodo_facturacion || t.plan,
            pagado_total: extra[t.id]?.pagado_total ?? null,
            n_pagos: extra[t.id]?.n_pagos ?? 0,
            salud: extra[t.id]?.salud || null,
            uso_semanal: extra[t.id]?.uso_semanal || null,
            ultima_actividad: extra[t.id]?.ultima_actividad || null,
        })).sort((a, b) => String(a.nombre).localeCompare(String(b.nombre), 'es'));
        pintarListaTalleres();
        // En escritorio se abre el primero para no dejar el panel vacío
        const anchoEscritorio = window.matchMedia('(min-width: 960px)').matches;
        if (!tallerAbierto && !fichaPendiente && anchoEscritorio && talleresCache.length) abrirFicha360(talleresCache[0].id, { desdeLista: true, mostrar: false });
        else if (tallerAbierto) marcarTallerActivo();
    } catch (e) {
        cont.innerHTML = `<p class="res-vacio-chico">No se pudo cargar la lista: ${esc(e.message)}</p>`;
    }
}

function filtrarTalleres(filtro) {
    filtroTalleres = filtro;
    document.querySelectorAll('.tal-filtros button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filtro === filtro)));
    pintarListaTalleres();
}

function cumpleFiltro(t, filtro) {
    const dias = diasHasta(t.fecha_vencimiento);
    if (filtro === 'activos') return t.estado_pago === 'activo';
    if (filtro === 'suspendidos') return t.estado_pago !== 'activo';
    if (filtro === 'por_vencer') return t.estado_pago === 'activo' && dias !== null && dias <= DIAS_POR_VENCER;
    return true;
}

function pintarListaTalleres() {
    ['todos', 'activos', 'por_vencer', 'suspendidos'].forEach(f =>
        elModal(`tal-n-${f}`).textContent = talleresCache.filter(t => cumpleFiltro(t, f)).length);
    const q = (elModal('tal-buscar').value || '').trim().toLowerCase();
    const lista = talleresCache.filter(t => cumpleFiltro(t, filtroTalleres) &&
        (!q || `${t.nombre} ${t.email}`.toLowerCase().includes(q)));
    const cont = elModal('lista-talleres');
    if (!lista.length) {
        cont.innerHTML = `<p class="res-vacio-chico">${talleresCache.length ? 'Ningún taller coincide con la búsqueda o el filtro.' : 'Todavía no hay talleres registrados.'}</p>`;
        return;
    }
    cont.innerHTML = lista.map(t => {
        const dias = diasHasta(t.fecha_vencimiento);
        let estado;
        if (t.estado_pago !== 'activo') estado = '<span class="res-salud suspendido"><i></i>Suspendido</span>';
        else if (dias !== null && dias < 0) estado = '<span class="res-salud baja"><i></i>Vencido</span>';
        else if (dias !== null && dias <= DIAS_POR_VENCER) estado = `<span class="res-salud inactivo"><i></i>Vence en ${dias} día${dias === 1 ? '' : 's'}</span>`;
        else if (t.salud === 'bajando') estado = '<span class="res-salud baja"><i></i>Uso bajando</span>';
        else estado = '<span class="res-salud ok"><i></i>Activo</span>';
        return `<button type="button" class="tal-item" role="listitem" data-id="${esc(t.id)}" onclick="abrirFicha360('${esc(t.id)}')">
            <span class="res-av">${esc(iniciales(t.nombre))}</span>
            <span class="tal-item-txt"><b>${esc(t.nombre)}</b>
                <span class="tal-item-meta"><span class="res-plan">${esc(t.plan_nombre || t.plan_codigo || 'Sin plan')}</span><span>${esc(t.periodo || '')}</span><span>Vence ${fechaCorta(t.fecha_vencimiento)}</span></span></span>
            <span class="tal-item-der">${estado}${t.pagado_total !== null ? `<span class="res-tenue">${dinero(t.pagado_total)} pagado</span>` : ''}</span>
        </button>`;
    }).join('');
    marcarTallerActivo();
}

function marcarTallerActivo() {
    document.querySelectorAll('.tal-item').forEach(b => b.classList.toggle('activo', b.dataset.id === String(tallerAbierto)));
}

// --- Registrar un taller nuevo (formulario en modal) ---
function modalNuevoTaller() {
    const opcionesPlan = planesCache.length
        ? planesCache.map(p => `<option value="${esc(p.codigo)}">${esc(p.nombre)}</option>`).join('')
        : '<option value="">Sin planes (ejecuta el SQL de planes)</option>';
    const html = `
        <div class="adm-rejilla-2">
            <label class="adm-campo-ancho">Nombre del taller<input type="text" id="nuevo_nombre" maxlength="80" placeholder="Ej. Lubricadora El Pana"></label>
            <label>Correo del dueño<input type="email" id="nuevo_email" placeholder="dueno@correo.com" autocomplete="off"></label>
            <label>Contraseña inicial<input type="text" id="nuevo_pass" minlength="6" placeholder="Mínimo 6 caracteres" autocomplete="off">
                <span class="adm-ayuda">Compártela con el dueño; podrá usarla para entrar.</span></label>
            <label>Plan<select id="nuevo_plan_codigo">${opcionesPlan}</select></label>
            <label>Periodo de pago<select id="nuevo_plan">
                <option value="mensual">Mensual</option><option value="trimestral">Trimestral</option><option value="anual">Anual</option></select></label>
        </div>`;
    abrirModal('Registrar taller', html, crearTaller, false, 'Crear taller');
    if (planesCache.length) elModal('nuevo_plan_codigo').value = planesCache[planesCache.length - 1].codigo;
}

async function crearTaller() {
    const req = {
        nombre_taller: elModal("nuevo_nombre").value.trim(),
        email_jefe: elModal("nuevo_email").value.trim(),
        password_jefe: elModal("nuevo_pass").value,
        plan: elModal("nuevo_plan").value,               // columna antigua (periodo)
        periodo_facturacion: elModal("nuevo_plan").value
    };
    const planCodigo = elModal("nuevo_plan_codigo").value;
    if (planCodigo) req.plan_codigo = planCodigo;   // vacío = migración de planes aún no ejecutada
    if (!req.nombre_taller || !req.email_jefe || !req.password_jefe) { showToast("Completa el nombre, el correo y la contraseña.", "error"); return; }
    if (req.password_jefe.length < 6) { showToast("La contraseña debe tener al menos 6 caracteres.", "error"); return; }

    const btn = elModal('modal-btn-confirmar');
    btn.disabled = true;
    try {
        const res = await fetch("/admin/talleres", { method: "POST", headers: cabeceraAdmin(true), body: JSON.stringify(req) });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const detalle = data.detail ? (typeof data.detail === 'string' ? data.detail : 'Revisa los datos del formulario.') : data.mensaje;
            showToast(detalle || `Error ${res.status}`, "error");
            return;
        }
        // "parcial": el taller se creó pero el usuario del dueño falló
        mostrarAviso(data.mensaje || "Taller registrado.", data.status === 'parcial' ? 'warning' : 'success',
                     data.status === 'parcial' ? 'Taller creado a medias' : 'Taller registrado');
        tallerAbierto = data.taller_id || tallerAbierto;
        await cargarTalleres();
        if (data.taller_id) abrirFicha360(data.taller_id);
        cargarDashboard();
    } catch {
        showToast("Error de conexión al servidor.", "error");
    } finally {
        btn.disabled = false;
    }
}

// --- Agregar un usuario supervisor al taller ---
function modalAgregarUsuario(id) {
    const t = talleresCache.find(x => String(x.id) === String(id));
    const html = `
        <p class="adm-modal-sub">${t ? `Podrá entrar a ${esc(t.nombre)} con este correo.` : 'Podrá entrar al taller con este correo.'}</p>
        <label>Correo del usuario<input type="email" id="modal_user_email" placeholder="usuario@correo.com" autocomplete="off"></label>
        <label>Contraseña<input type="text" id="modal_user_pass" placeholder="Mínimo 6 caracteres" autocomplete="off"></label>`;
    abrirModal("Agregar usuario", html, async () => {
        const email = elModal("modal_user_email").value.trim();
        const pass = elModal("modal_user_pass").value;
        if (!email || !pass) { showToast("Completa el correo y la contraseña.", "error"); return; }
        if (pass.length < 6) { showToast("La contraseña debe tener al menos 6 caracteres.", "error"); return; }
        const btn = elModal('modal-btn-confirmar');
        btn.disabled = true;
        try {
            const res = await fetch(`/admin/talleres/${encodeURIComponent(id)}/usuarios`, {
                method: "POST", headers: cabeceraAdmin(true),
                body: JSON.stringify({ email, password: pass, rol: "supervisor" })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) { showToast(typeof data.detail === 'string' ? data.detail : "No se pudo crear el usuario.", "error"); return; }
            mostrarAviso(`${email} ya puede entrar al taller.`, "success", "Usuario agregado");
        } catch {
            showToast("Error de conexión al servidor.", "error");
        } finally {
            btn.disabled = false;
        }
    }, false, 'Agregar usuario');
}

// --- Suspender / reactivar (siempre con confirmación) ---
function suspender(id) {
    const t = talleresCache.find(x => String(x.id) === String(id));
    confirmarAccion({
        titulo: `¿Suspender ${t ? t.nombre : 'este taller'}?`,
        mensaje: 'El taller no podrá usar el sistema hasta que lo reactives o registres un pago. Sus datos no se borran.',
        textoBoton: 'Suspender', peligro: true,
        alConfirmar: () => cambiarEstadoTaller(id, 'suspendido', 'Taller suspendido', `${t ? t.nombre : 'El taller'} quedó suspendido.`)
    });
}

function reactivar(id) {
    const t = talleresCache.find(x => String(x.id) === String(id));
    confirmarAccion({
        titulo: `¿Reactivar ${t ? t.nombre : 'este taller'}?`,
        mensaje: 'Vuelve a tener acceso con su fecha de vencimiento actual. Si te pagó, mejor usa "Registrar pago": reactiva y deja constancia del cobro.',
        textoBoton: 'Reactivar',
        alConfirmar: () => cambiarEstadoTaller(id, 'activo', 'Taller reactivado', `${t ? t.nombre : 'El taller'} vuelve a estar activo.`)
    });
}

async function cambiarEstadoTaller(id, estado, titulo, mensaje) {
    try {
        const res = await fetch(`/admin/talleres/${encodeURIComponent(id)}`, {
            method: "PATCH", headers: cabeceraAdmin(true), body: JSON.stringify({ estado_pago: estado })
        });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            mostrarAviso(typeof data.detail === 'string' ? data.detail : `Error ${res.status}`, 'error');
            return;
        }
        mostrarAviso(mensaje, estado === 'activo' ? 'success' : 'info', titulo);
        await cargarTalleres();
        if (String(tallerAbierto) === String(id)) abrirFicha360(id, { desdeLista: true, mostrar: elModal('tal-layout').classList.contains('con-detalle') });
        cargarDashboard();
    } catch {
        mostrarAviso("Error de conexión al servidor.", 'error');
    }
}

// --- Ficha 360° ---
// mostrar = false: carga la ficha sin tapar la lista en el celular (al volver a la sección)
async function abrirFicha360(id, { desdeLista = false, mostrar = true } = {}) {
    if (elModal('sec-talleres').hidden) {
        fichaPendiente = id;
        cambiarSeccion('sec-talleres');   // carga la lista y abre esta ficha
        return;
    }
    tallerAbierto = id;
    marcarTallerActivo();
    if (mostrar) elModal('tal-layout').classList.add('con-detalle');   // en el celular la ficha reemplaza a la lista
    if (!desdeLista && !window.matchMedia('(min-width: 960px)').matches) window.scrollTo(0, 0);
    const cont = elModal('contenido-360');
    cont.innerHTML = '<p class="res-vacio-chico">Cargando la ficha del taller...</p>';
    try {
        const [resF, resP] = await Promise.all([
            fetch(`/admin/talleres/${encodeURIComponent(id)}/ficha-360`, { headers: cabeceraAdmin() }),
            fetch(`/admin/talleres/${encodeURIComponent(id)}/pagos`, { headers: cabeceraAdmin() }).catch(() => null)
        ]);
        if (!resF.ok) throw new Error();
        const data = await resF.json();
        const pagos = resP && resP.ok ? await resP.json() : { pagos: [], total: 0 };
        if (String(tallerAbierto) !== String(id)) return;   // el usuario ya eligió otro
        renderizarFicha360(data, pagos);
        reanimar(cont);
    } catch {
        cont.innerHTML = '<p class="res-vacio-chico">No se pudo cargar la ficha de este taller.</p>';
    }
}

function cerrarVista360() {
    // En el celular vuelve a la lista; en escritorio la ficha sigue a la derecha
    elModal('tal-layout')?.classList.remove('con-detalle');
}

const NOMBRE_METODO = { efectivo: 'Efectivo', transferencia: 'Transferencia', deposito: 'Depósito', tarjeta: 'Tarjeta', otro: 'Otro' };

function renderizarFicha360(data, pagos) {
    const t = data.taller, u = data.uso, a = data.actividad;
    const fila = talleresCache.find(x => String(x.id) === String(t.id)) || {};
    const activo = t.estado_pago === 'activo';
    const dias = diasHasta(t.fecha_vencimiento);
    let estadoVence = '';
    if (activo && dias !== null) estadoVence = dias < 0 ? `<span class="res-chip rojo">Vencido hace ${-dias} día${dias === -1 ? '' : 's'}</span>`
        : dias <= DIAS_POR_VENCER ? `<span class="res-chip amarillo">${dias === 0 ? 'Vence hoy' : `Faltan ${dias} día${dias === 1 ? '' : 's'}`}</span>` : '';
    const precio = fila.plan_codigo ? precioDe({ plan_codigo: fila.plan_codigo, periodo: t.periodo }, t.periodo || 'mensual') : 0;
    const SALUD = { activo: ['Uso estable', 'ok'], bajando: ['Uso bajando', 'baja'], inactivo: ['Sin uso reciente', 'inactivo'] };
    const [txtSalud, clsSalud] = SALUD[fila.salud] || ['', ''];
    const ultima = a.ultima_actividad && a.ultima_actividad !== 'Sin actividad' ? haceCuanto(a.ultima_actividad) : 'Sin actividad registrada';

    const listaPagos = (pagos.pagos || []).slice(0, 6).map(p => `
        <li><span class="tal-pago-fecha">${fechaCorta(p.fecha_pago)}</span>
            <span class="tal-pago-txt"><b>${esc(NOMBRE_METODO[p.metodo] || p.metodo)}</b><span>${esc(p.periodo)}${p.cubre_hasta ? `, cubre hasta ${fechaCorta(p.cubre_hasta)}` : ''}${p.nota ? `. ${esc(p.nota)}` : ''}</span></span>
            <span class="res-monto">${dinero(p.monto)}</span></li>`).join('');
    const avisoPagos = pagos.falta_migracion
        ? `<p class="res-vacio-chico">El historial aparecerá cuando se ejecute la migración ${esc(pagos.falta_migracion)}.</p>`
        : '<p class="res-vacio-chico">Aún no hay pagos registrados para este taller.</p>';

    elModal("contenido-360").innerHTML = `
    <div class="f360">
        <header class="f360-cab">
            <span class="res-av f360-av">${esc(iniciales(t.nombre))}</span>
            <div class="f360-titulo">
                <h2>${esc(t.nombre)}</h2>
                <span class="res-tenue">${esc(t.email || '')}</span>
                <div class="f360-chips">
                    <span class="res-salud ${activo ? 'ok' : 'suspendido'}"><i></i>${activo ? 'Activo' : 'Suspendido'}</span>
                    <span class="res-plan">Plan ${esc(t.plan_codigo ? nombrePlan(t.plan_codigo) : t.plan)}</span>
                    <span class="res-plan">Pago ${esc(t.periodo || '')}</span>
                    ${txtSalud ? `<span class="res-salud ${clsSalud}"><i></i>${txtSalud}</span>` : ''}
                </div>
            </div>
        </header>

        <div class="f360-acciones">
            <button type="button" class="btn btn-primario" onclick="modalRegistrarPago('${esc(t.id)}')">Registrar pago</button>
            <button type="button" class="btn-chico" onclick="modalModulos('${esc(t.id)}')">Módulos</button>
            <button type="button" class="btn-chico" onclick="modalAgregarUsuario('${esc(t.id)}')">Agregar usuario</button>
            ${activo
                ? `<button type="button" class="btn-chico adm-btn-peligro" onclick="suspender('${esc(t.id)}')">Suspender</button>`
                : `<button type="button" class="btn-chico" onclick="reactivar('${esc(t.id)}')">Reactivar</button>`}
            <!-- Preparado para la futura función "Entrar como este taller" -->
            <button type="button" class="btn-chico f360-impersonar" onclick="mostrarAviso('La función Entrar como este taller está en desarrollo.', 'info')">Entrar como este taller</button>
        </div>

        <div class="f360-kpis">
            <div><span>Órdenes</span><b>${u.reparaciones}</b></div>
            <div><span>Vehículos</span><b>${u.vehiculos}</b></div>
            <div><span>Clientes</span><b>${u.clientes}</b></div>
            <div><span>Usos de IA hoy</span><b>${a.ia_hoy}</b></div>
        </div>

        <div class="f360-rejilla">
            <section class="f360-bloque">
                <h3>Suscripción</h3>
                <dl class="f360-datos">
                    <div><dt>Vence</dt><dd>${fechaCorta(t.fecha_vencimiento)} ${estadoVence}</dd></div>
                    <div><dt>Cobro por periodo</dt><dd>${precio ? dinero(precio) : 'Sin precio'}</dd></div>
                    <div><dt>Te ha pagado</dt><dd>${dinero(pagos.total || 0)} <span class="res-tenue">en ${(pagos.pagos || []).length} pago${(pagos.pagos || []).length === 1 ? '' : 's'}</span></dd></div>
                    <div><dt>Cliente desde</dt><dd>${t.created_at && t.created_at !== 'Desconocida' ? fechaCorta(t.created_at) : 'Sin fecha'}</dd></div>
                </dl>
            </section>
            <section class="f360-bloque">
                <h3>Uso</h3>
                <dl class="f360-datos">
                    <div><dt>Última actividad</dt><dd>${esc(ultima)}</dd></div>
                </dl>
                ${fila.uso_semanal ? `<div class="f360-uso">${minigrafico(fila.uso_semanal, clsSalud || 'ok').replace('width="104" height="28"', 'width="100%" height="56" preserveAspectRatio="none"').replace('viewBox="0 0 104 28"', 'viewBox="0 0 104 28"')}
                    <span class="res-tenue">Órdenes por semana, últimas 8 semanas</span></div>` : ''}
            </section>
            <section class="f360-bloque f360-ancho">
                <h3>Historial de pagos</h3>
                ${listaPagos ? `<ul class="tal-pagos">${listaPagos}</ul>` : avisoPagos}
            </section>
            <section class="f360-bloque f360-ancho">
                <h3>Módulos activos <span class="res-tenue">${(t.modulos || []).length}</span></h3>
                <div class="f360-modulos">${(t.modulos || []).map(m => `<span class="res-plan">${esc(m)}</span>`).join('') || '<span class="res-tenue">Solo funciones básicas</span>'}</div>
            </section>
        </div>
        <p class="f360-id res-tenue">ID del taller: ${esc(t.id)}</p>
    </div>`;
}

// Acceso directo desde el Resumen
function abrirMonitorIA() { cambiarSeccion('sec-monitor'); }

// ==========================================================================
// MONITOR DE IA
//   Cola de mensajes de Geor IA con filtros. "Reprocesar" solo aparece en los
//   que fallaron o se bloquearon (el servidor también lo impide en los demás).
// ==========================================================================
let filtroCola = 'todos';

// Explicación en lenguaje simple de cada estado y si conviene reintentar
function explicarEstado(estado) {
    const e = String(estado || '');
    if (e === 'Procesado') return { tipo: 'ok', etiqueta: 'Procesado', ayuda: '' };
    if (e === 'Pendiente' || e === 'Procesando') return { tipo: 'espera', etiqueta: e === 'Pendiente' ? 'En espera' : 'Procesando', ayuda: 'Geor lo procesará en unos segundos.' };
    if (e.includes('IA no disponible')) return { tipo: 'error', etiqueta: 'IA no disponible', reintentar: true,
        ayuda: 'Geor no respondió a tiempo. Reprocesar suele funcionar.' };
    if (e.includes('No clasificable')) return { tipo: 'error', etiqueta: 'No se entendió', reintentar: true,
        ayuda: 'Geor no supo si era un registro. Revisa el texto: si era una pregunta, no hace falta reprocesarlo.' };
    if (e.startsWith('Error de Formato')) return { tipo: 'error', etiqueta: 'Datos incompletos', reintentar: true,
        ayuda: 'La IA devolvió datos incompletos. Reprocesar suele funcionar.' };
    if (e.includes('Repuesto no encontrado')) return { tipo: 'error', etiqueta: 'Repuesto no encontrado', reintentar: true,
        ayuda: 'Menciona un repuesto que no está en el inventario del taller. Agrégalo antes de reprocesar.' };
    if (e.includes('Duplicado')) return { tipo: 'bloqueado', etiqueta: 'Duplicado', reintentar: true, confirmar: true,
        ayuda: 'Ya existía un registro igual. Reprocesar podría crear una orden repetida.' };
    if (e.includes('Ya pendiente')) return { tipo: 'bloqueado', etiqueta: 'Orden ya abierta', reintentar: true, confirmar: true,
        ayuda: 'El vehículo ya tenía una orden abierta en ese momento.' };
    if (e.startsWith('Error')) return { tipo: 'error', etiqueta: 'Error', reintentar: true, ayuda: e };
    if (e.startsWith('Bloqueado')) return { tipo: 'bloqueado', etiqueta: 'Bloqueado', reintentar: true, confirmar: true, ayuda: e };
    return { tipo: 'espera', etiqueta: e || 'Sin estado', ayuda: '' };
}

// "Hoy, 9:15", "Ayer, 21:40" o "26 ago 2026, 06:49" en la hora de este equipo
function fechaCola(ts) {
    if (!ts) return 'Sin fecha';
    const d = new Date(String(ts).replace(' ', 'T') + (/[zZ]|[+-]\d\d:?\d\d$/.test(ts) ? '' : 'Z'));
    if (isNaN(d)) return String(ts);
    const hora = d.toLocaleTimeString('es-EC', { hour: '2-digit', minute: '2-digit' });
    const hoy = new Date(); const ayer = new Date(); ayer.setDate(hoy.getDate() - 1);
    if (d.toDateString() === hoy.toDateString()) return `Hoy, ${hora}`;
    if (d.toDateString() === ayer.toDateString()) return `Ayer, ${hora}`;
    return `${d.getDate()} ${MESES_CORTOS[d.getMonth()]} ${d.getFullYear()}, ${hora}`;
}

function filtrarCola(filtro) {
    filtroCola = filtro;
    document.querySelectorAll('.mon-filtros button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filtro === filtro)));
    cargarColaIA();
}

async function cargarColaIA() {
    const cont = elModal("lista-cola-ia");
    cont.innerHTML = '<p class="res-vacio-chico">Cargando mensajes...</p>';
    cargarDashboard().then(() => {
        elModal('mon-hoy').textContent = elModal('dash-ai-today').textContent;
        const e = elModal('dash-errors').textContent;
        elModal('mon-errores-hoy').textContent = e;
        elModal('mon-errores-hoy').classList.toggle('rojo', Number(e) > 0);
    });
    try {
        const res = await fetch(`/admin/cola?filtro=${encodeURIComponent(filtroCola)}&limite=${filtroCola === 'todos' ? 50 : 200}`, { headers: cabeceraAdmin() });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
        const c = data.conteos || {};
        [['errores', 'mon-errores'], ['bloqueados', 'mon-bloqueados']].forEach(([k, id]) => {
            elModal(id).textContent = c[k] ?? '0';
            elModal(id).classList.toggle(k === 'errores' ? 'rojo' : 'amarillo', (c[k] || 0) > 0);
        });
        ['errores', 'bloqueados', 'pendientes'].forEach(k => elModal(`mon-n-${k}`).textContent = c[k] ?? '0');
        elModal('mon-actualizado').textContent = `Actualizado ${new Date().toLocaleTimeString('es-EC', { hour: '2-digit', minute: '2-digit' })}`;

        const mensajes = data.mensajes || [];
        if (!mensajes.length) {
            const vacio = { todos: 'Todavía no hay mensajes en la cola.', errores: 'No hay mensajes con error. Todo se procesó bien.',
                            bloqueados: 'No hay mensajes bloqueados.', pendientes: 'No hay mensajes esperando: la cola está al día.' }[filtroCola];
            cont.innerHTML = `<div class="tal-vacio mon-vacio"><b>${vacio}</b></div>`;
            return;
        }
        cont.innerHTML = mensajes.map(m => {
            const info = explicarEstado(m.estado);
            const taller = m.talleres?.nombre || 'Taller desconocido';
            return `
            <article class="mon-item ${info.tipo}">
                <span class="res-av">${esc(iniciales(taller))}</span>
                <div class="mon-cuerpo">
                    <div class="mon-meta">
                        <b>${esc(taller)}</b>
                        <span class="res-tenue">${esc(fechaCola(m.fecha_hora))}</span>
                        <span class="mon-estado ${info.tipo}" title="${esc(m.estado)}"><i></i>${esc(info.etiqueta)}</span>
                    </div>
                    <p class="mon-texto">${esc(m.texto)}</p>
                    ${info.ayuda && info.tipo !== 'ok' ? `<p class="mon-ayuda">${esc(info.ayuda)}</p>` : ''}
                </div>
                ${info.reintentar ? `<button type="button" class="btn-chico mon-btn" onclick="reprocesarMensaje(${Number(m.id)}, ${info.confirmar ? 'true' : 'false'})">
                    <svg class="icono" viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/></svg>Reprocesar</button>` : ''}
            </article>`;
        }).join('');
    } catch (e) {
        cont.innerHTML = `<p class="res-vacio-chico">No se pudo cargar la cola: ${esc(e.message)}</p>`;
    }
}

async function reprocesarMensaje(id, confirmar = false) {
    const enviar = async () => {
        try {
            const res = await fetch(`/admin/cola/${encodeURIComponent(id)}/reprocesar`, { method: "POST", headers: cabeceraAdmin() });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) { mostrarAviso(typeof data.detail === 'string' ? data.detail : `Error ${res.status}`, 'error'); return; }
            mostrarAviso('El mensaje volvió a la cola. Geor lo procesará en unos segundos; actualiza para ver el resultado.', 'success', 'Enviado a reprocesar');
            cargarColaIA();
        } catch {
            mostrarAviso('Error de conexión al servidor.', 'error');
        }
    };
    if (!confirmar) return enviar();
    confirmarAccion({
        titulo: '¿Reprocesar este mensaje?',
        mensaje: 'Se bloqueó para evitar un registro repetido. Si lo reprocesas, revisa después que no haya quedado una orden duplicada.',
        textoBoton: 'Reprocesar', alConfirmar: enviar
    });
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

// ==========================================================================
// MÓDULOS DE UN TALLER (modal)
//   Cada módulo: "Según plan", "Activar" o "Quitar" (excepción solo para este
//   taller, con fecha de fin opcional). Quitar no borra datos: solo los oculta.
// ==========================================================================
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
        mostrarAviso(e.message, "error");
        return;
    }
    catalogoModulos = catalogoModulos.length ? catalogoModulos : data.modulos.map(m => ({ clave: m.clave, nombre: m.nombre, requiere: m.requiere || [] }));
    window._planesModal = data.planes;

    const filas = data.modulos.map(m => {
        const opcion = (valor, texto) => `
            <label class="mod-opcion"><input type="radio" name="mod-${esc(m.clave)}" value="${valor}" ${m.estado === valor ? 'checked' : ''}
                onchange="ajustarFilaModulo(this)"><span>${texto}</span></label>`;
        let estado;
        if (m.activo) estado = '<span class="res-salud ok"><i></i>Activo</span>';
        else if (m.bloqueado) estado = `<span class="res-salud inactivo"><i></i>Falta ${esc(m.requiere_nombres.join(', '))}</span>`;
        else estado = '<span class="res-salud inactivo mod-apagado"><i></i>Inactivo</span>';
        return `
        <div class="mod-fila" data-clave="${esc(m.clave)}" data-en-plan="${m.en_plan ? '1' : '0'}">
            <div class="mod-info">
                <div class="mod-titulo"><b>${esc(m.nombre)}</b>${estado}${m.vencida ? '<span class="res-chip amarillo">Excepción vencida</span>' : ''}</div>
                <p>${esc(m.descripcion)}${m.requiere_nombres.length ? ` Requiere: ${esc(m.requiere_nombres.join(', '))}.` : ''}</p>
            </div>
            <div class="mod-control" role="radiogroup" aria-label="${esc(m.nombre)}">
                ${opcion('plan', `Según plan<small class="mod-txt-plan">${m.en_plan ? 'incluido' : 'no incluido'}</small>`)}
                ${opcion('activado', 'Activar')}
                ${opcion('desactivado', 'Quitar')}
            </div>
            <div class="mod-excepcion">
                <label>Hasta (opcional)<input type="date" class="inp-hasta" value="${esc(m.hasta || '')}" min="${hoyISO()}"></label>
                <label>Nota (opcional)<input type="text" class="inp-nota" maxlength="300" value="${esc(m.nota)}" placeholder="Ej. Prueba gratis de 30 días"></label>
            </div>
        </div>`;
    }).join('');

    const historial = (data.historial || []).map(h => `
        <li><span class="hist-fecha">${esc(formatearFecha(h.fecha))}</span>
            <span><b>${esc(TEXTO_ACCION[h.accion] || h.accion)}</b>${h.modulo ? ' ' + esc(nombreModulo(h.modulo)) : ''}${h.detalle ? ': ' + esc(h.detalle) : ''}
            ${h.admin_email ? `<span class="hist-quien">${esc(h.admin_email)}</span>` : ''}</span></li>`).join('');

    const html = `
        <div class="mod-cabecera">
            <label>Plan del taller
                <select id="sel-plan-taller" onchange="refrescarEtiquetasPlan()">
                    ${data.planes.map(p => `<option value="${esc(p.codigo)}" ${p.codigo === data.taller.plan_codigo ? 'selected' : ''}>${esc(p.nombre)}</option>`).join('')}
                </select></label>
            <p class="adm-ayuda">"Según plan" sigue lo que incluye el plan. "Activar" o "Quitar" es una excepción solo para este taller;
                con fecha, vuelve sola a lo del plan cuando vence. Quitar un módulo no borra datos: solo los oculta.</p>
        </div>
        <div class="mod-lista">${filas}</div>
        <details class="mod-historial">
            <summary>Últimos cambios</summary>
            <ul class="historial-modulos">${historial || '<li><span class="res-tenue">Sin cambios registrados.</span></li>'}</ul>
        </details>`;

    abrirModal(`Módulos de ${data.taller.nombre}`, html, () => guardarModulos(tallerId), true, 'Guardar módulos');
    document.querySelectorAll('#modal-body .mod-fila').forEach(f => ajustarFilaModulo(f.querySelector('input[type=radio]:checked')));
}

// Fecha y nota solo se muestran cuando hay excepción
function ajustarFilaModulo(radio) {
    if (!radio) return;
    const fila = radio.closest('.mod-fila');
    const valor = fila.querySelector('input[type=radio]:checked').value;
    fila.classList.toggle('con-excepcion', valor !== 'plan');
    fila.dataset.estado = valor;
}

// Al cambiar de plan, "Según plan (incluido / no incluido)" se actualiza
function refrescarEtiquetasPlan() {
    const codigo = elModal('sel-plan-taller').value;
    const plan = (window._planesModal || []).find(p => p.codigo === codigo) || { modulos: [] };
    document.querySelectorAll('#modal-body .mod-fila').forEach(f => {
        const incluido = plan.modulos.includes(f.dataset.clave);
        f.dataset.enPlan = incluido ? '1' : '0';
        f.querySelector('.mod-txt-plan').textContent = incluido ? 'incluido' : 'no incluido';
    });
}

async function guardarModulos(tallerId) {
    const ajustes = [...document.querySelectorAll('#modal-body .mod-fila')].map(f => ({
        modulo: f.dataset.clave,
        estado: f.querySelector('input[type=radio]:checked').value,
        hasta: f.querySelector('.inp-hasta').value || null,
        nota: f.querySelector('.inp-nota').value.trim()
    }));
    const btn = elModal('modal-btn-confirmar');
    btn.disabled = true;
    try {
        const res = await fetch(`/admin/talleres/${encodeURIComponent(tallerId)}/modulos`, {
            method: "PUT", headers: cabeceraAdmin(true),
            body: JSON.stringify({ plan_codigo: elModal('sel-plan-taller').value, ajustes })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            showToast(typeof data.detail === 'string' ? data.detail : `Error ${res.status}`, "error");
            return;
        }
        mostrarAviso(data.cambios ? `Se guardaron ${data.cambios} cambio${data.cambios > 1 ? 's' : ''}.` : 'No había cambios que guardar.',
                     data.cambios ? 'success' : 'info', data.cambios ? 'Módulos actualizados' : 'Sin cambios');
        if (!elModal('sec-talleres').hidden) {
            await cargarTalleres();
            if (String(tallerAbierto) === String(tallerId)) abrirFicha360(tallerId, { desdeLista: true, mostrar: elModal('tal-layout').classList.contains('con-detalle') });
        }
        cargarDashboard();
    } catch {
        showToast("Error de conexión al servidor.", "error");
    } finally {
        btn.disabled = false;
    }
}

function formatearFecha(valor) {
    const d = new Date(String(valor || '').replace(' ', 'T'));
    if (isNaN(d)) return String(valor || '');
    return `${d.getDate()} ${MESES_CORTOS[d.getMonth()]} ${d.getFullYear()}, ${d.toLocaleTimeString('es-EC', { hour: '2-digit', minute: '2-digit' })}`;
}

// ==========================================================================
// PLANES Y MÓDULOS (sección)
//   Una tarjeta por plan: nombre, precios por periodo (con su equivalente
//   mensual y el ahorro), módulos con interruptores y guardar solo si cambió.
// ==========================================================================
function abrirPlanes() { cambiarSeccion('sec-planes'); }

// Cuántos talleres tiene cada plan y cuánto aportan al mes (del Resumen)
async function estadisticasPlanes() {
    if (!ultimoResumen) {
        try {
            const res = await fetch('/admin/resumen?meses=6', { headers: cabeceraAdmin() });
            if (res.ok) ultimoResumen = await res.json();
        } catch { /* sin estadísticas: las tarjetas funcionan igual */ }
    }
    return Object.fromEntries((ultimoResumen?.planes || []).map(p => [p.codigo, p]));
}

async function cargarVistaPlanes() {
    const cont = elModal("lista-planes");
    cont.innerHTML = '<p class="res-vacio-chico">Cargando planes...</p>';
    const ok = await cargarPlanes();
    if (ok !== true) { cont.innerHTML = `<div class="res-aviso">${esc(ok)}</div>`; return; }
    const stats = await estadisticasPlanes();
    cont.innerHTML = planesCache.map(p => {
        const s = stats[p.codigo];
        const precio = (periodo, etiqueta) => `
            <label class="pla-precio"><span>${etiqueta}</span>
                <span class="pla-input-dinero"><i>$</i><input type="number" min="0" step="0.01" class="inp-precio" data-periodo="${periodo}"
                    value="${Number(p[`precio_${periodo}`]).toFixed(2)}" oninput="cambioEnPlan(this)"></span>
                <small class="pla-equiv" data-equiv="${periodo}"></small></label>`;
        return `
        <section class="pla-card res-card" data-codigo="${esc(p.codigo)}">
            <header class="pla-cab">
                <label class="pla-nombre"><span class="solo-lector">Nombre del plan</span>
                    <input type="text" class="inp-nombre" value="${esc(p.nombre)}" maxlength="40" oninput="cambioEnPlan(this)"></label>
                <div class="pla-stats">
                    <span class="res-plan">${s ? `${s.talleres} taller${s.talleres === 1 ? '' : 'es'}` : '0 talleres'}</span>
                    ${s ? `<span class="res-tenue">${dinero(s.mrr)} al mes</span>` : ''}
                </div>
            </header>
            <div class="pla-precios">
                ${precio('mensual', 'Mensual')}${precio('trimestral', 'Trimestral')}${precio('anual', 'Anual')}
            </div>
            <div class="pla-modulos">
                <span class="res-eti">Módulos incluidos <b class="pla-conteo"></b></span>
                ${catalogoModulos.map(m => `
                <label class="pla-switch" title="${esc(m.descripcion)}">
                    <span class="pla-switch-txt"><b>${esc(m.nombre)}</b>
                        <small>${esc(m.descripcion)}${m.requiere_nombres?.length ? ` Requiere: ${esc(m.requiere_nombres.join(', '))}.` : ''}</small></span>
                    <input type="checkbox" role="switch" value="${esc(m.clave)}" ${p.modulos.includes(m.clave) ? 'checked' : ''}
                        onchange="ajustarDependencias(this); cambioEnPlan(this)">
                    <i aria-hidden="true"></i>
                </label>`).join('')}
            </div>
            <footer class="pla-pie">
                <span class="pla-estado res-tenue">Sin cambios</span>
                <button type="button" class="btn-chico" onclick="descartarPlan(this)" disabled>Descartar</button>
                <button type="button" class="btn btn-primario" onclick="guardarPlan('${esc(p.codigo)}', this)" disabled>Guardar plan</button>
            </footer>
        </section>`;
    }).join('') || '<p class="res-vacio-chico">No hay planes configurados.</p>';
    document.querySelectorAll('.pla-card').forEach(c => { c.dataset.original = JSON.stringify(leerPlan(c)); actualizarCardPlan(c); });
}

// Lo que dice la tarjeta ahora mismo (para comparar con lo guardado y para enviar)
function leerPlan(card) {
    const precio = p => Math.round(parseFloat(card.querySelector(`.inp-precio[data-periodo="${p}"]`).value || '0') * 100) / 100;
    return {
        nombre: card.querySelector('.inp-nombre').value.trim(),
        precio_mensual: precio('mensual'), precio_trimestral: precio('trimestral'), precio_anual: precio('anual'),
        modulos: [...card.querySelectorAll('input[type=checkbox]:checked')].map(c => c.value)
    };
}

function cambioEnPlan(el) { actualizarCardPlan(el.closest('.pla-card')); }

// Equivalente mensual, ahorro, conteo de módulos y botones según haya cambios
function actualizarCardPlan(card) {
    const datos = leerPlan(card);
    const meses = { trimestral: 3, anual: 12 };
    Object.entries(meses).forEach(([periodo, n]) => {
        const el = card.querySelector(`[data-equiv="${periodo}"]`);
        const mensual = datos[`precio_${periodo}`] / n;
        const ahorro = datos.precio_mensual ? Math.round((1 - mensual / datos.precio_mensual) * 100) : 0;
        el.textContent = datos[`precio_${periodo}`] ? `${dinero(mensual)} al mes${ahorro > 0 ? `, ahorra ${ahorro}%` : ''}` : '';
    });
    card.querySelector('[data-equiv="mensual"]').textContent = datos.precio_mensual ? 'Precio base' : '';
    card.querySelector('.pla-conteo').textContent = `${datos.modulos.length} de ${catalogoModulos.length}`;
    const cambiado = JSON.stringify(datos) !== card.dataset.original;
    card.classList.toggle('con-cambios', cambiado);
    card.querySelector('.pla-estado').textContent = cambiado ? 'Cambios sin guardar' : 'Sin cambios';
    card.querySelectorAll('.pla-pie button').forEach(b => b.disabled = !cambiado);
}

function descartarPlan(btn) {
    const card = btn.closest('.pla-card');
    const o = JSON.parse(card.dataset.original);
    card.querySelector('.inp-nombre').value = o.nombre;
    ['mensual', 'trimestral', 'anual'].forEach(p => card.querySelector(`.inp-precio[data-periodo="${p}"]`).value = o[`precio_${p}`].toFixed(2));
    card.querySelectorAll('input[type=checkbox]').forEach(c => c.checked = o.modulos.includes(c.value));
    actualizarCardPlan(card);
}

// Marcar un módulo marca sus requisitos; desmarcar un requisito desmarca a quien lo necesita
function ajustarDependencias(check) {
    const card = check.closest('.pla-card');
    const marcar = (clave, v) => { const c = card.querySelector(`input[type=checkbox][value="${clave}"]`); if (c) c.checked = v; };
    const mod = catalogoModulos.find(m => m.clave === check.value);
    if (check.checked) (mod.requiere || []).forEach(r => marcar(r, true));
    else catalogoModulos.filter(m => (m.requiere || []).includes(check.value)).forEach(m => marcar(m.clave, false));
}

async function guardarPlan(codigo, btn) {
    const card = btn.closest('.pla-card');
    const cuerpo = leerPlan(card);
    if (cuerpo.nombre.length < 2) { mostrarAviso('El nombre del plan debe tener al menos 2 letras.', 'error'); return; }
    const s = (await estadisticasPlanes())[codigo];
    const guardar = async () => {
        btn.disabled = true;
        try {
            const res = await fetch(`/admin/planes/${encodeURIComponent(codigo)}`, {
                method: "PUT", headers: cabeceraAdmin(true), body: JSON.stringify(cuerpo)
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const d = data.detail;
                mostrarAviso(typeof d === 'string' ? d : (Array.isArray(d) ? 'Revisa el nombre y los precios.' : `Error ${res.status}`), "error");
                return;
            }
            // Lo guardado pasa a ser el nuevo punto de comparación
            if (data.planes) planesCache = data.planes;
            else planesCache = planesCache.map(p => p.codigo === codigo ? { ...p, ...cuerpo } : p);
            card.dataset.original = JSON.stringify(cuerpo);
            actualizarCardPlan(card);
            llenarSelectPlanes();
            ultimoResumen = null;   // el MRR esperado cambia con los precios
            mostrarAviso(`El plan ${cuerpo.nombre} quedó guardado y ya se aplica a sus talleres.`, "success", "Plan guardado");
        } catch {
            mostrarAviso("Error de conexión al servidor.", "error");
        } finally {
            actualizarCardPlan(card);
        }
    };
    // Si el plan tiene talleres y se quitan módulos, se avisa antes
    const original = JSON.parse(card.dataset.original);
    const quitados = original.modulos.filter(m => !cuerpo.modulos.includes(m));
    if (s?.talleres && quitados.length) {
        confirmarAccion({
            titulo: `¿Quitar módulos del plan ${cuerpo.nombre}?`,
            mensaje: `${s.talleres} taller${s.talleres === 1 ? '' : 'es'} dejará${s.talleres === 1 ? '' : 'n'} de ver: ${quitados.map(nombreModulo).join(', ')}. Sus datos no se borran, solo se ocultan.`,
            textoBoton: 'Guardar plan', alConfirmar: async () => { cerrarModal(); await guardar(); }
        });
    } else {
        await guardar();
    }
}
