"""Gemelo digital fluido: componente deck.gl animado en el navegador (sin recargas).

Genera el HTML/JS de un mapa deck.gl (basemap Carto sin token) que anima el avance de los
vehiculos con requestAnimationFrame a partir de la telemetria calculada UNA sola vez en
Python. Reemplaza la animacion por ticks (que recargaba la pagina) por una animacion fluida
del lado del cliente. Los estados de pedido (pendiente/en riesgo/en servicio/incidencia/
entregado) se colorean segun el tiempo simulado; las incidencias muestran un anillo pulsante.
La reproduccion es de UNA jornada (no un bucle de video): al llegar al final se detiene y se
puede reiniciar. La vista se ajusta al conjunto de puntos. Gemelo operativo SIMULADO.

Uso desde Streamlit:
    import streamlit.components.v1 as components
    components.html(html_gemelo(escenario), height=altura+180, scrolling=False)
"""
from __future__ import annotations

import json
import math


def _fit_view(lons, lats, w: int = 720, h: int = 520) -> dict:
    """Centro + zoom que encuadran todos los puntos (evita que queden fuera del mapa)."""
    if not lons:
        return {"longitude": -77.05, "latitude": -12.05, "zoom": 10.0}
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)

    def _merc_y(lat):
        s = min(max(math.sin(math.radians(lat)), -0.9999), 0.9999)
        return math.log((1 + s) / (1 - s)) / 2

    world = 512.0
    lat_frac = max((_merc_y(max_lat) - _merc_y(min_lat)) / (2 * math.pi), 1e-6)
    lon_frac = max((max_lon - min_lon) / 360.0, 1e-6)
    zoom = min(math.log2(h / world / lat_frac), math.log2(w / world / lon_frac)) - 0.35
    return {"longitude": (min_lon + max_lon) / 2, "latitude": (min_lat + max_lat) / 2,
            "zoom": max(8.5, min(13.0, zoom))}


def _datos_gemelo(escenario: dict) -> dict:
    hub = escenario["hub"]
    t0 = float(escenario.get("t_inicio_min", 540))
    trips, pedidos = [], []
    lons, lats = [hub["lon"]], [hub["lat"]]
    t_max = t0 + 60.0
    for veh, paradas in escenario["rutas"].items():
        path = [[hub["lon"], hub["lat"]]]
        ts = [t0]
        for p in paradas:
            lon, lat = p["coord"][1], p["coord"][0]
            path.append([lon, lat])
            ts.append(float(p["eta_min"]))
            lons.append(lon)
            lats.append(lat)
            tinc = p.get("t_incidencia")
            pedidos.append({"lon": lon, "lat": lat, "eta": float(p["eta_min"]),
                            "serv": float(p.get("servicio_min", 0.0)),
                            "iri": float(p.get("iri", 0.0)), "id": p["pedido_id"],
                            "inc": bool(p.get("incidencia", False)),
                            "tinc": float(tinc) if tinc is not None else -1.0})
        path.append([hub["lon"], hub["lat"]])       # regreso al hub
        ts.append(ts[-1] + 5.0)
        trips.append({"veh": veh, "path": path, "timestamps": ts})
        t_max = max(t_max, ts[-1])
    return {"hub": {"lon": hub["lon"], "lat": hub["lat"], "nombre": hub.get("nombre", "HUB")},
            "trips": trips, "pedidos": pedidos, "t0": t0, "tmax": t_max,
            "view": _fit_view(lons, lats)}


def html_gemelo(escenario: dict, altura: int = 560) -> str:
    data = json.dumps(_datos_gemelo(escenario))
    return _PLANTILLA.replace("__ALTURA__", str(int(altura))).replace("__DATA__", data)


