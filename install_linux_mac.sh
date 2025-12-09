#!/bin/sh
set -e

OS=$(uname -s)
ARCH=$(uname -m)

case "$OS" in
    Linux*) P="linux-x64" ;;
    Darwin*)
        if [ "$ARCH" = "arm64" ]; then
            P="macos-arm64"
        else
            P="macos-x64"
        fi
        ;;
    *) echo "Unsupported OS"; exit 1 ;;
esac

U="https://github.com/Vriddhachalam/nano-whale/releases/latest/download/nano-whale-$P.tar.gz"
D="$HOME/.nano-whale"
T="/tmp/nw.tar.gz"

command -v curl >/dev/null && curl -fsSL "$U" -o "$T" || wget -q "$U" -O "$T"

[ -d "$D" ] && rm -rf "$D"
mkdir -p "$D"

tar -xzf "$T" -C "$D"

chmod +x "$D/$P/nano-whale"

rm -f "$T"

# Link correct binary
if [ -w "/usr/local/bin" ]; then
    ln -sf "$D/$P/nano-whale" /usr/local/bin/nano-whale
else
    sudo ln -sf "$D/$P/nano-whale" /usr/local/bin/nano-whale \
    || echo "Add to PATH: export PATH=\"\$HOME/.nano-whale/$P:\$PATH\""
fi

echo "Installed. Run: nano-whale"
