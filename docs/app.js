let DATA=null;const charts={};let seaIceLeafletMap=null;let seaIceSeasonLayer=null;let seaIceSeasonManifest=null;const seaIceSeasonCache=new Map();let seaIceSeasonTimer=null;let algaeLeafletMap=null;let algaeSeasonLayer=null;let algaeSeasonManifest=null;let algaeHistoryIndex=null;const algaeSeasonCache=new Map();let snowMapLeaflet=null;let snowMapLayer=null;let snowMapBoundaryLayer=null;let snowMapIndex=null;let snowMapSeasonData=null;let snowGridIndex=null;let snowGridData=null;let snowGridGeometry=null;let snowGridSeries=null;let copernicusSnowDuration=null;let smhiRenderedSnowDaily=null;let smhiRenderedSnowQa=null;const snowMapSeasonCache=new Map();const snowGridCache=new Map();let lightningMapLeaflet=null;let lightningMapLayer=null;let lightningMapBoundary=null;let lightningMapIndex=null;let lightningMapData=null;const lightningMapCache=new Map();let algaeSeasonTimer=null;const months=['Jan','Feb','Mar','Apr','Maj','Jun','Jul','Aug','Sep','Okt','Nov','Dec'];const hours=Array.from({length:24},(_,i)=>String(i).padStart(2,'0'));const MONTH_GREEN='#4f9d69';const SUN_YELLOW='#f2c94c';const PRECIP_DARK_BLUE='#163a5f';let temp2Start=null;const dateYearCache={};
const el=id=>document.getElementById(id);
let globalLoadingCount=0;
function beginGlobalLoading(text='Laddar…'){
  globalLoadingCount++;
  const box=el('globalLoading'),label=el('globalLoadingText');
  if(label&&text)label.textContent=text;
  if(box)box.classList.remove('is-hidden');
  let ended=false;
  return ()=>{
    if(ended)return;
    ended=true;
    globalLoadingCount=Math.max(0,globalLoadingCount-1);
    if(globalLoadingCount===0&&box)box.classList.add('is-hidden');
  };
}
const nativeFetch=window.fetch.bind(window);
window.fetch=async function(...args){
  const done=beginGlobalLoading('Laddar data…');
  try{return await nativeFetch(...args);}
  finally{done();}
};
function destroyChart(id){if(charts[id]){charts[id].destroy();delete charts[id];}}
function lineChart(id,labels,datasets,yTitle,extra={}){destroyChart(id);charts[id]=new Chart(el(id),{type:'line',data:{labels,datasets:datasets.map(d=>({borderWidth:2,pointRadius:0,tension:.15,...d}))},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:datasets.length>1}},scales:{x:{grid:{display:false}},y:{title:{display:!!yTitle,text:yTitle}}},...extra}});}
function barChart(id,labels,data,yTitle,color=null){destroyChart(id);charts[id]=new Chart(el(id),{type:'bar',data:{labels,datasets:[{data,borderWidth:0,...(color?{backgroundColor:color}:{})}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:!!yTitle,text:yTitle}}}}});}
function currentFilters(){return{from:+el('yearFrom').value,to:+el('yearTo').value,month:+el('month').value};}
function inYears(r,f){return r.year>=f.from&&r.year<=f.to;}
function directionName(deg){const names=['N','NO','O','SO','S','SV','V','NV'];return names[Math.round((((deg||0)%360)+360)%360/45)%8];}
function updateCompass(deg,label=''){if(deg==null||Number.isNaN(+deg))return;const d=((+deg%360)+360)%360;el('windArrow').style.transform='translate(-50%,-100%) rotate('+d+'deg)';el('windCompassText').textContent=(label?label+' · ':'')+d.toFixed(0)+'° = vind från '+directionName(d);}
function circularFromParts(rows){let s=0,c=0,n=0;rows.forEach(r=>{s+=r.sin_sum||0;c+=r.cos_sum||0;n+=r.count||0;});if(!n||(!s&&!c))return null;let d=Math.atan2(s,c)*180/Math.PI;d=(d+360)%360;return d===0?360:d;}
function temperatureMetric(){return el('tempMetric').value;}
function metricName(m){
  if(m==='min')return 'Absolut minimum';
  if(m==='max')return 'Absolut maximum';
  if(m==='avg_daily_min')return 'Genomsnittligt dygnsminimum';
  if(m==='avg_daily_max')return 'Genomsnittligt dygnsmaximum';
  return 'Genomsnittlig';
}
function weatherPhenomenon(code){
  let n=Number(code); if(!Number.isFinite(n)) return 'Okänt väderfenomen';
  if(n>=100) n=n%100;
  if(n<=3) return n===0?'Klart eller oförändrat väder':n===1?'Moln upplöses':n===2?'Oförändrad molnighet':'Moln utvecklas';
  if(n===4) return 'Rök'; if(n===5) return 'Dis'; if(n===6) return 'Damm'; if(n<=9) return 'Damm- eller sandfenomen';
  if(n===10) return 'Dis'; if(n<=12) return 'Marknära dimma'; if(n===13) return 'Blixt synlig'; if(n<=16) return 'Nederbörd i närheten';
  if(n===17) return 'Åska utan nederbörd'; if(n===18) return 'Kastvind'; if(n===19) return 'Tromb';
  if(n===20) return 'Duggregn'; if(n===21) return 'Regn'; if(n===22) return 'Snö'; if(n===23) return 'Regn och snö';
  if(n===24) return 'Underkyld nederbörd'; if(n===25) return 'Regnskur'; if(n===26) return 'Snöby'; if(n===27) return 'Hagelby';
  if(n===28) return 'Dimma'; if(n===29) return 'Åska'; if(n<=35) return 'Damm- eller sandstorm'; if(n<=39) return 'Drivande eller yrande snö';
  if(n<=49) return 'Dimma'; if(n<=59) return 'Duggregn'; if(n<=69) return 'Regn'; if(n<=79) return 'Snö eller annan fast nederbörd';
  if(n<=89) return 'Skurar'; if(n<=99) return 'Åska';
  return 'Väderfenomen';
}
function normalizedWeatherPhenomenon(code,year){
  const label=weatherPhenomenon(code);
  if(year>=1949&&year<=1981&&['Moln utvecklas','Oförändrad molnighet','Moln upplöses'].includes(label)){
    return 'Klart eller oförändrat väder';
  }
  return label;
}
function temp2Quantile(values,q){
  const v=values.filter(x=>x!=null&&Number.isFinite(x)).slice().sort((a,b)=>a-b);
  if(!v.length)return null;
  if(v.length===1)return v[0];
  const pos=(v.length-1)*q;
  const base=Math.floor(pos),rest=pos-base;
  return v[base+1]!==undefined?v[base]+rest*(v[base+1]-v[base]):v[base];
}
function temp2AnnualMean(year){
  const vals=DATA.temperature.monthly
    .filter(r=>r.year===year&&r.avg!=null&&Number.isFinite(r.avg))
    .map(r=>r.avg);
  return vals.length?vals.reduce((s,v)=>s+v,0)/vals.length:null;
}
function setupTemp2Slider(){
  const years=[...DATA.years].sort((a,b)=>a-b);
  const period=30;
  const minStart=years[0],maxStart=Math.max(minStart,years[years.length-1]-(period-1));
  const centerOffset=(period-1)/2;
  const minCenter=minStart+centerOffset,maxCenter=maxStart+centerOffset;
  temp2Start=maxStart;
  const s=el('temp2Start');
  s.min=minCenter;s.max=maxCenter;s.step=1;s.value=temp2Start+centerOffset;
  s.addEventListener('input',e=>{temp2Start=Math.round((+e.target.value)-centerOffset);renderTemp2();});
  renderTemp2();
}
function renderTemp2(){
  const period=30;
  const allYears=[...DATA.years].sort((a,b)=>a-b);
  const fallbackStart=Math.max(allYears[0],allYears[allYears.length-1]-(period-1));
  const start=temp2Start??fallbackStart;
  const years=Array.from({length:period},(_,i)=>start+i).filter(y=>DATA.years.includes(y));
  if(!years.length)return;
  const latestYear=years[years.length-1];
  el('temp2PeriodLabel').textContent=start+'–'+(start+period-1);

  const yearMeans=years.map(y=>({year:y,mean:temp2AnnualMean(y)})).filter(x=>x.mean!=null&&Number.isFinite(x.mean));
  const extremeYear=yearMeans.length
    ? yearMeans.reduce((best,cur)=>cur.mean>best.mean?cur:best,yearMeans[0]).year
    : latestYear;

  const selectedMonth=+(el('month')?.value||0);

  destroyChart('tempProfiles');

  if(selectedMonth){
    const values=years.map(y=>{
      const r=DATA.temperature.monthly.find(x=>x.year===y&&x.month===selectedMonth);
      return r?.avg??null;
    });
    const p10=temp2Quantile(values,.10),p25=temp2Quantile(values,.25),median=temp2Quantile(values,.50),p75=temp2Quantile(values,.75),p90=temp2Quantile(values,.90);
    const latestIndex=years.indexOf(latestYear),extremeIndex=years.indexOf(extremeYear);
    charts.tempProfiles=new Chart(el('tempProfiles'),{
      type:'line',
      data:{labels:years,datasets:[
        {label:'Månadsmedel',data:values,borderColor:'#9ca3af',backgroundColor:'rgba(156,163,175,.15)',pointRadius:2,borderWidth:1.5,tension:.12},
        {label:'Median',data:years.map(()=>median),borderColor:'#6b7280',pointRadius:0,borderWidth:2},
        {label:'10–90 percentil',data:years.map(()=>p90),borderColor:'rgba(0,0,0,0)',pointRadius:0,borderWidth:0,fill:{target:{value:p10},above:'rgba(209,213,219,.28)'}},
        {label:'25–75 percentil',data:years.map(()=>p75),borderColor:'rgba(0,0,0,0)',pointRadius:0,borderWidth:0,fill:{target:{value:p25},above:'rgba(156,163,175,.28)'}},
        {label:String(latestYear),data:years.map((_,i)=>i===latestIndex?values[i]:null),showLine:false,pointRadius:6,pointBackgroundColor:'#2563eb',pointBorderColor:'#2563eb'},
        {label:extremeYear+' (varmaste år)',data:years.map((_,i)=>i===extremeIndex?values[i]:null),showLine:false,pointRadius:6,pointBackgroundColor:'#2e8b57',pointBorderColor:'#2e8b57'}
      ]},
      options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
        plugins:{legend:{display:true,labels:{filter:item=>!['10–90 percentil','25–75 percentil'].includes(item.text)}},
          tooltip:{callbacks:{label:c=>c.parsed.y==null?c.dataset.label:c.dataset.label+': '+c.parsed.y.toLocaleString('sv-SE',{maximumFractionDigits:2})+' °C'}}},
        scales:{x:{grid:{display:false}},y:{title:{display:true,text:'°C'}}}}
    });
    return;
  }

  const stats=[...Array(12)].map((_,i)=>{
    const vals=years.map(y=>{
      const r=DATA.temperature.monthly.find(x=>x.year===y&&x.month===i+1);
      return r?.avg??null;
    }).filter(v=>v!=null&&Number.isFinite(v));
    return {
      p10:temp2Quantile(vals,.10),
      p25:temp2Quantile(vals,.25),
      median:temp2Quantile(vals,.50),
      p75:temp2Quantile(vals,.75),
      p90:temp2Quantile(vals,.90)
    };
  });

  const latestSeries=[...Array(12)].map((_,i)=>{
    const r=DATA.temperature.monthly.find(x=>x.year===latestYear&&x.month===i+1);
    return r?.avg??null;
  });
  const extremeSeries=[...Array(12)].map((_,i)=>{
    const r=DATA.temperature.monthly.find(x=>x.year===extremeYear&&x.month===i+1);
    return r?.avg??null;
  });

  charts.tempProfiles=new Chart(el('tempProfiles'),{
    type:'line',
    data:{labels:months,datasets:[
      {label:'P10',data:stats.map(d=>d.p10),borderColor:'rgba(0,0,0,0)',backgroundColor:'rgba(0,0,0,0)',pointRadius:0,borderWidth:0},
      {label:'10–90 percentil',data:stats.map(d=>d.p90),borderColor:'rgba(0,0,0,0)',backgroundColor:'rgba(209,213,219,.42)',pointRadius:0,borderWidth:0,fill:'-1'},
      {label:'P25',data:stats.map(d=>d.p25),borderColor:'rgba(0,0,0,0)',backgroundColor:'rgba(0,0,0,0)',pointRadius:0,borderWidth:0},
      {label:'25–75 percentil',data:stats.map(d=>d.p75),borderColor:'rgba(0,0,0,0)',backgroundColor:'rgba(156,163,175,.42)',pointRadius:0,borderWidth:0,fill:'-1'},
      {label:start+'–'+(start+period-1)+' median',data:stats.map(d=>d.median),borderColor:'#737373',backgroundColor:'#737373',pointRadius:0,borderWidth:2,tension:.2},
      {label:extremeYear+' (varmaste år)',data:extremeSeries,borderColor:'#2e8b57',backgroundColor:'#2e8b57',pointRadius:0,borderWidth:2,borderDash:[5,4],tension:.2},
      {label:String(latestYear),data:latestSeries,borderColor:'#2563eb',backgroundColor:'#2563eb',pointRadius:0,borderWidth:2.5,tension:.2}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{display:true,labels:{filter:item=>!['P10','P25'].includes(item.text)}},
        tooltip:{callbacks:{label:c=>{
          if(c.parsed.y==null)return c.dataset.label;
          return c.dataset.label+': '+c.parsed.y.toLocaleString('sv-SE',{maximumFractionDigits:2})+' °C';
        }}}
      },
      scales:{x:{grid:{display:false}},y:{title:{display:true,text:'°C'}}}
    }
  });
}
function weatherChart(rows){
  destroyChart('weatherCodes');
  const selected=el('weatherCode').value;
  const years=[...new Set(rows.map(r=>r.year))].sort((a,b)=>a-b);
  const totals={};rows.forEach(r=>totals[r.year]=(totals[r.year]||0)+r.count);

  const categories=[...new Set(rows.map(r=>normalizedWeatherPhenomenon(r.code,r.year)))].sort((a,b)=>a.localeCompare(b,'sv'));
  if(selected==='all'){
    const datasets=categories.map(category=>({
      label:category,
      data:years.map(y=>{
        const n=rows.filter(r=>r.year===y&&normalizedWeatherPhenomenon(r.code,r.year)===category).reduce((s,r)=>s+r.count,0);
        return totals[y]?100*n/totals[y]:0;
      }),
      borderWidth:0
    }));
    charts.weatherCodes=new Chart(el('weatherCodes'),{type:'bar',data:{labels:years,datasets},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'nearest',intersect:true},
      plugins:{legend:{display:false},tooltip:{displayColors:false,callbacks:{title:items=>String(items[0].label),label:c=>(c.dataset.label||'')+': '+c.parsed.y.toFixed(1)+' %'}}},
      scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,min:0,max:100,title:{display:true,text:'Andel observationer (%)'},ticks:{callback:v=>v+' %'}}}}});
    el('weatherTitle').textContent='Rådande väder – fördelning per år';
    el('weatherHint').textContent='Väderkoder med samma betydelse är sammanslagna till gemensamma vädertyper för att färgerna ska vara jämförbara över tid.';
  }else{
    const vals=years.map(y=>{
      const n=rows.filter(r=>r.year===y&&normalizedWeatherPhenomenon(r.code,r.year)===selected).reduce((s,r)=>s+r.count,0);
      return totals[y]?100*n/totals[y]:0;
    });
    charts.weatherCodes=new Chart(el('weatherCodes'),{type:'bar',data:{labels:years,datasets:[{label:selected,data:vals,borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{displayColors:false,callbacks:{title:items=>String(items[0].label),label:c=>selected+': '+c.parsed.y.toFixed(1)+' %'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,max:100,title:{display:true,text:'Andel observationer (%)'},ticks:{callback:v=>v+' %'}}}}});
    el('weatherTitle').textContent=selected+' – andel observationer per år';
    el('weatherHint').textContent='Andel av samtliga väderobservationer det året som tillhör vald vädertyp.';
  }
}
function aggregateMonthlyMean(rows,key='avg'){return [...Array(12)].map((_,i)=>{const a=rows.filter(r=>r.month===i+1).map(r=>r[key]).filter(v=>v!=null);return a.length?a.reduce((s,v)=>s+v,0)/a.length:null;});}
function linearRegression(xs,ys){
  const pts=xs.map((x,i)=>[+x,ys[i]]).filter(p=>Number.isFinite(p[0])&&p[1]!=null&&Number.isFinite(p[1]));
  if(pts.length<2)return null;
  const xm=pts.reduce((s,p)=>s+p[0],0)/pts.length,ym=pts.reduce((s,p)=>s+p[1],0)/pts.length;
  const den=pts.reduce((s,p)=>s+(p[0]-xm)*(p[0]-xm),0);
  if(!den)return null;
  const slope=pts.reduce((s,p)=>s+(p[0]-xm)*(p[1]-ym),0)/den,intercept=ym-slope*xm;
  return {slope,intercept};
}
function linearTrend(xs,ys){
  const reg=linearRegression(xs,ys);
  return reg?xs.map(x=>reg.slope*(+x)+reg.intercept):ys.map(()=>null);
}
function trendRateText(xs,ys,unit,startLabel=null,endLabel=null){
  const reg=linearRegression(xs,ys);
  const valid=xs.map((x,i)=>({x:+x,y:ys[i],label:String(x)})).filter(p=>Number.isFinite(p.x)&&p.y!=null&&Number.isFinite(p.y));
  if(!reg||valid.length<2)return 'För få datapunkter för linjär trend.';
  const per10=reg.slope*10;
  const n=Math.abs(per10);
  const decimals=n>=100?0:n>=10?1:2;
  const value=(per10>=0?'+':'')+per10.toLocaleString('sv-SE',{minimumFractionDigits:decimals,maximumFractionDigits:decimals});
  const from=startLabel??valid[0].label,to=endLabel??valid[valid.length-1].label;
  return 'Från '+from+' till '+to+': '+value+' '+unit+' per 10 år (historisk linjär trend).';
}
function selectedAnnualRows(annualRows,monthlyRows,f){
  if(!f.month)return annualRows.filter(r=>inYears(r,f));
  return monthlyRows.filter(r=>inYears(r,f)&&r.month===f.month);
}
function precipTypeShares(rows,groupKey){
  const groups={};
  rows.forEach(r=>{
    const k=groupKey(r);
    if(!groups[k])groups[k]={rain:0,mixed:0,snow:0};
    groups[k][r.type]=(groups[k][r.type]||0)+r.count;
  });
  return Object.keys(groups).sort((a,b)=>+a-+b).map(k=>{
    const g=groups[k],tot=g.rain+g.mixed+g.snow;
    return {key:k,rain:tot?100*g.rain/tot:0,mixed:tot?100*g.mixed/tot:0,snow:tot?100*g.snow/tot:0};
  });
}
function renderPrecipTypeChart(id,labels,rows){
  destroyChart(id);
  const datasets=[
    {label:'Regn',data:rows.map(r=>r.rain),stack:'type',backgroundColor:'rgba(54,162,235,0.55)',borderWidth:0},
    {label:'Snöblandat regn',data:rows.map(r=>r.mixed),stack:'type',backgroundColor:'rgba(255,99,132,0.45)',borderWidth:0},
    {label:'Snö',data:rows.map(r=>r.snow),stack:'type',backgroundColor:'rgba(255,159,64,0.55)',borderWidth:0}
  ];
  charts[id]=new Chart(el(id),{type:'bar',data:{labels,datasets},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
    plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+c.parsed.y.toFixed(1).replace('.',',')+' %'}}},
    scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,min:0,max:100,title:{display:true,text:'andel (%)'},ticks:{callback:v=>v+' %'}}}}});
}

