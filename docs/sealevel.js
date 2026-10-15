// Independent water-level view: no changes to weather dashboards.
(() => {
let data=null, figures={};
const $=id=>document.getElementById(id);
const fmt=n=>Number(n).toLocaleString('sv-SE',{maximumFractionDigits:1});
function plot(id,labels,sets){if(figures[id])figures[id].destroy();figures[id]=new Chart($(id),{type:'line',data:{labels,datasets:sets.map(s=>({pointRadius:0,borderWidth:2,tension:0.1,spanGaps:false,...s}))},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:sets.length>1}},scales:{x:{ticks:{maxTicksLimit:13}},y:{title:{display:true,text:'cm (RH 2000)'}}}}});}
function render(){
 if(!data)return;
 const start=Number($('seaLevelFrom').value),end=Number($('seaLevelTo').value),resolution=$('seaLevelResolution').value;
 const filter=key=>Number(key.slice(0,4))>=start&&Number(key.slice(0,4))<=end;
 const rows=(resolution==='daily'?data.daily:data.monthly).filter(r=>filter(r.day||r.month));
 plot('seaLevelHistory',rows.map(r=>r.day||r.month),[{label:'Medelvattenstånd',data:rows.map(r=>r.mean_cm),borderColor:'#2563eb'}]);
 const annual=data.annual.filter(r=>r.year>=start&&r.year<=end);
 plot('seaLevelAnnual',annual.map(r=>String(r.year)),[
  {label:'Medel',data:annual.map(r=>r.mean_cm),borderColor:'#2563eb'},
  {label:'Minimum',data:annual.map(r=>r.min_cm),borderColor:'#0f766e'},
  {label:'Maximum',data:annual.map(r=>r.max_cm),borderColor:'#dc2626'}]);
 const months=Array.from({length:12},(_,i)=>String(i+1).padStart(2,'0'));
 const grouped=months.map(m=>data.monthly.filter(r=>filter(r.month)&&r.month.endsWith('-'+m)));
 plot('seaLevelSeason',['Jan','Feb','Mar','Apr','Maj','Jun','Jul','Aug','Sep','Okt','Nov','Dec'],[{label:'Vattenstånd',data:grouped.map(a=>a.length?a.reduce((s,r)=>s+r.mean_cm*r.count,0)/a.reduce((s,r)=>s+r.count,0):null),borderColor:'#2563eb'}]);
 const subset=annual;
 $('seaLevelStats').textContent='Godkända observationer: '+fmt(subset.reduce((s,r)=>s+r.count,0))+' · Högsta: '+(subset.length?fmt(Math.max(...subset.map(r=>r.max_cm)))+' cm':'–')+' · Lägsta: '+(subset.length?fmt(Math.min(...subset.map(r=>r.min_cm)))+' cm':'–');
}
async function init(){
 if(data||!$('seaLevelHistory'))return;
 const status=$('seaLevelStatus');
 try{
 const response=await fetch('sealevel/stromoren.json',{cache:'no-store'});
 if(!response.ok)throw new Error('Bearbetade data saknas. Kör bootstrap.');
 data=await response.json();
 if(!data.annual?.length)throw new Error('Inga godkända observationsvärden.');
 const years=data.annual.map(x=>x.year),min=Math.min(...years),max=Math.max(...years);
 for(const id of ['seaLevelFrom','seaLevelTo']){
  const s=$(id);s.innerHTML='';
  for(let y=min;y<=max;y++){const opt=document.createElement('option');opt.value=y;opt.textContent=y;s.append(opt);}
  s.value=id==='seaLevelFrom'?min:max;
  s.addEventListener('change',render);
 }
 $('seaLevelResolution').addEventListener('change',render);
 status.textContent='Strömören · '+data.coverage.first.slice(0,10)+' – '+data.coverage.last.slice(0,10)+' · RH 2000 · cm · UTC · kvalitetskod G. Före juli 2019 var observationerna inte kvalitetssäkrade på motsvarande sätt.';
 render();
 }catch(error){status.textContent='Diagram kan ännu inte visas: '+error.message;}
}
document.addEventListener('DOMContentLoaded',()=>{
 const tab=document.querySelector('#tabs button[data-page="sealevel"]');
 if(tab)tab.addEventListener('click',()=>setTimeout(init,50));
 if(document.querySelector('#page-sealevel.active'))init();
});
})();