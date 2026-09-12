# Optional PC Worker

A dedicated Ubuntu 24.04 Hyper-V virtual machine can contribute one GitHub Actions job slot while the
PC is awake and connected. Vagrant manages the VM, which joins Swarm as a worker. The permanent
server runner pool keeps its existing replica count and resource settings.

## Virtual Machine and Docker

The [VM definition](Vagrantfile) creates the VM named `pc-swarm-worker`, with the same Linux hostname.
It has its own Linux kernel, network interfaces, filesystem, and Docker daemon. The VM has six virtual
CPUs and `12 GiB` of memory, leaving capacity for the guest operating system beyond the runner's
reservation described below. It uses the community-maintained
`gusztavvargadr/ubuntu-server-2404-lts` box, pinned to version `2607.0.0` for Hyper-V on AMD64.

Run Vagrant from an elevated Windows PowerShell session with Hyper-V enabled. See
[Vagrant's Hyper-V provider documentation](https://developer.hashicorp.com/vagrant/docs/providers/hyperv).
Use the Hyper-V `Default Switch` for outbound connectivity through NAT. Vagrant's Hyper-V provider
does not create or configure virtual switches; it uses an existing switch. See the
[provider's networking limitations](https://developer.hashicorp.com/vagrant/docs/providers/hyperv/limitations).

The Swarm worker needs Docker Engine running as root because rootless Docker does not support the
required overlay networking. See [Docker's rootless limitations](https://docs.docker.com/engine/security/rootless/troubleshoot/#known-limitations).
The [bootstrap script](bootstrap.sh) prepares Docker and WireGuard tools inside the Ubuntu 24.04 guest.
Docker uses its standard `docker0` bridge within the VM. Repeated provisioning preserves existing
Docker daemon configuration and the guest's WireGuard private key. Shared host folders are disabled.
Before explicitly rerunning provisioning, finish any active job and drain the node using the shutdown
sequence below. Provisioning can upgrade Docker packages and restart the daemon. Ordinary `vagrant up`
after initial creation does not rerun provisioning.

The guest reaches the cluster through WireGuard. Keep its private keys and Swarm join tokens outside
the repository. Review the VM's Docker address pools against the VPN and cluster networks before
joining.

## Network and Placement

Use a private VPN connection between `<PC_VPN_IP>` and `<MANAGER_VPN_IP>`. The manager's public VPN
endpoint is `<MANAGER_PUBLIC_IP>:<VPN_UDP_PORT>`. Configure the corresponding peer public keys and
routes before joining. Use the PC's VPN address for both Swarm's advertised address and data path.

After creating the VM, read its public key from the same Vagrant directory in Windows PowerShell:

```powershell
vagrant ssh -c "sudo cat /etc/wireguard/pc-swarm.pub"
```

Register this public key on the manager as a WireGuard peer with the PC's VPN address as its allowed
address. Preserve the manager's existing peers and make the additional peer configuration persistent.
Vagrant installs the [VPN configuration script](configure-vpn.sh) as `configure-swarm-vpn` in the guest.
Configure its manager peer from Windows PowerShell, replacing all placeholders:

```powershell
vagrant ssh -c "sudo configure-swarm-vpn '<MANAGER_PUBLIC_KEY>' '<MANAGER_PUBLIC_IP>:<VPN_UDP_PORT>' '<PC_VPN_IP>/32' '<VPN_CIDR>'"
```

The script enables `ci-swarm-wg0` with `PersistentKeepalive=25` so the guest can
maintain its connection through NAT. It accepts an identical configuration on subsequent runs and
rejects changes to an existing configuration. Drain the node and stop the VPN before deliberately
replacing that configuration. Configuring the VPN does not join Swarm.
Check that the manager responds and that WireGuard reports a recent handshake before joining:

```powershell
vagrant ssh -c "sudo wg show ci-swarm-wg0 latest-handshakes; ping -c 3 <MANAGER_VPN_IP>"
```

Swarm uses these ports within the private network:

- TCP port 2377 for management.
- TCP and UDP port 7946 for node communication.
- UDP port 4789 for overlay traffic.

Keep overlay traffic within the private network. See
[Docker's networking requirements](https://docs.docker.com/engine/swarm/swarm-tutorial/#open-protocols-and-ports-between-the-hosts).

Label the node `ci_optional=true`. Leave database role and zone labels unset. The
`actions-runner-optional` service runs globally, with one launcher on each active Linux x86-64 node
carrying this label. Each launcher reserves four CPUs and `8G` of memory. The job worker and its
private Docker daemon each have limits of two CPUs and `4g` of memory.

The worker registers with `swarm,ubuntu-22,docker-isolated,personal-pc` labels. Ubuntu 22 describes the
runner container image; Ubuntu 24.04 describes its VM host. Existing workflows matching these labels
can use the PC, including deployment workflows.

The permanent runner service and otherwise unrestricted application services exclude
`node.labels.ci_optional == true` through the constraint `node.labels.ci_optional != true`.
Other database services already require labels or hostnames that this PC does not have.
Audit every live service before activating the node, including services deployed from other
repositories. Add the exclusion wherever an existing constraint would still allow this PC. A node
label alone does not stop an unrestricted service from using the node.

## Drained Rollout

1. Create the VM with Vagrant and confirm that its Docker daemon and VPN work.
2. Obtain a worker join token from the manager. Join with `--availability drain`, the PC's VPN address
   for `--advertise-addr` and `--data-path-addr`, and the manager's VPN address as the destination.
3. Confirm that Swarm reports the new node as a worker with `Ready` status and `Drain` availability.
   Add the `ci_optional=true` node label from the manager.
4. Apply and verify the placement exclusions on every live service. Deploy the runner stack with
   registry authentication so the new node can pull its private image and receive the existing runner
   registration secret. Keep the new node drained until these checks pass.
5. Activate the node. Confirm that only the optional runner launcher is scheduled there and that its
   worker registers in GitHub. Run a validation job and confirm that the next job receives a fresh
   worker and private Docker daemon.

The existing Ansible Swarm playbook joins additional nodes as managers. It must be adapted before
using it for this optional worker. Swarm's drained state prevents new service tasks; it does not stop
standalone containers created with `docker run`. See
[Docker's drain behavior](https://docs.docker.com/engine/swarm/swarm-tutorial/drain-node/).

## Manual Start and Stop

Keep the files in this directory together in your Windows copy. On this PC, use
`C:\Users\kyryl\Vagrant\SwarmWorker` as the Vagrant project directory. From elevated Windows
PowerShell, open that directory and start the VM:

```powershell
Set-Location 'C:\Users\kyryl\Vagrant\SwarmWorker'
vagrant up --provider=hyperv
```

Use `vagrant ssh` to open the guest shell. Docker starts through systemd after bootstrap. Confirm the
VPN is connected before making the node active from the Swarm manager:

```bash
docker node update --availability active pc-swarm-worker
```

For planned shutdown, pause scheduling from the manager and let the current runner finish its job:

```bash
docker node update --availability pause pc-swarm-worker
```

An existing idle runner can still accept a job while the node is paused. Pause prevents a replacement
launcher from starting after that runner exits. Wait until its worker and private Docker daemon have
been removed, then drain the node from the manager:

```bash
docker node update --availability drain pc-swarm-worker
```

If an idle runner is still waiting for work, draining stops it. Draining during a job interrupts that job.
Finally, shut down the VM from the same Vagrant directory in Windows PowerShell:

```powershell
vagrant halt
```

Start the VM again with `vagrant up --provider=hyperv`, verify its VPN, and activate its Swarm node when
offering its capacity. No Windows task starts the VM automatically. Sleeping, restarting Windows, or
stopping the VM during a job can cause that job to fail.
