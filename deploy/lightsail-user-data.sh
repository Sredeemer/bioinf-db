#!/bin/bash
set -e

# Enable swap
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Install Docker and prerequisites
apt-get update -y
apt-get install -y ca-certificates curl gnupg git

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow ubuntu user to run docker
usermod -aG docker ubuntu

# Single-folder storage invariants
mkdir -p /srv/ubuntubio/data/xet
mkdir -p /srv/ubuntubio/data/git
mkdir -p /srv/ubuntubio/data/tmp
mkdir -p /srv/ubuntubio/data/caddy_data
mkdir -p /srv/ubuntubio/data/caddy_config
mkdir -p /srv/ubuntubio/app

chown -R ubuntu:ubuntu /srv/ubuntubio
