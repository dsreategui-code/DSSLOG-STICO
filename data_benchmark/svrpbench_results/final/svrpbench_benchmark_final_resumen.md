# Resumen ejecutivo - Benchmark final SVRPBench (Fase 8)

- Instancias ejecutadas: **30** (tamanos [50, 100, 200]).
- Corridas totales (modelo x instancia x realizacion): **450**.
- Modelos comparados: **DSS, nn2opt, or-tools**.
- Tamanos evaluados: **[50, 100, 200]**.
- Mejor modelo por costo total (menor): **or-tools**.
- Mejor modelo por factibilidad: **DSS**.
- Mejor modelo por OTD benchmark: **DSS**.
- Mejor modelo por runtime (menor): **nn2opt**.
- Posicion del DSS en el ranking global: **3 de 3**.

## Agregado por modelo

| model_name | costo_prom | robustness | runtime_seconds | feasibility | constraint_violation_rate | otd_benchmark | vehicle_utilization | demand_fulfillment | n_exitosas | n_fallidas | n_infactibles |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DSS | 2250.6981 | 71.4884 | 10.017 | 1.0 | 0.0 | 1.0 | 0.0515 | 1.0 | 150 | 0 | 0 |
| nn2opt | 1228.356 | 45.608 | 0.0565 | 1.0 | 33.9704 | 0.6575 | 1.0 | 1.0 | 150 | 0 | 0 |
| or-tools | 1070.7526 | 33.7696 | 1.1002 | 1.0 | 43.7723 | 0.558 | 1.0 | 1.0 | 150 | 0 | 0 |

## Ranking

| rank | model_name | costo_prom | feasibility | constraint_violation_rate | otd_benchmark | runtime_seconds |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | or-tools | 1070.7526 | 1.0 | 43.7723 | 0.558 | 1.1002 |
| 2 | nn2opt | 1228.356 | 1.0 | 33.9704 | 0.6575 | 0.0565 |
| 3 | DSS | 2250.6981 | 1.0 | 0.0 | 1.0 | 10.017 |