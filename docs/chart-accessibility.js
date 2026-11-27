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
    const head=table.createTHead().insertRow();addCell(head,'th','Period / kategori').scope='col';
    sets.forEach((d,i)=>addCell(head,'th',d.label||'Serie '+(i+1)).scope='col');
    const body=table.createTBody();
    labels.forEach((label,i)=>{
      const row=body.insertRow();addCell(row,'th',format(label)).scope='row';
      sets.forEach(d=>{const v=d.data?.[i];addCell(row,'td',format(v&&typeof v==='object'&&!Array.isArray(v)?(v.y??v.r??null):Array.isArray(v)?v.map(format).join(' – '):v));});
    });
    target.append(table);
  }
  Chart.register({id:'accessibleDataTable',afterUpdate(chart){
    const canvas=chart.canvas,card=canvas.closest('.chart-card');if(!card)return;
    const heading=card.querySelector('h2')?.textContent||'Diagram';
    canvas.setAttribute('role','img');canvas.setAttribute('aria-label',heading);
    let details=panels.get(canvas);
    if(!details){
      details=document.createElement('details');details.className='chart-data-alternative';
      const summary=document.createElement('summary');summary.textContent='Visa diagramdata som tabell';
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
