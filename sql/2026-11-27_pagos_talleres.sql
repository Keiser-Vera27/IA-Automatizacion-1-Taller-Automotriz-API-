-- =============================================================================
-- MIGRACIÓN: registro de pagos de los talleres (panel de administración)
-- Fecha: 2026-11-27
--
--   pagos : cada cobro que recibes de un taller (cuánto, cuándo, cómo y qué
--           periodo cubre). Hasta ahora "Renovar pago" solo cambiaba la fecha
--           de vencimiento y no quedaba constancia del dinero recibido.
--
-- Con esta tabla el panel muestra los ingresos reales por mes y por plan,
-- cuánto te ha pagado cada taller y su historial de pagos.
--
-- No modifica ninguna tabla existente. Es seguro ejecutarlo más de una vez.
-- EJECUTAR ANTES de subir el código que la usa (si no, el panel avisa que falta).
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.pagos (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    taller_id     uuid NOT NULL REFERENCES public.talleres(id) ON DELETE CASCADE,
    monto         numeric(10,2) NOT NULL CHECK (monto >= 0),
    fecha_pago    date NOT NULL DEFAULT (now() AT TIME ZONE 'America/Guayaquil')::date,
    -- Plan y periodo del momento del pago: si el taller cambia de plan después,
    -- el historial sigue mostrando de qué plan vino cada ingreso.
    plan_codigo   text,
    periodo       text NOT NULL CHECK (periodo IN ('mensual', 'trimestral', 'anual')),
    metodo        text NOT NULL DEFAULT 'transferencia'
                  CHECK (metodo IN ('efectivo', 'transferencia', 'deposito', 'tarjeta', 'otro')),
    nota          text NOT NULL DEFAULT '' CHECK (char_length(nota) <= 300),
    -- Hasta qué fecha queda cubierto el taller con este pago
    cubre_hasta   date,
    admin_email   text,
    creado_en     timestamptz NOT NULL DEFAULT now()
);

-- Consultas del panel: ingresos por fecha y pagos de un taller
CREATE INDEX IF NOT EXISTS pagos_fecha_idx  ON public.pagos (fecha_pago);
CREATE INDEX IF NOT EXISTS pagos_taller_idx ON public.pagos (taller_id, fecha_pago DESC);

-- Solo el backend (service role) lee y escribe; nadie desde el navegador.
ALTER TABLE public.pagos ENABLE ROW LEVEL SECURITY;
