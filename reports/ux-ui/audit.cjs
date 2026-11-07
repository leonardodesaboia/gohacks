const {chromium}=require('C:/Users/User/AppData/Local/npm-cache/_npx/381cec31605a419a/node_modules/playwright');
const fs=require('fs');
const path=require('path');
const {pathToFileURL}=require('url');
const out=__dirname;
const results={screens:[],errors:[],checks:[]};
async function snapshot(page,name){
  await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});
  const info=await page.evaluate(()=>({
    viewport:innerWidth,width:document.documentElement.scrollWidth,
    heading:document.querySelector('h1')?.innerText,
    text:document.body.innerText,
    overflows:[...document.querySelectorAll('main *,[role="tabpanel"] *')].filter(el=>{
      const r=el.getBoundingClientRect();const cs=getComputedStyle(el);
      return r.width>0&&cs.position!=='absolute'&&(r.right>innerWidth+2||r.left< -2);
    }).slice(0,18).map(el=>({tag:el.tagName,cls:el.className,text:el.innerText?.slice(0,90),width:el.getBoundingClientRect().width})),
    tabs:[...document.querySelectorAll('[role="tab"]')].map(el=>({name:el.innerText,selected:el.getAttribute('aria-selected'),controls:el.getAttribute('aria-controls')})),
    buttons:[...document.querySelectorAll('button')].filter(el=>el.getBoundingClientRect().width).map(el=>({name:el.innerText,disabled:el.disabled,height:el.getBoundingClientRect().height})),
    svgTexts:[...document.querySelectorAll('svg text')].filter(el=>el.getBoundingClientRect().width).map(el=>({text:el.textContent,box:el.getBoundingClientRect().toJSON()}))
  }));
  results.screens.push({name,...info});
}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Users/User/AppData/Local/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.on('pageerror',e=>results.errors.push(e.message));
 await page.goto(pathToFileURL(path.resolve('site/index.html')).href);
 await snapshot(page,'static-desktop-initial');
 await page.getByRole('tab',{name:'Fila do analista',exact:true}).click();
 await snapshot(page,'static-initial-queue');
 for(let i=0;i<3;i++)await page.locator('#avancar').click();
 await snapshot(page,'static-desktop-queue');
 await page.getByText('Ver evidências',{exact:true}).first().click();
 await snapshot(page,'static-desktop-evidence');
 for(const width of [390,320]){
  await page.setViewportSize({width,height:844});
  await snapshot(page,'static-mobile-'+width+'-evidence');
 }
 await page.setViewportSize({width:1440,height:1000});
 await page.getByRole('tab',{name:'Visão geral',exact:true}).click();
 await snapshot(page,'static-desktop-overview');
 await page.getByRole('tab',{name:'Lote',exact:true}).click();
 await page.getByText('Ver a lista dos títulos',{exact:true}).click();
 await snapshot(page,'static-desktop-batch');
 await page.getByRole('tab',{name:'Quem foi chamado',exact:true}).click();
 await page.getByText('Ver dossiê',{exact:true}).first().click();
 await snapshot(page,'static-desktop-contacts');
 await page.getByRole('tab',{name:'Registro técnico',exact:true}).click();
 await snapshot(page,'static-desktop-register');
 await page.locator('#pre').click();
 await snapshot(page,'static-end');
 await page.getByRole('button',{name:'Fila inteira no corte',exact:true}).click();
 await page.locator('#pre').click();
 await page.getByRole('tab',{name:'Quem foi chamado',exact:true}).click();
 await page.setViewportSize({width:390,height:844});
 await snapshot(page,'static-mobile-approvals');
 await page.setViewportSize({width:1440,height:1000});
 await page.getByRole('tab',{name:'Visão geral',exact:true}).click();
 await snapshot(page,'static-cut-overview');
 const live=await browser.newPage({viewport:{width:1440,height:1000}});
 live.on('pageerror',e=>results.errors.push(e.message));
 await live.goto('http://127.0.0.1:8511');
 await live.getByRole('heading',{level:1}).waitFor({timeout:60000});
 await snapshot(live,'streamlit-desktop-initial');
 await live.getByRole('button',{name:'Avançar 1 hora',exact:true}).click();
 await live.waitForFunction(()=>document.querySelector('.sx-relogio-num')?.textContent.includes('15:00'));
 await live.getByRole('button',{name:'Avançar 1 hora',exact:true}).click();
 await live.waitForFunction(()=>document.querySelector('.sx-relogio-num')?.textContent.includes('16:00'));
 await snapshot(live,'streamlit-clock-16');
 await live.getByRole('button',{name:'Avançar 1 hora',exact:true}).click();
 await live.waitForFunction(()=>document.querySelector('.sx-titulo')?.textContent.includes('28 pagamentos'));
 await live.getByRole('tab',{name:'Fila do analista',exact:true}).click();
 await snapshot(live,'streamlit-desktop-queue');
 await live.setViewportSize({width:390,height:844});
 await live.getByText('Ver evidências',{exact:true}).first().click();
 await snapshot(live,'streamlit-mobile-evidence');
 await browser.close();
 fs.writeFileSync(path.join(out,'browser-audit.json'),JSON.stringify(results,null,2));
 console.log(JSON.stringify({screens:results.screens.map(s=>({name:s.name,viewport:s.viewport,width:s.width,overflows:s.overflows.length})),errors:results.errors}));
})().catch(e=>{fs.writeFileSync(path.join(out,'browser-audit.json'),JSON.stringify(results,null,2));console.error(e);process.exit(1)});
