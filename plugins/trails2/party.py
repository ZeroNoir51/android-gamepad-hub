"""Diagnóstico: ¿dónde guarda el juego qué personajes van en el grupo?

Busca en el bloque de estado listas de 4 IDs de personaje distintos seguidos (u16 o u32).
Con el grupo real del jugador se identifica cuál es; luego se leerá directamente.
"""
import re
import struct

from server.plugin_api import MemoryReadError

CHUNK = 1 << 20
MAX_HITS = 400


def candidates(mem, start, size, ids):
    """[(offset, ancho, (id1..id4))] de listas plausibles dentro de [start, start+size)."""
    ids = {i for i in ids if 0 <= i < 0x10000}
    nonzero = sorted(i for i in ids if i)
    if len(ids) < 4 or not nonzero:
        return []
    hits, seen = [], set()
    for width, fmt in ((2, '<4H'), (4, '<4I')):
        # Un elemento distinto de cero: toda lista válida tiene uno en su posición 0 o 1
        rx = re.compile(b'(?:' + b'|'.join(re.escape(struct.pack('<' + 'HI'[width == 4], i)) for i in nonzero)
                        + b')', re.DOTALL)
        for pos in range(0, size, CHUNK):
            length = min(CHUNK + 4 * width, size - pos)
            try:
                data = mem.read(start + pos, length)
            except MemoryReadError:
                continue
            for m in rx.finditer(data):
                if m.start() % width or m.start() >= CHUNK:
                    continue
                for first in (m.start(), m.start() - width):
                    if first < 0 or first + 4 * width > len(data):
                        continue
                    key = (pos + first, width)
                    if key in seen:
                        continue
                    seen.add(key)
                    vals = struct.unpack_from(fmt, data, first)
                    if len(set(vals)) == 4 and all(v in ids for v in vals):
                        hits.append((pos + first, width, vals))
                        if len(hits) >= MAX_HITS:
                            return hits
    return hits


def describe(hits, block, names, limit=8):
    if not hits:
        return 'ninguna lista de 4 personajes'
    parts = [f'{"u16" if w == 2 else "u32"} +0x{off:X}: ' + ', '.join(str(names.get(v, v)) for v in vals)
             for off, w, vals in sorted(hits)[:limit]]
    more = f' (+{len(hits) - limit} más, ver launcher.log)' if len(hits) > limit else ''
    return f'{len(hits)} listas: ' + ' | '.join(parts) + more
