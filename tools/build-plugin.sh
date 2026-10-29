#!/bin/sh
# Empaqueta plugins/<id>/ como gamepad-plugin-<id>-<versión>.zip (carpeta <id>/) y lo valida.
#
# Uso: sh tools/build-plugin.sh <id> [carpeta_de_salida] [--media]
#
# --media  mete también tus imágenes de ~/.local/share/gamepad/portraits/<id>/ y
#          ~/.local/share/gamepad/backgrounds/<id>/ (en <id>/portraits/ y <id>/backgrounds/
#          del zip). Son para tu uso: no subas al repositorio arte con copyright.
set -eu
DIR="$(cd "$(dirname "$0")/.." && pwd)"
MEDIA=0
ARGS=""
for a in "$@"; do
  if [ "$a" = "--media" ]; then MEDIA=1; else ARGS="$ARGS $a"; fi
done
set -- $ARGS
ID="${1:?Uso: build-plugin.sh <id> [salida] [--media]}"
OUT="$(cd "${2:-$DIR}" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/gamepad"
cd "$DIR"
PYTHONPATH="$DIR" python3 - "$ID" "$OUT" "$MEDIA" "$DATA" <<'PY'
import sys, zipfile
from pathlib import Path
from server.plugins import read_manifest
from server.plugin_pkg import inspect
from server.portraits import NAME_RE
pid, out, media, data = sys.argv[1], Path(sys.argv[2]), sys.argv[3] == '1', Path(sys.argv[4])
src = Path('plugins') / pid
m = read_manifest(src)
suffix = '-media' if media else ''
target = out / f"gamepad-plugin-{pid}-{m['version']}{suffix}.zip"
counts = {}
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zf:
    files = {}
    for path in sorted(src.rglob('*')):
        if '__pycache__' in path.parts or path.suffix == '.pyc' or not path.is_file():
            continue
        files[str(Path(pid) / path.relative_to(src))] = path
    if media:
        for kind in ('portraits', 'backgrounds'):
            folder = data / kind / pid
            if folder.is_dir():
                for img in sorted(folder.iterdir()):
                    if img.is_file() and not img.is_symlink() and NAME_RE.match(img.name):
                        files[f'{pid}/{kind}/{img.name}'] = img   # las del usuario mandan
    for name, path in sorted(files.items()):
        zf.write(path, name)
        kind = name.split('/')[1] if name.count('/') >= 2 else 'código'
        counts[kind] = counts.get(kind, 0) + 1
inspect(target)   # el mismo control que hará `gamepad plugin install`
print(f'Creado {target}')
print('  ' + ', '.join(f'{k}: {n}' for k, n in sorted(counts.items())))
PY