function dayOfYearLabel(doy){
  const d=new Date(Date.UTC(2001,0,1));
  d.setUTCDate(doy);
  return d.toLocaleDateString('sv-SE',{day:'numeric',month:'short',timeZone:'UTC'}).replace('.','');
}
function renderVegetation(f){
  if(!DATA.vegetation)return;
  const climate=(DATA.vegetation.climate_10y||[]).filter(r=>r.window_end>=f.from&&r.window_end<=f.to);
  const labels=climate.map(r=>r.window_end);
  const lengthVals=climate.map(r=>r.length_days);

  destroyChart('vegetationLength');
  charts.vegetationLength=new Chart(el('vegetationLength'),{
    data:{labels,datasets:[
      {type:'bar',label:'Längd',data:lengthVals,borderWidth:0},
      {type:'line',label:'Linjär trend',data:linearTrend(labels,lengthVals),borderColor:'#ff6384',backgroundColor:'rgba(255,99,132,0.35)',borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{title:items=>'10-årsperiod t.o.m. '+items[0].label,label:c=>c.dataset.label+': '+Math.round(c.parsed.y)+' dygn'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:false,title:{display:true,text:'dygn'}}}}
  });
  el('vegetationLengthTrendText').textContent=trendRateText(labels,lengthVals,'dygn');

  const startVals=climate.map(r=>r.start_doy);
  el('vegetationStartTrendText').textContent=trendRateText(labels,startVals,'dygn');
  destroyChart('vegetationStart');
  charts.vegetationStart=new Chart(el('vegetationStart'),{
    data:{labels,datasets:[
      {type:'bar',label:'Start',data:startVals,backgroundColor:'rgba(230,126,34,0.42)',borderWidth:0},
      {type:'line',label:'Linjär trend',data:linearTrend(labels,startVals),borderColor:'#ff6384',backgroundColor:'rgba(255,99,132,0.35)',borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{title:items=>'10-årsperiod t.o.m. '+items[0].label,label:c=>c.dataset.label==='Start'?'Start: '+dayOfYearLabel(c.parsed.y):'Trend: '+dayOfYearLabel(c.parsed.y)}}},
      scales:{x:{grid:{display:false}},y:{title:{display:true,text:'datum'},ticks:{callback:v=>dayOfYearLabel(v)}}}}
  });

  const endVals=climate.map(r=>r.end_doy);
  el('vegetationEndTrendText').textContent=trendRateText(labels,endVals,'dygn');
  destroyChart('vegetationEnd');
  charts.vegetationEnd=new Chart(el('vegetationEnd'),{
    data:{labels,datasets:[
      {type:'bar',label:'Slut',data:endVals,backgroundColor:'rgba(46,139,87,0.40)',borderWidth:0},
      {type:'line',label:'Linjär trend',data:linearTrend(labels,endVals),borderColor:'#ff6384',backgroundColor:'rgba(255,99,132,0.35)',borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{title:items=>'10-årsperiod t.o.m. '+items[0].label,label:c=>c.dataset.label==='Slut'?'Slut: '+dayOfYearLabel(c.parsed.y):'Trend: '+dayOfYearLabel(c.parsed.y)}}},
      scales:{x:{grid:{display:false}},y:{title:{display:true,text:'datum'},ticks:{callback:v=>dayOfYearLabel(v)}}}}
  });

  const frost=climate.filter(r=>r.frost_days!=null);
  el('vegetationFrostTrendText').textContent=trendRateText(frost.map(r=>r.window_end),frost.map(r=>r.frost_days),'dygn');
  destroyChart('vegetationFrost');
  charts.vegetationFrost=new Chart(el('vegetationFrost'),{
    data:{labels:frost.map(r=>r.window_end),datasets:[
      {type:'bar',label:'Frostnätter',data:frost.map(r=>r.frost_days),backgroundColor:'#6b8fb3',borderWidth:0},
      {type:'line',label:'Linjär trend',data:linearTrend(frost.map(r=>r.window_end),frost.map(r=>r.frost_days)),borderColor:'#ff6384',backgroundColor:'rgba(255,99,132,0.35)',borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{title:items=>'År '+items[0].label,label:c=>c.dataset.label+': '+Math.round(c.parsed.y)+' dygn'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'dygn'}}}}
  });

}

function daylightHoursForDate(dateStr){
  const s=solarTimes(dateStr);
  if(s.polarDay)return 24;
  if(s.polarNight)return 0;
  if(s.sunriseMinutes==null||s.sunsetMinutes==null)return null;
  let mins=s.sunsetMinutes-s.sunriseMinutes;
  if(mins<0)mins+=1440;
  return mins/60;
}
function daylightHoursInMonth(year,month){
  const days=new Date(Date.UTC(year,month,0)).getUTCDate();
  let total=0,valid=0;
  for(let d=1;d<=days;d++){
    const dateStr=year+'-'+String(month).padStart(2,'0')+'-'+String(d).padStart(2,'0');
    const h=daylightHoursForDate(dateStr);
    if(h!=null&&Number.isFinite(h)){total+=h;valid++;}
  }
  return valid===days?total:null;
}

async function loadLightningMapIndex(){
  if(lightningMapIndex)return lightningMapIndex;
  const r=await fetch('lightning_map/index.json?v=2',{cache:'no-store'});
  if(!r.ok)throw new Error('Blixtkartan väntar på första kartbygget.');
  lightningMapIndex=await r.json();
  return lightningMapIndex;
}

async function loadLightningMapYear(year){
  const key=Number(year);
  if(!Number.isFinite(key))throw new Error('Ogiltigt blixtår.');
  if(lightningMapCache.has(key))return lightningMapCache.get(key);
  const idx=await loadLightningMapIndex();
  const meta=(idx.years||[]).find(x=>Number(x.year)===key);
  if(!meta)throw new Error('Blixtkartan saknar data för '+key+'.');
  const r=await fetch('lightning_map/'+meta.file+'?v=2',{cache:'no-store'});
  if(!r.ok)throw new Error('Blixtkartan saknar data för '+key+'.');
  const data=await r.json();
  lightningMapCache.set(key,data);
  return data;
}

async function loadLightningMapRange(from,to){
  const idx=await loadLightningMapIndex();
  const years=(idx.years||[]).map(x=>Number(x.year)).filter(y=>y>=from&&y<=to).sort((a,b)=>a-b);
  if(!years.length)throw new Error('Inga blixtår finns i valt intervall.');
  const data=await Promise.all(years.map(loadLightningMapYear));
  return {years,data};
}

function lightningSurfaceLabel(s){
  return {mainland:'Fastland',islands:'Öar',sea:'Hav',inland_water:'Inlandsvatten',uncertain:'Osäkert område'}[s]||s;
}

function lightningGridCount(cell,surface,month){
  if(surface==='all'){
    return month ? Number(cell.by_month?.[String(month)]||0) : Number(cell.count||0);
  }
  if(month){
    return Number(cell.by_surface_month?.[surface]?.[String(month)]||0);
  }
  return Number(cell.by_surface?.[surface]||0);
}

function lightningHexToRgb(hex){
  const h=hex.replace('#','');
  return [parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16)];
}
function lightningMixColor(a,b,t){
  const x=lightningHexToRgb(a),y=lightningHexToRgb(b);
  const c=x.map((v,i)=>Math.round(v+(y[i]-v)*Math.max(0,Math.min(1,t))));
  return '#'+c.map(v=>v.toString(16).padStart(2,'0')).join('');
}
function lightningDensityColor(v,max){
  if(v<=0)return 'rgba(0,0,0,0)';
  const p=Math.max(0,Math.min(1,max>0?v/max:0));
  return p<=0.5
    ? lightningMixColor('#bfdbfe','#facc15',p/0.5)
    : lightningMixColor('#facc15','#dc2626',(p-0.5)/0.5);
}

async function renderLightningMapLayer(filterOverride=null){
  if(!lightningMapLeaflet)return;
  if(lightningMapLayer)lightningMapLeaflet.removeLayer(lightningMapLayer);
  lightningMapLayer=L.layerGroup();

  const mode=el('lightningMapMode')?.value||'grid2000';
  const surface=el('lightningMapSurface')?.value||'all';
  const status=el('lightningMapStatus');
  const f=filterOverride||currentFilters();

  if(mode==='none'){
    if(status)status.textContent='Blixtlagret är avstängt.';
    return;
  }

  if(status)status.textContent='Laddar blixtdata för valt filter…';

  try{
    const range=await loadLightningMapRange(f.from,f.to);
    const month=Number(f.month)||0;
    const monthLabel=month?months[month-1]:'alla månader';

    if(mode==='points'){
      const pts=[];
      range.data.forEach(data=>{
        (data.points||[]).forEach(p=>{
          if(month&&Number(p.month)!==month)return;
          if(surface!=='all'&&p.surface!==surface)return;
          pts.push(p);
        });
      });
      pts.forEach(p=>{
        const m=L.circleMarker([p.lat,p.lon],{
          radius:3,color:'#111827',weight:.4,fillColor:'#f59e0b',fillOpacity:.72
        });
        const current=p.current_ka==null?'okänd':Number(p.current_ka).toLocaleString('sv-SE',{maximumFractionDigits:1})+' kA';
        m.bindPopup((p.datetime_utc||'')+'<br>'+lightningSurfaceLabel(p.surface)+'<br>Strömstyrka: '+current);
        m.addTo(lightningMapLayer);
      });
      lightningMapLayer.addTo(lightningMapLeaflet);
      if(status)status.textContent=f.from+'–'+f.to+' · '+monthLabel+': '+pts.length.toLocaleString('sv-SE')+' registrerade urladdningar'+(surface==='all'?'.':' · '+lightningSurfaceLabel(surface)+'.');
      return;
    }

    const gridSize=mode==='grid1000'?1000:mode==='grid4000'?4000:2000;
    const aggregated=new Map();
    range.data.forEach(data=>{
      const grid=(data.grids?.[String(gridSize)]||[]);
      grid.forEach(c=>{
        const n=lightningGridCount(c,surface,month);
        if(n<=0)return;
        const key=String(c.lon)+','+String(c.lat);
        if(!aggregated.has(key))aggregated.set(key,{c,sum:0});
        aggregated.get(key).sum+=n;
      });
    });

    const yearCount=range.years.length;
    const isAverage=yearCount>1;
    const cells=[...aggregated.values()].map(x=>({
      c:x.c,
      n:isAverage?x.sum/yearCount:x.sum
    })).filter(x=>x.n>0);
    const max=Math.max(1,...cells.map(x=>x.n));

    cells.forEach(({c,n})=>{
      const poly=L.polygon(c.polygon.map(x=>[x[1],x[0]]),{
        color:'#aeb8c4',weight:.55,opacity:.82,
        fillColor:lightningDensityColor(n,max),fillOpacity:.72
      });
      const valueText=isAverage
        ? n.toLocaleString('sv-SE',{maximumFractionDigits:2})+' urladdningar per år'
        : n.toLocaleString('sv-SE',{maximumFractionDigits:0})+' urladdningar';
      const km=gridSize/1000;
      poly.bindPopup('<b>'+km+' × '+km+' km-ruta</b><br>'+valueText+'<br>'+monthLabel+(surface==='all'?'':' · '+lightningSurfaceLabel(surface)));
      poly.addTo(lightningMapLayer);
    });
    lightningMapLayer.addTo(lightningMapLeaflet);

    const total=cells.reduce((s,x)=>s+x.n,0);
    if(status){
      status.textContent=(isAverage?'Medel '+f.from+'–'+f.to:f.from)+' · '+monthLabel+': '+
        total.toLocaleString('sv-SE',{maximumFractionDigits:isAverage?1:0})+
        (isAverage?' urladdningar per år i genomsnitt':' urladdningar')+
        ' · '+cells.length.toLocaleString('sv-SE')+' belagda '+(gridSize/1000)+' × '+(gridSize/1000)+' km-rutor'+
        (surface==='all'?'.':' · '+lightningSurfaceLabel(surface)+'.');
    }
  }catch(err){
    if(status)status.textContent=err.message;
  }
}

function setupLightningMapControls(){
  el('lightningMapMode')?.addEventListener('change',()=>renderLightningMapLayer());
  el('lightningMapSurface')?.addEventListener('change',()=>renderLightningMapLayer());
}

async function initLightningMap(){
  const mapEl=el('lightningMap');
  if(!mapEl||typeof L==='undefined')return;
  const status=el('lightningMapStatus');
  if(lightningMapLeaflet){
    setTimeout(()=>lightningMapLeaflet.invalidateSize(),50);
    return;
  }
  try{
    if(status)status.textContent='Laddar blixtkartan…';
    lightningMapLeaflet=L.map(mapEl,{zoomControl:true});
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
      maxZoom:18,attribution:'&copy; OpenStreetMap contributors'
    }).addTo(lightningMapLeaflet);

    const br=await fetch('lightning_map/boundary.geojson?v=1',{cache:'no-store'});
    if(br.ok){
      const boundary=await br.json();
      lightningMapBoundary=L.geoJSON(boundary,{style:{color:'#dc2626',weight:2.4,fill:false}}).addTo(lightningMapLeaflet);
      const b=lightningMapBoundary.getBounds();if(b.isValid())lightningMapLeaflet.fitBounds(b.pad(.04));
    }

    const legend=L.control({position:'topright'});
    legend.onAdd=()=>{
      const div=L.DomUtil.create('div','seaice-map-legend');
      div.innerHTML='<b>Blixtar per rutnätscell</b>'+
        '<div style="margin:5px 0 2px;width:118px;height:12px;border-radius:2px;background:linear-gradient(90deg,#bfdbfe 0%,#facc15 50%,#dc2626 100%)"></div>'+
        '<div style="display:flex;justify-content:space-between;width:118px;font-size:11px"><span>Låg</span><span>Medel</span><span>Hög</span></div>'+
        '<div style="margin-top:5px"><i style="background:transparent;border:2px solid #dc2626"></i>Luleå kommun</div>';
      return div;
    };
    legend.addTo(lightningMapLeaflet);

    await loadLightningMapIndex();
    await renderLightningMapLayer();
  }catch(err){
    if(status)status.textContent=err.message;
  }
}

