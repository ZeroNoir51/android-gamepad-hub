"""Estado del servicio para el usuario: `gamepad code`, `gamepad status` y la notificación al arrancar.

Solo biblioteca estándar (lo usa también el plugin de Decky, que no tiene el venv).
"""
import json
import shutil
import socket
import subprocess
import urllib.request

from . import VERSION, auth, paths

PORT = 8080


def lan_ip():
    """IP de la interfaz que sale a la red local (no envía nada: UDP sin datos)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.0.2.1', 9))   # TEST-NET-1: solo elige la ruta
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def url(port=PORT):
    ip = lan_ip()
    return f'http://{ip}:{port}' if ip else f'http://<IP-LAN>:{port}'


def service_up(port=PORT, timeout=1.5):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/session', timeout=timeout) as r:
            return r.status == 200
    except OSError:
        return False


def snapshot(port=PORT):
    return {'up': service_up(port), 'version': VERSION, 'url': url(port),
            'code': auth.load_or_create_code(paths.code_file())}


def notify(title, body):
    """Notificación de escritorio, si hay sesión gráfica. Nunca falla ni bloquea."""
    if shutil.which('notify-send'):
        cmd = ['notify-send', '--app-name=GamePad', '--icon=input-gaming', title, body]
    elif shutil.which('gdbus'):
        cmd = ['gdbus', 'call', '--session', '--dest', 'org.freedesktop.Notifications',
               '--object-path', '/org/freedesktop/Notifications',
               '--method', 'org.freedesktop.Notifications.Notify',
               'GamePad', '0', 'input-gaming', title, body, '[]', '{}', '8000']
    else:
        return False
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


def main(argv):
    """`gamepad code [--new]` y `gamepad status [--json]`."""
    cmd, opts = argv[0], argv[1:]
    if cmd == 'code':
        if '--new' in opts:
            code = auth.new_code(paths.code_file())
            paths.sessions_file().unlink(missing_ok=True)   # un código nuevo cierra las sesiones abiertas
            print(f'Código nuevo: {code}. Se cerraron las sesiones; reinicia: systemctl --user restart gamepad')
        else:
            print(auth.load_or_create_code(paths.code_file()))
        return 0
    info = snapshot()
    if '--json' in opts:
        print(json.dumps(info))
    else:
        print(f"GamePad {info['version']}: {'activo' if info['up'] else 'NO responde en el puerto 8080'}")
        print(f"Android: {info['url']}   código: {info['code']}")
    return 0 if info['up'] else 1
