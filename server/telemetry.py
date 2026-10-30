"""Telemetría del host Linux sin dependencias: /proc y /sys.

FPS y frametimes no se pueden leer "desde fuera" de forma genérica; se obtienen
del log CSV que MangoHud escribe mientras corre el juego (ver README).
"""
import ctypes
import os
import time
from pathlib import Path

_FALLOC_FL_KEEP_SIZE = 0x01
_FALLOC_FL_PUNCH_HOLE = 0x02
try:
    _libc = ctypes.CDLL(None, use_errno=True)
    _libc.fallocate.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_long, ctypes.c_long]
except (OSError, AttributeError):
    _libc = None


def punch_hole(path, length):
    """Libera los primeros `length` bytes del archivo sin cambiar su tamaño ni sus offsets.

    MangoHud sigue escribiendo al final con normalidad; la parte ya leída deja de
    ocupar RAM/disco. Devuelve False si el sistema de archivos no lo soporta.
    """
    if _libc is None or length <= 0:
        return False
    try:
        fd = os.open(path, os.O_WRONLY)
    except OSError:
        return False
    try:
        return _libc.fallocate(fd, _FALLOC_FL_PUNCH_HOLE | _FALLOC_FL_KEEP_SIZE, 0, length) == 0
    finally:
        os.close(fd)

CPU_HWMON = ('k10temp', 'zenpower', 'coretemp', 'cpu_thermal', 'soc_thermal')
GPU_HWMON = ('amdgpu', 'nouveau', 'i915', 'xe')


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int(path):
    v = _read(path)
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


def _find_hwmon_temp(names):
    """Primer hwmon cuyo 'name' esté en names (en ese orden de preferencia)."""
    found = {}
    for hw in sorted(Path('/sys/class/hwmon').glob('hwmon*')):
        name = _read(hw / 'name')
        if name in names and name not in found and (hw / 'temp1_input').exists():
            found[name] = hw / 'temp1_input'
    for n in names:
        if n in found:
            return found[n]
    return None


def _find_thermal_zone():
    zones = sorted(Path('/sys/class/thermal').glob('thermal_zone*'))
    for z in zones:
        if _read(z / 'type') in ('x86_pkg_temp', 'cpu-thermal', 'cpu_thermal'):
            return z / 'temp'
    return zones[0] / 'temp' if zones else None


class SystemTelemetry:
    def __init__(self):
        self._prev_cpu = None
        self.cpu_temp_path = _find_hwmon_temp(CPU_HWMON) or _find_thermal_zone()
        self.gpu_temp_path = _find_hwmon_temp(GPU_HWMON)
        busy = sorted(Path('/sys/class/drm').glob('card*/device/gpu_busy_percent'))
        self.gpu_busy_path = busy[0] if busy else None

    def sources(self):
        return {'cpu_temp': str(self.cpu_temp_path), 'gpu_temp': str(self.gpu_temp_path),
                'gpu_busy': str(self.gpu_busy_path)}

    def _cpu_load(self):
        line = _read('/proc/stat')
        if not line:
            return None
        parts = [int(x) for x in line.splitlines()[0].split()[1:]]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        total = sum(parts[:8])
        prev, self._prev_cpu = self._prev_cpu, (idle, total)
        if prev is None or total == prev[1]:
            return None
        return round(100.0 * (1 - (idle - prev[0]) / (total - prev[1])), 1)

    @staticmethod
    def _temp(path):
        v = _read_int(path) if path else None
        return round(v / 1000, 1) if v is not None else None

    @staticmethod
    def _mem():
        info = {}
        for line in (_read('/proc/meminfo') or '').splitlines():
            k, _, rest = line.partition(':')
            if k in ('MemTotal', 'MemAvailable'):
                info[k] = int(rest.split()[0]) * 1024
        if len(info) < 2:
            return None, None
        return info['MemTotal'] - info['MemAvailable'], info['MemTotal']

    def sample(self):
        used, total = self._mem()
        return {
            'cpu': {'load': self._cpu_load(), 'temp': self._temp(self.cpu_temp_path)},
            'gpu': {'load': _read_int(self.gpu_busy_path) if self.gpu_busy_path else None,
                    'temp': self._temp(self.gpu_temp_path)},
            'mem': {'used': used, 'total': total},
        }