function renderLightning(f){
  if(lightningMapLeaflet)renderLightningMapLayer(f);
  const L=DATA.lightning||{};
  const has=(L.annual||[]).length>0;
  const noData=el('lightningNoData');
  if(noData)noData.style.display=has?'none':'block';
  ['lightningAnnual','lightningDays','lightningMonthly','lightningUncertain'].forEach(id=>{
    const canvas=el(id);if(canvas)canvas.parentElement.style.display=has?'block':'none';
    if(!has)destroyChart(id);
  });
  if(!has)return;

  const classes=[
    {key:'mainland',label:'Fastland',color:'rgba(79,157,105,0.68)'},
    {key:'islands',label:'Öar',color:'rgba(242,201,76,0.68)'},
    {key:'sea',label:'Hav',color:'rgba(54,162,235,0.62)'},
    {key:'inland_water',label:'Inlandsvatten',color:'rgba(125,187,214,0.52)'}
  ];
  const annualClasses=[
    ...classes,
    {key:'uncertain_area_500',label:'Osäkert område',color:'rgba(156,163,175,0.72)'}
  ];
  const annualSource=f.month?(L.monthly_by_year||[]).filter(r=>r.month===f.month):(L.annual||[]);
  const rows=annualSource.filter(r=>r.year>=f.from&&r.year<=f.to).sort((a,b)=>a.year-b.year);
  const years=rows.map(r=>r.year);

  destroyChart('lightningAnnual');
  charts.lightningAnnual=new Chart(el('lightningAnnual'),{
    type:'bar',
    data:{labels:years,datasets:annualClasses.map(x=>({label:x.label,stack:'surface',backgroundColor:x.color,borderWidth:0,data:rows.map(r=>{
      const uncertain=r.uncertain_area_500||0;
      if(x.key==='uncertain_area_500')return uncertain;
      const bySurface=r.uncertain_by_surface||{};
      return Math.max(0,(r[x.key]||0)-(bySurface[x.key]||0));
    })}))},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+Math.round(c.parsed.y)}}},
      scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,beginAtZero:true,title:{display:true,text:'urladdningar'},ticks:{precision:0}}}}
  });

  const dayVals=rows.map(r=>r.lightning_days||0);
  destroyChart('lightningDays');
  charts.lightningDays=new Chart(el('lightningDays'),{
    data:{labels:years,datasets:[
      {type:'bar',label:'Blixtdygn',data:dayVals,backgroundColor:'rgba(99,102,241,0.58)',borderWidth:0},
      {type:'line',label:'Linjär trend',data:linearTrend(years,dayVals),borderColor:'#ff6384',backgroundColor:'rgba(255,99,132,0.35)',borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+Number(c.parsed.y).toLocaleString('sv-SE',{maximumFractionDigits:1})+' dygn'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'dygn'},ticks:{precision:0}}}}
  });
  if(el('lightningDaysTrendText'))el('lightningDaysTrendText').textContent=trendRateText(years,dayVals,'dygn');

  const monthRows=(L.monthly_by_year||[]).filter(r=>r.year>=f.from&&r.year<=f.to);
  const monthAgg=months.map((_,i)=>{
    const rr=monthRows.filter(r=>r.month===i+1);
    const yearsN=new Set(rr.map(r=>r.year)).size||1;
    const out={};
    annualClasses.forEach(x=>{
      if(x.key==='uncertain_area_500'){
        out[x.key]=rr.reduce((s,r)=>s+(r.uncertain_area_500||0),0)/yearsN;
      }else{
        out[x.key]=rr.reduce((s,r)=>{
          const bySurface=r.uncertain_by_surface||{};
          return s+Math.max(0,(r[x.key]||0)-(bySurface[x.key]||0));
        },0)/yearsN;
      }
    });
    return out;
  });
  destroyChart('lightningMonthly');
  charts.lightningMonthly=new Chart(el('lightningMonthly'),{
    type:'bar',
    data:{labels:months,datasets:annualClasses.map(x=>({label:x.label,stack:'surface',backgroundColor:x.color,borderWidth:0,data:monthAgg.map(r=>r[x.key]||0)}))},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+c.parsed.y.toFixed(1).replace('.',',')}}},
      scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,beginAtZero:true,title:{display:true,text:'genomsnitt per år'}}}}
  });

  const uncertaintyTypes=[
    {key:'mainland__sea',label:'Fastland ↔ hav',color:'#2563eb'},
    {key:'islands__sea',label:'Öar ↔ hav',color:'#f59e0b'},
    {key:'inland_water__mainland',label:'Fastland ↔ inlandsvatten',color:'#16a34a'},
    {key:'inland_water__islands',label:'Öar ↔ inlandsvatten',color:'#a855f7'},
    {key:'inland_water__sea',label:'Hav ↔ inlandsvatten',color:'#06b6d4'},
    {key:'islands__mainland',label:'Fastland ↔ öar',color:'#ec4899'}
  ];
  const visibleTypes=uncertaintyTypes.filter(t=>rows.some(r=>((r.uncertainty_pairs||{})[t.key]||0)>0));
  const uncertaintyDatasets=visibleTypes.map(t=>({
    label:t.label,
    stack:'uncertainty',
    backgroundColor:t.color,
    borderWidth:0,
    data:rows.map(r=>((r.uncertainty_pairs||{})[t.key]||0))
  }));
  uncertaintyDatasets.push({
    label:'Kommungräns',
    stack:'uncertainty',
    backgroundColor:'#374151',
    borderWidth:0,
    data:rows.map(r=>r.municipality_boundary_uncertain_500||0)
  });
  destroyChart('lightningUncertain');
  charts.lightningUncertain=new Chart(el('lightningUncertain'),{
    type:'bar',
    data:{labels:years,datasets:uncertaintyDatasets},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+Math.round(c.parsed.y)}}},
      scales:{
        x:{stacked:true,grid:{display:false}},
        y:{stacked:true,beginAtZero:true,title:{display:true,text:'urladdningar'},ticks:{precision:0}}
      }}
  });
}

function seaIceTypeColor(t){
  if(t===8)return '#a78bfa';
  if(t>=6)return '#60a5fa';
  if(t>=4)return '#93c5fd';
  return '#bfdbfe';
}

function formatSeaIceMapDate(iso){
  const d=new Date(iso+'T12:00:00Z');
  return d.toLocaleDateString('sv-SE',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
}

async function loadSeaIceSeasonManifest(){
  if(seaIceSeasonManifest)return seaIceSeasonManifest;
  const status=el('seaIceSeasonStatus');
  try{
    const r=await fetch('seaice/2023-24/manifest.json?v=1',{cache:'no-store'});
    if(!r.ok)throw new Error('Säsongskartan är ännu inte genererad. Kör workflowet i auto-läge en gång.');
    seaIceSeasonManifest=await r.json();
    const dates=seaIceSeasonManifest.dates||[];
    const slider=el('seaIceSeasonSlider');
    if(!slider||!dates.length)throw new Error('Inga kartdatum hittades för issäsong 2023/24.');
    slider.min=0;
    slider.max=String(dates.length-1);
    const preferred=Math.max(0,dates.findIndex(x=>x.date==='2023-12-14'));
    slider.value=String(preferred>=0?preferred:0);
    slider.disabled=false;
    el('seaIcePrevDate').disabled=false;
    el('seaIceNextDate').disabled=false;
    updateSeaIceSeasonDateLabel();
    if(status)status.textContent='Välj datum med reglaget. Endast den valda dagens ispolygoner laddas.';
    return seaIceSeasonManifest;
  }catch(err){
    if(status)status.textContent=err.message;
    throw err;
  }
}

function updateSeaIceSeasonDateLabel(){
  const dates=seaIceSeasonManifest?.dates||[];
  const slider=el('seaIceSeasonSlider');
  if(!slider||!dates.length)return;
  const item=dates[Number(slider.value)];
  if(!item)return;
  const label=el('seaIceSeasonDateLabel');
  if(label)label.textContent=formatSeaIceMapDate(item.date);
}

async function showSeaIceSeasonDate(index){
  if(!seaIceLeafletMap)return;
  const manifest=await loadSeaIceSeasonManifest();
  const dates=manifest.dates||[];
  if(!dates.length)return;
  const safe=Math.max(0,Math.min(dates.length-1,Number(index)||0));
  const slider=el('seaIceSeasonSlider');
  slider.value=String(safe);
  updateSeaIceSeasonDateLabel();
  const item=dates[safe];
  const status=el('seaIceSeasonStatus');
  if(status)status.textContent='Laddar '+formatSeaIceMapDate(item.date)+'…';
  const started=performance.now();

  try{
    let geo=seaIceSeasonCache.get(item.date);
    let kb=null;
    if(!geo){
      const r=await fetch('seaice/2023-24/'+item.file+'?v=1',{cache:'no-store'});
      if(!r.ok)throw new Error('Kartfil saknas för '+item.date+'.');
      const textData=await r.text();
      kb=Math.round(new Blob([textData]).size/1024);
      geo=JSON.parse(textData);
      seaIceSeasonCache.set(item.date,geo);
    }

    if(seaIceSeasonLayer)seaIceLeafletMap.removeLayer(seaIceSeasonLayer);
    seaIceSeasonLayer=L.geoJSON(geo,{
      style:f=>({
        color:'#334155',
        weight:1,
        fillColor:seaIceTypeColor(Number(f?.properties?.ice_type)),
        fillOpacity:.62
      }),
      onEachFeature:(f,layer)=>{
        const p=f.properties||{};
        const rows=[
          p.ice_type_name?'Istyp: '+p.ice_type_name:null,
          p.iceact?'Koncentration: '+p.iceact:null,
          p.mean_thickness_cm!=null?'Medeltjocklek: '+p.mean_thickness_cm+' cm':null,
          p.max_thickness_cm!=null?'Maximal tjocklek: '+p.max_thickness_cm+' cm':null
        ].filter(Boolean);
        if(rows.length)layer.bindPopup(rows.join('<br>'));
      }
    }).addTo(seaIceLeafletMap);

    const ms=Math.round(performance.now()-started);
    const count=(geo.features||[]).length;
    const bits=[
      formatSeaIceMapDate(item.date)+': '+count+' ispolygoner',
      item.ice_share_pct!=null?'isutbredning '+Number(item.ice_share_pct).toLocaleString('sv-SE',{maximumFractionDigits:4})+' %':null,
      item.mean_ice_thickness_cm!=null?'medeltjocklek '+Number(item.mean_ice_thickness_cm).toLocaleString('sv-SE')+' cm':null,
      item.max_ice_thickness_cm!=null?'max '+Number(item.max_ice_thickness_cm).toLocaleString('sv-SE')+' cm':null,
      kb!=null?kb+' kB':null,
      ms+' ms'
    ].filter(Boolean);
    if(status)status.textContent=bits.join(' · ');
  }catch(err){
    if(status)status.textContent=err.message;
  }
}

function algaeClassColor(name){
  if(name==='surface')return '#16a34a';
  if(name==='risk')return '#facc15';
  if(name==='cloud')return '#9ca3af';
  if(name==='no_data')return '#111827';
  return '#60a5fa';
}

function algaeClassLabel(name){
  const labels={
    surface:'Ytansamling',
    risk:'Risk för ytansamling',
    cloud:'Moln',
    no_data:'Data saknas'
  };
  if(labels[name])return labels[name];
  const m=String(name||'').match(/^class_(.+)$/);
  return m?'SMHI klass '+m[1]:(name||'Övrigt');
}

function algaeClassRows(manifest){
  const dates=manifest?.dates||[];
  const keys=new Set();
  dates.forEach(r=>{
    const raw=r.classes_pct_sea||{};
    Object.keys(raw).forEach(k=>keys.add(k));
    if(!Object.keys(raw).length){
      if((r.surface_pct_sea||0)>0)keys.add('surface');
      if((r.risk_pct_sea||0)>0)keys.add('risk');
      if((r.cloud_pct_sea||0)>0)keys.add('cloud');
      if((r.no_data_pct_sea||0)>0)keys.add('no_data');
    }
  });
  const order=['surface','risk','cloud','no_data'];
  return [...keys].sort((a,b)=>{
    const ai=order.indexOf(a),bi=order.indexOf(b);
    if(ai>=0||bi>=0)return (ai<0?999:ai)-(bi<0?999:bi);
    return String(a).localeCompare(String(b),'sv');
  });
}

function algaePct(row,key){
  if(row?.classes_pct_sea&&row.classes_pct_sea[key]!=null)return Number(row.classes_pct_sea[key])||0;
  const fallback={surface:'surface_pct_sea',risk:'risk_pct_sea',cloud:'cloud_pct_sea',no_data:'no_data_pct_sea'};
  return fallback[key]&&row?.[fallback[key]]!=null?Number(row[fallback[key]])||0:0;
}

function renderAlgaeCharts(manifest){
  const rows=manifest?.dates||[];
  const keys=algaeClassRows(manifest);
  if(!el('algaeDailyClasses')||!el('algaeClassDays'))return;

  destroyChart('algaeDailyClasses');
  destroyChart('algaeClassDays');

  if(!rows.length||!keys.length){
    const msg='Klassarealer saknas i nuvarande manifest. Nästa algkörning fyller på dem från de redan sparade kartfilerna.';
    const a=el('algaeDailyClasses')?.parentElement?.querySelector('.hint');
    const b=el('algaeClassDays')?.parentElement?.querySelector('.hint');
    if(a)a.textContent=msg;
    if(b)b.textContent=msg;
    return;
  }

  charts.algaeDailyClasses=new Chart(el('algaeDailyClasses'),{
    type:'bar',
    data:{
      labels:rows.map(r=>r.date),
      datasets:keys.map(k=>({
        label:algaeClassLabel(k),
        data:rows.map(r=>algaePct(r,k)),
        backgroundColor:algaeClassColor(k),
        borderWidth:0,
        stack:'algae'
      }))
    },
    options:{
      responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+c.parsed.y.toLocaleString('sv-SE',{maximumFractionDigits:2})+' %'}}},
      scales:{
        x:{stacked:true,grid:{display:false},ticks:{autoSkip:true,maxTicksLimit:24,maxRotation:55,minRotation:35}},
        y:{stacked:true,beginAtZero:true,max:100,title:{display:true,text:'andel av kommunal havsyta (%)'},ticks:{callback:v=>v+' %'}}
      }
    }
  });

  const dayCounts=keys.map(k=>rows.reduce((n,r)=>n+(algaePct(r,k)>0?1:0),0));
  charts.algaeClassDays=new Chart(el('algaeClassDays'),{
    type:'bar',
    data:{
      labels:keys.map(algaeClassLabel),
      datasets:[{label:String(manifest.year||''),data:dayCounts,backgroundColor:keys.map(algaeClassColor),borderWidth:0}]
    },
    options:{
      responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.parsed.y+' observationsdagar'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'observationsdagar'},ticks:{precision:0}}}
    }
  });
}

async function loadAlgaeHistoryIndex(){
  if(algaeHistoryIndex)return algaeHistoryIndex;
  const r=await fetch('algae/index.json?v=1',{cache:'no-store'});
  if(!r.ok){
    const current=new Date().getUTCMonth()+1>=6?new Date().getUTCFullYear():new Date().getUTCFullYear()-1;
    algaeHistoryIndex={years:[{year:current}]};
    return algaeHistoryIndex;
  }
  algaeHistoryIndex=await r.json();
  const select=el('algaeYear');
  if(select){
    const years=(algaeHistoryIndex.years||[]).map(x=>Number(x.year)).filter(Number.isFinite).sort((a,b)=>b-a);
    select.innerHTML=years.map(y=>'<option value="'+y+'">'+y+(y<=2009?' · äldre klassning':'')+'</option>').join('');
  }
  return algaeHistoryIndex;
}

async function loadAlgaeSeasonManifest(year=null,force=false){
  const status=el('algaeSeasonStatus');
  try{
    const idx=await loadAlgaeHistoryIndex();
    const available=(idx.years||[]).map(x=>Number(x.year)).filter(Number.isFinite).sort((a,b)=>b-a);
    if(year==null){
      const selected=Number(el('algaeYear')?.value);
      year=Number.isFinite(selected)&&selected?selected:(available[0]||new Date().getUTCFullYear());
    }
    if(!force&&algaeSeasonManifest&&Number(algaeSeasonManifest.year)===Number(year))return algaeSeasonManifest;

    const r=await fetch('algae/'+year+'/manifest.json?v=1',{cache:'no-store'});
    if(!r.ok)throw new Error('Ingen algsäsong hittades för '+year+'.');
    algaeSeasonManifest=await r.json();
    if(el('algaeYear'))el('algaeYear').value=String(year);
    renderAlgaeCharts(algaeSeasonManifest);

    const dates=algaeSeasonManifest.dates||[];
    const slider=el('algaeSeasonSlider');
    if(!slider||!dates.length)throw new Error('Inga algkartdatum hittades för '+year+'.');
    slider.min=0;
    slider.max=String(dates.length-1);
    slider.value=String(dates.length-1);
    slider.disabled=false;
    el('algaePrevDate').disabled=false;
    el('algaeNextDate').disabled=false;
    if(el('algaeSeasonLabel'))el('algaeSeasonLabel').textContent='Algsäsong '+year;
    updateAlgaeSeasonDateLabel();

    const legacy=algaeSeasonManifest.legacy_classification||Number(year)<=2009;
    if(status)status.textContent=legacy
      ? 'Äldre SMHI-klassning (2002–2009). Råa klasser visas där säker översättning saknas.'
      : 'Välj datum med reglaget. Endast vald dags polygoner laddas.';
    return algaeSeasonManifest;
  }catch(err){
    if(status)status.textContent=err.message;
    throw err;
  }
}

