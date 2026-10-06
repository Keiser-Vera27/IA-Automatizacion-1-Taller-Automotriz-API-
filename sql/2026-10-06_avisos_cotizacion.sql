-- =============================================================================
-- MIGRACIÓN: aviso al taller cuando el cliente responde una cotización
-- Fecha: 2026-10-06
--
--   cotizaciones.aviso_visto_en: cuándo el taller vio el aviso emergente de la
--     respuesta del cliente. NULL = respondida y todavía sin ver (se muestra el
--     pop-up). Al pulsar OK se llena y el aviso no vuelve a salir.
--
--   Las cotizaciones respondidas hace más de 2 días se marcan como vistas, para
--   no mostrar de golpe avisos viejos. Las de los últimos 2 días SÍ se avisan.
--
-- Requiere la migración 2026-10-01_cotizaciones.sql. Sin esta migración la
-- página funciona igual, solo que sin avisos. Es seguro ejecutarlo más de una vez.
-- =============================================================================

DO $$
BEGIN
    -- Solo la primera vez: así una segunda ejecución no vuelve a "des-ver" avisos
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'cotizaciones'
                      AND column_name = 'aviso_visto_en') THEN
        ALTER TABLE public.cotizaciones ADD COLUMN aviso_visto_en timestamptz;

        UPDATE public.cotizaciones
           SET aviso_visto_en = now()
         WHERE estado = 'respondida'
           AND respondido_en < now() - interval '2 days';
    END IF;
END $$;

-- La consulta de avisos (cada 30 s por taller) usa solo las respondidas sin ver
CREATE INDEX IF NOT EXISTS cotizaciones_avisos_idx
    ON public.cotizaciones (taller_id)
    WHERE estado = 'respondida' AND aviso_visto_en IS NULL;
