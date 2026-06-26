# Diagnostico del adaptador SVRPBench -> DSS (Fase 5)

Integracion modular y segura entre el subconjunto SVRPBench (Fase 4) y el formato interno del
DSS. **No** se ejecuto el benchmark final, **no** se corrieron todos los modelos, **no** se
modifico la logica central del DSS. El DSS sigue intacto (15 vistas, app importa sin errores).

---

## 1. ¿Que formato espera actualmente el DSS?

El optimizador (`optimization/route_optimizer.py` / `route_optimizer_ortools.py`) recibe **dos
DataFrames** y usa un **deposito global** (`config.settings.ALMACEN`, Callao):

- `pedidos`: `pedido_id`, `latitud`, `longitud`, `peso_kg`, `tiempo_servicio_min`,
  `ventana_inicio` (HH:MM), `ventana_fin` (HH:MM), `zona` (+ `cliente`, `distrito`, `modelo`,
  `tipo_servicio` que pide el validador).
- `vehiculos`: `vehiculo_id`, `capacidad_unidades`, `capacidad_kg`, `zona_preferente`,
  (`placa`, `conductor`).
- No requiere matriz externa: el optimizador construye distancias euclidianas desde ALMACEN.

El adaptador entrega DataFrames directamente (instruccion 14), sin obligar a Excel.

## 2. ¿Que campos de SVRPBench se mapearon directamente?

- `demands[i]` -> `pedidos.peso_kg`.
- `vehicle_capacities[v]` -> `vehiculos.capacidad_kg`.
- `num_vehicles` -> nº de vehiculos.
- `instance_uid`, `size_declarado`, `instance_id`, `row_index_original` -> `metadata`.

## 3. ¿Que campos requirieron transformacion?

- **Coordenadas**: `locations` (grilla entera) -> lat/lon mediante **traslacion+escala** para
  que `locations[0]` (deposito) coincida con ALMACEN, preservando geometria relativa
  (`KM_POR_UNIDAD = 0.05`).
- **Matriz de tiempos** (opcional): euclidiana en km y min a 18 km/h.
- **capacidad_unidades**: derivada = nº clientes (alto, no restringe).

## 4. ¿Que campos requirieron supuestos?

| Campo DSS | Supuesto | Motivo |
|---|---|---|
| `ventana_inicio` / `ventana_fin` | 09:00-19:00 (abiertas) | el parquet NO trae valores de ventana |
| `tiempo_servicio_min` | 0 min | no existe en SVRPBench |
| `zona` / `zona_preferente` | "ALM" unica | single-depot; sin zonas de Lima |
| `capacidad_unidades` | = nº clientes | SVRPBench restringe por kg, no por unidades |
| escala km | `KM_POR_UNIDAD = 0.05` | unidad de grilla -> km plausible |

(Detalle completo en `svrpbench_mapping_dss_fase5.md`.)

## 5. ¿Que archivos o modulos nuevos se crearon?

- `svrpbench_scripts/svrpbench_to_dss_adapter.py` - adaptador (no reemplaza nada).
- `svrpbench_scripts/test_svrpbench_adapter.py` - pruebas (9 tests).
- `svrpbench_processed/svrpbench_mapping_dss_fase5.md` - documento de mapeo.
- `svrpbench_processed/svrpbench_adapter_diagnostico_fase5.md` - este diagnostico.
- `svrpbench_cases/<instance_uid>/` - por instancia: `pedidos_benchmark.csv`,
  `vehiculos_benchmark.csv`, `zonas_benchmark.csv`, `matriz_tiempos_benchmark.csv`,
  `parametros_benchmark.csv`, `metadata_benchmark.json`.

`app.py` y los modulos del DSS **no** se modificaron en esta fase (no fue necesaria una entrada
visual de benchmark para construir/probar el adaptador).

## 6. ¿Que instancias fueron probadas?

| Instancia | Clientes | Vehiculos | Demanda total | Capacidad total |
|---|---|---|---|---|
| `twvrp_50_single_depot__0` | 50 | 12 | 2403 | 28836 |
| `twvrp_100_single_depot__0` | 100 | 25 | 5100 | 127500 |
| `twvrp_200_single_depot__0` | 200 | 48 | 10720 | 514560 |

## 7. ¿El adaptador funciona para 50, 100 y 200 clientes?

**Si.** Las tres se adaptan sin errores, con las columnas que el DSS espera, deposito unico,
multi-vehiculo, demanda, capacidad, ventanas (abiertas), coordenadas e identificador. 9/9 pruebas
en verde.

## 8. ¿El optimizador actual pudo recibir una instancia SVRPBench?

**Si, confirmado con el motor real.**
- Greedy (corrida minima): 50/50 clientes asignados en 12 vehiculos, sin exceder capacidad.
- **OR-Tools (motor del DSS, `auto`, limite 5 s)**: 50/50 clientes ruteados en 10 vehiculos.
El optimizador acepta la instancia adaptada sin modificaciones a su logica.

## 9. ¿Que errores se detectaron?

Ninguno funcional. El manejo de errores del adaptador se verifico:
- `AdapterError` ante instancia inexistente (`no_existe__999`).
- Validaciones activas: demandas negativas, capacidades nulas/<=0, ventanas invalidas
  (inicio>=fin), clientes sin coordenadas, vehiculos sin capacidad, capacidad total <
  demanda total, y matriz sin deposito. Ninguna se disparo en las 3 instancias (datos validos).

## 10. ¿Que limitaciones existen antes del benchmark final?

1. **Ventanas abiertas (no materializadas)**: la corrida actual es efectivamente CVRP. Para un
   TWCVRP real hay que **materializar ventanas** (generador de la suite, semilla fija) y volver a
   adaptar con esas ventanas.
2. **Escala de unidades supuesta** (`KM_POR_UNIDAD = 0.05`): afecta la magnitud absoluta de
   costos/tiempos, no la geometria relativa. Debe fijarse y documentarse para comparabilidad.
3. **Sin capa estocastica todavia**: congestion/retrasos/accidentes y las 5 realizaciones se
   aplicaran en la fase de ejecucion (no en el adaptador).
4. **Mapeo demanda->kg / capacidad->kg**: unidimensional; coherente con SVRPBench, pero los KPIs
   del DSS que dependan de "unidades" deben interpretarse con cuidado.
5. **Comparabilidad de costo**: el `total_cost` del DSS (km/min a 18 km/h) vs el de la suite debe
   alinearse con la misma metrica/escala en la fase de evaluacion.

## 11. ¿Que debe revisarse en la Fase 6?

1. **Materializar ventanas e incertidumbre** para las 30 instancias (fuente unica y semilla
   documentadas) y reejecutar el adaptador con ventanas reales.
2. **Definir el harness de evaluacion comun** (mismas instancias/ventanas/realizaciones/metricas)
   para DSS y baselines, segun el protocolo de la Fase 3.
3. **Alinear unidades y metrica de costo** suite<->DSS antes de comparar.
4. **Decidir la entrada visual de benchmark** en `app.py` (opcional): solo si se quiere lanzar
   desde la UI; el flujo programatico (adaptador + optimizador) ya funciona sin tocar la UI.
5. Mantener el DSS intacto: toda la integracion vive en `svrpbench_scripts/` / `svrpbench_cases/`.

---

## Estado del DSS

**Intacto.** No se modifico `app.py`, ni el optimizador, simulador, metricas, dashboards o vistas.
No se uso ni sobrescribio la carpeta `data/` del DSS. La integracion es aditiva y reversible:
el adaptador importa el optimizador del DSS como libreria y le entrega DataFrames; el motor no
fue alterado.