function updateAlgaeSeasonDateLabel(){
  const dates=algaeSeasonManifest?.dates||[];
  const slider=el('algaeSeasonSlider');
  if(!slider||!dates.length)return;
  const item=dates[Number(slider.value)];
  if(!item)return;
  const label=el('algaeSeasonDateLabel');
  if(label)label.textContent=formatSeaIceMapDate(item.date);
}

async function showAlgaeSeasonDate(index){
  if(!algaeLeafletMap)return;
  const manifest=await loadAlgaeSeasonManifest();
  const dates=manifest.dates||[];
  if(!dates.length)return;
  const safe=Math.max(0,Math.min(dates.length-1,Number(index)||0));
  const slider=el('algaeSeasonSlider');
  slider.value=String(safe);
  updateAlgaeSeasonDateLabel();
  const item=dates[safe];
  const status=el('algaeSeasonStatus');
  if(status)status.textContent='Laddar '+formatSeaIceMapDate(item.date)+'…';
  const started=performance.now();

  try{
    let geo=algaeSeasonCache.get(item.date);
    let kb=null;
    if(!geo){
      const r=await fetch('algae/'+manifest.year+'/'+item.file+'?v=1',{cache:'no-store'});
      if(!r.ok)throw new Error('Kartfil saknas för '+item.date+'.');
      const textData=await r.text();
      kb=Math.round(new Blob([textData]).size/1024);
      geo=JSON.parse(textData);
      algaeSeasonCache.set(item.date,geo);
    }

    if(algaeSeasonLayer)algaeLeafletMap.removeLayer(algaeSeasonLayer);
    algaeSeasonLayer=L.geoJSON(geo,{
      style:f=>({
        color:'#334155',
        weight:.7,
        fillColor:algaeClassColor(f?.properties?.algae_class),
        fillOpacity:.62
      }),
      onEachFeature:(f,layer)=>{
        const p=f.properties||{};
        const names={surface:'Ytansamling',risk:'Risk för ytansamling',cloud:'Moln',no_data:'Data saknas'};
        const rows=[
          'Klass: '+(names[p.algae_class]||algaeClassLabel(p.algae_class)||'Övrigt'),
          p.date?'Datum: '+p.date:null
        ].filter(Boolean);
        layer.bindPopup(rows.join('<br>'));
      }
    }).addTo(algaeLeafletMap);

    const ms=Math.round(performance.now()-started);
    const bits=[
      formatSeaIceMapDate(item.date)+': '+(geo.features||[]).length+' polygoner',
      item.surface_pct_sea!=null?'ytansamling '+Number(item.surface_pct_sea).toLocaleString('sv-SE',{maximumFractionDigits:2})+' %':null,
      item.risk_pct_sea!=null?'risk '+Number(item.risk_pct_sea).toLocaleString('sv-SE',{maximumFractionDigits:2})+' %':null,
      item.cloud_pct_sea!=null?'moln '+Number(item.cloud_pct_sea).toLocaleString('sv-SE',{maximumFractionDigits:2})+' %':null,
      kb!=null?kb+' kB':null,
      ms+' ms'
    ].filter(Boolean);
    if(status)status.textContent=bits.join(' · ');
  }catch(err){
    if(status)status.textContent=err.message;
  }
}

function setupAlgaeSeasonControls(){
  const slider=el('algaeSeasonSlider');
  if(!slider)return;
  slider.addEventListener('input',()=>{
    updateAlgaeSeasonDateLabel();
    clearTimeout(algaeSeasonTimer);
    algaeSeasonTimer=setTimeout(()=>showAlgaeSeasonDate(slider.value),180);
  });
  el('algaePrevDate')?.addEventListener('click',()=>showAlgaeSeasonDate(Number(slider.value)-1));
  el('algaeNextDate')?.addEventListener('click',()=>showAlgaeSeasonDate(Number(slider.value)+1));
  el('algaeYear')?.addEventListener('change',async e=>{
    const year=Number(e.target.value);
    if(algaeSeasonLayer&&algaeLeafletMap){
      algaeLeafletMap.removeLayer(algaeSeasonLayer);
      algaeSeasonLayer=null;
    }
    await loadAlgaeSeasonManifest(year,true);
    await showAlgaeSeasonDate(el('algaeSeasonSlider')?.value||0);
  });
}

async function initAlgaeMap(){
  const mapEl=el('algaeMap');
  if(!mapEl||typeof L==='undefined')return;
  const status=el('algaeMapStatus');
  if(algaeLeafletMap){
    setTimeout(()=>algaeLeafletMap.invalidateSize(),50);
    return;
  }
  if(status)status.textContent='Laddar Luleås havsgeometri…';
  try{
    const r=await fetch('seaice_analysis_area.geojson?v=1',{cache:'no-store'});
    if(!r.ok)throw new Error('Luleås havsgeometri saknas.');
    const geo=await r.json();

    algaeLeafletMap=L.map(mapEl,{zoomControl:true});
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
      maxZoom:18,
      attribution:'&copy; OpenStreetMap contributors'
    }).addTo(algaeLeafletMap);

    const municipal=L.geoJSON(geo,{
      filter:f=>f?.properties?.kind==='municipal_sea',
      style:{color:'#dc2626',weight:2.5,fill:false,fillOpacity:0}
    }).addTo(algaeLeafletMap);
    const bounds=municipal.getBounds();
    if(bounds.isValid())algaeLeafletMap.fitBounds(bounds.pad(.03));

    const legend=L.control({position:'topright'});
    legend.onAdd=()=>{
      const div=L.DomUtil.create('div','seaice-map-legend');
      div.innerHTML=
        '<div><i style="background:#16a34a"></i>Ytansamling</div>'+
        '<div><i style="background:#facc15"></i>Risk för ytansamling</div>'+
        '<div><i style="background:#9ca3af"></i>Moln</div>'+
        '<div><i style="background:#111827"></i>Data saknas</div>'+
        '<div><i style="background:transparent;border:2px solid #dc2626"></i>Kommunal havsyta</div>';
      return div;
    };
    legend.addTo(algaeLeafletMap);

    if(status)status.textContent='SMHI:s alganalys klipps mot Luleås kommunala havsyta. Bakgrundskarta: OpenStreetMap.';
    await loadAlgaeSeasonManifest();
    await showAlgaeSeasonDate(el('algaeSeasonSlider')?.value||0);
  }catch(err){
    if(status)status.textContent=err.message;
  }
}

function snowDepthClass(cm){
  const v=Number(cm);
  if(!Number.isFinite(v)||v<1)return {label:'Barmark',color:'#b59b78'};
  if(v<3)return {label:'1–2 cm',color:'#dbeafe'};
  if(v<10)return {label:'3–9 cm',color:'#bfdbfe'};
  if(v<30)return {label:'10–29 cm',color:'#93c5fd'};
  if(v<50)return {label:'30–49 cm',color:'#60a5fa'};
  if(v<75)return {label:'50–74 cm',color:'#3b82f6'};
  if(v<100)return {label:'75–99 cm',color:'#2563eb'};
  if(v<150)return {label:'100–149 cm',color:'#4338ca'};
  if(v<200)return {label:'150–199 cm',color:'#6d28d9'};
  return {label:'200+ cm',color:'#7e22ce'};
}

async function loadSnowMapIndex(){
  if(snowMapIndex)return snowMapIndex;
  const r=await fetch('snowmap/index.json?v=1',{cache:'no-store'});
  if(!r.ok)throw new Error('Stationsdata för snötäckeskartan saknas.');
  snowMapIndex=await r.json();
  return snowMapIndex;
}

async function loadSnowGridIndex(){
  if(snowGridIndex)return snowGridIndex;
  const r=await fetch('snowgrid/index.json?v=1',{cache:'no-store'});
  if(!r.ok)throw new Error('Det analyserade snödjupslagret väntar på första GridClim-körningen.');
  snowGridIndex=await r.json();
  return snowGridIndex;
}

async function loadSnowGridSeries(){
  if(snowGridSeries)return snowGridSeries;
  const r=await fetch('snowgrid/series.json?v=3',{cache:'no-store'});
  if(!r.ok)return null;
  snowGridSeries=await r.json();
  return snowGridSeries;
}

async function loadCopernicusSnowDuration(){
  if(copernicusSnowDuration)return copernicusSnowDuration;
  const r=await fetch('snowgrid/copernicus_scd_series.json?v=1',{cache:'no-store'});
  if(!r.ok)return null;
  copernicusSnowDuration=await r.json();
  return copernicusSnowDuration;
}

function buildSnowGridTimeline(series){
  const labels=[],meanGrid=[],maxGrid=[],coverGrid=[],mainGrid=[];
  const meanRecent=[],maxRecent=[],coverRecent=[],mainRecent=[],seasonKeys=[];
  (series?.seasons||[]).slice().sort((a,b)=>a.season.localeCompare(b.season)).forEach((s,idx,arr)=>{
    const recent=s.source_type==='observations_interpolated';
    const mainlandRows=s.daily_mainland_majority||s.daily_mainland||[];
    const mainlandByDate=new Map(mainlandRows.map(r=>[r.date,r.snow_cover_share_pct]));
    (s.daily||[]).forEach(r=>{
      labels.push(r.date);
      const main=mainlandByDate.has(r.date)?mainlandByDate.get(r.date):null;
      meanGrid.push(recent?null:r.mean_cm); maxGrid.push(recent?null:r.max_cm);
      coverGrid.push(recent?null:r.snow_cover_share_pct); mainGrid.push(recent?null:main);
      meanRecent.push(recent?r.mean_cm:null); maxRecent.push(recent?r.max_cm:null);
      coverRecent.push(recent?r.snow_cover_share_pct:null); mainRecent.push(recent?main:null);
      seasonKeys.push(s.season);
    });
    if(idx<arr.length-1){
      labels.push('');
      meanGrid.push(null);maxGrid.push(null);coverGrid.push(null);mainGrid.push(null);
      meanRecent.push(null);maxRecent.push(null);coverRecent.push(null);mainRecent.push(null);
      seasonKeys.push(null);
    }
  });
  return {labels,meanGrid,maxGrid,coverGrid,mainGrid,meanRecent,maxRecent,coverRecent,mainRecent,seasonKeys};
}

function snowMapSource(){
  return el('snowMapSource')?.value||'grid';
}

async function refreshSnowMapSeasonOptions(){
  const source=snowMapSource();
  const select=el('snowMapSeason');
  if(source==='grid'){
    const idx=await loadSnowGridIndex();
    const seasons=(idx.seasons||[]).slice().sort((a,b)=>b.season.localeCompare(a.season));
    select.innerHTML=seasons.map(s=>{
      const recent=s.source_type==='observations_interpolated';
      const partial=s.last_date && !String(s.last_date).endsWith('-07-31');
      const method=recent?' · interpolerat':' · GridClim';
      return '<option value="'+s.season+'">'+s.season.replace('-', '/')+method+(partial?' · ofullständig':'')+'</option>';
    }).join('');
    if(seasons.length)select.value=seasons[0].season;
  }else{
    const idx=await loadSnowMapIndex();
    const seasons=(idx.seasons||[]).slice().sort((a,b)=>b.season.localeCompare(a.season));
    select.innerHTML=seasons.map(s=>'<option value="'+s.season+'">'+s.season.replace('-', '/')+'</option>').join('');
    if(seasons.length)select.value=seasons[0].season;
  }
}

async function loadSnowGridSeason(season=null,force=false){
  const idx=await loadSnowGridIndex();
  const available=(idx.seasons||[]).slice().sort((a,b)=>b.season.localeCompare(a.season));
  season=season||el('snowMapSeason')?.value||available[0]?.season;
  if(!season)throw new Error('Ingen analyserad snösäsong hittades.');
  if(!force&&snowGridData&&snowGridData.season===season)return snowGridData;
  if(snowGridCache.has(season)){
    const cached=snowGridCache.get(season);
    snowGridData=cached.data;snowGridGeometry=cached.grid;
  }else{
    const meta=available.find(x=>x.season===season);
    const [dr,gr]=await Promise.all([
      fetch('snowgrid/'+(meta?.file||season+'.json')+'?v=1',{cache:'no-store'}),
      fetch('snowgrid/'+(meta?.grid_file||season+'_grid.geojson')+'?v=1',{cache:'no-store'})
    ]);
    if(!dr.ok||!gr.ok)throw new Error('GridClim-data saknas för '+season+'.');
    snowGridData=await dr.json();
    snowGridGeometry=await gr.json();
    snowGridCache.set(season,{data:snowGridData,grid:snowGridGeometry});
  }
  if(el('snowMapSeason'))el('snowMapSeason').value=season;
  if(el('snowMapSeasonLabel'))el('snowMapSeasonLabel').textContent='Snösäsong '+season.replace('-', '/');
  setupSnowMapSlider();
  updateSnowMapCopy();
  await renderSnowMapCharts();
  return snowGridData;
}

async function loadSnowMapSeason(season=null,force=false){
  if(snowMapSource()==='grid')return loadSnowGridSeason(season,force);
  const idx=await loadSnowMapIndex();
  const available=(idx.seasons||[]).slice().sort((a,b)=>b.season.localeCompare(a.season));
  season=season||el('snowMapSeason')?.value||available[0]?.season;
  if(!season)throw new Error('Ingen snösäsong hittades.');
  if(!force&&snowMapSeasonData&&snowMapSeasonData.season===season)return snowMapSeasonData;
  if(snowMapSeasonCache.has(season)){
    snowMapSeasonData=snowMapSeasonCache.get(season);
  }else{
    const meta=available.find(x=>x.season===season);
    const r=await fetch('snowmap/'+(meta?.file||season+'.json')+'?v=1',{cache:'no-store'});
    if(!r.ok)throw new Error('Stationsdata saknas för '+season+'.');
    snowMapSeasonData=await r.json();
    snowMapSeasonCache.set(season,snowMapSeasonData);
  }
  if(el('snowMapSeason'))el('snowMapSeason').value=season;
  if(el('snowMapSeasonLabel'))el('snowMapSeasonLabel').textContent='Snösäsong '+season.replace('-', '/');
  setupSnowMapSlider();
  await renderSnowMapCharts();
  return snowMapSeasonData;
}

function snowMapDates(){
  if(snowMapSource()==='grid')return (snowGridData?.days||[]).map(r=>r.date);
  return [...new Set((snowMapSeasonData?.observations||[]).map(r=>r.date))].sort();
}

function setupSnowMapSlider(){
  const slider=el('snowMapDateSlider');
  const dates=snowMapDates();
  if(!slider||!dates.length)return;
  slider.min=0;slider.max=String(dates.length-1);slider.value=String(dates.length-1);slider.disabled=false;
  el('snowMapPrevDate').disabled=false;el('snowMapNextDate').disabled=false;
  updateSnowMapDateLabel();
}

function updateSnowMapDateLabel(){
  const dates=snowMapDates(),slider=el('snowMapDateSlider');
  if(!dates.length||!slider)return;
  const d=dates[Math.max(0,Math.min(dates.length-1,Number(slider.value)||0))];
  if(el('snowMapDateLabel'))el('snowMapDateLabel').textContent=formatSeaIceMapDate(d);
}

function updateSnowMapCopy(){
  const grid=snowMapSource()==='grid';
  const recent=grid&&snowGridData?.source_type==='observations_interpolated';
  if(el('snowMapTitle'))el('snowMapTitle').textContent=grid
    ?(recent?'Interpolerat snödjup i Luleå kommun':'Analyserat snödjup i Luleå kommun')
    :'Observerat snödjup i och nära Luleå kommun';
  if(el('snowMapHint'))el('snowMapHint').textContent=grid
    ?(recent
      ?'Varje 2,5 km-gridcell visar IDW-interpolerat snödjup från SMHI:s snödjupsstationer. Detta är en separat metod från GridClim.'
      :'Varje 2,5 km-gridcell visar analyserat snödjup från SMHIGridClim inom Luleå kommun.')
    :'Fyllda cirklar är stationer inom kommunen; ringmarkerade stationer ligger utanför kommunen men inom 60 km.';
  if(el('snowMapMeanTitle'))el('snowMapMeanTitle').textContent=grid?'Snödjup per snösäsong':'Genomsnittligt observerat snödjup per datum';
  if(el('snowMapMeanHint'))el('snowMapMeanHint').textContent=grid
    ?'Säsongerna visas efter varandra. Linjerna visar analyserat medel- och maxsnödjup inom Luleå kommun.'
    :'Medelvärde för tillgängliga stationer inom Luleå kommun; närliggande stationer används om kommunstationer saknas.';
  if(el('snowMapCoverageTitle'))el('snowMapCoverageTitle').textContent=grid?'Andel yta med snötäcke per snösäsong':'Andel stationer med mätbart snötäcke';
  if(el('snowMapCoverageHint'))el('snowMapCoverageHint').textContent=grid
    ?'Andel analyserade gridceller med minst 1 cm snödjup. Grön streckad linje visar celler där minst 50 % av den del av gridcellen som ligger inom kommunen är fastland, enligt samma fastlandsgeometri som Blixt-sidan.'
    :'Andel rapporterande stationer med minst 1 cm snödjup.';
}

