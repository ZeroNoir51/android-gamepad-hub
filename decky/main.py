"""Backend del plugin de Decky "GamePad".

Corre con el usuario (plugin.json sin la marca "root"). Solo lee el código de acceso
del archivo del usuario y pregunta al servicio en 127.0.0.1 si responde. No abre
puertos ni expone el código por la red. Sin dependencias: Decky trae su propio Python.
"""
import os
import socket
import urllib.request
from pathlib import Path

try:
    import decky   # lo inyecta Decky Loader
    HOME = Path(decky.DECKY_USER_HOME)
except Exception:   # fuera de Decky (pruebas)
    decky = None
    HOME = Path(os.environ.get('DECKY_USER_HOME') or Path.home())

PORT = 8080
CODE_FILE = HOME / '.local' / 'state' / 'gamepad' / 'code'


def _lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.0.2.1', 9))   # no envía nada: solo elige la interfaz de salida
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _up():
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/session', timeout=1.5) as r:
            return r.status == 200
    except OSError:
        return False


def _code():
    try:
        code = CODE_FILE.read_text().strip().upper()
        return code if len(code) == 4 and code.isalpha() else None
    except OSError:
        return None


class Plugin:
    async def status(self):
        ip = _lan_ip()
        return {'up': _up(), 'url': f'http://{ip}:{PORT}' if ip else None, 'code': _code()}

    async def _main(self):
        if decky:
            decky.logger.info(f'GamePad: leyendo el código de {CODE_FILE}')

    async def _unload(self):
        pass
