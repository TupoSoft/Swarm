FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive

ARG RUNNER_VERSION

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
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
    gzip \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m runner \
    && mkdir /actions-runner \
    && chown runner:runner /actions-runner

WORKDIR /actions-runner

USER runner

RUN curl -O -L https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz \
    && tar xzf actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz \
    && rm actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

VOLUME [ "/actions-runner/_work" ]

ENTRYPOINT ["/entrypoint.sh"]
