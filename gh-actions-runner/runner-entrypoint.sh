#!/usr/bin/env bash
set -euo pipefail

cd /actions-runner
: "${RUNNER_REGISTRATION_TOKEN:?Set RUNNER_REGISTRATION_TOKEN}"
: "${RUNNER_URL:?Set RUNNER_URL}"
: "${RUNNER_NAME:?Set RUNNER_NAME}"

# Actions refuses service containers when it sees a host Docker cgroup path.
# The launcher supplies a private cgroup namespace; verify it before registering.
while IFS= read -r cgroup; do
  if [[ "${cgroup,,}" == *:/docker/* ]]; then
    echo 'ERROR: service containers require a private cgroup namespace' >&2
    exit 1
  fi
done < /proc/1/cgroup

# The socket belongs only to this worker's Docker daemon. Leave Docker context
# selection to the workflow, including remote contexts used by Swarm deploys.
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
chown root:docker /var/run/docker.sock
chmod 0660 /var/run/docker.sock
mkdir -p /actions-runner/_work/_temp /opt/hostedtoolcache
chown runner:runner /actions-runner/_work /actions-runner/_work/_temp /opt/hostedtoolcache

# Tests also bind temporary fixture files into Docker containers. Keep those
# files within the workspace volume visible at the same path in both containers.
export TMPDIR=/actions-runner/_work/_temp
export TMP="$TMPDIR" TEMP="$TMPDIR"

runuser -u runner -- ./config.sh \
  --unattended \
  --url "$RUNNER_URL" \
  --token "$RUNNER_REGISTRATION_TOKEN" \
  --name "$RUNNER_NAME" \
  --work _work \
  --labels "${RUNNER_LABELS:-swarm,ubuntu-22,docker-isolated}" \
  --ephemeral

unset RUNNER_REGISTRATION_TOKEN
exec runuser -u runner -- ./run.sh
