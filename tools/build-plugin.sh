#!/bin/sh
# Empaqueta plugins/<id>/ como gamepad-plugin-<id>-<versión>.zip (carpeta <id>/) y lo valida.
# Uso: sh tools/build-plugin.sh ffrs [carpeta_de_salida]
set -eu
DIR="$(cd "$(dirname "$0")/.." && pwd)"
ID="${1:?Uso: build-plugin.sh <id> [salida]}"
OUT="$(cd "${2:-$DIR}" && pwd)"
cd "$DIR"
PYTHONPATH="$DIR" python3 - "$ID" "$OUT" <<'PY'
import sys, zipfile
from pathlib import Path
from server.plugins import read_manifest
from server.plugin_pkg import inspect
pid, out = sys.argv[1], Path(sys.argv[2])
src = Path('plugins') / pid
m = read_manifest(src)
target = out / f"gamepad-plugin-{pid}-{m['version']}.zip"
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(src.rglob('*')):
        if '__pycache__' in path.parts or path.suffix == '.pyc' or not path.is_file():
            continue
        zf.write(path, Path(pid) / path.relative_to(src))
inspect(target)   # el mismo control que hará `gamepad plugin install`
print(f'Creado {target}')
PY
