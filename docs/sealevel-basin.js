(() => {
const $=id=>document.getElementById(id);
let basin=null,graphs={},playTimer=null;
const DAY_MS=86400000;
function nextDay(iso){return new Date(Date.parse(iso+'T00:00:00Z')+DAY_MS).toISOString().slice(0,10);}
function pauseProfile(){if(playTimer!==null){clearInterval(playTimer);playTimer=null;}if($('basinPlay'))$('basinPlay').disabled=false;if($('basinPause'))$('basinPause').disabled=true;}
function playProfile(){if(playTimer!==null||!basin)return;const picker=$('basinMoment');if($('basinInterval').value!=='daily'){$('basinInterval').value='daily';render();}const max=picker.max;if(!picker.value||picker.value>=max)picker.value=picker.min||max;if(!picker.value||picker.value>=max)return; $('basinPlay').disabled=true;$('basinPause').disabled=false;playTimer=setInterval(()=>{if(!document.querySelector('#page-sealevel.active')){pauseProfile();return;}const next=nextDay(picker.value);if(next>max){pauseProfile();return;}picker.value=next;renderProfile();if(next>=max)pauseProfile();},250);}
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
function extremeTrend(rows,key){
 const n=rows.length;
 if(n<3)return {values:rows.map(()=>null),slope:null};
 const meanX=rows.reduce((a,r)=>a+r.year,0)/n;
 const meanY=rows.reduce((a,r)=>a+r[key],0)/n;
 const denominator=rows.reduce((a,r)=>a+(r.year-meanX)**2,0);
 if(!denominator)return {values:rows.map(()=>null),slope:null};
 const slope=rows.reduce((a,r)=>a+(r.year-meanX)*(r[key]-meanY),0)/denominator;
 return {values:rows.map(r=>+(meanY+slope*(r.year-meanX)).toFixed(2)),slope};
}
function renderProfile(){
 if(!basin)return;
 const series=valid(),frequency=$('basinInterval').value;
 const time=$('basinMoment').value;
 const profileFrequency=frequency;
 const profileKey=profileFrequency==='weekly'?weekStart(time):profileFrequency==='monthly'?time.slice(0,7):time;
 const rows=series.map(station=>{
   const r=intervalRows(station,profileFrequency).find(x=>x.time===profileKey);
   return {s:station,r};
 }).filter(x=>x.r&&Number.isFinite(x.r.mean_cm)).sort((a,b)=>Number(a.s.lat)-Number(b.s.lat));
 const profileLabel=profileFrequency==='weekly'?'Veckomedel, vald vecka':profileFrequency==='monthly'?'Månadsmedel, vald månad':'Dygnsmedel, vald dag';
 chart('basinProfile','line',rows.map(x=>x.s.name),[{label:profileLabel,data:rows.map(x=>x.r.mean_cm),borderColor:'#8492a6',pointRadius:5,pointBackgroundColor:rows.map(x=>stationColor(x.s)),pointBorderColor:rows.map(x=>stationColor(x.s)),spanGaps:false,tension:0}], 'cm RH 2000');
}
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
 renderProfile();
 $('basinStatus').textContent='Tidsserie: skillnad i cm mot '+(ref?.name||'referensstation')+' vid samma datum (0 cm för referensstationen). RH 2000 · G · UTC. Saknade samtidiga värden ger luckor. Bassängprofilen visar absoluta RH 2000-värden.';
 const extremeStation=series.find(s=>String(s.id)===$('basinExtremeStation').value);
 if(extremeStation){
   const annual=extremeStation.annual.filter(r=>r.coverage_pct>=90);
   const keys=annual.map(r=>String(r.year));
   const color=stationColor(extremeStation);
   const minTrend=extremeTrend(annual,'min_cm'),maxTrend=extremeTrend(annual,'max_cm');
   chart('basinExtremes','line',keys,[
     {label:'Årsminimum',data:annual.map(r=>r.min_cm),borderColor:color,borderDash:[5,4],pointRadius:3,spanGaps:false},
     {label:'Årsmaximum',data:annual.map(r=>r.max_cm),borderColor:color,pointRadius:3,spanGaps:false},
     {label:'Linjär trend – minimum',data:minTrend.values,borderColor:'#dc2626',borderWidth:2,pointRadius:0,borderDash:[6,4],spanGaps:false},
     {label:'Linjär trend – maximum',data:maxTrend.values,borderColor:'#dc2626',borderWidth:2,pointRadius:0,spanGaps:false}
   ],'cm RH 2000');
   const first=annual[0]?.year,last=annual.at(-1)?.year;
   const trendText=t=>{
     if(t.slope===null)return 'för få datapunkter för linjär trend';
     const per10=t.slope*10,amount=Math.abs(per10),digits=amount>=100?0:amount>=10?1:2;
     return (per10>=0?'+':'')+per10.toLocaleString('sv-SE',{minimumFractionDigits:digits,maximumFractionDigits:digits})+' cm per 10 år';
   };
   $('basinExtremeTrend').textContent=first===undefined
      ?'För få fullständiga år för trendberäkning.'
      :'Från '+first+' till '+last+': årsminimum '+trendText(minTrend)+'; årsmaximum '+trendText(maxTrend)+' (historisk linjär trend). Beräknad med faktisk kalenderårsskala utifrån '+annual.length+' år med minst 90 % godkända timvärden.';
   const short=annual.length<10||(last-first+1)<10;
   $('basinExtremeWarning').textContent=short?'Obs! Trendperiod kortare än 10 år ('+annual.length+' år med data).':'';
   $('basinExtremeWarning').hidden=!short;
 }

}
async function init(){
 if(basin||!$('basinHistory'))return;
 try{
 const response=await fetch('sealevel/basin.json',{cache:'no-store'});if(!response.ok)throw Error('Datakörningen behöver köras innan bassängdiagrammen visas');
 basin=await response.json();let stations=valid();if(!stations.length)throw Error('Inga stationsdata');
 $('basinReference').innerHTML=stations.map(s=>'<option value="'+s.id+'">'+s.name+'</option>').join('');
 $('basinReference').value=String(stations.find(s=>s.id===2056)?.id||stations[0].id);
 $('basinReference').addEventListener('change',render);
 $('basinExtremeStation').innerHTML=stations.map(s=>'<option value="'+s.id+'">'+s.name+'</option>').join('');
 $('basinExtremeStation').value=String(stations.find(s=>s.id===2056)?.id||stations[0].id);
 $('basinExtremeStation').addEventListener('change',render);
 $('basinStationList').innerHTML=stations.map(s=>'<label style="display:inline-flex;gap:5px;align-items:center;margin:5px"><input type="checkbox" id="basinStation'+s.id+'" checked><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:'+stationColor(s)+'"></span> '+s.name+'</label>').join(' ');
 const all=stations.flatMap(s=>s.daily.map(r=>r.time)).sort(),latest=all.at(-1);
 $('basinStart').value=latest.slice(0,4)+'-01-01';$('basinEnd').value=latest;
 const day=stations.find(s=>s.name==='Strömören')?.daily.at(-1)?.time||latest;
 $('basinMoment').value=day;$('basinMoment').min=all[0];$('basinMoment').max=latest;
 $('basinPlay').addEventListener('click',playProfile);$('basinPause').addEventListener('click',pauseProfile);
 $('basinMoment').addEventListener('change',pauseProfile);
 for(const id of ['basinStart','basinEnd','basinMoment','basinInterval'])$(id).addEventListener('change',render);
 $('basinStationList').addEventListener('change',render);render();
 }catch(e){$('basinStatus').textContent='Bassängdiagrammen väntar på data: '+e.message;}
}
document.addEventListener('DOMContentLoaded',()=>{document.querySelectorAll('#tabs button[data-page]').forEach(tab=>tab.addEventListener('click',()=>{if(tab.dataset.page!=='sealevel')pauseProfile();else setTimeout(init,100);}));if($('page-sealevel')?.classList.contains('active'))init();});
})();