# Resumen ejecutivo - Benchmark FINAL FIEL TWCVRP (Fase 8b)

- Instancias: **30** | corridas: **600** | modelos: **DSS, nn2opt, or-tools, or-tools-tw**.
- Reconstruccion fiel: capacidad real `ceil(total/num_veh)` + ventanas por cliente (generador oficial, 60/40 res/com) + evaluador estocastico del paper.
- Cobertura total garantizada (demand_fulfillment = 1.0); flota holgada e igual.
- Reparaciones dedicadas del DSS (clientes no encajables en ventana estricta) totales: **44** (prom/instancia 1.5).

## Agregado por modelo

| model_name | costo_prom | robustness | runtime_seconds | feasibility | constraint_violation_rate | otd_benchmark | vehicle_utilization | demand_fulfillment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DSS | 28488.8354 | 0.3149 | 12.0175 | 0.3667 | 1.1307 | 0.9889 | 0.8473 | 1.0 |
| nn2opt | 43064.0564 | 0.7906 | 0.0577 | 0.4 | 0.953 | 0.9906 | 0.5513 | 1.0 |
| or-tools | 43066.2641 | 0.7915 | 0.1851 | 0.4 | 0.953 | 0.9906 | 0.5513 | 1.0 |
| or-tools-tw | 28145.4272 | 0.7292 | 12.003 | 0.3667 | 1.1863 | 0.9884 | 0.8587 | 1.0 |

## Por modelo y tamano

| model_name | instance_size | costo_prom | otd_benchmark | constraint_violation_rate | robustness | runtime_seconds |
| --- | --- | --- | --- | --- | --- | --- |
| DSS | 50 | 10010.1907 | 0.9939 | 0.6128 | 0.2627 | 8.0069 |
| DSS | 100 | 22960.3838 | 0.9929 | 0.7093 | 0.2898 | 12.0126 |
| DSS | 200 | 52495.9316 | 0.98 | 2.07 | 0.3923 | 16.0331 |
| nn2opt | 50 | 16726.7918 | 0.9959 | 0.4128 | 1.5287 | 0.0094 |
| nn2opt | 100 | 35861.2976 | 0.9939 | 0.6062 | 0.3286 | 0.0334 |
| nn2opt | 200 | 76604.0799 | 0.982 | 1.84 | 0.5146 | 0.1304 |
| or-tools | 50 | 16726.7918 | 0.9959 | 0.4128 | 1.5287 | 0.0294 |
| or-tools | 100 | 35861.2976 | 0.9939 | 0.6062 | 0.3286 | 0.1022 |
| or-tools | 200 | 76610.7029 | 0.982 | 1.84 | 0.5172 | 0.4236 |
| or-tools-tw | 50 | 9992.3001 | 0.9939 | 0.6128 | 1.5145 | 8.0014 |
| or-tools-tw | 100 | 22799.2871 | 0.9929 | 0.7062 | 0.2748 | 12.0028 |
| or-tools-tw | 200 | 51644.6944 | 0.9785 | 2.24 | 0.3983 | 16.0047 |

## Ranking (menor costo, mayor factibilidad, menor CVR, mayor OTD, menor runtime)

| rank | model_name | costo_prom | feasibility | constraint_violation_rate | otd_benchmark | runtime_seconds |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | or-tools-tw | 28145.4272 | 0.3667 | 1.1863 | 0.9884 | 12.003 |
| 2 | DSS | 28488.8354 | 0.3667 | 1.1307 | 0.9889 | 12.0175 |
| 3 | nn2opt | 43064.0564 | 0.4 | 0.953 | 0.9906 | 0.0577 |
| 4 | or-tools | 43066.2641 | 0.4 | 0.953 | 0.9906 | 0.1851 |