# Diagnostico de la prueba piloto - Fase 7

Prueba piloto **controlada** del benchmark SVRPBench: DSS vs baselines sobre pocas instancias,
1 realizacion, usando la config y los runners de la Fase 6. **No** es el benchmark final. El DSS
sigue intacto (15 vistas, app importa).

---

## Tabla comparativa piloto

| Modelo | Tamano | Total Cost (km) | Runtime (s) | Feasibility | CVR (%) | TW Violations | OTD | Veh. Util. | Demand Fulfill. |
|---|---|---|---|---|---|---|---|---|---|
| DSS | 50 | 285.09 | 10.01 | 1.00 | 0.00 | 0 | 1.000 | 0.100 | 1.00 |
| OR-Tools | 50 | 227.11 | 1.05 | 1.00 | 29.17 | 14 | 0.702 | 1.000 | 1.00 |
| NN+2opt | 50 | 261.79 | 0.02 | 1.00 | 10.42 | 5 | 0.894 | 1.000 | 1.00 |
| DSS | 100 | 553.71 | 10.02 | 1.00 | 0.00 | 0 | 1.000 | 0.040 | 1.00 |
| OR-Tools | 100 | 302.44 | 1.06 | 1.00 | 45.92 | 45 | 0.536 | 1.000 | 1.00 |
| NN+2opt | 100 | 319.36 | 0.04 | 1.00 | 22.45 | 22 | 0.773 | 1.000 | 1.00 |
| DSS | 200 | 1075.84 | 10.03 | 1.00 | 0.00 | 0 | 1.000 | 0.025 | 1.00 |
| OR-Tools | 200 | 439.55 | 1.25 | 1.00 | 62.19 | 125 | 0.375 | 1.000 | 1.00 |
| NN+2opt | 200 | 517.34 | 0.14 | 1.00 | 60.20 | 121 | 0.395 | 1.000 | 1.00 |

---

## Respuestas

### 1. ¿Que instancias piloto se ejecutaron?
`twvrp_50_single_depot__0`, `twvrp_100_single_depot__0`, `twvrp_200_single_depot__0`
(primera instancia de cada tamano). Registradas en `pilot_selected_instances.csv` (3/3 cargables).

### 2. ¿Que tamanos se probaron?
50, 100 y 200 clientes.

### 3. ¿Que modelos se ejecutaron?
DSS, OR-Tools y NN+2opt (los dos baselines priorizados, estables y rapidos).

### 4. ¿Que modelos fallaron y por que?
**Ninguno.** 9/9 corridas con estado OK, `error_message` vacio.

### 5. ¿El DSS pudo ejecutar las instancias SVRPBench?
**Si**, en los tres tamanos, via el adaptador + optimizador del DSS (motor auto).

### 6. ¿El adaptador funciono correctamente?
**Si.** Convirtio cada instancia a `pedidos`/`vehiculos` sin tocar `data/`; el optimizador del DSS
las acepto.

### 7. ¿Las metricas se calcularon correctamente?
**Si**, con el modulo comun (mismas formulas para todos). Validacion de sanidad: 0 errores,
`total_cost >= 0`, `runtime > 0`, OTD/feasibility/util/demand en [0,1], CVR en [0,100].

### 8. ¿Los resultados se guardaron correctamente?
**Si**: `pilot_results.csv`, `pilot_results.xlsx`, 9 JSON por corrida y `resultados_pilot_*.csv`.

### 9. ¿Los logs se generaron correctamente?
**Si**: `svrpbench_logs/benchmark_pilot_*.log` con las 9 corridas (timestamp, modelo, instancia,
estado, costo, runtime).

### 10. ¿Las metricas tienen unidades coherentes?
**Si**: costo/distancia en km (escala 0.05 km/unidad), tiempo en min, runtime en s, OTD/feasibility/
utilizacion/demanda en [0,1], CVR en %.

