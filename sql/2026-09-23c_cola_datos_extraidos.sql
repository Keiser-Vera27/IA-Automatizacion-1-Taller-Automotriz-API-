-- =============================================================================
-- MIGRACIÓN: datos pre-extraídos en la cola de mensajes
-- Fecha: 2026-09-23
--
-- Ahora /procesar-mensaje extrae y VALIDA la orden de trabajo antes de
-- encolarla (técnico registrado, placa, modelo, cliente, cédula, celular,
-- motivo, método de pago). Lo validado se guarda en esta columna y el
-- trabajador de la cola lo usa directamente, sin volver a llamar a la IA.
--
-- Es seguro ejecutarlo más de una vez. Si el backend se despliega antes de
-- correr esto, sigue funcionando (encola sin esta columna).
-- =============================================================================

ALTER TABLE public.cola_mensajes
    ADD COLUMN IF NOT EXISTS datos_extraidos jsonb;

COMMENT ON COLUMN public.cola_mensajes.datos_extraidos IS
    'Extracción de la IA ya validada en /procesar-mensaje. Si es NULL, el trabajador extrae con la IA.';


-- -----------------------------------------------------------------------------
-- OPCIONAL (solo lectura): órdenes con técnico no registrado.
-- Desde ahora no cuentan en el ranking, la liquidación ni las comisiones.
-- Si quieres asignarles un técnico, corrige el campo "oficial" de esas órdenes.
-- -----------------------------------------------------------------------------
SELECT r.oficial, COUNT(*) AS ordenes, SUM(r.cobro) AS total
FROM public.reparaciones r
WHERE r.estado = 'Terminado'
  AND NOT EXISTS (
      SELECT 1 FROM public.tecnicos t
      WHERE t.taller_id = r.taller_id
        AND lower(trim(t.nombre)) = lower(trim(COALESCE(r.oficial, '')))
  )
GROUP BY r.oficial
ORDER BY ordenes DESC;
