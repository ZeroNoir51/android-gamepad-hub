"""Lectura (solo lectura) de estructuras de Unreal Engine 5 desde otro proceso.

Es parte del plugin, no del hub: el hub solo ofrece leer bytes (plugin_api) y cada
plugin trae su propia lógica para encontrar los valores.

Disposición verificada para FINAL FANTASY RESONANCE build 24250053 por la tabla
shawnjohnjr/ff-RESONANCE-ct (FFRS_Steam_24250053_Starter.CT):
- GNames (FNamePool): bloque actual en +0x08, punteros a bloques desde +0x10.
- GObjects apunta al FChunkedFixedUObjectArray: bloques en +0x00, total en +0x14,
  elementos de 24 bytes (objeto en +0, número de serie en +16).
- UObject: flags +0x08, índice +0x0C, clase +0x10, nombre +0x18, outer +0x20.
- UStruct: SuperStruct +0x40, Children (UField) +0x48.

Sin verificar con esa tabla: la reflexión (UStruct.ChildProperties y FField). La
disposición estándar de UE 5.0-5.3 (ChildProperties +0x50; FField: clase +0x08,
Next +0x20, nombre +0x28; Offset_Internal +0x4C) NO funcionó en el juego real
(build 24250053 en Bazzite: FField+0x08 nulo). properties() prueba las variantes de
REFLECTION_LAYOUTS y se queda con la primera cuyos campos tienen sentido.
"""
import re
import struct

from server.plugin_api import MemoryReadError

OBJ_FLAGS, OBJ_INDEX, OBJ_CLASS, OBJ_NAME, OBJ_OUTER = 0x08, 0x0C, 0x10, 0x18, 0x20
RF_CLASS_DEFAULT = 0x10
RF_DEAD = 0x18000                 # BeginDestroyed | FinishDestroyed
CHUNK = 65536
ITEM = 24
STRUCT_SUPER, STRUCT_CHILD_PROPS = 0x40, 0x50
FIELD_CLASS, FIELD_NEXT, FIELD_NAME, PROP_OFFSET = 0x08, 0x20, 0x28, 0x4C
# (UStruct.ChildProperties, FField.ClassPrivate, FField.Next, FField.NamePrivate, FProperty.Offset_Internal)
REFLECTION_LAYOUTS = [
    (0x50, 0x08, 0x20, 0x28, 0x4C),   # UE 5.0-5.3 (FFieldVariant de 16 bytes)
    (0x50, 0x08, 0x18, 0x20, 0x44),   # FFieldVariant de 8 bytes (puntero con marca)
    (0x58, 0x08, 0x20, 0x28, 0x4C), (0x58, 0x08, 0x18, 0x20, 0x44),
    (0x48, 0x08, 0x20, 0x28, 0x4C), (0x48, 0x08, 0x18, 0x20, 0x44),
    (0x60, 0x08, 0x20, 0x28, 0x4C), (0x60, 0x08, 0x18, 0x20, 0x44),
]
_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_ ]{0,127}$')


