"""FINAL FANTASY RESONANCE (Steam, build 24250053) — Unreal Engine 5, vía Proton.

Solo lectura. Las rutas vienen de la tabla FFRS_Steam_24250053_Starter.CT
(shawnjohnjr/ff-RESONANCE-ct), probada por su autor en esta build:

  Limit:    parámetro de la unidad +0x118, tope +0x2A0                  (script 15)
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

HP y MP (la tabla no los lee; verificado con launcher.log del juego real):
  - NO son UPROPERTY: CPP_UnitParameter solo refleja 4 campos.
  - Actual: CPP_UnitParameter / CPP_BtlUnitParameter +0x10C (HP) y +0x110 (MP). La tabla
    usa +0x10C > 0 como "puede actuar"; ambos coincidieron con CurrentPoint del ViewModel.
  - Máximo: ViewModel de la interfaz CPP_VM_UnitParam (uno por UnitId) -> HitPointVM /
    MagicPointVM -> MaxPoint. Offsets resueltos por NOMBRE con la reflexión
    (UnitId, HitPointVM, MagicPointVM, CurrentPoint, MaxPoint).
  - Fuera de batalla: la tabla llama a una función nativa (0x523D360) para obtener el
    CPP_UnitParameter vivo; un lector no puede llamar funciones, así que se escanean los
    objetos y se usa uno solo si es el único con ese ID en +0xD0 (lo mismo con los ViewModels).

Retratos: imágenes del propio usuario en ~/.local/share/gamepad/portraits/ffrs/
(ver server/portraits.py). No se incluye arte del juego.

La EXP para el siguiente nivel se deriva de las curvas; compárala con el menú.
"""
import collections
import time

from server.memory import MemoryReadError
from server import portraits
from server.plugins import Field, GamePlugin
from server.ue import OBJ_CLASS, OBJ_OUTER, UEReader, pe_info

MODULE = 'FFRS-Win64-Shipping.exe'
BUILD = {'timestamp': 0x6A586B2F, 'image_size': 503013376}     # build 24250053
UE_RVA = {'gnames_rva': 0x9CA1280, 'gobjects_rva': 0x9D84DD0, 'gworld_rva': 0x9AA0540}

WORLD_GAME_INSTANCE = 0x228
MANAGER_SAVE = 0x60
SAVE_GIL, SAVE_UNITS, SAVE_PARTY = 0x28, 0x60, 0x90
UNIT_STRIDE, UNIT_EXP = 0xA0, 0x04
WORLD_SUBSYSTEMS = 0x930
BTL_UNIT_MANAGER, UNITS_ARRAY, UNIT_PARAMETER, PARAM_CHAR_ID = 0x48, 0x28, 0x838, 0xD0
PARAM_HP, PARAM_MP = 0x10C, 0x110         # actual, en CPP_UnitParameter y CPP_BtlUnitParameter
PARAM_LIMIT, PARAM_LIMIT_MAX = 0x118, 0x2A0   # tabla CT (script 15); en el juego real: 0 y 100
VM_CLASS = 'CPP_VM_UnitParam'             # ViewModel de la interfaz: da el máximo
VM_NAMES = ('UnitId', 'HitPointVM', 'MagicPointVM')
POINT_NAMES = ('CurrentPoint', 'MaxPoint')

NAMES = {1001: 'Rain', 1002: 'Lasswell', 1003: 'Fina', 1004: 'Lid',
         1005: 'Nichol', 1006: 'Archwitch Fina', 1007: 'Jake', 1008: 'Sakura'}
# Nombres de archivo de retrato aceptados además de <id>.png (los del script de recortes)
PORTRAIT_NAMES = {1001: ('rain',), 1002: ('lasswell',), 1003: ('fina',), 1004: ('lid',),
                  1005: ('nichol',), 1006: ('archwitch_fina', 'dark_fina'), 1007: ('jake',),
                  1008: ('sakura',)}

