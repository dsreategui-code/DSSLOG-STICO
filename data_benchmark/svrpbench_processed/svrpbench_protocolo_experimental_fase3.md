# Protocolo experimental SVRPBench - Fase 3

Documento metodologico que define, de forma tecnica y defendible, bajo que condiciones se
comparara el **DSS de ultima milla** contra los modelos base de SVRPBench. **No** ejecuta el
benchmark ni adapta el DSS; deja listo el protocolo para la Fase 4.

Insumos: `svrpbench_raw/svrpbench_diagnostico_fase1.md` y
`svrpbench_evaluation_suite/svrpbench_diagnostico_fase2.md`.

Convencion de evidencia (instruccion 10):
**[CONFIRMADO]** verificado en datos/codigo · **[VIABLE]** factible sin verificacion total ·
**[VALIDAR]** requiere comprobacion en Fase 4.

---

## Resumen de insumos

### Fase 1 (dataset)
- Parquet unico, split `test`, **560 instancias / 56 subsets**. Columnas: `subset_name`,
  `file_name`, `instance_id`, `locations`, `demands`, `num_vehicles`, `vehicle_capacities`,
  `appear_times`.
- Filtros viven en `subset_name` (`{variante}_{tamano}_{config}`) + `num_vehicles`.
- Tamanos: 10/20/50/100/200/500/1000 (80 instancias c/u). Variantes: cvrp (420), twcvrp (140).
- **Vacios [CONFIRMADO]**: no hay columnas de ventanas horarias (ni en `twvrp_*`), ni de
  congestion/retraso/accidente; `appear_times` es trivial (todo 0). Esas dimensiones provienen
  del **generador de la suite**, no del parquet.

### Fase 2 (suite de evaluacion)
- Baselines **[CONFIRMADO] ejecutables**: `or-tools`, `nn2opt`, `tabu`, `aco`
  (`python -m vrp_bench list`).
- **No disponibles sin dependencias pesadas**: Attention Model / POMO (rl4co+torch), LKH-3
  (binario). **ALNS no existe.**
- Metricas implementadas: `total_cost`, `runtime`, `feasibility`, `cvr`, `waiting_time`,
  `robustness`, y `time_window_violations` (condicional, TWCVRP).
- Ejecucion: CLI `python -m vrp_bench solve --solver S --data X.npz --limit N --realizations R`
  o API `evaluate(solver, instances, num_realizations)`. **Soporta multiples realizaciones.**
- Capa estocastica en `time_windows_generator.py` (ventanas residencial/comercial) y
  `travel_time_generator.py` (trafico por hora, retraso log-normal, accidentes Poisson).
- **Limitaciones [CONFIRMADO]**: instancias `.npz` no estan en `main` (estan en rama
  `classic_methods`, solo **CVRP**); `requirements.txt` incompleto (falta `scikit-learn`);
  ortools 9.9 (DSS) vs 9.10 (repo).

---

## 1. Objetivo del benchmark

Evaluar de forma reproducible y comparable la calidad operativa del DSS de ultima milla frente
a baselines establecidos de ruteo (OR-Tools y heuristicas) sobre instancias publicas de
SVRPBench con ventanas horarias e incertidumbre, usando indicadores operativos (costo,
factibilidad, cumplimiento de ventanas, robustez), de modo defendible para una tesis.

## 2. Justificacion del uso de SVRPBench

- Es un benchmark **publico, citable y reproducible** (paper arXiv 2505.21887) alineado con el
  alcance del DSS: ventanas horarias, capacidad, multi-vehiculo, **incertidumbre** (trafico,
  retrasos log-normales, accidentes).
- Aporta **baselines implementados** (OR-Tools, NN+2opt, Tabu, ACO) y una capa estocastica con
  **realizaciones multiples**, lo que permite medir **robustez**, no solo costo puntual.
- Reemplaza a ALM RRC (deprecado), cuya evaluacion media similitud de secuencia, no indicadores
  operativos.

## 3. Alcance del benchmark

Incluye unicamente condiciones comparables con el DSS:
single-depot, flota de vehiculos (multi-vehicle), ventanas horarias, capacidad vehicular,
demanda, e incertidumbre (congestion/retrasos/accidentes via generador de la suite).
**Excluye** variables locales del caso de Lima que no pertenecen al dataset publico:
instalacion de colchones, trafico especifico de Lima, seguridad urbana y condiciones
particulares de cliente.

