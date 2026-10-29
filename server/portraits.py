"""Imágenes por plugin que pone el usuario (nunca arte incluido en el proyecto).

  ~/.local/share/gamepad/portraits/<plugin>/     retratos; cada plugin decide qué nombres
                                                  acepta por personaje (p. ej. 1001.png o rain.png)
  ~/.local/share/gamepad/backgrounds/<plugin>/   fondos del panel del juego; el cliente elige
                                                  cuál usar (GET /api/media/<plugin> los lista)

Fuera de la carpeta del proyecto, así no se pierden al actualizar.

Un plugin también puede traer sus imágenes en <plugin>/portraits/ y <plugin>/backgrounds/
(las mete `tools/build-plugin.sh <id> --media`). Se busca primero en la carpeta del
usuario (que así puede sustituir una) y luego en la del plugin instalado o incluido.

El lanzador solo comprueba si existe el archivo y manda la URL; el servicio lo sirve
tras validar nombre y ruta. Sin SVG: puede llevar scripts.
"""
import re
import time
from pathlib import Path

from . import paths

EXTENSIONS = ('png', 'jpg', 'jpeg', 'webp')
PLUGIN_RE = re.compile(r'^[a-z0-9_]+$')
NAME_RE = re.compile(r'^[A-Za-z0-9_-]+\.(?i:png|jpg|jpeg|webp)$')
MAX_BYTES = 15 * 1024 * 1024
KINDS = ('portraits', 'backgrounds')
CONTENT_TYPES = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}
RECHECK_EVERY = 10.0   # s; recoge imágenes nuevas sin reiniciar el juego


ROOT = Path(__file__).resolve().parent.parent


def folders(kind, plugin, base=None):
    """Carpetas donde buscar, por prioridad. Con base (pruebas), solo base/<plugin>."""
    if base:
        return [Path(base) / plugin]
    user = paths.portraits_dir() if kind == 'portraits' else paths.backgrounds_dir()
    return [user / plugin, paths.plugins_dir() / plugin / kind, ROOT / 'plugins' / plugin / kind]


def _valid(plugin, name, kind):
    return kind in KINDS and PLUGIN_RE.match(plugin or '') and NAME_RE.match(name or '')


def _in(folder, name):
    try:
        root = folder.resolve()
        path = (root / name).resolve()
    except OSError:
        return None
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > MAX_BYTES:
        return None
    return path


def resolve(plugin, name, base=None, kind='portraits'):
    """Ruta segura a una imagen existente (y de tamaño razonable), o None."""
    if not _valid(plugin, name, kind):
        return None
    for folder in folders(kind, plugin, base):
        path = _in(folder, name)
        if path:
            return path
    return None


def listing(plugin, kind='backgrounds', base=None):
    """URLs de las imágenes válidas de un plugin (todas las carpetas, sin repetir), por nombre."""
    if kind not in KINDS or not PLUGIN_RE.match(plugin or ''):
        return []
    names = set()
    for folder in folders(kind, plugin, base):
        if folder.is_dir():
            names.update(p.name for p in folder.iterdir() if NAME_RE.match(p.name) and _in(folder, p.name))
    return [f'/{kind}/{plugin}/{n}' for n in sorted(names)]


def content_type(path):
    return CONTENT_TYPES[path.suffix[1:].lower()]


class Finder:
    """Busca el archivo de cada personaje con caché, para no tocar el disco en cada lectura."""

    def __init__(self, plugin_id, base=None):
        self.plugin_id = plugin_id
        self.base = base
        self._cache = {}   # clave -> (caduca, url o None)

    def url(self, key, aliases=()):
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
        found = None
        for stem in (str(key), *aliases):
            for ext in EXTENSIONS:
                name = f'{stem}.{ext}'
                if resolve(self.plugin_id, name, self.base):
                    found = f'/portraits/{self.plugin_id}/{name}'
                    break
            if found:
                break
        self._cache[key] = (now + RECHECK_EVERY, found)
        return found
