#!/usr/bin/env bash
set -e

function get_reg_token() {
    local gh_pat="$1"
    local api_url="$2"
    local reg_token

    reg_token="$(curl -sSL \
        -X POST \
        -H "Accept: application/vnd.github+json" \
        -H "Authorization: Bearer $gh_pat" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "$api_url" \
        | jq -r .token )"

    if [[ -z "$reg_token" || "$reg_token" == "null" ]]; then
      echo "ERROR: failed to fetch runner registration token" >&2
      return 1
    fi

    echo "$reg_token"
    return 0
}

function cleanup() {
  local gh_pat="$1"
  local api_url="$2"
  local reg_token

  reg_token=$(get_reg_token "$gh_pat" "$api_url") || return 1
  runuser -u runner -- ./config.sh remove --token "$reg_token"

  return 0
}

function setup() {
  local gh_pat
  local api_url
  local runner_url
  local reg_token

  groupmod -g "$(stat -c "%g" /var/run/docker.sock)" docker

  if [[ -f "$GH_PAT_SECRET_FILE_PATH" ]]; then
    gh_pat="$(cat "$GH_PAT_SECRET_FILE_PATH")"
  else
    echo "ERROR: Secret file not found at $GH_PAT_SECRET_FILE_PATH" >&2
    return 1
  fi

  if [[ -n "$RUNNER_REPO" ]]; then
    runner_url="https://github.com/${RUNNER_REPO}"
    api_url="https://api.github.com/repos/${RUNNER_REPO}/actions/runners/registration-token"
  elif [[ -n "$RUNNER_ORG" ]]; then
    runner_url="https://github.com/${RUNNER_ORG}"
    api_url="https://api.github.com/orgs/${RUNNER_ORG}/actions/runners/registration-token"
  else
    echo "ERROR: must set RUNNER_REPO or RUNNER_ORG" >&2
    return 1
  fi

  reg_token=$(get_reg_token "$gh_pat" "$api_url") || return 1

  if [[ -z "$reg_token" || "$reg_token" == "null" ]]; then
    echo "ERROR: failed to fetch runner registration token" >&2
    return 1
  fi

  runuser -u runner -- ./config.sh \
    --unattended \
    --url      "${runner_url}" \
    --token    "${reg_token}" \
    --name     "${RUNNER_NAME:swarm-gh-actions-runner-$(hostname)}" \
    --work     "${RUNNER_WORKDIR:-_work}" \
    --labels   "${RUNNER_LABELS:-self-hosted}" \
    --replace

  trap 'cleanup "$gh_pat" "$api_url"' SIGINT SIGTERM

  local runner_pid
  local exit_code

  runuser -u runner -- ./run.sh &
  runner_pid=$!
  wait "${runner_pid}"
  exit_code=$?

  cleanup "$gh_pat" "$api_url"

  return "$exit_code"
}

setup