## 4. Subconjunto experimental seleccionado

**[CONFIRMADO]** Subsets objetivo (validados en Fase 3 sobre el parquet):

| Subset | Instancias | num_vehicles | Capacidades | Cumple criterios |
|---|---|---|---|---|
| `twvrp_50_single_depot`  | 10 | 10-16 | consistentes (len = num_vehicles) | TWCVRP, single-depot, multi-vehicle, 50 |
| `twvrp_100_single_depot` | 10 | 24-34 | consistentes | TWCVRP, single-depot, multi-vehicle, 100 |
| `twvrp_200_single_depot` | 10 | 44-56 | consistentes | TWCVRP, single-depot, multi-vehicle, 200 |

- **Total: 30 instancias** (10 por tamano).
- Eleccion clave: estos `twvrp_*_single_depot` cumplen **todos** los criterios a la vez y
  ademas tienen `len(vehicle_capacities) == num_vehicles` (evitan la inconsistencia de los
  subsets `*_multi_vehicule_capacities`, donde solo hay 1 capacidad). Los `cvrp_*_single_depot`
  se descartan porque son **single-vehicle** (`num_vehicles == 1`), incompatibles con el
  criterio multi-vehicle.

**[VALIDAR]** Las **ventanas horarias** de estos subsets **no estan materializadas** en el
parquet; en Fase 4 se generan con `time_windows_generator.sample_time_window` (semilla fija) o
se obtienen del `.npz` de `Yahias21/vrp_benchmark` si los incluye. Hasta resolver esto, la
variante es "TWCVRP por etiqueta y estructura, con ventanas a materializar".

## 5. Criterios de inclusion de instancias

Una instancia se incluye si y solo si:
1. `subset_name` comienza con `twvrp_` (TWCVRP);
2. `subset_name` contiene `single_depot`;
3. `num_vehicles > 1` (multi-vehicle);
4. tamano declarado en {50, 100, 200};
5. `len(vehicle_capacities) == num_vehicles` (capacidades consistentes).

Se usan **todas** las instancias que cumplen (universo completo = 30) -> **sin muestreo, sin
sesgo de seleccion**.

## 6. Criterios de exclusion de instancias

- Variante `cvrp_*` (sin ventanas) -> fuera del alcance TWCVRP objetivo.
- `multi_depot` y `depots_equal_city` -> el DSS es single-depot.
- `num_vehicles == 1` -> no es flota.
- Tamanos 10, 20, 500, 1000 -> fuera del rango 50/100/200.
- Subsets `*_multi_vehicule_capacities` -> capacidades inconsistentes (1 valor para N vehiculos).
- Instancias que en Fase 4 no puedan materializar ventanas validas -> se reportan, no se ocultan.

## 7. Modelos base a comparar

| Categoria | Modelo | solver_id | Estado |
|---|---|---|---|
| Obligatorio | **DSS** (sistema bajo prueba) | - | a adaptar en Fase 4 |
| Obligatorio | **OR-Tools** | `or-tools` | [CONFIRMADO] |
| Deseable | **NN + 2-opt** | `nn2opt` | [CONFIRMADO] |
| Deseable | **Tabu Search** | `tabu` | [CONFIRMADO] |
| Opcional | **ACO** | `aco` | [CONFIRMADO] (runtime alto) |
| No recomendado | Attention Model / POMO | - | rl4co+torch (~2 GB), GPU |
| No recomendado | LKH-3 | - | binario externo |
| No recomendado | ALNS | - | no existe en la suite |

Justificacion de priorizacion: OR-Tools es el comparador directo (mismo motor que el DSS);
NN+2opt y Tabu son baselines simples y estables; ACO es valido pero costoso; los RL exceden el
presupuesto tecnico/reproducibilidad de la tesis.

## 8. Rol del DSS en la comparacion

El DSS es el **sistema bajo prueba (SUT)**. En Fase 4 se le entregaran las **mismas instancias,
ventanas, capacidades, demandas y realizaciones** que a los baselines, y se evaluara con las
**mismas metricas**. El DSS **no** define las reglas de evaluacion: produce rutas que el harness
de evaluacion comun puntua igual que a los demas modelos. No se ajustan soluciones a su favor.

