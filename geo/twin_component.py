"""Gemelo digital fluido e INTERACTIVO: componente deck.gl animado en el navegador.

Cada vehiculo lleva su PROPIO reloj. Cuando un vehiculo llega a una incidencia con una
propuesta de re-ruteo, ese vehiculo se PARALIZA en el punto y muestra su tarjeta de decision
(ruta actual vs re-secuenciada, con sustento) mientras los demas siguen su recorrido. El
usuario aprueba o mantiene ruta EN EL MAPA; el vehiculo reanuda con la ruta elegida. Toda la
interaccion es del lado del cliente (una recarga de Streamlit reiniciaria la animacion). Los
tiempos se recomputan en JS replicando la velocidad/haversine del backend. Gemelo SIMULADO.

Uso:
    import streamlit.components.v1 as components
    components.html(html_gemelo(escenario), height=..., scrolling=False)
"""
from __future__ import annotations

import json
import math

from core.demo_scenario import VELOCIDAD_KMH
from core.twin_sim import proponer_reruteo


def _fit_view(lons, lats, w: int = 720, h: int = 520) -> dict:
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
    hub = {"lon": escenario["hub"]["lon"], "lat": escenario["hub"]["lat"],
           "nombre": escenario["hub"].get("nombre", "HUB")}
    t0 = float(escenario.get("t_inicio_min", 540))
    props = {p["vehiculo_id"]: p for p in proponer_reruteo(escenario)}
    lons, lats = [hub["lon"]], [hub["lat"]]
    vehiculos = []
    for veh, paradas in escenario["rutas"].items():
        stops, inc_idx = [], -1
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
        prop = props.get(veh)
        card = None
        orden_prop = None
        if prop is not None:
            orden_prop = prop["orden_propuesto"]
            card = {"hora": prop["incidencia_hora"], "distrito": prop["incidencia_distrito"],
                    "incMin": prop["incidencia_min"], "nPend": prop["n_pendientes"],
                    "tardeAct": prop["tarde_actual"], "tardAct": prop["tard_actual_min"],
                    "tardeProp": prop["tarde_propuesto"], "tardProp": prop["tard_propuesto_min"],
                    "recuperadas": prop["recuperadas"], "reduccion": prop["reduccion_min"],
                    "ordenAct": prop["orden_actual"]}
        vehiculos.append({"veh": veh, "stops": stops, "incIdx": inc_idx,
                          "ordenProp": orden_prop, "card": card})
    return {"hub": hub, "t0": t0, "speed": float(VELOCIDAD_KMH), "vehiculos": vehiculos,
            "view": _fit_view(lons, lats)}


def html_gemelo(escenario: dict, altura: int = 560) -> str:
    data = json.dumps(_datos_gemelo(escenario))
    return _PLANTILLA.replace("__ALTURA__", str(int(altura))).replace("__DATA__", data)


