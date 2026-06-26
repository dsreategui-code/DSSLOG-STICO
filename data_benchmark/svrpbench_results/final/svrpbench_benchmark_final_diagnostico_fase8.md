> ⚠️ **SUPERADO POR LA FASE 8b.** Al contrastar con el paper se detectó que esta corrida
> usó un problema **degenerado**: la capacidad del subconjunto era no vinculante (`cap =
> demanda_total` por vehículo) y las ventanas de tiempo **no estaban en el dato** (se asumió
> ventana abierta). Es decir, NO era un TWCVRP real. La reconstrucción fiel (capacidad
> `ceil(total/num_veh)` + ventanas por cliente + evaluador del paper) está en
> `../final_twcvrp/svrpbench_benchmark_twcvrp_diagnostico_fase8b.md` y **invierte** la
> conclusión (los modelos quedan parejos; el DSS gana a tamaño 50 pero escala peor). Este
> documento se conserva como registro honesto del hallazgo del defecto.

# Diagnóstico técnico — Benchmark final SVRPBench (Fase 8)

> Documento de cierre de la **Fase 8: ejecución del benchmark final**. Reporta de forma
> honesta y reproducible la comparación entre el **DSS logístico** y los baselines
> aprobados (**OR-Tools**, **NN+2opt**) sobre el subconjunto SVRPBench definido en la
> Fase 4, con scoring estocástico semillado (Fase 8). No se ajustaron resultados, no se
> ocultaron corridas y no se modificó la lógica central del DSS para favorecerlo.

Fecha de ejecución: 2026-06-25 · Interpretador: `.venv` (Python 3.11, OR-Tools + suite
`vrp_bench`) · Corridas: 450 · Log: `data_benchmark/svrpbench_logs/benchmark_final_20260625_202403.log`

---

## 0. Resumen de una línea

El DSS queda **3.º por costo** (más caro y más lento), pero es el **único** modelo con
**factibilidad operativa real**: OTD = 1.0, 0 violaciones de ventana y 0 violaciones de
capacidad en las 150 corridas, mientras los baselines minimizan distancia con **una sola
mega-ruta** que, bajo tiempos de viaje estocásticos, incumple ventanas masivamente
(CVR 34–44 %, OTD 0.56–0.66). El subconjunto resultó **no exigente en capacidad**, por lo
que la dimensión que discrimina a los modelos es el **tiempo bajo incertidumbre**, no la
capacidad.

---

## Tabla maestra de resultados (agregado por modelo)

| Modelo   | Costo prom. | Costo std | Robustez | Runtime (s) | Factib. | CVR (%) | OTD  | TWv prom. | Util. veh. | Demanda | Éxitos | Fallos | Infact. |
|----------|------------:|----------:|---------:|------------:|--------:|--------:|-----:|----------:|-----------:|--------:|-------:|-------:|--------:|
| or-tools |    1070.75  |   325.04  |  33.77   |     1.10    |  1.0    |  43.77  | 0.558| 59.73     |   1.000    |  1.0    |  150   |   0    |   0     |
| nn2opt   |    1228.36  |   391.49  |  45.61   |     0.057   |  1.0    |  33.97  | 0.658| 52.02     |   1.000    |  1.0    |  150   |   0    |   0     |
| **DSS**  |  **2250.70**|  1270.87  |  71.49   |    10.02    |  1.0    | **0.00**|**1.0**| **0.00** |   0.052    |  1.0    |  150   |   0    |   0     |

> `costo` y `robustez` están en **minutos de tiempo operativo** bajo escenario estocástico
> (ver Q5). `total_distance` (determinista, km) promedio: DSS 673.8 · nn2opt 368.1 ·
> or-tools 321.3.

Ranking final (criterio del protocolo: menor costo › mayor factibilidad › menor CVR ›
mayor OTD › menor runtime): **1.º or-tools, 2.º nn2opt, 3.º DSS**.

---

## 20 preguntas técnicas

### Q1. ¿Qué se ejecutó exactamente?
3 modelos (DSS, or-tools, nn2opt) × 30 instancias del subconjunto (10 de tamaño 50, 10 de
100, 10 de 200; todas TWCVRP, depósito único, multi-vehículo) × 5 realizaciones
estocásticas = **450 corridas**. Cada modelo **optimiza una vez** por instancia y esa
solución se **evalúa bajo 5 escenarios** estocásticos compartidos.

