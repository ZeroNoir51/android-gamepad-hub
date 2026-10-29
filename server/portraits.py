"""Retratos por plugin: imágenes que pone el usuario, nunca arte incluido en el proyecto.

Carpeta: ~/.local/share/ps5gamepad/portraits/<plugin>/  (fuera de la carpeta del
proyecto, así no se pierden al descomprimir otra versión). Cada plugin decide qué
nombres acepta por personaje (p. ej. 1001.png o rain.png).

El lanzador solo comprueba si existe el archivo y manda la URL; el servicio lo sirve
tras validar nombre y ruta. Sin SVG: puede llevar scripts.
"""
import re
import time
from pathlib import Path

from . import paths

EXTENSIONS = ('png', 'jpg', 'jpeg', 'webp')
PLUGIN_RE = re.compile(r'^[a-z0-9_]+$')
NAME_RE = re.compile(r'^[A-Za-z0-9_-]+\.(png|jpg|jpeg|webp)$')
CONTENT_TYPES = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}
RECHECK_EVERY = 10.0   # s; recoge imágenes nuevas sin reiniciar el juego


def resolve(plugin, name, base=None):
    """Ruta segura a un retrato existente, o None."""
    if not PLUGIN_RE.match(plugin or '') or not NAME_RE.match(name or ''):
        return None
    root = Path(base or paths.portraits_dir()).resolve()
    path = (root / plugin / name).resolve()
    if not path.is_relative_to(root / plugin) or not path.is_file():
        return None
    return path


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