_PLANTILLA = r"""
<link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
<div style="font-family:Inter,sans-serif;">
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 6px;">
    <button id="pp" style="padding:6px 14px;border:1px solid #D0D5DD;border-radius:8px;background:#fff;cursor:pointer;font-size:13px;">&#10073;&#10073; Pausar</button>
    <button id="rs" style="padding:6px 14px;border:1px solid #D0D5DD;border-radius:8px;background:#fff;cursor:pointer;font-size:13px;">&#8635; Reiniciar</button>
    <span style="font-size:13px;color:#475467;">Velocidad</span>
    <input id="sp" type="range" min="0.5" max="6" step="0.5" value="2" style="width:100px;">
    <span id="kpi" style="font-size:12.5px;color:#475467;">entregados 0 &middot; alertas 0</span>
    <span id="clk" style="font-size:13px;font-weight:600;color:#0C111D;margin-left:auto;">09:00</span>
  </div>
  <div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:#475467;margin-bottom:6px;">
    <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#98A2B3;"></span> pendiente</span>
    <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#E8A33D;"></span> en riesgo</span>
    <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#0D9488;"></span> en servicio</span>
    <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#D92D20;"></span> incidencia (paralizado)</span>
    <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#027A48;"></span> entregado</span>
  </div>
  <div id="wrap" style="position:relative;width:100%;height:__ALTURA__px;">
    <div id="map" style="position:absolute;inset:0;border-radius:12px;overflow:hidden;background:#EAECF0;"></div>
    <div id="alerts" style="position:absolute;top:10px;left:10px;width:340px;max-height:calc(100% - 20px);overflow:auto;display:flex;flex-direction:column;gap:8px;z-index:5;"></div>
  </div>
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
    var VEHCOL=[[21,112,239],[127,86,217],[14,150,204],[181,71,8],[3,152,158],[122,39,113],[16,24,40],[190,24,93]];
    var TORAD=Math.PI/180;
    function hav(a,b){var p1=a.lat*TORAD,p2=b.lat*TORAD,dphi=(b.lat-a.lat)*TORAD,dl=(b.lon-a.lon)*TORAD;var h=Math.sin(dphi/2)*Math.sin(dphi/2)+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)*Math.sin(dl/2);return 2*6371*Math.asin(Math.sqrt(h));}

    function nuevoEstado(){
      return DATA.vehiculos.map(function(v){
        return {veh:v.veh,stops:v.stops,incIdx:v.incIdx,ordenProp:v.ordenProp,card:v.card,
                order:v.stops.map(function(_,i){return i;}),
                decided:(v.card?false:true),applied:false,pause:0,tInc:null,
                arr:[],dep:[],arrOf:{},total:0};
      });
    }
    var V=nuevoEstado();
    function recalc(v){
      var t=DATA.t0,prev=DATA.hub,arr=[],dep=[],arrOf={};
      for(var k=0;k<v.order.length;k++){var s=v.stops[v.order[k]];
        t+=hav(prev,s)/DATA.speed*60;arr[k]=t;arrOf[v.order[k]]=t;
        t+=s.serv+s.incMin;dep[k]=t;prev=s;}
      t+=hav(prev,DATA.hub)/DATA.speed*60;
      v.arr=arr;v.dep=dep;v.arrOf=arrOf;v.total=t;
      if(v.tInc===null&&v.incIdx>=0){var pos=v.order.indexOf(v.incIdx);v.tInc=(pos>=0?arr[pos]:-1);}
    }
    V.forEach(recalc);
    function localT(v){return simT-v.pause;}
    function awaiting(v){return v.card&&!v.decided&&v.tInc>=0&&localT(v)>=v.tInc;}
    function posAt(v,lt){
      if(lt>=v.total)return [DATA.hub.lon,DATA.hub.lat];
      var prev=DATA.hub;
      for(var k=0;k<v.order.length;k++){var s=v.stops[v.order[k]];
        var travStart=(k===0?DATA.t0:v.dep[k-1]);
        if(lt<v.arr[k]){var f=(v.arr[k]>travStart)?(lt-travStart)/(v.arr[k]-travStart):1;f=Math.max(0,Math.min(1,f));return [prev.lon+f*(s.lon-prev.lon),prev.lat+f*(s.lat-prev.lat)];}
        if(lt<v.dep[k])return [s.lon,s.lat];
        prev=s;}
      return [prev.lon,prev.lat];
    }
    function estadoStop(v,si,lt){
      var a=v.arrOf[si],s=v.stops[si];
      if(a===undefined)return 'pendiente';
      if(lt>=a+s.serv+s.incMin)return 'entregado';
      if(si===v.incIdx&&awaiting(v))return 'incidencia';
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
    function decide(i,act){var v=V[i];if(v.decided)return;if(act==='ap'){aplicarPropuesta(v);v.applied=true;}v.pause=simT-v.tInc;v.decided=true;recalc(v);sigAlert='';}

    var deckgl=new deck.DeckGL({container:'map',map:maplibregl,
      mapStyle:'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
      initialViewState:{longitude:DATA.view.longitude,latitude:DATA.view.latitude,zoom:DATA.view.zoom,pitch:0,bearing:0},
      controller:true});
    var simT=DATA.t0,playing=true,mult=2,last=performance.now(),done=false,sigAlert='';
    var pp=document.getElementById('pp');
    pp.onclick=function(){if(done)return;playing=!playing;pp.innerHTML=playing?'&#10073;&#10073; Pausar':'&#9658; Reanudar';if(playing){last=performance.now();requestAnimationFrame(loop);}};
    document.getElementById('rs').onclick=function(){V=nuevoEstado();V.forEach(recalc);simT=DATA.t0;done=false;playing=true;sigAlert='';pp.innerHTML='&#10073;&#10073; Pausar';last=performance.now();requestAnimationFrame(loop);};
    document.getElementById('sp').oninput=function(){mult=parseFloat(this.value);};
    function hhmm(m){m=Math.round(m);return ('0'+Math.floor(m/60)).slice(-2)+':'+('0'+(m%60)).slice(-2);}

    function buildAlerts(){
      var box=document.getElementById('alerts');var html='';
      for(var i=0;i<V.length;i++){var v=V[i];if(!awaiting(v))continue;var c=v.card;
        var chip=(v.applied?'':'');
        html+='<div style="background:#fff;border:1px solid #FDA29B;border-left:4px solid #D92D20;border-radius:10px;padding:10px 12px;box-shadow:0 4px 14px rgba(16,24,40,.12);font-size:12.5px;">'
          +'<div style="font-weight:600;color:#B42318;">&#9888; '+v.veh+' paralizado &middot; incidencia '+c.hora+'</div>'
          +'<div style="color:#475467;margin:2px 0 8px;">'+c.distrito+' (+'+Math.round(c.incMin)+' min) &middot; '+c.nPend+' pendientes en riesgo</div>'
          +'<div style="display:flex;gap:8px;">'
            +'<div style="flex:1;background:#F9FAFB;border-radius:8px;padding:6px 8px;"><div style="color:#667085;">Ruta actual</div><div style="font-weight:600;">'+c.tardeAct+' fuera</div><div style="color:#667085;">'+Math.round(c.tardAct)+' min tard.</div></div>'
            +'<div style="flex:1;background:#ECFDF3;border-radius:8px;padding:6px 8px;"><div style="color:#667085;">Re-secuenciada</div><div style="font-weight:600;color:#027A48;">'+c.tardeProp+' fuera</div><div style="color:#027A48;">'+Math.round(c.tardProp)+' min tard.</div></div>'
          +'</div>'
          +'<div style="color:#475467;margin:8px 0;">'+(c.recuperadas>0?('Recupera <b>'+c.recuperadas+'</b> entrega(s) y '):'')+'reduce la tardanza en <b>'+Math.round(c.reduccion)+' min</b>. Mismos pedidos.</div>'
          +'<div style="display:flex;gap:8px;">'
            +'<button data-i="'+i+'" data-a="ap" style="flex:1;padding:6px;border:0;border-radius:8px;background:#027A48;color:#fff;cursor:pointer;font-size:12.5px;">Aprobar re-ruteo</button>'
            +'<button data-i="'+i+'" data-a="de" style="flex:1;padding:6px;border:1px solid #D0D5DD;border-radius:8px;background:#fff;cursor:pointer;font-size:12.5px;">Mantener</button>'
          +'</div></div>';
      }
      box.innerHTML=html;
      var bts=box.querySelectorAll('button');
      for(var j=0;j<bts.length;j++){bts[j].onclick=function(){decide(parseInt(this.getAttribute('data-i')),this.getAttribute('data-a'));};}
    }

    function render(){
      var layers=[];var pd=[];var entregados=0,nAlert=0,acum=0,total=0;
      for(var i=0;i<V.length;i++){var v=V[i];var lt=localT(v);var col=VEHCOL[i%VEHCOL.length];
        var path=[[DATA.hub.lon,DATA.hub.lat]];var ts=[DATA.t0];
        for(var k=0;k<v.order.length;k++){var s=v.stops[v.order[k]];path.push([s.lon,s.lat]);ts.push(v.arr[k]);}
        layers.push(new deck.TripsLayer({id:'tr'+i,data:[{path:path,ts:ts}],getPath:function(d){return d.path;},getTimestamps:function(d){return d.ts;},getColor:col,opacity:0.65,widthMinPixels:3,trailLength:70,currentTime:lt}));
        layers.push(new deck.ScatterplotLayer({id:'vh'+i,data:[v],getPosition:function(d){return posAt(d,localT(d));},getFillColor:col,getRadius:150,radiusMinPixels:6,radiusMaxPixels:13,stroked:true,getLineColor:[255,255,255],lineWidthMinPixels:2,updateTriggers:{getPosition:lt}}));
        if(awaiting(v)){var ip=v.stops[v.incIdx];layers.push(new deck.ScatterplotLayer({id:'rg'+i,data:[ip],getPosition:function(d){return [d.lon,d.lat];},filled:false,stroked:true,getLineColor:[217,45,32],lineWidthMinPixels:2,getRadius:400+260*Math.abs(Math.sin(simT/2.2)),radiusMinPixels:12,radiusMaxPixels:46,updateTriggers:{getRadius:simT}}));nAlert++;}
        for(var k2=0;k2<v.stops.length;k2++){var st=estadoStop(v,k2,lt);pd.push({lon:v.stops[k2].lon,lat:v.stops[k2].lat,c:COL[st]});if(st==='entregado')entregados++;}
        total+=v.stops.length;if(lt<v.total)acum++;
      }
      layers.push(new deck.ScatterplotLayer({id:'pd',data:pd,getPosition:function(d){return [d.lon,d.lat];},getFillColor:function(d){return d.c;},getRadius:85,radiusMinPixels:4,radiusMaxPixels:10,stroked:true,getLineColor:[255,255,255],lineWidthMinPixels:1,updateTriggers:{getFillColor:simT}}));
      layers.push(new deck.ScatterplotLayer({id:'hb',data:[DATA.hub],getPosition:function(d){return [d.lon,d.lat];},getFillColor:[12,17,29],getRadius:180,radiusMinPixels:7}));
      deckgl.setProps({layers:layers});
      var sig='';for(var i2=0;i2<V.length;i2++){sig+=(awaiting(V[i2])?('1'+V[i2].applied):'0');}
      if(sig!==sigAlert){sigAlert=sig;buildAlerts();}
      document.getElementById('clk').textContent=done?'Jornada completada':hhmm(simT);
      document.getElementById('kpi').innerHTML='entregados '+entregados+'/'+total+' &middot; <b style="color:'+(nAlert>0?'#B42318':'#475467')+';">alertas '+nAlert+'</b>';
    }
    function finished(){for(var i=0;i<V.length;i++){if(!V[i].decided)return false;if(localT(V[i])<V[i].total)return false;}return true;}
    function loop(now){var dt=Math.min(0.05,(now-last)/1000);last=now;simT+=dt*mult*20;
      for(var i=0;i<V.length;i++){var v=V[i];if(v.card&&!v.decided&&v.tInc>=0&&(simT-v.pause)>=v.tInc){v.pause=simT-v.tInc;}}
      if(finished()){done=true;playing=false;pp.innerHTML='&#8635; Reiniciar';}
      render();if(playing&&!done)requestAnimationFrame(loop);}
    render();requestAnimationFrame(loop);
  }
  var tries=0;(function wait(){if((window.deck&&window.maplibregl)||tries>40){boot();}else{tries++;setTimeout(wait,150);}})();
})();
</script>
"""