### Q2. ¿Se respetó el protocolo experimental de la Fase 3?
Sí. Modelos comparados, tamaños (50/100/200), número de realizaciones (5) y métricas
(costo, distancia, tiempo, runtime, factibilidad, CVR, TWv, OTD, utilización, cumplimiento
de demanda, robustez) provienen del protocolo. La **única extensión** fue materializar la
robustez con scoring estocástico semillado (Q5), justificada porque el protocolo exige
robustez pero el subconjunto no traía realizaciones precomputadas.

### Q3. ¿Se respetó el subconjunto de la Fase 4?
Sí. Se usaron las 30 instancias de `selected_instances.csv` cargadas desde
`svrpbench_subset.parquet`. No se añadieron, quitaron ni regeneraron instancias.

### Q4. ¿Cómo se garantizó una comparación justa entre modelos heterogéneos?
Todos los modelos producen **rutas como listas de índices de cliente** y se puntúan con el
**mismo** módulo `svrpbench_metrics.calcular_metricas` sobre la **misma instancia canónica**
(grilla SVRPBench). Ningún modelo se mide con su propia métrica. El DSS recibe la instancia
vía el adaptador de la Fase 5 (traslación+escala que preserva la geometría relativa) y
devuelve rutas que se re-puntúan en la grilla canónica igual que los baselines.

### Q5. ¿Cómo funciona el scoring estocástico y por qué es justo?
A cada arco (i,j) de cada realización r se le aplica un multiplicador de tiempo de viaje
log-normal `m = lognormvariate(μ, σ)` con `σ = 0.30` y `μ = −σ²/2` (⇒ E[m] = 1), semillado
de forma determinista por `crc32("instance_uid|r|i|j")`. Como la semilla **no depende del
modelo**, todos los modelos enfrentan **exactamente los mismos** retrasos por arco en cada
realización. Es una simplificación reproducible del retraso estocástico de la suite.

### Q6. ¿Por qué "optimizar una vez y puntuar N escenarios" en vez de re-optimizar 5 veces?
Eficiencia sin pérdida de validez: las heurísticas/solvers evaluados son **deterministas**
dada la instancia, así que re-optimizar 5 veces daría la misma ruta. Puntuar la ruta fija
bajo 5 escenarios mide exactamente lo que pide la robustez (sensibilidad del costo de una
solución a la incertidumbre) y evita ~25 min de cómputo redundante (total real: 338 s).

### Q7. ¿Cómo se define `total_cost`, `total_distance` y `robustness`?
- `total_distance`: distancia geométrica de las rutas en km (**determinista**, no depende
  del escenario).
- `total_cost`: en modo estocástico = **tiempo operativo realizado** (viaje perturbado +
  servicio) en minutos; es la magnitud sensible a la incertidumbre.
- `robustness`: desviación estándar de `total_cost` entre las 5 realizaciones, por
  instancia, promediada sobre instancias. Menor = más estable.

### Q8. ¿Quién ganó por costo y por qué?
**or-tools** (1070.75) < **nn2opt** (1228.36) < **DSS** (2250.70). Los baselines minimizan
distancia y, como la capacidad es no-vinculante (Q12), construyen **una sola ruta** que
recorre todos los clientes (un TSP gigante), minimizando kilómetros. El DSS reparte la
demanda en muchas rutas cortas, sumando más kilómetros de ida/vuelta al depósito.

### Q9. ¿Quién ganó por factibilidad, CVR, OTD y ventanas?
El **DSS domina en calidad de servicio**: factibilidad 1.0, **CVR 0.00 %**, **OTD 1.0**,
**0 violaciones de ventana**. Los baselines: CVR 34–44 %, OTD 0.56–0.66, 52–60 violaciones
de ventana promedio por corrida. La factibilidad de demanda (1.0) es igual para todos.

### Q10. ¿Por qué los baselines violan tantas ventanas si son "óptimos"?
Porque optimizan **distancia**, no tiempo de jornada. Su mega-ruta única de 50–200 paradas
excede largamente la jornada (09:00–19:00); bajo tiempos de viaje estocásticos, los clientes
del final del recorrido se atienden después del cierre ⇒ violación de ventana. Es óptimo en
km pero **operativamente inviable** para una flota real.

### Q11. ¿Por qué el DSS logra OTD = 1.0?
El DSS modela la **flota real de colchones** (muchos vehículos de capacidad acotada) y
balancea carga / duración de turno, generando 10 rutas (tamaño 50) a 40 rutas (tamaño 200),
cada una corta. Rutas cortas ⇒ todas las entregas caben en la jornada incluso con retrasos
⇒ cero violaciones. Es el comportamiento que se espera de un DSS de última milla.

