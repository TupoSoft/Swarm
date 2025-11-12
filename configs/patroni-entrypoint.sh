#!/usr/bin/env bash
set -euo pipefail

PGPASSWORD_SUPERUSER="$(cat "$PGPASSWORD_SUPERUSER_FILE")"
export PGPASSWORD_SUPERUSER

exec /launch.sh
