-- =============================================================================
-- MIGRACIÓN: cotizaciones con aprobación del cliente
-- Fecha: 2026-10-01
--
--   cotizaciones      : un presupuesto ligado a una orden abierta. El cliente
--                       lo abre con un link (token secreto, sin iniciar sesión)
--                       y aprueba o rechaza cada línea.
--   cotizacion_items  : las líneas (servicio, repuesto u otro) con su precio y
--                       la decisión del cliente.
--   plan_modulos      : el módulo 'cotizaciones' se incluye en el plan Pro.
--
-- EJECUTAR ANTES de subir el código. Es seguro ejecutarlo más de una vez.
-- =============================================================================

DO $$
DECLARE tipo_taller text; tipo_orden text;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod) INTO tipo_taller FROM pg_attribute a
     WHERE a.attrelid = 'public.talleres'::regclass AND a.attname = 'id';
    SELECT format_type(a.atttypid, a.atttypmod) INTO tipo_orden FROM pg_attribute a
     WHERE a.attrelid = 'public.reparaciones'::regclass AND a.attname = 'id';

    IF to_regclass('public.cotizaciones') IS NULL THEN
        EXECUTE format($f$
            CREATE TABLE public.cotizaciones (
                id              bigserial PRIMARY KEY,
                taller_id       %s NOT NULL REFERENCES public.talleres(id) ON DELETE CASCADE,
                reparacion_id   %s NOT NULL REFERENCES public.reparaciones(id) ON DELETE CASCADE,
                token           text NOT NULL UNIQUE CHECK (length(token) >= 24),
                estado          text NOT NULL DEFAULT 'pendiente'
                                CHECK (estado IN ('pendiente', 'respondida', 'anulada')),
                vehiculo        text,
                cliente         text,
                nota            text,
                vence           date NOT NULL,
                total           numeric(12,2) NOT NULL DEFAULT 0 CHECK (total >= 0),
                total_aprobado  numeric(12,2),
                comentario_cliente text,
                aplicada_a_orden boolean NOT NULL DEFAULT false,
                creado_en       timestamptz NOT NULL DEFAULT now(),
                respondido_en   timestamptz
            )$f$, tipo_taller, tipo_orden);
    END IF;

    IF to_regclass('public.cotizacion_items') IS NULL THEN
        EXECUTE format($f$
            CREATE TABLE public.cotizacion_items (
                id              bigserial PRIMARY KEY,
                cotizacion_id   bigint NOT NULL REFERENCES public.cotizaciones(id) ON DELETE CASCADE,
                taller_id       %s NOT NULL REFERENCES public.talleres(id) ON DELETE CASCADE,
                tipo            text NOT NULL CHECK (tipo IN ('servicio', 'repuesto', 'otro')),
                descripcion     text NOT NULL CHECK (length(descripcion) BETWEEN 1 AND 200),
                servicio_id     text,
                inventario_id   text,
                cantidad        numeric(10,2) NOT NULL CHECK (cantidad > 0),
                precio_unitario numeric(12,2) NOT NULL CHECK (precio_unitario >= 0),
                prioridad       text NOT NULL DEFAULT 'recomendado'
                                CHECK (prioridad IN ('urgente', 'recomendado', 'opcional')),
                decision        text NOT NULL DEFAULT 'pendiente'
                                CHECK (decision IN ('pendiente', 'aprobado', 'rechazado')),
                orden           integer NOT NULL DEFAULT 0
            )$f$, tipo_taller);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS cotizaciones_orden_idx  ON public.cotizaciones (taller_id, reparacion_id);
CREATE INDEX IF NOT EXISTS cotizacion_items_cot_idx ON public.cotizacion_items (cotizacion_id);

-- Solo el backend (service_role) lee/escribe: el cliente entra por el token,
-- siempre a través de la API, nunca directo a la base.
ALTER TABLE public.cotizaciones     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cotizacion_items ENABLE ROW LEVEL SECURITY;

-- El módulo se incluye en el plan Pro (si la migración de planes ya se ejecutó)
DO $$
BEGIN
    -- EXECUTE: así la consulta no se analiza si las tablas de planes no existen
    IF to_regclass('public.plan_modulos') IS NOT NULL THEN
        EXECUTE $q$
            INSERT INTO public.plan_modulos (plan_codigo, modulo)
            SELECT 'pro', 'cotizaciones' WHERE EXISTS (SELECT 1 FROM public.planes WHERE codigo = 'pro')
            ON CONFLICT DO NOTHING
        $q$;
    END IF;
END $$;
