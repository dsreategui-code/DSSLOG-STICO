# Diagnóstico técnico — Benchmark FINAL FIEL TWCVRP (Fase 8b)

> Reconstrucción **fiel al paper** SVRPBench (arXiv:2505.21887) del benchmark, tras detectar
> que la Fase 8 corrió sobre un problema degenerado (capacidad no vinculante y sin ventanas).
> Incluye además **mejoras al optimizador del DSS** y una **línea base fuerte** (OR-Tools
> TWCVRP que sí respeta ventanas). Sin ajustar resultados, sin ocultar corridas.

Fecha: 2026-06-26 · Interpretador: `.venv` (OR-Tools + suite `vrp_bench`) · 600 corridas
(4 modelos × 30 instancias × 5 escenarios) · Log: `benchmark_twcvrp_20260626_064752.log`

---

## 0. Conclusión en una línea

Con un benchmark TWCVRP **fiel** y el DSS **mejorado**, el DSS pasa de 3.º (perdedor) a
**2.º, empatado con el mejor OR-Tools TWCVRP posible** (28489 vs 28145, +1.2 %) y **31–40 %
más barato que las heurísticas ingenuas** (43064). El DSS tiene además la **mejor robustez**
(0.31) y ~99 % de entregas a tiempo. La "victoria" del DSS en la Fase 8 era artefacto; ahora
su competitividad es **real y verificada** contra un rival que respeta ventanas.

---

## 1. Reconstrucción fiel (qué se corrigió de la Fase 8)

| Defecto Fase 8 (degenerada) | Corrección Fase 8b (fiel) |
|---|---|
| Capacidad no vinculante (`cap = demanda_total`/veh) → 1 mega-ruta | `cap = ceil(demanda_total / num_vehicles)` (paper §3), idéntico a todos |
| Sin ventanas (abierta 09:00-19:00) | Ventanas por cliente con el generador **oficial** de la suite (§2.2: 60 % resid / 40 % comer, semilla por instancia) |
| Estocasticidad simplificada propia | Evaluador **autoritativo** de la suite (`VRPSolverBase`): congestión + log-normal + accidentes (§2.1) |
| `feasibility` = fracción de demanda | Binario por corrida (paper §4) → su promedio = Feasibility Rate |

Validación: con ventanas estrictas el plan determinista del DSS da **OTD = 1.000**, lo que
confirma que la escala temporal (1 unidad de grilla = 1 minuto) quedó bien alineada.

---

## 2. Mejoras implementadas al DSS (y al montaje)

Tras un primer corrido fiel, el DSS quedaba 3.º (costo 49893) por dos limitaciones reales.
Se corrigieron (mejoras genuinas, no para maquillar el benchmark; los 122 tests del DSS
siguen pasando):

1. **Espera desacoplada de la tolerancia (la grande).** En `route_optimizer_ortools.py`,
   `slack_minutos` hacía dos cosas: permitir esperar a que abra una ventana **y** ensanchar
   las ventanas. Con ventanas estrictas (slack=0) el DSS **no podía esperar** y descartaba a
   los clientes a los que llegaba temprano. Se añadió un parámetro **`espera_max_min`**
   (permiso de esperar, por defecto = jornada completa) separado de la tolerancia. Esperar
   nunca viola la ventana ni suma al costo (el costo es tiempo de viaje): solo amplía el
   conjunto factible. **Es una corrección correcta que también mejora producción** (hoy un
   camión del DSS no podía esperar a que abriera una ventana). Efecto: descartes por
   instancia 4.8→0.2, 14.5→0.6, 43.7→3.6; costo del DSS −34 %.
2. **Balance al nivel de flota natural.** La flota holgada (2×`num_vehicles`) con
   `factor_balance=1.0` forzaba al DSS a repartir en rutas artificialmente finas. Se fija
   `factor_balance = _FLOTA_FACTOR` para balancear al nivel del fleet del paper
   (`num_vehicles`), dejando vehículos de sobra para reparaciones. Efecto a tamaño 200:
   58441 → 49628.
