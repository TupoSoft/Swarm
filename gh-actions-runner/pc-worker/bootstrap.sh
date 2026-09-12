#!/usr/bin/env bash
set -euo pipefail

[[ ${EUID} == 0 && $(hostname -s) == pc-swarm-worker ]] || {
  echo 'ERROR: run as root inside the pc-swarm-worker VM' >&2
  exit 1
}
[[ $(systemd-detect-virt --vm) == microsoft ]] || {
  echo 'ERROR: this bootstrap requires a Hyper-V VM' >&2
  exit 1
}
# shellcheck source=/dev/null
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || {
  echo 'ERROR: this bootstrap requires Ubuntu 24.04' >&2
  exit 1
}

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl jq wireguard-tools

install -d -m 0755 /etc/apt/keyrings
curl --fail --silent --show-error --location \
  https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod 0644 /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $VERSION_CODENAME
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

# Preserve existing daemon configuration when provisioning again.
install -d -m 0755 /etc/docker
if [[ ! -e /etc/docker/daemon.json ]]; then
  printf '%s\n' '{"log-driver":"local"}' > /etc/docker/daemon.json
fi
apt-get update
apt-get install -y --no-install-recommends \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
dockerd --validate --config-file /etc/docker/daemon.json
systemctl enable --now docker

install -d -m 0700 /etc/wireguard
if [[ ! -e /etc/wireguard/pc-swarm.key ]]; then
  (umask 077; wg genkey > /etc/wireguard/pc-swarm.key)
fi
wg pubkey < /etc/wireguard/pc-swarm.key > /etc/wireguard/pc-swarm.pub
chmod 0600 /etc/wireguard/pc-swarm.key
chmod 0644 /etc/wireguard/pc-swarm.pub

docker info --format 'Docker: {{.ServerVersion}}; Swarm: {{.Swarm.LocalNodeState}}'
printf 'Worker WireGuard public key: '
cat /etc/wireguard/pc-swarm.pub
echo 'Configure the VPN, then join Swarm as a drained worker before allowing jobs.'