RESCAN_EVERY = 10.0         # s; solo mientras no hay partida (en el título)
PARAM_RESCAN_EVERY = 15.0   # s; CPP_UnitParameter / ViewModels, si falta el de algún miembro
CURVE_RETRY_EVERY = 30.0    # s; curvas de nivel, si aún no se pudieron leer


def _party_fields():
    fields = []
    for n in range(1, 5):
        fields += [
            Field(f'p{n}_name', f'Miembro {n}', kind='text', section='party', slot=n),
            Field(f'p{n}_img', 'Retrato', kind='image', section='party', slot=n),
            Field(f'p{n}_lv', 'Nivel', kind='text', section='party', slot=n),
            Field(f'p{n}_hp', 'HP', kind='bar', max_key=f'p{n}_hp_max', tone='hp', section='party', slot=n),
            Field(f'p{n}_mp', 'MP', kind='bar', max_key=f'p{n}_mp_max', tone='mp', section='party', slot=n),
            Field(f'p{n}_lb', 'Limit', kind='bar', max_key=f'p{n}_lb_max', tone='limit', section='party', slot=n),
        ]
    return fields


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
        Field('dbg_battle', 'Diag. batalla', kind='text', section='info'),
        Field('dbg_curves', 'Diag. curvas', kind='text', section='info'),
        Field('dbg_hpmp', 'Diag. HP/MP', kind='text', section='info'),
    ]

    # --- enganche ---
    def on_attach(self, mem, proc):
        self.base = mem.module_base(MODULE)
        pe = pe_info(mem, self.base)
        self.build_ok = pe == BUILD
        self.build = f"0x{pe['timestamp']:08X} / {pe['image_size']}" + ('' if self.build_ok else ' (build distinta)')
        self.ue = UEReader(mem, self.base, **UE_RVA) if self.build_ok else None
        self.manager = None
        self.curves = {}             # {id de personaje: [EXP acumulada para nivel 1..99]}
        self.curves_diag = 'sin leer'
        self.next_curve_try = 0.0
        self.battle_diag = ''
        self.logged_subsystems = False
        self.dumped = set()          # clases cuya reflexión ya se escribió en launcher.log
        self.census_done = False
        self.next_scan = 0.0
        self.field_params = {}       # {id de personaje: CPP_UnitParameter} fuera de batalla
        self.vms = {}                # {id de personaje: CPP_VM_UnitParam}
        self.vm_off = None           # offsets de VM_NAMES + POINT_NAMES, por reflexión
        self.vm_error_logged = False
        self.next_param_scan = 0.0
        self.hp_source = 'esperando datos'
        self.portraits = portraits.Finder(self.id)
        print(f'[ffrs] PID {proc.pid}, base 0x{self.base:x}, build {self.build}', flush=True)

    # --- partida y tablas ---
    def _find_save(self, world):
        gi = self.ue.mem.ptr(world + WORLD_GAME_INSTANCE)
        t0 = time.monotonic()
        found = self.ue.scan({'CPP_MuchaSaveDataManager', 'DataTable', 'CPP_UnitParameter', VM_CLASS})
        managers = [m for m in found['CPP_MuchaSaveDataManager'] if self.ue.mem.ptr(m + OBJ_OUTER) == gi]
        print(f'[ffrs] escaneo: {self.ue.object_count()} objetos en {time.monotonic() - t0:.1f} s, '
              f'{len(managers)} gestor(es) de partida', flush=True)
        if len(managers) != 1:
            return None
        if not self.census_done:
            self.census_done = True
            self._census(found['DataTable'])
        self._set_field_params(found['CPP_UnitParameter'])
        self._set_vms(found[VM_CLASS])
        self.next_param_scan = time.monotonic() + PARAM_RESCAN_EVERY
        self._try_curves(found['DataTable'])
        return managers[0]

    # --- diagnóstico para launcher.log (una vez por partida) ---
    CENSUS_KEYS = ('Param', 'Btl', 'Unit', 'Party', 'Chara', 'Status')

    def _census(self, tables):
        """Qué clases y qué tablas hay de verdad: sirve para corregir rutas sin adivinar."""
        t0 = time.monotonic()
        counts = collections.Counter(name for _, name in self.ue.objects()
                                     if any(k in name for k in self.CENSUS_KEYS))
        print(f'[ffrs] censo de clases ({time.monotonic() - t0:.1f} s), las que contienen '
              f'{"/".join(self.CENSUS_KEYS)}:', flush=True)
        for name, n in sorted(counts.items()):
            print(f'  {n:6d}  {name}', flush=True)
        structs = collections.Counter()
        for t in tables:
            try:
                structs[self.ue.object_name(self.ue.mem.ptr(t + 0x28))] += 1
            except MemoryReadError:
                structs['?'] += 1
        print(f'[ffrs] DataTable por RowStruct ({len(tables)} tablas):', flush=True)
        for name, n in sorted(structs.items()):
            print(f'  {n:6d}  {name}', flush=True)

    def _dump_class(self, obj, why):
        """Escribe una vez en el log las propiedades (nombre, tipo, offset) de la clase de obj."""
        try:
            cls = self.ue.mem.ptr(obj + OBJ_CLASS)
            if cls in self.dumped:
                return
            self.dumped.add(cls)
            props = self.ue.properties(cls)
            print(f'[ffrs] propiedades de {self.ue.object_name(cls)} ({why}):', flush=True)
            for name, ftype, offset, owner in props:
                print(f'  {name:40s} {ftype:20s} 0x{offset:X}  {owner}', flush=True)
        except MemoryReadError as ex:
            print(f'[ffrs] no se pudo volcar la clase ({why}): {ex}', flush=True)

    def _describe_ptr(self, ptr):
        if not ptr:
            return 'nulo'
        try:
            return f'0x{ptr:X} ({self.ue.class_name(ptr)}{"" if self.ue.live(ptr) else ", no vivo"})'
        except MemoryReadError:
            return f'0x{ptr:X} (ilegible)'

    def _try_curves(self, tables=None):
        """Carga las curvas; si faltan, se reintenta más tarde (las tablas pueden cargarse después)."""
        self.next_curve_try = time.monotonic() + CURVE_RETRY_EVERY
        try:
            if tables is None:
                tables = self.ue.scan({'DataTable'})['DataTable']
            self.curves = self._load_curves(tables)
        except MemoryReadError as ex:
            self.curves_diag = f'error: {ex}'
            print(f'[ffrs] no se pudieron leer las curvas de nivel: {ex!r}', flush=True)

    def _merged_rows(self, by_struct, struct, key_off, read_value):
        """{clave: valor} juntando TODAS las tablas con ese RowStruct (puede haber varias,
        p. ej. una de enemigos). Una clave con valores distintos en dos tablas se descarta."""
        out, conflict, rows = {}, set(), 0
        for table in by_struct.get(struct, ()):
            try:
                entries = self.ue.table_rows(table, struct)
            except MemoryReadError:
                continue
            for _, row in entries:
                key, value = self.ue.mem.i32(row + key_off), read_value(row)
                rows += 1
                if key in out and out[key] != value:
                    conflict.add(key)
                out.setdefault(key, value)
        for key in conflict:
            del out[key]
        print(f'[ffrs] {struct}: {len(by_struct.get(struct, ()))} tabla(s), {rows} filas'
              + (f', claves en conflicto {sorted(conflict)[:10]}' if conflict else ''), flush=True)
        return out

    def _load_curves(self, tables):
        ue, mem = self.ue, self.ue.mem
        by_struct = {}
        for t in tables:
            try:
                by_struct.setdefault(ue.object_name(mem.ptr(t + 0x28)), []).append(t)
            except MemoryReadError:
                continue
        definitions = self._merged_rows(by_struct, 'UNIT_PARAMETER', 8, lambda r: mem.i32(r + 0x3C))
        if definitions:
            sample = sorted(definitions)[:12]
            print(f'[ffrs] UNIT_PARAMETER: IDs de ejemplo (+8) {sample}', flush=True)
        lists = self._merged_rows(by_struct, 'UNIT_LEVEL_PARAMETER_LIST', 8, lambda r: mem.ptr(r + 0x10))
        curves, missing = {}, []
        for char_id in NAMES:
            try:
                per_level = {}
                for _, row in ue.table_rows(lists[definitions[char_id]], 'UNIT_LEVEL_PARAMETER'):
                    per_level[mem.i32(row + 8)] = mem.i32(row + 12)
                total, cumulative = 0, []
                for lv in range(1, 100):
                    total += per_level[lv]
                    cumulative.append(total)   # EXP total para alcanzar el nivel lv
                curves[char_id] = cumulative
            except (MemoryReadError, KeyError) as ex:
                step = ('sin fila en UNIT_PARAMETER' if char_id not in definitions else
                        f'curva {definitions[char_id]} sin lista' if definitions[char_id] not in lists else repr(ex))
                missing.append(f'{char_id}: {step}')
                print(f'[ffrs] sin curva de nivel para {NAMES[char_id]} ({char_id}): {step}', flush=True)
        print(f'[ffrs] curvas de nivel cargadas: {sorted(curves)}', flush=True)
        self.curves_diag = (f'{len(curves)}/{len(NAMES)} personajes; tablas UNIT_PARAMETER '
                            f'{len(by_struct.get("UNIT_PARAMETER", ()))} ({len(definitions)} IDs)'
                            + (f'; falta {missing[0]}' + (f' (+{len(missing) - 1})' if len(missing) > 1 else '')
                               if missing else ''))
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
        """[(id, CPP_BtlUnitParameter)] en orden de batalla, o None. Deja en battle_diag
        en qué paso de la cadena se cortó, para el panel de debug."""
        ue, mem = self.ue, self.ue.mem
        entries = ue.sparse_entries(world + WORLD_SUBSYSTEMS, 24, 256)
        manager, classes = None, []
        for entry in entries:
            obj = mem.ptr(entry + 8)
            try:
                classes.append(ue.class_name(obj))
            except MemoryReadError:
                classes.append('?')
                continue
            if ue.live(obj) and ue.isa(obj, 'CPP_BtlManager') and mem.ptr(obj + OBJ_OUTER) == world:
                manager = obj
                break
        if not self.logged_subsystems:
            self.logged_subsystems = True
            print(f'[ffrs] subsistemas del World ({len(entries)}): {", ".join(classes)}', flush=True)
        if manager is None:
            self.battle_diag = f'sin CPP_BtlManager entre {len(entries)} subsistemas'
            return None
        self._dump_class(manager, 'gestor de batalla')
        units = mem.ptr(manager + BTL_UNIT_MANAGER)
        if not ue.live(units) or not ue.isa(units, 'CPP_BtlUnitManager'):
            self.battle_diag = f'CPP_BtlManager +0x48 = {self._describe_ptr(units)}, no es CPP_BtlUnitManager'
            return None
        self._dump_class(units, 'gestor de unidades')
        data, n = self._array(units + UNITS_ARRAY, 128)
        members, actors, params, ids = [], 0, 0, []
        for i in range(n):
            actor = mem.ptr(data + i * 8)
            if not ue.live(actor) or not ue.isa(actor, 'CPP_BtlUnit'):
                continue
            actors += 1
            self._dump_class(actor, 'unidad de batalla')
            param = mem.ptr(actor + UNIT_PARAMETER)
            if not ue.live(param) or not ue.isa(param, 'CPP_BtlUnitParameter'):
                continue
            params += 1
            char_id = mem.i32(param + PARAM_CHAR_ID)
            ids.append(char_id)
            if char_id in NAMES and all(m[0] != char_id for m in members):
                members.append((char_id, param))
        self.battle_diag = (f'{n} unidades, {actors} CPP_BtlUnit, {params} con parámetros, '
                            f'{len(members)} aliados; IDs {ids[:8]}')
        return members

    # --- fuera de batalla (experimental) ---
    def _set_field_params(self, objects):
        by_id = {}
        for obj in objects:
            try:
                by_id.setdefault(self.ue.mem.i32(obj + PARAM_CHAR_ID), []).append(obj)
            except MemoryReadError:
                continue
        # Solo IDs con un único objeto: si hay varios no sabemos cuál es el vivo
        self.field_params = {cid: objs[0] for cid, objs in by_id.items() if cid in NAMES and len(objs) == 1}
        dup = sorted(cid for cid, objs in by_id.items() if cid in NAMES and len(objs) > 1)
        print(f'[ffrs] CPP_UnitParameter: {len(objects)} objetos; únicos {sorted(self.field_params)}'
              + (f'; ambiguos {dup}' if dup else ''), flush=True)

    def _field_param(self, char_id):
        """CPP_UnitParameter de un personaje si sigue vivo y su ID no cambió."""
        obj = self.field_params.get(char_id)
        if obj is not None:
            try:
                if self.ue.live(obj) and self.ue.mem.i32(obj + PARAM_CHAR_ID) == char_id:
                    return obj
            except MemoryReadError:
                pass
            del self.field_params[char_id]
        return None

    def _refresh_objects(self, roster_ids):
        """Reescanea (con límite de frecuencia) si falta el parámetro o el ViewModel de algún miembro."""
        complete = all(self._field_param(cid) and self._vm(cid) for cid in roster_ids)
        if complete or time.monotonic() < self.next_param_scan:
            return
        self.next_param_scan = time.monotonic() + PARAM_RESCAN_EVERY
        t0 = time.monotonic()
        found = self.ue.scan({'CPP_UnitParameter', VM_CLASS})
        self._set_field_params(found['CPP_UnitParameter'])
        self._set_vms(found[VM_CLASS])
        print(f'[ffrs] reescaneo de parámetros y ViewModels en {time.monotonic() - t0:.1f} s', flush=True)

    # --- máximo de HP/MP: ViewModel de la interfaz ---
    def _resolve_vm_offsets(self, vm):
        """(UnitId, HitPointVM, MagicPointVM, CurrentPoint, MaxPoint) por nombre, o None."""
        if self.vm_off:
            return self.vm_off
        ue, mem = self.ue, self.ue.mem
        try:
            names = {n: off for n, _, off, _ in ue.properties(mem.ptr(vm + OBJ_CLASS))}
            point = mem.ptr(vm + names['HitPointVM'])
            if not point:
                return None   # aún sin crear: se reintenta
            pnames = {n: off for n, _, off, _ in ue.properties(mem.ptr(point + OBJ_CLASS))}
            self.vm_off = tuple(names[n] for n in VM_NAMES) + tuple(pnames[n] for n in POINT_NAMES)
            print(f'[ffrs] ViewModel: ' + ', '.join(f'{n}@0x{o:X}' for n, o in zip(VM_NAMES + POINT_NAMES, self.vm_off)),
                  flush=True)
        except (MemoryReadError, KeyError) as ex:
            if not self.vm_error_logged:
                self.vm_error_logged = True
                print(f'[ffrs] no se pudo resolver el ViewModel por nombre: {ex!r}', flush=True)
            return None
        return self.vm_off

    def _set_vms(self, objects):
        by_id = {}
        for vm in objects:
            off = self._resolve_vm_offsets(vm)
            if not off:
                continue
            try:
                by_id.setdefault(self.ue.mem.i32(vm + off[0]), []).append(vm)
            except MemoryReadError:
                continue
        self.vms = {cid: objs[0] for cid, objs in by_id.items() if cid in NAMES and len(objs) == 1}
        if objects:
            print(f'[ffrs] {VM_CLASS}: {len(objects)} objetos; únicos {sorted(self.vms)}', flush=True)

    def _vm(self, char_id):
        vm = self.vms.get(char_id)
        if vm is not None:
            try:
                if self.ue.live(vm) and self.ue.mem.i32(vm + self.vm_off[0]) == char_id:
                    return vm
            except MemoryReadError:
                pass
            del self.vms[char_id]
        return None

    def _hp_mp(self, char_id, param):
        """{'hp','mp' (actual), 'hp_max','mp_max'} con lo que se pueda leer; nunca lanza.
        Devuelve también de dónde salió cada dato, para el panel de debug."""
        mem, out, src = self.ue.mem, {}, []
        try:
            if param is not None:
                out['hp'], out['mp'] = mem.i32(param + PARAM_HP), mem.i32(param + PARAM_MP)
                lb, lb_max = mem.i32(param + PARAM_LIMIT), mem.i32(param + PARAM_LIMIT_MAX)
                if 0 < lb_max <= 10000 and 0 <= lb <= lb_max:   # si no cuadra, no se muestra
                    out['lb'], out['lb_max'] = lb, lb_max
                src.append('actual de la unidad')
            vm = self._vm(char_id)
            if vm is not None:
                _, hp_vm, mp_vm, cur, mx = self.vm_off
                for key, off in (('hp', hp_vm), ('mp', mp_vm)):
                    point = mem.ptr(vm + off)
                    if point:
                        out[f'{key}_max'] = mem.i32(point + mx)
                        out.setdefault(key, mem.i32(point + cur))   # sin unidad: el actual de la interfaz
                src.append('máximo de la interfaz')
        except MemoryReadError as ex:
            src.append(f'error: {ex}')
        # nunca mostrar basura; un máximo de 0 es un ViewModel aún sin rellenar
        out = {k: v for k, v in out.items() if 0 <= v <= 999999 and not (k.endswith('_max') and v == 0)}
        return out, src

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
        if not self.curves and time.monotonic() >= self.next_curve_try:
            self._try_curves()
        units, un = self._array(save + SAVE_UNITS, 64)
        exp = {mem.i32(units + i * UNIT_STRIDE): mem.i32(units + i * UNIT_STRIDE + UNIT_EXP) for i in range(un)}
        party, pn = self._array(save + SAVE_PARTY, 8)
        roster = [(mem.i32(party + i * 4), None) for i in range(pn)]

        # Batalla: si hay, manda el orden y los HP/MP en vivo
        try:
            members = self._battle_members(world)
        except MemoryReadError as ex:
            members, self.battle_diag = None, f'error: {ex}'
        values['battle'] = f'en batalla ({len(members)})' if members else 'fuera de batalla'
        if members:
            roster = members
        else:
            self._refresh_objects([cid for cid, _ in roster[:4] if cid in NAMES])
            roster = [(cid, self._field_param(cid)) for cid, _ in roster]

        no_exp = [cid for cid, _ in roster[:4] if cid not in exp]
        diag, sources = [], set()
        for slot, (char_id, param) in enumerate(roster[:4], 1):
            values[f'p{slot}_name'] = NAMES.get(char_id, f'ID {char_id}')
            values[f'p{slot}_img'] = self.portraits.url(char_id, PORTRAIT_NAMES.get(char_id, ()))
            if char_id in exp:
                values[f'p{slot}_lv'] = self._level(char_id, exp[char_id])
            stats, src = self._hp_mp(char_id, param)
            for key, value in stats.items():
                values[f'p{slot}_{key}'] = value
            sources.update(src)
            diag.append(f"{NAMES.get(char_id, char_id)} HP {stats.get('hp', '—')}/{stats.get('hp_max', '—')}"
                        f" MP {stats.get('mp', '—')}/{stats.get('mp_max', '—')}"
                        f" LB {stats.get('lb', '—')}/{stats.get('lb_max', '—')}")
        values['hp_source'] = (' + '.join(sorted(sources)) if sources else 'sin objetos de HP/MP todavía') + (
            ' (batalla)' if members else ' (fuera de batalla)')
        values['dbg_hpmp'] = ' · '.join(diag)
        values['dbg_battle'] = self.battle_diag
        values['dbg_curves'] = self.curves_diag + (f'; sin EXP en la partida para {no_exp}' if no_exp else '')
        values['status'] = 'Lectura OK'
        return values
