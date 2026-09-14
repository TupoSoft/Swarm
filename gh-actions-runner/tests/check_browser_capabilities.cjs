'use strict';

const assert = require('node:assert/strict');
const { constants } = require('node:fs');
const fs = require('node:fs/promises');
const path = require('node:path');

async function main() {
  const [packageDirectory, ...extraArguments] = process.argv.slice(2);
  assert(
    packageDirectory && path.isAbsolute(packageDirectory) && extraArguments.length === 0,
    'Usage: node check_browser_capabilities.cjs /absolute/path/to/playwright-core',
  );
  assert(typeof process.getuid === 'function' && process.getuid() !== 0,
    'Run this check as the non-root runner user');

  const metadata = JSON.parse(await fs.readFile('/opt/runner-playwright.json', 'utf8'));
  const packageMetadata = JSON.parse(await fs.readFile(path.join(packageDirectory, 'package.json'), 'utf8'));
  const browserManifest = JSON.parse(await fs.readFile(path.join(packageDirectory, 'browsers.json'), 'utf8'));
  assert.equal(packageMetadata.name, 'playwright-core', 'Expected the playwright-core package');
  assert.equal(packageMetadata.version, metadata.version, 'Playwright version does not match the image');
  assert.match(metadata.integrity, /^sha512-[A-Za-z0-9+/]{86}==$/, 'Expected a SHA-512 archive integrity');
  assert(Array.isArray(metadata.browsers) && metadata.browsers.length > 0, 'Browser manifest is missing');
  assert.deepEqual(browserManifest.browsers, metadata.browsers, 'Browser revisions do not match the image');
  assert.equal(metadata.browserPath, '/opt/ms-playwright', 'Unexpected image browser path');
  assert.equal(process.env.PLAYWRIGHT_BROWSERS_PATH, metadata.browserPath,
    'PLAYWRIGHT_BROWSERS_PATH must match the image metadata');

  await fs.access(metadata.browserPath, constants.R_OK | constants.W_OK | constants.X_OK);
  const temporaryDirectory = await fs.mkdtemp(path.join(metadata.browserPath, '.capability-check-'));
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
