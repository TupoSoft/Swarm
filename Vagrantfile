VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = "ubuntu/jammy64"
  config.vm.provider "virtualbox" do |v|
      v.memory = 2048
      v.cpus = 2
  end

  %w[manager-1 manager-2 manager-3].each_with_index do |name, idx|
    config.vm.define name do |node|
      node.vm.hostname = name
      ip_last = idx + 11
      node.vm.network "private_network", ip: "192.168.56.#{ip_last}"

      node.vm.provision "shell", name: "install dependencies", inline: <<-SHELL
        sudo apt update
        sudo apt install -y jq
      SHELL

      node.vm.provision "shell", inline: <<-SHELL
        curl -fsSL https://get.docker.com -o get-docker.sh
        sh ./get-docker.sh
        groupadd -f docker
        usermod -aG docker vagrant
        newgrp docker
      SHELL

      if name == 'manager-1'
        node.vm.provision "shell", name: "init a cluster", inline: <<-SHELL
          docker swarm init --advertise-addr 192.168.56.11
          docker swarm join-token manager -q > /vagrant/.vagrant/manager-token
        SHELL
      else
        node.vm.provision "shell", name: "join the cluster", inline: <<-SHELL
          while [ ! -f /vagrant/.vagrant/manager-token ]; do sleep 2; done
          TOKEN=$(cat /vagrant/.vagrant/manager-token)
          docker swarm join --token $TOKEN 192.168.56.11:2377
        SHELL
      end
    end
  end
end
