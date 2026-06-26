# Diagnostico del subconjunto SVRPBench - Fase 4

Construccion del subconjunto procesado segun el protocolo de la Fase 3
(`svrpbench_protocolo_experimental_fase3.md`) y el diagnostico de la Fase 1
(`svrpbench_raw/svrpbench_diagnostico_fase1.md`).

**No** se adapta el DSS, **no** se ejecutan modelos, **no** se altera el crudo. Solo se
filtraron, validaron y guardaron las instancias que cumplen el protocolo, de forma trazable.

---

## 1. ¿Que archivos crudos se usaron?

- `data_benchmark/svrpbench_raw/svrpbench_test.parquet` (560 instancias, split `test`,
  solo lectura). El crudo **no fue modificado** (verificado por fecha de modificacion).

## 2. ¿Que filtros se aplicaron?

Filtros secuenciales y trazables (cada instancia excluida guarda el **primer** filtro que la
descarta):

| Paso | Regla |
|---|---|
| F1_variante_TWCVRP | `subset_name` comienza con `twvrp_` |
| F2_single_depot | `single_depot` in `subset_name` |
| F3_tamano_50_100_200 | tamano derivado en {50, 100, 200} |
| F4_multi_vehicle | `num_vehicles > 1` |
| F5_capacidades_consistentes | `len(vehicle_capacities) == num_vehicles` |
| F6_campos_criticos_no_nulos | clientes+deposito+demanda+capacidad+vehiculos+id+tamano no nulos |

## 3. ¿Que campos reales del dataset se usaron para cada filtro?

| Filtro | Campo real |
|---|---|
| Tipo de problema / ventanas | `subset_name` (prefijo `twvrp_`) |
| Single-depot | `subset_name` (`single_depot`) |
| Tamano | derivado de `subset_name` (y validado con `len(locations)-1`) |
| Multi-vehicle | `num_vehicles` |
| Capacidad consistente | `len(vehicle_capacities)` vs `num_vehicles` |
| Campos criticos | `locations`, `demands`, `vehicle_capacities`, `num_vehicles`, `instance_id` |

> **Nota (instruccion 11):** el campo de **valores de ventana horaria NO existe** en el parquet.
> Por eso el filtro de ventanas se aplico a nivel de **variante** (`twvrp_`), que es el marcador
> oficial del dataset para la variante con ventanas. **No se invento** ninguna columna.

## 4-6. Conteos antes y despues de cada filtro

| Paso | Antes | Despues | Excluidas en el paso |
|---|---|---|---|
| F0_universo | 560 | 560 | 0 |
| F1_variante_TWCVRP | 560 | 140 | 420 |
| F2_single_depot | 140 | 70 | 70 |
| F3_tamano_50_100_200 | 70 | 30 | 40 |
| F4_multi_vehicle | 30 | 30 | 0 |
| F5_capacidades_consistentes | 30 | 30 | 0 |
| F6_campos_criticos_no_nulos | 30 | 30 | 0 |

- **Instancias originales: 560.**
- **Instancias finales para el benchmark: 30.**
- **Excluidas: 530** (420 por F1, 70 por F2, 40 por F3).

## 7. ¿Cuantas instancias de 50, 100 y 200 clientes?

| Tamano | Instancias |
|---|---|
| 50 | 10 |
| 100 | 10 |
| 200 | 10 |

Balanceado (10 por tamano), universo completo del subconjunto -> **sin sesgo de seleccion**.

## 8. ¿Que instancias fueron excluidas y por que?

Registradas en `excluded_instances.csv` (530 filas, con `motivo_exclusion`):

| Motivo (primer filtro que excluye) | Cantidad |
|---|---|
| F1: no es TWCVRP (`cvrp_*`) | 420 |
| F2: no es single-depot (`multi_depot`/`depots_equal_city`) | 70 |
| F3: tamano fuera de {50,100,200} (10/20/500/1000) | 40 |
| F4/F5/F6 | 0 |

Ninguna exclusion fue manual; todas obedecen a una regla registrada.

## 9. ¿Todas las seleccionadas tienen ventanas horarias?

**Parcial / con matiz honesto.** Las 30 son la **variante TWCVRP** del dataset
(`is_twcvrp_variant = True`), pero el parquet crudo **no contiene los valores** de ventana
(`has_time_window_values = False` en las 30). Los valores deben **materializarse** con el
generador de la suite (`time_windows_generator`, semilla fija) antes de evaluar. **No se
fabricaron** ventanas en esta fase.

