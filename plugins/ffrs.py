"""FINAL FANTASY RESONANCE (Steam, build 24250053) — Unreal Engine 5, vía Proton.

Solo lectura. Las rutas vienen de la tabla FFRS_Steam_24250053_Starter.CT
(shawnjohnjr/ff-RESONANCE-ct), probada por su autor en esta build:

  Gil:      World +0x228 -> GameInstance
            objeto CPP_MuchaSaveDataManager cuyo outer (+0x20) es esa GameInstance
            +0x60 -> CPP_MuchaGameSaveData;  Gil = int32 en +0x28           (script 01)
  Equipo:   SaveData +0x90 = TArray<int32> de IDs (1001-1008)               (script 05)
  EXP:      SaveData +0x60 = TArray de unidades (0xA0 c/u): ID +0, EXP +4   (script 05)
            UNIT_PARAMETER: ID +8, curva +0x3C; UNIT_LEVEL_PARAMETER_LIST: curva +8,
            tabla +0x10; UNIT_LEVEL_PARAMETER: nivel +8, EXP de ese nivel +12
  Batalla:  World +0x930 (subsistemas) -> CPP_BtlManager (outer == World)
            +0x48 -> CPP_BtlUnitManager; +0x28 = TArray<CPP_BtlUnit*>
            unidad +0x838 -> CPP_BtlUnitParameter; ID de personaje +0xD0  (script 15)

HP y MP en batalla: la tabla no los lee. Se buscan por NOMBRE en la reflexión de
CPP_BtlUnitParameter (el juego usa nombres como "MaxHitPoint"). La reflexión se
autocomprueba: debe encontrar los offsets conocidos 0xD0 y 0x118 (Limit). La lista
completa de propiedades se escribe en launcher.log la primera vez.

La EXP para el siguiente nivel se deriva de las curvas; compárala con el menú.
"""
import re
import time

from server.memory import MemoryReadError
from server.plugins import Field, GamePlugin
from server.ue import OBJ_OUTER, UEReader, pe_info

MODULE = 'FFRS-Win64-Shipping.exe'
BUILD = {'timestamp': 0x6A586B2F, 'image_size': 503013376}     # build 24250053
UE_RVA = {'gnames_rva': 0x9CA1280, 'gobjects_rva': 0x9D84DD0, 'gworld_rva': 0x9AA0540}

WORLD_GAME_INSTANCE = 0x228
MANAGER_SAVE = 0x60
SAVE_GIL, SAVE_UNITS, SAVE_PARTY = 0x28, 0x60, 0x90
UNIT_STRIDE, UNIT_EXP = 0xA0, 0x04
WORLD_SUBSYSTEMS = 0x930
BTL_UNIT_MANAGER, UNITS_ARRAY, UNIT_PARAMETER, PARAM_CHAR_ID = 0x48, 0x28, 0x838, 0xD0
KNOWN_PARAM_OFFSETS = {0xD0, 0x118}                       # para validar la reflexión

NAMES = {1001: 'Rain', 1002: 'Lasswell', 1003: 'Fina', 1004: 'Lid',
         1005: 'Nichol', 1006: 'Fina oscura', 1007: 'Jake', 1008: 'Sakura'}

# Nombres normalizados (minúsculas, sin "m_" ni "_") que se aceptan para cada valor.
HP_MP_NAMES = {
    'hp': {'hitpoint', 'hp', 'currenthitpoint', 'nowhitpoint', 'currenthp', 'nowhp'},
    'hp_max': {'maxhitpoint', 'maxhp', 'hitpointmax', 'hpmax'},
    'mp': {'magicpoint', 'mp', 'currentmagicpoint', 'nowmagicpoint', 'currentmp', 'nowmp'},
    'mp_max': {'maxmagicpoint', 'maxmp', 'magicpointmax', 'mpmax'},
}
NUMERIC = {'IntProperty': 'i32', 'UInt32Property': 'u32', 'FloatProperty': 'f32',
           'Int64Property': 'i64', 'DoubleProperty': 'f64', 'Int16Property': 'i16'}
RESCAN_EVERY = 10.0   # s; solo mientras no hay partida (en el título)


def _party_fields():
    fields = []
    for n in range(1, 5):
        fields += [
            Field(f'p{n}_name', f'Miembro {n}', kind='text', section='party', slot=n),
            Field(f'p{n}_lv', 'Nivel', kind='text', section='party', slot=n),
            Field(f'p{n}_hp', 'HP', kind='bar', max_key=f'p{n}_hp_max', tone='hp', section='party', slot=n),
            Field(f'p{n}_mp', 'MP', kind='bar', max_key=f'p{n}_mp_max', tone='mp', section='party', slot=n),
        ]
    return fields


def _norm(name):
    return re.sub(r'^m_|_', '', name.lower())


