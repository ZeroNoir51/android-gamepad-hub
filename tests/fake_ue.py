"""Memoria sintética con la disposición de UE5 de FINAL FANTASY RESONANCE (build 24250053).

Reproduce lo que leen plugins/ffrs/ue.py y plugins/ffrs/plugin.py, con los offsets de la tabla
FFRS_Steam_24250053_Starter.CT (ver docstrings de esos módulos). Sirve para probar
el lector y el plugin sin el juego: cada test arma un escenario con FakeGame y
lee con el plugin real.

Verificado con launcher.log del juego real (y reproducido aquí):
- reflexión de CPP_UnitParameter: solo PARAM_PROPS (HP/MP no son UPROPERTY);
- HP/MP actual en +0x10C/+0x110 del parámetro; máximo en el ViewModel CPP_VM_UnitParam
  (UnitId 0x68, HitPointVM 0x90, MagicPointVM 0x98) -> CPP_VM_Point (CurrentPoint 0xB8, MaxPoint 0xBC).
La disposición de la reflexión es configurable (FakeGame(layout=...)).
"""
import struct

from server.memory import LinuxProcessMemory, MemoryReadError, ProcInfo
from conftest import load_plugin

U = load_plugin('ffrs', 'ue')   # el lector de UE5 es parte del plugin

MODULE = 'FFRS-Win64-Shipping.exe'
BASE = 0x140000000
BUILD = {'timestamp': 0x6A586B2F, 'image_size': 503013376}
RVA = {'gnames_rva': 0x9CA1280, 'gobjects_rva': 0x9D84DD0, 'gworld_rva': 0x9AA0540}

RF_CLASS_DEFAULT = U.RF_CLASS_DEFAULT
RF_BEGIN_DESTROYED = 0x8000

# Propiedades reflejadas de verdad en el juego: (nombre, tipo, offset, clase dueña)
PARAM_PROPS = [
    ('m_ContEffectList', 'ArrayProperty', 0xB8, 'CPP_UnitParameter'),
    ('m_ActiveSkillTargets', 'ArrayProperty', 0x270, 'CPP_UnitParameter'),
    ('UnitName', 'TextProperty', 0x288, 'CPP_UnitParameter'),
    ('UnitNameDA', 'ObjectProperty', 0x298, 'CPP_UnitParameter'),
    ('m_pOwnerBtlUnit', 'ObjectProperty', 0x360, 'CPP_BtlUnitParameter'),
]
VM_PROPS = [
    ('UnitId', 'IntProperty', 0x68, 'CPP_VM_UnitBase'),
    ('UnitParam', 'ObjectProperty', 0x70, 'CPP_VM_UnitBase'),
    ('HitPointVM', 'ObjectProperty', 0x90, 'CPP_VM_UnitParam'),
    ('MagicPointVM', 'ObjectProperty', 0x98, 'CPP_VM_UnitParam'),
    ('LimitPointVM', 'ObjectProperty', 0xA0, 'CPP_VM_UnitParam'),
    ('CurrentPoint', 'IntProperty', 0xB8, 'CPP_VM_Point'),
    ('MaxPoint', 'IntProperty', 0xBC, 'CPP_VM_Point'),
    ('bEnablePredict', 'BoolProperty', 0xC8, 'CPP_VM_PredictPoint'),
    ('Multiplier', 'FloatProperty', 0x11C, 'CPP_VM_UnitParamPoint'),
]


