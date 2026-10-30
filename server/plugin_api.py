"""API estable para plugins (API 2). Un plugin importa SOLO de aquí.

Si algo de esto cambia de forma incompatible, sube plugins.API_VERSION: los
plugins con otra "api" en su plugin.json no se cargan (en vez de fallar raro).

    Field, GamePlugin                  declarar el plugin y sus campos
    MemoryReadError, ProcessGone       errores de lectura (los gestiona el hub)
    pe_info                            build del .exe (TimeDateStamp, SizeOfImage)
    PortraitFinder                     retratos del usuario (~/.local/share/gamepad/portraits/<id>/)

La memoria que reciben on_attach(mem, proc) y read(mem) ofrece: read, value, u8..f64,
ptr, string, pointer (cadenas estilo Cheat Engine), module_base y alive.

El hub no sabe buscar valores de ningún juego ni motor: esa lógica (punteros, firmas,
lectores de motor como el de Unreal) va dentro de cada plugin, que puede tener sus
propios módulos y importarlos con import relativo (from .ue import ...).
"""
from .memory import MemoryReadError, ProcessGone
from .plugins import API_VERSION, Field, GamePlugin
from .portraits import Finder as PortraitFinder
from .pe import pe_info

__all__ = ['API_VERSION', 'Field', 'GamePlugin', 'MemoryReadError', 'ProcessGone', 'PortraitFinder',
           'pe_info']
