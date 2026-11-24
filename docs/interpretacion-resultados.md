# Interpretación de resultados (borrador de trabajo)

> **Nota de alcance.** El enunciado exige que *el análisis de resultados y las
> conclusiones sean de elaboración propia*. Este documento es material de
> trabajo: recoge los hallazgos con sus cifras **verificadas contra Dremio** y
> la trazabilidad hacia la configuración del simulador, para que la redacción
> final de la memoria parta de números defendibles. Cada cifra es reproducible
> con las consultas del anexo; reescríbelo con tus propias palabras y sé capaz
> de defender cada número.

Escenario analizado: **SIM-01**, 7 días (05/10–11/10/2026), **1.007 salidas
válidas**, 50 aviones (18–22 salidas por avión, media 20,1), 10 compañías,
4 destinos, 5 puertas con umbral 15 min (20 min en G4).

---

## Hallazgo 1 — Dónde se concentran: puerta G4 y destino DEST-02

**Qué se compara.** El porcentaje de salidas que superan el umbral de su
puerta, desglosado por puerta y por destino, aislando el efecto de cada factor.

**Resultado numérico.**

| Segmento | Superan / Salidas | % |
|---|---|---|
| **G4** (todas) | 128 / 206 | **62,14 %** |
| Resto de puertas | 246 / 801 | 30,71 % |
| **DEST-02** (todos) | 115 / 233 | **49,36 %** |
| Resto de destinos | 259 / 774 | 33,46 % |
| G4 + DEST-02 (intersección) | 36 / 44 | **81,82 %** |

Los dos efectos no son el mismo dato disfrazado: dentro de G4, el 81,82 % de
los vuelos a DEST-02 supera el umbral frente al 56,79 % del resto de G4
(92/162); y fuera de G4, DEST-02 sigue en 41,80 % (79/189) frente al
26,05–29,89 % de los otros destinos. Es decir, **cada factor aporta por su
cuenta** y juntos se potencian (probabilidades que el simulador multiplica:
0,24 × 2,0 × 1,5 = 0,72 → 72 % esperado, observado 81,8 % con n = 44).

La raíz está en la configuración (`app/seed.py`): el perfil de generación
multiplica la probabilidad de retraso por 2,0 en G4 y por 1,5 en DEST-02.
El resultado numérico reproduce el mecanismo sembrado, no un patrón emergente.

**Limitaciones.**
- n = 44 en la celda G4×DEST-02: la diferencia entre 81,8 % y el 72 % teórico
  está dentro del ruido muestral (desviación típica ≈ 6,8 puntos).
- El umbral de G4 es 20 min, no 15: comparar porcentajes entre puertas compara
  también umbrales distintos (G4 lo supera *pese a* tener el umbral más
  exigente, lo que refuerza el hallazgo).
- Un solo escenario de 7 días; el porcentaje puntual de una celda pequeña no
  es estable entre simulaciones.

Aparece en el informe: página 1 (barras por puerta) y página 3 (tabla
puerta–destino con superaciones).

---

## Hallazgo 2 — Cuándo se concentran: la franja nocturna (18–24 h)

**Qué se compara.** El porcentaje de superación por franja horaria local, y el
efecto *puro* de franja tras excluir la puerta G4 (para separar el efecto del
horario del efecto de composición: qué puertas vuelan de noche).

**Resultado numérico.**

| Franja | Superan / Salidas | % | % sin G4 (n) |
|---|---|---|---|
| **Noche (18–24)** | 119 / 235 | **50,64 %** | **39,88 %** (173) |
| Mañana (06–12) | 102 / 301 | 33,89 % | 29,10 % (244) |
| Tarde (12–18) | 94 / 286 | 32,87 % | 27,85 % (237) |
| Madrugada (00–06) | 59 / 185 | 31,89 % | 27,21 % (147) |

Dos componentes suman el efecto:

1. **Efecto directo de la franja.** Sin G4, la noche casi duplica al resto
   (39,88 % frente a 27,2–29,1 %). La configuración aplica un multiplicador de
   1,7 al tramo 18–24 h: 0,24 × 1,7 = 0,408 → 40,8 % esperado, observado
   39,9 %.
