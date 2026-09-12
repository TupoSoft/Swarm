#!/usr/bin/env bash
set -euo pipefail

# Only this Swarm launcher receives the host Docker socket and organization PAT.
host_docker() {
  env -u DOCKER_CONTEXT -u DOCKER_HOST -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
    docker --host=unix:///var/run/docker.sock "$@"
}

github_api() {
  curl --fail --silent --show-error --connect-timeout 10 --max-time 30 \
    -X "$1" \
    -H 'Accept: application/vnd.github+json' \
    -H "Authorization: Bearer $gh_pat" \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "https://api.github.com/$api_scope/actions/runners$2"
}

cleanup() {
  local failed=0 agent_id status registered_name

  if [[ -n "$worker_container" ]]; then
    host_docker stop --time 30 "$worker_container" >/dev/null 2>&1 || true

    # Ephemeral jobs normally remove their own registration. On cancellation or
    # failed startup, read this exact worker's ID before removing its filesystem.
    if host_docker cp "$worker_container:/actions-runner/.runner" "$metadata_file" >/dev/null 2>&1; then
      agent_id=$(jq -er '.agentId | select(type == "number" and . > 0)' "$metadata_file") || agent_id=
      if [[ "$agent_id" =~ ^[0-9]+$ ]]; then
        # The job can edit .runner. Verify the name with GitHub before using the
        # launcher's privileged token to delete this untrusted candidate ID.
        status=$(curl --silent --show-error --connect-timeout 10 --max-time 30 \
          -o "$metadata_file" -w '%{http_code}' -X GET \
          -H "Authorization: Bearer $gh_pat" \
          -H 'Accept: application/vnd.github+json' \
          -H 'X-GitHub-Api-Version: 2022-11-28' \
          "https://api.github.com/$api_scope/actions/runners/$agent_id") || status=failed
        if [[ "$status" == 200 ]]; then
          registered_name=$(jq -er '.name | select(type == "string")' "$metadata_file") || registered_name=
          if [[ "$registered_name" == "$runner_name" ]]; then
            status=$(curl --silent --show-error --connect-timeout 10 --max-time 30 \
              -o /dev/null -w '%{http_code}' -X DELETE \
              -H "Authorization: Bearer $gh_pat" \
              -H 'Accept: application/vnd.github+json' \
              -H 'X-GitHub-Api-Version: 2022-11-28' \
              "https://api.github.com/$api_scope/actions/runners/$agent_id") || status=failed
          else
            status=ownership-mismatch
          fi
        fi
        # A 404 means GitHub already removed the completed ephemeral runner.
        if [[ "$status" != 204 && "$status" != 404 ]]; then
          echo "ERROR: runner registration cleanup failed ($status)" >&2
          failed=1
        fi
      fi
    fi
    host_docker rm --force --volumes "$worker_container" >/dev/null || failed=1
  fi

  if [[ -n "$daemon_container" ]]; then
    host_docker rm --force --volumes "$daemon_container" >/dev/null || failed=1
  fi
  if ((${#created_volumes[@]})); then
    host_docker volume rm "${created_volumes[@]}" >/dev/null || failed=1
  fi
  [[ -z "$metadata_file" ]] || rm -f "$metadata_file"
  return "$failed"
}

on_exit() {
  local status=$?
  trap - EXIT INT TERM
  cleanup || status=1
  exit "$status"
}

main() {
  local owner_id image registration_token volume ready=0 worker_status worker_state attach_status
  local daemon_name worker_name workspace_volume socket_volume data_volume

  [[ -r "${GH_PAT_SECRET_FILE_PATH:?Set GH_PAT_SECRET_FILE_PATH}" ]] || {
    echo 'ERROR: runner registration secret is not readable' >&2
    return 1
  }
  gh_pat=$(cat "$GH_PAT_SECRET_FILE_PATH")
  [[ -n "$gh_pat" ]] || { echo 'ERROR: runner registration secret is empty' >&2; return 1; }

  if [[ -n "${RUNNER_REPO:-}" ]]; then
    api_scope="repos/$RUNNER_REPO"
    runner_url="https://github.com/$RUNNER_REPO"
  elif [[ -n "${RUNNER_ORG:-}" ]]; then
    api_scope="orgs/$RUNNER_ORG"
    runner_url="https://github.com/$RUNNER_ORG"
  else
    echo 'ERROR: set RUNNER_REPO or RUNNER_ORG' >&2
    return 1
  fi
  [[ "${DIND_READY_ATTEMPTS:-60}" =~ ^[1-9][0-9]*$ ]] || {
    echo 'ERROR: DIND_READY_ATTEMPTS must be a positive integer' >&2
    return 1
  }

  owner_id=$(host_docker inspect --format '{{.Id}}' "${HOSTNAME:?}")
  image=${RUNNER_IMAGE:-$(host_docker inspect --format '{{.Image}}' "$owner_id")}
  local prefix="actions-${owner_id:0:16}"
  daemon_name="$prefix-docker"
  worker_name="$prefix-worker"
  workspace_volume="$prefix-work"
  socket_volume="$prefix-socket"
  data_volume="$prefix-data"
  runner_name=${RUNNER_NAME:-"swarm-gh-actions-runner-${owner_id:0:16}"}
  [[ "$runner_name" =~ ^[a-zA-Z0-9._-]+$ ]] || {
    echo 'ERROR: RUNNER_NAME must contain only letters, digits, dots, underscores, or hyphens' >&2
    return 1
  }
  metadata_file=$(mktemp)

  for volume in "$workspace_volume" "$socket_volume" "$data_volume"; do
    host_docker volume create --label "tuposoft.actions-runner.owner=$owner_id" "$volume" >/dev/null
    created_volumes+=("$volume")
  done

  # Explicit dockerd arguments keep the Docker API on the shared Unix socket.
  # The daemon's network namespace and filesystem belong to this one job.
  host_docker create --name "$daemon_name" --privileged \
    --label "tuposoft.actions-runner.owner=$owner_id" \
    --cpus "${DIND_CPUS:-2}" --memory "${DIND_MEMORY:-4g}" \
    --volume "$workspace_volume:/actions-runner/_work" \
    --volume "$socket_volume:/var/run" \
    --volume "$data_volume:/var/lib/docker" \
    "${DIND_IMAGE:?Set DIND_IMAGE to a pinned Docker DinD image}" \
    dockerd --host=unix:///var/run/docker.sock >/dev/null
  daemon_container=$daemon_name
  host_docker start "$daemon_container" >/dev/null

  for ((attempt = 0; attempt < ${DIND_READY_ATTEMPTS:-60}; attempt++)); do
    if host_docker exec "$daemon_container" docker --host=unix:///var/run/docker.sock info >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 1
  done
  if ((ready == 0)); then
    echo 'ERROR: isolated Docker daemon did not become ready' >&2
    host_docker logs "$daemon_container" >&2 || true
    return 1
  fi

  registration_token=$(github_api POST /registration-token | jq -er '.token | select(type == "string" and length > 0)')
  # Passing the variable name keeps the short-lived token out of command output.
  # Neither the long-lived PAT nor the host socket is passed to the worker.
  RUNNER_REGISTRATION_TOKEN="$registration_token" host_docker create \
    --name "$worker_name" --init --cgroupns private \
    --label "tuposoft.actions-runner.owner=$owner_id" \
    --cpus "${RUNNER_CPUS:-2}" --memory "${RUNNER_MEMORY:-4g}" \
    --shm-size "${RUNNER_SHM_SIZE:-1g}" \
    --network "container:$daemon_container" \
    --volume "$workspace_volume:/actions-runner/_work" \
    --volume "$socket_volume:/var/run" \
    --env RUNNER_REGISTRATION_TOKEN \
    --env "RUNNER_URL=$runner_url" \
    --env "RUNNER_NAME=$runner_name" \
    --env "RUNNER_LABELS=${RUNNER_LABELS:-swarm,ubuntu-22,docker-isolated}" \
    --entrypoint /runner-entrypoint.sh "$image" >/dev/null
  worker_container=$worker_name
  unset registration_token

  # Background the attached client so signals can interrupt wait and clean up.
  host_docker start --attach "$worker_container" &
  local attach_pid=$!
  if wait "$attach_pid"; then attach_status=0; else attach_status=$?; fi
  read -r worker_state worker_status < <(host_docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$worker_container")
  if [[ "$worker_state" != exited ]]; then
    echo 'ERROR: runner attachment ended before the worker exited' >&2
    return 1
  fi
  [[ "$worker_status" =~ ^[0-9]+$ ]] || return 1
  if ((worker_status == 0 && attach_status != 0)); then
    return "$attach_status"
  fi
  return "$worker_status"
}

gh_pat='' api_scope='' runner_url='' runner_name='' worker_container='' daemon_container='' metadata_file=''
created_volumes=()
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
main "$@"
