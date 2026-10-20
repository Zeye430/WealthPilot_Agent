#!/bin/bash
# 服务器首次开机时执行（Lightsail user-data，以 root 运行）：交换空间 + Docker。
set -euxo pipefail

# 2 GB 交换空间：2 GB 内存的机型在构建前端、加载语音模型时需要
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