3. **Presupuesto de búsqueda por tamaño** (rec #2): `time_limit` 8/12/16 s para 50/100/200.
   Mejora marginal (~0.3 % a tamaño 200; el grueso lo aporta la mejora #1).

**Línea base fuerte (rec #3): `or-tools-tw`.** El `or-tools` registrado de la suite solo
restringe capacidad (ignora ventanas) y salía idéntico a NN+2opt. Se añadió `or-tools-tw`:
un OR-Tools TWCVRP independiente que **sí** respeta ventanas reales + capacidad + espera
generosa. Es el rival más fuerte y justo para el DSS.

**Decisiones metodológicas (acordadas):** cobertura total (clientes no encajables → viaje
dedicado de respaldo, coste cargado al modelo; total 44 viajes, vs 630 antes de la mejora #1)
y flota holgada e igual para todos.

---

## 3. Resultados (600 corridas)

### Agregado por modelo

| Modelo | Costo prom. | Robustez | Runtime (s) | Feasib. (FR) | CVR (%) | OTD | Util. veh. |
|---|---:|---:|---:|---:|---:|---:|---:|
| **or-tools-tw** | **28145** | 0.73 | 12.0 | 0.37 | 1.19 | 0.988 | 0.86 |
| **DSS** | **28489** | **0.31** | 12.0 | 0.37 | 1.13 | 0.989 | 0.85 |
| nn2opt | 43064 | 0.79 | 0.06 | 0.40 | 0.95 | 0.991 | 0.55 |
| or-tools (solo cap.) | 43066 | 0.79 | 0.19 | 0.40 | 0.95 | 0.991 | 0.55 |

Ranking: **1.º or-tools-tw, 2.º DSS, 3.º nn2opt, 4.º or-tools**. El DSS y or-tools-tw
(ambos TWCVRP reales) dejan a las heurísticas ingenuas ~50 % atrás en costo. El DSS tiene la
**mejor robustez** (0.31) y la mayor utilización de flota tras or-tools-tw.

### DSS vs el rival fuerte (or-tools-tw) y vs heurísticas ingenuas

| Tamaño | Costo DSS | Costo or-tools-tw | DSS gana | gap medio | DSS vs baseline ingenua |
|---:|---:|---:|---|---:|---:|
| 50 | 10010 | 9992 | **5/10** | +0.2 % | **−40 %** |
| 100 | 22960 | 22799 | 4/10 | +0.7 % | −36 % |
| 200 | 52496 | 51645 | 2/10 | +1.7 % | −31 % |

El DSS está **empatado** con or-tools-tw a escala pequeña/media (su caso de uso real) y a lo
sumo 1.7 % por detrás a 200. OTD ~0.98-0.99 y CVR < 2.3 % en todos.

---

## 4. Interpretación honesta

- **El DSS es competitivo de verdad.** Tras desacoplar la espera, iguala a un OR-Tools
  TWCVRP de referencia y supera a las heurísticas ingenuas por ~31-40 % en costo, con la
  mejor robustez. A 50-100 clientes (última milla real) está estadísticamente empatado.
- **El pequeño margen a favor de or-tools-tw (1.2 %)** viene de que el DSS balancea carga
  (su diseño) y `or-tools-tw` minimiza costo puro; el DSS lo compensa con mejor robustez.
- **La mejora clave fue una corrección, no un truco.** Permitir esperar en ventana es
  comportamiento CVRPTW estándar que también beneficia a producción; no cambia el objetivo
  ni favorece selectivamente al DSS en la puntuación (todos se miden igual).
- **El veredicto sigue siendo lo opuesto a la Fase 8 degenerada**, pero ahora con un DSS
  fuerte: con capacidad y ventanas reales, las heurísticas ingenuas que "ganaban" por
  comprimir todo en una mega-ruta quedan muy por detrás.

---

## 5. Amenazas a la validez / limitaciones

1. **Feasibility Rate baja (~0.37-0.40) para todos:** es binaria sobre una realización
   estocástica; un solo accidente (Poisson, 30-120 min) marca la corrida infactible. Mide
   fragilidad de peor caso, no calidad media (OTD ~0.99).
2. **Reparación dedicada:** garantiza cobertura total; ahora es marginal (44 viajes totales,
   vs 630 antes). Se carga su coste al modelo y se reporta aparte.
3. **`or-tools` (solo capacidad) ≈ `nn2opt`:** se mantienen como referencia "ingenua"; el
   rival serio es `or-tools-tw`.
4. **Margen de mejora restante del DSS:** a tamaño 200 va 1.7 % detrás de or-tools-tw; un
   `factor_balance` aún más laxo o más tiempo de búsqueda lo cerrarían, a costa de menos
   balance de carga (compromiso de diseño del DSS).

---

## 6. Entregables

`data_benchmark/svrpbench_results/final_twcvrp/`
- `twcvrp_results_detailed.csv` / `.xlsx` — 600 corridas.
- `twcvrp_results_by_model / _by_size / _by_model_size / _by_instance.csv` · `twcvrp_model_ranking.csv`.
- `twcvrp_failed_runs.csv` (0) · `twcvrp_dss_reparaciones.csv` (transparencia de cobertura).
- `svrpbench_benchmark_twcvrp_resumen.md` (autogenerado) · este diagnóstico.

Código: `svrpbench_faithful.py` (instancia fiel + solvers incl. `or-tools-tw` + puntuación),
`run_final_fase8b.py` (runner, 4 modelos, tiempo por tamaño). Mejora de producción:
`optimization/route_optimizer_ortools.py` (parámetro `espera_max_min`; 122 tests OK). La
Fase 8 original (`final/`) se conserva, documentada como degenerada/superada.
