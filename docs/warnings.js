let smhiWarningMap=null, smhiWarningsData=null,smhiWarningBoundary=null,smhiWarningLayer=null;
function warningCategoryCode(event){
  const c=String(event||'').toUpperCase();
  if(c.includes('FIRE'))return 'fire';
  if(c.includes('WATER_SHORTAGE'))return 'water';
  if(c.includes('HEAT')||c.includes('HIGH_TEMPERATURE'))return 'heat';
  return 'weather';
}
function warningText(value){
  return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
function warningDate(value){
  if(!value)return 'Ej angivet';
  const d=new Date(value);
  return Number.isFinite(d.getTime())?d.toLocaleString('sv-SE',{dateStyle:'medium',timeStyle:'short'}):String(value);
}
function filteredWarnings(){
  const cat=document.getElementById('warningCategory').value;
  const lev=document.getElementById('warningLevel').value;
  return (smhiWarningsData?.warnings||[]).filter(w=>(cat==='all'||warningCategoryCode(w.event_code)===cat)&&(lev==='all'||String(w.level_code).toUpperCase()===lev));
}
function drawWarnings(){
  const status=document.getElementById('warningStatus'),results=document.getElementById('warningResults');
  const matches=filteredWarnings();
  if(smhiWarningsData){
    status.textContent='Hämtad: '+warningDate(smhiWarningsData.fetched_utc)+' · '+matches.length+' varningsområden som matchar valda filter (totalt '+smhiWarningsData.municipality_warning_areas+').';
  }
  results.innerHTML=matches.length?matches.map(w=>'<article class="warning-item"><strong>'+warningText(w.event||w.title||'Varning')+'</strong> · '+warningText(w.level||'')+
    '<div class="warning-meta">'+warningText(w.title||'')+' · '+warningText(w.area_name||'')+' · '+warningDate(w.start)+' – '+warningDate(w.end)+'</div>'+
    '<div class="warning-meta">Överlappning: '+Number(w.overlap_km2||0).toLocaleString('sv-SE')+' km² ('+Number(w.overlap_percent||0).toLocaleString('sv-SE')+' % av arbetsgeometrin)</div></article>').join('')
    :'<p>Inga varningsområden matchar valda filter i senast insamlade data.</p>';
  if(!smhiWarningMap)return;
  if(smhiWarningLayer)smhiWarningMap.removeLayer(smhiWarningLayer);
  smhiWarningLayer=L.layerGroup().addTo(smhiWarningMap);
  const colors={YELLOW:'#e5bc35',ORANGE:'#ea7b22',RED:'#be3131',MESSAGE:'#4288b8'};
  matches.forEach(w=>{
    if(!w.geometry)return;
    L.geoJSON(w.geometry,{style:{color:colors[String(w.level_code).toUpperCase()]||'#387ba8',weight:2,fillOpacity:0.35}})
      .bindPopup('<strong>'+warningText(w.event||w.title)+'</strong><p>'+warningText(w.level||'')+'</p><p>'+warningDate(w.start)+'</p>').addTo(smhiWarningLayer);
  });
}
async function initWarningsPage(){
  const status=document.getElementById('warningStatus');
  if(!smhiWarningMap){
    smhiWarningMap=L.map('warningsMap',{scrollWheelZoom:false}).setView([65.6,22.1],8);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap contributors'}).addTo(smhiWarningMap);
    document.getElementById('warningCategory').addEventListener('change',drawWarnings);
    document.getElementById('warningLevel').addEventListener('change',drawWarnings);
  }
  setTimeout(()=>smhiWarningMap.invalidateSize(),80);
  if(!smhiWarningBoundary){
    try{
      const b=await fetch('snowmap_boundary.geojson').then(r=>{if(!r.ok)throw Error('Kommungeometri saknas');return r.json();});
      smhiWarningBoundary=L.geoJSON(b,{style:{color:'#243e5c',weight:2,fillColor:'#eef3fa',fillOpacity:0.15}}).addTo(smhiWarningMap);
      smhiWarningMap.fitBounds(smhiWarningBoundary.getBounds());
    }catch(e){status.textContent='Kommungränsen kunde inte läsas: '+e.message;}
  }
  try{
    const response=await fetch('warnings/current.json',{cache:'no-store'});
    if(!response.ok)throw Error('Ingen publicerad varningsfil ännu');
    smhiWarningsData=await response.json();
    drawWarnings();
  }catch(e){status.textContent='Varningsdata är inte publicerade ännu: '+e.message;document.getElementById('warningResults').textContent='Väntar på första lyckade körningen av arkiveringen.';}
  try{
    const response=await fetch('warnings/history.json',{cache:'no-store'});
    if(!response.ok)throw Error('Ingen historik');
    const entries=await response.json();
    const body=document.getElementById('warningHistory');
    if(!Array.isArray(entries)||!entries.length){body.textContent='Historik saknas ännu.';return;}
    body.innerHTML='<table class="warning-history-table"><thead><tr><th>Insamlad</th><th>Varningsområden i Luleå</th><th>Kategorier</th></tr></thead><tbody>'+
      entries.slice(-50).reverse().map(e=>'<tr><td>'+warningDate(e.fetched_utc)+'</td><td>'+Number(e.lulea_area_count||0)+'</td><td>'+warningText((e.events||[]).join(', ')||'Inga')+'</td></tr>').join('')+'</tbody></table>';
  }catch{document.getElementById('warningHistory').textContent='Ingen publicerad insamlingshistorik ännu.';}
}
