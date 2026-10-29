"""`gamepad plugin list | install <zip> [--yes] | remove <id> [--yes]`.

Un paquete de plugin es un zip con UNA carpeta <id>/ que contiene plugin.json (ver
server/plugins.py). Al instalar se valida antes de escribir nada: rutas dentro de
la carpeta, sin enlaces simbólicos, tamaño acotado y API compatible. Se instala en
~/.local/share/gamepad/plugins/<id>/ de forma atómica (renombrando), sustituyendo
la versión anterior. Solo biblioteca estándar.
"""
import json
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

from . import paths
from .plugins import API_VERSION, check_manifest, read_manifest

MAX_FILES = 500
MAX_BYTES = 20 * 1024 * 1024
ROOT = Path(__file__).resolve().parent.parent


class PackageError(Exception):
    pass


def inspect(zip_path):
    """(manifiesto, [ZipInfo de archivos]) o PackageError. No escribe nada."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as ex:
        raise PackageError(f'no es un zip válido: {ex}') from None
    with zf:
        infos = zf.infolist()
        if not infos or len(infos) > MAX_FILES:
            raise PackageError(f'el zip debe tener entre 1 y {MAX_FILES} entradas')
        if sum(i.file_size for i in infos) > MAX_BYTES:
            raise PackageError(f'el contenido supera {MAX_BYTES // 1024 // 1024} MB')
        tops, files = set(), []
        for info in infos:
            name = info.filename
            parts = PurePosixPath(name).parts
            if (name.startswith('/') or '\\' in name or ':' in name or not parts
                    or any(p in ('..', '.') for p in parts)):
                raise PackageError(f'ruta no permitida en el zip: {name!r}')
            if stat.S_ISLNK(info.external_attr >> 16):
                raise PackageError(f'enlace simbólico no permitido: {name!r}')
            tops.add(parts[0])
            if not info.is_dir():
                if len(parts) < 2:
                    raise PackageError(f'archivo fuera de la carpeta del plugin: {name!r}')
                files.append(info)
        if len(tops) != 1:
            raise PackageError(f'el zip debe tener una sola carpeta raíz (tiene: {", ".join(sorted(tops))})')
        top = tops.pop()
        names = {i.filename for i in files}
        try:
            data = json.loads(zf.read(f'{top}/plugin.json'))
        except KeyError:
            raise PackageError(f'falta {top}/plugin.json') from None
        except ValueError as ex:
            raise PackageError(f'plugin.json ilegible: {ex}') from None
        try:
            manifest = check_manifest(data, top, lambda entry: f'{top}/{entry}' in names)
        except ValueError as ex:
            raise PackageError(str(ex)) from None
        return manifest, files


def install(zip_path, yes=False, dest=None, out=print, ask=input):
    manifest, files = inspect(zip_path)
    dest = Path(dest or paths.plugins_dir())
    pid, target = manifest['id'], dest / manifest['id']
    current = None
    if target.is_dir():
        try:
            current = read_manifest(target)['version']
        except ValueError:
            current = '?'
    out(f"Plugin: {manifest['name']} ({pid}) {manifest['version']}"
        + (f'  [sustituye a {current}]' if current else ''))
    if manifest.get('description'):
        out(f"  {manifest['description']}")
    out(f'  Se instalará en {target} ({len(files)} archivos).')
    out('  AVISO: un plugin es código Python que puede leer la memoria del juego con tu usuario.')
    if not yes and ask('¿Instalar? [s/N] ').strip().lower() not in ('s', 'si', 'sí', 'y', 'yes'):
        out('Cancelado.')
        return False
    tmp, old = dest / f'.tmp-{pid}', dest / f'.old-{pid}'
    for p in (tmp, old):
        shutil.rmtree(p, ignore_errors=True)
    tmp.mkdir(mode=0o700, parents=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in files:
            rel = PurePosixPath(info.filename).relative_to(pid)
            path = tmp.joinpath(*rel.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(path, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            path.chmod(0o644)
    if target.exists():
        target.rename(old)
    tmp.rename(target)
    shutil.rmtree(old, ignore_errors=True)
    out(f'Instalado {pid} {manifest["version"]}. Se usará la próxima vez que lances el juego.')
    return True


def installed(dest=None):
    """[(id, versión, carpeta, origen)] de los plugins de paquete (incluidos e instalados)."""
    rows = []
    for origin, base in (('incluido', ROOT / 'plugins'), ('instalado', Path(dest or paths.plugins_dir()))):
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if path.is_dir() and not path.name.startswith(('_', '.')) and path.name != '__pycache__':
                try:
                    m = read_manifest(path)
                    rows.append((m['id'], m['version'], path, origin))
                except ValueError as ex:
                    rows.append((path.name, f'inválido: {ex}', path, origin))
    return rows


def remove(pid, yes=False, dest=None, out=print, ask=input):
    target = Path(dest or paths.plugins_dir()) / pid
    if not target.is_dir() or pid.startswith(('.', '_')) or '/' in pid:
        out(f'No hay ningún plugin instalado con id {pid!r}.')
        return False
    if not yes and ask(f'¿Desinstalar {pid} de {target}? [s/N] ').strip().lower() not in ('s', 'si', 'sí', 'y', 'yes'):
        out('Cancelado.')
        return False
    shutil.rmtree(target)
    out(f'Desinstalado {pid}. Los retratos de ~/.local/share/gamepad/portraits/{pid}/ no se tocan.')
    return True


def main(argv):
    """argv: ['plugin', subcomando, ...]."""
    args = argv[1:]
    yes = '--yes' in args or '-y' in args
    args = [a for a in args if a not in ('--yes', '-y')]
    try:
        if args[:1] == ['list'] or not args:
            rows = installed()
            if not rows:
                print('No hay plugins de paquete.')
            for pid, version, path, origin in rows:
                print(f'{pid:16s} {version:12s} {origin:9s} {path}')
            print(f'(API de plugins de este hub: {API_VERSION})')
            return 0
        if args[0] == 'install' and len(args) == 2:
            return 0 if install(args[1], yes) else 1
        if args[0] == 'remove' and len(args) == 2:
            return 0 if remove(args[1], yes) else 1
    except PackageError as ex:
        print(f'Paquete no válido: {ex}', file=sys.stderr)
        return 1
    print('Uso: gamepad plugin list | install <zip> [--yes] | remove <id> [--yes]', file=sys.stderr)
    return 2
