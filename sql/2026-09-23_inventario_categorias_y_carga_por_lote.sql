-- =============================================================================
-- MIGRACIÓN: categorías de inventario + carga masiva por lote (multi-hoja)
-- Fecha: 2026-09-23
--
-- Ejecutar en Supabase > SQL Editor, EN ORDEN, paso por paso.
--   PASO 1  Revisar si hay códigos repetidos (solo lectura).
--   PASO 2  (Solo si el PASO 1 devolvió filas) unificar duplicados.
--   PASO 3  Columna categoria + índice único (taller_id, codigo).
--   PASO 4  Función importar_inventario_lote (carga en una sola transacción).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- PASO 1: ¿Hay repuestos con el mismo código dentro de un mismo taller?
-- Si esta consulta NO devuelve filas, sáltate el PASO 2.
-- -----------------------------------------------------------------------------
SELECT taller_id, codigo, COUNT(*) AS repetidos, SUM(cantidad) AS cantidad_total
FROM public.inventario
GROUP BY taller_id, codigo
HAVING COUNT(*) > 1
ORDER BY repetidos DESC;


-- -----------------------------------------------------------------------------
-- PASO 2 (opcional): unificar duplicados.
-- Se conserva el registro actualizado más recientemente, se le suma la
-- cantidad de los repetidos, y los detalles de órdenes (reparacion_detalles)
-- que apuntaban a los repetidos se re-apuntan al registro conservado, para no
-- perder el historial. Todo en una transacción: si algo falla, no cambia nada.
-- -----------------------------------------------------------------------------
BEGIN;

CREATE TEMP TABLE _dup_inventario ON COMMIT DROP AS
WITH ranked AS (
    SELECT id, taller_id, codigo,
           ROW_NUMBER() OVER (PARTITION BY taller_id, codigo
                              ORDER BY fecha_actualizacion DESC NULLS LAST, id) AS rn,
           SUM(COALESCE(cantidad, 0)) OVER (PARTITION BY taller_id, codigo)   AS total,
           COUNT(*) OVER (PARTITION BY taller_id, codigo)                     AS n
    FROM public.inventario
)
SELECT r.id, r.rn, r.total, k.id AS id_conservado
FROM ranked r
JOIN ranked k ON k.taller_id = r.taller_id AND k.codigo = r.codigo AND k.rn = 1
WHERE r.n > 1;

-- Re-apuntar el historial de órdenes al registro que se conserva
UPDATE public.reparacion_detalles d
SET inventario_id = x.id_conservado
FROM _dup_inventario x
WHERE d.inventario_id = x.id AND x.rn > 1;

-- Sumar las cantidades en el registro conservado
UPDATE public.inventario i
SET cantidad = x.total
FROM _dup_inventario x
WHERE i.id = x.id AND x.rn = 1;

-- Borrar los repetidos
DELETE FROM public.inventario i
USING _dup_inventario x
WHERE i.id = x.id AND x.rn > 1;

COMMIT;


-- -----------------------------------------------------------------------------
-- PASO 3: categoría + código único por taller
-- -----------------------------------------------------------------------------
ALTER TABLE public.inventario
    ADD COLUMN IF NOT EXISTS categoria text NOT NULL DEFAULT 'General';

-- Un código no puede repetirse dentro del mismo taller (sí entre talleres).
CREATE UNIQUE INDEX IF NOT EXISTS inventario_taller_codigo_uk
    ON public.inventario (taller_id, codigo);

-- Para filtrar/consultar inventario por categoría rápidamente.
CREATE INDEX IF NOT EXISTS inventario_taller_categoria_idx
    ON public.inventario (taller_id, categoria);


-- -----------------------------------------------------------------------------
-- PASO 4: carga masiva en UNA sola llamada y UNA sola transacción.
--   p_items: arreglo JSON [{codigo, nombre, marca, proveedor, aplicacion,
--            categoria, cantidad, costo, precio_venta}, ...] (ya sin códigos
--            repetidos; el backend los agrupa antes).
--   Reglas (las mismas del registro por IA):
--     * Código existente -> SUMA cantidad; costo/precio/categoría se
--       actualizan solo si vienen con valor (NULL = conservar el actual).
--     * Código nuevo     -> se crea con valores por defecto donde falten.
--   Devuelve una fila por código con accion = 'actualizado' | 'nuevo'.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.importar_inventario_lote(
    p_taller_id uuid,
    p_items     jsonb,
    p_fecha     public.inventario.fecha_actualizacion%TYPE
)
RETURNS TABLE (codigo text, accion text)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
#variable_conflict use_column
BEGIN
    -- Los tipos de cada campo se toman de la propia tabla inventario
    CREATE TEMP TABLE _items ON COMMIT DROP AS
    SELECT * FROM jsonb_populate_recordset(NULL::public.inventario, p_items);

    -- 1) Actualizar los que ya existen en ESTE taller
    RETURN QUERY
    UPDATE public.inventario AS inv
    SET cantidad            = COALESCE(inv.cantidad, 0) + COALESCE(i.cantidad, 0),
        costo               = COALESCE(i.costo, inv.costo),
        precio_venta        = COALESCE(i.precio_venta, inv.precio_venta),
        categoria           = COALESCE(i.categoria, inv.categoria),
        fecha_actualizacion = p_fecha
    FROM _items i
    WHERE inv.taller_id = p_taller_id
      AND inv.codigo    = i.codigo
    RETURNING inv.codigo::text, 'actualizado'::text;

    -- 2) Insertar los nuevos
    RETURN QUERY
    INSERT INTO public.inventario AS inv
        (taller_id, codigo, nombre, marca, proveedor, aplicacion, categoria,
         cantidad, costo, precio_venta, fecha_actualizacion)
    SELECT p_taller_id, i.codigo,
           COALESCE(NULLIF(i.nombre, ''), i.codigo),
           COALESCE(i.marca, ''),
           COALESCE(NULLIF(i.proveedor, ''), 'General'),
           COALESCE(NULLIF(i.aplicacion, ''), 'General'),
           COALESCE(NULLIF(i.categoria, ''), 'General'),
           COALESCE(i.cantidad, 0), COALESCE(i.costo, 0), COALESCE(i.precio_venta, 0),
           p_fecha
    FROM _items i
    WHERE NOT EXISTS (
        SELECT 1 FROM public.inventario e
        WHERE e.taller_id = p_taller_id AND e.codigo = i.codigo
    )
    ON CONFLICT (taller_id, codigo) DO NOTHING
    RETURNING inv.codigo::text, 'nuevo'::text;

    DROP TABLE IF EXISTS _items;
END;
$$;

-- SEGURIDAD MULTI-TENANT: la función recibe p_taller_id como parámetro, así que
-- NINGÚN usuario del navegador debe poder llamarla directamente (podría pasar
-- el id de otro taller). Solo el backend (service_role) la ejecuta, con el
-- taller_id sacado del JWT.
REVOKE ALL ON FUNCTION public.importar_inventario_lote(uuid, jsonb, public.inventario.fecha_actualizacion%TYPE) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.importar_inventario_lote(uuid, jsonb, public.inventario.fecha_actualizacion%TYPE) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.importar_inventario_lote(uuid, jsonb, public.inventario.fecha_actualizacion%TYPE) TO service_role;
