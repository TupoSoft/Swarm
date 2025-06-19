#!/usr/bin/env bash
set -e
set -o pipefail
set -x

if [[ -f "$SECRET_FILE_PATH" ]]; then
  RUNNER_TOKEN="$(cat "$SECRET_FILE_PATH")"
else
  echo "ERROR: Secret file not found at $SECRET_FILE_PATH" >&2
  exit 1
fi

if [[ -n "$RUNNER_REPO" ]]; then
  RUNNER_URL="https://github.com/${RUNNER_REPO}"
elif [[ -n "$RUNNER_ORG" ]]; then
  RUNNER_URL="https://github.com/${RUNNER_ORG}"
else
  echo "ERROR: must set RUNNER_REPO or RUNNER_ORG" >&2
  exit 1
fi

./config.sh \
  --unattended \
  --url      "${RUNNER_URL}" \
  --token    "${RUNNER_TOKEN}" \
  --name     "${RUNNER_NAME:-$(hostname)}" \
  --work     "${RUNNER_WORKDIR:-_work}" \
  --labels   "${RUNNER_LABELS:-self-hosted}" \
  --replace

cleanup() {
  echo "Deregistering runner..."
  ./config.sh remove --token "${RUNNER_TOKEN}"
}
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

exec ./run.sh