_PLANTILLA = r"""
<link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
<div style="font-family:Inter,sans-serif;">
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 6px;">
    <button id="pp" style="padding:6px 14px;border:1px solid #D0D5DD;border-radius:8px;background:#fff;cursor:pointer;font-size:13px;">&#10073;&#10073; Pausar</button>
    <span style="font-size:13px;color:#475467;">Velocidad</span>
    <input id="sp" type="range" min="0.5" max="6" step="0.5" value="2" style="width:110px;">
    <span id="kpi" style="font-size:12.5px;color:#475467;">entregados 0 &middot; incidencias 0</span>
    <span id="clk" style="font-size:13px;font-weight:600;color:#0C111D;margin-left:auto;">09:00</span>
  </div>
  <div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:#475467;margin-bottom:6px;">
    <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#98A2B3;"></span> pendiente</span>
    <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#E8A33D;"></span> en riesgo</span>
    <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#0D9488;"></span> en servicio</span>
    <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#D92D20;"></span> incidencia</span>
    <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#027A48;"></span> entregado</span>
    <span><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#1570EF;"></span> vehiculo</span>
  </div>
  <div id="map" style="position:relative;width:100%;height:__ALTURA__px;border-radius:12px;overflow:hidden;background:#EAECF0;"></div>
  <div id="err" style="color:#B42318;font-size:12px;margin-top:6px;"></div>
</div>
<script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/deck.gl@9.0.30/dist.min.js"></script>
<script>
(function(){
  var DATA=__DATA__;
  function boot(){
    if(!window.deck||!window.maplibregl){document.getElementById('err').textContent='No se pudieron cargar deck.gl/MapLibre (revisa la conexion).';return;}
    var COL={pendiente:[152,162,179],en_ruta:[21,112,239],en_servicio:[13,148,136],entregado:[2,122,72],en_riesgo:[232,163,61],incidencia:[217,45,32]};
    function estado(p,t){
      if(t>=p.eta+p.serv)return 'entregado';
      if(p.inc&&t>=p.tinc&&t<p.eta+p.serv)return 'incidencia';
      if(t>=p.eta)return 'en_servicio';
      if(p.iri>=0.61)return 'en_riesgo';
      return 'pendiente';
    }
    function headPos(trip,t){var ts=trip.timestamps,pa=trip.path;if(t<=ts[0])return pa[0];if(t>=ts[ts.length-1])return pa[pa.length-1];for(var i=0;i<ts.length-1;i++){if(t>=ts[i]&&t<=ts[i+1]){var f=(ts[i+1]>ts[i])?(t-ts[i])/(ts[i+1]-ts[i]):1;return [pa[i][0]+f*(pa[i+1][0]-pa[i][0]),pa[i][1]+f*(pa[i+1][1]-pa[i][1])];}}return pa[pa.length-1];}
    var deckgl=new deck.DeckGL({container:'map',map:maplibregl,
      mapStyle:'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
      initialViewState:{longitude:DATA.view.longitude,latitude:DATA.view.latitude,zoom:DATA.view.zoom,pitch:0,bearing:0},
      controller:true});
    var t=DATA.t0,playing=true,done=false,mult=2,last=performance.now();
    var pp=document.getElementById('pp');
    pp.onclick=function(){
      if(done){t=DATA.t0;done=false;playing=true;pp.innerHTML='&#10073;&#10073; Pausar';last=performance.now();requestAnimationFrame(loop);return;}
      playing=!playing;pp.innerHTML=playing?'&#10073;&#10073; Pausar':'&#9658; Reanudar';
      if(playing){last=performance.now();requestAnimationFrame(loop);}
    };
    document.getElementById('sp').oninput=function(){mult=parseFloat(this.value);};
    function hhmm(m){m=Math.round(m);return ('0'+Math.floor(m/60)).slice(-2)+':'+('0'+(m%60)).slice(-2);}
    function render(){
      var activos=DATA.pedidos.filter(function(p){return p.inc&&t>=p.tinc&&t<p.eta+p.serv+20;});
      var entregados=0,vistas=0;
      for(var i=0;i<DATA.pedidos.length;i++){if(t>=DATA.pedidos[i].eta+DATA.pedidos[i].serv)entregados++;if(DATA.pedidos[i].inc&&t>=DATA.pedidos[i].tinc)vistas++;}
      var pulso=400+260*Math.abs(Math.sin(t/2.2));
      var trips=new deck.TripsLayer({id:'tr',data:DATA.trips,getPath:function(d){return d.path;},getTimestamps:function(d){return d.timestamps;},getColor:[21,112,239],opacity:0.7,widthMinPixels:3,trailLength:80,currentTime:t});
      var rings=new deck.ScatterplotLayer({id:'rg',data:activos,getPosition:function(d){return [d.lon,d.lat];},filled:false,stroked:true,getLineColor:[217,45,32],lineWidthMinPixels:2,getRadius:pulso,radiusMinPixels:10,radiusMaxPixels:44,updateTriggers:{getRadius:t}});
      var peds=new deck.ScatterplotLayer({id:'pd',data:DATA.pedidos,getPosition:function(d){return [d.lon,d.lat];},getFillColor:function(d){return COL[estado(d,t)];},getRadius:90,radiusMinPixels:4,radiusMaxPixels:11,stroked:true,getLineColor:[255,255,255],lineWidthMinPixels:1,pickable:true,updateTriggers:{getFillColor:t}});
      var veh=new deck.ScatterplotLayer({id:'vh',data:DATA.trips,getPosition:function(d){return headPos(d,t);},getFillColor:[21,112,239],getRadius:150,radiusMinPixels:6,radiusMaxPixels:14,stroked:true,getLineColor:[255,255,255],lineWidthMinPixels:2,updateTriggers:{getPosition:t}});
      var hub=new deck.ScatterplotLayer({id:'hb',data:[DATA.hub],getPosition:function(d){return [d.lon,d.lat];},getFillColor:[12,17,29],getRadius:180,radiusMinPixels:7});
      deckgl.setProps({layers:[trips,rings,peds,veh,hub]});
      document.getElementById('clk').textContent=done?'Jornada completada':hhmm(t);
      document.getElementById('kpi').innerHTML='entregados '+entregados+'/'+DATA.pedidos.length+' &middot; incidencias '+vistas;
    }
    function loop(now){var dt=Math.min(0.05,(now-last)/1000);last=now;t+=dt*mult*20;if(t>=DATA.tmax){t=DATA.tmax;playing=false;done=true;pp.innerHTML='&#8635; Reiniciar';}render();if(playing)requestAnimationFrame(loop);}
    render();requestAnimationFrame(loop);
  }
  var tries=0;(function wait(){if((window.deck&&window.maplibregl)||tries>40){boot();}else{tries++;setTimeout(wait,150);}})();
})();
</script>
"""