class Plugin(GamePlugin):
    id = 'ffrs'
    name = 'Final Fantasy Resonance'
    process_names = (MODULE, MODULE[:15])    # comm del kernel: 15 caracteres
    poll_hz = 2
    fields = _party_fields() + [
        Field('gil', 'Gil', tone='gold', section='stats'),
        Field('status', 'Estado', kind='text', section='info'),
        Field('battle', 'Batalla', kind='text', section='header'),
        Field('hp_source', 'Origen HP/MP', kind='text', section='info'),
        Field('world', 'Mapa', kind='text', section='info'),
        Field('build', 'Ejecutable', kind='text', section='info'),
    ]

    # --- enganche ---
    def on_attach(self, mem, proc):
        self.base = mem.module_base(MODULE)
        pe = pe_info(mem, self.base)
        self.build_ok = pe == BUILD
        self.build = f"0x{pe['timestamp']:08X} / {pe['image_size']}" + ('' if self.build_ok else ' (build distinta)')
        self.ue = UEReader(mem, self.base, **UE_RVA) if self.build_ok else None
        self.manager = None
        self.curves = None           # {id de personaje: [EXP acumulada para nivel 1..99]}
        self.next_scan = 0.0
        self.hp_offsets = None       # {'hp': (offset, tipo), ...} resuelto por reflexión
        self.hp_source = 'esperando una batalla'
        print(f'[ffrs] PID {proc.pid}, base 0x{self.base:x}, build {self.build}', flush=True)

    # --- partida y tablas ---
    def _find_save(self, world):
        gi = self.ue.mem.ptr(world + WORLD_GAME_INSTANCE)
        t0 = time.monotonic()
        found = self.ue.scan({'CPP_MuchaSaveDataManager', 'DataTable'})
        managers = [m for m in found['CPP_MuchaSaveDataManager'] if self.ue.mem.ptr(m + OBJ_OUTER) == gi]
        print(f'[ffrs] escaneo: {self.ue.object_count()} objetos en {time.monotonic() - t0:.1f} s, '
              f'{len(managers)} gestor(es) de partida', flush=True)
        if len(managers) != 1:
            return None
        if self.curves is None:
            try:
                self.curves = self._load_curves(found['DataTable'])
            except (MemoryReadError, KeyError) as ex:
                self.curves = {}
                print(f'[ffrs] no se pudieron leer las curvas de nivel: {ex!r}', flush=True)
        return managers[0]

    def _load_curves(self, tables):
        ue = self.ue
        by_struct = {}
        for t in tables:
            try:
                by_struct.setdefault(ue.object_name(ue.mem.ptr(t + 0x28)), t)
            except MemoryReadError:
                continue
        definitions = {ue.mem.i32(row + 8): ue.mem.i32(row + 0x3C)
                       for _, row in ue.table_rows(by_struct['UNIT_PARAMETER'], 'UNIT_PARAMETER')}
        lists = {ue.mem.i32(row + 8): ue.mem.ptr(row + 0x10)
                 for _, row in ue.table_rows(by_struct['UNIT_LEVEL_PARAMETER_LIST'], 'UNIT_LEVEL_PARAMETER_LIST')}
        curves = {}
        for char_id in NAMES:
            try:
                per_level = {}
                for _, row in ue.table_rows(lists[definitions[char_id]], 'UNIT_LEVEL_PARAMETER'):
                    per_level[ue.mem.i32(row + 8)] = ue.mem.i32(row + 12)
                total, cumulative = 0, []
                for lv in range(1, 100):
                    total += per_level[lv]
                    cumulative.append(total)   # EXP total para alcanzar el nivel lv
                curves[char_id] = cumulative
            except (MemoryReadError, KeyError) as ex:
                print(f'[ffrs] sin curva de nivel para {NAMES[char_id]} ({char_id}): {ex!r}', flush=True)
        print(f'[ffrs] curvas de nivel cargadas: {sorted(curves)}', flush=True)
        return curves

    def _array(self, address, max_count):
        mem = self.ue.mem
        data, n, cap = mem.ptr(address), mem.i32(address + 8), mem.i32(address + 12)
        if not 0 <= n <= cap <= max_count or (n and not data):
            raise MemoryReadError('array inválido')
        return data, n

    def _level(self, char_id, exp):
        cumulative = self.curves.get(char_id) if self.curves else None
        if not cumulative:
            return None
        level = max([lv for lv, need in enumerate(cumulative, 1) if need <= exp], default=1)
        if level >= 99:
            return 'Nv 99 · máximo'
        missing = cumulative[level] - exp
        return f'Nv {level} · faltan {missing:,} EXP'.replace(',', '.')

    # --- batalla ---
    def _battle_members(self, world):
        ue, mem = self.ue, self.ue.mem
        manager = None
        for entry in ue.sparse_entries(world + WORLD_SUBSYSTEMS, 24, 256):
            obj = mem.ptr(entry + 8)
            if ue.live(obj) and ue.isa(obj, 'CPP_BtlManager') and mem.ptr(obj + OBJ_OUTER) == world:
                manager = obj
                break
        if manager is None:
            return None
        units = mem.ptr(manager + BTL_UNIT_MANAGER)
        if not ue.live(units) or not ue.isa(units, 'CPP_BtlUnitManager'):
            return None
        data, n = self._array(units + UNITS_ARRAY, 128)
        members = []
        for i in range(n):
            actor = mem.ptr(data + i * 8)
            if not ue.live(actor) or not ue.isa(actor, 'CPP_BtlUnit'):
                continue
            param = mem.ptr(actor + UNIT_PARAMETER)
            if not ue.live(param) or not ue.isa(param, 'CPP_BtlUnitParameter'):
                continue
            char_id = mem.i32(param + PARAM_CHAR_ID)
            if char_id in NAMES and all(m[0] != char_id for m in members):
                members.append((char_id, param))
        return members

    def _resolve_hp_offsets(self, param):
        props = self.ue.properties(self.ue.mem.ptr(param + 0x10))
        print('[ffrs] propiedades de CPP_BtlUnitParameter (nombre, tipo, offset, clase):', flush=True)
        for name, ftype, offset, owner in props:
            print(f'  {name:40s} {ftype:20s} 0x{offset:X}  {owner}', flush=True)
        if not KNOWN_PARAM_OFFSETS <= {p[2] for p in props}:
            self.hp_offsets = {}
            self.hp_source = 'reflexión no verificada (offsets 0xD0/0x118 ausentes); ver launcher.log'
            return
        chosen = {}
        for key, accepted in HP_MP_NAMES.items():
            hits = [(off, NUMERIC[t]) for name, t, off, _ in props if _norm(name) in accepted and t in NUMERIC]
            if len(hits) == 1:
                chosen[key] = hits[0]
        self.hp_offsets = chosen
        missing = sorted(set(HP_MP_NAMES) - set(chosen))
        found = ', '.join(f'{k}@0x{v[0]:X}' for k, v in sorted(chosen.items()))
        self.hp_source = f'por nombre: {found or "ninguno"}' + (f'; faltan {", ".join(missing)} (ver launcher.log)' if missing else '')

    def _hp_mp(self, param):
        if self.hp_offsets is None:
            self._resolve_hp_offsets(param)
        return {k: self.ue.mem.value(t, param + off) for k, (off, t) in self.hp_offsets.items()}

    # --- lectura periódica ---
    def read(self, mem):
        values = {'build': self.build, 'hp_source': self.hp_source}
        if not self.build_ok:
            values['status'] = 'Build distinta de la 24250053: no se lee nada para no mostrar datos falsos'
            return values
        world = self.ue.world()
        values['world'] = self.ue.object_name(world)

        # Partida: Gil, equipo y EXP
        if self.manager is None or not self.ue.live(self.manager):
            self.manager = None
            if time.monotonic() >= self.next_scan:
                self.next_scan = time.monotonic() + RESCAN_EVERY
                self.manager = self._find_save(world)
        if self.manager is None:
            values['status'] = 'Esperando a que cargues una partida'
            return values
        save = mem.ptr(self.manager + MANAGER_SAVE)
        if self.ue.class_name(save) != 'CPP_MuchaGameSaveData':
            raise MemoryReadError('la partida activa no está disponible')
        values['gil'] = mem.i32(save + SAVE_GIL)
        units, un = self._array(save + SAVE_UNITS, 64)
        exp = {mem.i32(units + i * UNIT_STRIDE): mem.i32(units + i * UNIT_STRIDE + UNIT_EXP) for i in range(un)}
        party, pn = self._array(save + SAVE_PARTY, 8)
        roster = [(mem.i32(party + i * 4), None) for i in range(pn)]

        # Batalla: si hay, manda el orden y los HP/MP en vivo
        try:
            members = self._battle_members(world)
        except MemoryReadError:
            members = None
        values['battle'] = f'en batalla ({len(members)})' if members else 'fuera de batalla'
        if members:
            roster = members

        for slot, (char_id, param) in enumerate(roster[:4], 1):
            values[f'p{slot}_name'] = NAMES.get(char_id, f'ID {char_id}')
            if char_id in exp:
                values[f'p{slot}_lv'] = self._level(char_id, exp[char_id])
            if param is not None:
                for key, value in self._hp_mp(param).items():
                    values[f'p{slot}_{key}'] = value
        values['hp_source'] = self.hp_source
        values['status'] = 'Lectura OK'
        return values
