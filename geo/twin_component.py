"""Gemelo digital fluido e INTERACTIVO: componente deck.gl animado en el navegador.

Cada vehiculo lleva su PROPIO reloj. Arranca con el boton "Iniciar" (no auto-inicia). Cuando
un vehiculo llega a una incidencia con propuesta de re-ruteo, ESE vehiculo se paraliza y su
tarjeta aparece en el CENTRO DE ALERTAS (debajo del mapa) con la causa descrita (tipo,
severidad, distrito, franja) mientras los demas siguen. El usuario aprueba o mantiene la ruta
en el mapa; el vehiculo reanuda. Debajo del mapa hay una barra de resultados EN VIVO. Toda la
interaccion es del lado del cliente. Velocidad por defecto 1 s = 1 min simulado. Gemelo SIMULADO.
"""
from __future__ import annotations

import json
import math

from config.cortex_settings import FACTOR_CIRCUITO
from core.demo_scenario import VELOCIDAD_KMH
from core.twin_sim import MARGEN_RIESGO_MIN, _franja, _hhmm, proponer_reruteo


def _fit_view(lons, lats, w: int = 720, h: int = 460) -> dict:
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


# Paleta de vehiculos (debe coincidir con VEHCOL en el JS).
VEHCOL = [[21, 112, 239], [127, 86, 217], [14, 150, 204], [181, 71, 8],
          [3, 152, 158], [122, 39, 113], [217, 45, 32], [2, 122, 72]]


def _cumdist(geom):
    """Distancia acumulada (km aprox, planar) a lo largo de una polilinea [[lon,lat],...]."""
    cum = [0.0]
    for i in range(1, len(geom)):
        (x0, y0), (x1, y1) = geom[i - 1], geom[i]
        mlat = math.radians((y0 + y1) / 2.0)
        dx = (x1 - x0) * 111.0 * math.cos(mlat)
        dy = (y1 - y0) * 111.0
        cum.append(round(cum[-1] + (dx * dx + dy * dy) ** 0.5, 4))
    return cum


def _closest_cum(geom, cum, lon, lat):
    """Distancia acumulada del vertice de la polilinea mas cercano a (lon,lat)."""
    best, bd = 0, 1e18
    for i, (x, y) in enumerate(geom):
        d = (x - lon) ** 2 + (y - lat) ** 2
        if d < bd:
            bd, best = d, i
    return cum[best]


