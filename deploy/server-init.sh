#!/bin/bash
# Runs on the server's first boot (Lightsail user data, as root): swap + Docker.
set -euxo pipefail

# 2 GB swap: 2 GB servers need it while building the frontend and loading the speech model
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10
  echo 'vm.swappiness=10' > /etc/sysctl.d/99-wealthpilot.conf
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2
systemctl enable --now docker
usermod -aG docker ubuntu
mkdir -p /opt/wealthpilot/releases /opt/wealthpilot/backups
