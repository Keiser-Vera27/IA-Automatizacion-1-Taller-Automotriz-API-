// ==========================================================================
// GENERADOR DE IMÁGENES (FICHAS DE SERVICIO)
// ==========================================================================
async function generarImagenFactura(orden) {
    // 1. Inyectar los datos básicos en la plantilla
    document.getElementById('orden-placa').innerText = orden.vehiculo || '---';
    document.getElementById('orden-cliente').innerText = orden.cliente || '---';
    
    // Formatear la fecha para que se vea legible
    const fecha = new Date(orden.fecha_hora);
    document.getElementById('orden-fecha').innerText = fecha.toLocaleDateString();
    
    // CORRECCIÓN: Usamos 'orden.oficial' que es como lo guarda tu base de datos actual
    document.getElementById('orden-tecnico').innerText = orden.oficial || 'No asignado';
    
    document.getElementById('orden-motivo').innerText = orden.motivo || '---';
    document.getElementById('orden-trabajo').innerText = orden.trabajo_realizado || '---';

    // 2. Llenar la tabla de repuestos dinámicamente
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

    // 3. Calcular el total (Repuestos + Mano de obra si el campo "cobro" la tiene)
    const cobroManoObra = parseFloat(orden.cobro || 0);
    const totalFinal = totalRepuestos + cobroManoObra;
    document.getElementById('orden-total').innerText = totalFinal.toFixed(2);

    // 4. Preparar el contenedor para la foto
    const plantilla = document.getElementById('plantilla-orden');
    plantilla.style.display = 'block'; 
    plantilla.style.position = 'absolute';
    plantilla.style.left = '-9999px';

    try {
        // 5. Tomar la foto
        const canvas = await html2canvas(plantilla, { scale: 2 });
        const imgData = canvas.toDataURL('image/png');
        
        // 6. Forzar la descarga automática en el dispositivo
        const enlaceDescarga = document.createElement('a');
        enlaceDescarga.href = imgData;
        enlaceDescarga.download = `Orden_Trabajo_${orden.vehiculo}.png`;
        enlaceDescarga.click();
        
    } catch (error) {
        console.error("Error al generar la imagen:", error);
        mostrarNotificacion("Hubo un error al crear la imagen", "error");
    } finally {
        // 7. Esconder la plantilla y dejar todo como estaba
        plantilla.style.display = 'none';
        plantilla.style.position = 'static';
    }
}