2. **Efecto de composición (menor).** De noche vuela proporcionalmente más G4
   (26,4 % de las salidas nocturnas frente al 17–20 % en otras franjas), lo que
   añade un punto extra al agregado.

Advertencia de nomenclatura: la franja que el informe llama **«Noche (18–24)»
es el tramo `evening` del generador** (18:00–23:59), el único con
multiplicador 1,7. La «Madrugada (00–06)» es el `night` del generador, que
**no** tiene multiplicador de retraso (solo de volumen, 0,75). El nombre de la
vista y el del perfil no coinciden; conviene no mezclarlos en la memoria.

**Limitaciones.**
- La hora local procede de una zona horaria fija (Europa/Madrid) sobre
  fechas UTC; 54 vuelos cambian de día al convertir. Si la franja se calculara
  en UTC, el resultado cambiaría.
- Franjas con n ≈ 185–301: diferencias de 2–3 puntos entre Mañana, Tarde y
  Madrugada (33,9 / 32,9 / 31,9 %) **no son distinguibles del ruido**; la única
  diferencia clara es la nocturna (+17 puntos).
- El «peor día» (11/10, domingo, 64 superaciones en 140 salidas = 45,7 %)
  concentra el aparente efecto fin de semana; ver Hallazgo 3 y la sección de
  patrones emergentes.

Aparece en el informe: página 2 (evolución diaria, barras por franja y tabla
por tipo de día).

---

## Hallazgo 3 — Proporción de salidas vs proporción de aviones: 37,14 % ≠ 100 %

**Qué se compara.** Dos formas legítimas de medir «cuánto supera el umbral»:
sobre salidas (vuelo a vuelo) y sobre aviones (alguna superación por matrícula).

**Resultado numérico.**

| Indicador | Valor | Muestra |
|---|---|---|
| Salidas que superan el umbral | **37,14 %** | 374 de 1.007 |
| Aviones con alguna superación | **100 %** | 50 de 50 |
| Superaciones por avión afectado | media 7,5; máx 11; mín 1 | 50 aviones |
| Reparto de aviones | 1 con 1–3 superaciones; 14 con 4–6; 35 con 7 o más | 50 aviones |

La lectura conjunta: un porcentaje bajo por vuelo (37,14 %) convive con un
100 % de flota afectada porque cada avión opera ~20 salidas en la semana; a
nivel de matrícula, la probabilidad de acabar con al menos una superación se
dispara. Con la media de 7,5 superaciones por avión, el dato útil no es *si*
un avión supera el umbral sino *cuántas veces*.

**Limitaciones.**
- El indicador de aviones está **saturado en este escenario**: no discrimina
  (50 = 50). Verificado que no es un bug de agregación: los 50 aviones tienen
  al menos una superación (mínimo 1). Con otra configuración (menos días, más
  aviones, menor probabilidad) dejaría de ser 100 %.
- No se puede promediar ni sumar «aviones con superación» por puerta: un avión
  repite en varias puertas y la suma superaría el total del aeropuerto. Cada
  total se calcula en su contexto (la suma de aviones distintos por puerta no
  es el total de aviones distintos).
- La comparación de los dos porcentajes solo tiene sentido dentro del mismo
  periodo y simulación.

Aparece en el informe: tarjetas de las páginas 1 y 3.

---

## Dos prioridades de seguimiento

Justificadas con porcentaje y tamaño de muestra (no solo recuentos):

**P1. Auditar la pareja G4 + DEST-02.** 44 salidas en 7 días (4,4 % del
volumen) concentran 36 superaciones: el **11,7 % de todas las superaciones del
aeropuerto** con una tasa del **81,82 %**, frente al 30,71 % del resto de la
planta. Si el patrón se mantuviera en simulaciones más largas, sería la
primera candidata a revisión de planificación o de umbral. Vigilar además G4
en solitario (62,14 %, n = 206): es la puerta con umbral más alto (20 min) y
aun así la peor.

**P2. Vigilar la franja 18–24 h.** 235 salidas (23,3 % del volumen) generan
119 superaciones: el **31,8 % del total** con tasa del **50,64 %**, diecisiete
puntos por encima de cualquier otra franja. El efecto persiste excluyendo G4
(39,88 %, n = 173), así que no es solo composición. Acción de seguimiento:
presupuestar refuerzos entre las 18 y las 24 h y comprobar si el pico horario
de las 20 h (64,1 %, n = 39) se mantiene o era ruido.

