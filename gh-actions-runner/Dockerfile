FROM ubuntu:22.04

# Define arguments
ARG DEBIAN_FRONTEND=noninteractive

# Ensure base system is up-to-date and install base dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    curl \
    git \
    jq \
    gettext-base \
    ca-certificates \
    sudo \
    tini \
    python3 \
    build-essential \
    unzip \
    zip \
    xz-utils \
    bzip2 \
    libicu70 \
    libssl3 \
    libkrb5-3 \
    libssl-dev \
    libunwind8 \
    libyaml-0-2 \
    libgmp10 \
    libreadline8 \
    zlib1g \
    tzdata \
    gzip && \
    rm -rf /var/lib/apt/lists/*

# Add Docker's GPG key and configure Docker repository
RUN install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker components
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m runner && \
    usermod -aG docker runner && \
    mkdir -p /actions-runner/_work /opt/hostedtoolcache && \
    chown -R runner:runner /actions-runner /opt/hostedtoolcache && \
    printf 'runner ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/runner && \
    chmod 0440 /etc/sudoers.d/runner

ENV RUNNER_TOOL_CACHE=/opt/hostedtoolcache

WORKDIR /actions-runner

ARG RUNNER_VERSION=2.337.0
ARG RUNNER_SHA256=70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613

# Download and extract GitHub Actions Runner
RUN curl --fail --location --retry 3 -O https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz && \
    printf '%s  %s\n' "$RUNNER_SHA256" "actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz" | sha256sum --check --strict && \
    tar xzf actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz && \
    rm actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz && \
    chown -R runner:runner /actions-runner

# The launcher creates job-owned volumes; workers never inherit its host socket or PAT.
COPY --chmod=755 gh-actions-runner/entrypoint.sh gh-actions-runner/runner-entrypoint.sh /
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
