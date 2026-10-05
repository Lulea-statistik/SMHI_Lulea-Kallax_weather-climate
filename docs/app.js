let DATA=null;const charts={};const months=['Jan','Feb','Mar','Apr','Maj','Jun','Jul','Aug','Sep','Okt','Nov','Dec'];const hours=Array.from({length:24},(_,i)=>String(i).padStart(2,'0'));const MONTH_GREEN='#4f9d69';const SUN_YELLOW='#f2c94c';const PRECIP_DARK_BLUE='#163a5f';let temp2Start=null;const dateYearCache={};
const el=id=>document.getElementById(id);
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
function setupTemp2Slider(){
  const years=[...DATA.years].sort((a,b)=>a-b);
  const minStart=years[0],maxStart=years[years.length-1]-9;
  const minCenter=minStart+4.5,maxCenter=maxStart+4.5;
  temp2Start=maxStart;
  const s=el('temp2Start');
  s.min=minCenter;s.max=maxCenter;s.step=1;s.value=temp2Start+4.5;
  s.addEventListener('input',e=>{temp2Start=Math.round((+e.target.value)-4.5);renderTemp2();});
  renderTemp2();
}
function renderTemp2(){
  const start=temp2Start??([...DATA.years].sort((a,b)=>a-b).slice(-10)[0]);
  const years=Array.from({length:10},(_,i)=>start+i).filter(y=>DATA.years.includes(y));
  el('temp2PeriodLabel').textContent=start+'–'+(start+9);

  const selectedMonth=+(el('month')?.value||0);
  if(selectedMonth){
    const vals=years.map(y=>{
      const r=DATA.temperature.monthly.find(x=>x.year===y&&x.month===selectedMonth);
      return r?r.avg:null;
    });
    lineChart('tempProfiles',years,[{label:months[selectedMonth-1],data:vals,borderColor:MONTH_GREEN,backgroundColor:MONTH_GREEN}],'°C');
  }else{
    lineChart('tempProfiles',months,years.map(y=>({
      label:String(y),
      data:[...Array(12)].map((_,i)=>{
        const r=DATA.temperature.monthly.find(x=>x.year===y&&x.month===i+1);
        return r?r.avg:null;
      })
    })),'°C');
  }
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

function renderLightning(f){
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
  barChart('lightningDays',years,dayVals,'dygn','rgba(99,102,241,0.58)');

  const monthRows=(L.monthly_by_year||[]).filter(r=>r.year>=f.from&&r.year<=f.to);
  const monthAgg=months.map((_,i)=>{
    const rr=monthRows.filter(r=>r.month===i+1);
    const yearsN=new Set(rr.map(r=>r.year)).size||1;
    const out={};
    classes.forEach(x=>out[x.key]=rr.reduce((s,r)=>s+(r[x.key]||0),0)/yearsN);
    return out;
  });
  destroyChart('lightningMonthly');
  charts.lightningMonthly=new Chart(el('lightningMonthly'),{
    type:'bar',
    data:{labels:months,datasets:classes.map(x=>({label:x.label,stack:'surface',backgroundColor:x.color,borderWidth:0,data:monthAgg.map(r=>r[x.key]||0)}))},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+c.parsed.y.toFixed(1).replace('.',',')}}},
      scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,beginAtZero:true,title:{display:true,text:'genomsnitt per år'}}}}
  });

  const uncertaintyTypes=[
    {key:'mainland__sea',label:'Fastland ↔ hav'},
    {key:'islands__sea',label:'Öar ↔ hav'},
    {key:'inland_water__mainland',label:'Fastland ↔ inlandsvatten'},
    {key:'inland_water__islands',label:'Öar ↔ inlandsvatten'},
    {key:'inland_water__sea',label:'Hav ↔ inlandsvatten'},
    {key:'islands__mainland',label:'Fastland ↔ öar'}
  ];
  const visibleTypes=uncertaintyTypes.filter(t=>rows.some(r=>((r.uncertainty_pairs||{})[t.key]||0)>0));
  const uncertaintyDatasets=visibleTypes.map((t,i)=>({
    label:t.label,
    backgroundColor:['rgba(107,114,128,0.68)','rgba(156,163,175,0.68)','rgba(75,85,99,0.58)','rgba(209,213,219,0.88)','rgba(148,163,184,0.72)','rgba(120,113,108,0.62)'][i%6],
    borderWidth:0,
    data:rows.map(r=>((r.uncertainty_pairs||{})[t.key]||0))
  }));
  uncertaintyDatasets.push({
    label:'Kommungräns',
    backgroundColor:'rgba(17,24,39,0.78)',
    borderWidth:0,
    data:rows.map(r=>r.municipality_boundary_uncertain_500||0)
  });
  destroyChart('lightningUncertain');
  charts.lightningUncertain=new Chart(el('lightningUncertain'),{
    type:'bar',
    data:{labels:years,datasets:uncertaintyDatasets},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true},tooltip:{callbacks:{label:c=>c.dataset.label+': '+Math.round(c.parsed.y)}}},
      scales:{x:{grid:{display:false}},y:{beginAtZero:true,title:{display:true,text:'urladdningar'},ticks:{precision:0}}}}
  });
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
  ['seaIceDaily','seaIceSeasonMax','seaIceThickness','seaIceFast','seaIceLength'].forEach(id=>{
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
      {label:'Isutbredning',data:timeline.rows.map(r=>r?r.ice_share_pct:null),borderWidth:2,pointRadius:0,spanGaps:false},
      {label:'Data saknas – sista kända värde',data:iceTail,borderColor:'#9ca3af',backgroundColor:'#9ca3af',borderDash:[6,4],borderWidth:2,pointRadius:0,tension:0,spanGaps:false}
    ],'%');

    lineChart('seaIceThickness',timeline.labels,[
      {label:'Medeltjocklek',data:timeline.rows.map(r=>r?r.mean_ice_thickness_cm:null),borderWidth:2,pointRadius:0,spanGaps:false},
      {label:'Maximal tjocklek',data:timeline.rows.map(r=>r?r.max_ice_thickness_cm:null),borderWidth:2,pointRadius:0,spanGaps:false},
      {label:'Saknad data – medel',data:meanTail,borderColor:'#9ca3af',backgroundColor:'#9ca3af',borderDash:[6,4],borderWidth:2,pointRadius:0,tension:0,spanGaps:false},
      {label:'Saknad data – max',data:maxTail,borderColor:'#6b7280',backgroundColor:'#6b7280',borderDash:[3,4],borderWidth:2,pointRadius:0,tension:0,spanGaps:false}
    ],'cm');
  }else{
    destroyChart('seaIceDaily');
    destroyChart('seaIceThickness');
  }

  const labels=seasonal.map(r=>r.season);
  barChart('seaIceSeasonMax',labels,seasonal.map(r=>r.max_ice_share_pct),'%');
  barChart('seaIceFast',labels,seasonal.map(r=>r.max_fast_ice_share_pct),'%');
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
  const vaVals=va.map(r=>Math.round(r.avg));
  destroyChart('visibilityAnnual');
  charts.visibilityAnnual=new Chart(el('visibilityAnnual'),{type:'line',data:{labels:va.map(r=>r.year),datasets:[{data:vaVals,borderWidth:2,pointRadius:0,tension:.15}]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>Math.round(c.parsed.y)+' meter'}}},
      scales:{x:{grid:{display:false}},y:{title:{display:true,text:'meter'},ticks:{precision:0,callback:v=>Math.round(v)}}}}});
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
function setupTabs(){document.querySelectorAll('#tabs button').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('#tabs button').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));btn.classList.add('active');el('page-'+btn.dataset.page).classList.add('active');document.body.classList.toggle('dateweather-active',btn.dataset.page==='dateweather');document.body.classList.toggle('temp2-active',btn.dataset.page==='temp2');setTimeout(()=>Object.values(charts).forEach(c=>c.resize()),50);}));}
function setupFilters(){const years=DATA.years,min=years[0],max=years[years.length-1];['yearFrom','yearTo'].forEach(id=>el(id).innerHTML=years.map(y=>'<option value="'+y+'">'+y+'</option>').join(''));el('yearFrom').value=min;el('yearTo').value=max;['rangeFrom','rangeTo'].forEach(id=>{el(id).min=min;el(id).max=max;el(id).step=1;});el('rangeFrom').value=min;el('rangeTo').value=max;el('rangeFromLabel').textContent=min;el('rangeToLabel').textContent=max;updateRangeTrack();el('yearFrom').addEventListener('change',e=>syncYear('from',e.target.value,true));
el('yearTo').addEventListener('change',e=>syncYear('to',e.target.value,true));
el('rangeFrom').addEventListener('input',e=>syncYear('from',e.target.value,false));
el('rangeTo').addEventListener('input',e=>syncYear('to',e.target.value,false));
el('rangeFrom').addEventListener('change',e=>syncYear('from',e.target.value,true));
el('rangeTo').addEventListener('change',e=>syncYear('to',e.target.value,true));
el('month').addEventListener('change',render);
el('tempMetric').addEventListener('change',render);
el('weatherCode').addEventListener('change',render);
el('resetFilters').addEventListener('click',()=>{
  el('yearFrom').value=min;el('yearTo').value=max;
  el('rangeFrom').value=min;el('rangeTo').value=max;
  el('rangeFromLabel').textContent=min;el('rangeToLabel').textContent=max;
  el('month').value='0';updateRangeTrack();render();
});}
function setupWeatherCodes(){
  const types=[...new Set(DATA.weather.codes.map(r=>normalizedWeatherPhenomenon(r.code,r.year)))].sort((a,b)=>a.localeCompare(b,'sv'));
  el('weatherCode').innerHTML='<option value="all">Alla vädertyper</option>'+types.map(t=>'<option value="'+t+'">'+t+'</option>').join('');
  el('weatherCode').value='all';
}
fetch('dashboard_data.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('dashboard_data.json saknas');return r.json();}).then(d=>{DATA=d;el('updated').textContent='Data uppdaterad: '+(d.generated_at||'okänt');el('weatherSource').href=d.weather.source_url;setupWeatherCodes();setupTemp2Slider();setupTabs();setupFilters();setupDateWeather();render();}).catch(err=>{document.querySelector('main').innerHTML='<div class="chart-card"><h2>Rapportdata saknas</h2><p>'+err.message+'</p></div>';});