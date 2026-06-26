# Benchmark SVRPBench (activo)

Benchmark **principal** del DSS. Reemplaza al benchmark ALM RRC (movido a
`../_deprecated_almrrc/`). SVRPBench se alinea con los indicadores operativos del DSS:
incertidumbre, congestion, retrasos, accidentes, ventanas horarias y operacion dinamica
— a diferencia de ALM RRC, cuya evaluacion mide similitud con la secuencia del conductor.

## Estructura de carpetas

```
data_benchmark/
  svrpbench_raw/        Instancias originales descargadas de SVRPBench (NO versionado)
  svrpbench/            Instancias normalizadas listas para adaptar    (NO versionado)
  svrpbench_processed/  Artefactos intermedios (matrices, escenarios)  (NO versionado)
  svrpbench_results/    Salidas consolidadas CSV/XLSX                   (NO versionado)
  svrpbench_scripts/    Codigo del benchmark                           (VERSIONADO)
```

Solo `svrpbench_scripts/` se versiona en git; las carpetas de datos guardan una
`.gitkeep` para preservar la estructura sin subir datos pesados.

## Pipeline previsto (a implementar)

| Modulo | Responsabilidad |
|---|---|
| `svrpbench_loader.py` | Cargar instancias desde `svrpbench_raw/` o `svrpbench/`. |
| `svrpbench_adapter.py` | Convertir cada instancia al formato interno del DSS (pedidos, vehiculos, ventanas, perfiles de congestion, eventos de incertidumbre). |
| `svrpbench_runner.py` | Ejecutar el optimizador/simulador **actual** del DSS por instancia (sin modificar su logica central; usar wrappers). |
| `svrpbench_metrics.py` | Indicadores **operativos**: OTD, retraso medio/p90, % fuera de ventana, impacto de congestion/accidentes, robustez ante incertidumbre. |
| `bench_common.py` | (ya disponible) Exportacion CSV/XLSX y agregacion compartidas. |

## Funciones reutilizables ya disponibles

`bench_common.py` conserva, adaptado y sin dependencias de ALM RRC:

- `exportar_resultados(df, prefijo, resumen)` -> escribe CSV + XLSX en `svrpbench_results/`.
- `resumen_promedios(filas, columnas)` -> agrega promedios de columnas (filas `status == 'ok'`).
- Rutas `RAW_DIR`, `INSTANCES_DIR`, `PROCESSED_DIR`, `RESULTS_DIR` (se crean solas).

## Principios

- **No romper el DSS**: el benchmark es un modo adicional, aislado y reversible.
- **No modificar el nucleo** del optimizador/simulador; usar adaptadores/wrappers.
- **Indicadores operativos**, no de similitud de secuencia.

## Referencia del benchmark anterior

El benchmark ALM RRC quedo respaldado en `../_deprecated_almrrc/` (codigo + datos).
No esta activo ni se importa desde el DSS, pero se conserva para trazabilidad.
