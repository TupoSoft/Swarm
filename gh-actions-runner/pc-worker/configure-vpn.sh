#!/usr/bin/env bash
set -euo pipefail

python3 - "$@" <<'PY'
import base64
import binascii
import ipaddress
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import tempfile


WIREGUARD_DIR = Path("/etc/wireguard")
SERVICE = "wg-quick@ci-swarm-wg0"


def validate_key(value, name):
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError(f"{name} must be a base64-encoded 32-byte WireGuard key") from None
    if len(decoded) != 32 or base64.b64encode(decoded).decode() != value:
        raise ValueError(f"{name} must be a base64-encoded 32-byte WireGuard key")
    return value


def validate_arguments(args):
    if len(args) != 4:
        raise ValueError("usage: configure-vpn.sh MANAGER_PUBLIC_KEY ENDPOINT PC_CIDR VPN_CIDR")
    public_key, endpoint, pc_cidr, vpn_cidr = args
    validate_key(public_key, "MANAGER_PUBLIC_KEY")
    host, separator, port = endpoint.rpartition(":")
    if not separator or not re.fullmatch(r"[0-9]+", port) or not 1 <= int(port) <= 65535:
        raise ValueError("ENDPOINT must be an IPv4 address or hostname followed by a port from 1 to 65535")
    if re.fullmatch(r"[0-9.]+", host):
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            raise ValueError("ENDPOINT contains an invalid IPv4 address") from None
    elif not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                         r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.?", host) or len(host) > 253:
        raise ValueError("ENDPOINT contains an invalid hostname")
    try:
        if "/" not in pc_cidr or "/" not in vpn_cidr:
            raise ValueError()
        address = ipaddress.IPv4Interface(pc_cidr)
        routes = ipaddress.IPv4Network(vpn_cidr, strict=True)
    except ValueError:
        raise ValueError("PC_CIDR must be an IPv4 interface and VPN_CIDR a canonical IPv4 network, both with prefix lengths") from None
    return public_key, f"{host}:{int(port)}", str(address), str(routes)


def main(args):
    public_key, endpoint, address, routes = validate_arguments(args)
    if os.geteuid() != 0 or socket.gethostname() != "pc-swarm-worker":
        raise ValueError("run as root inside the dedicated pc-swarm-worker Hyper-V guest")
    release = platform.freedesktop_os_release()
    if release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "24.04":
        raise ValueError("the VPN helper requires Ubuntu 24.04")
    if subprocess.check_output(["systemd-detect-virt"], text=True).strip() != "microsoft":
        raise ValueError("the VPN helper requires the dedicated Hyper-V guest")

    key_path = WIREGUARD_DIR / "pc-swarm.key"
    if not key_path.is_file():
        raise ValueError("run bootstrap.sh first to generate /etc/wireguard/pc-swarm.key")
    private_key = validate_key(key_path.read_text().strip(), "Worker private key")
    configuration = (
        "[Interface]\n"
        f"Address = {address}\n"
        f"PrivateKey = {private_key}\n"
        "\n[Peer]\n"
        f"PublicKey = {public_key}\n"
        f"Endpoint = {endpoint}\n"
        f"AllowedIPs = {routes}\n"
        "PersistentKeepalive = 25\n"
    )
    config_path = WIREGUARD_DIR / "ci-swarm-wg0.conf"
    if config_path.exists():
        if config_path.read_text() != configuration:
            raise ValueError(
                "VPN configuration differs. Drain pc-swarm-worker on the manager, stop "
                "wg-quick@ci-swarm-wg0, then remove /etc/wireguard/ci-swarm-wg0.conf "
                "before an intentional configuration change."
            )
        config_path.chmod(0o600)
    else:
        descriptor, temporary_path = tempfile.mkstemp(prefix=".ci-swarm-wg0-", dir=WIREGUARD_DIR)
        try:
            with os.fdopen(descriptor, "w") as temporary:
                temporary.write(configuration)
            os.replace(temporary_path, config_path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
    subprocess.run(["systemctl", "enable", "--now", SERVICE], check=True)
    print("WireGuard configured and started on ci-swarm-wg0. Verify the manager peer and VPN before joining Swarm.")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
PY
