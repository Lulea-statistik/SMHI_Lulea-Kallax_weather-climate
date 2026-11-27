/* Chart focus: move the existing chart card, preserving its live chart and data. */
(() => {
  const dialog=document.createElement('dialog');
  dialog.className='chart-focus-dialog';dialog.setAttribute('aria-label','Diagram i fokusläge');
  const close=document.createElement('button');close.type='button';close.className='chart-focus-close';close.textContent='Stäng fokusläge';
  dialog.append(close);document.body.append(dialog);
  let card=null,placeholder=null,trigger=null;
  const resize=()=>requestAnimationFrame(()=>card?.querySelectorAll('canvas').forEach(c=>Chart.getChart(c)?.resize()));
  const restore=()=>{if(!card)return;const old=card;placeholder.replaceWith(old);placeholder=null;card=null;requestAnimationFrame(()=>{old.querySelectorAll('canvas').forEach(c=>Chart.getChart(c)?.resize());trigger?.focus();});};
  close.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',restore);
  dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
  document.querySelectorAll('.chart-card').forEach(c=>{
    if(!c.querySelector('canvas')||c.querySelector('.seaice-map'))return;
    const button=document.createElement('button');button.type='button';button.className='chart-focus-button';button.textContent='Fokusläge';
    button.setAttribute('aria-label','Fokusläge: '+(c.querySelector('h2')?.textContent||'diagram'));
    c.prepend(button);button.addEventListener('click',()=>{if(card)return;card=c;trigger=button;placeholder=document.createElement('div');placeholder.style.minHeight=c.offsetHeight+'px';c.replaceWith(placeholder);dialog.append(c);dialog.showModal();resize();});
  });
  if(window.Chart){Chart.defaults.font.family='Inter, system-ui, sans-serif';Chart.defaults.font.size=13;Chart.defaults.locale='sv-SE';}
})();
