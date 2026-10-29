"""`gamepad run %command%`: lanza el juego como hijo y lee su memoria sin root.

- Activa los logs de MangoHud en una carpeta en RAM y los borra al salir.
- Ejecuta los plugins solo sobre sus propios descendientes (ptrace_scope=1 lo permite).
- Envía los datos al servicio por un socket Unix privado; no abre puertos.
- Si algo de esto falla, el juego se lanza igual.
"""
import asyncio
import json
import os
import signal
import sys
import time
import traceback
from pathlib import Path

from . import paths
from .plugins import PluginManager, load_plugins

ROOT = Path(__file__).resolve().parent.parent
LOG_KEYS = {'output_folder', 'autostart_log', 'log_interval', 'log_duration', 'no_display'}


def mangohud_env(env, log_dir):
    """Añade el logging a la configuración de MangoHud que ya usa el jugador."""
    options = {'output_folder': str(log_dir), 'autostart_log': '1', 'log_interval': '0', 'log_duration': '0'}
    if env.get('MANGOHUD_CONFIG'):                       # configuración en línea del jugador
        kept = [o for o in env['MANGOHUD_CONFIG'].split(',') if o.split('=', 1)[0].strip() not in LOG_KEYS]
        env['MANGOHUD_CONFIG'] = ','.join(kept + [f'{k}={v}' for k, v in options.items()])
        return 'MANGOHUD_CONFIG'
    source = Path(env.get('MANGOHUD_CONFIGFILE') or Path.home() / '.config/MangoHud/MangoHud.conf')
    lines = []
    if source.is_file():
        for line in source.read_text(errors='replace').splitlines():
            if line.split('=', 1)[0].strip() not in LOG_KEYS:
                lines.append(line)
    lines += ['', '# añadido por gamepad'] + [f'{k}={v}' for k, v in options.items()]
    target = paths.cache_dir() / 'mangohud.conf'
    target.write_text('\n'.join(lines) + '\n')
    env['MANGOHUD_CONFIGFILE'] = str(target)
    return f'MANGOHUD_CONFIGFILE ({source if source.is_file() else "sin config previa"})'


def clean_logs(log_dir, since):
    for f in log_dir.glob('*.csv'):
        try:
            st = f.stat()
            if st.st_mtime >= since or time.time() - st.st_mtime > 86400:
                f.unlink()
        except OSError:
            pass


class Bridge:
    """Cliente del socket del servicio; reconecta solo y nunca bloquea al juego."""

    def __init__(self, path):
        self.path = path
        self.writer = None
        self.last_meta = None
        self._next_try = 0.0

    async def send(self, msg):
        if msg.get('t') == 'game':
            self.last_meta = msg
        if self.writer is None and time.monotonic() >= self._next_try:
            try:
                _, self.writer = await asyncio.open_unix_connection(str(self.path))
                print('[bridge] conectado al servicio', flush=True)
                if self.last_meta and msg is not self.last_meta:
                    await self._write(self.last_meta)
            except OSError:
                self._next_try = time.monotonic() + 3
                return
        if self.writer is not None:
            await self._write(msg)

    async def _write(self, msg):
        try:
            self.writer.write(json.dumps(msg, separators=(',', ':')).encode() + b'\n')
            await self.writer.drain()
        except (OSError, ConnectionError):
            self.writer = None
            self._next_try = time.monotonic() + 3

    async def close(self):
        if self.writer is not None:
            self.writer.close()


async def run(cmd):
    started = time.time()
    env = dict(os.environ)
    log_dir = None
    try:
        log_dir = paths.mangohud_dir()
        print(f'[mangohud] logging vía {mangohud_env(env, log_dir)} en {log_dir}', flush=True)
    except Exception:
        print(f'[mangohud] no se pudo preparar el logging:\n{traceback.format_exc()}', flush=True)

    child = await asyncio.create_subprocess_exec(*cmd, env=env)
    print(f'[run] juego lanzado, PID {child.pid}: {" ".join(cmd)}', flush=True)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        loop.add_signal_handler(sig, lambda s=sig: child.returncode is None and child.send_signal(s))

    bridge = Bridge(paths.socket_path())
    plugins = None
    try:
        plugins = PluginManager(load_plugins([ROOT / 'plugins', paths.plugins_dir()]), root_pid=os.getpid())
    except Exception:
        print(f'[plugins] desactivados:\n{traceback.format_exc()}', flush=True)

    async def plugin_loop():
        while True:
            try:
                for msg in await plugins.tick():
                    await bridge.send(msg)
            except Exception:
                print(f'[plugins] error:\n{traceback.format_exc()}', flush=True)
            await asyncio.sleep(plugins.period)

    task = asyncio.create_task(plugin_loop()) if plugins and plugins.plugins else None
    code = await child.wait()
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    if plugins:
        plugins.close()
    await bridge.send({'t': 'game', 'state': 'none', 'plugins': []})
    await bridge.close()
    if log_dir:
        clean_logs(log_dir, started)
    print(f'[run] el juego terminó con código {code}', flush=True)
    return code if code >= 0 else 128 - code


def main(argv):
    if argv and argv[0] == '--':
        argv = argv[1:]
    if not argv:
        print('Uso: gamepad run %command%', file=sys.stderr)
        return 2
    # Nuestros mensajes van a un log; la salida estándar original queda para el juego.
    try:
        log = open(paths.runtime_dir() / 'launcher.log', 'w', buffering=1)
        sys.stdout = sys.stderr = log
    except OSError:
        pass
    return asyncio.run(run(argv))