### Q12. ¿Por qué la utilización de vehículos del DSS es 0.05 y la de los baselines 1.0?
**Métrica degenerada en este subconjunto.** La capacidad por vehículo de las instancias
SVRPBench es igual a la **demanda total** de la instancia (p. ej. 2403 en tamaño 50, 10720
en tamaño 200): un solo vehículo basta. Los baselines usan **1 ruta** ⇒ utilización
nominal 1.0. El DSS usa muchos vehículos (su flota real) ⇒ utilización nominal baja. Esta
métrica **no compara eficiencia real de flota** aquí; es un artefacto de la capacidad
no-vinculante (ver Q19). Debe interpretarse con cautela en la Fase 9.

### Q13. ¿Hubo corridas fallidas (errores de ejecución)?
**No: 0 fallidas** (`final_failed_runs.csv` vacío). Los 3 modelos resolvieron las 30
instancias sin excepciones. El pipeline registra cada corrida con `status` ∈
{success, failed, infeasible, timeout}.

### Q14. ¿Hubo corridas infactibles?
**No: 0 infactibles** (`final_infeasible_runs.csv` vacío), tras la corrección del Q15.
Toda la demanda se sirve y ninguna ruta viola capacidad.

### Q15. ¿Qué pasó con las "100 infactibles" detectadas en la primera corrida? (corrección documentada)
En la corrida inicial, 100 corridas (or-tools y nn2opt, tamaños 50 y 100) salían marcadas
"infeasible". La investigación mostró que **no era infactibilidad real**: factibilidad = 1.0
y cumplimiento de demanda = 1.0 en todas. La causa: los solvers de la suite **no visitan
clientes con demanda 0** (no aportan a la capacidad), y la verificación estricta "todos los
clientes servidos" los contaba como faltantes. Los tamaños 50 y 100 tienen hasta 3 clientes
con demanda 0 por instancia (promedio 1.5); el tamaño 200 tiene **0**, lo que explicaba
exactamente por qué el flag solo aparecía en 50/100.

**Corrección (error técnico del pipeline, no metodológica):** la factibilidad de cobertura
ahora exige servir únicamente a los **clientes con demanda positiva**; un cliente con demanda
0 no requiere entrega y omitirlo no es una infactibilidad. La regla se aplica **idéntica a
todos los modelos** (el DSS sirve a todos de todos modos, así que no lo beneficia
selectivamente). Tras la corrección: 0 infactibles, sin alterar ningún costo, distancia ni
métrica de calidad. Cambio en `svrpbench_metrics.calcular_metricas`
(`clientes_pos`/`todos_pos_servidos`).

### Q16. ¿Cómo escala cada modelo con el tamaño de instancia?
La ventaja del DSS **crece con el tamaño** (ver `final_results_by_model_size.csv`):

| Tamaño | OTD or-tools | OTD nn2opt | OTD DSS | CVR or-tools | CVR DSS |
|-------:|-------------:|-----------:|--------:|-------------:|--------:|
| 50     | 0.734        | 0.884      | 1.0     | 26.0 %       | 0.0 %   |
| 100    | 0.550        | 0.685      | 1.0     | 44.6 %       | 0.0 %   |
| 200    | 0.390        | 0.404      | 1.0     | 60.7 %       | 0.0 %   |

Los baselines se **degradan** (OTD cae a ~0.40, CVR sube a ~60 %) al alargarse la mega-ruta;
el DSS se mantiene perfecto. En costo, los baselines ganan en los tres tamaños, pero la
brecha de calidad se ensancha.

### Q17. ¿Qué tan robustos (estables) son los modelos ante la incertidumbre?
Robustez (std de costo entre escenarios, menor = mejor): or-tools 33.77 < nn2opt 45.61 <
DSS 71.49. El DSS muestra mayor variabilidad **absoluta** de costo porque su costo base es
mayor (más rutas ⇒ más arcos perturbados). En términos **relativos** (std/media) las tres
son comparables (~3 %). La robustez no cambia el orden de calidad: el DSS sigue siendo el
único sin violaciones en cualquier escenario.

