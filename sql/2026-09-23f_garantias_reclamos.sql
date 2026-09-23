-- =============================================================================
-- MIGRACIÓN: garantías etapa 2 — reclamos ligados a la orden original,
-- causa y costo del reclamo, y reclamos de garantía a proveedores.
-- Fecha: 2026-09-23 (requiere 2026-09-23d y 2026-09-23e)
-- Es seguro ejecutarlo más de una vez.
-- =============================================================================

-- 1) Orden original que se está cubriendo con la garantía.
--    Se crea con el MISMO tipo que reparaciones.id (bigint o uuid) y como FK.
DO $$
DECLARE tipo_id text;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod) INTO tipo_id
    FROM pg_attribute a
    WHERE a.attrelid = 'public.reparaciones'::regclass AND a.attname = 'id';

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'reparaciones'
                     AND column_name = 'garantia_orden_origen') THEN
        EXECUTE format('ALTER TABLE public.reparaciones ADD COLUMN garantia_orden_origen %s
                        REFERENCES public.reparaciones(id) ON DELETE SET NULL', tipo_id);
    END IF;
END $$;

-- 2) Causa y costo del reclamo
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS garantia_causa text
    CHECK (garantia_causa IS NULL OR garantia_causa IN ('mano_obra', 'repuesto', 'otra'));
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS garantia_costo numeric(12,2) NOT NULL DEFAULT 0
    CHECK (garantia_costo >= 0);

-- 3) Reclamo al proveedor (cuando falló el repuesto)
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS reclamo_proveedor_estado text
    CHECK (reclamo_proveedor_estado IS NULL OR reclamo_proveedor_estado IN ('Pendiente', 'Aprobado', 'Rechazado'));
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS reclamo_proveedor_nombre text;
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS reclamo_proveedor_monto numeric(12,2) NOT NULL DEFAULT 0
    CHECK (reclamo_proveedor_monto >= 0);

-- 4) Índices para el reporte de garantías
CREATE INDEX IF NOT EXISTS reparaciones_reclamos_garantia_idx
    ON public.reparaciones (taller_id, fecha_salida)
    WHERE garantia_orden_origen IS NOT NULL;
CREATE INDEX IF NOT EXISTS reparaciones_reclamo_proveedor_idx
    ON public.reparaciones (taller_id, reclamo_proveedor_estado)
    WHERE reclamo_proveedor_estado IS NOT NULL;
