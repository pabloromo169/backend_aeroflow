-- AeroFlow: definiciones de las vistas del espacio `Aeroflow` en Dremio.
--
-- Fuente:  mongo_aeroflow  (MongoDB, base `aeroflow`, colecciones `vuelos` y `operativos`)
-- Espacio: Aeroflow
-- Exportado desde el catálogo de Dremio 26.0.5 el 2026-11-15.
--
-- 13 vistas virtuales: 2 base (V0_*) y 11 derivadas (D1-D9, D4b, D5b).
-- Crear primero `V0_salidas` y `V0_puertas`: el resto depende de ellas.
--
-- Ejecutar cada bloque en el SQL Runner de Dremio o por API:
--   POST /api/v3/sql   {"sql": "<bloque>"}
-- con la cabecera  Authorization: _dremio<TOKEN>  (sin espacio).
--
-- Reglas comunes: métricas sobre `record_valid = TRUE`; retraso en minutos entre
-- `actual_departure_at` y `scheduled_departure_at`; superación cuando el retraso es
-- ESTRICTAMENTE mayor que `delay_threshold_minutes`; agrupaciones temporales por
-- salida programada en `Europe/Madrid`; puertas tomadas de `operativos`.

-- --------------------------------------------------------------------------
-- V0_puertas  (Vista base)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.V0_puertas AS
SELECT
  t.simulation_id,
  t.gate.gate_id AS gate_id,
  t.gate.name AS gate_name,
  t.gate.terminal_id AS terminal_id,
  t.gate.delay_threshold_minutes AS gate_threshold
FROM (
  SELECT simulation_id, FLATTEN(gates) AS gate
  FROM mongo_aeroflow.aeroflow.operativos
) t
;

-- --------------------------------------------------------------------------
-- V0_salidas  (Vista base)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.V0_salidas AS
SELECT
  v.simulation_id, v.event_id, v.operation_id,
  v.scheduled_departure_at, v.actual_departure_at, v.emitted_at,
  v.terminal_id, v.gate_id, v.aircraft_id, v.flight_number,
  v.airline, v.aircraft_model, v.destination_id, v.delay_threshold_minutes,
  v.scheduled_local,
  CAST(v.scheduled_local AS DATE) AS scheduled_local_date,
  EXTRACT(HOUR FROM v.scheduled_local) AS local_hour,
  EXTRACT(DOW FROM v.scheduled_local) AS local_dow,
  CASE WHEN EXTRACT(HOUR FROM v.scheduled_local) < 6 THEN 'Madrugada (00-06)'
       WHEN EXTRACT(HOUR FROM v.scheduled_local) < 12 THEN 'Mañana (06-12)'
       WHEN EXTRACT(HOUR FROM v.scheduled_local) < 18 THEN 'Tarde (12-18)'
       ELSE 'Noche (18-24)' END AS time_band,
  CASE WHEN EXTRACT(DOW FROM v.scheduled_local) IN (1,7) THEN 'Fin de semana' ELSE 'Laborable' END AS day_type,
  TIMESTAMPDIFF(SECOND, v.scheduled_departure_at, v.actual_departure_at) / 60.0 AS delay_minutes,
  CASE WHEN TIMESTAMPDIFF(SECOND, v.scheduled_departure_at, v.actual_departure_at) / 60.0 > v.delay_threshold_minutes THEN 1 ELSE 0 END AS exceeds_threshold,
  TIMESTAMPDIFF(SECOND, v.scheduled_departure_at, v.actual_departure_at) / 60.0 - v.delay_threshold_minutes AS minutes_over_threshold
FROM (
  SELECT *, CONVERT_TIMEZONE('UTC','Europe/Madrid', scheduled_departure_at) AS scheduled_local
  FROM mongo_aeroflow.aeroflow.vuelos
  WHERE record_valid = TRUE
) v
;

-- --------------------------------------------------------------------------
-- D1_salidas_por_puerta_destino  (Vista derivada)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.D1_salidas_por_puerta_destino AS
SELECT g.simulation_id, g.gate_id, g.terminal_id, v.destination_id,
       COUNT(v.event_id) AS valid_departures,
       COUNT(DISTINCT v.aircraft_id) AS distinct_aircraft
FROM Aeroflow.V0_puertas g
LEFT JOIN Aeroflow.V0_salidas v
  ON v.simulation_id = g.simulation_id AND v.gate_id = g.gate_id
GROUP BY g.simulation_id, g.gate_id, g.terminal_id, v.destination_id
;

-- --------------------------------------------------------------------------
-- D2_pct_sobre_umbral_puerta  (Vista derivada)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.D2_pct_sobre_umbral_puerta AS
SELECT g.simulation_id, g.gate_id, g.terminal_id, g.gate_threshold,
       COUNT(v.event_id) AS valid_departures,
       COALESCE(SUM(v.exceeds_threshold), 0) AS over_threshold,
       CASE WHEN COUNT(v.event_id) = 0 THEN 0.0
            ELSE COALESCE(SUM(v.exceeds_threshold), 0) * 100.0 / COUNT(v.event_id) END AS pct_over_threshold
