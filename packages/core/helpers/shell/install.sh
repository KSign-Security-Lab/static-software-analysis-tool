#!/usr/bin/env bash
set -euo pipefail

# Usage: sudo ./install-tools.sh [--reinstall]
REINSTALL=false
[[ "${1-:-}" == "--reinstall" ]] && REINSTALL=true

# Require root to avoid mixed sudo calls later
if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root: sudo $0 [--reinstall]" >&2
  exit 1
fi

# Resolve the real target user (who invoked sudo), fallback to root
TARGET_USER="${SUDO_USER:-root}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"

echo "→ Installing APT dependencies"
apt-get update
apt-get install -y --no-install-recommends default-jdk git unzip wget curl ca-certificates
rm -rf /var/lib/apt/lists/*

# 2) Joern v4.0.361
JOERN_VERSION="4.0.361"
JOERN_URL="https://github.com/joernio/joern/releases/download/v${JOERN_VERSION}/joern-cli.zip"
JOERN_BASE="/opt/joern/joern-cli"
JOERN_BIN="${JOERN_BASE}/joern"
JOERN_JAR="${JOERN_BASE}/lib/io.joern.joern-cli-${JOERN_VERSION}.jar"

if [[ -x "$JOERN_BIN" && -f "$JOERN_JAR" && "$REINSTALL" != true ]]; then
  echo "✓ Joern ${JOERN_VERSION} already installed (jar present)"
else
  echo "→ Installing Joern ${JOERN_VERSION}"
  rm -rf "/opt/joern" /usr/local/bin/joern
  mkdir -p "$(dirname "$JOERN_BASE")"
  wget --show-progress "$JOERN_URL" -O /tmp/joern-cli.zip
  unzip -q /tmp/joern-cli.zip -d /opt/joern
  # Ensure world read/exec so non-root users can run it
  chmod -R a+rX /opt/joern
  for tool in joern joern-parse joern-export joern-scan; do
    ln -sf "$JOERN_BASE/$tool" /usr/local/bin/$tool
  done
  echo "✓ Joern installed to $JOERN_BASE"
fi

# 3) Ghidra 11.4_PUBLIC
GHIDRA_TAG="Ghidra_11.4_build"
GH_API="https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/tags/${GHIDRA_TAG}"
INSTALL_BASE="/opt"

# locate existing Ghidra install (any suffix)
EXIST_GH=$(find "$INSTALL_BASE" -maxdepth 1 -type d -name "ghidra_11.4_PUBLIC*" | head -n1 || true)

if [[ -n "$EXIST_GH" && "$REINSTALL" != true ]]; then
  echo "✓ Ghidra already installed at $(basename "$EXIST_GH")"
else
  echo "→ Resolving Ghidra download URL"
  GH_URL=$(curl -fsSL "$GH_API" \
    | grep -E '"browser_download_url":' \
    | grep -E '\.zip"' \
    | head -n1 \
    | cut -d '"' -f4)
  if [[ -z "${GH_URL:-}" ]]; then
    echo "Could not resolve Ghidra download URL from GitHub API" >&2
    exit 2
  fi
  echo "→ Downloading Ghidra"
  rm -rf ${INSTALL_BASE}/ghidra_11.4_PUBLIC* || true
  rm -f /usr/local/bin/ghidra /usr/local/bin/ghidraHeadless
  wget --show-progress "$GH_URL" -O /tmp/ghidra.zip
  unzip -q /tmp/ghidra.zip -d "$INSTALL_BASE"
  EXIST_GH=$(find "$INSTALL_BASE" -maxdepth 1 -type d -name "ghidra_11.4_PUBLIC*" | head -n1)
  # Ensure scripts are executable and traversable by all users
  chmod -R a+rX "$EXIST_GH"
  chmod +x "$EXIST_GH/ghidraRun" "$EXIST_GH/support/analyzeHeadless"
  echo "✓ Ghidra installed to $(basename "$EXIST_GH")"
fi

# 4) Symlinks
if [[ -n "$EXIST_GH" ]]; then
  ln -sf "$EXIST_GH/ghidraRun" /usr/local/bin/ghidra
  ln -sf "$EXIST_GH/support/analyzeHeadless" /usr/local/bin/ghidraHeadless
  chmod a+rx /usr/local/bin/ghidra /usr/local/bin/ghidraHeadless
fi

# 5) Verification (as root, just to confirm presence)
echo "→ Verifying installations"
command -v joern >/dev/null && echo "  • joern → $(command -v joern)" || { echo "✗ joern missing" >&2; exit 1; }
command -v ghidra >/dev/null && echo "  • ghidra → $(command -v ghidra)" || { echo "✗ ghidra missing" >&2; exit 1; }
command -v ghidraHeadless >/dev/null && echo "  • ghidraHeadless → $(command -v ghidraHeadless)" || { echo "✗ ghidraHeadless missing" >&2; exit 1; }

# 6) Optional: normalize ownership of your working tree so non-root user can write
# Adjust this path to your repo root if different
WORKDIR_BASE="/home/${TARGET_USER}/C-AST-Generator"
if [[ -d "$WORKDIR_BASE" ]]; then
  echo "→ Normalizing ownership of $WORKDIR_BASE to ${TARGET_USER}"
  chown -R "${TARGET_USER}:${TARGET_USER}" "$WORKDIR_BASE"
fi

# 7) Smoke tests under the target (non-root) user
echo "→ Running smoke tests as ${TARGET_USER}"
sudo -u "$TARGET_USER" bash -lc 'java -version >/dev/null 2>&1 || exit 3'
sudo -u "$TARGET_USER" bash -lc 'ghidraHeadless -version >/dev/null 2>&1 || exit 4'
sudo -u "$TARGET_USER" bash -lc 'ghidra -help >/dev/null 2>&1 || exit 5'

echo -e "\n🎉 All set! You can now run 'joern', 'ghidra', and 'ghidraHeadless' from any shell."