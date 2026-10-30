"""Diagnóstico: ¿dónde guarda el juego qué personajes van en el grupo?

Busca en el bloque de estado listas de 4 IDs de personaje distintos. Como no se sabe
cómo las guarda el juego, prueba varias formas: IDs de 1, 2 o 4 bytes, seguidos o como
primer campo de pequeñas estructuras (cada 4, 8 o 16 bytes). Con el grupo real del
jugador se identifica cuál es; luego se leerá directamente.
"""
import re
import struct

from server.plugin_api import MemoryReadError

CHUNK = 1 << 20
MAX_HITS = 120                      # por forma: los IDs pequeños dan muchas coincidencias
# (nombre, ancho del ID, separación entre miembros)
LAYOUTS = [('u8', 1, 1), ('u16', 2, 2), ('u16', 2, 4), ('u16', 2, 8),
           ('u32', 4, 4), ('u32', 4, 8), ('u32', 4, 16)]
FMT = {1: '<B', 2: '<H', 4: '<I'}


def candidates(mem, start, size, ids, layouts=LAYOUTS):
    """[(offset, forma, (id1..id4))] de listas plausibles dentro de [start, start+size).
    Con `layouts` se puede repartir el trabajo entre varias lecturas (una forma cada vez)."""
    ids = {i for i in ids if 0 <= i < 0x10000}
    hits = []
    for name, width, stride in layouts:
        usable = sorted(i for i in ids if i and i < 1 << (8 * width))
        if len(usable) < 3:
            continue
        found = _scan(mem, start, size, ids, width, stride, usable)
        hits += [(off, f'{name}/{stride}', vals) for off, vals in found]
    return hits


def _scan(mem, start, size, ids, width, stride, usable):
    fmt = FMT[width]
    # Toda lista válida tiene un ID distinto de 0 en su posición 0 o 1
    rx = re.compile(b'|'.join(re.escape(struct.pack(fmt, i)) for i in usable), re.DOTALL)
    span = 3 * stride + width
    out, seen = [], set()
    for pos in range(0, size, CHUNK):
        length = min(CHUNK + span + stride, size - pos)
        try:
            data = mem.read(start + pos, length)
        except MemoryReadError:
            continue
        for m in rx.finditer(data):
            if m.start() % width or m.start() >= CHUNK:
                continue
            for first in (m.start(), m.start() - stride):
                if first < 0 or first + span > len(data) or (pos + first) in seen:
                    continue
                seen.add(pos + first)
                vals = tuple(struct.unpack_from(fmt, data, first + k * stride)[0] for k in range(4))
                if len(set(vals)) == 4 and all(v in ids for v in vals) and sum(1 for v in vals if v) >= 3:
                    out.append((pos + first, vals))
                    if len(out) >= MAX_HITS:
                        return out
    return out


def describe(hits, block, names, limit=8):
    if not hits:
        return 'ninguna lista de 4 personajes'
    parts = [f'{form} +0x{off:X}: ' + ', '.join(str(names.get(v, v)) for v in vals)
             for off, form, vals in sorted(hits)[:limit]]
    more = f' (+{len(hits) - limit} más, ver launcher.log)' if len(hits) > limit else ''
    return f'{len(hits)} listas: ' + ' | '.join(parts) + more
