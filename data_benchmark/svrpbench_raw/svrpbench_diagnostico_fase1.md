# Diagnostico SVRPBench - Fase 1 (descarga e inspeccion)

Dataset: **MBZUAI/svrp-bench** (Hugging Face).  
Fase: descarga, organizacion e inspeccion. **No** se adapta al DSS ni se ejecutan modelos.

## 1. Descarga

- El dataset se descargo correctamente: **si**.
- Estructura del repo: un unico Parquet (`data/test-00000-of-00001.parquet`) + README.
- Split unico: **test** con **560 instancias**, agrupadas en **56 subsets** (`subset_name`).

## 2. Archivos generados (en `data_benchmark/svrpbench_raw/`)

- `svrpbench_test.parquet` - dataset completo en Parquet.
- `svrpbench_sample.csv` - muestra (1 instancia por subset) con anidados en JSON y columnas derivadas.
- `svrpbench_columns.txt` - lista de columnas, tipos y ejemplos.
- `svrpbench_diagnostico_fase1.md` - este diagnostico.

## 3. Columnas del dataset

| columna | tipo | rol |
|---|---|---|
| `subset_name` | object | Clave de filtrado: variante + tamano + config de deposito/vehiculo. |
| `file_name` | object | Nombre del archivo .npz de origen (redundante con subset_name). |
| `instance_id` | int64 | Indice de la instancia dentro del subset (0-9). |
| `locations` | object | Lista de coordenadas [x, y]. **locations[0] = deposito**, resto = clientes. |
| `demands` | object | Lista de demandas por punto. demands[0]=0 (deposito). |
| `num_vehicles` | int64 | Numero de vehiculos de la instancia. |
| `vehicle_capacities` | object | Lista de capacidades (1 por vehiculo). |
| `appear_times` | object | Tiempo de aparicion por punto (dinamismo). En este dataset: todo 0. |

## 4. Campos para filtrar (taxonomia en `subset_name`)

Formato observado: `{variante}_{tamano}_{config_deposito}[_config_vehiculo]`.

- **Variantes**: {'cvrp': 420, 'twcvrp': 140}  
  - `cvrp_*` = CVRP capacitado.  `twvrp_*` = **TWCVRP** (con ventanas horarias).
- **Tamanos** (clientes): {10: 80, 20: 80, 50: 80, 100: 80, 200: 80, 500: 80, 1000: 80}
- **Config de deposito**: {'single_depot': 350, 'multi_depot': 140, 'depots_equal_city': 70}
- **Vehiculo single/multi** (por `num_vehicles`): {'multi': 280, 'single': 280}

### Reglas de filtrado propuestas (para Fase 2)

| Objetivo | Regla |
|---|---|
| TWCVRP | `subset_name.startswith('twvrp_')` |
| Single-depot | `'single_depot' in subset_name` |
| Multi-depot | `'multi_depot' in subset_name` o `'depots_equal_city' in subset_name` |
| Single-vehicle | `num_vehicles == 1` |
| Multi-vehicle | `num_vehicles > 1` |
| Tamano 50 / 100 / 200 | size derivado de `subset_name` == 50 / 100 / 200 |

## 5. Presencia de elementos clave

| Elemento | Presente | Como |
|---|---|---|
| Coordenadas de clientes | Si | `locations[1:]` |
| Deposito(s) | Si (implicito) | `locations[0]` (demanda 0); multi-depot por config |
| Demanda | Si | `demands` (entero por punto) |
| Capacidad vehicular | Si | `vehicle_capacities` |
| Numero de vehiculos | Si | `num_vehicles` |
| Ventanas horarias (columna explicita) | **No** | no hay columna TW; ni siquiera en `twvrp_*` |
| Variables estocasticas (congestion/retraso/accidente) | **No** | no hay columnas; ver seccion 7 |
| Dinamismo (`appear_times`) | Presente pero **trivial** | todo 0 en 560 filas (max global=0) |

## 6. Tamano de instancia vs numero de puntos

