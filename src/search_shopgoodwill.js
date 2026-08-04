#!/usr/bin/env node
const fs = require('fs');
const { chromium } = require('playwright');

function parseArgs(argv) {
  const options = { query: 'motherboard', pages: 3, output: 'output/listings.json' };
  for (let i = 2; i < argv.length; i += 1) {
    if (argv[i] === '--query') options.query = argv[++i];
    else if (argv[i] === '--pages') options.pages = Number(argv[++i]);
    else if (argv[i] === '--output') options.output = argv[++i];
    else throw new Error(`Unknown argument: ${argv[i]}`);
  }
  return options;
}

(async () => {
  const options = parseArgs(process.argv);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const listings = [];
  try {
    await page.goto('https://shopgoodwill.com/home', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(3000);
    const input = page.locator('#txtGlobalSearch');
    await input.fill(options.query);
    await Promise.all([page.waitForURL(/categories\/listing/, { timeout: 30000 }), input.press('Enter')]);
    for (let pageNumber = 1; pageNumber <= options.pages; pageNumber += 1) {
      const url = new URL(page.url());
      url.searchParams.set('p', String(pageNumber));
      await page.goto(url.toString(), { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.waitForTimeout(7000);
      const pageListings = await page.locator('a[href*="/item/"]').evaluateAll(anchors => {
        const seen = new Set();
        const rows = [];
        for (const anchor of anchors) {
          const match = anchor.href.match(/\/item\/(\d+)/);
          const title = (anchor.innerText || '').trim();
          if (!match || !title || seen.has(match[1])) continue;
          let element = anchor;
          for (let depth = 0; depth < 8 && element; depth += 1, element = element.parentElement) {
            const card = (element.innerText || '').trim();
            if (/\$\d/.test(card) && /Time remaining:|Buy It Now/.test(card)) {
              rows.push({ id: match[1], title, url: anchor.href, card });
              seen.add(match[1]);
              break;
            }
          }
        }
        return rows;
      });
      listings.push(...pageListings);
      console.log(`page=${pageNumber} listings=${pageListings.length}`);
    }
  } finally {
    await browser.close();
  }
  const unique = [...new Map(listings.map(item => [item.id, item])).values()];
  fs.mkdirSync(require('path').dirname(options.output), { recursive: true });
  fs.writeFileSync(options.output, JSON.stringify(unique, null, 2));
  console.log(`total=${unique.length}`);
})();
