"""Plugins por juego: detectan el proceso y leen sus valores de memoria.

Los ejecuta el lanzador (`gamepad run`), que es el proceso padre del juego:
por eso el kernel le permite leer su memoria sin root.

Formato (API 1): una carpeta <id>/ con plugin.json y el archivo de entrada, que
define `class Plugin(GamePlugin)` e importa SOLO de server.plugin_api:

    {"id": "ffrs", "name": "...", "version": "1.0.0", "api": 1, "entry": "plugin.py"}

Se buscan, por orden, en la carpeta plugins/ del proyecto (incluidos) y en
~/.local/share/gamepad/plugins/ (instalados con `gamepad plugin install`); si un
id está en las dos, gana el instalado. Un archivo suelto plugins/<algo>.py
(formato antiguo) sigue funcionando. Lo que empieza por "_" o "." se ignora.

AVISO: un plugin es código Python con permiso para leer la memoria del juego, con
tu usuario. Instala solo plugins que hayas escrito o revisado.
"""
import asyncio
import importlib.util
import json
import re
import sys
import time
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path

API_VERSION = 2   # 2: los lectores de motor salieron del hub; cada plugin trae el suyo
ID_RE = re.compile(r'^[a-z0-9_]{1,32}$')
ENTRY_RE = re.compile(r'^[A-Za-z0-9_]+\.py$')
VERSION_RE = re.compile(r'^\d+(\.\d+){0,3}$')
KINDS = {'number', 'bar', 'text', 'image'}
SECTIONS = {'party', 'stats', 'info', 'header'}
TONES = {'hp', 'mp', 'limit', 'gold', 'xp', 'neutral'}

from .memory import MemoryReadError, ProcessGone, descendants, open_process


@dataclass
class Field:
    key: str
    label: str
    kind: str = 'number'      # 'number' | 'bar' | 'text' | 'image' (URL /portraits/<plugin>/<archivo>)
    max_key: str = None       # para 'bar': clave del valor máximo
    tone: str = 'neutral'     # 'hp' | 'mp' | 'limit' | 'gold' | 'xp' | 'neutral' (color en el cliente)
    section: str = 'stats'    # dónde se muestra: 'party' | 'stats' | 'info' (debug) | 'header'
    slot: int = 0             # en 'party': número de miembro (1-4)


class GamePlugin:
    id = ''
    name = ''
    version = ''              # lo pone el cargador desde plugin.json
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


def check_manifest(data, folder_name=None, entry_exists=None):
    """Valida un plugin.json ya leído. Devuelve el manifiesto normalizado o lanza ValueError."""
    if not isinstance(data, dict):
        raise ValueError('plugin.json debe ser un objeto')
    m = {'entry': 'plugin.py', **data}
    for key in ('id', 'name', 'version', 'api', 'entry'):
        if key not in m:
            raise ValueError(f'plugin.json: falta "{key}"')
    if not isinstance(m['id'], str) or not ID_RE.match(m['id']):
        raise ValueError(f'id inválido {m["id"]!r}: solo a-z, 0-9 y _ (máx. 32)')
    if folder_name is not None and folder_name != m['id']:
        raise ValueError(f'la carpeta {folder_name!r} no coincide con el id {m["id"]!r}')
    if m['api'] != API_VERSION:
        raise ValueError(f'el plugin es para la API {m["api"]!r}; este hub usa la API {API_VERSION}')
    if not isinstance(m['version'], str) or not VERSION_RE.match(m['version']):
        raise ValueError(f'versión inválida {m["version"]!r} (p. ej. "1.0.0")')
    if not isinstance(m['entry'], str) or not ENTRY_RE.match(m['entry']):
        raise ValueError(f'entry inválido {m["entry"]!r}')
    if entry_exists is not None and not entry_exists(m['entry']):
        raise ValueError(f'no existe el archivo de entrada {m["entry"]}')
    return m


def read_manifest(folder):
    folder = Path(folder)
    try:
        data = json.loads((folder / 'plugin.json').read_text())
    except (OSError, ValueError) as ex:
        raise ValueError(f'plugin.json ilegible: {ex}') from None
    return check_manifest(data, folder.name, lambda entry: (folder / entry).is_file())


def check_plugin(plugin):
    """Errores de declaración que el cliente no sabría mostrar."""
    if not isinstance(plugin, GamePlugin):
        raise TypeError('Plugin debe heredar de GamePlugin')
    if not ID_RE.match(plugin.id or ''):
        raise ValueError(f'id inválido {plugin.id!r}')
    seen = set()
    for f in plugin.fields:
        if f.key in seen:
            raise ValueError(f'campo repetido {f.key!r}')
        seen.add(f.key)
        if f.kind not in KINDS or f.section not in SECTIONS or f.tone not in TONES:
            raise ValueError(f'campo {f.key!r}: kind/section/tone desconocido ({f.kind}, {f.section}, {f.tone})')
        if f.section == 'party' and not 1 <= f.slot <= 4:
            raise ValueError(f'campo {f.key!r}: slot debe ser 1-4 en la sección party')


