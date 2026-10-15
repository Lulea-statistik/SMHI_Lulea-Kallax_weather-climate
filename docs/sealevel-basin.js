(() => {
const $=id=>document.getElementById(id);
let basin=null,graphs={};
// Continuous latitude scale: southernmost dark blue, northernmost pale red.
const south=[18,48,125],north=[244,156,164];
const validLat=()=>valid().filter(s=>Number.isFinite(+s.lat));
function stationColor(s){
 const latitudes=validLat().map(x=>+x.lat), lo=Math.min(...latitudes), hi=Math.max(...latitudes);
 const t=hi===lo?0.5:Math.max(0,Math.min(1,(+s.lat-lo)/(hi-lo)));
 return 'rgb('+south.map((v,i)=>Math.round(v+(north[i]-v)*t)).join(',')+')';
}
function weekStart(date){
 const d=new Date(date+'T00:00:00Z');
 d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7);
 return d.toISOString().slice(0,10);
}
function intervalRows(s,frequency){
 if(frequency!=='weekly')return s[frequency]||[];
 const groups=new Map();
 for(const r of s.daily||[]){
   const key=weekStart(r.time), old=groups.get(key)||{sum:0,count:0};
   old.sum+=r.mean_cm*r.count;old.count+=r.count;groups.set(key,old);
 }
 return [...groups].sort((a,b)=>a[0].localeCompare(b[0])).map(([time,v])=>({time,mean_cm:v.sum/v.count,count:v.count}));
}
const valid=()=>basin.stations.filter(s=>s.annual?.length);
function chart(id,type,labels,series,ylabel){if(graphs[id])graphs[id].destroy();graphs[id]=new Chart($(id),{type,data:{labels,datasets:series},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:true}},scales:{x:{ticks:{maxTicksLimit:11}},y:{title:{display:true,text:ylabel}}}}});}
function render(){
 if(!basin)return;
 const series=valid(),frequency=$('basinInterval').value;
 const start=$('basinStart').value,end=$('basinEnd').value;
 const chosen=series.filter(s=>$('basinStation'+s.id)?.checked);
 const ref=series.find(s=>String(s.id)===$('basinReference').value);
 const refMap=new Map((ref?intervalRows(ref,frequency):[]).map(r=>[r.time,r.mean_cm]));
 const minKey=frequency==='weekly'?weekStart(start):start.slice(0,frequency==='monthly'?7:10);
 const maxKey=frequency==='weekly'?weekStart(end):end.slice(0,frequency==='monthly'?7:10);
 const keys=[...new Set(chosen.flatMap(s=>intervalRows(s,frequency).map(r=>r.time).filter(t=>t>=minKey&&t<=maxKey)))].sort();
 chart('basinHistory','line',keys,chosen.map((s,i)=>{let map=new Map(intervalRows(s,frequency).map(r=>[r.time,r.mean_cm]));return {label:s.name,data:keys.map(k=>map.has(k)&&refMap.has(k)?+(map.get(k)-refMap.get(k)).toFixed(2):null),pointRadius:0,borderWidth:1.5,spanGaps:false,borderColor:stationColor(s)};}),'cm relativt '+(ref?.name||'referensstation'));
 const time=$('basinMoment').value;
 const rows=series.map(s=>{let r=s.daily.find(x=>x.time===time);return {s,r};});
 chart('basinProfile','line',rows.map(x=>x.s.name),[{label:'Dygnsmedel, vald dag',data:rows.map(x=>x.r?.mean_cm??null),borderColor:'#8492a6',pointRadius:5,pointBackgroundColor:rows.map(x=>stationColor(x.s)),pointBorderColor:rows.map(x=>stationColor(x.s)),spanGaps:false}], 'cm RH 2000');
 $('basinStatus').textContent='Tidsserie: skillnad i cm mot '+(ref?.name||'referensstation')+' vid samma datum (0 cm för referensstationen). RH 2000 · G · UTC. Saknade samtidiga värden ger luckor. Bassängprofilen visar absoluta RH 2000-värden.';
 const years=[...new Set(series.flatMap(s=>s.annual.map(x=>x.year)))].sort();
 chart('basinExtremes','line',years.map(String),chosen.flatMap(s=>['min_cm','max_cm'].map((metric,j)=>{const d=new Map(s.annual.map(r=>[r.year,(r.coverage_pct>=90?r[metric]:null)]));return {label:s.name+(j?' max':' min'),data:years.map(y=>d.get(y)??null),borderColor:colors[series.indexOf(s)%colors.length],borderDash:j?[]:[5,4],pointRadius:2,spanGaps:false};})),'cm RH 2000');
}
async function init(){
 if(basin||!$('basinHistory'))return;
 try{
 const response=await fetch('sealevel/basin.json',{cache:'no-store'});if(!response.ok)throw Error('Datakörningen behöver köras innan bassängdiagrammen visas');
 basin=await response.json();let stations=valid();if(!stations.length)throw Error('Inga stationsdata');
 $('basinReference').innerHTML=stations.map(s=>'<option value="'+s.id+'">'+s.name+'</option>').join('');
 $('basinReference').value=String(stations.find(s=>s.id===2056)?.id||stations[0].id);
 $('basinReference').addEventListener('change',render);
 $('basinStationList').innerHTML=stations.map(s=>'<label style="display:inline-flex;gap:5px;align-items:center;margin:5px"><input type="checkbox" id="basinStation'+s.id+'" checked><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+stationColor(s)+'"></span> '+s.name+'</label>').join(' ');
 const all=stations.flatMap(s=>s.daily.map(r=>r.time)).sort(),latest=all.at(-1);
 $('basinStart').value=latest.slice(0,4)+'-01-01';$('basinEnd').value=latest;
 const day=stations.find(s=>s.name==='Strömören')?.daily.at(-1)?.time||latest;
 $('basinMoment').value=day;$('basinMoment').max=latest;
 for(const id of ['basinStart','basinEnd','basinMoment','basinInterval'])$(id).addEventListener('change',render);
 $('basinStationList').addEventListener('change',render);render();
 }catch(e){$('basinStatus').textContent='Bassängdiagrammen väntar på data: '+e.message;}
}
document.addEventListener('DOMContentLoaded',()=>{document.querySelector('#tabs button[data-page="sealevel"]')?.addEventListener('click',()=>setTimeout(init,100));if($('page-sealevel')?.classList.contains('active'))init();});
})();