"""Cabecera PE de un .exe en memoria: sirve a cualquier plugin para reconocer la build."""
from .memory import MemoryReadError


def pe_info(mem, module_base):
    """TimeDateStamp y SizeOfImage de la cabecera PE: identifican la build del .exe."""
    if mem.read(module_base, 2) != b'MZ':
        raise MemoryReadError('el módulo no empieza con MZ')
    nt = module_base + mem.u32(module_base + 0x3C)
    if mem.read(nt, 4) != b'PE\0\0':
        raise MemoryReadError('cabecera PE no encontrada')
    return {'timestamp': mem.u32(nt + 0x08), 'image_size': mem.u32(nt + 0x50)}