## 9. Metricas principales

| Metrica | Comparacion |
|---|---|
| Total Cost | directa |
| Feasibility Rate | directa |
| Constraint Violation Rate (CVR) | directa |
| Time Window Violations | directa (TWCVRP) |
| OTD benchmark | directa (indicador operativo del DSS, calculado uniforme para todos) |
| Runtime | directa (contextual: hardware comun) |
| Robustness | directa |

## 10. Metricas complementarias

| Metrica | Uso |
|---|---|
| Total Distance / Total Time | complementario (desagregado del costo) |
| Waiting Time | complementario |
| Vehicle Utilization | complementario (no nativo; derivado de rutas + capacidades) |
| Demand Fulfillment | complementario (relacionado con feasibility) |

## 11. Formulas de calculo

| Metrica | Definicion / formula | Unidad | Interpretacion |
|---|---|---|---|
| Total Cost | suma de costos de arco de todas las rutas (distancia/velocidad + retraso muestreado) | unidades de costo del suite | menor = mejor |
| Total Distance | suma de distancias euclidianas de arcos (sin retraso) | unidades de distancia | menor = mejor |
| Runtime | tiempo de pared del solver por instancia | s | menor = mejor |
| Feasibility Rate | fraccion de demanda servida respetando capacidad y ventana | [0,1] | mayor = mejor |
| CVR | nº restricciones violadas / nº restricciones evaluadas x 100 | % | menor = mejor |
| Time Window Violations | nº (o tiempo) de llegadas fuera de ventana | conteo o min | menor = mejor |
| **OTD benchmark** | **clientes atendidos dentro de ventana / clientes totales** | [0,1] | mayor = mejor |
| Robustness | **desv. estandar del total_cost entre las 5 realizaciones** | unidades de costo | menor = mas robusto |
| Waiting Time | tiempo de espera por llegar antes de apertura de ventana | min | menor = mejor |
| Vehicle Utilization | carga transportada / capacidad total disponible | [0,1] | contextual |
| Demand Fulfillment | demanda servida / demanda total | [0,1] | mayor = mejor |

## 12. Numero de corridas por instancia

**5 realizaciones estocasticas por instancia** (`num_realizations=5`), **[CONFIRMADO]** soportado
por la suite. Total de evaluaciones por modelo: 30 instancias x 5 = **150 corridas**. Las 5
realizaciones usan la **misma secuencia de semillas** para todos los modelos.

## 13. Reglas para manejar incertidumbre

- La incertidumbre (trafico por hora, retraso log-normal, accidentes Poisson) se aplica con el
  **generador de la suite** (`travel_time_generator`), no con parametros del caso de Lima.
- **Semilla global = 42**; cada instancia x realizacion usa una semilla derivada determinista,
  **identica para DSS y baselines**, de modo que todos enfrentan las mismas realizaciones.
- La robustez se mide sobre esas 5 realizaciones (seccion 15).

## 14. Calculo del OTD benchmark

`OTD = (nº de clientes cuya hora de llegada cae dentro de [apertura, cierre] de su ventana) /
(nº total de clientes)`.
- Se calcula **por realizacion** con las horas de llegada efectivas (incluyendo retrasos), y se
  **promedia por instancia** y luego por subconjunto.
- Lo calcula **nuestro harness de evaluacion** de forma uniforme para el DSS y para cada
  baseline (no depende de que el solver lo reporte).

## 15. Calculo de la robustez

`Robustness(instancia) = std( total_cost_r ), r = 1..5` (desviacion estandar del costo total
entre las 5 realizaciones de la misma instancia). Menor desviacion = mayor robustez. Se reporta
ademas el coeficiente de variacion (`std/mean`) como complemento normalizado.

## 16. Reglas para manejar soluciones infactibles

1. Si una solucion viola capacidad o ventana: se **marca la instancia como infactible** para ese
   modelo/realizacion (`feasibility < 1`, `cvr > 0`, `time_window_violations > 0`).
2. Se **reportan las violaciones** (cantidad y tipo); no se descartan filas.
3. **No se ocultan** resultados desfavorables.
4. **No se ajustan** soluciones manualmente para favorecer al DSS.
5. Las metricas agregadas se reportan **con y sin** instancias infactibles cuando aplique, para
   transparencia.

