"""Registros de personaje dentro del bloque de estado del juego.

La tabla (script "Selected Character") obtiene un registro inyectando código; aquí se
buscan leyendo: cada registro empieza con ID (u16), nivel, EXP, HP/máx, EP/máx, CP/máx y
las estadísticas, y tiene que cuadrar todo a la vez. Los registros de verdad forman un
array con separación fija (sin solaparse) y cada uno es un personaje distinto: gana la
serie con más IDs de personajes conocidos y, a igualdad, más IDs distintos. Así no ganan
ni las copias repetidas de un personaje ni las "ventanas" desplazadas dentro de los
registros reales (que también pueden cuadrar, pero con IDs que no son de personajes).
"""
import array
import collections
import re
import struct

from server.plugin_api import MemoryReadError

# Offsets del registro (tabla sora_2nd-v2.CT, script "Selected Character")
ID, LEVEL, EXP, HP, HP_MAX, EP, EP_MAX, CP, CP_MAX = 0x0, 0x4, 0x8, 0xC, 0x10, 0x14, 0x18, 0x1C, 0x20
STATS = 0x24            # STR, DEF, ATS, ADF, SPD, AGL, DEX (u32 cada uno)
MOV = 0x40
RECORD = struct.Struct('<HH17I')   # ID, (u16), nivel ... MOV: 0x48 bytes
SCAN_CHUNK = 256 << 10


def plausible(w, i):
    """¿Empieza un registro de personaje en la palabra i (u32) de w?"""
    lv = w[i + 1]
    if not 1 <= lv <= 200 or (w[i] & 0xFFFF) > 0x3FF or w[i + 2] > 99_999_999:
        return False
    hp, hp_max, ep, ep_max, cp, cp_max = w[i + 3:i + 9]
    if not (1 <= hp_max <= 999_999 and hp <= hp_max and ep_max <= 99_999 and ep <= ep_max
            and 100 <= cp_max <= 300 and cp <= cp_max):   # CP máximo: 200 en la saga
        return False
    if not all(1 <= s <= 99_999 for s in w[i + 9:i + 16]):
        return False
    return 1 <= w[i + 16] <= 50


def candidates(mem, start, size):
    """Direcciones (alineadas a 4) dentro de [start, start+size) que parecen registros."""
    out = []
    overlap = RECORD.size
    for pos in range(0, size, SCAN_CHUNK):
        length = min(SCAN_CHUNK + overlap, size - pos) & ~3
        try:
            data = mem.read(start + pos, length)
        except MemoryReadError:
            continue
        w = array.array('I')
        w.frombytes(data)
        last = min(SCAN_CHUNK, length) // 4
        for i in range(min(last, len(w) - 16)):
            if 1 <= w[i + 1] <= 200 and plausible(w, i):
                out.append(start + pos + i * 4)
    return out


def best_run(addrs, ident=None, known=()):
    """(primera, separación, cuántos) de la serie con separación constante (>= un registro)
    con más IDs conocidos y luego más IDs distintos. ident(dirección) -> ID."""
    if not addrs:
        return None
    ident = ident or (lambda a: a)
    present, known = set(addrs), set(known)

    def score(ids):
        return len(ids & known), len(ids)

    best = (addrs[0], 0, 1)
    best_score = score({ident(addrs[0])})
    # Distancias a los siguientes candidatos (no solo al inmediato: puede haber otros en medio)
    diffs = collections.Counter(b - a for i, a in enumerate(addrs) for b in addrs[i + 1:i + 9]
                                if b - a >= RECORD.size)
    for stride, _ in diffs.most_common(300):   # basura repetida puede ser más frecuente que el grupo
        for a in addrs:
            if a - stride in present:
                continue                       # no es el principio de una serie
            n = 1
            while a + n * stride in present:
                n += 1
            sc = score({ident(a + k * stride) for k in range(n)})
            if sc > best_score:
                best, best_score = (a, stride, n), sc
    return best


def find_roster(mem, start, size, known=()):
    """(candidatos, serie) dentro del bloque. Si hay IDs conocidos, la serie se busca solo
    entre los candidatos con esos IDs (los inicios reales de registro)."""
    found = candidates(mem, start, size)
    ident = {a: mem.u16(a) for a in found}
    pool = [a for a in found if ident[a] in known] or found
    return found, best_run(pool, ident.get, known)


def loose(w, i):
    """Comprobación mínima de un registro, para cuando ya se conoce la rejilla del array."""
    return ((w[i] & 0xFFFF) <= 0x3FF and 1 <= w[i + 1] <= 200 and w[i + 2] <= 99_999_999
            and 1 <= w[i + 4] <= 999_999)


def grid(mem, run, lo, hi, span=40):
    """{ID: dirección} de los registros en la rejilla de la serie (también los que no pasan
    plausible(), p. ej. con algún campo fuera de lo esperado). La primera aparición gana."""
    first, stride, n = run
    out = {}
    if not stride:
        return {mem.u16(first): first}
    for k in range(-span, n + span):
        a = first + k * stride
        if a < lo or a + RECORD.size > hi:
            continue
        try:
            w = array.array('I')
            w.frombytes(mem.read(a, RECORD.size))
        except MemoryReadError:
            continue
        if loose(w, 0):
            out.setdefault(w[0] & 0xFFFF, a)
    return out


def by_id(mem, start, size, ids, fits, limit=8):
    """{ID: [direcciones]} de registros de esos personajes en todo el bloque, aunque no estén
    en la serie. fits(nivel, exp) valida la EXP contra la fórmula del juego: un filtro fuerte."""
    ids = {i for i in ids if 0 <= i <= 0x3FF}
    if not ids:
        return {}
    # ID (u32) seguido de un nivel 1-200: así las zonas de ceros no coinciden con Estelle (ID 0)
    level = b'[\x01-\xc8]\x00\x00\x00'
    # (?=...): sin consumir bytes, para que unos ceros justo antes de un registro ("ID 0, nivel 2")
    # no se coman la coincidencia del registro de verdad
    rx = re.compile(b'(?=(?:' + b'|'.join(re.escape(struct.pack('<I', i)) for i in sorted(ids)) + b')' + level
                    + b')', re.DOTALL)
    out = {}
    for pos in range(0, size, SCAN_CHUNK):
        length = min(SCAN_CHUNK + RECORD.size, size - pos)
        try:
            data = mem.read(start + pos, length)
        except MemoryReadError:
            continue
        for m in rx.finditer(data):
            i = m.start()
            if i % 4 or i >= SCAN_CHUNK or i + RECORD.size > len(data):
                continue
            v = RECORD.unpack_from(data, i)
            cid, level, exp, hp, hp_max, ep, ep_max, cp, cp_max = v[0], *v[2:10]
            if (1 <= level <= 200 and 1 <= hp_max <= 999_999 and hp <= hp_max and ep <= ep_max <= 99_999
                    and cp <= cp_max <= 300 and fits(level, exp)):
                found = out.setdefault(cid, [])
                if len(found) < limit:
                    found.append(start + pos + i)
    return out


def read_record(mem, addr):
    v = RECORD.unpack(mem.read(addr, RECORD.size))
    return {'id': v[0], 'level': v[2], 'exp': v[3], 'hp': v[4], 'hp_max': v[5],
            'ep': v[6], 'ep_max': v[7], 'cp': v[8], 'cp_max': v[9]}


def still_valid(mem, addr):
    try:
        w = array.array('I')
        w.frombytes(mem.read(addr, RECORD.size))
        return plausible(w, 0)
    except MemoryReadError:
        return False
