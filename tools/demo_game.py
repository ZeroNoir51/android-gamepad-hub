#!/usr/bin/env python3
"""Juego falso para probar el sistema de plugins sin un juego real.

Pruébalo como lo haría Steam:  ps5gamepad run python3 tools/demo_game.py

Guarda HP/MP/Gold en una estructura en memoria nativa y publica en
/tmp/ps5-gamepad-demo.json la dirección de un objeto "World" que contiene
un puntero al jugador (para probar cadenas de punteros).

Disposición en memoria:
  World  @W : +0x0 u32 magic 'GHDB' | +0x8 Player*
  Player @P : +0x0 i32 hp | +0x4 i32 hp_max | +0x8 i32 mp | +0xC i32 mp_max
              +0x10 i64 gold | +0x18 i32 level
"""
import ctypes
import json
import os
import random
import time
from pathlib import Path

INFO = Path('/tmp/ps5-gamepad-demo.json')
MAGIC = 0x42444847  # 'GHDB' en little-endian


class Player(ctypes.Structure):
    _fields_ = [('hp', ctypes.c_int32), ('hp_max', ctypes.c_int32),
                ('mp', ctypes.c_int32), ('mp_max', ctypes.c_int32),
                ('gold', ctypes.c_int64), ('level', ctypes.c_int32)]


class World(ctypes.Structure):
    _fields_ = [('magic', ctypes.c_uint32), ('_pad', ctypes.c_uint32),
                ('player', ctypes.POINTER(Player))]


def main():
    player = Player(hp=120, hp_max=120, mp=40, mp_max=60, gold=0, level=1)
    world = World(magic=MAGIC, player=ctypes.pointer(player))
    addr = ctypes.addressof(world)
    INFO.write_text(json.dumps({'pid': os.getpid(), 'world': addr}))
    print(f'demo_game PID {os.getpid()}  World @ 0x{addr:x}  Player @ 0x{ctypes.addressof(player):x}')
    print('Ctrl+C para salir')
    try:
        while True:
            time.sleep(0.5)
            if random.random() < 0.5:
                player.hp = max(0, player.hp - random.randint(3, 18))
            else:
                player.hp = min(player.hp_max, player.hp + random.randint(1, 8))
            player.mp = max(0, min(player.mp_max, player.mp + random.randint(-6, 4)))
            player.gold += random.randint(0, 25)
            if player.hp == 0:
                player.level += 1
                player.hp_max += 15
                player.hp = player.hp_max
    except KeyboardInterrupt:
        pass
    finally:
        INFO.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
