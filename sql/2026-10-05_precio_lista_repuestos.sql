-- =============================================================================
-- MIGRACIÓN: precio de lista en los repuestos de cada orden
-- Fecha: 2026-10-05
--
--   reparacion_detalles.precio_lista: precio de venta del inventario al momento
--     de usar el repuesto. precio_unitario guarda el precio REAL cobrado (puede
--     ser menor si se negoció con el cliente, ej. "el TPS se le dejó en 30").
--     La diferencia permite reportar los descuentos otorgados.
--   NULL = registros anteriores a esta migración o materiales de kit.
--
-- El código funciona sin esta migración (guarda sin la columna), pero sin ella
-- no queda registro del descuento. Es seguro ejecutarlo más de una vez.
-- =============================================================================

ALTER TABLE public.reparacion_detalles
    ADD COLUMN IF NOT EXISTS precio_lista numeric(12, 2);

COMMENT ON COLUMN public.reparacion_detalles.precio_lista IS
    'Precio de venta del inventario al usar el repuesto; precio_unitario es lo cobrado realmente';
