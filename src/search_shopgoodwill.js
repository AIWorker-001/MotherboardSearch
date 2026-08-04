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
    query: 'motherboard',
    pages: 3,
    output: 'output/listings.json',
    errors: 'output/search_errors.json',
    session: 'output/session/shopgoodwill.json',
    retries: 4,
  };
  for (let i = 2; i < argv.length; i += 1) {
    if (argv[i] === '--query') options.query = argv[++i];
    else if (argv[i] === '--pages') options.pages = Number(argv[++i]);
    else if (argv[i] === '--output') options.output = argv[++i];
    else if (argv[i] === '--errors') options.errors = argv[++i];
    else if (argv[i] === '--session') options.session = argv[++i];
    else if (argv[i] === '--retries') options.retries = Number(argv[++i]);
    else throw new Error(`Unknown argument: ${argv[i]}`);
  }
  return options;
}

async function extractListings(page) {
  return page.locator('a[href*="/item/"]').evaluateAll(anchors => {
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
}

(async () => {
  const options = parseArgs(process.argv);
  const errors = [];
  const listings = [];
  const { browser, context } = await createPersistentContext(chromium, { sessionPath: options.session });
  const page = await context.newPage();
  try {
    await gotoWithRetry(page, 'https://shopgoodwill.com/home', { retries: options.retries });
    await page.waitForTimeout(2500);
    const input = page.locator('#txtGlobalSearch');
    if ((await input.count()) === 0) throw new Error('global_search_input_missing');
    await input.fill(options.query);
    await Promise.all([
      page.waitForURL(/categories\/listing/, { timeout: 30000 }),
      input.press('Enter'),
    ]);

    const searchUrl = page.url();
    for (let pageNumber = 1; pageNumber <= options.pages; pageNumber += 1) {
      const url = new URL(searchUrl);
      url.searchParams.set('p', String(pageNumber));
      try {
        await gotoWithRetry(page, url.toString(), { retries: options.retries });
        await page.waitForTimeout(5000);
        const pageListings = await extractListings(page);
        if (!pageListings.length) throw new Error('listing_page_returned_zero_items');
        listings.push(...pageListings);
        console.log(`page=${pageNumber} listings=${pageListings.length}`);
      } catch (error) {
        errors.push({ stage: 'listing_page', page: pageNumber, url: url.toString(), message: error.message, attempts: error.attempts || [] });
      }
    }
    await saveSession(context, options.session);
  } catch (error) {
    errors.push({ stage: 'search_initialization', message: error.message, attempts: error.attempts || [] });
  } finally {
    await browser.close();
  }

  const unique = [...new Map(listings.map(item => [item.id, item])).values()];
  fs.mkdirSync(path.dirname(options.output), { recursive: true });
  fs.writeFileSync(options.output, `${JSON.stringify(unique, null, 2)}\n`);
  writeJson(options.errors, errors);
  console.log(`total=${unique.length} errors=${errors.length}`);
  if (!unique.length) process.exitCode = 2;
})();