def import_module(module_name, path, package_dir=None):
    """Importa el código de un plugin. Con package_dir es un paquete: sus módulos propios
    se importan con import relativo (from .ue import ...)."""
    kwargs = {'submodule_search_locations': [str(package_dir)]} if package_dir else {}
    spec = importlib.util.spec_from_file_location(module_name, path, **kwargs)
    module = importlib.util.module_from_spec(spec)
    for name in [n for n in sys.modules if n == module_name or n.startswith(module_name + '.')]:
        del sys.modules[name]   # no mezclar con una copia anterior del mismo plugin
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[module_name]
        raise
    return module


def _import(module_name, path, package_dir=None):
    return import_module(module_name, path, package_dir).Plugin()


def load_plugins(folders):
    """Carga los plugins de una o varias carpetas (las últimas tienen prioridad)."""
    if isinstance(folders, (str, Path)):
        folders = [folders]
    packages, singles = {}, []
    for base in map(Path, folders):
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if path.name.startswith(('_', '.')) or path.name == '__pycache__':
                continue
            if path.is_dir():
                try:
                    manifest = read_manifest(path)
                except ValueError as ex:
                    print(f'[plugins] se ignora {path}: {ex}', flush=True)
                    continue
                if manifest['id'] in packages:
                    print(f'[plugins] {manifest["id"]}: se usa {path} en lugar de {packages[manifest["id"]][0]}',
                          flush=True)
                packages[manifest['id']] = (path, manifest)
            elif path.suffix == '.py':
                singles.append(path)
    plugins = []
    for path in singles:   # formato antiguo: solo se sabe el id tras importarlo
        try:
            plugin = _import(f'gamepad_plugin_file_{path.stem}', path)
            check_plugin(plugin)
            if plugin.id in packages:
                print(f'[plugins] {plugin.id}: se ignora {path.name}; hay un paquete con ese id', flush=True)
                continue
            plugins.append(plugin)
            print(f'[plugins] cargado {plugin.id} ({path.name})', flush=True)
        except Exception:
            print(f'[plugins] error cargando {path.name}:\n{traceback.format_exc()}', flush=True)
    for plugin_id, (path, manifest) in sorted(packages.items()):
        try:
            plugin = _import(f'gamepad_plugin_{plugin_id}', path / manifest['entry'], package_dir=path)
            check_plugin(plugin)
            if plugin.id != plugin_id:
                raise ValueError(f'Plugin.id {plugin.id!r} no coincide con plugin.json ({plugin_id!r})')
            plugin.version = manifest['version']
            plugins.append(plugin)
            print(f'[plugins] cargado {plugin_id} {manifest["version"]} ({path})', flush=True)
        except Exception:
            print(f'[plugins] error cargando {path}:\n{traceback.format_exc()}', flush=True)
    return plugins


class PluginManager:
    SCAN_EVERY = 2.0
    ERROR_EVERY = 2.0
    RETRY_LOG_EVERY = 30.0   # s; un enganche que aún no puede leer se reintenta en silencio
    READ_TIMEOUT = 5.0       # s; un read() más lento se avisa y no se lanza otro hasta que acabe

    def __init__(self, plugins, root_pid):
        self.plugins = plugins
        self.root_pid = root_pid   # solo se buscan juegos entre los descendientes de este PID
        self.active = None     # (plugin, mem, proc)
        self._next_scan = 0.0
        self._last_error_sent = 0.0
        self._failed = set()   # (plugin_id, pid) que fallaron de forma definitiva: no reintentar
        self._retrying = {}    # (plugin_id, pid) -> próximo log; el juego aún arranca
        self._logged_errors = set()
        self._pending = None   # read() en curso que superó READ_TIMEOUT

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
        self._pending = None
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
            if self._pending is None:   # lecturas largas no bloquean el bucle
                self._pending = asyncio.get_running_loop().run_in_executor(None, plugin.read, mem)
            done, _ = await asyncio.wait({self._pending}, timeout=self.READ_TIMEOUT)
            if not done:
                # No se puede matar un hilo: se espera a que acabe sin lanzar otra lectura
                if now - self._last_error_sent >= self.ERROR_EVERY:
                    self._last_error_sent = now
                    print(f'[plugins] {plugin.id}: read() tarda más de {self.READ_TIMEOUT:.0f} s', flush=True)
                    return [{'t': 'gv', 'err': f'el plugin tarda más de {self.READ_TIMEOUT:.0f} s en leer'}]
                return []
            future, self._pending = self._pending, None
            values = future.result()
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
