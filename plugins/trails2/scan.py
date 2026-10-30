"""Búsqueda de firmas (AOB) en el código de un .exe en memoria, solo lectura.

Las firmas se escriben como en Cheat Engine: "48 8B ?? ?? 0F" o "488B????0F"
(?? o ** = cualquier byte). Solo se buscan las secciones ejecutables de la imagen PE.
"""
import re
import struct

from server.plugin_api import MemoryReadError

CHUNK = 4 << 20                  # se lee el código por trozos de 4 MB
SCN_MEM_EXECUTE = 0x20000000


class SignatureError(Exception):
    """La firma no aparece (o aparece más de una vez): probablemente otra versión del juego."""


def compile_aob(text):
    hexes = text.replace(' ', '')
    if not hexes or len(hexes) % 2:
        raise ValueError(f'firma inválida: {text!r}')
    parts = []
    for i in range(0, len(hexes), 2):
        tok = hexes[i:i + 2]
        parts.append(b'.' if tok in ('??', '**') else re.escape(bytes([int(tok, 16)])))
    return re.compile(b''.join(parts), re.DOTALL), len(parts)


def code_sections(mem, base):
    """(nombre, inicio, tamaño) de cada sección ejecutable."""
    if mem.read(base, 2) != b'MZ':
        raise MemoryReadError('el módulo no empieza con MZ')
    nt = base + mem.u32(base + 0x3C)
    if mem.read(nt, 4) != b'PE\0\0':
        raise MemoryReadError('cabecera PE no encontrada')
    count, opt_size = mem.u16(nt + 6), mem.u16(nt + 0x14)
    table = mem.read(nt + 0x18 + opt_size, 40 * count)
    out = []
    for i in range(count):
        name, vsize, rva = struct.unpack_from('<8sII', table, i * 40)
        flags = struct.unpack_from('<I', table, i * 40 + 36)[0]
        if flags & SCN_MEM_EXECUTE and vsize:
            out.append((name.rstrip(b'\0').decode('ascii', 'replace'), base + rva, vsize))
    return out


def find(mem, base, aob, limit=2):
    """Direcciones donde aparece la firma (como mucho `limit`)."""
    rx, n = compile_aob(aob)
    hits = []
    for _, start, size in code_sections(mem, base):
        for pos in range(0, size, CHUNK):
            length = min(CHUNK + n - 1, size - pos)   # solapa para no perder firmas partidas
            try:
                data = mem.read(start + pos, length)
            except MemoryReadError:
                continue
            for m in rx.finditer(data):
                if m.start() < CHUNK:                 # las del solape las encuentra el trozo siguiente
                    hits.append(start + pos + m.start())
                    if len(hits) >= limit:
                        return hits
    return hits


def find_one(mem, base, aob, what):
    hits = find(mem, base, aob)
    if not hits:
        raise SignatureError(f'firma de {what} no encontrada')
    if len(hits) > 1:
        raise SignatureError(f'firma de {what} ambigua (aparece varias veces)')
    return hits[0]


def rip_target(mem, insn, disp_offset, insn_len):
    """Dirección a la que apunta una instrucción con operando [rip+disp32]."""
    return insn + insn_len + mem.i32(insn + disp_offset)
