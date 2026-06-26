# Diagnostico de preparacion de ejecucion - Fase 6

Arquitectura de ejecucion para correr el DSS y los baselines de SVRPBench bajo el mismo
protocolo (mismas instancias, restricciones, realizaciones y metricas). **No** se ejecuto el
benchmark final ni los modelos de forma masiva. El DSS sigue intacto (15 vistas, app importa).

---

## 1. ¿Que modelos base estan realmente disponibles?

Verificado en runtime (`list_solvers()` de la suite + smoke test):

| Modelo | Solver id | Disponible | Comprobacion |
|---|---|---|---|
| OR-Tools | `or-tools` | **Si** | registrado + corre |
| NN + 2-opt | `nn2opt` | **Si** | registrado + smoke OK (50 clientes) |
| Tabu Search | `tabu` | **Si** | registrado |
| ACO | `aco` | **Si** | registrado (runtime alto en grandes) |
| DSS (sistema bajo prueba) | - | **Si** | optimizador del DSS corre via adaptador |

## 2. ¿Que modelos se podran ejecutar en la comparacion?

- **Obligatorios**: DSS, OR-Tools.
- **Viables**: NN+2opt, Tabu.
- **Opcional**: ACO (se incluira con cuidado por su runtime).

## 3. ¿Que modelos fueron descartados y por que?

| Modelo | Estado | Motivo |
|---|---|---|
| POMO / Attention Model (RL) | descartado (no recomendado) | requieren `rl4co`+`torch` (~2 GB) y GPU; no instalados (instruccion 8) |
| LKH-3 | descartado | requiere binario externo del sistema |
| ALNS | descartado | no existe en la suite |

## 4. ¿Como se ejecutara el DSS dentro del benchmark?

Como **modelo evaluado**: `run_dss_model.py` toma la instancia canonica, usa el **adaptador de
la Fase 5** para obtener `pedidos`/`vehiculos` (sin tocar `data/`), llama al optimizador actual
del DSS (`construir_rutas_iniciales`, motor configurable), convierte sus rutas a indices de
cliente y las puntua con el **modulo de metricas comun**. El motor del DSS no se modifica.

## 5. ¿Que archivos nuevos se crearon?

```
data_benchmark/svrpbench_runners/
  svrpbench_metrics.py        metricas COMUNES (instancia canonica + scoring uniforme)
  _suite_common.py            pegamento para baselines de la suite
  run_dss_model.py            wrapper DSS
  run_ortools_baseline.py     wrapper OR-Tools
  run_nn_2opt_baseline.py     wrapper NN+2opt
  run_tabu_baseline.py        wrapper Tabu
  run_aco_baseline.py         wrapper ACO
  run_svrpbench_benchmark.py  runner general (dry-run por defecto; --run para ejecutar)
data_benchmark/svrpbench_processed/
  benchmark_execution_config.json
  svrpbench_execution_preparation_diagnostico_fase6.md  (este)
data_benchmark/svrpbench_results/
  benchmark_results_schema.csv   plantilla con las columnas definitivas
  pilot/  final/                 carpetas de resultados
data_benchmark/svrpbench_logs/   logs por ejecucion
```

## 6. ¿Que configuracion experimental quedo preparada?

`benchmark_execution_config.json` incluye: rutas del subconjunto/instancias, tamanos
{50,100,200}, realizaciones (final=5, pilot=1), modelos por categoria, metricas, carpetas de
resultados/logs, limites de tiempo (30 s/instancia; 10 s optimizador DSS), criterios de fallo y
el bloque `pilot` (3 instancias x [DSS, or-tools] x 1 realizacion).

## 7. ¿Que metricas se calcularan para todos los modelos?

Identicas para todos (modulo comun): `total_cost`, `total_distance`, `total_time`,
`runtime_seconds`, `feasibility`, `constraint_violation_rate`, `time_window_violations`,
`otd_benchmark`, `vehicle_utilization`, `demand_fulfillment`. **Robustness** queda preparada
para la Fase 8 (desviacion estandar del costo entre realizaciones).

Definiciones clave (en `svrpbench_metrics.py`): costo = distancia euclidiana total (km, escala
0.05 km/unidad); tiempo a 18 km/h; OTD = clientes a tiempo / clientes servidos; feasibility =
demanda servida en vehiculos sin exceso de capacidad / demanda total; CVR = violaciones
(capacidad + ventana) / restricciones evaluadas x 100; utilizacion = carga / capacidad usada.

