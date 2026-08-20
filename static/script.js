// ==============================================================================
// Script del Taller Automotriz - Autotronic Solutions IA
// ==============================================================================

// Validar sesión activa al cargar
window.onload = function() {
    const token = localStorage.getItem("taller_token");
    if (token) {
        document.getElementById("login-container").style.display = "none";
        document.getElementById("app-container").style.display = "block";
    }

    // --- AJUSTE: permitir enviar con ENTER ---

    // Login: ENTER en correo o contraseña dispara iniciarSesion()
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

    // Mensaje: ENTER envía, SHIFT+ENTER permite salto de línea
    // (útil porque es un textarea de varias líneas, no un input simple)
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

    // --- AJUSTE: limpiar la última respuesta/notificación visible ---
    // Sin esto, la caja de notificación (creada dinámicamente la primera vez)
    // seguía en el DOM con el contenido de la última consulta, y al volver
    // a iniciar sesión se veía la respuesta de la sesión anterior.
    const cajaNotificacion = document.getElementById('caja-notificacion-ia');
    if (cajaNotificacion) {
        cajaNotificacion.innerHTML = "";
        cajaNotificacion.style.padding = "0";
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

        if (data.status === "éxito") {
            inputTexto.value = "";
            mostrarNotificacion(`${data.mensaje_bd}`, "success");
        }
        else if (data.status === "éxito_consulta") {
            inputTexto.value = "";
            mostrarNotificacion(`<b>Respuesta del Gerente IA:</b><br>${data.mensaje_bd}`, "info");
        }
        else {
            mostrarNotificacion(`Error del sistema: ${data.mensaje}`, "error");
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
            mostrarNotificacion("Error al generar el archivo de inventario.", "error");
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
            mostrarNotificacion("Error al generar el reporte diario.", "error");
        }
    } catch (error) {
        console.error("Error:", error);
        mostrarNotificacion("Error de conexion al descargar el reporte.", "error");
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

    // Si es respuesta analítica de la IA, traducimos el formato Markdown a HTML limpio con marked.js
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