### 11. ¿Problemas con ventanas, capacidad, demanda o depositos?
- **Capacidad/demanda/deposito: sin problemas** (feasibility=1.0 y demand_fulfillment=1.0 en todas;
  capacidad total cubre la demanda; deposito unico via `locations[0]`).
- **Ventanas (HALLAZGO IMPORTANTE, no es bug)**: como no estan materializadas, se usa **ventana
  abierta = jornada operativa 09:00-19:00**. Por eso una ruta que termina despues de las 19:00
  cuenta como fuera de ventana. Los baselines **consolidan** en pocos vehiculos (utilizacion 1.0)
  -> rutas largas que exceden la jornada -> CVR/TWv altos y OTD < 1. El DSS **balancea carga**
  (utilizacion 0.025-0.10, muchos vehiculos) -> rutas cortas dentro de la jornada -> OTD=1.0, TWv=0.

### 12. ¿Problemas de runtime?
El **DSS toco el limite de 10 s** en las tres (motor auto/OR-Tools con `time_limit=10`); los
baselines corrieron en <1.3 s (OR-Tools de la suite tiene `time_limit=1 s` interno). El runtime
**no es directamente comparable** por presupuestos de tiempo distintos.

### 13. ¿Diferencias de formato entre modelos?
**Ninguna.** Todos devuelven la misma estructura de salida y se puntuan con el mismo modulo. Las
rutas se normalizan a indices de cliente (deposito=0) de forma uniforme.

### 14. ¿Que errores deben corregirse antes del benchmark final?
No hay errores **tecnicos** de pipeline. Items **metodologicos** a resolver:
1. **Materializar ventanas horarias reales** (generador de la suite, semilla fija) para una
   comparacion TWCVRP fiel; con ventanas abiertas, OTD/CVR/TWv miden "dentro de la jornada", no la
   ventana del cliente.
2. **Mismatch de objetivo**: el DSS **balancea carga** (limita vehiculos, baja utilizacion, mayor
   distancia) mientras los baselines **minimizan costo** (alta utilizacion, menor distancia). El
   `total_cost` no es un "ganador" simple: refleja filosofias distintas. Decidir el encuadre del
   reporte (p. ej. reportar costo Y utilizacion Y OTD juntos; o evaluar el DSS tambien en un modo
   orientado a costo) **sin** alterar la logica del DSS.
3. **Presupuesto de tiempo**: igualar limites por modelo o reportar runtime como contextual.

### 15. ¿Que modelos mantener para la ejecucion final?
**DSS, OR-Tools y NN+2opt** (estables, rapidos, 0 fallos). **Tabu** es viable como cuarto.

### 16. ¿Que modelos descartar o dejar opcionales?
**Opcional**: ACO (runtime alto en grandes). **Descartados**: POMO/Attention Model (rl4co+torch),
LKH-3 (binario externo), ALNS (no existe).

### 17. ¿El pipeline esta listo para la Fase 8?
**Si, tecnicamente.** Carga, adaptacion, ejecucion, metricas uniformes, guardado y logs funcionan
de extremo a extremo sin errores. Antes de la corrida final conviene resolver los items
metodologicos (sobre todo **materializar ventanas**) y dejar listas las **5 realizaciones** para
robustness.

### 18. ¿El DSS normal sigue funcionando despues de la prueba?
**Si.** `app` importa con 15 vistas; no se modifico `data/`, ni el optimizador, simulador,
metricas, dashboards o vistas. La prueba corrio aislada en `svrpbench_runners/` / `svrpbench_results/`.

---

## Conclusion

El piloto **valida el flujo completo**: 9 corridas, 0 errores, metricas coherentes y comparables,
resultados y logs persistidos. La integracion DSS<->SVRPBench es estable. El hallazgo central no es
un fallo de pipeline sino **metodologico**: con ventanas abiertas y objetivos distintos (balance vs
costo), las metricas de cumplimiento y costo deben interpretarse con cuidado y, idealmente,
materializar ventanas reales antes del benchmark final (Fase 8). No se ajusto ningun resultado a
mano; el DSS quedo intacto.