def _downsample(geom, objetivo=220):
    """Reduce la densidad de la polilinea OSRM manteniendo su forma (cada k-esimo + extremos)."""
    n = len(geom)
    if n <= objetivo:
        return [[round(x, 5), round(y, 5)] for x, y in geom]
    step = max(1, n // objetivo)
    ds = [geom[i] for i in range(0, n, step)]
    if ds[-1] != geom[-1]:
        ds.append(geom[-1])
    return [[round(x, 5), round(y, 5)] for x, y in ds]


def _datos_gemelo(escenario: dict) -> dict:
    hub = {"lon": escenario["hub"]["lon"], "lat": escenario["hub"]["lat"],
           "nombre": escenario["hub"].get("nombre", "HUB")}
    t0 = float(escenario.get("t_inicio_min", 540))
    props = {p["vehiculo_id"]: p for p in proponer_reruteo(escenario)}
    lons, lats = [hub["lon"]], [hub["lat"]]
    vehiculos = []
    for veh, paradas in escenario["rutas"].items():
        stops, inc_idx, inc_info = [], -1, None
        for i, p in enumerate(paradas):
            lon, lat = p["coord"][1], p["coord"][0]
            lons.append(lon)
            lats.append(lat)
            stops.append({"lon": lon, "lat": lat, "pid": p["pedido_id"],
                          "serv": float(p.get("servicio_min", 8.0)),
                          "vfin": float(p.get("ventana_fin_min", 0.0)),
                          "incMin": float(p.get("incidencia_min", 0.0)),
                          "distrito": p.get("distrito", "-")})
            if p.get("incidencia") and inc_idx < 0:
                inc_idx = i
                t = float(p.get("t_incidencia") or p["eta_min"])
                inc_info = {"tipo": p.get("incidencia_tipo"),
                            "desc": p.get("incidencia_desc") or "Incidencia",
                            "sev": p.get("incidencia_sev") or "media",
                            "distrito": p.get("distrito", "-"), "franja": _franja(t),
                            "hora": _hhmm(t), "min": float(p.get("incidencia_min", 0.0)),
                            "pid": p["pedido_id"]}
        prop = props.get(veh)
        card = None
        orden_prop = None
        if prop is not None:
            orden_prop = prop["orden_propuesto"]
            card = {"nPend": prop["n_pendientes"],
                    "tardeAct": prop["tarde_actual"], "tardAct": prop["tard_actual_min"],
                    "tardeProp": prop["tarde_propuesto"], "tardProp": prop["tard_propuesto_min"],
                    "recuperadas": prop["recuperadas"], "reduccion": prop["reduccion_min"]}
        # 'alerta' = el vehiculo se PARALIZA para decidir. Se dispara cuando hay una decision
        # real: existe un re-ruteo propuesto, o la incidencia es de ALTA severidad. El resto de
        # incidencias no paralizan pero SI aparecen en el feed de alertas (con su causa).
        alta = bool(inc_info and inc_info.get("sev") == "alta")
        alerta = bool(inc_idx >= 0 and (card is not None or alta))
        # Geometria de calle (OSRM) para que el camion siga las vias en vez de linea recta.
        geomv = escenario.get("geometrias", {}).get(veh)
        geom = cum = dstop = None
        if geomv and len(geomv) > len(stops) + 2:      # enriquecida (no linea recta hub->paradas)
            geom = _downsample(geomv)
            cum = _cumdist(geom)
            dstop = [round(_closest_cum(geom, cum, s["lon"], s["lat"]), 4) for s in stops]
        vehiculos.append({"veh": veh, "stops": stops, "incIdx": inc_idx, "alerta": bool(alerta),
                          "ordenProp": orden_prop, "card": card, "inc": inc_info,
                          "geom": geom, "cum": cum, "dstop": dstop})
    return {"hub": hub, "t0": t0, "speed": float(VELOCIDAD_KMH),
            "circuito": float(FACTOR_CIRCUITO), "vehiculos": vehiculos,
            "colores": VEHCOL, "view": _fit_view(lons, lats)}


def html_gemelo(escenario: dict, altura: int = 460) -> str:
    data = json.dumps(_datos_gemelo(escenario))
    return _PLANTILLA.replace("__ALTURA__", str(int(altura))).replace("__DATA__", data)


_PLANTILLA = r"""
<link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
<div style="font-family:Inter,sans-serif;color:#0C111D;">
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 8px;">
    <button id="pp" style="padding:7px 16px;border:0;border-radius:8px;background:#1570EF;color:#fff;cursor:pointer;font-size:13px;font-weight:600;">&#9658; Iniciar</button>
    <button id="rs" style="padding:7px 14px;border:1px solid #D0D5DD;border-radius:8px;background:#fff;cursor:pointer;font-size:13px;">&#8635; Reiniciar</button>
    <span style="font-size:13px;color:#475467;">Velocidad</span>
    <input id="sp" type="range" min="1" max="12" step="1" value="2" style="width:110px;">
    <span id="spl" style="font-size:12px;color:#475467;">2 min/s</span>
    <span id="clk" style="font-size:14px;font-weight:700;margin-left:auto;">09:00</span>
  </div>
  <div id="leg" style="display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px;color:#475467;margin-bottom:6px;"></div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px;color:#475467;margin-bottom:6px;">
    <span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#98A2B3;"></i> pendiente</span>
    <span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#E8A33D;"></i> en riesgo</span>
    <span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#0D9488;"></i> en servicio</span>
    <span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#D92D20;"></i> incidencia</span>
    <span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#027A48;"></i> entregado</span>
  </div>
  <div id="map" style="position:relative;width:100%;height:__ALTURA__px;border-radius:12px;overflow:hidden;background:#EAECF0;"></div>
  <div id="live" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px;"></div>
  <div style="font-size:12.5px;font-weight:600;color:#344054;margin:12px 0 6px;">Centro de alertas</div>
  <div id="alerts" style="display:flex;flex-direction:column;gap:8px;max-height:360px;overflow:auto;"></div>
  <div id="err" style="color:#B42318;font-size:12px;margin-top:6px;"></div>
</div>
<script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/deck.gl@9.0.30/dist.min.js"></script>
<script>
(function(){
  var DATA=__DATA__;
  function boot(){
    if(!window.deck||!window.maplibregl){document.getElementById('err').textContent='No se pudieron cargar deck.gl/MapLibre (revisa la conexion).';return;}
    var COL={pendiente:[152,162,179],en_servicio:[13,148,136],entregado:[2,122,72],en_riesgo:[232,163,61],incidencia:[217,45,32]};
    var VEHCOL=DATA.colores;
    var TORAD=Math.PI/180;
    function vcol(i){return VEHCOL[i%VEHCOL.length];}
    function rgb(c){return 'rgb('+c[0]+','+c[1]+','+c[2]+')';}
    function hav(a,b){var p1=a.lat*TORAD,p2=b.lat*TORAD,dphi=(b.lat-a.lat)*TORAD,dl=(b.lon-a.lon)*TORAD;var h=Math.sin(dphi/2)*Math.sin(dphi/2)+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)*Math.sin(dl/2);return 2*6371*Math.asin(Math.sqrt(h));}

    // Leyenda de vehiculos por color
    var leg=DATA.vehiculos.map(function(v,i){return '<span><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:'+rgb(vcol(i))+';"></i> '+v.veh+'</span>';}).join('');
    document.getElementById('leg').innerHTML=leg;

    function nuevoEstado(){
      return DATA.vehiculos.map(function(v){
        return {veh:v.veh,stops:v.stops,incIdx:v.incIdx,ordenProp:v.ordenProp,card:v.card,
                alerta:v.alerta,inc:v.inc,geom:v.geom,cum:v.cum,dstop:v.dstop,geomTimes:null,
                order:v.stops.map(function(_,i){return i;}),
                decided:(v.alerta?false:true),applied:false,pause:0,tInc:null,
                arr:[],dep:[],arrOf:{},total:0};
      });
    }
    var V=nuevoEstado();
    function recalc(v){
      var t=DATA.t0,prev=DATA.hub,arr=[],dep=[],arrOf={};
      for(var k=0;k<v.order.length;k++){var s=v.stops[v.order[k]];
        t+=hav(prev,s)*DATA.circuito/DATA.speed*60;arr[k]=t;arrOf[v.order[k]]=t;
        t+=s.serv+s.incMin;dep[k]=t;prev=s;}
      t+=hav(prev,DATA.hub)*DATA.circuito/DATA.speed*60;
      v.arr=arr;v.dep=dep;v.arrOf=arrOf;v.total=t;
      if(v.tInc===null&&v.incIdx>=0){var pos=v.order.indexOf(v.incIdx);v.tInc=(pos>=0?arr[pos]:-1);}
      // Mapeo de la geometria de calle (OSRM): distancia acumulada por parada + tiempo por vertice.
      if(v.geom&&v.dstop&&!v.applied){
        var dseg=[0];for(var k=0;k<v.order.length;k++){dseg.push(v.dstop[v.order[k]]);}
        v.dseg=dseg;
        var gt=new Array(v.geom.length);
        for(var j=0;j<v.geom.length;j++){var d=v.cum[j];var kk=0;while(kk<v.order.length&&d>dseg[kk+1])kk++;
          if(kk>=v.order.length){gt[j]=v.total;continue;}
          var tStart=(kk===0?DATA.t0:dep[kk-1]);var d0=dseg[kk],d1=dseg[kk+1];
          var f=(d1>d0)?(d-d0)/(d1-d0):1;f=Math.max(0,Math.min(1,f));gt[j]=tStart+f*(arr[kk]-tStart);}
        v.geomTimes=gt;
      } else { v.geomTimes=null; }
    }
    function posAtDist(geom,cum,d){
      if(d<=0)return geom[0];var n=cum.length;if(d>=cum[n-1])return geom[n-1];
      for(var j=0;j<n-1;j++){if(d>=cum[j]&&d<=cum[j+1]){var f=(cum[j+1]>cum[j])?(d-cum[j])/(cum[j+1]-cum[j]):0;return [geom[j][0]+f*(geom[j+1][0]-geom[j][0]),geom[j][1]+f*(geom[j+1][1]-geom[j][1])];}}
      return geom[n-1];
    }
    V.forEach(recalc);
    function localT(v){return simT-v.pause;}
    function awaiting(v){return v.alerta&&!v.decided&&v.tInc>=0&&localT(v)>=v.tInc;}
    function posAt(v,lt){
      if(lt>=v.total)return [DATA.hub.lon,DATA.hub.lat];
      if(v.geom&&v.geomTimes&&v.dseg&&!v.applied){          // seguir la calle real (OSRM)
        for(var k=0;k<v.order.length;k++){var s=v.stops[v.order[k]];
          var travStart=(k===0?DATA.t0:v.dep[k-1]);
          if(lt<v.arr[k]){var f=(v.arr[k]>travStart)?(lt-travStart)/(v.arr[k]-travStart):1;f=Math.max(0,Math.min(1,f));var d=v.dseg[k]+f*(v.dseg[k+1]-v.dseg[k]);return posAtDist(v.geom,v.cum,d);}
          if(lt<v.dep[k])return [s.lon,s.lat];}
        return [DATA.hub.lon,DATA.hub.lat];
      }
      var prev=DATA.hub;                                    // respaldo: linea recta entre paradas
      for(var k=0;k<v.order.length;k++){var s=v.stops[v.order[k]];
        var travStart=(k===0?DATA.t0:v.dep[k-1]);
        if(lt<v.arr[k]){var f=(v.arr[k]>travStart)?(lt-travStart)/(v.arr[k]-travStart):1;f=Math.max(0,Math.min(1,f));return [prev.lon+f*(s.lon-prev.lon),prev.lat+f*(s.lat-prev.lat)];}
        if(lt<v.dep[k])return [s.lon,s.lat];
        prev=s;}
      return [prev.lon,prev.lat];
    }
    function incActivo(v,lt){
      if(v.incIdx<0||!v.inc)return false;
      if(awaiting(v))return true;                         // paralizado por decision
      var a=v.arrOf[v.incIdx],s=v.stops[v.incIdx];
      return lt>=a&&lt<a+s.serv+s.incMin;                 // atendiendo la parada con incidencia
    }
    function estadoStop(v,si,lt){
      var a=v.arrOf[si],s=v.stops[si];
      if(a===undefined)return 'pendiente';
      if(lt>=a+s.serv+s.incMin)return 'entregado';
      // Cualquier parada con incidencia se pinta roja mientras se atiende (o si esta paralizada).
      if((s.incMin>0&&lt>=a&&lt<a+s.serv+s.incMin)||(si===v.incIdx&&awaiting(v)))return 'incidencia';
      if(lt>=a)return 'en_servicio';
      var conocido=(v.decided||(v.tInc>=0&&lt>=v.tInc));
      if(conocido&&a>s.vfin)return 'en_riesgo';
      return 'pendiente';
    }
    function aplicarPropuesta(v){
      var p=v.order.indexOf(v.incIdx);var head=v.order.slice(0,p+1);var pend=v.order.slice(p+1);
      var byPid={};pend.forEach(function(si){byPid[v.stops[si].pid]=si;});
      var no=[];v.ordenProp.forEach(function(pid){if(byPid[pid]!==undefined){no.push(byPid[pid]);delete byPid[pid];}});
      pend.forEach(function(si){if(byPid[v.stops[si].pid]!==undefined)no.push(si);});
      v.order=head.concat(no);
    }
    function decide(i,act){var v=V[i];if(v.decided)return;if(act==='ap'&&v.ordenProp){aplicarPropuesta(v);v.applied=true;}v.pause=simT-v.tInc;v.decided=true;recalc(v);sigAlert='';}

    var deckgl=new deck.DeckGL({container:'map',map:maplibregl,
      mapStyle:'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
      initialViewState:{longitude:DATA.view.longitude,latitude:DATA.view.latitude,zoom:DATA.view.zoom,pitch:0,bearing:0},
      controller:true});
    var simT=DATA.t0,playing=false,mult=2,last=performance.now(),done=false,sigAlert='',started=false;
    var pp=document.getElementById('pp');
    pp.onclick=function(){
      if(done){V=nuevoEstado();V.forEach(recalc);simT=DATA.t0;done=false;}
      playing=!playing;started=started||playing;
      pp.innerHTML=playing?'&#10073;&#10073; Pausar':'&#9658; Reanudar';
      if(playing){last=performance.now();requestAnimationFrame(loop);}
    };
    document.getElementById('rs').onclick=function(){V=nuevoEstado();V.forEach(recalc);simT=DATA.t0;done=false;playing=false;started=false;sigAlert='';pp.innerHTML='&#9658; Iniciar';render();};
    var spl=document.getElementById('spl');
    document.getElementById('sp').oninput=function(){mult=parseFloat(this.value);spl.textContent=mult+' min/s';};
    function hhmm(m){m=Math.round(m);return ('0'+Math.floor(m/60)).slice(-2)+':'+('0'+(m%60)).slice(-2);}

    function tile(label,val,color){return '<div style="background:#F9FAFB;border:1px solid #EAECF0;border-radius:10px;padding:8px 10px;"><div style="font-size:11px;color:#667085;">'+label+'</div><div style="font-size:18px;font-weight:700;color:'+(color||'#0C111D')+';">'+val+'</div></div>';}

    function buildAlerts(){
      var box=document.getElementById('alerts');var html='';var sevcol={alta:'#B42318',media:'#B54708',baja:'#475467'};
      for(var i=0;i<V.length;i++){var v=V[i];var lt=localT(v);if(!v.inc||lt<v.tInc)continue;var c=v.inc;var sc=sevcol[c.sev]||'#B54708';
        var head='<div style="display:flex;align-items:center;gap:8px;"><span style="width:9px;height:9px;border-radius:50%;background:'+sc+';display:inline-block;"></span><b>'+v.veh+' &middot; '+c.desc+'</b><span style="margin-left:auto;font-size:11px;color:#fff;background:'+sc+';border-radius:20px;padding:2px 8px;">severidad '+c.sev+'</span></div>'
          +'<div style="color:#475467;margin:4px 0 8px;">'+c.distrito+' &middot; franja '+c.franja+' &middot; '+c.hora+' &middot; +'+Math.round(c.min)+' min &middot; pedido '+c.pid+'</div>';
        if(awaiting(v)&&v.card){var p=v.card;
          html+='<div style="background:#fff;border:1px solid #FDA29B;border-left:4px solid '+sc+';border-radius:10px;padding:12px 14px;box-shadow:0 2px 8px rgba(16,24,40,.10);font-size:13px;">'+head
            +'<div style="color:#344054;margin-bottom:8px;">&#128681; <b>'+v.veh+' PARALIZADO.</b> Impacto: '+p.nPend+' paradas pendientes, '+p.tardeAct+' en riesgo de incumplir. <b>Propuesta del motor:</b> re-secuenciar &rarr; '+(p.recuperadas>0?('recupera '+p.recuperadas+' entrega(s), '):'')+'-'+Math.round(p.reduccion)+' min.</div>'
            +'<div style="display:flex;gap:8px;"><button data-i="'+i+'" data-a="ap" style="flex:1;padding:7px;border:0;border-radius:8px;background:#027A48;color:#fff;cursor:pointer;font-size:12.5px;font-weight:600;">Aprobar re-ruteo</button><button data-i="'+i+'" data-a="de" style="flex:1;padding:7px;border:1px solid #D0D5DD;border-radius:8px;background:#fff;cursor:pointer;font-size:12.5px;">Mantener ruta</button></div></div>';
        }else if(awaiting(v)){
          html+='<div style="background:#fff;border:1px solid #FDA29B;border-left:4px solid '+sc+';border-radius:10px;padding:12px 14px;box-shadow:0 2px 8px rgba(16,24,40,.10);font-size:13px;">'+head
            +'<div style="color:#344054;margin-bottom:8px;">&#128681; <b>'+v.veh+' PARALIZADO.</b> Incidencia de alta severidad. El re-ruteo no recupera entregas (el plan absorbe la demora); confirma para continuar.</div>'
            +'<div style="display:flex;gap:8px;"><button data-i="'+i+'" data-a="de" style="flex:1;padding:7px;border:0;border-radius:8px;background:#1570EF;color:#fff;cursor:pointer;font-size:12.5px;font-weight:600;">Continuar (mantener ruta)</button></div></div>';
        }else{
          var estado=v.applied?'Re-ruteo aplicado':(v.decided?'Atendida':(incActivo(v,lt)?'En curso':'Demora absorbida por el plan'));
          html+='<div style="background:#F9FAFB;border:1px solid #EAECF0;border-left:4px solid '+sc+';border-radius:10px;padding:10px 12px;font-size:12.5px;">'+head+'<div style="color:#475467;">Estado: '+estado+'.</div></div>';
        }
      }
      if(!html){html='<div style="color:#667085;font-size:12.5px;padding:4px 2px;">'+(started?'Sin incidencias activas en este momento.':'Pulsa Iniciar para arrancar la jornada. Las alertas apareceran aqui.')+'</div>';}
      box.innerHTML=html;
      var bts=box.querySelectorAll('button');
      for(var j=0;j<bts.length;j++){bts[j].onclick=function(){decide(parseInt(this.getAttribute('data-i')),this.getAttribute('data-a'));};}
    }

    function render(){
      var layers=[];var pd=[];var done_n=0,aTiempo=0,tard=0,total=0,nAlert=0,incVistas=0;
      for(var i=0;i<V.length;i++){var v=V[i];var lt=localT(v);var col=vcol(i);
        var path,ts;
        if(v.geom&&v.geomTimes&&!v.applied){path=v.geom;ts=v.geomTimes;}
        else{path=[[DATA.hub.lon,DATA.hub.lat]];ts=[DATA.t0];for(var kp=0;kp<v.order.length;kp++){var sp=v.stops[v.order[kp]];path.push([sp.lon,sp.lat]);ts.push(v.arr[kp]);}}
        layers.push(new deck.TripsLayer({id:'tr'+i,data:[{path:path,ts:ts}],getPath:function(d){return d.path;},getTimestamps:function(d){return d.ts;},getColor:col,opacity:0.6,widthMinPixels:3,trailLength:80,currentTime:lt}));
        layers.push(new deck.ScatterplotLayer({id:'vh'+i,data:[v],getPosition:function(d){return posAt(d,localT(d));},getFillColor:col,getRadius:150,radiusMinPixels:6,radiusMaxPixels:13,stroked:true,getLineColor:[255,255,255],lineWidthMinPixels:2,updateTriggers:{getPosition:lt}}));
        if(incActivo(v,lt)){var ip=v.stops[v.incIdx];layers.push(new deck.ScatterplotLayer({id:'rg'+i,data:[ip],getPosition:function(d){return [d.lon,d.lat];},filled:false,stroked:true,getLineColor:[217,45,32],lineWidthMinPixels:2,getRadius:400+260*Math.abs(Math.sin(simT/2.2)),radiusMinPixels:12,radiusMaxPixels:46,updateTriggers:{getRadius:simT}}));nAlert++;}
        for(var k2=0;k2<v.stops.length;k2++){var st=estadoStop(v,k2,lt);var s2=v.stops[k2];var a2=v.arrOf[k2];
          pd.push({lon:s2.lon,lat:s2.lat,c:COL[st]});
          if(a2!==undefined&&lt>=a2+s2.serv+s2.incMin){done_n++;if(a2<=s2.vfin)aTiempo++;else tard+=(a2-s2.vfin);}
        }
        total+=v.stops.length;
        if(v.incIdx>=0&&v.tInc>=0&&lt>=v.tInc)incVistas++;
      }
      layers.push(new deck.ScatterplotLayer({id:'pd',data:pd,getPosition:function(d){return [d.lon,d.lat];},getFillColor:function(d){return d.c;},getRadius:85,radiusMinPixels:4,radiusMaxPixels:10,stroked:true,getLineColor:[255,255,255],lineWidthMinPixels:1,updateTriggers:{getFillColor:simT}}));
      layers.push(new deck.ScatterplotLayer({id:'hb',data:[DATA.hub],getPosition:function(d){return [d.lon,d.lat];},getFillColor:[12,17,29],getRadius:180,radiusMinPixels:7}));
      deckgl.setProps({layers:layers});
      var otd=done_n?Math.round(1000*aTiempo/done_n)/10:100;
      document.getElementById('live').innerHTML=
        tile('Entregados',done_n+'/'+total)
        +tile('OTD acumulado',otd+'%',otd>=90?'#027A48':(otd>=75?'#B54708':'#B42318'))
        +tile('Incidencias',incVistas,incVistas>0?'#B54708':'#0C111D')
        +tile('Alertas activas',nAlert,nAlert>0?'#B42318':'#0C111D');
      var sig='';for(var i2=0;i2<V.length;i2++){var vv=V[i2];var lt2=localT(vv);var occ=(vv.inc&&lt2>=vv.tInc);sig+=(occ?((awaiting(vv)?'A':(vv.decided?'D':(incActivo(vv,lt2)?'C':'O')))+(vv.applied?'1':'0')):'0');}
      if(sig!==sigAlert){sigAlert=sig;buildAlerts();}
      document.getElementById('clk').textContent=done?'Jornada completada':hhmm(simT);
    }
    function finished(){for(var i=0;i<V.length;i++){if(!V[i].decided)return false;if(localT(V[i])<V[i].total)return false;}return true;}
    function loop(now){var dt=Math.min(0.05,(now-last)/1000);last=now;simT+=dt*mult;
      for(var i=0;i<V.length;i++){var v=V[i];if(v.alerta&&!v.decided&&v.tInc>=0&&(simT-v.pause)>=v.tInc){v.pause=simT-v.tInc;}}
      if(finished()){done=true;playing=false;pp.innerHTML='&#8635; Reiniciar';}
      render();if(playing&&!done)requestAnimationFrame(loop);}
    render();buildAlerts();
  }
  var tries=0;(function wait(){if((window.deck&&window.maplibregl)||tries>40){boot();}else{tries++;setTimeout(wait,150);}})();
})();
</script>
"""
