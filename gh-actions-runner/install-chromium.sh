#!/bin/sh
set -eu

: "${PLAYWRIGHT_VERSION:?PLAYWRIGHT_VERSION is required}"
: "${PLAYWRIGHT_INTEGRITY:?PLAYWRIGHT_INTEGRITY is required}"
: "${PLAYWRIGHT_BROWSERS_PATH:?PLAYWRIGHT_BROWSERS_PATH is required}"

if [ "$PLAYWRIGHT_BROWSERS_PATH" != /opt/ms-playwright ]; then
    printf '%s\n' 'Unexpected browser installation path' >&2
    exit 1
fi

archive_path=/tmp/runner-playwright.tgz
digest_path=/tmp/runner-playwright.sha512
installer_path=/tmp/runner-playwright
node_binary=/actions-runner/externals/node24/bin/node

# Verify the pinned archive before extracting or executing any of its files.
curl --fail --location --retry 3 \
    "https://registry.npmjs.org/playwright-core/-/playwright-core-${PLAYWRIGHT_VERSION}.tgz" \
    --output "$archive_path"

openssl dgst -sha512 -binary -out "$digest_path" "$archive_path"
archive_digest=$(openssl base64 -A -in "$digest_path")
if [ "sha512-$archive_digest" != "$PLAYWRIGHT_INTEGRITY" ]; then
    printf '%s\n' 'Playwright archive integrity does not match' >&2
    exit 1
fi

mkdir "$installer_path"
tar xzf "$archive_path" --strip-components=1 -C "$installer_path"

if ! jq -e --arg version "$PLAYWRIGHT_VERSION" \
    '.version == $version' "$installer_path/package.json" > /dev/null; then
    printf '%s\n' 'Playwright package version does not match' >&2
    exit 1
fi

jq --arg version "$PLAYWRIGHT_VERSION" \
    --arg integrity "$PLAYWRIGHT_INTEGRITY" \
    --arg browserPath "$PLAYWRIGHT_BROWSERS_PATH" \
    '{version: $version, integrity: $integrity, browserPath: $browserPath, browsers: .browsers}' \
    "$installer_path/browsers.json" > /opt/runner-playwright.json

# Keep the installer available for the subsequent offline checks as runner.
"$node_binary" "$installer_path/cli.js" install --with-deps chromium
chown -R runner:runner "$PLAYWRIGHT_BROWSERS_PATH"

rm "$archive_path" "$digest_path"
rm -rf /var/lib/apt/lists/*
