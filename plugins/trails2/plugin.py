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

Sin verificar en el juego todavía: dónde están los registros de personaje y qué
miembros forman el grupo (se muestran los 4 primeros del array). Los diagnósticos
(Debug) dicen qué se encontró.
"""
import math
import struct
import time

from server.plugin_api import Field, GamePlugin, MemoryReadError, pe_info

from . import roster
from .scan import SignatureError, find_one, rip_target

MODULE = 'sora_2nd.exe'
AOB_STATE = '488B??????????0FB6??????????488B??????????488B????F3'
AOB_PLAYTIME = 'F2??????????????F2??????????????0F57??F3'
CT_PLAYTIME = 0x20B650           # si falta la firma del tiempo de juego, el de la tabla
MONEY = struct.Struct('<8IIId')  # sepith x8, Mira, (relleno), tiempo de juego: desde tiempo - 0x28
SCAN_SIZE = 0x700000             # el bloque llega al menos a +0x6247C0 (script del tiempo de juego)
RESCAN_EVERY = 10.0
SEPITH = ('Tierra', 'Agua', 'Fuego', 'Viento', 'Tiempo', 'Espacio', 'Espejismo', 'Masa')

# IDs 0-7: grupo principal (tabla); el orden de nombres es el de la saga, por confirmar.
NAMES = {0: 'Estelle', 1: 'Joshua', 2: 'Scherazard', 3: 'Olivier', 4: 'Kloe', 5: 'Agate',
         6: 'Tita', 7: 'Zin', 100: 'Kurt', 101: 'Anelace', 106: 'Josette',
         107: 'Schwarz', 112: 'Vander', 119: 'Kevin', 124: 'Dorothy'}


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
    fields = _party_fields() + [
        Field('mira', 'Mira', tone='gold', section='stats'),
        Field('playtime', 'Tiempo de juego', kind='text', section='stats'),
        Field('sepith', 'Sepith', kind='text', section='stats'),
        Field('status', 'Estado', kind='text', section='info'),
        Field('build', 'Ejecutable', kind='text', section='info'),
        Field('dbg_sig', 'Diag. firmas', kind='text', section='info'),
        Field('dbg_roster', 'Diag. personajes', kind='text', section='info'),
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
        self.block = None
        self.run = None              # (primer registro, separación, cuántos)
        self._next_scan = 0.0
        self._scan_note = 'sin buscar'

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
            self._scan_note = (f'{len(found)} candidatos; serie de {n} cada 0x{stride:X} '
                               f'desde bloque+0x{first - block:X} ({took:.1f} s)')
        else:
            self._scan_note = f'ningún registro en bloque+0..0x{SCAN_SIZE:X} ({took:.1f} s)'
        return self.run

    def _party(self, mem, values, run):
        first, stride, n = run
        seen = []
        for k in range(n):
            rec = roster.read_record(mem, first + k * stride)
            seen.append(rec)
            slot = k + 1
            if slot > 4:
                continue
            values[f'p{slot}_name'] = NAMES.get(rec['id'], f'ID {rec["id"]}')
            values[f'p{slot}_lv'] = f'Nv {rec["level"]} · {fmt(rec["exp"])} EXP'
            for key in ('hp', 'hp_max', 'ep', 'ep_max', 'cp', 'cp_max'):
                values[f'p{slot}_{key}'] = rec[key]
        listing = ', '.join(f'{NAMES.get(r["id"], r["id"])} Nv{r["level"]}' for r in seen[:16])
        values['dbg_roster'] = f'{self._scan_note}: {listing}'

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
            self.block, self.run, self._next_scan = block, None, 0.0
        *sepith, mira, _, played = MONEY.unpack(mem.read(block + self.play_off - 0x28, MONEY.size))
        if not (math.isfinite(played) and 0 <= played < 1e8) or mira > 999_999_999:
            values['status'] = 'Los datos no cuadran: ¿versión distinta del juego?'
            return values
        if played == 0 and mira == 0 and not any(sepith):
            values['status'] = 'Esperando a que cargues una partida'
            return values
        values['mira'] = mira
        values['playtime'] = playtime_text(played)
        values['sepith'] = ' · '.join(f'{name} {fmt(n)}' for name, n in zip(SEPITH, sepith))
        try:
            run = self._roster(mem, block)
        except MemoryReadError as ex:
            run, self._scan_note = None, f'error buscando personajes: {ex}'
        if run:
            self._party(mem, values, run)
            values['status'] = 'Lectura OK'
        else:
            values['dbg_roster'] = self._scan_note
            values['status'] = 'Mira y sepith OK; personajes aún no encontrados'
        return values
