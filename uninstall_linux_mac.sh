#!/bin/sh
set -e

BIN_NAME="nano-whale"

# Determine install location
INSTALL_DIR="/usr/local/bin"
if [ ! -w "$INSTALL_DIR" ]; then
    INSTALL_DIR="$HOME/.local/bin"
fi

if [ -f "${INSTALL_DIR}/${BIN_NAME}" ]; then
    echo "Removing ${INSTALL_DIR}/${BIN_NAME}..."
    rm "${INSTALL_DIR}/${BIN_NAME}"
    echo "nano-whale has been successfully uninstalled."
else
    echo "nano-whale is not installed in ${INSTALL_DIR}."
fi
