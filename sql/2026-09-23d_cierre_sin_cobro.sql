-- =============================================================================
-- MIGRACIÓN: cerrar órdenes SIN COBRO (botón "Cerrar orden" en la tarjeta)
-- Fecha: 2026-09-23
--
-- Nuevo estado de reparaciones: 'Cerrado sin cobro'
--   Motivos: Se cubre garantía | Cliente sin presupuesto | Cliente sin tiempo |
--            Falla sobrepasa las capacidades del taller | Otro
-- No suma a ingresos, ranking ni comisiones (esos reportes solo usan 'Terminado').
-- Es seguro ejecutarlo más de una vez.
-- =============================================================================

-- 1) Columnas del cierre
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS motivo_cierre  text;
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS detalle_cierre text;

-- 2) Si la tabla restringe los valores de "estado" (CHECK), se reemplaza la
--    restricción por una que incluya el nuevo estado. Si no existe, no pasa nada.
DO $$
DECLARE c record;
BEGIN
    FOR c IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'public.reparaciones'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%estado%'
    LOOP
        EXECUTE format('ALTER TABLE public.reparaciones DROP CONSTRAINT %I', c.conname);
    END LOOP;
END $$;

-- NOT VALID: se aplica a lo nuevo sin bloquear por datos antiguos.
ALTER TABLE public.reparaciones
    ADD CONSTRAINT reparaciones_estado_check
    CHECK (estado IN ('Pendiente', 'Terminado', 'Cerrado sin cobro')) NOT VALID;

-- 3) Consultas rápidas de cierres del día / por motivo
CREATE INDEX IF NOT EXISTS reparaciones_taller_estado_salida_idx
    ON public.reparaciones (taller_id, estado, fecha_salida);
