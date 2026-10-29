"""Rutas compartidas entre el servicio y el lanzador (siempre del usuario, nunca de root)."""
import os
from pathlib import Path


def runtime_dir():
    """$XDG_RUNTIME_DIR/ps5gamepad: en RAM (tmpfs), privado (0700), se borra al cerrar sesión."""
    base = os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'
    path = Path(base) / 'ps5gamepad'
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def socket_path():
    return runtime_dir() / 'hub.sock'


def cache_dir():
    """~/.cache/ps5gamepad: dentro de la carpeta personal, que el contenedor de Steam
    (pressure-vessel) comparte con el juego. /run/user/... no siempre es visible ahí."""
    base = os.environ.get('XDG_CACHE_HOME') or str(Path.home() / '.cache')
    path = Path(base) / 'ps5gamepad'
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def mangohud_dir():
    path = cache_dir() / 'mangologs'
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def state_dir():
    base = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local' / 'state')
    path = Path(base) / 'ps5gamepad'
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path
