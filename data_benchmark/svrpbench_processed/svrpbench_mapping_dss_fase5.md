# Mapeo SVRPBench -> formato interno del DSS (Fase 5)

Documento de mapeo de campos entre una instancia del subconjunto SVRPBench y las entradas
que el optimizador actual del DSS consume. El adaptador
(`svrpbench_scripts/svrpbench_to_dss_adapter.py`) implementa exactamente este mapeo **sin
modificar el DSS**.

## Formato que espera el DSS (verificado en codigo)

- `pedidos` (DataFrame) - el optimizador lee: `pedido_id`, `latitud`, `longitud`, `peso_kg`,
  `tiempo_servicio_min`, `ventana_inicio` (HH:MM), `ventana_fin` (HH:MM), `zona`.
  (El validador del DSS pide ademas `cliente`, `distrito`, `modelo`, `tipo_servicio`.)
- `vehiculos` (DataFrame) - el optimizador lee: `vehiculo_id`, `capacidad_unidades`,
  `capacidad_kg`, `zona_preferente`.
- **Deposito**: global `config.settings.ALMACEN` (Callao, lat -12.0500 / lon -77.1200). El
  optimizador NO recibe el deposito por instancia; usa ALMACEN y construye matrices euclidianas.

## Decision arquitectonica: traslacion + escala de coordenadas

Como el DSS usa deposito fijo, el adaptador **traslada y escala** las coordenadas SVRPBench para
que el deposito de la instancia (`locations[0]`) caiga exactamente en ALMACEN, preservando la
geometria relativa. Asi el motor del DSS queda intacto y las distancias entre puntos se conservan
(en km, segun la escala). Verificado: deposito grid (495, 488) -> lat/lon (-12.0500, -77.1200).

## Tabla de mapeo

| Campo origen (SVRPBench) | Campo destino (DSS) | Transformacion | Unidad | Supuesto | Oblig. |
|---|---|---|---|---|---|
| `locations[0]` (x,y) | deposito = `ALMACEN` | se usa como origen de la traslacion; mapea a Callao | grilla -> lat/lon | locations[0] es el deposito (demanda 0), single-depot | Si |
| `locations[i]` i>=1 | `pedidos.latitud/longitud` | `(P - depot) * KM_POR_UNIDAD` -> offset km -> lat/lon sobre ALMACEN | grilla -> grados | KM_POR_UNIDAD = 0.05 km/unidad | Si |
| `demands[i]` i>=1 | `pedidos.peso_kg` | directo | unidades de demanda -> "kg" | demanda generica = peso | Si |
| `vehicle_capacities[v]` | `vehiculos.capacidad_kg` | directo (1 por vehiculo) | unidades de capacidad -> "kg" | capacidad por vehiculo (consistente) | Si |
| `num_vehicles` | nº filas de `vehiculos` | genera V01..Vn | conteo | multi-vehicle | Si |
| (no existe) | `pedidos.ventana_inicio/fin` | constante "09:00"/"19:00" | HH:MM | **ventanas no materializadas -> ventana abierta = jornada** | Si (DSS) |
| (no existe) | `pedidos.tiempo_servicio_min` | constante 0.0 | min | sin tiempo de servicio en SVRPBench | Si (DSS) |
| `instance_uid` | `metadata.instance_uid` | directo | id | trazabilidad a la fila original | Si |
| `size_declarado` | `metadata.size_declarado` | directo | conteo | tamano 50/100/200 | Si |
| (single-depot) | `pedidos.zona` / `vehiculos.zona_preferente` | constante "ALM" | etiqueta | zona unica; sin variables de Lima | Si (DSS) |
| (derivado) | `pedidos.cliente/distrito/modelo` | placeholders ("cliente_i"/"ALM"/"benchmark") | texto | requeridos por validador, no por optimizador | Opcional |
| (derivado) | `vehiculos.placa/conductor` | placeholders ("BMK-xxx"/"benchmark") | texto | requeridos por validador | Opcional |
| (derivado) | `vehiculos.capacidad_unidades` | = nº clientes | conteo | alto para NO restringir (SVRPBench limita por kg) | Si (DSS) |
| (derivado euclidiano) | `matriz_tiempos_benchmark` (origen/destino/tiempo_min/distancia_km) | distancia euclidiana km, tiempo a 18 km/h | km / min | matriz opcional; el optimizador recomputa internamente | Opcional |

## Constantes / supuestos (registrados)

| Supuesto | Valor | Justificacion |
|---|---|---|
| `KM_POR_UNIDAD` | 0.05 km/unidad | grilla ~1000 -> ciudad ~50 km (plausible urbano) |
| Ventanas | 09:00-19:00 (abiertas) | el parquet NO trae valores de ventana (Fase 4) |
| Tiempo de servicio | 0 min | no existe en SVRPBench |
| `capacidad_unidades` | nº clientes | evita restriccion por unidades; SVRPBench restringe por kg |
| Zona | "ALM" unica | single-depot; sin zonas de Lima |
| Velocidad | 18 km/h | parametro neutro del DSS para convertir distancia<->tiempo |

## Variables explicitamente NO agregadas (instruccion 12)

Instalacion de colchones, trafico especifico de Lima, seguridad urbana y condiciones
particulares de cliente: **no** se incorporan, por no pertenecer a SVRPBench.

## Trazabilidad

Cada caso conserva en `metadata_benchmark.json`: `instance_uid`, `row_index_original`,
`depot_grid`, `depot_latlon` y todos los supuestos, enlazando el caso adaptado con su fila en
`svrpbench_subset.parquet` y, por esta, con el parquet crudo.
