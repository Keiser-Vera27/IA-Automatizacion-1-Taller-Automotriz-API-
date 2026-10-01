-- =============================================================================
-- MIGRACIÓN: planes de suscripción y módulos por taller
-- Fecha: 2026-09-25
--
--   planes            : los planes que vendes (ej. Básico y Pro) con sus precios.
--   plan_modulos      : qué módulos incluye cada plan.
--   taller_modulos    : excepciones por taller (activar o quitar un módulo
--                       aunque su plan diga otra cosa), con fecha de fin opcional
--                       para pruebas gratis.
--   modulos_historial : registro de cada cambio (quién, cuándo, qué).
--   talleres.plan_codigo         : plan del taller (qué funciones tiene).
--   talleres.periodo_facturacion : mensual / trimestral / anual (cuánto paga).
--     Antes ambas cosas vivían en talleres.plan; esa columna se conserva
--     como copia del periodo para no romper nada.
--
-- Los talleres que ya existen quedan en el plan 'pro' (todo activado), así
-- que NADIE pierde funciones al ejecutar esto.
--
-- EJECUTAR ANTES de subir el código. Es seguro ejecutarlo más de una vez.
-- =============================================================================

-- 1) Planes
CREATE TABLE IF NOT EXISTS public.planes (
    codigo            text PRIMARY KEY CHECK (codigo ~ '^[a-z0-9_]{2,30}$'),
    nombre            text NOT NULL,
    precio_mensual    numeric(10,2) NOT NULL DEFAULT 0 CHECK (precio_mensual >= 0),
    precio_trimestral numeric(10,2) NOT NULL DEFAULT 0 CHECK (precio_trimestral >= 0),
    precio_anual      numeric(10,2) NOT NULL DEFAULT 0 CHECK (precio_anual >= 0),
    orden             integer NOT NULL DEFAULT 0,
    creado_en         timestamptz NOT NULL DEFAULT now()
);

-- Planes iniciales (los precios y módulos se editan luego desde el panel admin)
INSERT INTO public.planes (codigo, nombre, precio_mensual, precio_trimestral, precio_anual, orden) VALUES
    ('basico', 'Básico', 19.99, 54.99, 199.99, 1),
    ('pro',    'Pro',    29.99, 79.99, 299.99, 2)
ON CONFLICT (codigo) DO NOTHING;

-- 2) Módulos incluidos en cada plan (la lista de módulos vive en el código)
CREATE TABLE IF NOT EXISTS public.plan_modulos (
    plan_codigo text NOT NULL REFERENCES public.planes(codigo) ON DELETE CASCADE ON UPDATE CASCADE,
    modulo      text NOT NULL CHECK (modulo ~ '^[a-z0-9_]{2,40}$'),
    PRIMARY KEY (plan_codigo, modulo)
);

INSERT INTO public.plan_modulos (plan_codigo, modulo) VALUES
    ('basico', 'control_garantias'),
    ('basico', 'dashboard'),
    ('pro', 'inventario'),
    ('pro', 'materiales_servicio'),
    ('pro', 'control_garantias'),
    ('pro', 'tecnicos'),
    ('pro', 'dashboard'),
    ('pro', 'consultas_ia')
ON CONFLICT DO NOTHING;

-- 3) Plan y periodo de cada taller
ALTER TABLE public.talleres ADD COLUMN IF NOT EXISTS plan_codigo text NOT NULL DEFAULT 'pro';
ALTER TABLE public.talleres ADD COLUMN IF NOT EXISTS periodo_facturacion text NOT NULL DEFAULT 'mensual';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'talleres_plan_codigo_fk') THEN
        ALTER TABLE public.talleres ADD CONSTRAINT talleres_plan_codigo_fk
            FOREIGN KEY (plan_codigo) REFERENCES public.planes(codigo) ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'talleres_periodo_facturacion_ck') THEN
        ALTER TABLE public.talleres ADD CONSTRAINT talleres_periodo_facturacion_ck
            CHECK (periodo_facturacion IN ('mensual', 'trimestral', 'anual'));
    END IF;
END $$;

-- El periodo que hoy está guardado en 'plan' pasa a su columna propia
-- (solo la primera vez: si ya se cambió desde el panel, no se pisa)
UPDATE public.talleres
   SET periodo_facturacion = plan
 WHERE plan IN ('mensual', 'trimestral', 'anual')
   AND periodo_facturacion = 'mensual'
   AND plan <> 'mensual';

-- 4) Excepciones por taller y 5) historial (tipo de talleres.id detectado solo)
DO $$
DECLARE tipo_taller text;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod) INTO tipo_taller FROM pg_attribute a
     WHERE a.attrelid = 'public.talleres'::regclass AND a.attname = 'id';

    IF to_regclass('public.taller_modulos') IS NULL THEN
        EXECUTE format($f$
            CREATE TABLE public.taller_modulos (
                taller_id      %s NOT NULL REFERENCES public.talleres(id) ON DELETE CASCADE,
                modulo         text NOT NULL CHECK (modulo ~ '^[a-z0-9_]{2,40}$'),
                habilitado     boolean NOT NULL,
                hasta          date,
                nota           text,
                actualizado_en timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (taller_id, modulo)
            )$f$, tipo_taller);
    END IF;

    IF to_regclass('public.modulos_historial') IS NULL THEN
        EXECUTE format($f$
            CREATE TABLE public.modulos_historial (
                id          bigserial PRIMARY KEY,
                taller_id   %s REFERENCES public.talleres(id) ON DELETE CASCADE,
                plan_codigo text,
                modulo      text,
                accion      text NOT NULL,
                detalle     text,
                admin_email text,
                fecha       timestamptz NOT NULL DEFAULT now()
            )$f$, tipo_taller);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS modulos_historial_taller_idx
    ON public.modulos_historial (taller_id, fecha DESC);

-- Seguridad: estas tablas solo las lee/escribe el backend (service_role).
-- Sin políticas, nadie puede tocarlas desde el navegador con la llave pública.
ALTER TABLE public.planes            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.plan_modulos      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.taller_modulos    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.modulos_historial ENABLE ROW LEVEL SECURITY;
