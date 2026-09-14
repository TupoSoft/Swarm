FROM node:24-bookworm-slim AS node-runtime

FROM ubuntu:22.04

# Define arguments
ARG DEBIAN_FRONTEND=noninteractive

# Ensure base system is up-to-date and install base dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    curl \
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

# Ubuntu 22.04's Git cannot emit the NUL-delimited history required by consumers.
# Use the stable PPA recommended by https://git-scm.com/install/linux.
RUN install -m 0755 -d /etc/apt/keyrings && \
    curl --fail --location --retry 3 \
    'https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xF911AB184317630C59970973E363C90F8F1B6217' \
    -o /etc/apt/keyrings/git-core.asc && \
    chmod a+r /etc/apt/keyrings/git-core.asc && \
    echo 'deb [signed-by=/etc/apt/keyrings/git-core.asc] https://ppa.launchpadcontent.net/git-core/ppa/ubuntu jammy main' \
    > /etc/apt/sources.list.d/git-core.list && \
    apt-get update && apt-get install -y --no-install-recommends git && \
    dpkg --compare-versions "$(git --version | cut -d ' ' -f 3)" ge 2.50.0 && \
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

# Exercise the real Git binary as the job user before the image can be published.
COPY gh-actions-runner/tests/check_git_capabilities.py /tmp/check_git_capabilities.py
RUN runuser -u runner -- python3 /tmp/check_git_capabilities.py && \
    rm /tmp/check_git_capabilities.py

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

# Supply the standard Node/npm toolchain without changing the runner's Ubuntu base.
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

ARG PLAYWRIGHT_VERSION=1.63.0
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

# Install the same Playwright version selected by the consumer's lockfile.
COPY gh-actions-runner/install-chromium.sh /tmp/install-chromium.sh
RUN sh /tmp/install-chromium.sh

# An offline check as the job user proves browser reuse and launch before publishing.
COPY gh-actions-runner/tests/check_browser_capabilities.cjs /tmp/check_browser_capabilities.cjs
RUN --network=none runuser -u runner -- playwright install chromium
RUN --network=none runuser -u runner -- node /tmp/check_browser_capabilities.cjs \
    /usr/local/lib/node_modules/playwright "$PLAYWRIGHT_VERSION"
RUN rm /tmp/check_browser_capabilities.cjs /tmp/install-chromium.sh

# The launcher creates job-owned volumes; workers never inherit its host socket or PAT.
COPY --chmod=755 gh-actions-runner/entrypoint.sh gh-actions-runner/runner-entrypoint.sh /
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
