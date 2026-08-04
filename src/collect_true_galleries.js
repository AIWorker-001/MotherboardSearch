#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const {
  createPersistentContext,
  gotoWithRetry,
  saveSession,
  writeJson,
} = require('./browser_support');

function parseArgs(argv) {
  const options = {
    ids: [], output: 'output/true_galleries.json', errors: 'output/gallery_errors.json',
    session: 'output/session/shopgoodwill.json', waitMs: 3000, retries: 4, concurrency: 4,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--ids') options.ids = argv[++i].split(',').map(v => v.trim()).filter(Boolean);
    else if (arg === '--ids-file') options.idsFile = argv[++i];
    else if (arg === '--output') options.output = argv[++i];
    else if (arg === '--errors') options.errors = argv[++i];
    else if (arg === '--session') options.session = argv[++i];
    else if (arg === '--wait-ms') options.waitMs = Number(argv[++i]);
    else if (arg === '--retries') options.retries = Number(argv[++i]);
    else if (arg === '--concurrency') options.concurrency = Math.max(1, Number(argv[++i]));
    else throw new Error(`Unknown argument: ${arg}`);
  }
  if (options.idsFile) options.ids.push(...fs.readFileSync(options.idsFile, 'utf8').split(/\s+/).filter(Boolean));
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

async function collectOne(context, id, options) {
  const page = await context.newPage();
  try {
    const navigation = await gotoWithRetry(page, `https://shopgoodwill.com/item/${id}`, { retries: options.retries });
    await page.waitForTimeout(options.waitMs);
    const gallery = page.locator('.image-gallery').first();
    if ((await gallery.count()) === 0) throw new Error('gallery_not_loaded');
    const title = (await page.title()).replace(/ \| ShopGoodwill\.com$/, '');
    const styles = await gallery.locator('[style*="background-image"]').evaluateAll(
      elements => elements.map(element => element.getAttribute('style'))
    );
    const urls = [...new Set(styles.map(extractUrl).filter(Boolean))];
    if (!urls.length) throw new Error('gallery_loaded_without_images');
    return { id, title, urls, attempts: navigation.attempt, fetched_at: new Date().toISOString() };
  } finally {
    await page.close();
  }
}

async function runPool(items, concurrency, worker) {
  const output = new Array(items.length);
  let cursor = 0;
  async function consume() {
    while (true) {
      const index = cursor++;
      if (index >= items.length) return;
      output[index] = await worker(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, consume));
  return output;
}

(async () => {
  const options = parseArgs(process.argv);
  const errors = [];
  const { browser, context } = await createPersistentContext(chromium, { sessionPath: options.session });
  let results;
  try {
    results = await runPool(options.ids, options.concurrency, async id => {
      try {
        const result = await collectOne(context, id, options);
        console.log(`${id} | gallery=${result.urls.length} | ${result.title}`);
        return result;
      } catch (error) {
        const failure = { id, error: error.message, urls: [], attempts: error.attempts || [], failed_at: new Date().toISOString() };
        errors.push(failure);
        console.error(`${id} | ERROR | ${error.message}`);
        return failure;
      }
    });
    await saveSession(context, options.session);
  } finally {
    await browser.close();
  }
  fs.mkdirSync(path.dirname(options.output), { recursive: true });
  fs.writeFileSync(options.output, `${JSON.stringify(results, null, 2)}\n`);
  writeJson(options.errors, errors);
  console.log(`total=${results.length} errors=${errors.length} concurrency=${options.concurrency}`);
})();
