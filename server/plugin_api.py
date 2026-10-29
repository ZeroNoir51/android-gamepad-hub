"""API estable para plugins (API 1). Un plugin importa SOLO de aquí.

Si algo de esto cambia de forma incompatible, sube plugins.API_VERSION: los
plugins con otra "api" en su plugin.json no se cargan (en vez de fallar raro).

    Field, GamePlugin                  declarar el plugin y sus campos
    MemoryReadError, ProcessGone       errores de lectura (los gestiona el hub)
    UEReader, pe_info, OBJ_*           lectura de Unreal Engine 5
    PortraitFinder                     retratos del usuario (~/.local/share/gamepad/portraits/<id>/)

La memoria que reciben on_attach(mem, proc) y read(mem) ofrece: read, value, u8..f64,
ptr, string, pointer (cadenas estilo Cheat Engine), module_base y alive.
"""
from .memory import MemoryReadError, ProcessGone
from .plugins import API_VERSION, Field, GamePlugin
from .portraits import Finder as PortraitFinder
from .ue import OBJ_CLASS, OBJ_FLAGS, OBJ_INDEX, OBJ_NAME, OBJ_OUTER, UEReader, pe_info

__all__ = ['API_VERSION', 'Field', 'GamePlugin', 'MemoryReadError', 'ProcessGone', 'PortraitFinder',
           'UEReader', 'pe_info', 'OBJ_CLASS', 'OBJ_FLAGS', 'OBJ_INDEX', 'OBJ_NAME', 'OBJ_OUTER']
