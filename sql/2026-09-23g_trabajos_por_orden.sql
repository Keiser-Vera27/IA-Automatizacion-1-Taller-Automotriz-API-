-- =============================================================================
-- MIGRACIÓN: lista de trabajos por orden (se van agregando mientras la orden
-- está abierta) — Fecha: 2026-09-23
--
-- Cada elemento: {"descripcion": "...", "precio": 40.0, "mensaje_id": "...", "fecha": "..."}
-- La columna "trabajo_realizado" se sigue llenando (texto unido con " | ")
-- para que reportes, ranking y garantías funcionen igual que antes.
-- EJECUTAR ANTES de subir el código. Es seguro ejecutarlo más de una vez.
-- =============================================================================

ALTER TABLE public.reparaciones
    ADD COLUMN IF NOT EXISTS trabajos jsonb NOT NULL DEFAULT '[]'::jsonb;

-- Órdenes que siguen ABIERTAS y ya tenían texto en trabajo_realizado:
-- se convierte ese texto en el primer trabajo de la lista (precio 0).
UPDATE public.reparaciones
SET trabajos = jsonb_build_array(jsonb_build_object('descripcion', trabajo_realizado, 'precio', 0))
WHERE estado = 'Pendiente'
  AND COALESCE(trim(trabajo_realizado), '') <> ''
  AND trabajos = '[]'::jsonb;
