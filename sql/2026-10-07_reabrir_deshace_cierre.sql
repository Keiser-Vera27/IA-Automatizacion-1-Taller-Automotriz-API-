-- =============================================================================
-- MIGRACIÓN: reabrir una orden deshace lo que trajo el mensaje de cierre
-- Fecha: 2026-10-07
--
--   reparaciones.motivo_antes_cierre: el motivo tal como estaba ANTES del
--     mensaje de cierre. Al reabrir se restaura (lo que el cierre agregó al
--     motivo se descarta) y la columna vuelve a NULL.
--   reparacion_detalles.registrado_en: instante en que se registró el material
--     (la hora del mensaje). Si coincide con la fecha_salida de la orden, vino
--     con el cierre: al reabrir se quita de la orden y vuelve al stock.
--
-- Los trabajos no necesitan columna nueva: cada uno ya guarda la hora del
-- mensaje que lo agregó. Sin esta migración el código funciona igual, pero al
-- reabrir no se restaura el motivo ni se devuelven los repuestos sueltos del
-- cierre (los kits de los trabajos del cierre sí se devuelven).
-- Es seguro ejecutarlo más de una vez.
-- =============================================================================

ALTER TABLE public.reparaciones
    ADD COLUMN IF NOT EXISTS motivo_antes_cierre text;

ALTER TABLE public.reparacion_detalles
    ADD COLUMN IF NOT EXISTS registrado_en timestamptz;   -- mismo tipo que reparaciones.fecha_salida

COMMENT ON COLUMN public.reparaciones.motivo_antes_cierre IS
    'Motivo antes del mensaje de cierre; se restaura al reabrir la orden';
COMMENT ON COLUMN public.reparacion_detalles.registrado_en IS
    'Hora (UTC) del mensaje que registró el material; igual a fecha_salida = vino con el cierre';
