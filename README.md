# Swarm Cluster

This repository contains the configuration and deployment scripts for a multi-node Docker Swarm cluster. It uses Vagrant for local development and Ansible for provisioning and infrastructure management.

## Project Structure

- **`ansible/`**: Contains Ansible playbooks, roles, and inventories for cluster setup and maintenance.
- **`stacks/`**: Docker Stack files (Compose format) for deploying services to the Swarm.
- **`configs/`**: Configuration files for various services (HAProxy, Nginx, CoreDNS, etc.).
- **`Vagrantfile`**: Defines the local development environment with 3 Ubuntu-based manager nodes.

## Infrastructure Components

- **Docker Swarm**: Orchestration for all services.
- **HAProxy**: Load balancing and entry point for the cluster.
- **Patroni + PostgreSQL**: Highly available PostgreSQL cluster.
- **Etcd**: Distributed key-value store used by Patroni for leader election.
- **CoreDNS**: Internal service discovery and DNS management.
- **Wireguard**: Secure VPN for inter-node communication.
- **nftables**: Advanced Linux firewall rules applied to all nodes.

## Prerequisites

- [Vagrant](https://www.vagrantup.com/)
- [VirtualBox](https://www.virtualbox.org/)
- [Ansible](https://www.ansible.com/)

## Getting Started

### Local Development

1.  **Bring up the VMs:**
    ```bash
    vagrant up
    ```
    This will create 3 manager nodes (`local-manager-1`, `local-manager-2`, `local-manager-3`) and automatically run the Ansible playbooks to:
    - Install Docker
    - Initialize the Swarm cluster
    - Configure networking (Wireguard, nftables)

2.  **SSH into a node:**
    ```bash
    vagrant ssh local-manager-1
    ```

### Deploying Stacks

To deploy a stack to the Swarm, use the `docker stack deploy` command. For example, to deploy the Patroni cluster:

```bash
docker stack deploy -c stacks/patroni.yml patroni
```

Note: Some stacks might require external secrets or networks to be created beforehand. Check the `external: true` definitions in the stack files.

## Available Stacks

- **`patroni.yml`**: HA PostgreSQL cluster.
- **`etcd.yml`**: Etcd cluster for Patroni.
- **`haproxy.yml`**: Load balancer.
- **`coredns.yml`**: Internal DNS.
- **`mongo.yml`**: MongoDB replica set.
- **`redis.yml`**: Redis Sentinel setup.
- **`postfixadmin.yml`**: PostfixAdmin for mail management.
- **`graylog.yml`**: Log management and analysis.

## Configuration & Overrides

The project supports environment-specific overrides for Docker stacks. See the `stacks/overrides/` directory for examples. These can be applied by including multiple compose files:

```bash
docker stack deploy -c stacks/patroni.yml -c stacks/overrides/patroni/patroni.override.yml patroni
```

## Maintenance Playbooks

Located in `ansible/playbooks/`:
- **`swarm.yml`**: Base cluster setup.
- **`wireguard.yml`**: VPN configuration.
- **`apply-nftables-rules.yml`**: Updates firewall rules.
- **`prune-unused-docker-volumes.yml`**: Cleanup script for unused volumes.
