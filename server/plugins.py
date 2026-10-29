"""Plugins por juego: detectan el proceso y leen sus valores de memoria.

Los ejecuta el lanzador (`gamepad run`), que es el proceso padre del juego:
por eso el kernel le permite leer su memoria sin root.

Un plugin es un archivo plugins/<algo>.py que define `class Plugin(GamePlugin)`.
Los archivos que empiezan por "_" se ignoran (plantillas).

AVISO: un plugin es código Python que se ejecuta con los permisos del servidor
(hoy, root). Instala solo plugins que hayas escrito o revisado.
"""
import asyncio
import importlib.util
import time
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path

from .memory import MemoryReadError, ProcessGone, descendants, open_process


@dataclass
class Field:
    key: str
    label: str
    kind: str = 'number'      # 'number' | 'bar' | 'text' | 'image' (URL /portraits/<plugin>/<archivo>)
    max_key: str = None       # para 'bar': clave del valor máximo
    tone: str = 'neutral'     # 'hp' | 'mp' | 'gold' | 'xp' | 'neutral' (color en el cliente)
    section: str = 'stats'    # dónde se muestra: 'party' | 'stats' | 'info'
    slot: int = 0             # en 'party': número de miembro (1-4)


class GamePlugin:
    id = ''
    name = ''
    process_names = ()        # coincide con comm o con el basename de argv[0], sin mayúsculas
    cmdline_contains = None   # alternativa: subcadena de la línea de comandos
    ptr_size = 8              # 4 para juegos de 32 bits
    poll_hz = 4
    fields = []

    def matches(self, proc):
        names = {n.lower() for n in self.process_names}
        if names and (proc.comm.lower() in names or proc.exe_name.lower() in names):
            return True
        return bool(self.cmdline_contains) and self.cmdline_contains in proc.cmdline

    def on_attach(self, mem, proc):
        """Opcional: resolver direcciones base una sola vez."""

    def read(self, mem):
        """Devuelve {clave: valor} con las claves declaradas en fields."""
        raise NotImplementedError


def load_plugins(folder):
    plugins = []
    for path in sorted(Path(folder).glob('*.py')):
        if path.name.startswith('_'):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f'hub_plugin_{path.stem}', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            plugin = module.Plugin()
            if not isinstance(plugin, GamePlugin) or not plugin.id:
                raise TypeError('Plugin debe heredar de GamePlugin y definir id')
            plugins.append(plugin)
            print(f'[plugins] cargado {plugin.id} ({path.name})', flush=True)
        except Exception:
            print(f'[plugins] error cargando {path.name}:\n{traceback.format_exc()}', flush=True)
    return plugins


class PluginManager:
    SCAN_EVERY = 2.0
    ERROR_EVERY = 2.0
    RETRY_LOG_EVERY = 30.0   # s; un enganche que aún no puede leer se reintenta en silencio

    def __init__(self, plugins, root_pid):
        self.plugins = plugins
        self.root_pid = root_pid   # solo se buscan juegos entre los descendientes de este PID
        self.active = None     # (plugin, mem, proc)
        self._next_scan = 0.0
        self._last_error_sent = 0.0
        self._failed = set()   # (plugin_id, pid) que fallaron de forma definitiva: no reintentar
        self._retrying = {}    # (plugin_id, pid) -> próximo log; el juego aún arranca
        self._logged_errors = set()

    @property
    def period(self):
        return 1.0 / (self.active[0].poll_hz if self.active else 4)

    def meta(self):
        if not self.active:
            return {'t': 'game', 'state': 'none', 'plugins': [p.name for p in self.plugins]}
        plugin, _, proc = self.active
        return {'t': 'game', 'state': 'attached', 'id': plugin.id, 'name': plugin.name,
                'pid': proc.pid, 'fields': [asdict(f) for f in plugin.fields]}

    def _scan(self):
        for proc in descendants(self.root_pid):
            for plugin in self.plugins:
                if (plugin.id, proc.pid) in self._failed or not plugin.matches(proc):
                    continue
                key, mem = (plugin.id, proc.pid), None
                try:
                    mem = open_process(proc.pid, plugin.ptr_size)
                    plugin.on_attach(mem, proc)
                    if self._retrying.pop(key, None) is not None:
                        print(f'[plugins] {plugin.id}: el PID {proc.pid} ya se puede leer', flush=True)
                    return plugin, mem, proc
                except ProcessGone:
                    pass
                except MemoryReadError as ex:
                    # Normal al arrancar: el juego aún no inicializó sus estructuras (punteros nulos).
                    now = time.monotonic()
                    if now >= self._retrying.get(key, 0.0):
                        self._retrying[key] = now + self.RETRY_LOG_EVERY
                        print(f'[plugins] {plugin.id}: el PID {proc.pid} aún no se puede leer ({ex}); '
                              f'reintentando cada {self.SCAN_EVERY:.0f} s', flush=True)
                except Exception as ex:
                    self._failed.add(key)
                    print(f'[plugins] {plugin.id}: no se pudo enganchar al PID {proc.pid}: {ex}', flush=True)
                if mem is not None:
                    mem.close()
        return None

    def _detach(self):
        if self.active:
            self.active[1].close()
            print(f'[plugins] {self.active[0].id}: proceso terminado', flush=True)
        self.active = None

    async def tick(self):
        """Devuelve la lista de mensajes que hay que enviar al cliente."""
        now = time.monotonic()
        if not self.active:
            if not self.plugins or now < self._next_scan:
                return []
            self._next_scan = now + self.SCAN_EVERY
            self.active = await asyncio.to_thread(self._scan)
            if self.active:
                print(f'[plugins] {self.active[0].id}: enganchado al PID {self.active[2].pid}', flush=True)
                return [self.meta()]
            return []
        plugin, mem, _ = self.active
        try:
            values = await asyncio.to_thread(plugin.read, mem)   # lecturas largas no bloquean
            return [{'t': 'gv', 'v': values}]
        except ProcessGone:
            self._detach()
            return [self.meta()]
        except Exception as ex:   # MemoryReadError o fallo del plugin: no tumbar el servidor
            if not mem.alive():
                self._detach()
                return [self.meta()]
            if now - self._last_error_sent < self.ERROR_EVERY:
                return []
            self._last_error_sent = now
            # Cada error distinto se escribe una vez con su traza: dice en qué lectura falló
            where = traceback.extract_tb(ex.__traceback__)[-3:]
            key = (type(ex).__name__, str(ex), tuple((f.name, f.lineno) for f in where))
            if key not in self._logged_errors:
                self._logged_errors.add(key)
                print(f'[plugins] {plugin.id}: {traceback.format_exc()}', flush=True)
            return [{'t': 'gv', 'err': str(ex)}]

    def close(self):
        self._detach()