## 8. ¿Que metricas no estan disponibles para algun modelo?

Todas se calculan para todos (el scoring es externo al modelo: se aplica a las rutas que cada
modelo produce). **Matiz**: `time_window_violations` y `otd_benchmark` dependen de las ventanas;
con ventanas **abiertas por defecto** (no materializadas), OTD tiende a 1.0 salvo cuando una
ruta consolidada excede el fin de jornada (19:00). Cuando se materialicen ventanas reales, estas
dos metricas tomaran valores plenos sin cambiar el codigo.

## 9. ¿Como se controla que todos usen las mismas instancias?

Todos los wrappers reciben la **misma `CanonicalInstance`** cargada del subconjunto de la Fase 4
(`svrpbench_subset.parquet`) por `instance_uid`. El runner itera la misma lista de instancias
para todos los modelos.

## 10. ¿Como se controla que usen las mismas restricciones?

La instancia canonica define depot, demandas, capacidades, vehiculos y (cuando existan) ventanas;
los wrappers la consumen sin alterarla. El DSS la recibe via el adaptador (mismas capacidades y
demandas); los baselines la reciben como `Instance` de la suite construida de los mismos campos.
El scoring es comun, asi que las violaciones se miden igual para todos.

## 11. ¿Como se manejaran soluciones infactibles?

No se descartan ni se corrigen. Una solucion con exceso de capacidad o llegada fuera de ventana
se reporta con `feasibility < 1`, `constraint_violation_rate > 0` y `time_window_violations > 0`.
Los clientes no servidos reducen `demand_fulfillment`.

## 12. ¿Como se registraran errores?

Cada wrapper devuelve `error_message` (no lanza). El runner ademas envuelve cada corrida en una
red de seguridad y escribe un **log por ejecucion** (`svrpbench_logs/`) con estado OK/ERROR,
costo, runtime y mensaje. Modelos/dependencias faltantes se omiten registrando el motivo.

## 13. ¿Como se guardaran los resultados?

Por corrida: un JSON `{modelo}__{instancia}__r{realizacion}.json` en `pilot/` o `final/`, y una
fila en el CSV consolidado (`resultados_*_{timestamp}.csv`) con las columnas de
`benchmark_results_schema.csv`.

## 14. ¿Que queda listo para la Fase 7 (prueba piloto)?

- Runner con `--pilot --run` configurado para 3 instancias (50/100/200) x [DSS, OR-Tools] x 1
  realizacion (6 corridas). Por seguridad **no se ejecuta sin `--run`**.
- Metricas, schema, logs, manejo de errores y deteccion de modelos: operativos y probados en
  smoke (DSS y NN+2opt corrieron sobre la instancia de 50).

## 15. ¿Que riesgos tecnicos existen antes de la prueba piloto?

1. **Ventanas abiertas (no materializadas)**: la comparacion actual es CVRP-like; OTD/TWv no son
   plenamente significativos hasta materializar ventanas (prerequisito Fase 7/8).
2. **Runtime de baselines** en tamano 200 (ACO/Tabu pueden ser lentos): el limite de tiempo por
   instancia (30 s) mitiga, pero hay que validar que respeten timeouts.
3. **Escala/metrica de costo**: `total_cost` = distancia km con escala 0.05; debe documentarse al
   comparar con cifras publicadas del paper (otra escala).
4. **Estocasticidad de los baselines de la suite** (muestreo de trafico/accidentes) vs el scoring
   determinista comun: en el piloto se usa 1 realizacion; la coherencia estocastica se aborda en
   Fase 8 (robustness con semillas compartidas).
5. **Comparabilidad de rutas**: se asume que las rutas de la suite usan indices de nodo con
   deposito 0 y clientes 1..N (verificado en resultados precomputados); revisar si algun solver
   devuelve otro formato.

---

## Estado del DSS

**Intacto.** No se modifico `app.py`, optimizador, simulador, metricas, dashboards ni vistas. No
se uso/sobrescribio `data/`. La preparacion es aditiva y separada del flujo operativo. No se
ejecuto el benchmark final ni los modelos de forma masiva (solo smoke de 1 instancia para
validar la integracion).
