'use strict';

const assert = require('node:assert/strict');
const { constants } = require('node:fs');
const fs = require('node:fs/promises');
const path = require('node:path');

async function main() {
  const [packageDirectory, expectedVersion, ...extraArguments] = process.argv.slice(2);
  assert(
    packageDirectory && path.isAbsolute(packageDirectory) && expectedVersion && extraArguments.length === 0,
    'Usage: node check_browser_capabilities.cjs /absolute/path/to/playwright expected-version',
  );
  assert(typeof process.getuid === 'function' && process.getuid() !== 0,
    'Run this check as the non-root runner user');

  const packageMetadata = JSON.parse(await fs.readFile(path.join(packageDirectory, 'package.json'), 'utf8'));
  assert.equal(packageMetadata.name, 'playwright', 'Expected the playwright package');
  assert.equal(packageMetadata.version, expectedVersion, 'Playwright version does not match the image');
  const browserPath = '/opt/ms-playwright';
  assert.equal(process.env.PLAYWRIGHT_BROWSERS_PATH, browserPath, 'Unexpected image browser path');

  await fs.access(browserPath, constants.R_OK | constants.W_OK | constants.X_OK);
  const temporaryDirectory = await fs.mkdtemp(path.join(browserPath, '.capability-check-'));
  try {
    const temporaryFile = path.join(temporaryDirectory, 'writable');
    await fs.writeFile(temporaryFile, 'runner browser capability check\n', { flag: 'wx' });
    assert.equal(await fs.readFile(temporaryFile, 'utf8'), 'runner browser capability check\n');
  } finally {
    await fs.rm(temporaryDirectory, { recursive: true, force: true });
  }

  const { chromium } = require(packageDirectory);
  for (const channel of [undefined, 'chromium']) {
    const mode = channel ?? 'default headless';
    const browser = await chromium.launch({ headless: true, channel, timeout: 30_000 });
    try {
      const page = await browser.newPage();
      page.setDefaultTimeout(10_000);
      await page.setContent('<!doctype html><title>Runner browser check</title><h1>Chromium is ready</h1>');
      assert.equal(await page.title(), 'Runner browser check', `${mode}: local HTML did not render`);
      const screenshot = await page.screenshot({ type: 'png' });
      assert(Buffer.isBuffer(screenshot) && screenshot.length > 0, `${mode}: screenshot is empty`);
      console.log(`Chromium capability check passed: ${mode}`);
    } finally {
      await browser.close();
    }
  }
}

main().catch((error) => {
  console.error(`Browser capability check failed: ${error.message}`);
  process.exitCode = 1;
});
