#!/bin/sh
# Compila el plugin de Decky y crea gamepad-decky-<versión>.zip (carpeta GamePad/) en la carpeta indicada.
set -eu
DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$DIR}"
cd "$DIR/decky"
npm install --no-audit --no-fund
npm run build
rm -f dist/*.map
VERSION="$(sed -n 's/^VERSION = .\(.*\).$/\1/p' "$DIR/server/__init__.py")"
TMP="$(mktemp -d)"
mkdir "$TMP/GamePad"
cp -r plugin.json package.json main.py dist "$TMP/GamePad/"
(cd "$TMP" && rm -f "$OUT/gamepad-decky-$VERSION.zip" && python3 -m zipfile -c "$OUT/gamepad-decky-$VERSION.zip" GamePad)
rm -rf "$TMP"
echo "Creado $OUT/gamepad-decky-$VERSION.zip"