---

## Qué patrones proceden de la configuración y cuáles emergen

**Sembrados en la configuración** (`app/seed.py`, semilla 42) y visibles tal
cual en los resultados:

| Configuración | Resultado observado |
|---|---|
| Multiplicador de retraso ×2,0 en G4 | G4 al 62,14 % (n = 206) vs 30,71 % el resto |
| Multiplicador ×1,5 en DEST-02 | DEST-02 al 49,36 % (n = 233) vs 33,46 % el resto |
| Multiplicador ×1,7 en la franja 18–24 | Noche al 50,64 % (n = 235); efecto puro 39,9 % ≈ 0,24×1,7 |
| Volumen: mañana ×1,2, madrugada ×0,75 | Mañana es la franja más cargada (301 salidas) y Madrugada la menos (185) |
| Umbrales 15 min (20 en G4) | El «estricto >» deja 36 vuelos exactamente en el umbral sin contar como superación |
| Probabilidad base 0,24 con tope 1,0 | 374 superaciones observadas frente a 380,1 esperadas al componer los multiplicadores por segmento (diferencia 1,6 %, dentro del ruido) |

**Emergentes (no hay parámetro que los provoque):**

- **El fin de semana sale peor**: 40,21 % (n = 286, 2 días) frente a 35,92 %
  (n = 721, 5 días). No existe multiplicador por tipo de día. La diferencia es
  de 4,3 puntos ≈ 1,3 desviaciones típicas y está concentrada casi por entero
  en el domingo 11/10 (45,7 %, n = 140). Con una semana de datos, la conclusión
  honesta es que **probablemente es ruido**; habría que simular más semanas
  antes de darlo por bueno.
- **Horas pico sueltas** (20 h al 64,1 %, 15 h al 50 %, 18 h al 55 %): celdas
  de n ≈ 35–55, inestables; el agregado por franja es la lectura fiable.
- **Compañías**: el rango entre la peor (Aero03, 43,0 %) y la mejor
  (Aero06/Aero10, 31,7 %) es de 11,3 puntos con n ≈ 100 cada una; con
  p ≈ 0,37 y 10 muestras de ese tamaño, un rango así entre extremos es lo
  esperable por azar (σ ≈ 4,8 puntos por compañía). El simulador no
  distingue compañías, y los datos tampoco lo contradicen.

**Reconciliación global.** Componer la probabilidad base (0,24) con los tres
multiplicadores por segmento —con el tope en 1,0— reproduce el total: **380,1
superaciones esperadas frente a 374 observadas** (1,6 % de desviación, dentro
del ruido). Además, 36 vuelos quedan exactamente en el umbral y no cuentan
como superación por el «>» estricto; con «>=» serían 410. La simulación no es
solo cualitativamente coherente con la configuración: es cuantitativamente
reconciliable segmento a segmento. La semilla fija (42) hace la simulación
determinista: la misma configuración regenera exactamente los mismos 1.007
eventos.

---

## Por qué estas conclusiones no se trasladan a un aeropuerto real

1. **Los retrasos son independentes y de probabilidad constante por segmento.**
   Cada vuelo es un Bernoulli aislado: un retraso no encadena retrasos. En un
   aeropuerto real la causa dominante es precisamente la dependencia (rotación
   de aeronaves, tripulaciones, slots): un avión retrasado retrasa la cadena.
   Aquí no existe ni rotación real (los 50 aviones hacen 18–22 salidas en 7
   días siempre en el mismo entorno) ni propago.
2. **La duración del retraso es uniforme, sin cola pesada.** Al superar el
   umbral, el exceso es uniforme entre 1 y 60 min (media 30,8). Los retrasos
   reales tienen distribuciones con cola larga y multimodales (reacciones en
   cadena, meteorología, technicals); la media y el máximo aquí (60 min
   exactos, tope del parámetro) no se parecen a esa realidad.
3. **El umbral es arbitrario y fijo** (15/20 min de configuración), no una
   métrica operativa (p. ej. facturación, slot, curfew). El 37,14 % es
   sensible al valor elegido: con umbral 20 en todas las puertas bajaría sin
   que cambie ningún vuelo.
