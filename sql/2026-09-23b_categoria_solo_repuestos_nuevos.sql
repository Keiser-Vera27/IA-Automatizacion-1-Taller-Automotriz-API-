-- =============================================================================
-- MIGRACIÓN: la categoría de un repuesto EXISTENTE ya no se cambia por el
-- nombre de la hoja del Excel.
-- Fecha: 2026-09-23 (requiere haber ejecutado antes 2026-09-23_inventario_categorias_y_carga_por_lote.sql)
--
-- Regla nueva:
--   * Repuesto NUEVO      -> categoría = columna "Categoría" de la fila, o el
--                            nombre de la hoja si no hay columna.
--   * Repuesto EXISTENTE  -> conserva su categoría, SALVO que la fila traiga
--                            columna "Categoría" con valor (el backend lo marca
--                            con "forzar_categoria": true).
--
-- Ejecutar completo en Supabase > SQL Editor. Reemplaza la función anterior
-- (misma firma), así que el backend sigue llamándola igual.
-- =============================================================================

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
    -- Datos del repuesto con los tipos de la propia tabla inventario
    CREATE TEMP TABLE _items ON COMMIT DROP AS
    SELECT * FROM jsonb_populate_recordset(NULL::public.inventario, p_items);

    -- Marca que no es columna de inventario: ¿la categoría vino de una
    -- columna explícita del Excel (true) o solo del nombre de la hoja (false)?
    CREATE TEMP TABLE _flags ON COMMIT DROP AS
    SELECT x.codigo, COALESCE(x.forzar_categoria, false) AS forzar_categoria
    FROM jsonb_to_recordset(p_items) AS x(codigo text, forzar_categoria boolean);

    -- 1) Actualizar los que ya existen en ESTE taller
    RETURN QUERY
    UPDATE public.inventario AS inv
    SET cantidad            = COALESCE(inv.cantidad, 0) + COALESCE(i.cantidad, 0),
        costo               = COALESCE(i.costo, inv.costo),
        precio_venta        = COALESCE(i.precio_venta, inv.precio_venta),
        -- Solo se cambia la categoría si el Excel la trae en una columna
        categoria           = CASE WHEN f.forzar_categoria
                                   THEN COALESCE(NULLIF(i.categoria, ''), inv.categoria)
                                   ELSE inv.categoria END,
        fecha_actualizacion = p_fecha
    FROM _items i
    JOIN _flags f ON f.codigo = i.codigo
    WHERE inv.taller_id = p_taller_id
      AND inv.codigo    = i.codigo
    RETURNING inv.codigo::text, 'actualizado'::text;

    -- 2) Insertar los nuevos (aquí sí se usa la categoría de la hoja)
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
    DROP TABLE IF EXISTS _flags;
END;
$$;

-- Se reafirman los permisos: solo el backend (service_role) puede ejecutarla.
REVOKE ALL ON FUNCTION public.importar_inventario_lote(uuid, jsonb, public.inventario.fecha_actualizacion%TYPE) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.importar_inventario_lote(uuid, jsonb, public.inventario.fecha_actualizacion%TYPE) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.importar_inventario_lote(uuid, jsonb, public.inventario.fecha_actualizacion%TYPE) TO service_role;
