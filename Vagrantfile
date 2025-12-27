require "vagrant"

VAGRANTFILE_API_VERSION = "2"

MANAGER_COUNT = 3
MANAGER_IP_BASE = "192.168.56"
MANAGER_IP_START = 11
SSH_PORT_START = 2200
VM_MEMORY = 2048
VM_CPUS = 2

# @param [VagrantPlugins::Kernel_V2::VMConfig] vm
# @param [String] playbook
# @param [String] run
# @param [String] limit
# @return [Void]
def provision_ansible(vm, playbook, run: "once", limit: "swarm")
  vm.provision playbook.split("/").last.sub(".yml", ""),
    type: "ansible",
    run: run,
    playbook: playbook,
    config_file: "ansible/ansible.cfg",
    inventory_path: "ansible/inventory/local",
    limit: limit
end

# @param [VagrantPlugins::Kernel_V2::VMConfig] config
# @param [Integer] index
# @return [Void]
def configure_node(config, index)
  name = "local-manager-#{index}"
  ssh_port = SSH_PORT_START + index - 1
  node_ip = "#{MANAGER_IP_BASE}.#{MANAGER_IP_START + index - 1}"

  config.define name do |node|
    # @type [VagrantPlugins::Kernel_V2::VMConfig]
    vm = node.vm
    vm.hostname = name
    vm.network :private_network, ip: node_ip
    vm.network :forwarded_port, guest: 22, host: ssh_port, id: "ssh"

    if index == MANAGER_COUNT
      provision_ansible vm, "ansible/playbooks/prune-unused-docker-volumes.yml", run: "never"
      provision_ansible vm, "ansible/playbooks/local-wireguard.yml"
      provision_ansible vm, "ansible/playbooks/local-swarm.yml"
      provision_ansible vm, "ansible/playbooks/apply-nftables-rules.yml"
    end
  end
end

# @type [Vagrant::Plugin::V1::Guest] config
Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  # @type [VagrantPlugins::Kernel_V2::VMConfig]
  vm = config.vm

  vm.box = "ubuntu/jammy64"

  vm.provider :virtualbox do |v|
    v.memory = VM_MEMORY
    v.cpus = VM_CPUS
  end

  (1..MANAGER_COUNT).each { |index| configure_node config.vm, index }
end

local_vagrantfile = File.join(File.dirname(__FILE__), "Vagrantfile.local")
load local_vagrantfile if File.exist?(local_vagrantfile)
