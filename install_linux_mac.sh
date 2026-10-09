#!/bin/sh
set -e

REPO="Vriddhachalam/nano-whale"
BIN_NAME="nano-whale"

# Determine OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     OS_STR="linux" ;;
    Darwin*)    OS_STR="macos" ;;
    *)          echo "Unsupported OS: ${OS}"; exit 1 ;;
esac

# Determine Architecture
ARCH="$(uname -m)"
case "${ARCH}" in
    x86_64*|amd64*) ARCH_STR="x86_64" ;;
    aarch64*|arm64*) ARCH_STR="arm64" ;;
    *)              echo "Unsupported architecture: ${ARCH}"; exit 1 ;;
esac

ASSET_NAME="${BIN_NAME}-${OS_STR}-${ARCH_STR}"

echo "Fetching latest release for ${ASSET_NAME}..."
LATEST_URL=$(curl -s "https://api.github.com/repos/${REPO}/releases/latest" | grep -Eo "\"browser_download_url\": \"[^\"]*${ASSET_NAME}\"" | cut -d '"' -f 4 | head -n 1)

if [ -z "$LATEST_URL" ]; then
    echo "Could not find a release asset for your platform (${ASSET_NAME})."
    echo "Make sure a release exists in the repository."
    exit 1
fi

echo "Downloading ${LATEST_URL}..."

# Download to a temporary location
TMP_DIR=$(mktemp -d)
TMP_BIN="${TMP_DIR}/${BIN_NAME}"

curl -fsSL "$LATEST_URL" -o "$TMP_BIN"
chmod +x "$TMP_BIN"

# Determine install location
INSTALL_DIR="/usr/local/bin"
if [ ! -w "$INSTALL_DIR" ]; then
    INSTALL_DIR="$HOME/.local/bin"
    mkdir -p "$INSTALL_DIR"
fi

echo "Installing to ${INSTALL_DIR}/${BIN_NAME}..."
mv "$TMP_BIN" "${INSTALL_DIR}/${BIN_NAME}"
rm -rf "$TMP_DIR"

echo "Installation complete! Run '${BIN_NAME}' to start."
if [ "$INSTALL_DIR" = "$HOME/.local/bin" ]; then
    echo "Make sure ${INSTALL_DIR} is in your PATH."
fi
