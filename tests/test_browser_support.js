'use strict';
const assert = require('assert');
const { jitteredBackoff } = require('../src/browser_support');
for (let attempt = 1; attempt <= 5; attempt += 1) {
  const value = jitteredBackoff(attempt, 100, 1000);
  assert(value >= 80);
  assert(value <= 1200);
}
console.log('browser_support tests passed');