### Q18. ¿Cuánto cuesta computacionalmente cada modelo?
Runtime promedio: nn2opt 0.057 s « or-tools 1.10 s « DSS 10.02 s. El DSS corre OR-Tools
CVRPTW con límite de 10 s (lo agota por diseño, buscando la mejor solución balanceada). Es
el más lento pero sigue siendo apto para planificación operativa (no tiempo real).

### Q19. ¿Cuáles son las principales amenazas a la validez / limitaciones?
1. **Capacidad no-vinculante:** la capacidad SVRPBench ≈ demanda total ⇒ el subconjunto
   prueba *ruteo bajo incertidumbre temporal*, no *ruteo capacitado*. La comparación de
   costo es en parte "TSP de una ruta (baselines) vs. ruteo multi-vehículo realista (DSS)".
2. **Ventanas abiertas / jornada uniforme:** el subconjunto no traía ventanas por cliente;
   se asumió jornada 09:00–19:00 para todos (Fases 4/5). Ventanas más estrechas y
   heterogéneas penalizarían aún más a los baselines.
3. **Escala km y velocidad fijas** (KM_POR_UNIDAD = 0.05; 18 km/h) heredadas del adaptador;
   afectan magnitudes absolutas, no el orden relativo.
4. **Un solo modelo de ruido** (log-normal, σ = 0.30, una familia de semillas). No se
   barrieron niveles de σ ni distribuciones alternativas.
5. **Utilización de vehículos** no comparable (Q12).

### Q20. ¿Qué conclusión deja la Fase 8 y qué debe analizar la Fase 9?
**Conclusión:** existe un *trade-off* claro y honesto. Los baselines minimizan distancia/
costo pero entregan soluciones operativamente inviables bajo incertidumbre (mega-ruta que
incumple ventanas). El DSS sacrifica costo y tiempo de cómputo para entregar soluciones
**desplegables**: balanceadas, sin violaciones de capacidad ni de ventana y con OTD perfecto,
con ventaja creciente al aumentar el tamaño. La elección "mejor modelo" depende del objetivo:
**costo puro ⇒ baselines; cumplimiento de servicio ⇒ DSS**.

**Para la Fase 9 se recomienda:** (a) reportar el trade-off costo-vs-OTD explícitamente
(frontera de Pareto), no solo el ranking por costo; (b) graficar la degradación de OTD/CVR
por tamaño; (c) marcar la utilización de vehículos como métrica no concluyente aquí;
(d) discutir la limitación de capacidad no-vinculante; (e) opcionalmente, un experimento
complementario con ventanas estrechas o capacidad ajustada para estresar ambas dimensiones.

---

## Cambios técnicos aplicados antes de la corrida final (transparencia)

Se corrigieron **únicamente errores técnicos del pipeline**, sin tocar la lógica del DSS ni
los criterios de comparación:

1. **Factibilidad sobre demanda positiva** (Q15): resuelve el falso "infeasible" de clientes
   con demanda 0. Aplicada por igual a todos los modelos.
2. **Generación de entregables robusta a dependencias:** `_resumen_auto` ya no depende de
   `tabulate` (tabla markdown autocontenida) y la exportación `.xlsx` prueba
   `xlsxwriter`→`openpyxl`. Evita que falte un entregable por una dependencia ausente.
3. **Escritura de `final_results_by_instance.csv`** añadida a `main()` (antes se calculaba
   pero no se guardaba).
4. **Interpretador correcto:** la corrida final usa el `.venv` del proyecto (OR-Tools + suite
   disponibles). Ejecutar con un Python sin estas dependencias degradaría el DSS a su
   fallback voraz y haría fallar a los baselines; se verificó el entorno antes de la corrida.

Ninguno de estos cambios altera costos, distancias ni métricas de calidad ya calculadas.

---

## Archivos entregables (Fase 8)

`data_benchmark/svrpbench_results/final/`
- `final_results_detailed.csv` / `.xlsx` — 450 corridas (todas las métricas por corrida).
- `final_results_by_model.csv`, `final_results_by_size.csv`,
  `final_results_by_model_size.csv`, `final_results_by_instance.csv` — agregados.
- `final_model_ranking.csv` — ranking por el criterio del protocolo.
- `final_failed_runs.csv` (0), `final_infeasible_runs.csv` (0).
- `svrpbench_benchmark_final_resumen.md` — resumen ejecutivo autogenerado.
- `svrpbench_benchmark_final_diagnostico_fase8.md` — este documento.
- JSON por (modelo × instancia) con las 5 realizaciones.

Logs: `data_benchmark/svrpbench_logs/benchmark_final_20260625_202403.log`.
