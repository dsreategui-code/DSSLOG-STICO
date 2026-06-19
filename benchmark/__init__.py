"""Modo benchmark con literatura - Amazon Last Mile Routing Research Challenge (ALM RRC).

Paquete AISLADO y ADITIVO: no modifica el flujo del DSS (Validacion / Demostracion).
Permite leer el dataset ALM RRC transformado, construir casos por ruta, ejecutar el
mismo motor de optimizacion del DSS (OR-Tools, misma configuracion) sobre cada ruta y
comparar contra la secuencia real del conductor con metricas alineadas a la literatura.

Modulos:
    paths             - localizacion automatica de archivos y cache.
    prepare_cache     - extraccion unica de una muestra de rutas desde los archivos
                        grandes (incluido el de 9.5 GB) hacia un cache compacto.
    alm_loader        - carga del indice de muestra y de cada ruta desde el cache.
    adapter           - convierte una ruta ALM al formato interno del DSS.
    optimizer_adapter - optimiza la secuencia con el motor del DSS sobre la matriz real.
    metrics           - metricas comparables con literatura.
    runner            - ejecuta el benchmark sobre la muestra y consolida resultados.
"""
