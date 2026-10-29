"""Plugin de ejemplo para tools/demo_game.py."""
import json
from pathlib import Path

from server.plugin_api import Field, GamePlugin, MemoryReadError

INFO = Path('/tmp/gamepad-demo.json')
MAGIC = 0x42444847


class Plugin(GamePlugin):
    id = 'demo'
    name = 'Demo Game'
    cmdline_contains = 'demo_game.py'
    poll_hz = 4
    fields = [
        Field('hp', 'HP', kind='bar', max_key='hp_max', tone='hp'),
        Field('mp', 'MP', kind='bar', max_key='mp_max', tone='mp'),
        Field('gold', 'Oro', tone='gold'),
        Field('level', 'Nivel'),
    ]

    def on_attach(self, mem, proc):
        info = json.loads(INFO.read_text())
        if info['pid'] != proc.pid:
            raise MemoryReadError('el archivo de la demo es de otro proceso')
        self.world = info['world']
        if mem.u32(self.world) != MAGIC:   # validar que apuntamos a lo correcto
            raise MemoryReadError('firma de World incorrecta')

    def read(self, mem):
        p = mem.pointer(self.world + 0x8, 0x0)   # [World+8] + 0 -> Player
        return {
            'hp': mem.i32(p + 0x0), 'hp_max': mem.i32(p + 0x4),
            'mp': mem.i32(p + 0x8), 'mp_max': mem.i32(p + 0xC),
            'gold': mem.i64(p + 0x10), 'level': mem.i32(p + 0x18),
        }