4. **El catálogo es ficticio y diminuto**: 5 puertas, 4 destinos, 10
   compañías, 50 aviones, 7 días, 1.007 salidas. Un aeropuerto medio maneja
   órdenes de magnitud más operaciones con recursos compartidos y saturación
   horaria; aquí ninguna puerta se satura porque la capacidad no se modela.
5. **Muestras pequeñas por celda.** Las diferencias de menos de ~5 puntos entre
   segmentos de n ≈ 100–300 no son estadísticamente distinguibles del ruido
   (como el aparente efecto fin de semana). En explotación real esas diferencias
   motivarían decisiones; aquí no deberían.
6. **No hay estacionalidad, ni eventos discrecionales, ni crecimiento.** La
   demanda es constante por construcción (pesos de volumen fijos), de modo que
   cualquier patrón temporal observado solo puede venir de los multiplicadores
   o del azar — nunca de la demanda real, que es el motor de los picos en un
   aeropuerto verdadero.

En consecuencia: los tres hallazgos son válidos como **verificación de que la
plataforma mide lo que la configuración simula** y como ejercicio de lectura
de un cuadro de mando, no como conclusiones operativas sobre gestión aeroportuaria.

---

## Anexo — Consultas de verificación (Dremio, espacio `Aeroflow`)

Todas filtradas por `simulation_id = 'SIM-01'`.

```sql
-- H1: porcentaje por puerta y por destino
SELECT gate_id, valid_departures, over_threshold,
       ROUND(100.0*over_threshold/valid_departures, 2) pct
FROM Aeroflow.D2_pct_sobre_umbral_puerta
WHERE simulation_id = 'SIM-01' ORDER BY pct DESC;

-- H1: intersección G4 x DEST-02 y efectos puros (grano vuelo)
SELECT gate_id, destination_id, COUNT(*) salidas,
       SUM(exceeds_threshold) superan,
       ROUND(100.0*AVG(exceeds_threshold), 2) pct
FROM Aeroflow.V0_salidas
WHERE simulation_id = 'SIM-01'
GROUP BY gate_id, destination_id ORDER BY pct DESC;

-- H2: franjas y efecto puro de franja (sin G4)
SELECT time_band, COUNT(*) salidas, SUM(exceeds_threshold) superan,
       ROUND(100.0*AVG(exceeds_threshold), 2) pct
FROM Aeroflow.V0_salidas
WHERE simulation_id = 'SIM-01' [AND gate_id <> 'G4']
GROUP BY time_band ORDER BY pct DESC;

-- H3: salidas vs aviones
SELECT COUNT(*) salidas, SUM(exceeds_threshold) superan
FROM Aeroflow.V0_salidas WHERE simulation_id = 'SIM-01';

SELECT COUNT(*) aviones, MIN(n) minimo, MAX(n) maximo, ROUND(AVG(n), 1) media
FROM (SELECT aircraft_id, SUM(exceeds_threshold) n
      FROM Aeroflow.V0_salidas
      WHERE simulation_id = 'SIM-01' GROUP BY aircraft_id) t;

-- Tipo de día (verificacion del aparente efecto fin de semana)
SELECT day_type, COUNT(*) salidas, SUM(exceeds_threshold) superan,
       ROUND(100.0*AVG(exceeds_threshold), 2) pct
FROM Aeroflow.V0_salidas WHERE simulation_id = 'SIM-01' GROUP BY day_type;

-- Exceso en minutos (solo superaciones)
SELECT MIN(minutes_over_threshold), MAX(minutes_over_threshold),
       ROUND(AVG(minutes_over_threshold), 1), COUNT(*)
FROM Aeroflow.V0_salidas
WHERE simulation_id = 'SIM-01' AND exceeds_threshold = 1;
```

Parámetros de configuración usados en la trazabilidad (`app/seed.py`,
`generation_profiles` de SIM-01): `base_delay_probability: 0.24`,
`gate_delay_multipliers: {G4: 2.0}`, `destination_delay_multipliers:
{DEST-02: 1.5}`, `time_band_delay_multipliers: {evening: 1.7}`,
`max_delay_minutes_beyond_threshold: 60`, `random_seed: 42`.