class UEReader:
    def __init__(self, mem, module_base, gnames_rva, gobjects_rva, gworld_rva):
        self.mem = mem
        self.gnames = module_base + gnames_rva
        self.gobjects = module_base + gobjects_rva
        self.gworld = module_base + gworld_rva
        self._names = {}
        self._class_names = {}
        self.layout = None   # disposición de la reflexión, detectada en el primer uso
        if self.name(0) != 'None':
            raise MemoryReadError('la tabla de nombres no coincide con esta build')

    # --- nombres ---
    def name(self, index, number=0):
        key = (index, number)
        if key in self._names:
            return self._names[key]
        if index < 0 or (index >> 16) > self.mem.u32(self.gnames + 0x08):
            raise MemoryReadError(f'FName {index} fuera de rango')
        block = self.mem.ptr(self.gnames + 0x10 + (index >> 16) * 8)
        entry = block + (index & 0xFFFF) * 2
        header = self.mem.u16(entry)
        length = header >> 6
        if not 0 < length <= 1023:
            raise MemoryReadError(f'FName {index} con longitud inválida')
        if header & 1:
            text = self.mem.read(entry + 2, length * 2).decode('utf-16-le', 'replace')
        else:
            text = self.mem.read(entry + 2, length).decode('latin-1')
        if number:
            text = f'{text}_{number - 1}'
        self._names[key] = text
        return text

    def fname(self, address):
        idx, number = struct.unpack('<iI', self.mem.read(address, 8))
        return self.name(idx, number)

    def object_name(self, obj):
        return self.fname(obj + OBJ_NAME)

    def class_name(self, obj):
        cls = self.mem.ptr(obj + OBJ_CLASS)
        if cls not in self._class_names:
            self._class_names[cls] = self.object_name(cls)
        return self._class_names[cls]

    # --- registro de objetos ---
    def object_count(self):
        return self.mem.i32(self.gobjects + 0x14)

    def _item(self, index):
        if not 0 <= index < self.object_count():
            return None
        chunk = self.mem.ptr(self.mem.ptr(self.gobjects) + (index // CHUNK) * 8)
        return chunk + (index % CHUNK) * ITEM if chunk else None

    def live(self, obj, allow_default=False):
        """True si obj sigue registrado en su índice y no está destruido."""
        if not obj or obj < 0x10000:
            return False
        try:
            flags, index = struct.unpack('<iI', self.mem.read(obj + OBJ_FLAGS, 8))
            mask = RF_DEAD | (0 if allow_default else RF_CLASS_DEFAULT)
            item = self._item(index)
            return not flags & mask and item is not None and self.mem.ptr(item) == obj
        except MemoryReadError:
            return False

    def isa(self, obj, class_name):
        cls = self.mem.ptr(obj + OBJ_CLASS)
        for _ in range(32):
            if not cls:
                return False
            if self.object_name(cls) == class_name:
                return True
            cls = self.mem.ptr(cls + STRUCT_SUPER)
        return False

    def objects(self):
        """(objeto, nombre de clase) de todos los objetos vivos, sin CDO, en una pasada."""
        count = self.object_count()
        chunks = self.mem.ptr(self.gobjects)
        for c in range((count + CHUNK - 1) // CHUNK):
            chunk = self.mem.ptr(chunks + c * 8)
            n = min(CHUNK, count - c * CHUNK)
            if not chunk or n <= 0:
                continue
            raw = self.mem.read(chunk, n * ITEM)
            for i in range(n):
                obj = int.from_bytes(raw[i * ITEM:i * ITEM + 8], 'little')
                if not obj:
                    continue
                try:
                    head = self.mem.read(obj + OBJ_FLAGS, 0x10)   # flags, índice, clase
                    if int.from_bytes(head[0:4], 'little') & (RF_DEAD | RF_CLASS_DEFAULT):
                        continue
                    cls = int.from_bytes(head[8:16], 'little')
                    if cls not in self._class_names:
                        self._class_names[cls] = self.object_name(cls)
                    yield obj, self._class_names[cls]
                except MemoryReadError:
                    continue

    def scan(self, class_names):
        """Una pasada por todos los objetos: {clase: [objetos vivos, sin CDO]}."""
        found = {c: [] for c in set(class_names)}
        for obj, name in self.objects():
            if name in found:
                found[name].append(obj)
        return found

    # --- mundo ---
    def world(self):
        world = self.mem.ptr(self.gworld)
        if not world:
            raise MemoryReadError('GWorld es nulo (¿pantalla de carga?)')
        cls = self.class_name(world)
        if cls != 'World':
            raise MemoryReadError(f'GWorld apunta a un {cls!r}, no a un World: offsets de otra build')
        return world

    def sparse_entries(self, address, stride, max_count=4096):
        """Direcciones de los elementos asignados de un TSet/TMap (TSparseArray)."""
        data = self.mem.ptr(address)
        n, cap = self.mem.i32(address + 8), self.mem.i32(address + 12)
        if not 0 <= n <= cap <= max_count or (n and not data):
            raise MemoryReadError('contenedor inválido')
        bits = self.mem.ptr(address + 0x20) or address + 0x10   # bits en línea si no hay heap
        out = []
        for i in range(n):
            if self.mem.u32(bits + (i // 32) * 4) & (1 << (i % 32)):
                out.append(data + i * stride)
        return out

    def table_rows(self, table, row_struct):
        """Filas de un UDataTable: [(clave, puntero a la fila)]."""
        if self.class_name(table) != 'DataTable' or self.object_name(self.mem.ptr(table + 0x28)) != row_struct:
            raise MemoryReadError(f'la tabla {row_struct} cambió')
        return [(self.fname(e), self.mem.ptr(e + 8)) for e in self.sparse_entries(table + 0x30, 24, 10000)]

    # --- reflexión de propiedades ---
    def _walk(self, cls, layout, strict):
        """Propiedades declaradas en cls (sin padres) con una disposición dada.
        strict: lanza MemoryReadError si algún campo no parece una FProperty real."""
        child_props, f_class, f_next, f_name, p_offset = layout
        out = []
        field = self.mem.ptr(cls + child_props)
        for _ in range(2048):
            if not field:
                break
            ftype = self.fname(self.mem.ptr(field + f_class))
            name = self.fname(field + f_name)
            offset = self.mem.i32(field + p_offset)
            if strict and not (ftype.endswith('Property') and name != 'None' and _IDENT.match(name)
                               and 0 <= offset < 0x100000):
                raise MemoryReadError('no parece una lista de FProperty')
            out.append((name, ftype, offset))
            field = self.mem.ptr(field + f_next)
        return out

    def detect_layout(self, cls):
        """Primera disposición de REFLECTION_LAYOUTS que da propiedades coherentes en cls o sus padres."""
        for layout in REFLECTION_LAYOUTS:
            c, found = cls, 0
            try:
                for _ in range(32):
                    if not c:
                        break
                    found += len(self._walk(c, layout, strict=True))
                    c = self.mem.ptr(c + STRUCT_SUPER)
            except MemoryReadError:
                continue
            if found:
                return layout
        raise MemoryReadError('disposición de la reflexión desconocida (ninguna variante encaja)')

    def properties(self, cls):
        """[(nombre, tipo, offset, clase dueña)] recorriendo la clase y sus padres."""
        if self.layout is None:
            self.layout = self.detect_layout(cls)
        out = []
        for _ in range(32):
            if not cls:
                break
            owner = self.object_name(cls)
            out += [(name, ftype, offset, owner) for name, ftype, offset in self._walk(cls, self.layout, False)]
            cls = self.mem.ptr(cls + STRUCT_SUPER)
        return out

    def hexdump(self, address, size):
        """Líneas '+0x10: 0x... 0x...' (u64) para escribir en el log al diagnosticar."""
        lines = []
        for off in range(0, size, 0x20):
            try:
                words = struct.unpack('<4Q', self.mem.read(address + off, 0x20))
                lines.append(f'+0x{off:03X}: ' + ' '.join(f'{w:016X}' for w in words))
            except MemoryReadError:
                lines.append(f'+0x{off:03X}: ilegible')
        return lines
