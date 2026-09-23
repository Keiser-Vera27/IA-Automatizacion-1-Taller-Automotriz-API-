-- =============================================================================
-- MIGRACIÓN: garantías (etapa 1) + kilometraje
-- Fecha: 2026-09-23
--
--   * Cada servicio del catálogo puede tener su propia garantía (días y km).
--     Si no la tiene, se aplica la del taller por defecto: 30 días o 1.000 km.
--     garantia_dias = 0  ->  ese servicio NO tiene garantía (ej. diagnóstico).
--   * Cada orden guarda el kilometraje de ingreso y, al terminarse, la
--     garantía que se entregó (hasta qué fecha y hasta qué kilometraje).
--
-- EJECUTAR ANTES de subir el código. Es seguro ejecutarlo más de una vez.
-- =============================================================================

-- Garantía por servicio (NULL = usar la del taller por defecto)
ALTER TABLE public.servicios ADD COLUMN IF NOT EXISTS garantia_dias integer CHECK (garantia_dias IS NULL OR garantia_dias >= 0);
ALTER TABLE public.servicios ADD COLUMN IF NOT EXISTS garantia_km   integer CHECK (garantia_km   IS NULL OR garantia_km   >= 0);

-- Kilometraje y garantía entregada en cada orden
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS kilometraje        integer;
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS garantia_dias      integer;
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS garantia_km        integer;
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS garantia_vence     date;
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS garantia_km_limite integer;
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS garantia_servicio  text;

-- Búsqueda rápida de garantías vigentes por placa (aviso al reingreso)
CREATE INDEX IF NOT EXISTS reparaciones_garantia_placa_idx
    ON public.reparaciones (taller_id, vehiculo, garantia_vence)
    WHERE garantia_vence IS NOT NULL;

-- Garantía por defecto de CADA TALLER (la define el dueño en "Catálogo de Servicios").
-- Se usa cuando el servicio no tiene garantía propia y el mensaje no indica otra.
ALTER TABLE public.talleres ADD COLUMN IF NOT EXISTS garantia_dias_defecto integer NOT NULL DEFAULT 30   CHECK (garantia_dias_defecto >= 0);
ALTER TABLE public.talleres ADD COLUMN IF NOT EXISTS garantia_km_defecto   integer NOT NULL DEFAULT 1000 CHECK (garantia_km_defecto   >= 0);
