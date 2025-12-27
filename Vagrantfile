require 'vagrant'

VAGRANTFILE_API_VERSION = "2"

MANAGER_COUNT = 3
MANAGER_IP_BASE = "192.168.56"
WIREGUARD_IP_BASE = "192.168.57"
WIREGUARD_IP_SUBNET = 24
MANAGER_IP_START = 11
SSH_PORT_START = 2200
VM_MEMORY = 2048
VM_CPUS = 2

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = "ubuntu/jammy64"

  config.vm.provider "virtualbox" do |v|
    v.memory = VM_MEMORY
    v.cpus = VM_CPUS
  end

  nodes = []
  host_vars = {}

  (1..MANAGER_COUNT).each do |i|
    name = "local-manager-#{i}"
    ip_last = MANAGER_IP_START + i - 1
    ssh_port = SSH_PORT_START + i - 1
    node_ip = "#{MANAGER_IP_BASE}.#{ip_last}"

    nodes << name

    host_vars[name] = {
      wireguard_addresses: "'[\"#{WIREGUARD_IP_BASE}.#{ip_last}/#{WIREGUARD_IP_SUBNET}\"]'",
      wireguard_endpoint: node_ip,
    }

    config.vm.define name do |node|
      node.vm.hostname = name
      node.vm.network "private_network", ip: node_ip
      node.vm.network "forwarded_port", guest: 22, host: ssh_port, id: "ssh"

      node.vm.provision "prune-volumes", type: "shell", run: "never", name: "Prune unused Docker volumes", inline: <<-SHELL
        set -euo pipefail
        if command -v docker >/dev/null 2>&1; then
          echo "Pruning unused Docker volumes..."
          sudo docker volume prune -af || true
        else
          echo "Docker not installed; skipping."
        fi
      SHELL

      if i == MANAGER_COUNT
        node.vm.provision "wg-mesh",
                          type: "ansible",
                          playbook: "ansible/local-swarm.yml",
                          config_file: "ansible/ansible.cfg",
                          limit: "vpn",
                          host_vars: host_vars,
                          groups: {
                            vpn: nodes,
                            "vpn:vars": {
                              ansible_python_interpreter: "/usr/bin/python3.10",
                              wireguard_preup: ["echo 1 > /proc/sys/net/ipv4/ip_forward"],
                            }
                          }
      end
    end
  end
end

local_vagrantfile = File.join(File.dirname(__FILE__), 'Vagrantfile.local')
load local_vagrantfile if File.exist?(local_vagrantfile)
