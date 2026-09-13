# Optional PC Worker from WSL

Run Linux Vagrant and Ansible inside WSL to manage a dedicated Ubuntu 24.04 Hyper-V VM.
The VM contributes one GitHub Actions job slot while the PC is awake and connected.
It has its own kernel, networking, filesystem, and Docker daemon. The permanent server
runner pool keeps its existing capacity.

## Prerequisites

Use Linux Vagrant 2.4.9 or newer inside WSL, with the same Vagrant version installed on
Windows. Install the full Ansible package, Python 3, OpenSSH, and the standard `ip`,
`findmnt`, and `wslpath` tools in WSL. Windows needs Hyper-V and its `Default Switch`.
See [Vagrant's WSL instructions](https://developer.hashicorp.com/vagrant/docs/other/wsl).

Start WSL from a Windows Terminal session with permission to manage Hyper-V virtual machines. Windows
administrator access or membership in Hyper-V Administrators is required. Linux `sudo`
does not grant Windows permissions. Windows executable interoperability must be enabled.
All commands below run inside WSL.

Keep a full checkout of this repository on the Linux filesystem. Provisioning uses the
shared Ansible files under `ansible/`, so copying this directory alone is insufficient.

## Start the Worker

From the repository root:

```bash
cd gh-actions-runner/pc-worker
cp worker.example.yml worker.local.yml
```

Edit `worker.local.yml` with the worker's unused VPN address, VPN subnet, manager public
key, and public VPN endpoint. These are public connection settings; private keys and
Swarm join tokens do not belong in this file. The file is ignored by Git.

```bash
./vagrant-wsl validate
./vagrant-wsl up
```

The launcher selects Linux Vagrant and the Hyper-V provider, enables Windows access,
and supplies the Windows executable paths. It also checks for a conflicting WSL route
to the VM network before starting or connecting to the VM.

The VM uses six virtual CPUs and `12 GiB` of memory, leaving room beyond the job's
container limits. The community-maintained `gusztavvargadr/ubuntu-server-2404-lts` box
is pinned to `2607.0.0` for Hyper-V on AMD64. Shared host folders are disabled.

The normal Ansible provisioner runs on the WSL host. It installs Docker through the
same tasks used by the existing Swarm playbook and configures WireGuard through the
existing pinned role. Vagrant installs that role from `ansible/requirements.yml`.
Its generated inventory contains only this VM and does not load the production
inventory or vault. Provisioning neither joins Swarm nor assigns database labels.

Ansible prints the worker's public key after provisioning. Retrieve it again with:

```bash
./vagrant-wsl ssh -c 'sudo wg show ci-swarm-wg0 public-key'
```

Register that public key on the manager with the worker's VPN address as its allowed
address. Preserve the existing peers and persist the addition. Then verify a recent
handshake and manager reachability, replacing the address placeholder:

```bash
./vagrant-wsl ssh -c 'sudo wg show ci-swarm-wg0 latest-handshakes; ping -c 3 <MANAGER_VPN_IP>'
```

## Windows Storage and Linux Keys

Hyper-V needs VM files on a Windows drive. The launcher defaults to:

- Windows Vagrant cache: `<Windows profile>/.vagrant.d`.
- VM state: `<Windows profile>/Vagrant/SwarmWorker/.vagrant`.
- Ansible SSH key: `~/.local/share/swarm-pc-worker/ssh/private_key` inside Linux.

The first two locations can be overridden with `VAGRANT_HOME` and `VAGRANT_DOTFILE_PATH`;
use WSL paths such as `/mnt/c/Users/...`. The SSH location can be overridden with
`PC_WORKER_SSH_KEY_PATH` and must remain on the Linux filesystem. Reuse the same state
location for every lifecycle command so Vagrant continues managing the same VM.

The launcher refreshes the Linux SSH key copy for existing VMs; the Ansible adapter
also copies the newly generated key during first provisioning. They set directory
permissions to `0700` and key permissions to `0600`.
This lets Linux OpenSSH use the key when Windows storage does not enforce Linux modes.
The adapter handles host authentication only; guest provisioning stays in Ansible.

## Network Conflicts

The launcher stops before VM startup if a Docker bridge or inactive route intercepts
traffic for the Hyper-V Default Switch. It reports the subnet, interface, and current
route without changing networking. Fix the conflicting subnet or route before retrying.

On this PC, the observed Default Switch subnet was `172.18.240.0/20`; WSL routed it to a
Docker bridge covering `172.18.0.0/16`. In WSL NAT mode, a route through the current Windows
gateway can resolve that overlap. Recheck the subnet and gateway after a Windows or WSL
restart, and replace both placeholders before using this command:

```bash
ip route show default
sudo ip route replace <CURRENT_HYPERV_SUBNET> via <CURRENT_WINDOWS_GATEWAY> dev <WSL_INTERFACE>
```

This route is temporary. Verify guest SSH after correcting it. Changing WSL-wide mounts,
Docker networks, or Windows switches is not part of provisioning.

## Join and Activate

Use the fixed WireGuard address for Swarm's advertised address and data path. Keep TCP
2377, TCP/UDP 7946, and UDP 4789 reachable over the private network. Keep overlay traffic
off public interfaces. See [Docker's network requirements](https://docs.docker.com/engine/swarm/swarm-tutorial/#open-protocols-and-ports-between-the-hosts).

1. Obtain a worker join token from the manager. Inside the guest, join with
   `--availability drain`, the worker VPN address for both `--advertise-addr` and
   `--data-path-addr`, and the manager VPN address as the destination.
2. Confirm that Swarm reports `pc-swarm-worker` as a ready worker with drained availability.
   Add the `ci_optional=true` node label from the manager. Leave database role and zone labels unset.
3. Apply and verify placement exclusions on every live service, including services deployed
   from other repositories. A node label alone does not exclude unrestricted services.
4. Deploy the runner stack with registry authentication, then activate the node. Confirm
   that only its optional launcher runs there and that a validation job receives a fresh
   worker and private Docker daemon.

The optional service runs one launcher on each active Linux x86-64 node labeled
`ci_optional=true`. It reserves four CPUs and `8G` of memory. The job worker and private
Docker daemon each have limits of two CPUs and `4g`. The permanent pool and otherwise
unrestricted application services exclude these nodes.

Runner labels are `swarm,ubuntu-22,docker-isolated,personal-pc`. Ubuntu 22 describes the
runner image; Ubuntu 24.04 describes the VM host. Existing matching workflows can use
this slot. The original Ansible Swarm playbook still joins managers and must not be used
for this worker.

## Pause, Stop, and Reprovision

On the manager, pause scheduling and let the existing runner finish:

```bash
docker node update --availability pause pc-swarm-worker
```

An idle registered runner can still accept one job while paused, but Swarm will not
start its replacement. After the worker and private daemon are removed, drain the node:

```bash
docker node update --availability drain pc-swarm-worker
```

Draining a busy launcher interrupts its job. To stop the VM, run in WSL:

```bash
./vagrant-wsl halt
```

For an intentional configuration change, finish and drain jobs first, edit
`worker.local.yml`, then run `./vagrant-wsl provision`. Ansible preserves existing Docker
configuration and the VPN private key. Changed VPN settings can restart its interface.
Use at most `-vv` for Ansible diagnostics; the playbook rejects higher verbosity because
the upstream WireGuard role can reveal private keys at those levels.

Restart with `./vagrant-wsl up`, verify the VPN, and activate the node from the manager
when offering its capacity. Ordinary startup after initial creation does not rerun
provisioning. The VM does not start automatically with Windows. Sleeping or shutting down
the PC during a job can make that job fail.