async function renderSnowMapCharts(){
  const grid=snowMapSource()==='grid';
  const durationCard=el('snowMapDuration')?.parentElement;
  if(durationCard)durationCard.style.display=grid?'block':'none';

  if(grid){
    const series=await loadSnowGridSeries();
    if(series?.seasons?.length){
      const t=buildSnowGridTimeline(series);
      destroyChart('snowMapMean');
      charts.snowMapMean=new Chart(el('snowMapMean'),{
        type:'line',
        data:{labels:t.labels,datasets:[
          {label:'Medelsnödjup · GridClim',data:t.meanGrid,borderColor:'#67b7e1',backgroundColor:'#67b7e1',borderWidth:2,pointRadius:0,tension:.12,spanGaps:false},
          {label:'Maxsnödjup · GridClim',data:t.maxGrid,borderColor:'#1f5f8b',backgroundColor:'#1f5f8b',borderWidth:2,pointRadius:0,tension:.08,spanGaps:false},
          {label:'Medelsnödjup · interpolerat',data:t.meanRecent,borderColor:'#67b7e1',backgroundColor:'#67b7e1',borderWidth:2,pointRadius:0,borderDash:[6,4],tension:.12,spanGaps:false},
          {label:'Maxsnödjup · interpolerat',data:t.maxRecent,borderColor:'#1f5f8b',backgroundColor:'#1f5f8b',borderWidth:2,pointRadius:0,borderDash:[6,4],tension:.08,spanGaps:false}
        ]},
        options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
          plugins:{legend:{display:true},tooltip:{callbacks:{title:items=>items[0]?.label||'',label:c=>c.dataset.label+': '+Number(c.parsed.y).toLocaleString('sv-SE',{maximumFractionDigits:1})+' cm'}}},
          scales:{x:{grid:{display:false},ticks:{autoSkip:true,maxTicksLimit:18,maxRotation:45}},y:{beginAtZero:true,title:{display:true,text:'cm'}}}}
      });

      const coverageDatasets=[
        {label:'Alla gridceller · GridClim',data:t.coverGrid,borderColor:'#6d28d9',backgroundColor:'#6d28d9',borderWidth:2,pointRadius:0,tension:.12,spanGaps:false},
        {label:'Alla gridceller · interpolerat',data:t.coverRecent,borderColor:'#6d28d9',backgroundColor:'#6d28d9',borderWidth:2,pointRadius:0,borderDash:[6,4],tension:.12,spanGaps:false}
      ];
      if(t.mainGrid.some(v=>v!=null)){
        coverageDatasets.push({
          label:'Minst 50 % fastland · GridClim',
          data:t.mainGrid,
          borderColor:'#15803d',
          backgroundColor:'#15803d',
          borderWidth:2,
          pointRadius:0,
          borderDash:[6,4],
          tension:.12,
          spanGaps:false
        });
      }
      if(t.mainRecent.some(v=>v!=null)){
        coverageDatasets.push({
          label:'Minst 50 % fastland · interpolerat',
          data:t.mainRecent,
          borderColor:'#15803d',
          backgroundColor:'#15803d',
          borderWidth:2,
          pointRadius:0,
          borderDash:[2,5],
          tension:.12,
          spanGaps:false
        });
      }
      destroyChart('snowMapCoverage');
      charts.snowMapCoverage=new Chart(el('snowMapCoverage'),{
        type:'line',
        data:{labels:t.labels,datasets:coverageDatasets},
        options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
          plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+Number(c.parsed.y).toLocaleString('sv-SE',{maximumFractionDigits:1})+' %'}}},
          scales:{x:{grid:{display:false},ticks:{autoSkip:true,maxTicksLimit:18,maxRotation:45}},y:{min:0,max:100,title:{display:true,text:'andel (%)'},ticks:{callback:v=>v+' %'}}}}
      });

      const copernicus=await loadCopernicusSnowDuration();
      const durationClasses=copernicus?.classes||[];
      const durationColors=['#e0f2fe','#bae6fd','#7dd3fc','#38bdf8','#0ea5e9','#0284c7','#0369a1','#075985','#0c4a6e'];
      const seasons=(copernicus?.seasons||[]).filter(s=>s.class_pct&&Object.keys(s.class_pct).length);
      destroyChart('snowMapDuration');
      if(seasons.length){
        charts.snowMapDuration=new Chart(el('snowMapDuration'),{
          type:'bar',
          data:{
            labels:seasons.map(s=>s.season.replace('-', '/')),
            datasets:durationClasses.map((label,i)=>({
              label,
              stack:'duration',
              backgroundColor:durationColors[i%durationColors.length],
              borderWidth:0,
              data:seasons.map(s=>Number(s.class_pct?.[label]||0))
            }))
          },
          options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
            plugins:{
              legend:{display:true},
              tooltip:{callbacks:{
                title:items=>{
                  const idx=items?.[0]?.dataIndex;
                  const s=seasons[idx];
                  return s?s.season.replace('-', '/')+' · '+(s.classified_cells||0)+' giltiga 2,5 km-celler':'';
                },
                label:c=>c.dataset.label+': '+Number(c.parsed.y).toLocaleString('sv-SE',{maximumFractionDigits:1})+' %'
              }}
            },
            scales:{
              x:{stacked:true,grid:{display:false}},
              y:{stacked:true,min:0,max:100,title:{display:true,text:'andel giltiga 2,5 km-celler (%)'},ticks:{callback:v=>v+' %'}}
            }}
        });
      }
      return;
    }
  }

  destroyChart('snowMapDuration');
  const rows=snowMapSeasonData?.daily||[];
  if(!rows.length)return;
  lineChart('snowMapMean',rows.map(r=>r.date),[
    {label:'Observerat medelsnödjup',data:rows.map(r=>r.mean_cm),borderColor:'#2563eb'}
  ],'cm',{scales:{x:{grid:{display:false},ticks:{autoSkip:true,maxTicksLimit:18,maxRotation:45}},y:{beginAtZero:true,title:{display:true,text:'cm'}}}});
  lineChart('snowMapCoverage',rows.map(r=>r.date),[
    {label:'Stationer med snötäcke',data:rows.map(r=>r.snow_cover_share_pct),borderColor:'#6d28d9'}
  ],'andel (%)',{scales:{x:{grid:{display:false},ticks:{autoSkip:true,maxTicksLimit:18,maxRotation:45}},y:{min:0,max:100,title:{display:true,text:'andel (%)'},ticks:{callback:v=>v+' %'}}}});
}

async function renderSmhiRenderedSnowDaily(){
  if(!el('smhiRenderedSnowDaily'))return;
  try{
    if(!smhiRenderedSnowDaily){
      const r=await fetch('snowgrid/smhi_snow_lulea_daily_2526.json?v=1',{cache:'no-store'});
      if(!r.ok)throw new Error('Den dagliga SMHI-kartserien saknas.');
      smhiRenderedSnowDaily=await r.json();
    }
    if(!smhiRenderedSnowQa){
      const qr=await fetch('snowgrid/smhi_snow_lulea_classification_2026-02-15.json?v=1',{cache:'no-store'});
      if(qr.ok)smhiRenderedSnowQa=await qr.json();
    }
    const rows=smhiRenderedSnowDaily?.daily||[];
    if(!rows.length)throw new Error('Inga klassificerade SMHI-kartdagar hittades.');

    const defs=[
      {key:'share_barmark',label:'Barmark',color:'#71A58F'},
      {key:'share_1_2',label:'1–2 cm',color:'#b7d1c6'},
      {key:'share_3_9',label:'3–9 cm',color:'#FFFFFF',border:'#cbd5e1'},
      {key:'share_10_29',label:'10–29 cm',color:'#DEEBF7'},
      {key:'share_30_49',label:'30–49 cm',color:'#9ED0F3'},
      {key:'share_50_74',label:'50–74 cm',color:'#3B9DDC'},
      {key:'share_75_99',label:'75–99 cm',color:'#3874B9'},
      {key:'share_100_149',label:'100–149 cm',color:'#8C96C6'},
      {key:'share_150_199',label:'150–199 cm',color:'#8C6BB1'},
      {key:'share_200plus',label:'200+ cm',color:'#810F7C'}
    ];

    destroyChart('smhiRenderedSnowDaily');
    charts.smhiRenderedSnowDaily=new Chart(el('smhiRenderedSnowDaily'),{
      type:'bar',
      data:{
        labels:rows.map(r=>r.date),
        datasets:defs.map(d=>({
          label:d.label,
          stack:'depth',
          data:rows.map(r=>Number(r[d.key]||0)),
          backgroundColor:d.color,
          borderColor:d.border||d.color,
          borderWidth:d.border?0.5:0,
          barPercentage:1,
          categoryPercentage:1
        }))
      },
      options:{
        responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
        plugins:{
          legend:{display:true},
          tooltip:{callbacks:{
            title:items=>{
              const i=items?.[0]?.dataIndex;
              const r=rows[i];
              return r?formatSeaIceMapDate(r.date)+' · klassificerad yta '+Number(r.classified_area_share_pct||0).toLocaleString('sv-SE',{maximumFractionDigits:1})+' %':'';
            },
            label:c=>c.dataset.label+': '+Number(c.parsed.y).toLocaleString('sv-SE',{maximumFractionDigits:1})+' %'
          }}
        },
        scales:{
          x:{stacked:true,grid:{display:false},ticks:{autoSkip:true,maxTicksLimit:18,maxRotation:45}},
          y:{stacked:true,min:0,max:100,title:{display:true,text:'andel klassificerad kommunyta (%)'},ticks:{callback:v=>v+' %'}}
        }
      }
    });

    const qa=smhiRenderedSnowQa?.qa||{};
    const cq=smhiRenderedSnowQa?.classification||{};
    const classShares=rows.map(r=>Number(r.classified_area_share_pct)).filter(Number.isFinite);
    const avgClass=classShares.length?classShares.reduce((a,b)=>a+b,0)/classShares.length:null;
    const bits=[
      (smhiRenderedSnowDaily.processed_days||rows.length)+' kartdagar',
      (smhiRenderedSnowDaily.failed_days||0)+' misslyckade dagar',
      smhiRenderedSnowDaily.metres_per_pixel_approx!=null?'ca '+Number(smhiRenderedSnowDaily.metres_per_pixel_approx).toLocaleString('sv-SE',{maximumFractionDigits:0})+' m/pixel':null,
      qa.fractional_raster_area_error_pct_vs_official!=null?'QA areafel '+Number(qa.fractional_raster_area_error_pct_vs_official).toLocaleString('sv-SE',{maximumFractionDigits:2})+' % mot SCB-geometrin':null,
      avgClass!=null?'genomsnittligt '+avgClass.toLocaleString('sv-SE',{maximumFractionDigits:1})+' % av kommunytan färgklassificerad':null,
      cq.classified_area_share_pct!=null?'testdatum 15 feb: '+Number(cq.classified_area_share_pct).toLocaleString('sv-SE',{maximumFractionDigits:1})+' % klassificerad':null
    ].filter(Boolean);
    if(el('smhiRenderedSnowQa'))el('smhiRenderedSnowQa').textContent=bits.join(' · ')+'.';
  }catch(err){
    destroyChart('smhiRenderedSnowDaily');
    if(el('smhiRenderedSnowQa'))el('smhiRenderedSnowQa').textContent=err.message;
  }
}

async function showSnowMapDate(index){
  if(!snowMapLeaflet)return;
  await loadSnowMapSeason();
  const dates=snowMapDates();
  if(!dates.length)return;
  const safe=Math.max(0,Math.min(dates.length-1,Number(index)||0));
  const slider=el('snowMapDateSlider');slider.value=String(safe);updateSnowMapDateLabel();
  const d=dates[safe];
  if(snowMapLayer)snowMapLeaflet.removeLayer(snowMapLayer);
  snowMapLayer=L.layerGroup();

  if(snowMapSource()==='grid'){
    const day=(snowGridData.days||[]).find(x=>x.date===d);
    const values=day?.values_cm||[];
    snowMapLayer=L.geoJSON(snowGridGeometry,{
      style:f=>{
        const id=Number(f?.properties?.cell_id??f?.id??0);
        const v=values[id];
        const cls=snowDepthClass(v??0);
        return {color:'#94a3b8',weight:.55,fillColor:cls.color,fillOpacity:.78};
      },
      onEachFeature:(f,layer)=>{
        const id=Number(f?.properties?.cell_id??f?.id??0);
        const v=values[id];
        const recent=snowGridData?.source_type==='observations_interpolated';
        const sourceLabel=recent?'SMHI MetObs · IDW-interpolerat 2,5 km':'SMHIGridClim 2,5 km';
        const valueLabel=recent?'Interpolerat snödjup':'Analyserat snödjup';
        layer.bindPopup('<b>'+sourceLabel+'</b><br>Datum: '+d+'<br>'+valueLabel+': '+(v==null?'saknas':Number(v).toLocaleString('sv-SE',{maximumFractionDigits:1})+' cm'));
      }
    }).addTo(snowMapLeaflet);
    const vals=values.filter(v=>v!=null&&Number.isFinite(Number(v)));
    const status=el('snowMapStatus');
    if(status){
      const recent=snowGridData?.source_type==='observations_interpolated';
      const sourceText=recent?'SMHI MetObs · IDW-interpolerat snödjup':'SMHIGridClim · analyserat snödjup';
      const partial=recent&&snowGridData?.season==='2025-26'?' · säsongen är ofullständig':'';
      status.textContent=formatSeaIceMapDate(d)+': '+vals.length+' gridceller · '+sourceText+', 2,5 km'+partial+'.';
    }
    return;
  }

  const rows=(snowMapSeasonData.observations||[]).filter(r=>r.date===d);
  const stationMeta=snowMapSeasonData.stations||{};
  let insideCount=0;
  rows.forEach(r=>{
    const s=stationMeta[r.station_id];if(!s)return;
    const cls=snowDepthClass(r.depth_cm);
    if(s.inside_municipality)insideCount++;
    const marker=L.circleMarker([s.latitude,s.longitude],{
      radius:s.inside_municipality?8:6,
      color:s.inside_municipality?'#0f172a':'#64748b',
      weight:s.inside_municipality?1.5:2,
      dashArray:s.inside_municipality?null:'4 3',
      fillColor:cls.color,fillOpacity:.9
    });
    marker.bindPopup('<b>'+s.name+'</b><br>Datum: '+d+'<br>Snödjup: '+Number(r.depth_cm).toLocaleString('sv-SE',{maximumFractionDigits:1})+' cm<br>Klass: '+cls.label+(s.inside_municipality?'<br>Inom Luleå kommun':'<br>Nära Luleå kommun'));
    marker.addTo(snowMapLayer);
  });
  snowMapLayer.addTo(snowMapLeaflet);
  const status=el('snowMapStatus');
  if(status){
    const mode=insideCount?'varav '+insideCount+' inom kommunen':'inga kommunstationer rapporterade – närliggande stationer visas';
    status.textContent=formatSeaIceMapDate(d)+': '+rows.length+' stationer · '+mode+'.';
  }
}

function setupSnowMapControls(){
  el('snowMapSource')?.addEventListener('change',async()=>{
    if(snowMapLayer&&snowMapLeaflet){snowMapLeaflet.removeLayer(snowMapLayer);snowMapLayer=null;}
    updateSnowMapCopy();
    await refreshSnowMapSeasonOptions();
    await loadSnowMapSeason(el('snowMapSeason')?.value,true);
    await showSnowMapDate(el('snowMapDateSlider')?.value||0);
  });
  el('snowMapSeason')?.addEventListener('change',async e=>{
    await loadSnowMapSeason(e.target.value,true);
    await showSnowMapDate(el('snowMapDateSlider')?.value||0);
  });
  el('snowMapDateSlider')?.addEventListener('input',e=>{updateSnowMapDateLabel();showSnowMapDate(e.target.value);});
  el('snowMapPrevDate')?.addEventListener('click',()=>showSnowMapDate(Number(el('snowMapDateSlider').value)-1));
  el('snowMapNextDate')?.addEventListener('click',()=>showSnowMapDate(Number(el('snowMapDateSlider').value)+1));
}

