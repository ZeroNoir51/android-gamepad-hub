"""Lectura (solo lectura) de memoria de otro proceso en Linux vía /proc/<pid>/mem.

Permisos: el kernel exige permiso de tipo ptrace sobre el proceso objetivo.
Con Yama ptrace_scope=1 (Ubuntu por defecto) un usuario normal solo puede
leer procesos descendientes suyos; root o CAP_SYS_PTRACE pueden leer cualquiera.

Windows (futuro): WindowsProcessMemory con OpenProcess(PROCESS_VM_READ) +
ReadProcessMemory, con la misma interfaz pública que LinuxProcessMemory.
"""
import os
import struct
from dataclasses import dataclass


class MemoryReadError(Exception):
    pass


class ProcessGone(Exception):
    pass


@dataclass(frozen=True)
class ProcInfo:
    pid: int
    comm: str        # nombre corto del kernel (máx. 15 caracteres)
    exe_name: str    # basename de argv[0]; con Wine/Proton suele ser "Juego.exe"
    cmdline: str


def iter_processes():
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        try:
            with open(f'/proc/{entry}/comm') as f:
                comm = f.read().strip()
            with open(f'/proc/{entry}/cmdline', 'rb') as f:
                argv = [a.decode('utf-8', 'replace') for a in f.read().split(b'\0') if a]
        except OSError:
            continue
        exe = argv[0].replace('\\', '/').rsplit('/', 1)[-1] if argv else ''
        yield ProcInfo(int(entry), comm, exe, ' '.join(argv))


def descendants(root_pid):
    """Procesos descendientes de root_pid (los únicos legibles con ptrace_scope=1)."""
    parent = {}
    for entry in os.listdir('/proc'):
        if entry.isdigit():
            try:
                with open(f'/proc/{entry}/stat') as f:
                    parent[int(entry)] = int(f.read().rsplit(')', 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                continue
    wanted = set()
    for pid in parent:
        p, seen = pid, 0
        while p in parent and p != root_pid and seen < 64:
            p, seen = parent[p], seen + 1
        if p == root_pid and pid != root_pid:
            wanted.add(pid)
    return [proc for proc in iter_processes() if proc.pid in wanted]


def _start_time(pid):
    with open(f'/proc/{pid}/stat') as f:
        # campo 22; el nombre (campo 2) puede contener espacios y paréntesis
        return int(f.read().rsplit(')', 1)[1].split()[19])


class LinuxProcessMemory:
    _FMT = {'u8': 'B', 'i8': 'b', 'u16': 'H', 'i16': 'h', 'u32': 'I', 'i32': 'i',
            'u64': 'Q', 'i64': 'q', 'f32': 'f', 'f64': 'd'}

    def __init__(self, pid, ptr_size=8):
        self.pid = pid
        self.ptr_size = ptr_size
        self._modules = None
        try:
            self._start = _start_time(pid)
            self._fd = os.open(f'/proc/{pid}/mem', os.O_RDONLY)
        except FileNotFoundError as ex:
            raise ProcessGone(pid) from ex
        except PermissionError as ex:
            raise PermissionError(
                f'Sin permiso para leer la memoria del PID {pid}: el juego debe lanzarse con '
                '`ps5gamepad run %command%` para ser descendiente del lector (ver README).') from ex

    def alive(self):
        try:
            return _start_time(self.pid) == self._start   # evita confundir PIDs reutilizados
        except (OSError, ValueError, IndexError):
            return False

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    # --- lectura básica ---
    def read(self, addr, size):
        if addr <= 0:
            raise MemoryReadError(f'dirección inválida 0x{addr:x}')
        try:
            data = os.pread(self._fd, size, addr)
        except OSError as ex:
            if not self.alive():
                raise ProcessGone(self.pid) from ex
            raise MemoryReadError(f'no se pudo leer 0x{addr:x} ({ex.strerror})') from ex
        if len(data) != size:
            if not self.alive():
                raise ProcessGone(self.pid)
            raise MemoryReadError(f'lectura incompleta en 0x{addr:x}')
        return data

    def value(self, kind, addr):
        fmt = self._FMT[kind]
        return struct.unpack('<' + fmt, self.read(addr, struct.calcsize(fmt)))[0]

    def u8(self, a): return self.value('u8', a)
    def i16(self, a): return self.value('i16', a)
    def u16(self, a): return self.value('u16', a)
    def i32(self, a): return self.value('i32', a)
    def u32(self, a): return self.value('u32', a)
    def i64(self, a): return self.value('i64', a)
    def u64(self, a): return self.value('u64', a)
    def f32(self, a): return self.value('f32', a)
    def f64(self, a): return self.value('f64', a)

    def ptr(self, addr):
        return self.value('u64' if self.ptr_size == 8 else 'u32', addr)

    def string(self, addr, max_len=64, encoding='utf-8'):
        raw = self.read(addr, max_len)
        return raw.split(b'\0', 1)[0].decode(encoding, 'replace')

    def pointer(self, base, *offsets):
        """Cadena de punteros estilo Cheat Engine.

        pointer(B, o1, o2) == [[B] + o1] + o2, es decir: lee el puntero en B,
        suma o1, lee el puntero ahí, suma o2 y devuelve esa dirección final
        (no su contenido). Sin offsets devuelve [B].
        """
        addr = self.ptr(base)
        for i, off in enumerate(offsets):
            if addr == 0:
                raise MemoryReadError(f'puntero nulo en el nivel {i} de la cadena')
            addr += off
            if i < len(offsets) - 1:
                addr = self.ptr(addr)
        return addr

    # --- módulos ---
    def module_base(self, name):
        """Dirección más baja donde está mapeado un ejecutable/librería (sin mayúsculas)."""
        if self._modules is None:
            mods = {}
            try:
                with open(f'/proc/{self.pid}/maps') as f:
                    for line in f:
                        parts = line.split(None, 5)
                        if len(parts) < 6:
                            continue
                        path = parts[5].strip().replace('\\', '/')
                        base = os.path.basename(path).lower()
                        start = int(parts[0].split('-')[0], 16)
                        if base and (base not in mods or start < mods[base]):
                            mods[base] = start
            except FileNotFoundError as ex:
                raise ProcessGone(self.pid) from ex
            self._modules = mods
        try:
            return self._modules[name.lower()]
        except KeyError:
            raise MemoryReadError(f'módulo {name!r} no encontrado en el proceso') from None


def open_process(pid, ptr_size=8):
    return LinuxProcessMemory(pid, ptr_size)
