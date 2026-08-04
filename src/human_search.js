const { chromium } = require('playwright');
(async()=>{
  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext({
    viewport:{width:1440,height:1000},
    userAgent:'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
  });
  const page = await context.newPage();
  page.on('console', m=>console.log('BROWSER_CONSOLE',m.type(),m.text()));
  page.on('response', r=>{ const u=r.url(); if(/search|listing|item|api|graphql/i.test(u)) console.log('RESPONSE',r.status(),u); });
  await page.goto('https://shopgoodwill.com/', {waitUntil:'domcontentloaded', timeout:60000});
  await page.waitForTimeout(5000);
  console.log('HOME_URL',page.url());
  const inputs = await page.locator('input').evaluateAll(els=>els.map((e,i)=>({i,type:e.type,name:e.name,id:e.id,placeholder:e.placeholder,aria:e.getAttribute('aria-label')})));
  console.log('INPUTS',JSON.stringify(inputs));
  const buttons = await page.locator('button').evaluateAll(els=>els.map((e,i)=>({i,text:(e.innerText||'').trim(),aria:e.getAttribute('aria-label'),title:e.title})).filter(x=>x.text||x.aria||x.title));
  console.log('BUTTONS',JSON.stringify(buttons.slice(0,80)));

  let search = page.locator('input[type="search"]').first();
  if(await search.count()===0) search = page.getByPlaceholder(/search/i).first();
  if(await search.count()===0) search = page.locator('input').filter({has: page.locator('nothing')});
  if(await search.count()===0){ console.log('NO_SEARCH_INPUT'); console.log((await page.locator('body').innerText()).slice(0,4000)); await browser.close(); return; }
  await search.fill('motherboard');
  console.log('FILLED_SEARCH');
  let clicked=false;
  const candidates=[page.getByRole('button',{name:/search/i}).first(), page.locator('button[type="submit"]').first(), page.locator('form').filter({has:search}).locator('button').first()];
  for(const b of candidates){ if(await b.count()){ try{await Promise.all([page.waitForLoadState('domcontentloaded',{timeout:30000}).catch(()=>{}),b.click()]); clicked=true; console.log('CLICKED_SEARCH'); break;}catch(e){console.log('CLICK_FAIL',e.message);} } }
  if(!clicked){ await search.press('Enter'); console.log('PRESSED_ENTER'); }
  await page.waitForTimeout(10000);
  console.log('RESULT_URL',page.url());
  console.log('TITLE',await page.title());
  const body=(await page.locator('body').innerText()).replace(/\n{3,}/g,'\n\n');
  console.log('BODY_START');
  console.log(body.slice(0,15000));
  console.log('BODY_END');
  await page.screenshot({path:'/tmp/sgw/human_search.png',fullPage:true});
  await browser.close();
})();
