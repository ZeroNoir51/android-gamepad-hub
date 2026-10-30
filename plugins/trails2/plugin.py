"""Trails in the Sky 2nd Chapter (2026) — motor propio de Falcom, vía Proton.

Solo lectura. Firmas y offsets de la tabla sora_2nd-v2.CT (Tuuuup!, sora_2nd.exe 1.0.0.0):

  Bloque de estado:  firma "Mira + Sepith and Play time": mov rXX,[rip+disp] -> puntero
                     al bloque. Tiempo de juego (double) en +0x20B650, Mira (u32) en
                     +0x20B648, sepith (8 x u32: tierra, agua, fuego, viento, tiempo,
                     espacio, espejismo, masa) desde +0x20B628.
  Tiempo de juego:   la firma "Set playtime to 0" es la instrucción que lo suma
                     (addsd xmm0,[rbx+0x20B650]); el offset se LEE de ahí, así que si
                     un parche lo mueve, Mira y sepith (relativos a él) lo siguen.
  Personajes:        estructura del script "Selected Character" (ID, nivel, EXP, HP,
                     EP, CP...). La tabla consigue la dirección inyectando código; aquí
                     se buscan los registros dentro del bloque (ver roster.py).
                     Verificado en el juego (1.03.1): nivel y EXP correctos.
  Siguiente nivel:   el juego lo calcula: EXP total(N+1) - EXP, con EXP total = 100·N·(N+3)
                     por un multiplicador (ver expcurve.py; constantes leídas del código).

Sin verificar en el juego todavía: dónde están los registros de personaje y qué
miembros forman el grupo (se muestran los 4 primeros del array). Los diagnósticos
(Debug) dicen qué se encontró.
"""
import math
import re
import struct
import time

from server.plugin_api import Field, GamePlugin, MemoryReadError, PortraitFinder, pe_info

from . import charparams, expcurve, party, roster
from .scan import SignatureError, find_one, rip_target

MODULE = 'sora_2nd.exe'
AOB_STATE = '488B??????????0FB6??????????488B??????????488B????F3'
AOB_PLAYTIME = 'F2??????????????F2??????????????0F57??F3'
CT_PLAYTIME = 0x20B650           # si falta la firma del tiempo de juego, el de la tabla
MONEY = struct.Struct('<8IIId')  # sepith x8, Mira, (relleno), tiempo de juego: desde tiempo - 0x28
SCAN_SIZE = 0x700000             # el bloque llega al menos a +0x6247C0 (script del tiempo de juego)
RESCAN_EVERY = 10.0
# Lista de miembros (u16, en orden; los 4 primeros forman el grupo activo). Encontrada en la
# 1.03.1 con el diagnóstico "grupo?" y el grupo real del jugador. Se valida contra los registros.
PARTY_LIST = 0x5145C
PARTY_MAX = 4
# Función del juego "EXP que falta para el siguiente nivel" (script "Selected Character"):
# su código llama a la que da la EXP total de un nivel; de esa se lee la fórmula (expcurve.py).
AOB_NEXT_LEVEL = '448B4304443BC07C??33C0488B5C2430'
NEXT_LEVEL_FUNC = -0x4E          # inicio de la función respecto a la firma
NEXT_LEVEL_CALL = 0x1E           # call a la función de EXP total

# IDs 0-7: grupo principal (tabla); el orden de nombres es el de la saga, por confirmar.
NAMES = {0: 'Estelle', 1: 'Joshua', 2: 'Scherazard', 3: 'Olivier', 4: 'Kloe', 5: 'Agate',
         6: 'Tita', 7: 'Zin', 100: 'Kurt', 101: 'Anelace', 106: 'Josette',
         107: 'Schwarz', 112: 'Vander', 119: 'Kevin', 124: 'Dorothy'}
# Retratos: ~/.local/share/gamepad/portraits/trails2/<nombre>.png (o <ID>.png)
PORTRAITS = {cid: (name.lower(),) for cid, name in NAMES.items()}


def fmt(n):
    return f'{n:,}'.replace(',', '.')


def playtime_text(seconds):
    total = int(seconds)
    return f'{total // 3600} h {total % 3600 // 60:02d} min'