class FakeMemory(LinuxProcessMemory):
    """Espacio de direcciones disperso: regiones [inicio, bytearray]."""

    def __init__(self, pid=4242):
        self.pid = pid
        self.ptr_size = 8
        self._fd = None
        self._modules = {MODULE.lower(): BASE}
        self.regions = []
        self.alive_flag = True
        self.reads = 0

    def map(self, start, size):
        self.regions.append((start, bytearray(size)))

    def _region(self, addr, size):
        for start, buf in self.regions:
            if start <= addr and addr + size <= start + len(buf):
                return start, buf
        raise MemoryReadError(f'no mapeado 0x{addr:x}+{size}')

    def read(self, addr, size):
        self.reads += 1
        if addr <= 0:
            raise MemoryReadError(f'dirección inválida 0x{addr:x}')
        start, buf = self._region(addr, size)
        return bytes(buf[addr - start:addr - start + size])

    def write(self, addr, data):
        start, buf = self._region(addr, len(data))
        buf[addr - start:addr - start + len(data)] = data

    def put(self, kind, addr, value):
        self.write(addr, struct.pack('<' + self._FMT[kind], value))

    def alive(self):
        return self.alive_flag

    def close(self):
        pass


class FakeGame:
    """Constructor del escenario. Las direcciones salen de un asignador lineal."""

    OBJ_SIZE = 0x900      # cubre CPP_BtlUnit +0x838

    def __init__(self, build=BUILD, layout=None):
        # Disposición de la reflexión que usa este "juego" (por defecto la de UE 5.0-5.3)
        self.layout = layout or U.REFLECTION_LAYOUTS[0]
        self.mem = m = FakeMemory()
        self._next = 0x200000000
        # Cabecera PE del módulo
        m.map(BASE, 0x1000)
        m.write(BASE, b'MZ')
        m.put('u32', BASE + 0x3C, 0x100)
        m.write(BASE + 0x100, b'PE\0\0')
        m.put('u32', BASE + 0x108, build['timestamp'])
        m.put('u32', BASE + 0x150, build['image_size'])
        # Globales
        self.gnames = BASE + RVA['gnames_rva']
        self.gobjects = BASE + RVA['gobjects_rva']
        self.gworld = BASE + RVA['gworld_rva']
        for g in (self.gnames, self.gobjects, self.gworld):
            m.map(g, 0x100)
        # FNamePool: un bloque de nombres
        self.name_block = self.alloc(0x40000)
        m.put('u32', self.gnames + 0x08, 0)
        m.put('u64', self.gnames + 0x10, self.name_block)
        self._name_cursor = 0
        self._names = {}
        self.fname_index('None')
        # GUObjectArray: un chunk
        self.chunks = self.alloc(0x100)
        self.chunk0 = self.alloc(U.CHUNK * U.ITEM)
        m.put('u64', self.gobjects, self.chunks)
        m.put('u64', self.chunks, self.chunk0)
        self.objects = []
        self._classes = {}
        self._field_classes = {}
        # Clases base
        self.cls('Class')
        self.cls('Object')

    # --- primitivas ---
    def alloc(self, size, align=0x10):
        addr = self._next
        self._next = (addr + size + 0xFFF) & ~0xFFF
        self.mem.map(addr, size)
        return addr

    def fname_index(self, text):
        if text in self._names:
            return self._names[text]
        raw = text.encode('latin-1')
        off = self._name_cursor
        self.mem.put('u16', self.name_block + off, len(raw) << 6)
        self.mem.write(self.name_block + off + 2, raw)
        self._name_cursor = (off + 2 + len(raw) + 1) & ~1     # alineado a 2
        idx = off // 2
        self._names[text] = idx
        return idx

    def write_fname(self, addr, text, number=0):
        self.mem.write(addr, struct.pack('<iI', self.fname_index(text), number))

    def obj(self, name, cls, outer=0, flags=0, size=None, registered=True):
        """UObject en GObjects. cls es un nombre de clase o la dirección de una clase."""
        addr = self.alloc(size or self.OBJ_SIZE)
        index = len(self.objects)
        cls_addr = self.cls(cls) if isinstance(cls, str) else cls
        m = self.mem
        m.put('i32', addr + U.OBJ_FLAGS, flags)
        m.put('u32', addr + U.OBJ_INDEX, index)
        m.put('u64', addr + U.OBJ_CLASS, cls_addr)
        self.write_fname(addr + U.OBJ_NAME, name)
        m.put('u64', addr + U.OBJ_OUTER, outer)
        self.objects.append(addr)
        m.put('u64', self.chunk0 + index * U.ITEM, addr if registered else 0)
        m.put('i32', self.gobjects + 0x14, len(self.objects))
        return addr

    def cls(self, name, super_name=None):
        """UClass (se crea una vez). Su clase es 'Class'."""
        if name in self._classes:
            return self._classes[name]
        addr = self.alloc(0x100)
        self._classes[name] = addr
        meta = self._classes.get('Class', addr)
        index = len(self.objects)
        m = self.mem
        m.put('u32', addr + U.OBJ_INDEX, index)
        m.put('u64', addr + U.OBJ_CLASS, meta)
        self.write_fname(addr + U.OBJ_NAME, name)
        self.objects.append(addr)
        m.put('u64', self.chunk0 + index * U.ITEM, addr)
        m.put('i32', self.gobjects + 0x14, len(self.objects))
        if super_name:
            m.put('u64', addr + U.STRUCT_SUPER, self.cls(super_name))
        return addr

    def props(self, cls_name, props):
        """Lista enlazada de FField en ChildProperties: [(nombre, tipo, offset)]."""
        child_props, f_class, f_next, f_name, p_offset = self.layout
        prev = None
        for name, ftype, offset in props:
            field = self.alloc(0x80)
            if ftype not in self._field_classes:
                fc = self.alloc(0x20)
                self.write_fname(fc, ftype)
                self._field_classes[ftype] = fc
            self.mem.put('u64', field + f_class, self._field_classes[ftype])
            self.write_fname(field + f_name, name)
            self.mem.put('i32', field + p_offset, offset)
            if prev is None:
                self.mem.put('u64', self.cls(cls_name) + child_props, field)
            else:
                self.mem.put('u64', prev + f_next, field)
            prev = field

    def tarray(self, addr, items, kind):
        size = {'i32': 4, 'u64': 8}[kind]
        data = self.alloc(max(1, len(items)) * size) if items else 0
        for i, v in enumerate(items):
            self.mem.put(kind, data + i * size, v)
        self.mem.put('u64', addr, data)
        self.mem.put('i32', addr + 8, len(items))
        self.mem.put('i32', addr + 12, len(items))

    def sparse(self, addr, elements, stride=24, holes=()):
        """TSparseArray en addr con elementos de `stride` bytes; devuelve sus direcciones.

        `holes` son índices libres (bit a 0). Bits en línea (+0x10) si caben en 128."""
        n = len(elements) + len(holes)
        data = self.alloc(max(1, n) * stride)
        m = self.mem
        m.put('u64', addr, data)
        m.put('i32', addr + 8, n)
        m.put('i32', addr + 12, n)
        bits = addr + 0x10 if n <= 128 else self.alloc((n + 31) // 32 * 4)
        if bits != addr + 0x10:
            m.put('u64', addr + 0x20, bits)
        out, it = [], iter(elements)
        for i in range(n):
            e = data + i * stride
            if i in holes:
                continue
            m.put('u32', bits + (i // 32) * 4, m.u32(bits + (i // 32) * 4) | (1 << (i % 32)))
            out.append((e, next(it)))
        return out

    def data_table(self, row_struct, rows):
        """UDataTable: rows = [(clave, {offset: (tipo, valor)})]."""
        table = self.obj(f'DT_{row_struct}', 'DataTable')
        self.mem.put('u64', table + 0x28, self.obj(row_struct, 'ScriptStruct'))
        for e, (key, fields) in self.sparse(table + 0x30, rows):
            row = self.alloc(0x40)
            for off, (kind, value) in fields.items():
                self.mem.put(kind, row + off, value)
            self.write_fname(e, key)
            self.mem.put('u64', e + 8, row)
        return table

    def proc(self):
        return ProcInfo(self.mem.pid, MODULE[:15], MODULE, f'Z:\\game\\{MODULE}')


def level_exp(level):
    """EXP necesaria en cada nivel de la curva sintética (nivel 1 = 0)."""
    return 0 if level == 1 else level * 100


def cumulative(level):
    return sum(level_exp(lv) for lv in range(1, level + 1))


def build_ffrs(game=None, *, party=(1001, 1002), units=None, gil=12345,
               battle=None, field=None, props=PARAM_PROPS, vms=None, vm_props=VM_PROPS,
               curve_for=None, save=True, world_class='World', enemy_table=False):
    """Escenario completo de FFRS.

    party: IDs del equipo (SaveData +0x90).
    units: {id: exp}; por defecto, los del equipo con EXP para nivel 5 y 10.
    battle: None (fuera de batalla) o [(id, {'hp':..,'hp_max':..,'mp':..,'mp_max':..})].
    field: CPP_UnitParameter vivos fuera de batalla, con el mismo formato que battle.
    vms: ViewModels CPP_VM_UnitParam [(id, stats)]; por defecto, uno por personaje de
         field y battle (sin repetir). [] = ninguno.
    curve_for: IDs con curva de nivel; por defecto los 8 personajes.
    """
    g = game or FakeGame()
    m = g.mem
    g.cls('Engine')
    g.cls('CPP_UnitParameter', 'Object')
    g.cls('CPP_BtlUnitParameter', 'CPP_UnitParameter')
    g.cls('CPP_VM_UnitBase', 'Object')
    g.cls('CPP_VM_UnitParam', 'CPP_VM_UnitBase')
    g.cls('CPP_VM_Point', 'Object')
    g.cls('CPP_VM_PredictPoint', 'CPP_VM_Point')
    g.cls('CPP_VM_UnitParamPoint', 'CPP_VM_PredictPoint')
    g.cls('VM_UnitParamPoint_C', 'CPP_VM_UnitParamPoint')
    for plist in (props, vm_props):
        by_owner = {}
        for name, ftype, off, owner in plist or ():
            by_owner.setdefault(owner, []).append((name, ftype, off))
        for owner, items in by_owner.items():
            g.props(owner, items)

    world = g.obj('Mucha_World', world_class, size=0x1000)
    gi = g.obj('GameInstance_0', 'CPP_MuchaGameInstance', outer=world)
    m.put('u64', g.gworld, world)
    m.put('u64', world + 0x228, gi)

    # Curvas: UNIT_PARAMETER (ID -> curva), LIST (curva -> tabla), LEVEL (nivel -> EXP)
    ids = (1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008)
    curve_for = ids if curve_for is None else curve_for
    if enemy_table:   # otra tabla con el mismo RowStruct, registrada antes (enemigos)
        g.data_table('UNIT_PARAMETER', [(f'E{i}', {8: ('i32', i), 0x3C: ('i32', 1)}) for i in range(5001, 5040)])
    g.data_table('UNIT_PARAMETER', [(f'U{i}', {8: ('i32', i), 0x3C: ('i32', 9000 + i)}) for i in ids])
    level_tables = {}
    for i in curve_for:
        level_tables[9000 + i] = level_table(g)
    add_curves(g, level_tables)

    if save:
        mgr_cdo = g.obj('Default__CPP_MuchaSaveDataManager', 'CPP_MuchaSaveDataManager',
                        outer=gi, flags=RF_CLASS_DEFAULT)
        mgr = g.obj('CPP_MuchaSaveDataManager_0', 'CPP_MuchaSaveDataManager', outer=gi)
        sd = g.obj('CPP_MuchaGameSaveData_0', 'CPP_MuchaGameSaveData', outer=mgr)
        m.put('u64', mgr + 0x60, sd)
        m.put('u64', mgr_cdo + 0x60, sd)
        m.put('i32', sd + 0x28, gil)
        if units is None:
            units = {cid: cumulative(lv) for cid, lv in zip(party, (5, 10, 15, 20))}
        udata = g.alloc(max(1, len(units)) * 0xA0)
        for k, (cid, exp) in enumerate(units.items()):
            m.put('i32', udata + k * 0xA0, cid)
            m.put('i32', udata + k * 0xA0 + 4, exp)
        m.put('u64', sd + 0x60, udata)
        m.put('i32', sd + 0x68, len(units))
        m.put('i32', sd + 0x6C, len(units))
        g.tarray(sd + 0x90, list(party), 'i32')
    g.world, g.gi = world, gi

    # Subsistemas del World (+0x930): siempre hay alguno; CPP_BtlManager solo en batalla
    subs = [g.obj('SomeSubsystem_0', 'WorldSubsystem', outer=world)]
    if battle is not None:
        bm = g.obj('CPP_BtlManager_0', 'CPP_BtlManager', outer=world)
        um = g.obj('CPP_BtlUnitManager_0', 'CPP_BtlUnitManager', outer=bm)
        m.put('u64', bm + 0x48, um)
        actors = []
        for k, (cid, stats) in enumerate(battle):
            actor = g.obj(f'CPP_BtlUnit_{k}', 'CPP_BtlUnit', outer=world)
            param = unit_parameter(g, 'CPP_BtlUnitParameter', cid, stats, outer=actor)
            m.put('u64', actor + 0x838, param)
            actors.append(actor)
        g.tarray(um + 0x28, actors, 'u64')
        subs.append(bm)
    for e, obj in g.sparse(world + 0x930, subs, holes=(0,)):
        m.put('u64', e + 8, obj)
    g.field_params = [unit_parameter(g, 'CPP_UnitParameter', cid, stats, outer=g.gi)
                      for cid, stats in (field or ())]
    if vms is None:
        vms = list({cid: stats for cid, stats in list(battle or ()) + list(field or ())}.items())
    manager = g.obj('CPP_UnitVMManager_0', 'CPP_UnitVMManager', outer=g.gi)
    g.vms = [viewmodel(g, cid, stats, outer=manager) for cid, stats in vms]
    return g


def viewmodel(g, cid, stats, outer=0):
    """CPP_VM_UnitParam con HitPointVM / MagicPointVM (CurrentPoint, MaxPoint)."""
    vm = g.obj(f'CPP_VM_UnitParam_{cid}_{len(g.objects)}', 'CPP_VM_UnitParam', outer=outer)
    g.mem.put('i32', vm + 0x68, cid)
    for key, off in (('hp', 0x90), ('mp', 0x98)):
        point = g.obj(f'VM_UnitParamPoint_C_{len(g.objects)}', 'VM_UnitParamPoint_C', outer=vm)
        g.mem.put('i32', point + 0xB8, stats.get(key, 0))
        g.mem.put('i32', point + 0xBC, stats.get(f'{key}_max', 0))
        g.mem.put('u64', vm + off, point)
    return vm


def level_table(g):
    return g.data_table('UNIT_LEVEL_PARAMETER',
                        [(f'L{lv}', {8: ('i32', lv), 12: ('i32', level_exp(lv))}) for lv in range(1, 100)])


def add_curves(g, level_tables):
    """Tabla UNIT_LEVEL_PARAMETER_LIST: {id de curva: tabla de niveles}."""
    g.data_table('UNIT_LEVEL_PARAMETER_LIST',
                 [(f'C{c}', {8: ('i32', c), 0x10: ('u64', t)}) for c, t in level_tables.items()])


def unit_parameter(g, cls, cid, stats, outer=0):
    """CPP_UnitParameter o CPP_BtlUnitParameter: ID en +0xD0, HP/MP actual en +0x10C/+0x110."""
    param = g.obj(f'{cls}_{cid}_{len(g.objects)}', cls, outer=outer)
    g.mem.put('i32', param + 0xD0, cid)
    for key, off in (('hp', 0x10C), ('mp', 0x110), ('lb', 0x118), ('lb_max', 0x2A0)):
        if key in stats:
            g.mem.put('i32', param + off, stats[key])
    return param


def kill(g, obj):
    """Marca un objeto como destruido (BeginDestroyed), como hace UE al descargar un mapa."""
    g.mem.put('i32', obj + U.OBJ_FLAGS, RF_BEGIN_DESTROYED)
