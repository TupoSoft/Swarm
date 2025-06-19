FROM ubuntu:22.04

# Define arguments
ARG DEBIAN_FRONTEND=noninteractive

# Ensure base system is up-to-date and install base dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    curl \
    git \
    jq \
    ca-certificates \
    libicu70 \
    libssl3 \
    libkrb5-3 \
    libssl-dev \
    libunwind8 \
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

# Configure non-root user and permissions
RUN groupadd -f docker && \
    useradd -m runner && \
    usermod -aG docker runner && \
    mkdir -p /actions-runner/_work && \
    chown -R runner:runner /actions-runner

# Switch to non-root user
USER runner
WORKDIR /actions-runner

ARG RUNNER_VERSION

# Download and extract GitHub Actions Runner
RUN curl -LO https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz && \
    tar xzf actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz && \
    rm actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

# Define volumes and entrypoint
VOLUME [ "/actions-runner/_work" ]
ENTRYPOINT ["/entrypoint.sh"]
