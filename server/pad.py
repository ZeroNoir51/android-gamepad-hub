"""Mando virtual. Linux: uinput (evdev). Pruebas u otros sistemas: NullPad.

Windows (futuro): implementar WindowsPad con ViGEmBus (p. ej. el paquete
`vgamepad`) respetando la misma interfaz: apply(state), reset(), close().
"""
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


class UInputPad:
    name = 'PS5 GamePad Virtual Xbox 360'

    def __init__(self):
        from evdev import UInput, AbsInfo, ecodes as e
        self._e = e
        self.buttons = {
            'a': e.BTN_SOUTH, 'b': e.BTN_EAST, 'x': e.BTN_NORTH, 'y': e.BTN_WEST,
            'lb': e.BTN_TL, 'rb': e.BTN_TR, 'back': e.BTN_SELECT,
            'start': e.BTN_START, 'guide': e.BTN_MODE,
            'ls': e.BTN_THUMBL, 'rs': e.BTN_THUMBR,
        }
        self.axes = {'lx': e.ABS_X, 'ly': e.ABS_Y, 'rx': e.ABS_RX, 'ry': e.ABS_RY,
                     'lt': e.ABS_Z, 'rt': e.ABS_RZ, 'dx': e.ABS_HAT0X, 'dy': e.ABS_HAT0Y}
        stick = AbsInfo(0, -32768, 32767, 16, 128, 0)
        trig = AbsInfo(0, 0, 255, 0, 0, 0)
        hat = AbsInfo(0, -1, 1, 0, 0, 0)
        caps = {
            e.EV_KEY: list(self.buttons.values()),
            e.EV_ABS: [(e.ABS_X, stick), (e.ABS_Y, stick), (e.ABS_RX, stick), (e.ABS_RY, stick),
                       (e.ABS_Z, trig), (e.ABS_RZ, trig), (e.ABS_HAT0X, hat), (e.ABS_HAT0Y, hat)],
        }
        # Identidad de mando Xbox 360 con cable. Es un dispositivo uinput, no XInput real.
        self.dev = UInput(caps, name=self.name, vendor=0x045e, product=0x028e,
                          version=0x0114, bustype=e.BUS_USB)
        self.state = protocol.neutral()

    def apply(self, state):
        e = self._e
        dirty = False
        for key, value in state.items():
            if self.state[key] == value:
                continue
            code = self.buttons.get(key)
            if code is not None:
                self.dev.write(e.EV_KEY, code, value)
            else:
                self.dev.write(e.EV_ABS, self.axes[key], value)
            dirty = True
        if dirty:
            self.dev.syn()
        self.state = state

    def reset(self):
        self.apply(protocol.neutral())

    def close(self):
        self.reset()
        self.dev.close()


def create_pad(kind):
    """kind: 'uinput' | 'null' | 'auto'."""
    if kind == 'null':
        return NullPad()
    try:
        return UInputPad()
    except Exception as ex:  # ImportError, PermissionError, FileNotFoundError...
        if kind == 'uinput':
            raise
        print(f'[pad] uinput no disponible ({ex!r}); usando NullPad', flush=True)
        return NullPad()
