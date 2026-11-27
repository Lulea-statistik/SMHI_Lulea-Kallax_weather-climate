import { test, expect } from '@playwright/test';

const pages = ['start','temp1','temp2','precip','weather','wind','visibility','pressure','humidity','sunshine','snow','zerocross','vegetation','snowmap','lightning','seaice','algae','sealevel','dateweather','data'];
const maps = {snowmap:'snowMap',lightning:'lightningMap',seaice:'seaIceMap',algae:'algaeMap'};
const charts = {temp1:'tempAnnual',temp2:'tempProfiles',precip:'precipAnnual',weather:'weatherCodes',wind:'windSpeed',visibility:'visibilityAnnual',pressure:'pressureAnnual',humidity:'humidityAnnual',sunshine:'sunAnnual',snow:'snowMeanAnnual',zerocross:'zeroAnnual',vegetation:'vegetationLength',snowmap:'snowMapMean',lightning:'lightningAnnual',seaice:'seaIceDaily',algae:'algaeDailyClasses',sealevel:'seaLevelHistory',dateweather:'dateTemp'};
async function open(page,id,query=''){
  await page.goto('/index.html#'+id+query,{waitUntil:'domcontentloaded'});
  await expect(page.locator('#page-'+id)).toBeVisible({timeout:60000});
  await expect(page.locator('#globalLoading')).toHaveClass(/is-hidden/,{timeout:90000});
  await expect(page.locator('#page-'+id+' .page-load-error')).toHaveCount(0);
}
function monitor(page){
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.url().startsWith('http://127.0.0.1:8765/')&&r.status()>=400&&!r.url().endsWith('/favicon.ico'))errors.push(r.status()+' '+r.url());});
  return errors;
}
for(const id of pages){
  test('page '+id,async({page},info)=>{
    const errors=monitor(page);
    await open(page,id);
    await expect(page.locator('#tabs button.active')).toHaveAttribute('data-page',id);
    if(charts[id]){
      await expect.poll(()=>page.evaluate(canvasId=>{
        const c=window.Chart?.getChart(canvasId);
        return !!c&&c.data.datasets.some(d=>Array.isArray(d.data)&&d.data.some(v=>v!==null&&v!==undefined));
      },charts[id]),{timeout:60000}).toBe(true);
    }
    const trendColors=await page.evaluate(id=>[...document.querySelectorAll('#page-'+id+' canvas')].flatMap(c=>(window.Chart?.getChart(c)?.data.datasets||[]).filter(d=>d.label?.startsWith('Linjär trend')).map(d=>d.borderColor)),id);
    expect(trendColors.every(c=>c==='#ff6384')).toBe(true);
    if(maps[id])await expect(page.locator('#'+maps[id])).toHaveClass(/leaflet-container/,{timeout:60000});
    if(id==='data')await expect(page.locator('#dataStatus li').first()).toBeVisible();
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
    expect(overflow,'document horizontal overflow').toBeLessThanOrEqual(4);
    await info.attach('page-'+id,{body:await page.screenshot(),contentType:'image/png'});
    expect(errors).toEqual([]);
  });
}
test('temperature filters, share link, data table and focus',async({page})=>{
  const errors=monitor(page);
  await open(page,'temp1','?from=1991&to=2020&month=1&station=162860');
  await expect(page.locator('#yearFrom')).toHaveValue('1991');
  await expect(page.locator('#yearTo')).toHaveValue('2020');
  await expect(page.locator('#month')).toHaveValue('1');
  await page.locator('#month').selectOption('2');
  await expect.poll(()=>new URL(page.url()).hash).toContain('month=2');
  await page.reload({waitUntil:'domcontentloaded'});
  await expect(page.locator('#month')).toHaveValue('2',{timeout:60000});
  const card=page.locator('#tempAnnual').locator('xpath=ancestor::div[contains(@class,"chart-card")][1]');
  await card.locator('summary').click();
  await expect(card.locator('tbody tr').first()).toBeVisible();
  await card.locator('.chart-focus-button').click();
  await expect(page.locator('dialog.chart-focus-dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('dialog.chart-focus-dialog')).not.toBeVisible();
  expect(errors).toEqual([]);
});
test('topic navigation',async({page})=>{
  await open(page,'start');
  await page.locator('.topic-menu button').filter({hasText:'Väderobservationer'}).click();
  await expect(page.locator('#tabs button[data-page="precip"]')).toBeVisible();
  await page.locator('#tabs button[data-page="precip"]').click();
  await expect(page.locator('#page-precip')).toBeVisible();
  await expect(page.locator('#globalLoading')).toHaveClass(/is-hidden/,{timeout:90000});
  await page.goBack();
  await expect(page.locator('#page-temp1')).toBeVisible({timeout:60000});
});

test('combined solar chart has comparable units and preserves missing data',async({page})=>{
  await open(page,'dateweather');
  await expect.poll(()=>page.evaluate(()=>window.Chart?.getChart('dateSun')?.data.datasets.length),{timeout:60000}).toBe(2);
  const data=await page.evaluate(()=>{const c=window.Chart.getChart('dateSun');return {max:c.options.scales.y.max,series:c.data.datasets.map(d=>d.data)};});
  expect(data.max).toBe(60);
  for(const values of data.series){expect(values).toHaveLength(24);expect(values.every(v=>v===null||(Number.isFinite(v)&&v>=0&&v<=60))).toBe(true);}
  await expect(page.locator('#dateSunshine')).toHaveCount(0);
});

test('start has one shortcut per non-start page in matching navigation order',async({page})=>{
  await open(page,'start');
  const expected=await page.locator('#tabs button[data-page]').evaluateAll(nodes=>nodes.map(n=>n.dataset.page).filter(p=>p!=='start'));
  const cards=await page.locator('#page-start button[data-go-page]').evaluateAll(nodes=>nodes.map(n=>n.dataset.goPage));
  expect(cards).toEqual(expected);
  await expect(page.locator('.shortcut-group-maps button')).toHaveCount(7);
  await expect(page.locator('#page-start .shortcut-icon svg use')).toHaveCount(19);
  await page.locator('#page-start button[data-go-page="temp2"]').click();
  await expect(page.locator('#page-temp2')).toBeVisible({timeout:60000});
});
