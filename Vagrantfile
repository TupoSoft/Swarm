VAGRANTFILE_API_VERSION = "2"

MANAGER_COUNT = 3
MANAGER_IP_BASE = "192.168.56"
MANAGER_IP_START = 11
VM_MEMORY = 2048
VM_CPUS = 2

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = "ubuntu/jammy64"

  config.vm.provider "virtualbox" do |v|
      v.memory = VM_MEMORY
      v.cpus = VM_CPUS
  end

  (1..MANAGER_COUNT).each do |i|
    name = "manager-#{i}"

    config.vm.define name do |node|
      node.vm.hostname = name
      ip_last = MANAGER_IP_START + i - 1
      node.vm.network "private_network", ip: "#{MANAGER_IP_BASE}.#{ip_last}"

      node.vm.provision "shell", name: "install dependencies", inline: <<-SHELL
        apt-get update
        apt-get install -y jq
      SHELL

      node.vm.provision "shell", name: "install docker", inline: <<-SHELL
        if ! command -v docker &> /dev/null; then
          curl -fsSL https://get.docker.com -o get-docker.sh
          sh ./get-docker.sh
          rm get-docker.sh
        fi
        groupadd -f docker
        usermod -aG docker vagrant
        newgrp docker
      SHELL

      if name == 'manager-1'
        node.vm.provision "shell", name: "init a cluster", inline: <<-SHELL
          if ! docker info | grep -q "Swarm: active"; then
            docker swarm init --advertise-addr 192.168.56.11
          fi
          docker swarm join-token manager -q > /vagrant/.vagrant/manager-token
        SHELL
      else
        node.vm.provision "shell", name: "join the cluster", inline: <<-SHELL
          if ! docker info | grep -q "Swarm: active"; then
            while [ ! -f /vagrant/.vagrant/manager-token ]; do sleep 2; done
            TOKEN=$(cat /vagrant/.vagrant/manager-token)
            docker swarm join --token $TOKEN 192.168.56.11:2377
          fi
        SHELL
      end
    end
  end
end

local_vagrantfile = File.join(File.dirname(__FILE__), 'Vagrantfile.local')
load local_vagrantfile if File.exist?(local_vagrantfile)
