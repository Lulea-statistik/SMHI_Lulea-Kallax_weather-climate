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
    '<div class="warning-meta">'+(w.geography_kind==='linje'?'Kuststräcka inom arbetsgeometrin: '+Number(w.overlap_length_km||0).toLocaleString('sv-SE')+' km (linjegeometri)':'Ytöverlappning: '+Number(w.overlap_km2||0).toLocaleString('sv-SE')+' km² ('+Number(w.overlap_percent||0).toLocaleString('sv-SE')+' % av arbetsgeometrin)')+'</div></article>').join('')
    :'<p>Inga varningsområden matchar valda filter i senast insamlade data.</p>';
  if(!smhiWarningMap)return;
  if(smhiWarningLayer)smhiWarningMap.removeLayer(smhiWarningLayer);
  smhiWarningLayer=L.layerGroup().addTo(smhiWarningMap);
  const colors={YELLOW:'#e5bc35',ORANGE:'#ea7b22',RED:'#be3131',MESSAGE:'#4288b8'};
  matches.forEach(w=>{
    // Older snapshots contain full SMHI geometries: never draw them outside Luleå.
    if(!w.geometry||w.clipped_to_municipality!==true)return;
    L.geoJSON(w.geometry,{style:{color:colors[String(w.level_code).toUpperCase()]||'#387ba8',weight:w.geometry?.type?.includes('Line')?5:2,fillOpacity:w.geometry?.type?.includes('Line')?0:0.35}})
      .bindPopup('<strong>'+warningText(w.event||w.title)+'</strong><p>'+warningText(w.level||'')+'</p><p>'+warningDate(w.start)+'</p>').addTo(smhiWarningLayer);
  });
}
async function initWarningsPage(){
  await loadWarningVersions();
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
    if(smhiWarningsData.warnings_clipped_to_municipality!==true)status.textContent+=' Kartytorna visas efter nästa datainsamling med kommunavgränsning.';
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

let warningVersions=null,warningVersionMap=null,warningVersionLayer=null;
function showWarningVersion(){
  const key=document.getElementById('warningVersionKey').value;
  const selector=document.getElementById('warningVersionIndex');
  const events=(warningVersions?.events||[]).filter(e=>e.key===key);
  const idx=Number(selector.value);
  const e=events[idx];
  const status=document.getElementById('warningVersionStatus');
  if(warningVersionLayer){warningVersionMap.removeLayer(warningVersionLayer);warningVersionLayer=null;}
  document.getElementById('warningVersionTimeline').innerHTML=events.map((item,i)=>
    '<div class="warning-item">'+warningText(warningDate(item.observed_at))+' – '+
    warningText(item.action==='first_observed'?'Först observerad':item.action==='changed'?'Ändrad':'Inte längre observerad')+
    ' · '+warningText(item.level_code||'')+(item.geometry_changed?' · Geometrin ändrades':'')+'</div>').join('');
  if(!e){status.textContent='Välj en observation.';return;}
  status.textContent='Observerad '+warningDate(e.observed_at)+' · '+(e.action==='first_observed'?'Första observation':e.action==='changed'?'Ändrad version':'Försvunnen ur flödet');
  if(e.geometry){
    const isLine=String(e.geography_kind).includes('Line');
    warningVersionLayer=L.geoJSON(e.geometry,{style:{color:e.level_code==='RED'?'#bb3030':e.level_code==='ORANGE'?'#ec8728':'#ddbb36',weight:isLine?5:2,fillOpacity:isLine?0:.4}}).addTo(warningVersionMap);
    if(warningVersionLayer.getBounds().isValid())warningVersionMap.fitBounds(warningVersionLayer.getBounds().pad(.15));
  }
  setTimeout(()=>warningVersionMap.invalidateSize(),40);
}
async function loadWarningVersions(){
  const status=document.getElementById('warningVersionStatus');
  if(!warningVersionMap){
    warningVersionMap=L.map('warningVersionMap',{scrollWheelZoom:false}).setView([65.6,22],8);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap contributors'}).addTo(warningVersionMap);
    document.getElementById('warningVersionKey').addEventListener('change',()=>{
      const key=document.getElementById('warningVersionKey').value;
      const matching=(warningVersions?.events||[]).filter(e=>e.key===key);
      const select=document.getElementById('warningVersionIndex');
      select.innerHTML=matching.map((e,i)=>'<option value="'+i+'">'+warningText(warningDate(e.observed_at))+' – '+warningText(e.action)+'</option>').join('');
      select.value=matching.length?String(matching.length-1):'';
      showWarningVersion();
    });
    document.getElementById('warningVersionIndex').addEventListener('change',showWarningVersion);
  }
  setTimeout(()=>warningVersionMap.invalidateSize(),100);
  try{
    const response=await fetch('warnings/versions.json',{cache:'no-store'});
    if(!response.ok)throw Error('Versionsfil saknas');
    warningVersions=await response.json();
    const keys=[...new Set((warningVersions.events||[]).map(e=>e.key))];
    const dropdown=document.getElementById('warningVersionKey');
    const previous=dropdown.value;
    dropdown.innerHTML=keys.map(k=>'<option value="'+warningText(k)+'">'+warningText(k)+'</option>').join('');
    dropdown.value=keys.includes(previous)?previous:(keys[0]||'');
    dropdown.dispatchEvent(new Event('change'));
    if(!keys.length)status.textContent='Inga observerade versioner ännu.';
  }catch(err){status.textContent='Kunde inte läsa versionshistorik: '+err.message;}
}
