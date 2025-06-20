#!/usr/bin/env bash
set -ex

if [[ -f "$GH_PAT_SECRET_FILE_PATH" ]]; then
  GH_PAT="$(cat "$GH_PAT_SECRET_FILE_PATH")"
else
  echo "ERROR: Secret file not found at $GH_PAT_SECRET_FILE_PATH" >&2
  exit 1
fi

if [[ -n "$RUNNER_REPO" ]]; then
  RUNNER_URL="https://github.com/${RUNNER_REPO}"
  API_URL="https://api.github.com/repos/${RUNNER_REPO}/actions/runners/registration-token"
elif [[ -n "$RUNNER_ORG" ]]; then
  RUNNER_URL="https://github.com/${RUNNER_ORG}"
  API_URL="https://api.github.com/orgs/${RUNNER_ORG}/actions/runners/registration-token"
else
  echo "ERROR: must set RUNNER_REPO or RUNNER_ORG" >&2
  exit 1
fi

REG_TOKEN="$(curl -sSL \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GH_PAT}" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "${API_URL}" \
  | jq -r .token )"

if [[ -z "$REG_TOKEN" || "$REG_TOKEN" == "null" ]]; then
  echo "ERROR: failed to fetch runner registration token" >&2
  exit 1
fi

runuser -u runner -- ./config.sh \
  --unattended \
  --url      "${RUNNER_URL}" \
  --token    "${REG_TOKEN}" \
  --name     "${RUNNER_NAME:-$(hostname)}" \
  --work     "${RUNNER_WORKDIR:-_work}" \
  --labels   "${RUNNER_LABELS:-self-hosted}" \
  --replace

cleanup() {
  echo "Deregistering runner..."
  runuser -u runner -- ./config.sh remove --token "${REG_TOKEN}"
}

trap cleanup SIGINT SIGTERM

runuser -u runner -- ./run.sh &
RUNNER_PID=$!

wait "${RUNNER_PID}"
EXIT_CODE=$?

cleanup

exit "${EXIT_CODE}"