async function initSnowMap(){
  const mapEl=el('snowMap');
  if(!mapEl||typeof L==='undefined')return;
  const status=el('snowMapStatus');
  if(snowMapLeaflet){
    setTimeout(()=>snowMapLeaflet.invalidateSize(),50);
    await renderSmhiRenderedSnowDaily();
    return;
  }
  try{
    if(status)status.textContent='Laddar Luleå kommun och snödjupslager…';
    snowMapLeaflet=L.map(mapEl,{zoomControl:true});
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
      maxZoom:18,attribution:'&copy; OpenStreetMap contributors'
    }).addTo(snowMapLeaflet);

    const br=await fetch('snowmap_boundary.geojson?v=1',{cache:'no-store'});
    if(!br.ok)throw new Error('Kommungränsen för snötäckeskartan saknas.');
    const boundary=await br.json();
    snowMapBoundaryLayer=L.geoJSON(boundary,{style:{color:'#dc2626',weight:2.5,fillColor:'#ffffff',fillOpacity:.03}}).addTo(snowMapLeaflet);
    const bounds=snowMapBoundaryLayer.getBounds();if(bounds.isValid())snowMapLeaflet.fitBounds(bounds.pad(.12));

    const legend=L.control({position:'topright'});
    legend.onAdd=()=>{
      const div=L.DomUtil.create('div','seaice-map-legend');
      const classes=[0,1,3,10,30,50,75,100,150,200];
      div.innerHTML='<b>Snödjup</b>'+classes.map(v=>{const c=snowDepthClass(v);return '<div><i style="background:'+c.color+'"></i>'+c.label+'</div>';}).join('')+
        '<div><i style="background:transparent;border:2px solid #dc2626"></i>Luleå kommun</div>';
      return div;
    };
    legend.addTo(snowMapLeaflet);

    updateSnowMapCopy();
    await refreshSnowMapSeasonOptions();
    await loadSnowMapSeason();
    await showSnowMapDate(el('snowMapDateSlider')?.value||0);
    await renderSmhiRenderedSnowDaily();
  }catch(err){
    if(status)status.textContent=err.message;
    if(el('snowMapSource'))el('snowMapSource').value='stations';
    try{
      updateSnowMapCopy();
      await refreshSnowMapSeasonOptions();
      await loadSnowMapSeason();
      await showSnowMapDate(el('snowMapDateSlider')?.value||0);
    }catch{}
  }
}

function setupSeaIceSeasonControls(){
  const slider=el('seaIceSeasonSlider');
  if(!slider)return;
  slider.addEventListener('input',()=>{
    updateSeaIceSeasonDateLabel();
    clearTimeout(seaIceSeasonTimer);
    seaIceSeasonTimer=setTimeout(()=>showSeaIceSeasonDate(slider.value),180);
  });
  el('seaIcePrevDate')?.addEventListener('click',()=>showSeaIceSeasonDate(Number(slider.value)-1));
  el('seaIceNextDate')?.addEventListener('click',()=>showSeaIceSeasonDate(Number(slider.value)+1));
}

async function initSeaIceMap(){
  const mapEl=el('seaIceMap');
  if(!mapEl||typeof L==='undefined')return;
  const status=el('seaIceMapStatus');
  if(seaIceLeafletMap){
    setTimeout(()=>seaIceLeafletMap.invalidateSize(),50);
    return;
  }
  if(status)status.textContent='Laddar kartgeometri…';
  try{
    const r=await fetch('seaice_analysis_area.geojson?v=1',{cache:'no-store'});
    if(!r.ok)throw new Error('Kartgeometrin är ännu inte genererad. Kör havsishämtningen i refresh-all-läge en gång.');
    const geo=await r.json();

    seaIceLeafletMap=L.map(mapEl,{zoomControl:true});
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
      maxZoom:18,
      attribution:'&copy; OpenStreetMap contributors'
    }).addTo(seaIceLeafletMap);

    const analysis=L.geoJSON(geo,{
      filter:f=>f?.properties?.kind==='smhi_analysis',
      style:{color:'#1f5f8b',weight:2,fillColor:'#67b7e1',fillOpacity:.40}
    }).addTo(seaIceLeafletMap);

    const municipal=L.geoJSON(geo,{
      filter:f=>f?.properties?.kind==='municipal_sea',
      style:{color:'#dc2626',weight:2.5,fill:false,fillOpacity:0}
    }).addTo(seaIceLeafletMap);

    const bounds=L.featureGroup([analysis,municipal]).getBounds();
    if(bounds.isValid())seaIceLeafletMap.fitBounds(bounds.pad(.03));

    const legend=L.control({position:'topright'});
    legend.onAdd=()=>{
      const div=L.DomUtil.create('div','seaice-map-legend');
      div.innerHTML=
        '<div><i style="background:rgba(103,183,225,.55);border:2px solid #1f5f8b"></i>SMHI analyserad havsyta</div>'+
        '<div><i style="background:transparent;border:2px solid #dc2626"></i>Kommunal havsyta</div>';
      return div;
    };
    legend.addTo(seaIceLeafletMap);

    const analysisFeature=(geo.features||[]).find(f=>f?.properties?.kind==='smhi_analysis');
    const sourceDate=analysisFeature?.properties?.source_date;
    if(status)status.textContent=sourceDate
      ? 'Kartgeometri från SMHI:s analys '+sourceDate+'. Bakgrundskarta: OpenStreetMap.'
      : 'Bakgrundskarta: OpenStreetMap.';
    await loadSeaIceSeasonManifest();
    await showSeaIceSeasonDate(el('seaIceSeasonSlider')?.value||0);
  }catch(err){
    if(status)status.textContent=err.message;
  }
}

function seaIceSeasonDateRange(startYear){
  const out=[];
  let d=new Date(Date.UTC(startYear,9,15));
  const end=new Date(Date.UTC(startYear+1,5,6));
  while(d<=end){
    out.push(d.toISOString().slice(0,10));
    d.setUTCDate(d.getUTCDate()+1);
  }
  return out;
}

function buildSeaIceSeasonTimeline(dailyRows,seasonalRows){
  const byDate=new Map(dailyRows.map(r=>[r.date,r]));
  const labels=[],rows=[],seasonKeys=[];
  seasonalRows.forEach((s,idx)=>{
    seaIceSeasonDateRange(s.start_year).forEach(date=>{
      labels.push(date);
      rows.push(byDate.get(date)||null);
      seasonKeys.push(s.season);
    });
    if(idx<seasonalRows.length-1){
      labels.push('');
      rows.push(null);
      seasonKeys.push(null);
    }
  });
  return {labels,rows,seasonKeys};
}

function buildSeaIceMissingTail(timeline,field){
  const out=Array(timeline.rows.length).fill(null);
  const seasons=[...new Set(timeline.seasonKeys.filter(Boolean))];
  seasons.forEach(season=>{
    const idxs=[];
    timeline.seasonKeys.forEach((s,i)=>{if(s===season)idxs.push(i);});
    let lastIdx=-1,lastValue=null;
    idxs.forEach(i=>{
      const r=timeline.rows[i];
      const v=r?r[field]:null;
      if(v!==null&&v!==undefined&&Number.isFinite(Number(v))){
        lastIdx=i;
        lastValue=Number(v);
      }
    });
    if(lastIdx<0)return;
    const seasonEnd=idxs[idxs.length-1];
    if(lastIdx>=seasonEnd)return;
    // Start at the last observed point so the grey dashed segment connects
    // cleanly to the measured line, then carry that last known value forward.
    for(let i=lastIdx;i<=seasonEnd;i++)out[i]=lastValue;
  });
  return out;
}

function renderSeaIce(f){
  const S=DATA.sea_ice||{};
  const seasonal=(S.seasonal||[])
    .filter(r=>r.start_year>=f.from&&r.start_year<=f.to)
    .sort((a,b)=>a.start_year-b.start_year);
  const selectedStarts=new Set(seasonal.map(r=>r.start_year));
  const daily=(S.daily||[])
    .filter(r=>selectedStarts.has(Number(String(r.season||'').slice(0,4))))
    .sort((a,b)=>String(a.date).localeCompare(String(b.date)));
  const timeline=buildSeaIceSeasonTimeline(daily,seasonal);

  const noData=el('seaIceNoData');
  const has=daily.length>0||seasonal.length>0;
  if(noData)noData.style.display=has?'none':'block';
  ['seaIceDaily','seaIceThickness','seaIceFast','seaIceLength'].forEach(id=>{
    const canvas=el(id);
    if(canvas)canvas.parentElement.style.display=has?'block':'none';
    if(!has)destroyChart(id);
  });
  if(!has)return;

  if(timeline.rows.length){
    const iceTail=buildSeaIceMissingTail(timeline,'ice_share_pct');
    const meanTail=buildSeaIceMissingTail(timeline,'mean_ice_thickness_cm');
    const maxTail=buildSeaIceMissingTail(timeline,'max_ice_thickness_cm');

    lineChart('seaIceDaily',timeline.labels,[
      {label:'Isutbredning',data:timeline.rows.map(r=>r?r.ice_share_pct:null),borderColor:'#111827',backgroundColor:'#111827',borderWidth:2,pointRadius:0,spanGaps:false},
      {label:'Data saknas – sista kända värde',data:iceTail,borderColor:'#dc2626',backgroundColor:'#dc2626',borderDash:[6,4],borderWidth:2,pointRadius:0,tension:0,spanGaps:false}
    ],'%');

    lineChart('seaIceThickness',timeline.labels,[
      {label:'Medeltjocklek',data:timeline.rows.map(r=>r?r.mean_ice_thickness_cm:null),borderColor:'#67b7e1',backgroundColor:'#67b7e1',borderWidth:2,pointRadius:0,spanGaps:false},
      {label:'Maximal tjocklek',data:timeline.rows.map(r=>r?r.max_ice_thickness_cm:null),borderColor:'#1f5f8b',backgroundColor:'#1f5f8b',borderWidth:2,pointRadius:0,spanGaps:false},
      {label:'Saknad data – medel',data:meanTail,borderColor:'#ef4444',backgroundColor:'#ef4444',borderDash:[6,4],borderWidth:2,pointRadius:0,tension:0,spanGaps:false},
      {label:'Saknad data – max',data:maxTail,borderColor:'#b91c1c',backgroundColor:'#b91c1c',borderDash:[3,4],borderWidth:2,pointRadius:0,tension:0,spanGaps:false}
    ],'cm');
  }else{
    destroyChart('seaIceDaily');
    destroyChart('seaIceThickness');
  }

  const labels=seasonal.map(r=>r.season);
  barChart('seaIceFast',labels,seasonal.map(r=>r.max_fast_ice_share_pct),'%','#d8b4fe');
  barChart('seaIceLength',labels,seasonal.map(r=>r.season_length_days),'dygn');

  const latest=seasonal.length?seasonal[seasonal.length-1]:null;
  const note=el('seaIceLatest');
  if(note){
    note.textContent=latest
      ? 'Varje issäsong visas från 15 oktober till 6 juni. Senaste kompletta/partiella säsong i datat: '+latest.season+
        '. Maximal isutbredning '+Number(latest.max_ice_share_pct||0).toFixed(1).replace('.',',')+
        ' % den '+(latest.max_ice_date||'–')+'.'
      : '';
  }
}

