"""Plantilla para un juego real (los archivos que empiezan por "_" no se cargan).

Copia este archivo como plugins/mi_juego.py y rellena offsets.
Los offsets se encuentran con Cheat Engine (Windows/Wine), PINCE o scanmem
(Linux), buscando el valor, cambiándolo en el juego y repitiendo hasta aislar
la dirección; luego "pointer scan" para obtener una cadena estable desde un
módulo (las direcciones directas cambian en cada arranque).

Con Proton/Wine el proceso suele llamarse "Juego.exe" y el .exe aparece en
/proc/<pid>/maps, así que module_base('Juego.exe') funciona igual.

No uses esto en juegos online con anti-cheat: leer memoria puede considerarse
trampa y acarrear un baneo, aunque sea solo lectura.
"""
from server.plugins import Field, GamePlugin

# Cadena estilo Cheat Engine: "Juego.exe"+0x01A2B3C0 -> 0x28 -> 0x10
PLAYER_BASE = 0x01A2B3C0
PLAYER_CHAIN = (0x28, 0x10)


class Plugin(GamePlugin):
    id = 'mi_juego'
    name = 'Mi Juego'
    process_names = ('Juego.exe',)
    ptr_size = 8          # 4 si el juego es de 32 bits
    poll_hz = 4
    fields = [
        Field('hp', 'HP', kind='bar', max_key='hp_max', tone='hp'),
        Field('mp', 'MP', kind='bar', max_key='mp_max', tone='mp'),
        Field('gold', 'Oro', tone='gold'),
    ]

    def on_attach(self, mem, proc):
        self.base = mem.module_base('Juego.exe')

    def read(self, mem):
        p = mem.pointer(self.base + PLAYER_BASE, *PLAYER_CHAIN)
        return {
            'hp': mem.i32(p + 0x00), 'hp_max': mem.i32(p + 0x04),
            'mp': mem.f32(p + 0x08), 'mp_max': mem.f32(p + 0x0C),
            'gold': mem.u32(p + 0x40),
        }
