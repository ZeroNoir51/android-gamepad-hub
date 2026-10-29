"""Mando virtual. Linux: /dev/uinput sin dependencias. Pruebas u otros sistemas: NullPad.

Windows (futuro): implementar WindowsPad con ViGEmBus (p. ej. el paquete
`vgamepad`) respetando la misma interfaz: apply(state), reset(), close().
"""
import fcntl
import os
import struct

from . import protocol


class NullPad:
    """No emite nada; sirve para probar telemetría y plugins sin /dev/uinput."""
    name = 'null (sin mando virtual)'

    def __init__(self):
        self.state = protocol.neutral()

    def apply(self, state):
        self.state = state

    def reset(self):
        self.state = protocol.neutral()

    def close(self):
        self.reset()


# --- uinput sin dependencias (linux/input.h, linux/uinput.h) ---
# Antes se usaba python-evdev, pero no tiene paquetes precompilados: en sistemas
# inmutables (Bazzite) compilarlo exige python3-devel, es decir, sudo y reiniciar.
EV_SYN, EV_KEY, EV_ABS, SYN_REPORT, BUS_USB = 0x00, 0x01, 0x03, 0, 0x03
BTN = {'a': 0x130, 'b': 0x131, 'x': 0x133, 'y': 0x134,       # SOUTH EAST NORTH WEST
       'lb': 0x136, 'rb': 0x137, 'back': 0x13a, 'start': 0x13b, 'guide': 0x13c,
       'ls': 0x13d, 'rs': 0x13e}                             # TL TR SELECT START MODE THUMBL/R
STICK = (-32768, 32767, 16, 128)                             # mínimo, máximo, fuzz, flat
TRIGGER = (0, 255, 0, 0)
HAT = (-1, 1, 0, 0)
ABS = {'lx': (0x00, STICK), 'ly': (0x01, STICK), 'rx': (0x03, STICK), 'ry': (0x04, STICK),
       'lt': (0x02, TRIGGER), 'rt': (0x05, TRIGGER), 'dx': (0x10, HAT), 'dy': (0x11, HAT)}


def _iow(nr, size):
    return (1 << 30) | (size << 16) | (ord('U') << 8) | nr


UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
UI_DEV_SETUP = _iow(3, 92)            # struct uinput_setup
UI_ABS_SETUP = _iow(4, 28)            # struct uinput_abs_setup
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_ABSBIT = _iow(100, 4), _iow(101, 4), _iow(103, 4)
EVENT = struct.Struct('llHHi')         # struct input_event (timeval nativo; el kernel pone la hora)


class UInputPad:
    name = 'PS5 GamePad Virtual Xbox 360'

    def __init__(self, path='/dev/uinput'):
        self.fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            for code in BTN.values():
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_ABS)
            for code, (lo, hi, fuzz, flat) in ABS.values():
                fcntl.ioctl(self.fd, UI_SET_ABSBIT, code)
                # uinput_abs_setup: code (u16, +2 de relleno) + input_absinfo (6 x s32)
                fcntl.ioctl(self.fd, UI_ABS_SETUP, struct.pack('<H2x6i', code, 0, lo, hi, fuzz, flat, 0))
            # Identidad de mando Xbox 360 con cable. Es un dispositivo uinput, no XInput real.
            name = self.name.encode()[:79]
            fcntl.ioctl(self.fd, UI_DEV_SETUP,
                        struct.pack('<4H80sI', BUS_USB, 0x045e, 0x028e, 0x0114, name, 0))
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise
        self.state = protocol.neutral()

    def apply(self, state):
        events = []
        for key, value in state.items():
            if self.state[key] == value:
                continue
            if key in BTN:
                events.append(EVENT.pack(0, 0, EV_KEY, BTN[key], value))
            else:
                events.append(EVENT.pack(0, 0, EV_ABS, ABS[key][0], value))
        if events:
            events.append(EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0))
            os.write(self.fd, b''.join(events))
        self.state = state

    def reset(self):
        self.apply(protocol.neutral())

    def close(self):
        if self.fd is None:
            return
        try:
            self.reset()
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)
            self.fd = None


def create_pad(kind):
    """kind: 'uinput' | 'null' | 'auto'."""
    if kind == 'null':
        return NullPad()
    try:
        return UInputPad()
    except Exception as ex:  # PermissionError, FileNotFoundError...
        if kind == 'uinput':
            raise
        print(f'[pad] uinput no disponible ({ex!r}); usando NullPad', flush=True)
        return NullPad()
