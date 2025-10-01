FROM ubuntu:22.04

ARG JOERN_VERSION=4.0.361
ARG GHIDRA_TAG=Ghidra_11.4_build
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="/usr/local/bin:${PATH}"
ENV JOERN_PORT=8080

# Base deps + tiny init for clean shutdowns + minimal X11 tools for optional Ghidra GUI
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      openjdk-17-jdk git unzip wget curl ca-certificates \
      xauth x11-apps locales tini && \
    rm -rf /var/lib/apt/lists/* && \
    update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-17-openjdk-amd64/bin/java 1

# Joern
RUN set -eux; \
    mkdir -p /opt/joern; \
    wget --progress=dot:giga -O /tmp/joern-cli.zip \
      "https://github.com/joernio/joern/releases/download/v${JOERN_VERSION}/joern-cli.zip"; \
    unzip -q /tmp/joern-cli.zip -d /opt/joern; \
    rm -f /tmp/joern-cli.zip; \
    ln -sf /opt/joern/joern-cli/joern /usr/local/bin/joern; \
    test -x /usr/local/bin/joern

# Ghidra 11.4_PUBLIC
RUN set -eux; \
    INSTALL_BASE="/opt"; \
    GH_API="https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/tags/${GHIDRA_TAG}"; \
    GH_URL="$(curl -s "${GH_API}" | grep '"browser_download_url":' | grep '.zip"' | head -n1 | cut -d '"' -f4)"; \
    wget --progress=dot:giga -O /tmp/ghidra.zip "${GH_URL}"; \
    unzip -q /tmp/ghidra.zip -d "${INSTALL_BASE}"; \
    rm -f /tmp/ghidra.zip; \
    EXIST_GH="$(find "${INSTALL_BASE}" -maxdepth 1 -type d -name "ghidra_11.4_PUBLIC*" | head -n1)"; \
    chmod +x "${EXIST_GH}/ghidraRun"; \
    ln -sf "${EXIST_GH}/ghidraRun" /usr/local/bin/ghidra; \
    ln -sf "${EXIST_GH}/support/analyzeHeadless" /usr/local/bin/ghidraHeadless; \
    chmod +x /usr/local/bin/ghidraHeadless

# Workspace
RUN mkdir -p /workspace && chmod 777 /workspace
WORKDIR /workspace

# Smoke checks (don’t launch UIs during build)
RUN joern --help >/dev/null 2>&1 || true; \
    ghidraHeadless >/dev/null 2>&1 || true

# Default: start Joern server
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/bin/bash", "-lc", "exec joern --server --server-port ${JOERN_PORT}"]