## 10. ¿Todas tienen demanda y capacidad?

**Si.** `tienen_demanda = True` (longitud de `demands` == nº de puntos) y
`tienen_capacidad = True` (`len(vehicle_capacities) >= 1`) en las 30.

## 11. ¿Todas son single-depot?

**Si.** `son_single_depot = True` (todas con `depot_config == single_depot`). Convencion:
`locations[0]` es el deposito unico (demanda 0).

## 12. ¿Todas son multi-vehicle?

**Si.** `son_multi_vehicle = True` (`num_vehicles > 1` en las 30): 10-16 vehiculos en tamano 50,
24-34 en 100 y 44-56 en 200. Ademas `len(vehicle_capacities) == num_vehicles` (capacidades por
vehiculo consistentes).

## 13. ¿Que variables de incertidumbre estan disponibles?

En el **parquet crudo: ninguna** materializada (sin columnas de congestion, retraso o accidente;
`appear_times` trivial = 0). La incertidumbre se **genera en runtime** con la suite de evaluacion
(`travel_time_generator`: trafico por hora, retraso log-normal, accidentes Poisson) bajo el
esquema de **5 realizaciones** definido en el protocolo. Por tanto, la incertidumbre es
**disponible via generador**, no via columnas del dataset.

## 14. ¿Que vacios o problemas se detectaron?

1. **Valores de ventana ausentes** en el crudo (solo etiqueta `twvrp_`). Pendiente de
   materializar; es el insumo critico para la Fase 5.
2. **Variables estocasticas ausentes** como columnas; provienen del generador de la suite.
3. **`num_depots` por `demand==0`** es ambiguo (clientes con demanda 0); para single-depot se
   asume `locations[0]`.
4. **Dos fuentes HF** (parquet `MBZUAI/svrp-bench` vs `.npz` `Yahias21/vrp_benchmark`): debe
   fijarse una sola antes de materializar ventanas/estocasticos.

## 15. ¿El subconjunto final es coherente con el protocolo experimental?

**Si.** Coincide exactamente con el subconjunto definido en la Fase 3:
`twvrp_{50,100,200}_single_depot`, 30 instancias, single-depot, multi-vehicle, capacidades
consistentes. Los criterios de inclusion/exclusion y los conteos por tamano son los previstos.

## 16. ¿Que debe revisarse antes de la Fase 5?

1. **Materializar las ventanas horarias** de las 30 instancias con el generador de la suite
   (semilla fija, documentada) o decidir usar el `.npz` de `Yahias21/vrp_benchmark` si las trae.
2. **Fijar una sola fuente HF** y reconciliar esquemas.
3. **Definir el mapeo de unidades** suite<->DSS (coordenadas ~0-1000, reloj del suite) antes de
   adaptar instancias.
4. **Resolver la asignacion de tiempos de servicio** (el parquet no los trae; el DSS los usa):
   decidir valor por defecto trazable o derivarlo.
5. Mantener el DSS intacto: la adaptacion de la Fase 5 vivira en `svrpbench_scripts/` como
   wrapper, sin tocar optimizador, simulador, metricas, dashboards, vistas ni `app.py`.

---

## Archivos generados (en `data_benchmark/svrpbench_processed/`)

| Archivo | Contenido |
|---|---|
| `svrpbench_subset.parquet` | 30 instancias seleccionadas (anidados originales + derivados + banderas). |
| `svrpbench_subset_sample.csv` | Las 30, con anidados en JSON y metadatos (inspeccion visual). |
| `selected_instances.csv` | Metadatos de las 30 seleccionadas (trazabilidad a la fila original). |
| `excluded_instances.csv` | Las 530 excluidas con su `motivo_exclusion`. |
| `benchmark_subset_config.json` | Configuracion del subconjunto (criterios, conteos, traza, validacion, rutas). |
| `svrpbench_subset_diagnostico_fase4.md` | Este diagnostico. |

## Trazabilidad

Cada instancia procesada conserva `instance_uid = subset_name + "__" + instance_id` y
`row_index_original`, que la enlazan inequivocamente con su fila en el parquet crudo. El crudo
**no fue modificado** en ningun momento.

## Estado del DSS

Intacto (15 vistas). Esta fase solo produjo artefactos en `svrpbench_processed/`. No se adapto
el DSS, no se ejecutaron modelos, no se corrio el benchmark.
