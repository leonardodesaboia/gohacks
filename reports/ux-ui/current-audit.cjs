const {chromium}=require('C:/Users/User/AppData/Local/npm-cache/_npx/381cec31605a419a/node_modules/playwright');
const fs=require('fs'),path=require('path'),{pathToFileURL}=require('url');
const results=[];
async function snap(p,name){
 await p.screenshot({path:path.join(__dirname,name+'.png'),fullPage:true});
 results.push({name,...await p.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,text:document.body.innerText,
  fields:[...document.querySelectorAll('.sx-campos:visible')].map(x=>x.textContent)
 })).catch(async()=>p.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,text:document.body.innerText,
  fields:[...document.querySelectorAll('.sx-campos')].filter(el=>el.getBoundingClientRect().width).map(el=>({width:el.getBoundingClientRect().width,columns:getComputedStyle(el).gridTemplateColumns,dd:[...el.querySelectorAll('dd')].map(d=>({text:d.textContent,width:d.getBoundingClientRect().width}))}))})))});
}
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:'C:/Users/User/AppData/Local/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe'});
try{
const p=await browser.newPage({viewport:{width:1440,height:1000}});
await p.goto(pathToFileURL(path.join(__dirname,'current.html')).href);
await snap(p,'current-initial');
for(let i=0;i<3;i++){
 try{await p.locator('#avancar').click({timeout:1500})}
 catch(e){results.push({name:'pointer-blocked-'+i,error:e.message});await snap(p,'current-pointer-blocked-'+i);await p.addStyleTag({content:'.sx-chave.sx-tile--fora::after { display:none !important; }'});results.push({name:'diagnostic-browser-only-css',note:'Disable legend pseudo-element only in this browser session so other flows can be inspected; product unchanged.'});await p.locator('#avancar').focus();await p.keyboard.press('Enter')}
}
await snap(p,'current-desktop-now');
await p.getByRole('tab',{name:'Fila do analista',exact:true}).click();
await p.locator('summary:visible').filter({hasText:'Ver evidências'}).first().click();
await p.setViewportSize({width:390,height:844});await snap(p,'current-mobile-evidence');
await p.setViewportSize({width:320,height:844});await snap(p,'current-320-evidence');
await p.setViewportSize({width:768,height:1024});await snap(p,'current-tablet-queue');
await p.setViewportSize({width:1440,height:1000});
await p.getByRole('tab',{name:'Quem foi chamado',exact:true}).click();
await p.locator('summary:visible').filter({hasText:/Ver dossi/}).first().click();await snap(p,'current-contacts');
await p.getByRole('tab',{name:'Registro técnico',exact:true}).click();await snap(p,'current-register');
await p.locator('#pre').click();await snap(p,'current-end');
results.push({name:'end-button-states',advanceDisabled:await p.locator('#avancar').isDisabled(),preDisabled:await p.locator('#pre').isDisabled()});
await p.getByRole('tab',{name:'Agora',exact:true}).focus();
await p.keyboard.press('ArrowRight');results.push({name:'keyboard-arrow',selected:await p.getByRole('tab',{selected:true}).innerText()});
await p.keyboard.press('End');results.push({name:'keyboard-end',selected:await p.getByRole('tab',{selected:true}).innerText()});
const live=await browser.newPage({viewport:{width:390,height:844}});
await live.goto('http://127.0.0.1:8511');await live.getByRole('heading',{level:1}).waitFor({timeout:60000});
await live.addStyleTag({content:'.sx-chave.sx-tile--fora::after { display:none !important; }'});
for(const hour of ['15:00','16:00','17:00']){
 await live.getByRole('button',{name:'Avançar 1 hora',exact:true}).click();
 await live.waitForFunction(h=>document.querySelector('.sx-relogio-num')?.textContent.includes(h),hour);
 await live.locator('[data-testid="stStatusWidget"]').waitFor({state:'hidden',timeout:60000});
}
await live.getByRole('tab',{name:'Fila do analista',exact:true}).click();
await live.locator('summary:visible').filter({hasText:'Ver evidências'}).first().click();
await snap(live,'current-streamlit-mobile');
await live.setViewportSize({width:1440,height:1000});await snap(live,'current-streamlit-desktop');
console.log(JSON.stringify(results.map(({name,width,scrollWidth,fields,selected})=>({name,width,scrollWidth,fields,selected}))));
}finally{fs.writeFileSync(path.join(__dirname,'current-audit.json'),JSON.stringify(results,null,2));await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
