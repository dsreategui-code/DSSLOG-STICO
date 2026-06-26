# Benchmark con literatura - Amazon Last Mile Routing Research Challenge (ALM RRC)

Modo **adicional, aislado y reversible** del DSS. Compara el motor de ruteo del DSS
contra rutas reales **High Quality** del ALM RRC 2021, con metricas alineadas a la
literatura. No altera el flujo normal del DSS (Validacion / Demostracion).

## Datos (no versionados)

Los archivos del dataset transformado viven en `data_benchmark/` y estan excluidos
de git por su tamano (el de tiempos de viaje pesa ~9.5 GB). En `.gitignore`:

```
data_benchmark/raw_json/
data_benchmark/processed_csv/
data_benchmark/processed_excel/
data_benchmark/cache/
```

Solo se versiona `data_benchmark/transformation.py` (script de transformacion JSON -> CSV)
para reproducibilidad. **El benchmark se ejecuta en local**, no en el despliegue cloud:
en Streamlit Community Cloud la vista muestra "dataset no encontrado" de forma controlada,
porque el dataset pesado no se sube.

## Uso

```powershell
# 1) Preparar el cache UNA sola vez (solo rutas High por defecto).
#    Extrae una muestra del archivo de 9.5 GB hacia un cache compacto.
python -m benchmark.prepare_cache --n-rutas 30 --seed 42

# 2) Correr el benchmark principal. Consolidado en data/outputs/.
python -m benchmark.runner --motor auto --time-limit 10

# 3) O desde la app: Home -> "Abrir benchmark".
streamlit run app.py
```

Salidas: `data/outputs/benchmark_almrrc_<timestamp>.csv` y `.xlsx`
(hojas `Detalle_por_ruta` y `Resumen`).

## Indicadores (benchmark principal)

| Indicador | Significado |
|---|---|
| `sd_stop` | Sequence Deviation a nivel de parada (formula oficial Cook et al.). 0 = mismo orden que el conductor. |
| `sd_zone` | Sequence Deviation a nivel de zona (orden de zonas visitadas). |
| `erp_ratio_min` | Penalizacion promedio por desviacion (Edit distance with Real Penalty sobre la matriz de tiempos, normalizada por parada). |
| `score_aprox` | `sd_stop x erp_ratio`. Proxy del score ALM RRC (replica su estructura SD x ERP; **no** es el binario oficial de Amazon). |
| `tiempo_real_min` / `tiempo_propuesto_min` | Tiempo total de la ruta real del conductor vs la propuesta por el DSS, sobre la matriz real. |
| `brecha_pct` | `(propuesto - real) / real * 100`. Negativa = el DSS propone ruta mas rapida. |
| `tiempo_computo_seg` | Tiempo computacional por ruta. |
| `n_paradas` | Numero de paradas. |
| `route_score` | Calidad original del dataset; **solo filtro/segmentacion**, no es salida del DSS. |

## Alcance

El benchmark evalua **ruteo, secuenciacion y tiempos**. No fuerza variables locales
del caso de Lima (trafico, instalacion de colchones, seguridad urbana, condiciones de
cliente), que no pertenecen al ALM RRC.

## Arquitectura

```
benchmark/
  paths.py            Localizacion automatica de archivos + cache.
  prepare_cache.py    Extraccion unica de muestra High desde los archivos grandes.
  alm_loader.py       Carga del indice y de cada ruta desde el cache (filtro High).
  adapter.py          ALM RRC -> caso interno (depot, matriz real, secuencia, zonas).
  optimizer_adapter.py Motor del DSS (OR-Tools, misma config) sobre la matriz real.
  metrics.py          SDstop, SDzone, ERPratio, score_aprox, tiempos y brecha.
  runner.py           Ejecuta la muestra y consolida resultados (CSV/XLSX).
```