function render(){
  const f=currentFilters(),m=temperatureMetric(),name=metricName(m);
  const ta=selectedAnnualRows(DATA.temperature.annual,DATA.temperature.monthly,f);const taYears=ta.map(r=>r.year),taVals=ta.map(r=>r[m]);
  lineChart('tempAnnual',taYears,[{label:name,data:taVals},{label:'Linjär trend',data:linearTrend(taYears,taVals),pointRadius:0,borderDash:[6,4]}],'°C');
  el('tempAnnualTitle').textContent=name+' lufttemperatur '+(f.month?'i '+months[f.month-1].toLowerCase()+' per år':'per år');
  el('tempAnnualTrendText').textContent=trendRateText(taYears,taVals,'°C');
  let tm=DATA.temperature.monthly.filter(r=>inYears(r,f));
  const tMonthAgg=[...Array(12)].map((_,i)=>{
    const rows=tm.filter(r=>r.month===i+1);if(!rows.length)return null;
    if(m==='min')return Math.min(...rows.map(r=>r.min));
    if(m==='max')return Math.max(...rows.map(r=>r.max));
    const vals=rows.map(r=>r[m]).filter(v=>v!=null);
    return vals.length?vals.reduce((s,v)=>s+v,0)/vals.length:null;
  });lineChart('tempMonthly',months,[{label:'°C',data:tMonthAgg,borderColor:MONTH_GREEN,backgroundColor:MONTH_GREEN}],'°C');el('tempMonthlyTitle').textContent=name+' lufttemperatur per månad';
  renderTemp2();
  renderVegetation(f);

  renderLightning(f);
  renderSeaIce(f);

  const pa=selectedAnnualRows(DATA.precipitation.annual,DATA.precipitation.monthly_total,f);const paYears=pa.map(r=>r.year),paVals=pa.map(r=>r.sum);
  destroyChart('precipAnnual');
  charts.precipAnnual=new Chart(el('precipAnnual'),{
    data:{labels:paYears,datasets:[
      {type:'bar',label:f.month?months[f.month-1]+' nederbörd':'Årsnederbörd',data:paVals,borderWidth:0},
      {type:'line',label:'Linjär trend',data:linearTrend(paYears,paVals),borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+Math.round(c.parsed.y)+' mm'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'mm'},ticks:{precision:0}}}}
  });
  el('precipAnnualTrendText').textContent=trendRateText(paYears,paVals,'mm');
  let pm=DATA.precipitation.monthly_total.filter(r=>inYears(r,f));
  const precipMonthVals=aggregateMonthlyMean(pm,'sum');
  destroyChart('precipMonthly');
  charts.precipMonthly=new Chart(el('precipMonthly'),{type:'bar',data:{labels:months,datasets:[{data:precipMonthVals,borderWidth:0,backgroundColor:MONTH_GREEN}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>Math.round(c.parsed.y)+' mm'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'mm'},ticks:{precision:0}}}}});

  let pt=DATA.precipitation.types.filter(r=>inYears(r,f));
  let ptAnnual=pt;if(f.month)ptAnnual=ptAnnual.filter(r=>r.month===f.month);
  const pta=precipTypeShares(ptAnnual,r=>r.year);
  const ptaLabels=pta.map(r=>r.key);
  renderPrecipTypeChart('precipTypeAnnual',ptaLabels,pta);
  el('precipTypeSourceText').textContent='Datakälla för nederbördstyp: '+(DATA.precipitation.type_source||'okänd');
  const ptm=precipTypeShares(pt,r=>r.month);
  const ptmByMonth=months.map((_,i)=>ptm.find(r=>+r.key===i+1)||{key:i+1,rain:0,mixed:0,snow:0});
  renderPrecipTypeChart('precipTypeMonthly',months,ptmByMonth);

  let wc=DATA.weather.codes.filter(r=>inYears(r,f));if(f.month)wc=wc.filter(r=>r.month===f.month);weatherChart(wc);

  const ws=(f.month?DATA.wind.speed_monthly.filter(r=>inYears(r,f)&&r.month===f.month):DATA.wind.speed_annual.filter(r=>inYears(r,f))),
        wm=(f.month?DATA.wind.max_monthly.filter(r=>inYears(r,f)&&r.month===f.month):DATA.wind.max_annual.filter(r=>inYears(r,f))),
        wg=(f.month?DATA.wind.gust_max_monthly.filter(r=>inYears(r,f)&&r.month===f.month):DATA.wind.gust_max_annual.filter(r=>inYears(r,f)));
  const windYears=[...new Set([...ws.map(r=>r.year),...wm.map(r=>r.year),...wg.map(r=>r.year)])].sort((a,b)=>a-b);
  lineChart('windSpeed',windYears,[
    {label:'Årsmedel',data:windYears.map(y=>{const x=ws.find(a=>a.year===y);return x?x.avg:null;})},
    {label:f.month?months[f.month-1]+' högsta medelvind':'Årets högsta medelvind',data:windYears.map(y=>{const x=wm.find(a=>a.year===y);return x?x.max:null;})},
    {label:f.month?months[f.month-1]+' högsta byvind':'Årets högsta byvind',data:windYears.map(y=>{const x=wg.find(a=>a.year===y);return x?x.max:null;})}
  ],'m/s');

  const wd=(f.month?DATA.wind.direction_monthly.filter(r=>inYears(r,f)&&r.month===f.month):DATA.wind.direction_annual.filter(r=>inYears(r,f)));destroyChart('windDirection');charts.windDirection=new Chart(el('windDirection'),{type:'line',data:{labels:wd.map(r=>r.year),datasets:[{data:wd.map(r=>r.avg),borderWidth:2,pointRadius:2,tension:.1}]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'nearest',intersect:false},onHover:(e,pts)=>{if(pts.length){const i=pts[0].index;updateCompass(wd[i].avg,String(wd[i].year));}},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.parsed.y.toFixed(0)+'° ('+directionName(c.parsed.y)+')'}}},scales:{x:{grid:{display:false}},y:{min:0,max:360,title:{display:true,text:'grader'},ticks:{stepSize:45,callback:v=>v+'° '+directionName(v)}}}}});
  const wdm=DATA.wind.direction_monthly.filter(r=>inYears(r,f));const monthly=[...Array(12)].map((_,i)=>circularFromParts(wdm.filter(r=>r.month===i+1)));destroyChart('windDirectionMonthly');charts.windDirectionMonthly=new Chart(el('windDirectionMonthly'),{type:'line',data:{labels:months,datasets:[{data:monthly,borderWidth:2,pointRadius:2,tension:.1,borderColor:MONTH_GREEN,backgroundColor:MONTH_GREEN}]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'nearest',intersect:false},onHover:(e,pts)=>{if(pts.length){const i=pts[0].index;updateCompass(monthly[i],months[i]);}},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.parsed.y.toFixed(0)+'° ('+directionName(c.parsed.y)+')'}}},scales:{x:{grid:{display:false}},y:{min:0,max:360,title:{display:true,text:'grader'},ticks:{stepSize:45,callback:v=>v+'° '+directionName(v)}}}}});
  let wds=DATA.wind.direction_sectors.filter(r=>inYears(r,f));if(f.month)wds=wds.filter(r=>r.month===f.month);
  const windShareYears=[...new Set(wds.map(r=>r.year))].sort((a,b)=>a-b);
  const windDirs=['N','NO','O','SO','S','SV','V','NV'];
  const WIND_DIR_COLORS={
    N:'rgba(243,234,42,0.80)',
    NO:'rgba(238,177,44,0.80)',
    O:'rgba(217,37,31,0.80)',
    SO:'rgba(142,42,115,0.80)',
    S:'rgba(70,58,151,0.80)',
    SV:'rgba(120,173,214,0.80)',
    V:'rgba(125,187,97,0.80)',
    NV:'rgba(184,207,55,0.80)'
  };
  const windTotals={};wds.forEach(r=>windTotals[r.year]=(windTotals[r.year]||0)+r.count);
  destroyChart('windDirectionShares');
  charts.windDirectionShares=new Chart(el('windDirectionShares'),{type:'bar',data:{labels:windShareYears,datasets:windDirs.map(dir=>({
    label:dir,stack:'dir',borderWidth:0,backgroundColor:WIND_DIR_COLORS[dir],
    data:windShareYears.map(y=>{const n=wds.filter(r=>r.year===y&&r.direction===dir).reduce((s,r)=>s+r.count,0);return windTotals[y]?100*n/windTotals[y]:0;})
  }))},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
    plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+c.parsed.y.toFixed(1).replace('.',',')+' %'}}},
    scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,min:0,max:100,title:{display:true,text:'andel (%)'},ticks:{callback:v=>v+' %'}}}}});

  const wdsMonthly=DATA.wind.direction_sectors.filter(r=>inYears(r,f));
  const monthlyTotals={};
  wdsMonthly.forEach(r=>monthlyTotals[r.month]=(monthlyTotals[r.month]||0)+r.count);
  destroyChart('windDirectionSharesMonthly');
  charts.windDirectionSharesMonthly=new Chart(el('windDirectionSharesMonthly'),{
    type:'bar',
    data:{labels:months,datasets:windDirs.map(dir=>({
      label:dir,stack:'dir',borderWidth:0,backgroundColor:WIND_DIR_COLORS[dir],
      data:months.map((_,i)=>{
        const month=i+1;
        const n=wdsMonthly.filter(r=>r.month===month&&r.direction===dir).reduce((s,r)=>s+r.count,0);
        return monthlyTotals[month]?100*n/monthlyTotals[month]:0;
      })
    }))},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+c.parsed.y.toFixed(1).replace('.',',')+' %'}}},
      scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,min:0,max:100,title:{display:true,text:'andel (%)'},ticks:{callback:v=>v+' %'}}}}
  });

  const va=selectedAnnualRows(DATA.visibility.annual,DATA.visibility.monthly,f);
  const vaYears=va.map(r=>r.year),vaVals=va.map(r=>Math.round(r.avg));
  destroyChart('visibilityAnnual');
  charts.visibilityAnnual=new Chart(el('visibilityAnnual'),{
    data:{labels:vaYears,datasets:[
      {type:'line',label:f.month?months[f.month-1]+' medel':'Årsmedel',data:vaVals,borderWidth:2,pointRadius:0,tension:.15},
      {type:'line',label:'Linjär trend',data:linearTrend(vaYears,vaVals),borderColor:'#ff6384',backgroundColor:'rgba(255,99,132,0.35)',borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+Math.round(c.parsed.y)+' meter'}}},
      scales:{x:{grid:{display:false}},y:{title:{display:true,text:'meter'},ticks:{precision:0,callback:v=>Math.round(v)}}}}
  });
  if(el('visibilityAnnualTrendText'))el('visibilityAnnualTrendText').textContent=trendRateText(vaYears,vaVals,'meter');
  let vm=DATA.visibility.monthly.filter(r=>inYears(r,f));
  const vmVals=aggregateMonthlyMean(vm).map(v=>v==null?null:Math.round(v));
  destroyChart('visibilityMonthly');
  charts.visibilityMonthly=new Chart(el('visibilityMonthly'),{type:'bar',data:{labels:months,datasets:[{data:vmVals,borderWidth:0,backgroundColor:MONTH_GREEN}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>Math.round(c.parsed.y)+' meter'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'meter'},ticks:{precision:0,callback:v=>Math.round(v)}}}}});

  const ha=selectedAnnualRows(DATA.humidity.annual,DATA.humidity.monthly,f);const haYears=ha.map(r=>r.year),haVals=ha.map(r=>r.avg);
  lineChart('humidityAnnual',haYears,[{label:f.month?months[f.month-1]+' medel':'Årsmedel',data:haVals},{label:'Linjär trend',data:linearTrend(haYears,haVals),pointRadius:0,borderDash:[6,4]}],'%');
  el('humidityAnnualTrendText').textContent=trendRateText(haYears,haVals,'procentenheter');
  let hm=DATA.humidity.monthly.filter(r=>inYears(r,f));barChart('humidityMonthly',months,aggregateMonthlyMean(hm),'%',MONTH_GREEN);

  const sunA=selectedAnnualRows(DATA.sunshine.annual,DATA.sunshine.monthly_total,f);const sunYears=sunA.map(r=>r.year),sunVals=sunA.map(r=>r.hours);
  destroyChart('sunAnnual');
  charts.sunAnnual=new Chart(el('sunAnnual'),{
    data:{labels:sunYears,datasets:[
      {type:'bar',label:f.month?months[f.month-1]+' solskenstid':'Solskenstid per år',data:sunVals,borderWidth:0},
      {type:'line',label:'Linjär trend',data:linearTrend(sunYears,sunVals),borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'timmar'}}}}
  });
  el('sunAnnualTrendText').textContent=trendRateText(sunYears,sunVals,'timmar');
  let sunM=DATA.sunshine.monthly_total.filter(r=>inYears(r,f));
  const sunMonthVals=aggregateMonthlyMean(sunM,'hours').map(v=>v==null?null:Math.round(v));
  destroyChart('sunMonthly');
  charts.sunMonthly=new Chart(el('sunMonthly'),{type:'bar',data:{labels:months,datasets:[{data:sunMonthVals,borderWidth:0,backgroundColor:MONTH_GREEN}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>Math.round(c.parsed.y)+' timmar'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'timmar'},ticks:{precision:0,callback:v=>Math.round(v)+' timmar'}}}}});

  const irrSource=f.month
    ? (DATA.sunshine.irradiance_monthly||[]).filter(r=>inYears(r,f)&&r.month===f.month)
    : (DATA.sunshine.irradiance_annual||[]).filter(r=>inYears(r,f));
  const irrYears=irrSource.map(r=>r.year),irrVals=irrSource.map(r=>r.kwh_m2);
  destroyChart('irradianceAnnual');
  charts.irradianceAnnual=new Chart(el('irradianceAnnual'),{
    data:{labels:irrYears,datasets:[
      {type:'bar',label:f.month?months[f.month-1]+' solinstrålning':'Årlig solinstrålning',data:irrVals,borderWidth:0,backgroundColor:'rgba(230,126,34,0.55)'},
      {type:'line',label:'Linjär trend',data:linearTrend(irrYears,irrVals),borderColor:'#ff6384',backgroundColor:'rgba(255,99,132,0.35)',borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.parsed.y==null?c.dataset.label+': –':c.dataset.label+': '+Math.round(c.parsed.y)+' kWh/m²'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'kWh/m²'}}}}
  });
  el('irradianceAnnualTrendText').textContent=trendRateText(irrYears,irrVals,'kWh/m²');

  const irrMonthlyRows=(DATA.sunshine.irradiance_monthly||[])
    .filter(r=>inYears(r,f)&&r.kwh_m2!=null);
  const daylightAdjusted=months.map((_,i)=>{
    const month=i+1;
    const vals=irrMonthlyRows.filter(r=>r.month===month).map(r=>{
      const daylightHours=daylightHoursInMonth(r.year,month);
      return daylightHours&&daylightHours>0 ? (r.kwh_m2*1000/daylightHours) : null;
    }).filter(v=>v!=null&&Number.isFinite(v));
    return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;
  });
  destroyChart('irradianceDaylightMonthly');
  charts.irradianceDaylightMonthly=new Chart(el('irradianceDaylightMonthly'),{
    type:'bar',
    data:{labels:months,datasets:[{label:'Genomsnittlig global irradians under dagsljus',data:daylightAdjusted,borderWidth:0,backgroundColor:'rgba(242,201,76,0.55)'}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.parsed.y==null?'–':Math.round(c.parsed.y)+' W/m²'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'W/m² under sol över horisonten'},ticks:{precision:0}}}}
  });

  const monthlyEnergy=months.map((_,i)=>{
    const vals=irrMonthlyRows.filter(r=>r.month===i+1).map(r=>r.kwh_m2).filter(v=>v!=null&&Number.isFinite(v));
    return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;
  });
  barChart('irradianceEnergyMonthly',months,monthlyEnergy,'kWh/m²','rgba(230,126,34,0.55)');

  const snowA=DATA.snow.annual_mean.filter(r=>r.year>=f.from&&r.year<=f.to),
        snowMax=DATA.snow.annual_max.filter(r=>r.year>=f.from&&r.year<=f.to);
  const snowMeanYears=snowA.map(r=>r.year),snowMeanVals=snowA.map(r=>r.avg),snowMeanLabels=snowA.map(r=>r.label||String(r.year));
  destroyChart('snowMeanAnnual');
  charts.snowMeanAnnual=new Chart(el('snowMeanAnnual'),{
    type:'line',
    data:{labels:snowMeanLabels,datasets:[
      {label:'Medelsnödjup',data:snowMeanVals,borderWidth:2,pointRadius:1,tension:.15},
      {label:'Linjär trend',data:linearTrend(snowMeanYears,snowMeanVals),borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:true}},scales:{x:{grid:{display:false}},y:{title:{display:true,text:'cm'}}}}
  });
  el('snowMeanTrendText').textContent=trendRateText(snowMeanYears,snowMeanVals,'cm',snowMeanLabels[0]??null,snowMeanLabels[snowMeanLabels.length-1]??null);

  const snowMaxYears=snowMax.map(r=>r.year),snowMaxVals=snowMax.map(r=>r.max),snowMaxLabels=snowMax.map(r=>r.label||String(r.year));
  destroyChart('snowMaxAnnual');
  charts.snowMaxAnnual=new Chart(el('snowMaxAnnual'),{
    type:'line',
    data:{labels:snowMaxLabels,datasets:[
      {label:'Största snödjup',data:snowMaxVals,borderWidth:2,pointRadius:1,tension:.15},
      {label:'Linjär trend',data:linearTrend(snowMaxYears,snowMaxVals),borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:true}},scales:{x:{grid:{display:false}},y:{title:{display:true,text:'cm'}}}}
  });
  el('snowMaxTrendText').textContent=trendRateText(snowMaxYears,snowMaxVals,'cm',snowMaxLabels[0]??null,snowMaxLabels[snowMaxLabels.length-1]??null);

  let snowM=DATA.snow.monthly.filter(r=>r.year>=f.from&&r.year<=f.to);
  barChart('snowMonthly',months,aggregateMonthlyMean(snowM),'cm',MONTH_GREEN);
  const snowSeasons=DATA.snow.seasons.filter(s=>s.start_year>=f.from&&s.start_year<=f.to);
  const seasonLabels=snowSeasons.map(s=>s.label),seasonVals=snowSeasons.map(s=>s.length_days);
  const seasonYears=snowSeasons.map(s=>s.start_year);
  const seasonTrend=linearTrend(seasonYears,seasonVals);
  destroyChart('snowSeason');
  el('snowSeasonTrendText').textContent=trendRateText(seasonYears,seasonVals,'dygn',seasonLabels[0]??null,seasonLabels[seasonLabels.length-1]??null);
  charts.snowSeason=new Chart(el('snowSeason'),{
    data:{labels:seasonLabels,datasets:[
      {type:'bar',label:'Säsongslängd',data:seasonVals,borderWidth:0},
      {type:'line',label:'Linjär trend',data:seasonTrend,borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+(c.parsed.y==null?'–':c.parsed.y.toFixed(1))+' dygn'}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'dygn'}}}}
  });

  let z=DATA.zero_crossings.filter(r=>inYears(r,f));if(f.month)z=z.filter(r=>r.month===f.month);
  const zy={};z.forEach(r=>zy[r.year]=(zy[r.year]||0)+1);
  const zYears=Object.keys(zy).map(Number).sort((a,b)=>a-b),zVals=zYears.map(y=>zy[y]);
  destroyChart('zeroAnnual');
  charts.zeroAnnual=new Chart(el('zeroAnnual'),{
    data:{labels:zYears,datasets:[
      {type:'bar',label:'Dygn med nollgenomgång',data:zVals,borderWidth:0},
      {type:'line',label:'Linjär trend',data:linearTrend(zYears,zVals),borderWidth:2,pointRadius:0,borderDash:[6,4]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'dygn'}}}}
  });
  el('zeroAnnualTrendText').textContent=trendRateText(zYears,zVals,'dygn');
  const tempCoverage=DATA.temperature.monthly.filter(r=>inYears(r,f));
  const zAllMonths=DATA.zero_crossings.filter(r=>inYears(r,f));
  const zm=[...Array(12)].map((_,i)=>{
    const yearsCovered=new Set(tempCoverage.filter(r=>r.month===i+1).map(r=>r.year)).size;
    return yearsCovered?zAllMonths.filter(r=>r.month===i+1).length/yearsCovered:null;
  });
  barChart('zeroMonthly',months,zm,'dygn per år',MONTH_GREEN);
  const crossByYear={};z.forEach(r=>{if(!crossByYear[r.year])crossByYear[r.year]={sum:0,n:0};crossByYear[r.year].sum+=r.crossings;crossByYear[r.year].n++;});
  const trendYears=Object.keys(crossByYear).map(Number).sort((a,b)=>a-b),trendVals=trendYears.map(y=>crossByYear[y].sum/crossByYear[y].n);
  lineChart('zeroTrend',trendYears,[{label:'Genomsnitt',data:trendVals,pointRadius:2},{label:'Linjär trend',data:linearTrend(trendYears,trendVals),pointRadius:0,borderDash:[6,4]}],'genomgångar per dygn');
  el('zeroTrendText').textContent=trendRateText(trendYears,trendVals,'genomgångar/dygn');
  el('zeroTable').innerHTML='<table><thead><tr><th>Datum</th><th>Min °C</th><th>Max °C</th><th>Antal genomgångar</th><th>Riktning</th><th>Observationer</th></tr></thead><tbody>'+z.slice().sort((a,b)=>b.date.localeCompare(a.date)).map(r=>'<tr><td>'+r.date+'</td><td>'+r.min+'</td><td>'+r.max+'</td><td>'+r.crossings+'</td><td>'+r.directions.join(', ')+'</td><td>'+r.observations+'</td></tr>').join('')+'</tbody></table>';

  el('coverage').innerHTML='<table><thead><tr><th>Parameter</th><th>Från</th><th>Till</th><th>Observationer</th></tr></thead><tbody>'+DATA.coverage.map(r=>'<tr><td>'+r.name+'</td><td>'+r.min_date+'</td><td>'+r.max_date+'</td><td>'+r.rows.toLocaleString('sv-SE')+'</td></tr>').join('')+'</tbody></table>';
}
function solarTimes(dateStr,lat=65.543,lon=22.124){
  const [y,m,d]=dateStr.split('-').map(Number);
  const rad=Math.PI/180,deg=180/Math.PI;
  const jd=Math.floor((Date.UTC(y,m-1,d)-Date.UTC(2000,0,1,12))/86400000)+2451545.0;
  const n=jd-2451545.0+0.0008;
  const jStar=n-lon/360;
  const M=(357.5291+0.98560028*jStar)%360;
  const C=1.9148*Math.sin(M*rad)+0.0200*Math.sin(2*M*rad)+0.0003*Math.sin(3*M*rad);
  const lambda=(M+C+180+102.9372)%360;
  const jTransit=2451545.0+jStar+0.0053*Math.sin(M*rad)-0.0069*Math.sin(2*lambda*rad);
  const delta=Math.asin(Math.sin(lambda*rad)*Math.sin(23.44*rad));
  const h0=-0.833*rad;
  const cosOmega=(Math.sin(h0)-Math.sin(lat*rad)*Math.sin(delta))/(Math.cos(lat*rad)*Math.cos(delta));
  if(cosOmega<-1)return {sunrise:null,sunset:null,dayLength:'24 h 00 min',sunriseMinutes:null,sunsetMinutes:null,polarDay:true,polarNight:false};
  if(cosOmega>1)return {sunrise:null,sunset:null,dayLength:'0 h 00 min',sunriseMinutes:null,sunsetMinutes:null,polarDay:false,polarNight:true};
  const omega=Math.acos(cosOmega)*deg;
  const jSet=jTransit+omega/360;
  const jRise=jTransit-omega/360;
  const jdToDate=j=>new Date((j-2440587.5)*86400000);
  const parts=t=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Stockholm',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(t);
  const hm=t=>{const p=parts(t);const h=+p.find(x=>x.type==='hour').value,mn=+p.find(x=>x.type==='minute').value;return {text:String(h).padStart(2,'0')+':'+String(mn).padStart(2,'0'),minutes:h*60+mn};};
  const rise=jdToDate(jRise),set=jdToDate(jSet),r=hm(rise),s=hm(set);
  const mins=Math.round((set-rise)/60000);
  return {sunrise:r.text,sunset:s.text,dayLength:Math.floor(mins/60)+' h '+String(mins%60).padStart(2,'0')+' min',sunriseMinutes:r.minutes,sunsetMinutes:s.minutes,polarDay:false,polarNight:false};
}
function hourlyAverage(obs){
  return hours.map((_,h)=>{
    const vals=(obs||[]).filter(r=>+r.time.slice(0,2)===h).map(r=>+r.value).filter(Number.isFinite);
    return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;
  });
}
function hourlySum(obs){
  return hours.map((_,h)=>{
    const vals=(obs||[]).filter(r=>+r.time.slice(0,2)===h).map(r=>+r.value).filter(Number.isFinite);
    return vals.length?vals.reduce((a,b)=>a+b,0):null;
  });
}
function hourlyWeather(obs){
  return hours.map((_,h)=>{
    const rows=(obs||[]).filter(r=>+r.time.slice(0,2)===h).sort((a,b)=>a.time.localeCompare(b.time));
    return rows.length?String(rows[rows.length-1].code):null;
  });
}
function sunHourFractions(sun){
  if(sun.polarDay)return hours.map(()=>100);
  if(sun.polarNight)return hours.map(()=>0);
  if(sun.sunriseMinutes==null||sun.sunsetMinutes==null)return hours.map(()=>null);
  return hours.map((_,h)=>{
    const a=h*60,b=(h+1)*60;
    let overlap=0;
    if(sun.sunsetMinutes>=sun.sunriseMinutes){
      overlap=Math.max(0,Math.min(b,sun.sunsetMinutes)-Math.max(a,sun.sunriseMinutes));
    }else{
      overlap=Math.max(0,Math.min(b,sun.sunsetMinutes)-a)+Math.max(0,b-Math.max(a,sun.sunriseMinutes));
    }
    return Math.round(100*overlap/60);
  });
}
function alignedHourlyOptions(yTitle,max=null,tooltipLabel=null){
  const tooltipCallbacks={
    title:items=>{
      const h=String(items[0]?.label??'').padStart(2,'0');
      return 'Timme: '+h+':00-'+h+':59';
    },
    ...(tooltipLabel?{label:tooltipLabel}:{})
  };
  return {responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
    plugins:{legend:{display:false},tooltip:{callbacks:tooltipCallbacks}},
    scales:{
      x:{grid:{display:false},offset:false,ticks:{autoSkip:false,maxRotation:0,minRotation:0,callback:(v,i)=>i%2===0?hours[i]:''}},
      y:{beginAtZero:max!=null,...(max!=null?{max}:{}),title:{display:true,text:yTitle},afterFit:s=>{s.width=72;}}
    }};
}
async function loadDateWeather(dateStr){
  if(!dateStr)return;
  const year=dateStr.slice(0,4);
  el('dateWeatherStatus').textContent='Laddar '+dateStr+'…';
  try{
    if(!dateYearCache[year]){
      const r=await fetch('daily/'+year+'.json',{cache:'no-store'});
      if(!r.ok)throw new Error('Ingen detaljdata för '+year);
      dateYearCache[year]=await r.json();
    }
    const day=dateYearCache[year].days[dateStr];
    if(!day)throw new Error('Inga observationer för valt datum.');
    el('dateWeatherStatus').textContent=dateStr;

    const tempHourly=hourlyAverage(day.temperature||[]);
    const tvals=(day.temperature||[]).map(r=>+r.value).filter(Number.isFinite);
    const minT=tvals.length?Math.min(...tvals):null,maxT=tvals.length?Math.max(...tvals):null;
    destroyChart('dateTemp');
    charts.dateTemp=new Chart(el('dateTemp'),{type:'line',data:{labels:hours,datasets:[{data:tempHourly,borderWidth:2,pointRadius:2,tension:.15}]},options:alignedHourlyOptions('°C')});

    const sun=solarTimes(dateStr),sunFractions=sunHourFractions(sun);
    destroyChart('dateSun');
    charts.dateSun=new Chart(el('dateSun'),{type:'bar',data:{labels:hours,datasets:[{data:sunFractions,borderWidth:1.5,borderColor:SUN_YELLOW,categoryPercentage:1,barPercentage:1,backgroundColor:'rgba(242,201,76,0.58)'}]},
      options:alignedHourlyOptions('%',100,c=>c.parsed.y+' % av timmen')});

    const precipHourly=hourlySum(day.precipitation_hourly||[]);
    destroyChart('datePrecip');
    charts.datePrecip=new Chart(el('datePrecip'),{type:'bar',data:{labels:hours,datasets:[{data:precipHourly,borderWidth:1.5,borderColor:PRECIP_DARK_BLUE,categoryPercentage:1,barPercentage:1,backgroundColor:'rgba(22,58,95,0.52)'}]},
      options:alignedHourlyOptions('mm',null,c=>(c.parsed.y??0).toLocaleString('sv-SE')+' mm')});

    el('dateSummary').innerHTML='<table><tbody>'+
      '<tr><th>Dygnsnederbörd</th><td>'+(day.precipitation_mm==null?'–':day.precipitation_mm.toLocaleString('sv-SE')+' mm')+'</td></tr>'+
      '<tr><th>Snödjup</th><td>'+(day.snow_cm==null?'–':day.snow_cm.toLocaleString('sv-SE')+' cm')+'</td></tr>'+
      '<tr><th>Temperatur min</th><td>'+(minT==null?'–':minT.toLocaleString('sv-SE')+' °C')+'</td></tr>'+
      '<tr><th>Temperatur max</th><td>'+(maxT==null?'–':maxT.toLocaleString('sv-SE')+' °C')+'</td></tr>'+
      '<tr><th>Soluppgång</th><td>'+(sun.sunrise??(sun.polarDay?'Midnattssol':'–'))+'</td></tr>'+
      '<tr><th>Solnedgång</th><td>'+(sun.sunset??(sun.polarDay?'Midnattssol':'–'))+'</td></tr>'+
      '<tr><th>Dagslängd</th><td>'+(sun.dayLength??'–')+'</td></tr>'+
      '</tbody></table><p class="hint">Soltider beräknade för Luleå-Kallax (65,5430° N, 22,1240° Ö) och visas i svensk lokal tid.</p>';

    const weatherByHour=hourlyWeather(day.weather||[]);
    const codes=[...new Set(weatherByHour.filter(Boolean))];
    destroyChart('dateWeather');
    const datasets=codes.map(code=>({label:weatherPhenomenon(code),data:weatherByHour.map(c=>c===code?100:null),borderWidth:0,categoryPercentage:1,barPercentage:1}));
    charts.dateWeather=new Chart(el('dateWeather'),{type:'bar',data:{labels:hours,datasets},options:{
      ...alignedHourlyOptions('registrerat väder',100),
      interaction:{mode:'nearest',intersect:true},
      plugins:{
        legend:{display:codes.length<=10},
        tooltip:{
          mode:'nearest',
          intersect:true,
          filter:item=>item.raw!=null,
          callbacks:{
            title:items=>{
              const h=String(items[0]?.label??'').padStart(2,'0');
              return 'Timme: '+h+':00-'+h+':59';
            },
            label:c=>c.dataset.label
          }
        }
      },
      scales:{
        x:{stacked:true,grid:{display:false},offset:false,ticks:{autoSkip:false,maxRotation:0,minRotation:0,callback:(v,i)=>i%2===0?hours[i]:''}},
        y:{stacked:true,min:0,max:100,ticks:{callback:v=>v+' %'},title:{display:true,text:'registrerat väder'},afterFit:s=>{s.width=72;}}
      }
    }});
  }catch(err){
    el('dateWeatherStatus').textContent=err.message;
    el('dateSummary').innerHTML='<p class="hint">'+err.message+'</p>';
    ['dateTemp','dateSun','datePrecip','dateWeather'].forEach(destroyChart);
  }
}
function setupDateWeather(){
  const picker=el('dateWeatherPicker');
  const cov=DATA.coverage.find(r=>r.name==='Lufttemperatur')||DATA.coverage[0];
  if(cov&&cov.min_date&&cov.min_date!=='-')picker.min=cov.min_date;
  if(cov&&cov.max_date&&cov.max_date!=='-'){picker.max=cov.max_date;picker.value=cov.max_date;}
  picker.addEventListener('change',()=>loadDateWeather(picker.value));
  if(picker.value)loadDateWeather(picker.value);
}
function updateRangeTrack(){
  const a=+el('rangeFrom').value,b=+el('rangeTo').value,min=+el('rangeFrom').min,max=+el('rangeFrom').max;
  const left=((a-min)/(max-min))*100,right=100-((b-min)/(max-min))*100;
  el('rangeSelected').style.left=left+'%';el('rangeSelected').style.right=right+'%';
}
function yearBoundsFromRows(rows,key='year'){
  const vals=(rows||[]).map(r=>Number(r?.[key])).filter(Number.isFinite);
  return vals.length?{min:Math.min(...vals),max:Math.max(...vals)}:null;
}
function pageYearBounds(page){
  const fallback={min:DATA.years[0],max:DATA.years[DATA.years.length-1]};
  const candidates={
    temp1:()=>yearBoundsFromRows(DATA.temperature?.annual||DATA.temperature?.monthly),
    temp2:()=>yearBoundsFromRows(DATA.temperature?.annual||DATA.temperature?.monthly),
    precip:()=>yearBoundsFromRows(DATA.precipitation?.annual||DATA.precipitation?.monthly_total),
    wind:()=>yearBoundsFromRows(DATA.wind?.speed_annual||DATA.wind?.speed_monthly),
    weather:()=>yearBoundsFromRows(DATA.weather?.codes),
    visibility:()=>yearBoundsFromRows(DATA.visibility?.annual||DATA.visibility?.monthly),
    humidity:()=>yearBoundsFromRows(DATA.humidity?.annual||DATA.humidity?.monthly),
    sunshine:()=>yearBoundsFromRows(DATA.sunshine?.annual||DATA.sunshine?.monthly_total),
    snow:()=>yearBoundsFromRows(DATA.snow?.annual_mean||DATA.snow?.annual_max),
    zerocross:()=>yearBoundsFromRows(DATA.zero_crossings),
    vegetation:()=>yearBoundsFromRows(DATA.vegetation?.climate_10y,'window_end'),
    lightning:()=>yearBoundsFromRows(DATA.lightning?.annual),
    dateweather:()=>yearBoundsFromRows(DATA.temperature?.annual||DATA.temperature?.monthly)
  };
  try{return candidates[page]?.()||fallback;}catch{return fallback;}
}
function applyPageYearBounds(page,resetToFull=true){
  if(!DATA||!el('yearFrom')||!el('yearTo')||!el('rangeFrom')||!el('rangeTo'))return;
  const b=pageYearBounds(page);
  const allYears=DATA.years.filter(y=>y>=b.min&&y<=b.max);
  if(!allYears.length)return;
  ['yearFrom','yearTo'].forEach(id=>el(id).innerHTML=allYears.map(y=>'<option value="'+y+'">'+y+'</option>').join(''));
  ['rangeFrom','rangeTo'].forEach(id=>{el(id).min=b.min;el(id).max=b.max;el(id).step=1;});
  let from=resetToFull?b.min:Math.max(b.min,Math.min(b.max,Number(el('yearFrom').value)||b.min));
  let to=resetToFull?b.max:Math.max(b.min,Math.min(b.max,Number(el('yearTo').value)||b.max));
  if(from>to){from=b.min;to=b.max;}
  el('yearFrom').value=String(from);el('yearTo').value=String(to);
  el('rangeFrom').value=String(from);el('rangeTo').value=String(to);
  el('rangeFromLabel').textContent=from;el('rangeToLabel').textContent=to;
  updateRangeTrack();
}