class MangoHudTail:
    """Sigue el CSV más reciente de MangoHud y entrega fps/frametime nuevos.

    MangoHud solo escribe logs si output_folder existe y está configurado
    (ver README). Con log_interval=0 escribe una fila por frame.
    """
    STALE_AFTER = 2.5   # s sin filas nuevas => no hay juego midiéndose
    RESCAN_EVERY = 1.0
    MAX_BATCH = 240
    FPS_WINDOW_MS = 1000.0
    PUNCH_EVERY = 4 * 1024 * 1024    # liberar cada 4 MB leídos

    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = None
        self.fh = None
        self.cols = None
        self.buf = ''
        self.last_row_at = 0.0
        self.recent = []          # frametimes recientes para promediar FPS
        self.status = 'sin comprobar'
        self._next_scan = 0.0

    def _newest(self):
        if not self.folder.is_dir():
            self.status = f'no existe la carpeta {self.folder}'
            return None
        try:
            files = [p for p in self.folder.glob('*.csv') if not p.name.endswith('_summary.csv')]
            newest = max(files, key=lambda p: p.stat().st_mtime, default=None)
        except OSError as ex:
            self.status = f'no se puede leer {self.folder}: {ex.strerror}'
            return None
        if newest is None:
            self.status = ''   # normal sin juego: el lanzador borra el log al cerrarlo
        return newest

    def _open(self, path):
        if self.fh:
            self.fh.close()
        self.fh = open(path, 'r', errors='replace')
        self.path, self.cols, self.buf, self.recent = path, None, '', []
        self.punched = 0

    def _fps(self):
        total, n = 0.0, 0
        for ft in reversed(self.recent):
            if total >= self.FPS_WINDOW_MS:
                break
            total += ft
            n += 1
        return round(n * 1000.0 / total, 1) if total > 0 else None

    def poll(self):
        now = time.monotonic()
        if now >= self._next_scan:
            self._next_scan = now + self.RESCAN_EVERY
            newest = self._newest()
            if newest is not None and newest != self.path:
                try:
                    self._open(newest)
                except OSError as ex:
                    self.path, self.fh = None, None
                    self.status = f'no se puede abrir {newest.name}: {ex.strerror}'
        new_ft = []
        if self.fh:
            self.buf += self.fh.read()
            *lines, self.buf = self.buf.split('\n')
            for line in lines:
                cells = line.strip().split(',')
                if self.cols is None:
                    if cells and cells[0] == 'fps':   # cabecera de métricas por frame
                        self.cols = {name: i for i, name in enumerate(cells)}
                    continue
                try:
                    if 'frametime' in self.cols:
                        ft = float(cells[self.cols['frametime']])
                    else:
                        ft = 1000.0 / float(cells[self.cols['fps']])
                except (ValueError, IndexError, ZeroDivisionError, KeyError):
                    continue
                if ft <= 0:
                    continue
                new_ft.append(round(ft, 2))
                self.last_row_at = now
            if new_ft:
                self.recent = (self.recent + new_ft)[-2000:]
            consumed = self.fh.buffer.tell() if hasattr(self.fh, 'buffer') else 0
            done = (consumed - len(self.buf.encode())) & ~0xFFFF   # alineado a 64 KiB
            if done - self.punched >= self.PUNCH_EVERY and punch_hole(self.path, done):
                self.punched = done
        if self.fh and now - self.last_row_at > self.STALE_AFTER:
            # Juego cerrado o en pausa: no es un error y no se avisa. Si el lanzador ya
            # borró el log, se suelta para que su espacio se libere de verdad.
            self.status = ''
            if not self.path.exists():
                self.fh.close()
                self.path, self.fh = None, None
        if now - self.last_row_at > self.STALE_AFTER:
            return {'fps': None, 'ft': None, 'ftNew': [], 'mh': self.status}
        self.status = f'ok: {self.path.name}'
        return {'fps': self._fps(), 'ft': self.recent[-1], 'ftNew': new_ft[-self.MAX_BATCH:], 'mh': self.status}
