#!/bin/sh
set -eu

: "${PLAYWRIGHT_VERSION:?PLAYWRIGHT_VERSION is required}"
: "${PLAYWRIGHT_BROWSERS_PATH:?PLAYWRIGHT_BROWSERS_PATH is required}"

if [ "$PLAYWRIGHT_BROWSERS_PATH" != /opt/ms-playwright ]; then
    printf '%s\n' 'Unexpected browser installation path' >&2
    exit 1
fi

npm install --global --no-audit --no-fund "playwright@$PLAYWRIGHT_VERSION"
playwright install --with-deps chromium
chown -R runner:runner "$PLAYWRIGHT_BROWSERS_PATH"

npm cache clean --force
rm -rf /var/lib/apt/lists/*