function syncYear(source,value,renderNow=true){
  let a=+el('yearFrom').value,b=+el('yearTo').value;
  if(source==='from')a=+value;else b=+value;
  if(a>b){if(source==='from')b=a;else a=b;}
  el('yearFrom').value=a;el('yearTo').value=b;
  el('rangeFrom').value=a;el('rangeTo').value=b;
  el('rangeFromLabel').textContent=a;el('rangeToLabel').textContent=b;
  updateRangeTrack();
  if(renderNow)render();
}
function setupTabs(){
  document.querySelectorAll('#tabs button').forEach(btn=>btn.addEventListener('click',()=>{
    const done=beginGlobalLoading('Laddar '+btn.textContent.trim()+'…');
    setTimeout(async()=>{
      try{
        document.querySelectorAll('#tabs button').forEach(x=>x.classList.remove('active'));
        document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));
        btn.classList.add('active');
        el('page-'+btn.dataset.page).classList.add('active');
        document.body.classList.toggle('dateweather-active',btn.dataset.page==='dateweather');
        document.body.classList.toggle('temp2-active',btn.dataset.page==='temp2');
        document.body.classList.toggle('algae-active',btn.dataset.page==='algae');
        applyPageYearBounds(btn.dataset.page,true);
        render();
        if(btn.dataset.page==='seaice')await initSeaIceMap();
        if(btn.dataset.page==='algae')await initAlgaeMap();
        if(btn.dataset.page==='snowmap')await initSnowMap();
        if(btn.dataset.page==='lightning')await initLightningMap();
        setTimeout(()=>{
          Object.values(charts).forEach(c=>c.resize());
          if(seaIceLeafletMap)seaIceLeafletMap.invalidateSize();
          if(algaeLeafletMap)algaeLeafletMap.invalidateSize();
          if(snowMapLeaflet)snowMapLeaflet.invalidateSize();
          if(lightningMapLeaflet)lightningMapLeaflet.invalidateSize();
        },80);
      }finally{
        setTimeout(done,100);
      }
    },0);
  }));
}

function setupFilters(){const years=DATA.years,min=years[0],max=years[years.length-1];['yearFrom','yearTo'].forEach(id=>el(id).innerHTML=years.map(y=>'<option value="'+y+'">'+y+'</option>').join(''));el('yearFrom').value=min;el('yearTo').value=max;['rangeFrom','rangeTo'].forEach(id=>{el(id).min=min;el(id).max=max;el(id).step=1;});el('rangeFrom').value=min;el('rangeTo').value=max;el('rangeFromLabel').textContent=min;el('rangeToLabel').textContent=max;updateRangeTrack();const activePage=document.querySelector('#tabs button.active')?.dataset.page||'temp1';applyPageYearBounds(activePage,true);el('yearFrom').addEventListener('change',e=>syncYear('from',e.target.value,true));
el('yearTo').addEventListener('change',e=>syncYear('to',e.target.value,true));
el('rangeFrom').addEventListener('input',e=>syncYear('from',e.target.value,false));
el('rangeTo').addEventListener('input',e=>syncYear('to',e.target.value,false));
el('rangeFrom').addEventListener('change',e=>syncYear('from',e.target.value,true));
el('rangeTo').addEventListener('change',e=>syncYear('to',e.target.value,true));
el('month').addEventListener('change',render);
el('tempMetric').addEventListener('change',render);
el('weatherCode').addEventListener('change',render);
el('resetFilters').addEventListener('click',()=>{
  const activePage=document.querySelector('#tabs button.active')?.dataset.page||'temp1';
  applyPageYearBounds(activePage,true);
  el('month').value='0';render();
});}
function setupWeatherCodes(){
  const types=[...new Set(DATA.weather.codes.map(r=>normalizedWeatherPhenomenon(r.code,r.year)))].sort((a,b)=>a.localeCompare(b,'sv'));
  el('weatherCode').innerHTML='<option value="all">Alla vädertyper</option>'+types.map(t=>'<option value="'+t+'">'+t+'</option>').join('');
  el('weatherCode').value='all';
}
const initialLoadingDone=beginGlobalLoading('Laddar rapport…');
fetch('dashboard_data.json',{cache:'no-store'})
  .then(r=>{if(!r.ok)throw new Error('dashboard_data.json saknas');return r.json();})
  .then(d=>{
    DATA=d;
    el('updated').textContent='Data uppdaterad: '+(d.generated_at||'okänt');
    el('weatherSource').href=d.weather.source_url;
    setupWeatherCodes();setupTemp2Slider();setupTabs();setupSeaIceSeasonControls();setupAlgaeSeasonControls();setupSnowMapControls();setupLightningMapControls();setupFilters();setupDateWeather();render();
  })
  .catch(err=>{document.querySelector('main').innerHTML='<div class="chart-card"><h2>Rapportdata saknas</h2><p>'+err.message+'</p></div>';})
  .finally(()=>setTimeout(initialLoadingDone,100));