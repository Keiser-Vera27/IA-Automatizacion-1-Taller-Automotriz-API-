-- =============================================================================
-- MIGRACIÓN: materiales por servicio (kits que se descuentan solos del inventario)
-- Fecha: 2026-09-24
--
--   servicio_materiales: qué materiales consume cada servicio del catálogo.
--     modelo NULL  -> se usa en TODOS los vehículos.
--     modelo 'Spark' -> solo si el modelo del vehículo contiene ese texto
--                       (la variante más específica gana: "Spark GT" > "Spark").
--     por_cilindro -> la cantidad se multiplica por los cilindros del motor.
--   servicios.materiales_incluidos: true = van incluidos en el precio del
--     servicio (no se suman al total); false = se cobran aparte.
--   reparacion_detalles: se marca de dónde vino cada material y si va incluido.
--
-- EJECUTAR ANTES de subir el código. Es seguro ejecutarlo más de una vez.
-- =============================================================================

-- 1) Tabla de materiales por servicio (tipos de id detectados automáticamente)
DO $$
DECLARE tipo_serv text; tipo_inv text;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod) INTO tipo_serv FROM pg_attribute a
     WHERE a.attrelid = 'public.servicios'::regclass AND a.attname = 'id';
    SELECT format_type(a.atttypid, a.atttypmod) INTO tipo_inv FROM pg_attribute a
     WHERE a.attrelid = 'public.inventario'::regclass AND a.attname = 'id';

    IF to_regclass('public.servicio_materiales') IS NULL THEN
        EXECUTE format($f$
            CREATE TABLE public.servicio_materiales (
                id            bigserial PRIMARY KEY,
                taller_id     uuid NOT NULL,
                servicio_id   %s NOT NULL REFERENCES public.servicios(id)  ON DELETE CASCADE,
                inventario_id %s NOT NULL REFERENCES public.inventario(id) ON DELETE CASCADE,
                cantidad      numeric(10,2) NOT NULL CHECK (cantidad > 0),
                por_cilindro  boolean NOT NULL DEFAULT false,
                modelo        text,
                creado_en     timestamptz NOT NULL DEFAULT now()
            )$f$, tipo_serv, tipo_inv);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS servicio_materiales_servicio_idx
    ON public.servicio_materiales (taller_id, servicio_id);

-- Un mismo material no se repite en la misma variante del mismo servicio
CREATE UNIQUE INDEX IF NOT EXISTS servicio_materiales_unico_uk
    ON public.servicio_materiales (servicio_id, inventario_id, (lower(coalesce(modelo, ''))));

-- Seguridad multi-tenant: nadie desde el navegador lee/escribe esta tabla
-- directamente; solo el backend (service_role), siempre filtrando por taller_id.
ALTER TABLE public.servicio_materiales ENABLE ROW LEVEL SECURITY;

-- 2) ¿Los materiales van incluidos en el precio del servicio?
ALTER TABLE public.servicios
    ADD COLUMN IF NOT EXISTS materiales_incluidos boolean NOT NULL DEFAULT true;

-- 3) Origen de cada repuesto/material usado en una orden
ALTER TABLE public.reparacion_detalles ADD COLUMN IF NOT EXISTS origen   text NOT NULL DEFAULT 'manual'
    CHECK (origen IN ('manual', 'kit'));
ALTER TABLE public.reparacion_detalles ADD COLUMN IF NOT EXISTS trabajo  text;
ALTER TABLE public.reparacion_detalles ADD COLUMN IF NOT EXISTS incluido boolean NOT NULL DEFAULT false;

-- 4) Número de cilindros del motor (para cantidades "por cilindro")
ALTER TABLE public.reparaciones ADD COLUMN IF NOT EXISTS cilindros integer
    CHECK (cilindros IS NULL OR cilindros BETWEEN 1 AND 16);
