"""Trails in the Sky 2nd Chapter (2026) — motor propio de Falcom, vía Proton.

Solo lectura. Firmas y offsets de la tabla sora_2nd-v2.CT (Tuuuup!, sora_2nd.exe 1.0.0.0):

  Bloque de estado:  firma "Mira + Sepith and Play time": mov rXX,[rip+disp] -> puntero
                     al bloque. Tiempo de juego (double) en +0x20B650, Mira (u32) en
                     +0x20B648 (sepith justo antes: solo se usa para saber si hay partida).
  Tiempo de juego:   la firma "Set playtime to 0" es la instrucción que lo suma
                     (addsd xmm0,[rbx+0x20B650]); el offset se LEE de ahí, así que si
                     un parche lo mueve, Mira (relativa a él) lo sigue.
  Brave Gauge:       firma "max Brave Rush on hit": el código que la limita hace
                       rdx = [[[exe+G1]+A]+B];  valor = u32 [rdx+C]
                       tope = 700 si byte [[exe+G2]+F] & 4, 600 si & 2, si no 500
                     (G1, A, G2, B, F y C se leen de esas mismas instrucciones).

Verificado en el juego (1.03.1): Mira y tiempo de juego. Los personajes se probaron y se
descartaron: el juego no guarda el grupo activo en un sitio fiable (ver historial de git).
Bracer Points: la tabla solo da el BP de cada misión (por inyección, con la pantalla de
rango abierta); no hay total ni rango que leer, así que no se muestran.
"""
import math
import struct

from server.plugin_api import Field, GamePlugin, MemoryReadError, pe_info

from .scan import SignatureError, find, find_one, rip_target

MODULE = 'sora_2nd.exe'
AOB_STATE = '488B??????????0FB6??????????488B??????????488B????F3'
AOB_PLAYTIME = 'F2??????????????F2??????????????0F57??F3'
CT_PLAYTIME = 0x20B650           # si falta la firma del tiempo de juego, el de la tabla
MONEY = struct.Struct('<8IIId')  # sepith x8, Mira, (relleno), tiempo de juego: desde tiempo - 0x28
# Brave Gauge (exe+DB5FA en la 1.0.0.0): seis instrucciones seguidas, con sus offsets
AOB_BRAVE = ('48 8B 05 ?? ?? ?? ??  48 8B 88 ?? ?? ?? ??  48 8B 05 ?? ?? ?? ??  48 8B 91 ?? ?? ?? ?? '
             '44 0F B6 80 ?? ?? ?? ??  44 8B 4A ??  41 8D 0C 19')
BRAVE_CAPS = (700, 600, 500)     # bit 4, bit 2, ninguno (mov eax,2BC / 258 / 1F4)


def fmt(n):
    return f'{n:,}'.replace(',', '.')


def playtime_text(seconds):
    total = int(seconds)
    return f'{total // 3600} h {total % 3600 // 60:02d} min'


class Plugin(GamePlugin):
    id = 'trails2'
    name = 'Trails in the Sky 2nd Chapter'
    process_names = (MODULE,)
    poll_hz = 4
    fields = [
        Field('brave', 'Brave', kind='gear', max_key='brave_max', tone='limit', section='stats'),
        Field('mira', 'Mira', tone='gold', section='stats'),
        Field('playtime', 'Tiempo de juego', kind='text', section='stats'),
        Field('status', 'Estado', kind='text', section='info'),
        Field('build', 'Ejecutable', kind='text', section='info'),
        Field('dbg_sig', 'Diag. firmas', kind='text', section='info'),
        Field('dbg_brave', 'Diag. Brave', kind='text', section='info'),
    ]

    def on_attach(self, mem, proc):
        self.base = mem.module_base(MODULE)
        pe = pe_info(mem, self.base)
        self.build = f'{MODULE} · PE {pe["timestamp"]:08X} · {fmt(pe["image_size"])} bytes'
        self.error = None
        self.state_ptr = None
        self.play_off, self.play_src = CT_PLAYTIME, 'de la tabla (firma no encontrada)'
        try:
            insn = find_one(mem, self.base, AOB_STATE, 'Mira')
            if mem.u8(insn + 2) & 0xC7 != 0x05:
                raise SignatureError('firma de Mira: la instrucción no es [rip+disp]')
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
        self.brave = None
        self.brave_note = ''
        try:
            hits = find(mem, self.base, AOB_BRAVE)
            if len(hits) != 1:
                raise SignatureError(f'firma de Brave {"no encontrada" if not hits else "ambigua"}')
            at = hits[0]
            self.brave = {
                'g1': rip_target(mem, at, 3, 7), 'a': mem.u32(at + 10),
                'g2': rip_target(mem, at + 14, 3, 7), 'b': mem.u32(at + 24),
                'flags': mem.u32(at + 32), 'off': mem.u8(at + 39),
            }
            b = self.brave
            self.brave_note = (f'[[[exe+0x{b["g1"] - self.base:X}]+0x{b["a"]:X}]+0x{b["b"]:X}]+0x{b["off"]:X}, '
                               f'tope por [[exe+0x{b["g2"] - self.base:X}]+0x{b["flags"]:X}]')
        except SignatureError as ex:
            self.brave_note = str(ex)

    def _brave(self, mem):
        """(valor, tope) de la Brave Gauge, o None si aún no existe (p. ej. en el título)."""
        b = self.brave
        try:
            rdx = mem.ptr(mem.ptr(mem.ptr(b['g1']) + b['a']) + b['b'])
            if not rdx:
                return None
            value = mem.u32(rdx + b['off'])
            bits = mem.u8(mem.ptr(b['g2']) + b['flags'])
        except MemoryReadError:
            return None
        cap = BRAVE_CAPS[0] if bits & 4 else BRAVE_CAPS[1] if bits & 2 else BRAVE_CAPS[2]
        if value > cap:
            return None
        return value, cap

    def read(self, mem):
        values = {'build': self.build, 'dbg_brave': self.brave_note,
                  'dbg_sig': f'bloque {"ok" if self.state_ptr else "no"}; offset del tiempo '
                             f'0x{self.play_off:X} ({self.play_src})'}
        if self.error:
            values['status'] = f'{self.error}: ¿versión distinta del juego? (ver README del plugin)'
            return values
        block = mem.ptr(self.state_ptr)
        if not block:
            values['status'] = 'Esperando a que el juego cree sus datos'
            return values
        *sepith, mira, _, played = MONEY.unpack(mem.read(block + self.play_off - 0x28, MONEY.size))
        if not (math.isfinite(played) and 0 <= played < 1e8) or mira > 999_999_999:
            values['status'] = 'Los datos no cuadran: ¿versión distinta del juego?'
            return values
        if played == 0 and mira == 0 and not any(sepith):
            values['status'] = 'Esperando a que cargues una partida'
            return values
        values['mira'] = mira
        values['playtime'] = playtime_text(played)
        brave = self._brave(mem) if self.brave else None
        if brave:
            value, cap = brave
            values['brave'], values['brave_max'] = value // 100, cap // 100   # el juego muestra centenas
            values['dbg_brave'] = f'{self.brave_note}: {value}/{cap}'
        values['status'] = 'Lectura OK'
        return values