def _party_fields():
    out = []
    for n in range(1, 5):
        out += [
            Field(f'p{n}_name', f'Miembro {n}', kind='text', section='party', slot=n),
            Field(f'p{n}_img', 'Retrato', kind='image', section='party', slot=n),
            Field(f'p{n}_lv', 'Nivel', kind='text', section='party', slot=n),
            Field(f'p{n}_hp', 'HP', kind='bar', max_key=f'p{n}_hp_max', tone='hp', section='party', slot=n),
            Field(f'p{n}_ep', 'EP', kind='bar', max_key=f'p{n}_ep_max', tone='mp', section='party', slot=n),
            Field(f'p{n}_cp', 'CP', kind='bar', max_key=f'p{n}_cp_max', tone='limit', section='party', slot=n),
        ]
    return out


class Plugin(GamePlugin):
    id = 'trails2'
    name = 'Trails in the Sky 2nd Chapter'
    process_names = (MODULE,)
    poll_hz = 4
    party_style = 'ring'
    fields = _party_fields() + [
        Field('mira', 'Mira', tone='gold', section='stats'),
        Field('playtime', 'Tiempo de juego', kind='text', section='stats'),
        Field('status', 'Estado', kind='text', section='info'),
        Field('build', 'Ejecutable', kind='text', section='info'),
        Field('dbg_sig', 'Diag. firmas', kind='text', section='info'),
        Field('dbg_roster', 'Diag. personajes', kind='text', section='info'),
        Field('dbg_party', 'Diag. grupo', kind='text', section='info'),
        Field('dbg_exp', 'Diag. EXP', kind='text', section='info'),
    ]

    def on_attach(self, mem, proc):
        self.base = mem.module_base(MODULE)
        pe = pe_info(mem, self.base)
        self.build = f'{MODULE} · PE {pe["timestamp"]:08X} · {fmt(pe["image_size"])} bytes'
        self.error = None
        self.state_ptr = None
        self.play_off, self.play_src = CT_PLAYTIME, 'de la tabla (firma no encontrada)'
        try:
            insn = find_one(mem, self.base, AOB_STATE, 'Mira/sepith')
            if mem.u8(insn + 2) & 0xC7 != 0x05:
                raise SignatureError('firma de Mira/sepith: la instrucción no es [rip+disp]')
            self.state_ptr = rip_target(mem, insn, 3, 7)
        except SignatureError as ex:
            self.error = str(ex)
        try:
            insn = find_one(mem, self.base, AOB_PLAYTIME, 'tiempo de juego')
            add, mov = mem.u32(insn + 4), mem.u32(insn + 12)
            if add == mov and 0x28 <= add < 0x10000000:   # addsd y movsd sobre el mismo campo
                self.play_off, self.play_src = add, 'leído de la firma'
        except SignatureError:
            pass
        self.mgr_slot = None          # gestor de datos del juego (lo pone _exp_curve)
        self.curve, self.curve_note = self._exp_curve(mem)
        self.portraits = PortraitFinder(self.id)
        self.block = None
        self.run = None              # (primer registro, separación, cuántos)
        self._next_scan = 0.0
        self._scan_note = 'sin buscar'
        self._party_scan = None       # (formas pendientes, IDs, coincidencias)
        self.records = {}             # ID -> dirección del registro (serie)
        self._by_id = {}              # ID -> [direcciones] buscadas por ID (fuera de la serie)
        self._next_id_scan = 0.0
        self._lookups_dumped = False
        self._char_curves = {}        # ID -> Curve propia (multiplicador/tope) o None
        self._party_src = ''
        self._party_off = PARTY_LIST    # lista de la que se lee el grupo
        self._watch = {}                # copias de la lista del grupo: offset -> últimos 8 bytes
        self._party_note = ''
        self._exp_note = self.curve_note

    def _exp_curve(self, mem):
        """Fórmula de EXP total por nivel, leída del código del juego."""
        try:
            hit = find_one(mem, self.base, AOB_NEXT_LEVEL, 'siguiente nivel')
            call = hit + NEXT_LEVEL_CALL
            if mem.u8(call) != 0xE8:
                raise SignatureError('siguiente nivel: no hay call donde se esperaba')
            func = rip_target(mem, call, 1, 5)
            curve = expcurve.from_code(mem, func)
            note = (f'EXP total = {curve.mul}·N·(N+{curve.add}) × {curve.mult:g} '
                    f'(exe+0x{func - self.base:X})')
            print(f'[trails2] {note}', flush=True)
            self.exp_func = func
            g = mem.read(func, expcurve.FUNC_SIZE).find(b'\x48\x8B\x35')   # mov rsi,[rip+disp]
            self.mgr_slot = rip_target(mem, func + g, 3, 7) if g >= 0 else None
            return curve, note
        except (SignatureError, MemoryReadError) as ex:
            print(f'[trails2] sin "siguiente nivel": {ex}', flush=True)
            return None, str(ex)

    def _dump_lookups(self, mem, func):
        """Diagnóstico (una vez, a launcher.log): el multiplicador propio de cada personaje
        sale de dos búsquedas en tablas del juego; se vuelca su código para poder leerlas."""
        try:
            code = mem.read(func, expcurve.FUNC_SIZE)
            g = code.find(b'\x48\x8B\x35')                 # mov rsi,[rip+disp]: gestor de datos
            if g >= 0:
                slot = rip_target(mem, func + g, 3, 7)
                mgr = mem.ptr(slot)
                print(f'[trails2] datos: exe+0x{slot - self.base:X} -> 0x{mgr:X}', flush=True)
                for off in (0x10, 0x28):
                    p = mem.ptr(mgr + off)
                    print(f'[trails2]   [+0x{off:X}] 0x{p:X} -> [+8] 0x{mem.ptr(p + 8):X}', flush=True)
            targets = []
            for pat in (b'\x48\x8B\xCD\xE8', b'\x48\x8B\x49\x08\xE8'):   # las dos búsquedas
                i = code.find(pat)
                if i >= 0:
                    targets.append(rip_target(mem, func + i + len(pat) - 1, 1, 5))
            for t in targets:
                data = mem.read(t, 0xC0)
                for i in range(0, len(data), 32):
                    print(f'[trails2] busqueda exe+0x{t + i - self.base:X}: {data[i:i + 32].hex(" ")}', flush=True)
        except MemoryReadError as ex:
            print(f'[trails2] sin volcado de las búsquedas: {ex}', flush=True)

    # --- personajes ---
    def _roster(self, mem, block):
        if self.run and roster.still_valid(mem, self.run[0]):
            return self.run
        now = time.monotonic()
        if now < self._next_scan:
            return None
        self._next_scan = now + RESCAN_EVERY
        t0 = time.monotonic()
        found, self.run = roster.find_roster(mem, block, SCAN_SIZE, NAMES)
        took = time.monotonic() - t0
        if self.run:
            first, stride, n = self.run
            self.records = roster.grid(mem, self.run, block, block + SCAN_SIZE)
            self._scan_note = (f'{len(found)} candidatos; serie de {n} cada 0x{stride:X} '
                               f'desde bloque+0x{first - block:X}; {len(self.records)} en la rejilla '
                               f'({took:.1f} s)')
        else:
            self._scan_note = f'ningún registro en bloque+0..0x{SCAN_SIZE:X} ({took:.1f} s)'
        return self.run

    def _char_curve(self, mem, rec):
        """Curva con el multiplicador/tope propios del personaje (los del juego), o None."""
        cid = rec['id']
        if cid in self._char_curves:
            return self._char_curves[cid]
        name, found = NAMES.get(cid, cid), None
        try:
            options = charparams.candidates(mem, mem.ptr(self.mgr_slot), cid) if self.mgr_slot else []
        except MemoryReadError as ex:
            options = []
            print(f'[trails2] parámetros de {name}: {ex}', flush=True)
        for desc, mult, cap in options:
            curve = expcurve.Curve(self.curve.add, self.curve.mul, mult, cap)
            ok = curve.consistent(rec['level'], rec['exp'])
            print(f'[trails2] parámetros de {name}: {desc}: × {mult:g}, tope {cap}'
                  f'{" (cuadra)" if ok else ""}', flush=True)
            if ok and found is None:
                found = curve
        if not options:
            print(f'[trails2] parámetros de {name}: no encontrados', flush=True)
        self._char_curves[cid] = found
        return found

    def _level_text(self, rec, mem=None):
        level, exp = rec['level'], rec['exp']
        if not self.curve:
            return f'Nv {level}'
        curve = self.curve
        if not curve.consistent(level, exp):
            # multiplicador propio del personaje (p. ej. 0,98 de los invitados): se lee del juego
            curve = self._char_curve(mem, rec) if mem is not None else None
            if curve is None:
                self._exp_note = (f'{self.curve_note}; no cuadra con {NAMES.get(rec["id"], rec["id"])} '
                                  f'(Nv {level}, {fmt(exp)} EXP)')
                return f'Nv {level}'
        nxt = curve.next(level, exp)
        return f'Nv {level} · Sig. {fmt(nxt)}' if nxt else f'Nv {level} · Máx.'

    @staticmethod
    def _parse_party(raw):
        ids = []
        for cid in struct.unpack('<4H', raw):
            if cid not in NAMES or cid in ids:
                break
            ids.append(cid)
        return ids if len(ids) >= 2 else None    # con ceros (lista vacía) solo saldría Estelle

    def _active_party(self, mem):
        """IDs del grupo activo, o None si no cuadra.

        La lista de +0x5145C se actualiza al cargar la partida; el juego guarda otras copias y
        alguna cambia en cuanto se cambia el grupo en el menú. Se vigilan todas las copias del
        grupo actual y se usa la última que cambió a una lista válida."""
        try:
            ids = self._parse_party(mem.read(self.block + self._party_off, 8))
        except MemoryReadError:
            return None
        if ids and not self._watch:
            pattern = re.escape(struct.pack(f'<{len(ids)}H', *ids))
            for pos in range(0, SCAN_SIZE, 1 << 20):
                try:
                    data = mem.read(self.block + pos, min((1 << 20) + 8, SCAN_SIZE - pos))
                except MemoryReadError:
                    continue
                for m in re.finditer(pattern, data, re.DOTALL):
                    if m.start() % 2 == 0 and m.start() < 1 << 20 and len(self._watch) < 16:
                        off = pos + m.start()
                        self._watch[off] = data[m.start():m.start() + 8]
            print('[trails2] copias de la lista del grupo: '
                  + ', '.join(f'bloque+0x{o:X}' for o in self._watch), flush=True)
        for off, old in self._watch.items():
            try:
                raw = mem.read(self.block + off, 8)
            except MemoryReadError:
                continue
            if raw != old:
                self._watch[off] = raw
                new = self._parse_party(raw)
                if new:
                    self._party_off, ids = off, new
                    print(f'[trails2] grupo cambiado en bloque+0x{off:X}: '
                          + ', '.join(NAMES.get(c, str(c)) for c in new), flush=True)
        return ids

    def _record_of(self, mem, ids):
        """{ID: dirección} para esos personajes: de la serie o, si no están, buscándolos por ID
        en todo el bloque (con la EXP validada por la fórmula). Las búsquedas se espacian."""
        found = {cid: self.records[cid] for cid in ids if cid in self.records}
        found.update({cid: self._by_id[cid][0] for cid in ids if cid in self._by_id and cid not in found})
        missing = [cid for cid in ids if cid not in found]
        now = time.monotonic()
        if missing and now >= self._next_id_scan:
            self._next_id_scan = now + RESCAN_EVERY
            fits = self.curve.near if self.curve else (lambda level, exp: True)
            hits = roster.by_id(mem, self.block, SCAN_SIZE, missing, fits)
            self._by_id.update(hits)
            for cid in missing:
                where = ', '.join(f'bloque+0x{a - self.block:X}' for a in hits.get(cid, [])) or 'no encontrado'
                print(f'[trails2] registro de {NAMES.get(cid, cid)} por ID: {where}', flush=True)
                if hits.get(cid):
                    found[cid] = hits[cid][0]
        return found

    def _party(self, mem, values, run):
        first, stride, n = run
        active = self._active_party(mem)
        addrs = self._record_of(mem, active) if active else {}
        if active and len(addrs) >= 2:
            members = [addrs[cid] for cid in active if cid in addrs]
            self._party_src = f'lista del juego (bloque+0x{self._party_off:X})'
        else:
            active = None
            members = [first + k * stride for k in range(min(n, 4))]
            self._party_src = 'sin lista del grupo: primeros registros encontrados'
        for slot, addr in enumerate(members, 1):
            rec = roster.read_record(mem, addr)
            values[f'p{slot}_name'] = NAMES.get(rec['id'], f'ID {rec["id"]}')
            values[f'p{slot}_img'] = self.portraits.url(rec['id'], PORTRAITS.get(rec['id'], ()))
            values[f'p{slot}_lv'] = self._level_text(rec, mem)
            for key in ('hp', 'hp_max', 'ep', 'ep_max', 'cp', 'cp_max'):
                values[f'p{slot}_{key}'] = rec[key]
        listing = ', '.join(f'{NAMES.get(cid, cid)}' for cid in sorted(self.records))
        values['dbg_roster'] = f'{self._scan_note}: {listing}'
        values['dbg_exp'] = self._exp_note
        if self._party_scan is None:   # una vez por partida: personajes (y lista del grupo si falta)
            print(f'[trails2] personajes: {self._scan_note}; grupo: {self._party_src}', flush=True)
            for cid, addr in sorted(self.records.items(), key=lambda kv: kv[1]):
                r = roster.read_record(mem, addr)
                print(f'[trails2]   bloque+0x{addr - self.block:X} ID {cid} {NAMES.get(cid, "?")} '
                      f'Nv {r["level"]} EXP {r["exp"]} HP {r["hp"]}/{r["hp_max"]} '
                      f'EP {r["ep"]}/{r["ep_max"]} CP {r["cp"]}/{r["cp_max"]}', flush=True)
            for k in range(-6, n + 2):     # la rejilla en bruto: por qué un registro no pasa
                a = first + k * stride
                try:
                    words = struct.unpack('<18I', mem.read(a, 0x48))
                    print(f'[trails2]   rejilla bloque+0x{a - self.block:X}: '
                          + ' '.join(f'{x:X}' for x in words), flush=True)
                except (MemoryReadError, struct.error):
                    pass
            pending = [] if active else list(party.LAYOUTS)   # el diagnóstico solo si no hay lista
            self._party_scan = (pending, set(NAMES) | set(self.records), [])
            self._party_note = 'buscando…' if pending else self._party_src
        layouts, ids, hits = self._party_scan
        if layouts:                     # una forma de lista por lectura: ninguna se alarga
            hits += party.candidates(mem, self.block, SCAN_SIZE, ids, [layouts.pop(0)])
            if not layouts:
                self._party_note = party.describe(hits, self.block, NAMES)
                for line in party.describe(hits, self.block, NAMES, limit=1000).split(' | '):
                    print(f'[trails2] grupo? {line}', flush=True)
        values['dbg_party'] = self._party_note

    def read(self, mem):
        values = {'build': self.build,
                  'dbg_sig': f'bloque {"ok" if self.state_ptr else "no"}; offset del tiempo '
                             f'0x{self.play_off:X} ({self.play_src})'}
        if self.error:
            values['status'] = f'{self.error}: ¿versión distinta del juego? (ver README del plugin)'
            return values
        block = mem.ptr(self.state_ptr)
        if not block:
            values['status'] = 'Esperando a que el juego cree sus datos'
            return values
        if block != self.block:
            self.block, self.run, self._next_scan, self._party_scan = block, None, 0.0, None
            self._by_id, self._next_id_scan = {}, 0.0
            self._party_off, self._watch = PARTY_LIST, {}
        *sepith, mira, _, played = MONEY.unpack(mem.read(block + self.play_off - 0x28, MONEY.size))
        if not (math.isfinite(played) and 0 <= played < 1e8) or mira > 999_999_999:
            values['status'] = 'Los datos no cuadran: ¿versión distinta del juego?'
            return values
        if played == 0 and mira == 0 and not any(sepith):
            values['status'] = 'Esperando a que cargues una partida'
            return values
        values['mira'] = mira
        values['playtime'] = playtime_text(played)
        try:
            run = self._roster(mem, block)
        except MemoryReadError as ex:
            run, self._scan_note = None, f'error buscando personajes: {ex}'
        if run:
            if not self._lookups_dumped and self.curve:   # con partida cargada: ya hay datos
                self._lookups_dumped = True
                self._dump_lookups(mem, self.exp_func)
            self._party(mem, values, run)
            values['status'] = 'Lectura OK'
        else:
            values['dbg_roster'] = self._scan_note
            values['status'] = 'Mira y tiempo de juego OK; personajes aún no encontrados'
        return values
