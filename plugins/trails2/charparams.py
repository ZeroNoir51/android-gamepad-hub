"""Multiplicador de EXP y tope de nivel propios de cada personaje (solo lectura).

La función de EXP total del juego los obtiene así (desensamblado de la 1.03.1):

  mgr = [exe+global]                          (mov rsi,[rip+disp] en la función de EXP)
  T   = [[mgr+0x10]+8]  -> búsqueda 1 (exe+0x255880): tabla de parámetros por ID
        idx = [T+0x28]; desc = [T+0x20] + idx*0x50
        n = u32 [desc+0x4C]; paso = u32 [desc+0x48]; ini = u64 [desc+0x44]; base = [T+0x10]
        entrada i = base + ini + (paso*i mod 2^32), con u16 [entrada] == ID
  clave = texto en [[entrada+0x40]]           -> CRC32 del texto (texto vacío: 0xFFFFFFFF)
  T2  = [[mgr+0x28]+8]  -> búsqueda 2 (exe+0x258970): unordered_map de MSVC
        nodos de una lista: {siguiente, anterior, clave u32 (+0x10), valor (+0x18)}
  resultado: byte [+0x10] == 1 -> tope 175 (si no, 200); float [+0xE8] -> multiplicador

Lo que el volcado no muestra (variante del CRC, valor puntero o dentro del nodo) se
resuelve probando: vale la combinación con la que la EXP del personaje cuadra.
"""
import struct
import zlib

from server.plugin_api import MemoryReadError

MASK64 = (1 << 64) - 1
MAX_ENTRIES = 4096
MAX_NODES = 8192


def _entry(mem, mgr, cid):
    t = mem.ptr(mem.ptr(mgr + 0x10) + 8)
    idx = struct.unpack('<i', mem.read(t + 0x28, 4))[0]
    desc = mem.ptr(t + 0x20) + idx * 0x50
    n, step = mem.u32(desc + 0x4C), mem.u32(desc + 0x48)
    start = (mem.ptr(t + 0x10) + mem.u64(desc + 0x44)) & MASK64
    print(f'[trails2]   tabla de parámetros: T=0x{t:X} idx={idx} desc=0x{desc:X} n={n} paso=0x{step:X} '
          f'ini=0x{mem.u64(desc + 0x44):X} base=0x{mem.ptr(t + 0x10):X} -> 0x{start:X}', flush=True)
    if not 0 < n <= MAX_ENTRIES:
        raise MemoryReadError(f'tabla de parámetros con {n} entradas')
    try:
        print('[trails2]   primeros IDs: ' + ' '.join(
            str(mem.u16((start + (step * i & 0xFFFFFFFF)) & MASK64)) for i in range(min(n, 12))), flush=True)
    except MemoryReadError as ex:
        print(f'[trails2]   primeros IDs: {ex}', flush=True)
    for i in range(n):
        addr = (start + (step * i & 0xFFFFFFFF)) & MASK64
        if mem.u16(addr) == cid:
            return addr
    return None


def _nodes(mem, mgr):
    """{clave: nodo} recorriendo la lista del unordered_map (acotado)."""
    t2 = mem.ptr(mem.ptr(mgr + 0x28) + 8)
    head = mem.ptr(t2 + 0x38)
    out, node = {}, mem.ptr(head)
    for _ in range(MAX_NODES):
        if node in (0, head):
            break
        out.setdefault(mem.u32(node + 0x10), node)
        node = mem.ptr(node)
    return out


def candidates(mem, mgr, cid):
    """[(descripción, multiplicador, tope)] posibles para el personaje; [] si no se encuentra."""
    entry = _entry(mem, mgr, cid)
    if entry is None:
        return []
    raw = mem.read(mem.ptr(entry + 0x40), 64).split(b'\0', 1)[0]
    keys = [0xFFFFFFFF] if not raw else [zlib.crc32(raw), ~zlib.crc32(raw) & 0xFFFFFFFF]
    nodes = _nodes(mem, mgr)
    out = []
    for k in keys:
        node = nodes.get(k)
        if node is None:
            continue
        for desc, params in (('valor puntero', mem.ptr(node + 0x18)), ('valor en el nodo', node + 0x18)):
            try:
                mult = mem.f32(params + 0xE8)
                cap = 175 if mem.u8(params + 0x10) == 1 else 200
            except MemoryReadError:
                continue
            if 0.1 <= mult <= 10:
                out.append((f'{raw.decode("ascii", "replace")} crc {k:08X} {desc}', mult, cap))
    return out
