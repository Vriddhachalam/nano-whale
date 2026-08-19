#!/bin/sh
set -e

OS=$(uname -s)

case "$OS" in
    Linux*) P="Linux" ;;
    Darwin*) P="macOS" ;;
    *) echo "Unsupported OS"; exit 1 ;;
esac

U="https://github.com/Karthikeyan-070204/nano-whale/releases/latest/download/nano-whale-$P.tar.gz"
D="$HOME/.nano-whale"
T="/tmp/nw.tar.gz"

echo "Downloading Nano Whale for $P..."
command -v curl >/dev/null && curl -fsSL "$U" -o "$T" || wget -q "$U" -O "$T"

[ -d "$D" ] && rm -rf "$D"
mkdir -p "$D"

echo "Extracting..."
tar -xzf "$T" -C "$D"

chmod +x "$D/nano-whale"

rm -f "$T"

echo "Adding to PATH..."
# Link correct binary
if [ -w "/usr/local/bin" ]; then
    ln -sf "$D/nano-whale" /usr/local/bin/nano-whale
else
    sudo ln -sf "$D/nano-whale" /usr/local/bin/nano-whale \
    || echo "Add to PATH: export PATH=\"\$HOME/.nano-whale:\$PATH\""
fi

echo "----------------------------------------"
echo "Nano Whale installed successfully!"
echo "Run it anywhere using the command: nano-whale"
echo "----------------------------------------"
