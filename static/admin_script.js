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

function mostrarModalPreparado(overlay, enfocar) {
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
    else if (id === 'sec-talleres') { cerrarVista360(); cargarTalleres(); }
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
        .map(a => ({ nivel: NIVEL[a.tipo] || 'azul', html: a.mensaje }));
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

function irARegistrarTaller() {
    cambiarSeccion('sec-talleres');
    setTimeout(() => elModal('nuevo_nombre')?.focus(), 80);
}

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
            cargarDashboard(); // Actualizar contador de errores y alertas
        } else {
            const detalle = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : data.mensaje;
            showToast("Error: " + detalle, "error");
        }
    } catch {
        showToast("Error de conexión al servidor.", "error");
    }
}

// --- ACCIONES CON MODAL PROPIO ---
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

// --- LÓGICA FICHA 360° ---
async function abrirFicha360(id) {
    const token = localStorage.getItem("admin_token");
    try {
        // Transición de vistas
        if (elModal('sec-talleres').hidden) cambiarSeccion('sec-talleres');
        document.getElementById("vista-principal").hidden = true;
        document.getElementById("vista-360-taller").hidden = false;
        window.scrollTo(0, 0);
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
    document.getElementById("vista-360-taller").hidden = true;
    document.getElementById("vista-principal").hidden = false;
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

// Accesos directos desde el Resumen
function abrirMonitorIA() { cambiarSeccion('sec-monitor'); }

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
        showToast(e.message, "error");
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
            showToast(typeof data.detail === 'string' ? data.detail : `Error ${res.status}`, "error");
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
function abrirPlanes() { cambiarSeccion('sec-planes'); }

async function cargarVistaPlanes() {
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
            showToast(typeof d === 'string' ? d : (Array.isArray(d) ? 'Revisa el nombre y los precios' : `Error ${res.status}`), "error");
            return;
        }
        planesCache = data.planes || planesCache;
        llenarSelectPlanes();
        showToast(`Plan ${cuerpo.nombre} guardado. Ya se aplica a sus talleres.`, "success");
    } catch {
        showToast("Error de conexión al servidor.", "error");
    } finally {
        btn.disabled = false;
    }
}