FROM Aeroflow.V0_puertas g
LEFT JOIN Aeroflow.V0_salidas v
  ON v.simulation_id = g.simulation_id AND v.gate_id = g.gate_id
GROUP BY g.simulation_id, g.gate_id, g.terminal_id, g.gate_threshold
;

-- --------------------------------------------------------------------------
-- D3_horas_franjas  (Vista derivada)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.D3_horas_franjas AS
SELECT simulation_id, gate_id, local_hour, time_band,
       COUNT(*) AS valid_departures,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, gate_id, local_hour, time_band
;

-- --------------------------------------------------------------------------
-- D4_laborables_fin_semana  (Vista derivada)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.D4_laborables_fin_semana AS
SELECT simulation_id, day_type,
       COUNT(*) AS valid_departures,
       COUNT(DISTINCT aircraft_id) AS distinct_aircraft,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, day_type
;

-- --------------------------------------------------------------------------
-- D4b_evolucion_diaria  (Vista derivada)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.D4b_evolucion_diaria AS
SELECT simulation_id, scheduled_local_date, day_type,
       COUNT(*) AS valid_departures,
       COUNT(DISTINCT aircraft_id) AS distinct_aircraft,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, scheduled_local_date, day_type
;

-- --------------------------------------------------------------------------
-- D5_companias  (Vista derivada)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.D5_companias AS
SELECT simulation_id, airline,
       COUNT(*) AS valid_departures,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold,
       CASE WHEN COUNT(*) >= 100 THEN TRUE ELSE FALSE END AS meets_minimum
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, airline
;

-- --------------------------------------------------------------------------
-- D5b_companias_por_puerta  (Vista derivada)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.D5b_companias_por_puerta AS
SELECT simulation_id, airline, gate_id,
       COUNT(*) AS valid_departures,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, airline, gate_id
;

-- --------------------------------------------------------------------------
-- D6_retraso_medio_magnitud  (Vista derivada)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.D6_retraso_medio_magnitud AS
SELECT g.simulation_id, g.gate_id, g.terminal_id, v.destination_id,
       COUNT(v.event_id) AS valid_departures,
       AVG(v.delay_minutes) AS avg_delay_minutes,
       COALESCE(SUM(v.exceeds_threshold), 0) AS over_threshold,
       AVG(CASE WHEN v.exceeds_threshold = 1 THEN v.minutes_over_threshold END) AS avg_minutes_over,
       MAX(CASE WHEN v.exceeds_threshold = 1 THEN v.minutes_over_threshold END) AS max_minutes_over,
       CASE WHEN COUNT(v.event_id) = 0 THEN 'Sin salidas'
            WHEN COALESCE(SUM(v.exceeds_threshold), 0) = 0 THEN 'Sin superaciones'
            ELSE 'Con superaciones' END AS note
FROM Aeroflow.V0_puertas g
LEFT JOIN Aeroflow.V0_salidas v
  ON v.simulation_id = g.simulation_id AND v.gate_id = g.gate_id
GROUP BY g.simulation_id, g.gate_id, g.terminal_id, v.destination_id
;

-- --------------------------------------------------------------------------
-- D7_aviones_repetidos_dia  (Vista derivada)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.D7_aviones_repetidos_dia AS
SELECT simulation_id, aircraft_id, scheduled_local_date,
       COUNT(DISTINCT operation_id) AS operations,
       COUNT(*) AS over_threshold_departures,
       MAX(minutes_over_threshold) AS max_minutes_over
FROM Aeroflow.V0_salidas
WHERE exceeds_threshold = 1
GROUP BY simulation_id, aircraft_id, scheduled_local_date
HAVING COUNT(DISTINCT operation_id) >= 2
;

-- --------------------------------------------------------------------------
-- D8_compania_modelo  (Vista derivada)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.D8_compania_modelo AS
SELECT simulation_id, airline, aircraft_model,
       COUNT(*) AS valid_departures,
       SUM(exceeds_threshold) AS over_threshold,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_over_threshold,
       CASE WHEN COUNT(*) >= 100 THEN TRUE ELSE FALSE END AS meets_minimum
FROM Aeroflow.V0_salidas
GROUP BY simulation_id, airline, aircraft_model
;

-- --------------------------------------------------------------------------
-- D9_aviones_con_superacion  (Vista derivada)
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW Aeroflow.D9_aviones_con_superacion AS
SELECT simulation_id,
       COUNT(*) AS valid_departures,
       COUNT(DISTINCT aircraft_id) AS distinct_aircraft,
       COUNT(DISTINCT CASE WHEN exceeds_threshold = 1 THEN aircraft_id END) AS aircraft_with_exceedance,
       SUM(exceeds_threshold) AS over_threshold_departures,
       COUNT(DISTINCT CASE WHEN exceeds_threshold = 1 THEN aircraft_id END) * 100.0 / COUNT(DISTINCT aircraft_id) AS pct_aircraft_with_exceedance,
       SUM(exceeds_threshold) * 100.0 / COUNT(*) AS pct_departures_over_threshold
FROM Aeroflow.V0_salidas
GROUP BY simulation_id
;
