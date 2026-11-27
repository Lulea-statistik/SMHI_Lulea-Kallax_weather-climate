/* Accessible data alternative to Chart.js canvas charts. */
(() => {
  if(!window.Chart)return;
  const format=v=>v==null?'Saknas':typeof v==='number'?v.toLocaleString('sv-SE',{maximumFractionDigits:3}):String(v);
  const panels=new WeakMap();
  function addCell(row,tag,value){const c=document.createElement(tag);c.textContent=value;row.append(c);return c;}
  function fill(chart,details){
    const target=details.querySelector('.chart-data-content');
    target.replaceChildren();
    const labels=chart.data.labels||[],sets=chart.data.datasets||[];
    if(!labels.length||!sets.length){target.textContent='Inga tabellvärden i aktuellt urval.';return;}
    const table=document.createElement('table'),caption=document.createElement('caption');
    caption.textContent=chart.canvas.getAttribute('aria-label')||'Diagramvärden';table.append(caption);
    const head=table.createTHead().insertRow();
    const headers=['Period / kategori',...sets.map((d,i)=>{const scale=chart.scales?.[d.yAxisID||'y']||chart.scales?.r;const axis=scale?.options?.title;const unit=axis?.display?axis.text:'';return (d.label||'Serie '+(i+1))+(unit?' · '+unit:'');})];
    const raw=v=>v&&typeof v==='object'&&!Array.isArray(v)?(v.y??v.r??null):v;
    const rows=labels.map((label,i)=>[label,...sets.map(d=>raw(d.data?.[i]))]).filter(r=>r[0]!=='');
    const body=table.createTBody();
    const state=details._chartSort||{column:0,direction:chart.canvas.id==='seaIceDaily'||chart.canvas.id==='seaIceThickness'?-1:1};
    const ths=[];
    const missing=v=>v==null||(typeof v==='number'&&!Number.isFinite(v));
    const compare=(a,b)=>typeof a==='number'&&typeof b==='number'?a-b:String(a).localeCompare(String(b),'sv',{numeric:true});
    function render(){
      body.replaceChildren();
      const sorted=rows.slice().sort((a,b)=>{
        const x=a[state.column],y=b[state.column];
        if(missing(x)||missing(y))return Number(missing(x))-Number(missing(y));
        return state.direction*compare(x,y);
      });
      for(const values of sorted){
        const row=body.insertRow();
        values.forEach((v,i)=>{const cell=addCell(row,i===0?'th':'td',Array.isArray(v)?v.map(format).join(' – '):format(v));if(i===0)cell.scope='row';});
      }
      ths.forEach((th,i)=>{
        th.setAttribute('aria-sort',i===state.column?(state.direction===1?'ascending':'descending'):'none');
        th.firstChild.textContent=headers[i]+(i===state.column?(state.direction===1?' ↑':' ↓'):' ↕');
      });
    }
    headers.forEach((label,i)=>{
      const th=addCell(head,'th','');th.scope='col';ths.push(th);
      const button=document.createElement('button');button.type='button';button.className='chart-sort-button';
      button.addEventListener('click',()=>{state.direction=state.column===i?-state.direction:(i===0?1:-1);state.column=i;details._chartSort=state;render();});
      th.append(button);
    });
    render();
    target.append(table);
  }
  Chart.register({id:'accessibleDataTable',afterDestroy(chart,args,options){const canvas=chart.canvas;if(canvas){const details=panels.get(canvas);details?.remove();panels.delete(canvas);}},beforeDestroy(chart){const canvas=chart.canvas;const details=panels.get(canvas);details?.remove();panels.delete(canvas);},afterUpdate(chart){
    const canvas=chart.canvas,card=canvas.closest('.chart-card');if(!card)return;
    const heading=card.querySelector('h2')?.textContent||'Diagram';
    canvas.setAttribute('role','img');canvas.setAttribute('aria-label',heading);
    let details=panels.get(canvas);
    if(!details){
      details=document.createElement('details');details.className='chart-data-alternative';
      const summary=document.createElement('summary');summary.textContent='Visa diagramdata som tabell: '+heading;
      const content=document.createElement('div');content.className='chart-data-content';
      details.append(summary,content);card.append(details);panels.set(canvas,details);
      details.addEventListener('toggle',()=>{const active=Chart.getChart(canvas);if(details.open&&active)fill(active,details);});
    }
    if(details.open)fill(chart,details);
  }});
  document.querySelectorAll('.chart-card canvas').forEach(canvas=>{
    canvas.setAttribute('role','img');canvas.setAttribute('aria-label',canvas.closest('.chart-card')?.querySelector('h2')?.textContent||'Diagram');
  });
})();
