"""Rutas compartidas entre el servicio y el lanzador (siempre del usuario, nunca de root)."""
import os
from pathlib import Path


def in_flatpak():
    """El lanzador corre dentro del sandbox de un Flatpak (p. ej. Heroic)."""
    return os.path.exists('/.flatpak-info')


def _xdg(name, default):
    """Carpeta XDG del usuario. Dentro de Flatpak, XDG_* apunta a ~/.var/app/<app>/...;
    usamos las del sistema (HOST_XDG_*) para compartir datos con el servicio."""
    if in_flatpak():
        return os.environ.get('HOST_' + name) or str(Path.home() / default)
    return os.environ.get(name) or str(Path.home() / default)


def runtime_dir():
    """$XDG_RUNTIME_DIR/gamepad: en RAM (tmpfs), privado (0700), se borra al cerrar sesión."""
    base = os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'
    path = Path(base) / 'gamepad'
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def socket_path():
    """Socket que usa el lanzador. En Flatpak /run/user es privado del sandbox: se usa el
    de ~/.cache/gamepad (el servicio escucha en los dos, ver socket_paths)."""
    return cache_dir() / 'hub.sock' if in_flatpak() else runtime_dir() / 'hub.sock'


def socket_paths():
    """Sockets donde escucha el servicio."""
    return [runtime_dir() / 'hub.sock', cache_dir() / 'hub.sock']


def log_dir():
    """Dónde deja el lanzador launcher.log (visible desde fuera del sandbox en Flatpak)."""
    return cache_dir() if in_flatpak() else runtime_dir()


def cache_dir():
    """~/.cache/gamepad: dentro de la carpeta personal, que el contenedor de Steam
    (pressure-vessel) comparte con el juego. /run/user/... no siempre es visible ahí."""
    path = Path(_xdg('XDG_CACHE_HOME', '.cache')) / 'gamepad'
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)   # aloja también un socket del servicio
    return path


def mangohud_dir():
    path = cache_dir() / 'mangologs'
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def state_dir():
    path = Path(_xdg('XDG_STATE_HOME', '.local/state')) / 'gamepad'
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def data_dir():
    """~/.local/share/gamepad: datos del usuario que sobreviven a cambiar de versión."""
    path = Path(_xdg('XDG_DATA_HOME', '.local/share')) / 'gamepad'
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def portraits_dir():
    path = data_dir() / 'portraits'
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def backgrounds_dir():
    path = data_dir() / 'backgrounds'
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def code_file():
    return state_dir() / 'code'


def sessions_file():
    return state_dir() / 'sessions.json'


def plugins_dir():
    """Plugins instalados con `gamepad plugin install` (fuera del proyecto)."""
    path = data_dir() / 'plugins'
    path.mkdir(mode=0o700, exist_ok=True)
    return path
