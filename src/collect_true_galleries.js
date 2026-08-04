#!/usr/bin/env node
const fs = require('fs');
const { chromium } = require('playwright');

function parseArgs(argv) {
  const options = { ids: [], output: 'output/true_galleries.json', waitMs: 4500 };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--ids') options.ids = argv[++i].split(',').map(v => v.trim()).filter(Boolean);
    else if (arg === '--ids-file') options.idsFile = argv[++i];
    else if (arg === '--output') options.output = argv[++i];
    else if (arg === '--wait-ms') options.waitMs = Number(argv[++i]);
    else throw new Error(`Unknown argument: ${arg}`);
  }
  if (options.idsFile) {
    const text = fs.readFileSync(options.idsFile, 'utf8');
    options.ids.push(...text.split(/\s+/).filter(Boolean));
  }
  options.ids = [...new Set(options.ids)];
  if (!options.ids.length) throw new Error('Provide --ids or --ids-file');
  return options;
}

function extractUrl(style) {
  const match = style && style.match(/url\(["']?([^"')]+)["']?\)/);
  if (!match) return null;
  let url = match[1];
  if (!/shopgoodwillimages/.test(url) || /\/General\//.test(url)) return null;
  return url.replace(/t(\d+)\.jpeg$/, '$1.jpg');
}

(async () => {
  const options = parseArgs(process.argv);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  const output = [];
  try {
    for (const id of options.ids) {
      let loaded = false;
      for (let attempt = 1; attempt <= 3 && !loaded; attempt += 1) {
        await page.goto(`https://shopgoodwill.com/item/${id}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.waitForTimeout(options.waitMs);
        loaded = (await page.locator('.image-gallery').count()) > 0;
      }
      if (!loaded) {
        output.push({ id, error: 'gallery_not_loaded', urls: [] });
        continue;
      }
      const gallery = page.locator('.image-gallery').first();
      const title = (await page.title()).replace(/ \| ShopGoodwill\.com$/, '');
      const styles = await gallery.locator('[style*="background-image"]').evaluateAll(
        elements => elements.map(element => element.getAttribute('style'))
      );
      const urls = [...new Set(styles.map(extractUrl).filter(Boolean))];
      output.push({ id, title, urls });
      console.log(`${id} | gallery=${urls.length} | ${title}`);
    }
  } finally {
    await browser.close();
  }
  fs.mkdirSync(require('path').dirname(options.output), { recursive: true });
  fs.writeFileSync(options.output, JSON.stringify(output, null, 2));
})();