## 17. Condiciones de comparabilidad

Todos los modelos (DSS incluido) se evaluan con:
- las **mismas 30 instancias**;
- las **mismas ventanas** materializadas (misma semilla);
- las **mismas capacidades** y **demandas** (las del dataset);
- las **mismas 5 realizaciones** estocasticas (mismas semillas);
- el **mismo harness** y las **mismas metricas**;
- el **mismo mapeo de unidades** suite<->DSS (a fijar en Fase 4);
- ejecucion en el **mismo hardware** para que `runtime` sea comparable.

## 18. Limitaciones metodologicas

- **Ventanas no materializadas en el parquet** [VALIDAR]: dependemos del generador de la suite o
  de la fuente `.npz`; debe documentarse la semilla y el metodo exacto.
- **Dos fuentes HF** (parquet `MBZUAI/svrp-bench` vs `.npz` `Yahias21/vrp_benchmark`): pueden
  diferir; hay que fijar **una sola** en Fase 4.
- **Mapeo de unidades**: las coordenadas (~0-1000) y el "reloj" del suite no son HH:MM del DSS;
  el costo del DSS debe traducirse a la escala del suite, o viceversa, sin favorecer a ninguno.
- **`num_depots` por `demand==0`** es ambiguo (clientes con demanda 0); para single-depot se
  asume `locations[0]` como deposito.
- **Version OR-Tools** distinta (9.9 vs 9.10): riesgo bajo, pero a documentar.
- **Sin RL**: la comparacion no incluye modelos de aprendizaje; se podran citar sus resultados
  publicados del README como referencia externa, no como corrida propia.
- **n=30 instancias**: muestra moderada; los resultados se interpretan con intervalos/desviacion,
  no como diferencias absolutas finas.

## 19. Archivos que deberan crearse en la Fase 4

```
data_benchmark/svrpbench_processed/
  instances/twvrp_{50,100,200}_single_depot/inst_{id}.json   # instancia normalizada
  time_windows/seed42/twvrp_{size}_{id}.json                  # ventanas materializadas
  unit_mapping.json                                           # mapeo de unidades suite<->DSS

data_benchmark/svrpbench_results/
  {modelo}/{subset}_{instancia}_r{realizacion}.json          # resultado por corrida
  benchmark_consolidado.csv                                   # tabla larga (modelo x instancia x realizacion)
  benchmark_consolidado.xlsx                                  # detalle + resumen agregado
  resumen_por_modelo.csv                                      # agregados por modelo y tamano
```

Codigo a implementar en Fase 4 (en `svrpbench_scripts/`, sin tocar el DSS):
`svrpbench_loader.py`, `svrpbench_adapter.py` (instancia -> formato DSS, **wrapper**),
`svrpbench_runner.py` (corre DSS + baselines bajo el mismo harness),
`svrpbench_metrics.py` (OTD, robustez, TW violations, etc.), reutilizando
`svrpbench_scripts/bench_common.py` para exportar CSV/XLSX.

## 20. Recomendacion final antes de pasar a la Fase 4

1. **Resolver el origen de las ventanas e incertidumbre** (insumo critico): decidir y documentar
   si se usa el **generador de la suite** (recomendado, reproducible con semilla) o el `.npz` de
   `Yahias21/vrp_benchmark`; fijar **una sola fuente**.
2. **Definir el mapeo de unidades** suite<->DSS antes de cualquier corrida.
3. **Construir primero el subconjunto procesado** (30 instancias) y validar que el harness corre
   **una** instancia con OR-Tools antes de escalar (prueba de humo, no masiva).
4. Mantener el DSS **intacto**: el adaptador vive en `svrpbench_scripts/` como wrapper; no se
   modifican optimizador, simulador, metricas, dashboards, vistas ni `app.py`.
5. Congelar este protocolo (`benchmark_protocol_config.json`) como contrato experimental;
   cualquier cambio se versiona explicitamente.

---

### Estado del DSS
Intacto. Esta fase solo produjo documentacion (`benchmark_protocol_config.json` y este `.md`)
en `data_benchmark/svrpbench_processed/`. No se ejecuto el benchmark ni se adapto el DSS.
