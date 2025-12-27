require "vagrant"

VAGRANTFILE_API_VERSION = "2"

MANAGER_COUNT = 3
MANAGER_IP_BASE = "192.168.56"
WIREGUARD_IP_BASE = "192.168.57"
WIREGUARD_IP_SUBNET = 24
WIREGUARD_WORKSTATION_IP = "#{WIREGUARD_IP_BASE}.254"
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

  (1..MANAGER_COUNT).each do |i|
    name = "local-manager-#{i}"
    ip_last = MANAGER_IP_START + i - 1
    ssh_port = SSH_PORT_START + i - 1
    node_ip = "#{MANAGER_IP_BASE}.#{ip_last}"

    config.vm.define name do |node|
      node.vm.hostname = name
      node.vm.network "private_network", ip: node_ip
      node.vm.network "forwarded_port", guest: 22, host: ssh_port, id: "ssh"

      node.vm.provision "prune-volumes",
        type: "ansible",
        run: "never",
        playbook: "ansible/playbooks/prune-unused-docker-volumes.yml",
        inventory_path: "ansible/inventory/local",
        limit: "swarm"

      if i == MANAGER_COUNT
        node.vm.provision "wireguard",
          type: "ansible",
          playbook: "ansible/playbooks/local-wireguard.yml",
          config_file: "ansible/ansible.cfg",
          inventory_path: "ansible/inventory/local",
          limit: "swarm"

        node.vm.provision "swarm",
          type: "ansible",
          playbook: "ansible/playbooks/local-swarm.yml",
          config_file: "ansible/ansible.cfg",
          inventory_path: "ansible/inventory/local",
          limit: "swarm"
      end
    end
  end
end

local_vagrantfile = File.join(File.dirname(__FILE__), "Vagrantfile.local")
load local_vagrantfile if File.exist?(local_vagrantfile)
