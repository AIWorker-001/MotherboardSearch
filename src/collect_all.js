const { chromium } = require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.goto('https://shopgoodwill.com/home',{waitUntil:'domcontentloaded',timeout:60000});
 await page.waitForTimeout(3000);
 const input=page.locator('#txtGlobalSearch');
 await input.fill('motherboard');
 await Promise.all([page.waitForURL(/categories\/listing/,{timeout:30000}),input.press('Enter')]);
 const out=[];
 for(let p=1;p<=3;p++){
   const u=new URL(page.url()); u.searchParams.set('p',String(p));
   await page.goto(u.toString(),{waitUntil:'domcontentloaded',timeout:60000});
   await page.waitForTimeout(8000);
   const items=await page.locator('a[href*="/item/"]').evaluateAll(as=>{
     const seen=new Set(), rows=[];
     for(const a of as){
       const text=(a.innerText||'').trim();
       const m=a.href.match(/\/item\/(\d+)/);
       if(!m||!text||seen.has(m[1])) continue;
       seen.add(m[1]);
       let el=a;
       for(let i=0;i<8&&el;i++,el=el.parentElement){
         const t=(el.innerText||'').trim();
         if(/\$\d/.test(t)&&/Time remaining:|Buy It Now/.test(t)) { rows.push({id:m[1],title:text,url:a.href,card:t}); break; }
       }
     }
     return rows;
   });
   console.log('PAGE',p,'COUNT',items.length);
   out.push(...items);
 }
 console.log('JSON_START'); console.log(JSON.stringify(out,null,2)); console.log('JSON_END');
 await browser.close();
})();