`n_puntos` deberia ser `tamano + 1` (clientes + deposito). En tamanos grandes hay
puntos extra (posibles depositos adicionales en configs multi-depot):

| tamano | n_puntos min | n_puntos max |
|---|---|---|
| 10 | 11 | 11 |
| 20 | 21 | 21 |
| 50 | 51 | 51 |
| 100 | 101 | 102 |
| 200 | 201 | 204 |
| 500 | 501 | 510 |
| 1000 | 1001 | 1020 |

## 7. Problemas y vacios detectados (CRITICO)

1. **No hay columnas de ventanas horarias** en el Parquet, ni siquiera para los subsets `twvrp_*` (TWCVRP). Las ventanas que describe el paper se generan con el **codigo del pipeline de SVRPBench** (repositorio de generacion), no estan materializadas en este dataset de Hugging Face.
2. **No hay columnas estocasticas** (congestion, retrasos log-normales, accidentes, trafico por hora). Son justamente el motivo para elegir SVRPBench, pero **viven en el simulador/generador**, no en estas 8 columnas. Hay que obtenerlas aparte.
3. **`appear_times` es trivial** (todo 0 en las 560 instancias): el dinamismo de aparicion no esta poblado en esta version del dataset.
4. **Representacion multi-deposito ambigua**: contar `demands == 0` no identifica depositos de forma fiable (hay clientes con demanda 0). Los depositos extra parecen reflejarse como puntos adicionales mas alla de `tamano+1`, pero el patron no es uniforme entre tamanos. Requiere verificacion en Fase 2.
5. **`subset_name` es la unica fuente de la taxonomia** (variante/tamano/config). No hay columnas atomicas para variante, tamano, n_depositos o config de vehiculo; se derivan por parsing del string.
6. **Capacidades inconsistentes en `multi_vehicule_capacities`**: en 140 de 140 de esos subsets, `len(vehicle_capacities)` = 1 mientras `num_vehicles` es mucho mayor (hasta ~175). Globalmente solo 420/560 filas cumplen `len(vehicle_capacities) == num_vehicles`. Hay que decidir en Fase 2 como asignar capacidad por vehiculo (replicar el valor unico o tratarlo como flota homogenea).

## 8. Que revisar antes de la Fase 2

1. **Origen de las ventanas horarias y de los eventos estocasticos**: revisar el repositorio/codigo oficial de SVRPBench (generador) para saber si se materializan ventanas, retrasos, congestion y accidentes, y con que distribuciones. Decidir si el adaptador del DSS (a) consume esos artefactos generados o (b) reconstruye las distribuciones segun el paper.
2. **Confirmar la convencion del deposito**: validar que `locations[0]` es siempre el deposito y como se listan multiples depositos en `multi_depot`/`depots_equal_city`.
3. **Definir el subconjunto experimental**: el contexto del DSS es ultima milla con ventanas y multi-vehiculo; el candidato natural es **`twvrp_*` single-depot** en tamanos **50/100/200**. Confirmar disponibilidad (hay 10 instancias por subset).
4. **Unidades y escala**: coordenadas enteras (~grilla 0-1000), capacidades en miles; definir el mapeo de unidades a tiempos/distancias del DSS.
5. **Compatibilidad con el DSS**: el DSS asume deposito unico (Callao) y ventanas HH:MM en una jornada; mapear el modelo SVRPBench (coordenadas abstractas, sin reloj explicito) a ese marco sin romper el flujo actual.

## 9. Conclusion de Fase 1

El dataset esta **descargado y organizado** en `data_benchmark/svrpbench_raw/`, con muestra CSV, lista de columnas y este diagnostico. La taxonomia de filtrado (variante/tamano/deposito/vehiculo) esta clara y vive en `subset_name` + `num_vehicles`. **Hallazgo principal**: las dimensiones estocasticas y de ventanas horarias **no estan en las columnas** del dataset HF; provienen del generador de SVRPBench. Resolver ese origen es el insumo critico para disenar la Fase 2.