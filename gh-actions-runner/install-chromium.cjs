'use strict';

const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const { mkdirSync, readFileSync, rmSync, writeFileSync } = require('node:fs');
const path = require('node:path');

const version = process.env.PLAYWRIGHT_VERSION;
const integrity = process.env.PLAYWRIGHT_INTEGRITY;
const browserPath = process.env.PLAYWRIGHT_BROWSERS_PATH;
const archivePath = '/tmp/runner-playwright.tgz';
const installerPath = '/tmp/runner-playwright';

assert(version, 'PLAYWRIGHT_VERSION is required');
assert(integrity, 'PLAYWRIGHT_INTEGRITY is required');
assert.equal(browserPath, '/opt/ms-playwright', 'Unexpected browser installation path');

// Verify the pinned archive before extracting or executing any of its files.
execFileSync('curl', [
  '--fail', '--location', '--retry', '3',
  `https://registry.npmjs.org/playwright-core/-/playwright-core-${version}.tgz`,
  '--output', archivePath,
], { stdio: 'inherit' });

const digest = createHash('sha512').update(readFileSync(archivePath)).digest('base64');
assert.equal(`sha512-${digest}`, integrity, 'Playwright archive integrity does not match');

mkdirSync(installerPath);
execFileSync('tar', [
  'xzf', archivePath, '--strip-components=1', '-C', installerPath,
], { stdio: 'inherit' });

const packageMetadata = JSON.parse(readFileSync(path.join(installerPath, 'package.json'), 'utf8'));
assert.equal(packageMetadata.version, version, 'Playwright package version does not match');

const { browsers } = JSON.parse(readFileSync(path.join(installerPath, 'browsers.json'), 'utf8'));
writeFileSync('/opt/runner-playwright.json', JSON.stringify({
  version,
  integrity,
  browserPath,
  browsers,
}, null, 2) + '\n');

// Keep the installer available for the subsequent offline checks as runner.
execFileSync(process.execPath, [
  path.join(installerPath, 'cli.js'), 'install', '--with-deps', 'chromium',
], { stdio: 'inherit' });
execFileSync('chown', ['-R', 'runner:runner', browserPath], { stdio: 'inherit' });

rmSync(archivePath);
rmSync('/var/lib/apt/lists', { recursive: true, force: true });
