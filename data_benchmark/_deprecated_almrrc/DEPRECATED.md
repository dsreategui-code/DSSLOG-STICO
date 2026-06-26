# Benchmark ALM RRC — DEPRECADO

Este directorio contiene el **respaldo completo** del benchmark Amazon Last Mile
Routing Research Challenge (ALM RRC), retirado como benchmark del DSS.

**Motivo del retiro:** la evaluacion de ALM RRC mide similitud con la secuencia de
paradas del conductor (SDstop, SDzone, ERP), no indicadores operativos del DSS. El
benchmark principal pasa a ser **SVRPBench** (ver `../svrpbench_scripts/`).

## Contenido respaldado

```
benchmark/          Paquete Python del benchmark ALM (paths, loader, adapter,
                    optimizer_adapter, metrics, runner, prepare_cache).
benchmark_view.py   Vista Streamlit del modo (ya no enrutada en app.py).
test_benchmark.py   Tests del benchmark ALM (fuera de la suite activa).
transformation.py   Script de transformacion JSON -> CSV del dataset ALM.
cache/              Muestra compacta de rutas High (datos, NO versionado).
processed_csv/      CSV transformados, incluye el de tiempos ~9.5 GB (NO versionado).
processed_excel/    Equivalentes XLSX (NO versionado).
raw_json/           JSON crudos del ALM RRC 2021 (NO versionado).
```

## Estado

- **No esta activo**: no se importa desde el DSS ni aparece en la app.
- **No eliminar sin confirmacion**: se conserva para trazabilidad y reproducibilidad.
- El codigo aqui ya no esta en el path de imports; si se quisiera reactivar habria que
  reubicarlo y volver a enrutarlo en `app.py`.
