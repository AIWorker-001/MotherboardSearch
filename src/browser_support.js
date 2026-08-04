'use strict';

const fs = require('fs');
const path = require('path');

const BLOCK_PATTERNS = [
  /cloudflare/i,
  /attention required/i,
  /verify you are human/i,
  /access denied/i,
  /too many requests/i,
  /temporarily unavailable/i,
];

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function jitteredBackoff(attempt, baseMs = 1500, maxMs = 30000) {
  const exponential = Math.min(maxMs, baseMs * (2 ** Math.max(0, attempt - 1)));
  return Math.round(exponential * (0.8 + Math.random() * 0.4));
}

async function inspectPage(page) {
  const title = await page.title().catch(() => '');
  const body = await page.locator('body').innerText({ timeout: 5000 }).catch(() => '');
  const text = `${title}\n${body.slice(0, 5000)}`;
  const matched = BLOCK_PATTERNS.find(pattern => pattern.test(text));
  return {
    blocked: Boolean(matched),
    reason: matched ? String(matched) : null,
    title,
    url: page.url(),
    bodyPreview: body.slice(0, 1000),
  };
}

async function gotoWithRetry(page, url, options = {}) {
  const retries = options.retries ?? 4;
  const timeout = options.timeout ?? 60000;
  const waitUntil = options.waitUntil ?? 'domcontentloaded';
  const errors = [];
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      const response = await page.goto(url, { waitUntil, timeout });
      const status = response ? response.status() : null;
      const inspection = await inspectPage(page);
      if (status === 403 || status === 429 || (status && status >= 500) || inspection.blocked) {
        const error = new Error(`blocked_or_rate_limited status=${status} reason=${inspection.reason || 'page-content'}`);
        error.code = status === 429 ? 'rate_limited' : 'blocked';
        error.httpStatus = status;
        error.inspection = inspection;
        throw error;
      }
      return { response, attempt, inspection };
    } catch (error) {
      errors.push({
        attempt,
        message: error.message,
        code: error.code || error.name,
        httpStatus: error.httpStatus || null,
        url,
      });
      if (attempt === retries) {
        error.attempts = errors;
        throw error;
      }
      await sleep(jitteredBackoff(attempt, options.baseDelayMs));
    }
  }
  throw new Error('unreachable');
}

async function createPersistentContext(browserType, options = {}) {
  const sessionPath = options.sessionPath;
  const contextOptions = {
    viewport: options.viewport || { width: 1440, height: 1000 },
    userAgent: options.userAgent || 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
  };
  if (sessionPath && fs.existsSync(sessionPath)) contextOptions.storageState = sessionPath;
  const browser = await browserType.launch({ headless: options.headless ?? true });
  const context = await browser.newContext(contextOptions);
  return { browser, context };
}

async function saveSession(context, sessionPath) {
  if (!sessionPath) return;
  fs.mkdirSync(path.dirname(sessionPath), { recursive: true });
  await context.storageState({ path: sessionPath });
}

function writeJson(pathname, value) {
  fs.mkdirSync(path.dirname(pathname), { recursive: true });
  fs.writeFileSync(pathname, `${JSON.stringify(value, null, 2)}\n`);
}

module.exports = {
  createPersistentContext,
  gotoWithRetry,
  inspectPage,
  jitteredBackoff,
  saveSession,
  sleep,
  writeJson,
};
