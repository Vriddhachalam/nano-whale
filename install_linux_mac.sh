#!/bin/sh
set -e
OS=$(uname -s)
ARCH=$(uname -m)
case "$OS" in Linux*)P="linux-x64";;Darwin*)[ "$ARCH" = "arm64" ]&&P="macos-arm64"||P="macos-x64";;*)echo "Unsupported OS";exit 1;;esac
U="https://github.com/Vriddhachalam/nano-whale/releases/latest/download/nano-whale-$P.tar.gz"
D="$HOME/.nano-whale"
T="/tmp/nw.tar.gz"
command -v curl >/dev/null && curl -fsSL "$U" -o "$T" || wget -q "$U" -O "$T"
[ -d "$D" ]&&rm -rf "$D"
mkdir -p "$D"
tar -xzf "$T" -C "$D"
chmod +x "$D/nano-whale"
rm -f "$T"
[ -w "/usr/local/bin" ]&&ln -sf "$D/nano-whale" /usr/local/bin/nano-whale||sudo ln -sf "$D/nano-whale" /usr/local/bin/nano-whale||echo "Add to PATH: export PATH=\"\$HOME/.nano-whale:\$PATH\""
echo "Installed. Run: nano-whale"