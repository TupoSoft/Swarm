#!/usr/bin/env bash
set -euo pipefail

load_and_export_credential() {
  local var_name="$1"
  local file_var="${var_name}_FILE"
  local file_path="${!file_var}"

  local value
  value="$(cat "$file_path")"
  export "$var_name=$value"
}

load_and_export_credential "PGPASSWORD_SUPERUSER"
load_and_export_credential "PGUSER_ADMIN"
load_and_export_credential "PGPASSWORD_ADMIN"
load_and_export_credential "PGUSER_STANDBY"
load_and_export_credential "PGPASSWORD_STANDBY"

exec /launch.sh
